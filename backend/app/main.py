from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.auth import router as auth_router
from app.api.routes.execution import router as execution_router
from app.api.routes.projects import files_router, projects_router
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.services.auth import AuthService
from app.services.code_runner import CodeRunner
from app.services.collaboration import CollaborationManager
from app.services.metrics import MetricsService
from app.services.projects import ProjectService
from app.services.redis_bus import RedisBus

logger = logging.getLogger(__name__)


async def wait_for_database(engine, settings: Settings) -> None:
    deadline = asyncio.get_running_loop().time() + settings.database_startup_timeout_seconds
    last_error: Exception | None = None

    while asyncio.get_running_loop().time() < deadline:
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            return
        except (OSError, OperationalError) as exc:
            last_error = exc
            logger.warning("Database not ready yet, retrying in %.1fs", settings.database_retry_interval_seconds)
            await asyncio.sleep(settings.database_retry_interval_seconds)

    if last_error is not None:
        raise last_error


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(resolved_settings.database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        await wait_for_database(engine, resolved_settings)

        auth_service = AuthService(session_factory, resolved_settings)
        project_service = ProjectService(session_factory, resolved_settings)
        metrics = MetricsService()
        collaboration_manager = CollaborationManager(project_service, resolved_settings, metrics)
        redis_bus = RedisBus(resolved_settings, collaboration_manager)
        collaboration_manager.attach_bus(redis_bus)
        code_runner = CodeRunner(
            timeout_seconds=resolved_settings.code_timeout_seconds,
            max_output_chars=resolved_settings.max_execution_output_chars,
            metrics=metrics,
        )

        app.state.settings = resolved_settings
        app.state.session_factory = session_factory
        app.state.auth_service = auth_service
        app.state.project_service = project_service
        app.state.collaboration_manager = collaboration_manager
        app.state.redis_bus = redis_bus
        app.state.code_runner = code_runner

        await redis_bus.start()
        try:
            yield
        finally:
            await collaboration_manager.shutdown()
            await redis_bus.stop()
            await engine.dispose()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix=resolved_settings.api_prefix)
    app.include_router(projects_router, prefix=resolved_settings.api_prefix)
    app.include_router(files_router, prefix=resolved_settings.api_prefix)
    app.include_router(execution_router, prefix=resolved_settings.api_prefix)
    app.mount("/metrics", make_asgi_app())

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws/files/{file_id}")
    async def file_socket(websocket: WebSocket, file_id: str) -> None:
        token = websocket.query_params.get("token")
        session_id = websocket.query_params.get("session_id")
        color = websocket.query_params.get("color")
        if not token or not session_id or not color:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        auth_service = websocket.app.state.auth_service
        current_user = await auth_service.get_user_from_token(token)
        if current_user is None:
            await websocket.close(code=4401)
            return

        project_service = websocket.app.state.project_service
        if not await project_service.user_can_access_file(file_id, current_user.id):
            await websocket.close(code=4403)
            return

        manager = websocket.app.state.collaboration_manager
        connected = False
        try:
            await manager.connect(websocket, file_id, session_id, current_user.full_name, color)
            connected = True
            while True:
                message = await websocket.receive_text()
                await manager.handle_client_message(file_id, session_id, message)
        except LookupError:
            if not connected:
                await websocket.close(code=4404)
        except WebSocketDisconnect:
            pass
        finally:
            if connected:
                await manager.disconnect(file_id, session_id)

    return app


app = create_app()

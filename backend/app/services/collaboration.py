from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket
from y_py import YDoc, apply_update, encode_state_as_update

from app.core.config import Settings
from app.services.metrics import MetricsService
from app.services.projects import PersistedFile, ProjectService

if TYPE_CHECKING:
    from app.services.redis_bus import RedisBus

SUPPORTED_LANGUAGES = {"python", "javascript", "cpp"}


def encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


@dataclass(slots=True)
class ParticipantPresence:
    session_id: str
    display_name: str
    color: str
    connected_at: datetime
    selection_start: int | None = None
    selection_end: int | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "displayName": self.display_name,
            "color": self.color,
            "connectedAt": self.connected_at.isoformat(),
            "selectionStart": self.selection_start,
            "selectionEnd": self.selection_end,
        }


@dataclass(slots=True)
class ActiveConnection:
    session_id: str
    websocket: WebSocket


@dataclass
class DocumentRuntimeState:
    file_id: str
    project_id: str
    project_name: str
    name: str
    language: str
    doc: YDoc
    connections: dict[str, ActiveConnection] = field(default_factory=dict)
    participants: dict[str, ParticipantPresence] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    save_task: asyncio.Task[None] | None = None


class CollaborationManager:
    def __init__(
        self,
        project_service: ProjectService,
        settings: Settings,
        metrics: MetricsService,
    ) -> None:
        self._project_service = project_service
        self._settings = settings
        self._metrics = metrics
        self._documents: dict[str, DocumentRuntimeState] = {}
        self._documents_lock = asyncio.Lock()
        self._bus: RedisBus | None = None

    def attach_bus(self, bus: "RedisBus") -> None:
        self._bus = bus

    def _document_payload(self, state: DocumentRuntimeState) -> dict[str, Any]:
        return {
            "id": state.file_id,
            "name": state.name,
            "projectId": state.project_id,
            "projectName": state.project_name,
            "language": state.language,
            "shareUrl": f"{self._settings.public_frontend_url.rstrip('/')}/projects/{state.project_id}/files/{state.file_id}",
        }

    async def _ensure_document(self, file_id: str) -> DocumentRuntimeState:
        existing = self._documents.get(file_id)
        if existing is not None:
            return existing

        async with self._documents_lock:
            existing = self._documents.get(file_id)
            if existing is not None:
                return existing

            persisted = await self._project_service.get_persisted_file(file_id)
            if persisted is None:
                raise LookupError(file_id)

            document_state = self._build_runtime_state(persisted)
            self._documents[file_id] = document_state
            return document_state

    def _build_runtime_state(self, persisted: PersistedFile) -> DocumentRuntimeState:
        doc = YDoc()
        if persisted.latest_state:
            apply_update(doc, persisted.latest_state)

        return DocumentRuntimeState(
            file_id=persisted.id,
            project_id=persisted.project_id,
            project_name=persisted.project_name,
            name=persisted.name,
            language=persisted.language,
            doc=doc,
        )

    def _encode_full_document(self, state: DocumentRuntimeState) -> str:
        return encode_bytes(bytes(encode_state_as_update(state.doc)))

    async def connect(
        self,
        websocket: WebSocket,
        file_id: str,
        session_id: str,
        display_name: str,
        color: str,
    ) -> None:
        started_at = perf_counter()
        state = await self._ensure_document(file_id)

        if self._bus is not None:
            await self._bus.ensure_document_subscription(file_id)

        await websocket.accept()

        async with state.lock:
            existing_connection = state.connections.get(session_id)
            if existing_connection is not None:
                try:
                    await existing_connection.websocket.close(code=4001)
                except Exception:
                    pass

            state.connections[session_id] = ActiveConnection(session_id=session_id, websocket=websocket)
            state.participants[session_id] = ParticipantPresence(
                session_id=session_id,
                display_name=display_name,
                color=color,
                connected_at=datetime.now(timezone.utc),
            )

            snapshot_message = {
                "type": "file.snapshot",
                "payload": {
                    "file": self._document_payload(state),
                    "document": self._encode_full_document(state),
                    "participants": [presence.as_payload() for presence in state.participants.values()],
                },
            }

        self._metrics.connection_opened()
        self._metrics.observe_state_sync(perf_counter() - started_at)
        self._metrics.record_message("outbound", "file.snapshot")

        await websocket.send_json(snapshot_message)

        presence_payload = state.participants[session_id].as_payload()
        await self._broadcast_json(
            state,
            {"type": "presence.update", "payload": presence_payload},
            exclude={session_id},
        )
        await self._publish(
            file_id,
            {
                "file_id": file_id,
                "event_type": "presence.update",
                "payload": presence_payload,
            },
        )
        await self._publish(
            file_id,
            {
                "file_id": file_id,
                "event_type": "presence.request",
                "payload": {},
            },
        )

    async def disconnect(self, file_id: str, session_id: str) -> None:
        state = self._documents.get(file_id)
        if state is None:
            return

        removed_connection = False
        removed_participant = False

        async with state.lock:
            if state.connections.pop(session_id, None) is not None:
                removed_connection = True
            if state.participants.pop(session_id, None) is not None:
                removed_participant = True
            remaining_connections = len(state.connections)

        if removed_connection:
            self._metrics.connection_closed()

        if removed_participant:
            payload = {"sessionId": session_id}
            await self._broadcast_json(state, {"type": "presence.leave", "payload": payload})
            await self._publish(
                file_id,
                {
                    "file_id": file_id,
                    "event_type": "presence.leave",
                    "payload": payload,
                },
            )

        if remaining_connections == 0:
            await self.persist_document(file_id, source="disconnect")
            if self._bus is not None:
                await self._bus.maybe_remove_document_subscription(file_id)
            await self._drop_document_if_idle(file_id)

    async def _drop_document_if_idle(self, file_id: str) -> None:
        async with self._documents_lock:
            state = self._documents.get(file_id)
            if state is None or state.connections:
                return

            if state.save_task is not None:
                state.save_task.cancel()
            self._documents.pop(file_id, None)

    async def _send_to_session(self, file_id: str, session_id: str, payload: dict[str, Any]) -> None:
        state = self._documents.get(file_id)
        if state is None:
            return

        connection = state.connections.get(session_id)
        if connection is None:
            return

        await connection.websocket.send_json(payload)
        self._metrics.record_message("outbound", payload["type"])

    async def _broadcast_json(
        self,
        state: DocumentRuntimeState,
        payload: dict[str, Any],
        exclude: set[str] | None = None,
    ) -> None:
        dead_sessions: list[str] = []
        excluded = exclude or set()

        for session_id, connection in list(state.connections.items()):
            if session_id in excluded:
                continue
            try:
                await connection.websocket.send_json(payload)
                self._metrics.record_message("outbound", payload["type"])
            except Exception:
                dead_sessions.append(session_id)

        for dead_session in dead_sessions:
            await self.disconnect(state.file_id, dead_session)

    async def _publish(self, file_id: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        await self._bus.publish(file_id, payload)

    async def handle_client_message(self, file_id: str, session_id: str, raw_message: str) -> None:
        try:
            envelope = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send_to_session(
                file_id,
                session_id,
                {"type": "error", "payload": {"message": "Invalid JSON message."}},
            )
            return

        message_type = envelope.get("type")
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        self._metrics.record_message("inbound", str(message_type))

        if message_type == "document.update":
            await self._handle_document_update(file_id, session_id, payload)
            return
        if message_type == "presence.update":
            await self._handle_presence_update(file_id, session_id, payload)
            return
        if message_type == "file.language":
            await self._handle_language_update(file_id, payload)
            return

        await self._send_to_session(
            file_id,
            session_id,
            {"type": "error", "payload": {"message": f"Unsupported message type: {message_type}"}},
        )

    async def _handle_document_update(
        self,
        file_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        state = await self._ensure_document(file_id)
        update_value = payload.get("update")
        if not isinstance(update_value, str):
            await self._send_to_session(
                file_id,
                session_id,
                {"type": "error", "payload": {"message": "Missing document update payload."}},
            )
            return

        started_at = perf_counter()
        update = decode_bytes(update_value)
        async with state.lock:
            apply_update(state.doc, update)

        self._schedule_snapshot(file_id)
        self._metrics.observe_document_update(perf_counter() - started_at)

        message_id = payload.get("messageId")
        if isinstance(message_id, str):
            await self._send_to_session(
                file_id,
                session_id,
                {
                    "type": "document.ack",
                    "payload": {
                        "messageId": message_id,
                        "processedAt": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

        broadcast_message = {
            "type": "document.update",
            "payload": {
                "update": update_value,
                "sessionId": session_id,
                "messageId": message_id,
            },
        }
        await self._broadcast_json(state, broadcast_message, exclude={session_id})
        await self._publish(
            file_id,
            {
                "file_id": file_id,
                "event_type": "document.update",
                "payload": broadcast_message["payload"],
            },
        )

    async def _handle_presence_update(
        self,
        file_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        state = await self._ensure_document(file_id)
        async with state.lock:
            participant = state.participants.get(session_id)
            if participant is None:
                return
            participant.selection_start = self._coerce_offset(payload.get("selectionStart"))
            participant.selection_end = self._coerce_offset(payload.get("selectionEnd"))
            presence_payload = participant.as_payload()

        message = {"type": "presence.update", "payload": presence_payload}
        await self._broadcast_json(state, message, exclude={session_id})
        await self._publish(
            file_id,
            {
                "file_id": file_id,
                "event_type": "presence.update",
                "payload": presence_payload,
            },
        )

    async def _handle_language_update(self, file_id: str, payload: dict[str, Any]) -> None:
        language = payload.get("language")
        if language not in SUPPORTED_LANGUAGES:
            return

        state = await self._ensure_document(file_id)
        async with state.lock:
            state.language = language

        await self._project_service.update_file_language(file_id, language)
        message = {"type": "file.language", "payload": {"language": language}}
        await self._broadcast_json(state, message)
        await self._publish(
            file_id,
            {
                "file_id": file_id,
                "event_type": "file.language",
                "payload": {"language": language},
            },
        )

    def _coerce_offset(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        return None

    def _schedule_snapshot(self, file_id: str) -> None:
        state = self._documents.get(file_id)
        if state is None:
            return

        if state.save_task is not None:
            state.save_task.cancel()

        state.save_task = asyncio.create_task(self._debounced_persist(file_id))

    async def _debounced_persist(self, file_id: str) -> None:
        try:
            await asyncio.sleep(self._settings.snapshot_debounce_seconds)
            await self.persist_document(file_id, source="autosave")
        except asyncio.CancelledError:
            return

    async def persist_document(self, file_id: str, source: str) -> None:
        state = self._documents.get(file_id)
        if state is None:
            return

        started_at = perf_counter()
        async with state.lock:
            snapshot = bytes(encode_state_as_update(state.doc))
            language = state.language

        await self._project_service.save_file_state(file_id, language, snapshot, source=source)
        self._metrics.observe_snapshot_save(perf_counter() - started_at)

    async def handle_bus_event(self, payload: dict[str, Any]) -> None:
        file_id = payload.get("file_id")
        event_type = payload.get("event_type")
        if not isinstance(file_id, str) or not isinstance(event_type, str):
            return

        state = self._documents.get(file_id)
        if state is None:
            return

        event_payload = payload.get("payload", {})
        if not isinstance(event_payload, dict):
            return

        if event_type == "document.update":
            update_value = event_payload.get("update")
            if not isinstance(update_value, str):
                return
            async with state.lock:
                apply_update(state.doc, decode_bytes(update_value))
            self._schedule_snapshot(file_id)
            await self._broadcast_json(
                state,
                {"type": "document.update", "payload": event_payload},
                exclude={event_payload.get("sessionId")} if isinstance(event_payload.get("sessionId"), str) else None,
            )
            return

        if event_type == "presence.update":
            session_id = event_payload.get("sessionId")
            if not isinstance(session_id, str):
                return
            async with state.lock:
                state.participants[session_id] = ParticipantPresence(
                    session_id=session_id,
                    display_name=str(event_payload.get("displayName", "guest")),
                    color=str(event_payload.get("color", "#457b9d")),
                    connected_at=datetime.fromisoformat(
                        str(event_payload.get("connectedAt", datetime.now(timezone.utc).isoformat()))
                    ),
                    selection_start=self._coerce_offset(event_payload.get("selectionStart")),
                    selection_end=self._coerce_offset(event_payload.get("selectionEnd")),
                )
            await self._broadcast_json(state, {"type": "presence.update", "payload": event_payload})
            return

        if event_type == "presence.leave":
            session_id = event_payload.get("sessionId")
            if not isinstance(session_id, str):
                return
            async with state.lock:
                state.participants.pop(session_id, None)
            await self._broadcast_json(state, {"type": "presence.leave", "payload": {"sessionId": session_id}})
            return

        if event_type == "file.language":
            language = event_payload.get("language")
            if language not in SUPPORTED_LANGUAGES:
                return
            async with state.lock:
                state.language = language
            await self._broadcast_json(state, {"type": "file.language", "payload": {"language": language}})
            return

        if event_type == "presence.request":
            participants = list(state.participants.values())
            for participant in participants:
                await self._publish(
                    file_id,
                    {
                        "file_id": file_id,
                        "event_type": "presence.update",
                        "payload": participant.as_payload(),
                    },
                )

    async def shutdown(self) -> None:
        file_ids = list(self._documents.keys())
        for file_id in file_ids:
            await self.persist_document(file_id, source="shutdown")
        async with self._documents_lock:
            for state in self._documents.values():
                if state.save_task is not None:
                    state.save_task.cancel()
            self._documents.clear()

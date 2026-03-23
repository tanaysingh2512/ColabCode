from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_current_user
from app.db.models import User
from app.schemas.project import (
    FileCreateRequest,
    FileJoinResponse,
    FileResponse,
    FileSessionResponse,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectSummaryResponse,
)
from app.utils.presence import generate_color

projects_router = APIRouter(prefix="/projects", tags=["projects"])
files_router = APIRouter(prefix="/files", tags=["files"])


@projects_router.get("", response_model=list[ProjectSummaryResponse])
async def list_projects(
    request: Request,
    current_user: User = Depends(require_current_user),
) -> list[ProjectSummaryResponse]:
    return await request.app.state.project_service.list_projects_for_user(current_user.id)


@projects_router.post("", response_model=ProjectDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> ProjectDetailResponse:
    return await request.app.state.project_service.create_project(current_user, payload)


@projects_router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> ProjectDetailResponse:
    project = await request.app.state.project_service.get_project_for_user(project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@projects_router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
async def delete_project(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> Response:
    deleted = await request.app.state.project_service.delete_project(project_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.post("/{project_id}/files", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def create_file(
    project_id: str,
    payload: FileCreateRequest,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> FileResponse:
    try:
        file = await request.app.state.project_service.create_file(project_id, current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return file


@files_router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> FileResponse:
    file = await request.app.state.project_service.get_file_for_user(file_id, current_user.id)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return file


@files_router.post("/{file_id}/join", response_model=FileJoinResponse)
async def join_file(
    file_id: str,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> FileJoinResponse:
    try:
        joined = await request.app.state.project_service.join_file_for_user(file_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if joined is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return joined


@files_router.post("/{file_id}/sessions", response_model=FileSessionResponse)
async def create_file_session(
    file_id: str,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> FileSessionResponse:
    project_service = request.app.state.project_service
    if not await project_service.user_can_access_file(file_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    session_id = str(uuid4())
    return FileSessionResponse(
        session_id=session_id,
        display_name=current_user.full_name,
        color=generate_color(session_id),
    )

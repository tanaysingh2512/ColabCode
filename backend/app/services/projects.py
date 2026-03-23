from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from y_py import YDoc, encode_state_as_update

from app.core.config import Settings
from app.db.models import CodeFile, FileSnapshot, Project, ProjectMember, User
from app.schemas.project import (
    FileCreateRequest,
    FileJoinResponse,
    FileResponse,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectSummaryResponse,
)


@dataclass(slots=True)
class PersistedFile:
    id: str
    project_id: str
    project_name: str
    name: str
    language: str
    latest_state: bytes
    latest_state_size: int
    created_at: datetime
    updated_at: datetime


class ProjectService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def _create_initial_snapshot(self, content: str) -> bytes:
        doc = YDoc()
        text = doc.get_text(self._settings.document_state_key)
        if content:
            with doc.begin_transaction() as txn:
                text.insert(txn, 0, content)
        return bytes(encode_state_as_update(doc))

    def _file_share_url(self, project_id: str, file_id: str) -> str:
        base_url = self._settings.public_frontend_url.rstrip("/")
        return f"{base_url}/projects/{project_id}/files/{file_id}"

    def _file_to_response(self, file: CodeFile) -> FileResponse:
        return FileResponse(
            id=file.id,
            project_id=file.project_id,
            name=file.name,
            language=file.language,
            latest_state_size=file.latest_state_size,
            created_at=file.created_at,
            updated_at=file.updated_at,
            share_url=self._file_share_url(file.project_id, file.id),
        )

    def _project_to_summary(self, project: Project) -> ProjectSummaryResponse:
        default_file_id = project.files[0].id if project.files else None
        return ProjectSummaryResponse(
            id=project.id,
            name=project.name,
            owner_id=project.owner_id,
            share_mode=project.share_mode,
            file_count=len(project.files),
            default_file_id=default_file_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _project_to_detail(self, project: Project) -> ProjectDetailResponse:
        files = [self._file_to_response(file) for file in project.files]
        return ProjectDetailResponse(
            id=project.id,
            name=project.name,
            owner_id=project.owner_id,
            share_mode=project.share_mode,
            created_at=project.created_at,
            updated_at=project.updated_at,
            files=files,
        )

    async def create_project(self, owner: User, payload: ProjectCreateRequest) -> ProjectDetailResponse:
        snapshot = self._create_initial_snapshot(payload.initial_content)
        project = Project(
            id=str(uuid4()),
            name=payload.name.strip(),
            owner_id=owner.id,
            share_mode=payload.share_mode,
        )
        file = CodeFile(
            id=str(uuid4()),
            project_id=project.id,
            name=payload.initial_file_name.strip(),
            language=payload.language,
            latest_state=snapshot,
            latest_state_size=len(snapshot),
        )
        owner_membership = ProjectMember(project_id=project.id, user_id=owner.id, role="owner")
        file_snapshot = FileSnapshot(
            file_id=file.id,
            state=snapshot,
            size_bytes=len(snapshot),
            source="seed",
        )

        async with self._session_factory() as session:
            session.add(project)
            session.add(owner_membership)
            session.add(file)
            session.add(file_snapshot)
            await session.commit()
            project = await self._load_project(session, project.id, owner.id)
            assert project is not None
            return self._project_to_detail(project)

    async def _load_project(
        self,
        session: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        result = await session.execute(
            select(Project)
            .join(ProjectMember)
            .where(Project.id == project_id, ProjectMember.user_id == user_id)
            .options(selectinload(Project.files))
        )
        return result.scalar_one_or_none()

    async def list_projects_for_user(self, user_id: str) -> list[ProjectSummaryResponse]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project)
                .join(ProjectMember)
                .where(ProjectMember.user_id == user_id)
                .options(selectinload(Project.files))
                .order_by(Project.updated_at.desc())
            )
            projects = result.scalars().unique().all()
            return [self._project_to_summary(project) for project in projects]

    async def get_project_for_user(self, project_id: str, user_id: str) -> ProjectDetailResponse | None:
        async with self._session_factory() as session:
            project = await self._load_project(session, project_id, user_id)
            if project is None:
                return None
            return self._project_to_detail(project)

    async def delete_project(self, project_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project).where(Project.id == project_id, Project.owner_id == user_id),
            )
            project = result.scalar_one_or_none()
            if project is None:
                return False
            await session.delete(project)
            await session.commit()
            return True

    async def create_file(
        self,
        project_id: str,
        user_id: str,
        payload: FileCreateRequest,
    ) -> FileResponse | None:
        snapshot = self._create_initial_snapshot(payload.initial_content)
        async with self._session_factory() as session:
            project = await self._load_project(session, project_id, user_id)
            if project is None:
                return None

            file = CodeFile(
                id=str(uuid4()),
                project_id=project.id,
                name=payload.name.strip(),
                language=payload.language,
                latest_state=snapshot,
                latest_state_size=len(snapshot),
            )
            file_snapshot = FileSnapshot(
                file_id=file.id,
                state=snapshot,
                size_bytes=len(snapshot),
                source="seed",
            )
            session.add(file)
            session.add(file_snapshot)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValueError("A file with that name already exists in this project.") from None
            await session.refresh(file)
            return self._file_to_response(file)

    async def get_file_for_user(self, file_id: str, user_id: str) -> FileResponse | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CodeFile)
                .join(Project)
                .join(ProjectMember)
                .where(CodeFile.id == file_id, ProjectMember.user_id == user_id)
            )
            file = result.scalar_one_or_none()
            if file is None:
                return None
            return self._file_to_response(file)

    async def user_can_access_file(self, file_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(CodeFile)
                .join(Project)
                .join(ProjectMember)
                .where(CodeFile.id == file_id, ProjectMember.user_id == user_id)
            )
            return bool(result.scalar_one())

    async def get_persisted_file(self, file_id: str) -> PersistedFile | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CodeFile, Project.name)
                .join(Project)
                .where(CodeFile.id == file_id)
            )
            row = result.one_or_none()
            if row is None:
                return None
            file, project_name = row
            return PersistedFile(
                id=file.id,
                project_id=file.project_id,
                project_name=project_name,
                name=file.name,
                language=file.language,
                latest_state=file.latest_state or b"",
                latest_state_size=file.latest_state_size,
                created_at=file.created_at,
                updated_at=file.updated_at,
            )

    async def update_file_language(self, file_id: str, language: str) -> None:
        async with self._session_factory() as session:
            file = await session.get(CodeFile, file_id)
            if file is None:
                return
            file.language = language
            await session.commit()

    async def save_file_state(self, file_id: str, language: str, state: bytes, source: str) -> None:
        async with self._session_factory() as session:
            file = await session.get(CodeFile, file_id)
            if file is None:
                return

            file.language = language
            file.latest_state = state
            file.latest_state_size = len(state)
            snapshot = FileSnapshot(
                file_id=file_id,
                state=state,
                size_bytes=len(state),
                source=source,
            )
            session.add(snapshot)
            await session.commit()

    async def join_file_for_user(self, file_id: str, user: User) -> FileJoinResponse | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CodeFile, Project)
                .join(Project)
                .where(CodeFile.id == file_id)
            )
            row = result.one_or_none()
            if row is None:
                return None

            file, project = row
            membership_result = await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == user.id,
                )
            )
            membership = membership_result.scalar_one_or_none()
            if membership is None:
                if project.share_mode != "authenticated_link":
                    raise PermissionError("This project requires an explicit invite.")
                session.add(ProjectMember(project_id=project.id, user_id=user.id, role="editor"))
                await session.commit()

            return FileJoinResponse(
                project_id=project.id,
                file_id=file.id,
                share_mode=project.share_mode,
            )

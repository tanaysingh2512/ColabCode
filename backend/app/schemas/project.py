from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["python", "javascript", "cpp"]
ShareMode = Literal["private", "authenticated_link"]


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    initial_file_name: str = Field(default="main.py", min_length=1, max_length=160)
    language: Language = "python"
    initial_content: str = Field(default="", max_length=50000)
    share_mode: ShareMode = "authenticated_link"


class FileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    language: Language = "python"
    initial_content: str = Field(default="", max_length=50000)


class FileResponse(BaseModel):
    id: str
    project_id: str
    name: str
    language: Language
    latest_state_size: int
    created_at: datetime
    updated_at: datetime
    share_url: str


class ProjectSummaryResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    share_mode: ShareMode
    file_count: int
    default_file_id: str | None
    created_at: datetime
    updated_at: datetime


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    share_mode: ShareMode
    created_at: datetime
    updated_at: datetime
    files: list[FileResponse]


class FileSessionResponse(BaseModel):
    session_id: str
    display_name: str
    color: str


class FileJoinResponse(BaseModel):
    project_id: str
    file_id: str
    share_mode: ShareMode

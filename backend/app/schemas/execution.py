from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["python", "javascript", "cpp"]


class CodeExecutionRequest(BaseModel):
    language: Language
    code: str = Field(min_length=1, max_length=50000)
    stdin: str = Field(default="", max_length=5000)


class CodeExecutionResponse(BaseModel):
    language: Language
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False

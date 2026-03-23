from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_current_user
from app.db.models import User
from app.schemas.execution import CodeExecutionRequest, CodeExecutionResponse

router = APIRouter(prefix="/execute", tags=["execution"])


@router.post("", response_model=CodeExecutionResponse)
async def execute_code(
    payload: CodeExecutionRequest,
    request: Request,
    current_user: User = Depends(require_current_user),
) -> CodeExecutionResponse:
    runner = request.app.state.code_runner
    return await runner.execute(payload)

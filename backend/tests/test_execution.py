from __future__ import annotations

import pytest

from app.schemas.execution import CodeExecutionRequest
from app.services.code_runner import CodeRunner


@pytest.mark.asyncio
async def test_python_execution_returns_stdout() -> None:
    runner = CodeRunner(timeout_seconds=2, max_output_chars=2000)
    result = await runner.execute(CodeExecutionRequest(language="python", code="print('hello')"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.schemas.execution import CodeExecutionRequest, CodeExecutionResponse
from app.services.metrics import MetricsService

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None


@dataclass(slots=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


class CodeRunner:
    def __init__(
        self,
        timeout_seconds: float,
        max_output_chars: int,
        metrics: MetricsService | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars
        self._metrics = metrics

    def _limit_process_resources(self) -> None:
        if resource is None:
            return

        memory_limit = 256 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        resource.setrlimit(resource.RLIMIT_CPU, (int(self._timeout_seconds) + 1, int(self._timeout_seconds) + 1))

    def _truncate(self, value: str) -> str:
        if len(value) <= self._max_output_chars:
            return value
        return value[: self._max_output_chars] + "\n...[truncated]"

    async def _run_subprocess(
        self,
        command: list[str],
        cwd: Path,
        stdin: str = "",
    ) -> CommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                preexec_fn=self._limit_process_resources if resource is not None else None,
            )
        except FileNotFoundError:
            return CommandResult("", f"Required runtime not found: {command[0]}", 127, False)

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin.encode()),
                timeout=self._timeout_seconds,
            )
            timed_out = False
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            timed_out = True

        exit_code = process.returncode if process.returncode is not None else -1
        return CommandResult(
            stdout=self._truncate(stdout_bytes.decode(errors="replace")),
            stderr=self._truncate(stderr_bytes.decode(errors="replace")),
            exit_code=exit_code,
            timed_out=timed_out,
        )

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        started_at = perf_counter()

        with TemporaryDirectory(prefix="collabcode-exec-") as temp_dir:
            workspace = Path(temp_dir)
            if request.language == "python":
                source_path = workspace / "main.py"
                source_path.write_text(request.code, encoding="utf-8")
                result = await self._run_subprocess(["python3", str(source_path)], workspace, request.stdin)
            elif request.language == "javascript":
                source_path = workspace / "main.js"
                source_path.write_text(request.code, encoding="utf-8")
                result = await self._run_subprocess(["node", str(source_path)], workspace, request.stdin)
            else:
                source_path = workspace / "main.cpp"
                binary_path = workspace / "program"
                source_path.write_text(request.code, encoding="utf-8")
                compile_result = await self._run_subprocess(
                    ["g++", str(source_path), "-std=c++17", "-O2", "-o", str(binary_path)],
                    workspace,
                )
                if compile_result.exit_code != 0 or compile_result.timed_out:
                    result = compile_result
                else:
                    result = await self._run_subprocess([str(binary_path)], workspace, request.stdin)

        duration_seconds = perf_counter() - started_at
        if self._metrics is not None:
            self._metrics.observe_code_execution(request.language, duration_seconds)
            if result.exit_code != 0 or result.timed_out:
                self._metrics.record_code_execution_failure(request.language)

        return CodeExecutionResponse(
            language=request.language,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=int(duration_seconds * 1000),
            timed_out=result.timed_out,
        )

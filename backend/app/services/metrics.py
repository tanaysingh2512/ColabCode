from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

ACTIVE_WS_CONNECTIONS = Gauge(
    "collabcode_active_ws_connections",
    "Number of currently open WebSocket connections.",
)
WS_MESSAGES = Counter(
    "collabcode_ws_messages_total",
    "WebSocket messages processed by the server.",
    labelnames=("direction", "message_type"),
)
DOCUMENT_UPDATE_PROCESSING_SECONDS = Histogram(
    "collabcode_document_update_processing_seconds",
    "Server-side processing time for document updates.",
)
STATE_SYNC_SECONDS = Histogram(
    "collabcode_state_sync_seconds",
    "Time required to send an initial room snapshot after connect.",
)
SNAPSHOT_SAVE_SECONDS = Histogram(
    "collabcode_snapshot_save_seconds",
    "Time spent persisting room snapshots.",
)
CODE_EXECUTION_SECONDS = Histogram(
    "collabcode_code_execution_seconds",
    "Code execution duration by language.",
    labelnames=("language",),
)
CODE_EXECUTION_FAILURES = Counter(
    "collabcode_code_execution_failures_total",
    "Code execution failures by language.",
    labelnames=("language",),
)


class MetricsService:
    def connection_opened(self) -> None:
        ACTIVE_WS_CONNECTIONS.inc()

    def connection_closed(self) -> None:
        ACTIVE_WS_CONNECTIONS.dec()

    def record_message(self, direction: str, message_type: str) -> None:
        WS_MESSAGES.labels(direction=direction, message_type=message_type).inc()

    def observe_document_update(self, duration_seconds: float) -> None:
        DOCUMENT_UPDATE_PROCESSING_SECONDS.observe(duration_seconds)

    def observe_state_sync(self, duration_seconds: float) -> None:
        STATE_SYNC_SECONDS.observe(duration_seconds)

    def observe_snapshot_save(self, duration_seconds: float) -> None:
        SNAPSHOT_SAVE_SECONDS.observe(duration_seconds)

    def observe_code_execution(self, language: str, duration_seconds: float) -> None:
        CODE_EXECUTION_SECONDS.labels(language=language).observe(duration_seconds)

    def record_code_execution_failure(self, language: str) -> None:
        CODE_EXECUTION_FAILURES.labels(language=language).inc()

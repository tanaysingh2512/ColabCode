from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from redis import asyncio as redis
from redis.exceptions import RedisError

from app.core.config import Settings

if TYPE_CHECKING:
    from app.services.collaboration import CollaborationManager

logger = logging.getLogger(__name__)


class RedisBus:
    def __init__(self, settings: Settings, manager: "CollaborationManager") -> None:
        self._settings = settings
        self._manager = manager
        self._instance_id = str(uuid4())
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._subscribed_documents: set[str] = set()
        self._enabled = settings.redis_enabled

    def _channel_name(self, file_id: str) -> str:
        return f"collabcode:files:{file_id}"

    async def start(self) -> None:
        if not self._enabled:
            return

        self._redis = redis.from_url(self._settings.redis_url, encoding="utf-8", decode_responses=True)
        self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)

        try:
            await self._redis.ping()
        except RedisError as exc:
            logger.warning("Redis unavailable, falling back to single-instance mode: %s", exc)
            self._enabled = False
            self._redis = None
            self._pubsub = None
            return

        self._listen_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._pubsub is not None:
            await self._pubsub.close()

        if self._redis is not None:
            await self._redis.close()

    async def ensure_document_subscription(self, file_id: str) -> None:
        if not self._enabled or self._pubsub is None or file_id in self._subscribed_documents:
            return

        await self._pubsub.subscribe(self._channel_name(file_id))
        self._subscribed_documents.add(file_id)

    async def maybe_remove_document_subscription(self, file_id: str) -> None:
        if not self._enabled or self._pubsub is None or file_id not in self._subscribed_documents:
            return

        await self._pubsub.unsubscribe(self._channel_name(file_id))
        self._subscribed_documents.discard(file_id)

    async def publish(self, file_id: str, payload: dict[str, Any]) -> None:
        if not self._enabled or self._redis is None:
            return

        envelope = {"instance_id": self._instance_id, **payload}
        await self._redis.publish(self._channel_name(file_id), json.dumps(envelope))

    async def _listen(self) -> None:
        if self._pubsub is None:
            return

        while True:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.05)
                continue

            try:
                payload = json.loads(message["data"])
            except (TypeError, json.JSONDecodeError):
                logger.warning("Dropped invalid Redis payload: %s", message)
                continue

            if payload.get("instance_id") == self._instance_id:
                continue

            await self._manager.handle_bus_event(payload)

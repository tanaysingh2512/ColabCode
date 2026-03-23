from __future__ import annotations

import base64
import json
from time import perf_counter
from uuid import uuid4

import gevent
from gevent.lock import Semaphore
from locust import HttpUser, between, events, task
from websocket import WebSocketConnectionClosedException, create_connection
from y_py import YDoc, apply_update, encode_state_as_update, encode_state_vector

ROOM_LOCK = Semaphore()
ROOM_ID: str | None = None


def to_ws_url(host: str) -> str:
    if host.startswith("https://"):
        return "wss://" + host.removeprefix("https://")
    return "ws://" + host.removeprefix("http://")


def encode_update(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode_update(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def shared_room_id(client) -> str:
    global ROOM_ID
    if ROOM_ID is not None:
        return ROOM_ID

    with ROOM_LOCK:
        if ROOM_ID is not None:
            return ROOM_ID
        response = client.post(
            "/api/v1/rooms",
            json={
                "name": "Locust Load Room",
                "language": "python",
                "initial_content": "print('load test')\n",
            },
            name="/api/v1/rooms",
        )
        response.raise_for_status()
        ROOM_ID = response.json()["id"]
        return ROOM_ID


class CollaborativeUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self) -> None:
        self.room_id = shared_room_id(self.client)
        session_response = self.client.post(
            f"/api/v1/rooms/{self.room_id}/sessions",
            json={"display_name": f"locust-{uuid4().hex[:6]}"},
            name="/api/v1/rooms/[id]/sessions",
        )
        session_response.raise_for_status()
        session = session_response.json()

        self.session_id = session["session_id"]
        self.display_name = session["display_name"]
        self.color = session["color"]
        self.pending: dict[str, float] = {}
        self.doc = YDoc()
        self.text = self.doc.get_text("code")

        ws_url = (
            f"{to_ws_url(self.host)}/ws/rooms/{self.room_id}"
            f"?session_id={self.session_id}"
            f"&display_name={self.display_name}"
            f"&color={self.color}"
        )
        self.socket = create_connection(ws_url, timeout=5)
        snapshot = json.loads(self.socket.recv())
        apply_update(self.doc, decode_update(snapshot["payload"]["document"]))

        self._stopped = False
        self.listener = gevent.spawn(self._listen)
        self._send_presence()

    def on_stop(self) -> None:
        self._stopped = True
        if hasattr(self, "listener"):
            self.listener.kill(block=False)
        if hasattr(self, "socket"):
            try:
                self.socket.close()
            except WebSocketConnectionClosedException:
                pass

    def _send_presence(self) -> None:
        self.socket.send(json.dumps({"type": "presence.update", "payload": {"selectionStart": 0, "selectionEnd": 0}}))

    def _listen(self) -> None:
        while not self._stopped:
            try:
                raw_message = self.socket.recv()
            except Exception:
                gevent.sleep(0.1)
                continue

            if not raw_message:
                continue

            message = json.loads(raw_message)
            if message["type"] == "document.update":
                apply_update(self.doc, decode_update(message["payload"]["update"]))
            elif message["type"] == "document.ack":
                message_id = message["payload"]["messageId"]
                started_at = self.pending.pop(message_id, None)
                if started_at is not None:
                    events.request.fire(
                        request_type="ws",
                        name="document.update",
                        response_time=(perf_counter() - started_at) * 1000,
                        response_length=0,
                        exception=None,
                    )

    @task(3)
    def edit_document(self) -> None:
        state_vector = encode_state_vector(self.doc)
        snippet = f"\n# locust-{uuid4().hex[:6]}"
        with self.doc.begin_transaction() as txn:
            self.text.insert(txn, len(str(self.text)), snippet)

        update = bytes(encode_state_as_update(self.doc, state_vector))
        message_id = uuid4().hex
        self.pending[message_id] = perf_counter()
        self.socket.send(
            json.dumps(
                {
                    "type": "document.update",
                    "payload": {
                        "update": encode_update(update),
                        "messageId": message_id,
                    },
                }
            )
        )

    @task(1)
    def send_presence(self) -> None:
        self._send_presence()

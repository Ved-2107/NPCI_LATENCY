"""WebSocket event broadcasting for real-time dashboard updates.

Events are emitted whenever a remittance changes state. Connected WebSocket
clients receive JSON messages with the event type, remittance ID, new status,
and a timestamp.
"""
import asyncio
import json
import time
from typing import Set

from fastapi import WebSocket


class EventBroadcaster:
    """Manages WebSocket connections and broadcasts state-change events."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._event_log: list = []
        self._max_log = 500
        self._loop = None  # will be set when the first WS connects (main event loop)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        # Capture the main event loop for cross-thread dispatch
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, event: dict):
        """Send an event to all connected clients and log it."""
        event["timestamp"] = time.time()
        event["iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._event_log.append(event)
        if len(self._event_log) > self._max_log:
            self._event_log = self._event_log[-self._max_log:]
        message = json.dumps(event)
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    def emit_sync(self, event: dict):
        """Non-async wrapper for use in synchronous ledger code.
        Schedules the broadcast on the main event loop using threadsafe dispatch."""
        event["timestamp"] = time.time()
        event["iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._event_log.append(event)
        if len(self._event_log) > self._max_log:
            self._event_log = self._event_log[-self._max_log:]
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast_existing(event), self._loop)
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast_existing(event))
            except RuntimeError:
                pass  # no event loop running (e.g., in unit tests)

    async def _broadcast_existing(self, event: dict):
        message = json.dumps(event)
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    @property
    def recent_events(self) -> list:
        return list(self._event_log)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Global broadcaster instance
broadcaster = EventBroadcaster()

"""WebSocket event broadcasting for real-time dashboard updates.

Events are emitted whenever a remittance changes state. Connected WebSocket
clients receive JSON messages with the event type, remittance ID, new status,
and a timestamp.
"""
import asyncio
import json
import logging
import threading
import time
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("remitchain.events")


class EventBroadcaster:
    """Manages WebSocket connections and broadcasts state-change events."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._event_log: list = []
        self._max_log = 500
        self._lock = threading.Lock()
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self._connections.add(ws)
            if not self.loop:
                try:
                    self.loop = asyncio.get_running_loop()
                except Exception:
                    pass
            count = len(self._connections)
        logger.info("WebSocket client connected. Active connections: %d", count)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            self._connections.discard(ws)
            count = len(self._connections)
        logger.info("WebSocket client disconnected. Active connections: %d", count)

    async def broadcast(self, event: dict):
        """Send an event to all connected clients and log it."""
        event["timestamp"] = time.time()
        event["iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
            targets = list(self._connections)
        message = json.dumps(event)
        dead = set()
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        if dead:
            with self._lock:
                self._connections -= dead

    def emit_sync(self, event: dict):
        """Non-async wrapper for use in synchronous ledger code.
        Schedules the broadcast on the main event loop across threads."""
        event["timestamp"] = time.time()
        event["iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast_existing(event), self.loop)
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast_existing(event))
            except RuntimeError:
                pass  # no event loop running (e.g. in standalone tests without loop)

    async def _broadcast_existing(self, event: dict):
        message = json.dumps(event)
        with self._lock:
            targets = list(self._connections)
        dead = set()
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        if dead:
            with self._lock:
                self._connections -= dead

    @property
    def recent_events(self) -> list:
        with self._lock:
            return list(self._event_log)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)


# Global broadcaster instance
broadcaster = EventBroadcaster()

"""WebSocket manager and endpoint for real-time project event streaming."""

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "redis://localhost:6379/1")


class ConnectionManager:
    """Maintains active WebSocket connections per project_id.

    Each project can have multiple dashboard clients connected. Messages
    are broadcast to all clients watching the same project.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._listeners: dict[str, asyncio.Task] = {}

    async def connect(self, ws: WebSocket, project_id: str) -> None:
        """Accept a WebSocket and register it for project_id."""
        await ws.accept()
        self._connections.setdefault(project_id, []).append(ws)
        logger.info("WS connected: project=%s total=%d", project_id, len(self._connections[project_id]))

        # Start Redis listener if not running for this project
        if project_id not in self._listeners:
            self._listeners[project_id] = asyncio.create_task(
                self._redis_forwarder(project_id)
            )

    async def disconnect(self, ws: WebSocket, project_id: str) -> None:
        """Remove a WebSocket from project_id's connection list."""
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns and project_id in self._listeners:
            self._listeners[project_id].cancel()
            del self._listeners[project_id]
        logger.info("WS disconnected: project=%s remaining=%d", project_id, len(conns))

    async def broadcast(self, project_id: str, event: dict[str, Any]) -> None:
        """Send an event dict to all WebSocket clients for a project."""
        dead: list[WebSocket] = []
        for ws in self._connections.get(project_id, []):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, project_id)

    def get_connection_count(self, project_id: str) -> int:
        """Return number of connected clients for a project."""
        return len(self._connections.get(project_id, []))

    async def _redis_forwarder(self, project_id: str) -> None:
        """Background task: listen on Redis pub/sub and forward to WS clients."""
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(REDIS_PUBSUB_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"project:{project_id}")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                await self.broadcast(project_id, data)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Redis forwarder error (project=%s): %s", project_id, exc)


# Singleton — shared across the app
manager = ConnectionManager()

router = APIRouter()


@router.websocket("/projects/{project_id}")
async def project_ws(ws: WebSocket, project_id: str) -> None:
    """WebSocket endpoint for real-time project events."""
    await manager.connect(ws, project_id)
    try:
        # Keep connection alive until client disconnects
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws, project_id)

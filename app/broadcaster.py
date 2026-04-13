"""
WebSocket connection manager.
Broadcasts new-request events to all connected dashboard clients.
"""

import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)
        logger.debug("WS client connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)
        logger.debug("WS client disconnected (%d total)", len(self.active))

    async def broadcast(self, data: dict) -> None:
        if not self.active:
            return
        dead: Set[WebSocket] = set()
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self.active -= dead


# Singleton shared across the app
manager = ConnectionManager()

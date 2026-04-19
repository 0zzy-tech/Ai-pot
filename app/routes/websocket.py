"""
WebSocket endpoint for real-time dashboard updates.
Token-authenticated: client must supply ?token=<sha256(ADMIN_PASSWORD)>.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.broadcaster import manager
from config import Config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = ""):
    if token != Config.WS_TOKEN:
        await ws.close(code=1008)   # Policy Violation — wrong token
        logger.debug("WebSocket connection rejected: bad token")
        return
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; dashboard only receives, never sends
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logger.debug("WebSocket error: %s", exc)
        manager.disconnect(ws)

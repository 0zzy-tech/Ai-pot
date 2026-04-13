"""
WebSocket endpoint for real-time dashboard updates.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.broadcaster import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
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

"""
Deception callback endpoint.
GET /track/{token}  — public, no auth — returns a 1×1 transparent GIF.
When an attacker follows a deception URL, this fires. The ASGI middleware logs
the request normally; the classifier flags /track/ paths as CRITICAL.
"""

import base64

from fastapi import APIRouter, Response

from app.deception import lookup_token

router = APIRouter()

# 1×1 transparent GIF (35 bytes)
_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@router.get("/track/{token}")
async def deception_callback(token: str):
    """
    Tracking pixel endpoint.  Called when an attacker follows a deception URL.
    The middleware already logs this request; the classifier marks it CRITICAL.
    We just return a silent 1×1 GIF so the request completes normally.
    """
    original_ip = lookup_token(token)
    # original_ip is informational — the actual logging happens in the middleware
    _ = original_ip
    return Response(content=_PIXEL, media_type="image/gif")

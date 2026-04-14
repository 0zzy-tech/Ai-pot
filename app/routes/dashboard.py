"""
Dashboard routes:
  GET  /__admin/           — serves the HTML dashboard
  GET  /__admin/api/stats  — aggregate stats for charts
  GET  /__admin/api/requests — paginated request feed
  GET  /__admin/api/map-data — geo-located IPs for map pins
  GET  /__admin/api/services — list all services with enabled state
  POST /__admin/api/services/{service_id}/toggle — enable/disable a service
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app import service_registry
from app.broadcaster import manager
from app.database import get_map_data, get_requests, get_stats
from config import Config

router = APIRouter(prefix=Config.ADMIN_PREFIX)
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()


def _check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(
        credentials.username.encode(), Config.ADMIN_USERNAME.encode()
    )
    correct_pass = secrets.compare_digest(
        credentials.password.encode(), Config.ADMIN_PASSWORD.encode()
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ── Dashboard HTML ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, _: str = Depends(_check_auth)):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":      request,
            "host":         request.headers.get("host", "localhost"),
            "admin_prefix": Config.ADMIN_PREFIX,
        },
    )


# ── Request data ───────────────────────────────────────────────────────────────

@router.get("/api/stats")
async def api_stats(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_stats())


@router.get("/api/requests")
async def api_requests(
    page:     int           = Query(1,    ge=1),
    limit:    int           = Query(50,   ge=1, le=200),
    risk:     Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    _: str = Depends(_check_auth),
):
    rows = await get_requests(page=page, limit=limit, risk=risk, category=category)
    return JSONResponse(content=rows)


@router.get("/api/map-data")
async def api_map_data(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_map_data())


# ── Service management ────────────────────────────────────────────────────────

@router.get("/api/services")
async def api_get_services(_: str = Depends(_check_auth)):
    """Return all service definitions with their current enabled state."""
    return JSONResponse(content=service_registry.get_all_service_states())


@router.post("/api/services/{service_id}/toggle")
async def api_toggle_service(
    service_id: str,
    _: str = Depends(_check_auth),
):
    """Toggle a service on or off. Broadcasts update to all dashboard clients."""
    if service_id not in service_registry.SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id!r}")

    current = service_registry.is_service_enabled(service_id)
    new_state = not current
    await service_registry.set_service_enabled(service_id, new_state)

    # Broadcast to all connected dashboard clients
    await manager.broadcast({
        "type": "service_update",
        "data": {"id": service_id, "enabled": new_state},
    })

    return JSONResponse(content={
        "id":      service_id,
        "enabled": new_state,
    })

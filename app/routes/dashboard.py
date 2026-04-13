"""
Dashboard routes:
  GET  /__admin/           — serves the HTML dashboard
  GET  /__admin/api/stats  — aggregate stats for charts
  GET  /__admin/api/requests — paginated request feed
  GET  /__admin/api/map-data — geo-located IPs for map pins
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

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


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, _: str = Depends(_check_auth)):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":  request,
            "host":     request.headers.get("host", "localhost"),
            "admin_prefix": Config.ADMIN_PREFIX,
        },
    )


# ── REST API ──────────────────────────────────────────────────────────────────

@router.get("/api/stats")
async def api_stats(_: str = Depends(_check_auth)):
    stats = await get_stats()
    return JSONResponse(content=stats)


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
    data = await get_map_data()
    return JSONResponse(content=data)

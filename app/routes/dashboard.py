"""
Dashboard routes:
  GET  /__admin/           — serves the HTML dashboard
  GET  /__admin/api/stats  — aggregate stats for charts
  GET  /__admin/api/requests — paginated request feed
  GET  /__admin/api/map-data — geo-located IPs for map pins
  GET  /__admin/api/services — list all services with enabled state
  POST /__admin/api/services/{service_id}/toggle — enable/disable a service
"""

import csv
import io
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app import service_registry
from app.broadcaster import manager
from app.database import (
    add_allowed_ip,
    add_custom_rule,
    clear_all_requests,
    delete_custom_rule,
    get_allowed_ips,
    get_blocked_ips,
    get_custom_rules,
    get_deception_callbacks,
    get_hourly_heatmap,
    get_ip_note,
    get_map_data,
    get_request_by_id,
    get_requests,
    get_requests_by_ip,
    get_requests_for_export,
    get_stats,
    get_threat_report_data,
    get_weekly_trend,
    remove_allowed_ip,
    stream_requests_csv,
    update_custom_rule,
)
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
        request,
        "dashboard.html",
        {
            "host":         request.headers.get("host", "localhost"),
            "admin_prefix": Config.ADMIN_PREFIX,
            "ws_token":     Config.WS_TOKEN,
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
    q:        Optional[str] = Query(None),
    _: str = Depends(_check_auth),
):
    rows = await get_requests(page=page, limit=limit, risk=risk, category=category, q=q)
    return JSONResponse(content=rows)


@router.get("/api/requests/{request_id}")
async def api_request_detail(request_id: int, _: str = Depends(_check_auth)):
    """Return full record for a single request (headers + body)."""
    row = await get_request_by_id(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return JSONResponse(content=row)


@router.get("/api/map-data")
async def api_map_data(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_map_data())


# ── Service management ────────────────────────────────────────────────────────

@router.get("/api/services")
async def api_get_services(_: str = Depends(_check_auth)):
    """Return all service definitions with their current enabled state."""
    return JSONResponse(content=service_registry.get_all_service_states())


@router.post("/api/requests/clear")
async def api_clear_requests(_: str = Depends(_check_auth)):
    """Delete all logged request data from the database."""
    await clear_all_requests()
    return JSONResponse(content={"cleared": True})


@router.get("/api/export/{service_id}.csv")
async def export_service_csv(service_id: str, _: str = Depends(_check_auth)):
    """Download all requests for a specific honeypot service as a CSV file."""
    if service_id not in service_registry.SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id!r}")
    defn = service_registry.SERVICES[service_id]
    rows = await get_requests_for_export(defn["prefixes"], defn["exact"])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "timestamp", "ip", "method", "path", "category", "risk_level",
        "user_agent", "country", "city", "asn", "flagged_patterns", "body",
    ])
    writer.writeheader()
    writer.writerows(rows)

    filename = (
        f"honeypot_{service_id}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/services/reset")
async def api_reset_services(_: str = Depends(_check_auth)):
    """Re-enable all honeypot services and broadcast the change to all dashboard clients."""
    await service_registry.reset_all_services()
    for sid in service_registry.SERVICES:
        await manager.broadcast({"type": "service_update", "data": {"id": sid, "enabled": True}})
    return JSONResponse(content={"reset": True})


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


# ── Tarpit ────────────────────────────────────────────────────────────────────

@router.post("/api/services/{service_id}/tarpit")
async def api_toggle_tarpit(service_id: str, _: str = Depends(_check_auth)):
    """Toggle tarpit mode for a service. Broadcasts update to all dashboard clients."""
    if service_id not in service_registry.SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id!r}")

    current = service_registry.is_service_tarpitted(service_id)
    new_state = not current
    await service_registry.set_service_tarpitted(service_id, new_state)

    await manager.broadcast({
        "type": "tarpit_update",
        "data": {"id": service_id, "tarpitted": new_state},
    })

    return JSONResponse(content={"id": service_id, "tarpitted": new_state})


# ── Per-IP session view ───────────────────────────────────────────────────────

@router.get("/api/ip/{ip}/requests")
async def api_ip_requests(ip: str, _: str = Depends(_check_auth)):
    """All requests from a specific IP address, oldest-first."""
    rows = await get_requests_by_ip(ip)
    return JSONResponse(content=rows)


@router.get("/api/ip/{ip}/enrichment")
async def api_ip_enrichment(ip: str, _: str = Depends(_check_auth)):
    """Cached enrichment data for a single IP (geo, reputation, feeds)."""
    from app.database import get_ip_cache
    cached = await get_ip_cache(ip)
    if not cached:
        return JSONResponse(content={})
    return JSONResponse(content={
        "isp":                      cached.get("isp"),
        "hosting":                  bool(cached.get("hosting")) if cached.get("hosting") is not None else None,
        "reverse_dns":              cached.get("reverse_dns"),
        "abuse_score":              cached.get("abuse_score"),
        "is_tor":                   bool(cached.get("is_tor")) if cached.get("is_tor") is not None else False,
        "threatfox_hit":            cached.get("threatfox_hit"),
        "greynoise_classification": cached.get("greynoise_classification"),
        "greynoise_noise":          bool(cached.get("greynoise_noise")) if cached.get("greynoise_noise") is not None else None,
        "greynoise_riot":           bool(cached.get("greynoise_riot")) if cached.get("greynoise_riot") is not None else None,
        "greynoise_name":           cached.get("greynoise_name"),
    })


# ── Webhook config + test ─────────────────────────────────────────────────────

@router.get("/api/webhooks/config")
async def api_webhook_config(_: str = Depends(_check_auth)):
    """Returns current webhook configuration (URLs are not exposed for security)."""
    return JSONResponse(content={
        "url_count":   len(Config.WEBHOOK_URLS),
        "format":      Config.WEBHOOK_FORMAT,
        "risk_levels": sorted(Config.WEBHOOK_RISK_LEVELS),
        "configured":  bool(Config.WEBHOOK_URLS),
    })


@router.post("/api/webhooks/test")
async def api_webhook_test(_: str = Depends(_check_auth)):
    """Send a test alert to all configured webhooks."""
    from app.webhooks import fire_webhooks
    test_record = {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "ip":              "1.2.3.4",
        "method":          "POST",
        "path":            "/v1/chat/completions",
        "category":        "attack",
        "risk_level":      "CRITICAL",
        "user_agent":      "test-client/1.0",
        "country":         "Test Country",
        "city":            "Test City",
        "flagged_patterns": json.dumps(["test_webhook_alert"]),
    }
    await fire_webhooks(test_record)
    return JSONResponse(content={
        "sent":   len(Config.WEBHOOK_URLS),
        "format": Config.WEBHOOK_FORMAT,
    })


# ── Canary token ──────────────────────────────────────────────────────────────

@router.get("/api/canary-token")
async def api_canary_token(_: str = Depends(_check_auth)):
    """Return the current session canary token for operator reference."""
    from app.canary import get_canary_token
    return JSONResponse(content={"token": get_canary_token()})


# ── IP blocking ──────────────────────────────────────────────────────────────

@router.get("/api/blocked-ips")
async def api_get_blocked_ips(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_blocked_ips())


@router.post("/api/blocked-ips")
async def api_block_ip(request: Request, _: str = Depends(_check_auth)):
    body = await request.json()
    ip = body.get("ip", "").strip()
    reason = body.get("reason", "manual block").strip() or "manual block"
    if not ip:
        raise HTTPException(status_code=400, detail="ip required")
    from app import service_registry
    await service_registry.block_ip(ip, reason)
    await manager.broadcast({"type": "ip_blocked", "data": {"ip": ip, "reason": reason}})
    return JSONResponse(content={"ip": ip, "reason": reason, "blocked": True})


@router.delete("/api/blocked-ips/{ip}")
async def api_unblock_ip(ip: str, _: str = Depends(_check_auth)):
    from app import service_registry
    await service_registry.unblock_ip(ip)
    await manager.broadcast({"type": "ip_unblocked", "data": {"ip": ip}})
    return JSONResponse(content={"ip": ip, "blocked": False})


@router.post("/api/requests/{request_id}/block-ip")
async def api_block_ip_from_request(request_id: int, _: str = Depends(_check_auth)):
    """Block the IP that made a specific request."""
    row = await get_request_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    ip = row["ip"]
    reason = f"manual block from request #{request_id}"
    from app import service_registry
    await service_registry.block_ip(ip, reason)
    await manager.broadcast({"type": "ip_blocked", "data": {"ip": ip, "reason": reason}})
    return JSONResponse(content={"ip": ip, "blocked": True})


# ── IP allow-list ─────────────────────────────────────────────────────────────

@router.get("/api/allowed-ips")
async def api_get_allowed_ips(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_allowed_ips())


@router.post("/api/allowed-ips")
async def api_allow_ip(request: Request, _: str = Depends(_check_auth)):
    body = await request.json()
    ip = body.get("ip", "").strip()
    label = body.get("label", "").strip() or "manual"
    if not ip:
        raise HTTPException(status_code=400, detail="ip required")
    from app import service_registry
    await service_registry.allow_ip(ip, label)
    return JSONResponse(content={"ip": ip, "label": label, "allowed": True})


@router.delete("/api/allowed-ips/{ip}")
async def api_unallow_ip(ip: str, _: str = Depends(_check_auth)):
    from app import service_registry
    await service_registry.unallow_ip(ip)
    return JSONResponse(content={"ip": ip, "allowed": False})


# ── IP notes ─────────────────────────────────────────────────────────────────

@router.get("/api/ip-notes/{ip}")
async def api_get_ip_note(ip: str, _: str = Depends(_check_auth)):
    note = await get_ip_note(ip)
    return JSONResponse(content={"ip": ip, "note": note})


@router.post("/api/ip-notes/{ip}")
async def api_set_ip_note(ip: str, request: Request, _: str = Depends(_check_auth)):
    body = await request.json()
    note = body.get("note", "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="note required")
    from app import service_registry
    await service_registry.set_ip_note(ip, note)
    return JSONResponse(content={"ip": ip, "note": note})


@router.delete("/api/ip-notes/{ip}")
async def api_delete_ip_note(ip: str, _: str = Depends(_check_auth)):
    from app import service_registry
    await service_registry.delete_ip_note(ip)
    return JSONResponse(content={"ip": ip, "note": None})


# ── Custom detection rules ────────────────────────────────────────────────────

@router.get("/api/custom-rules")
async def api_get_custom_rules(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_custom_rules())


@router.post("/api/custom-rules")
async def api_add_custom_rule(request: Request, _: str = Depends(_check_auth)):
    body = await request.json()
    name       = body.get("name", "").strip()
    pattern    = body.get("pattern", "").strip()
    risk_level = body.get("risk_level", "HIGH").upper()
    flag_name  = body.get("flag_name", name.lower().replace(" ", "_")).strip()
    if not name or not pattern:
        raise HTTPException(status_code=400, detail="name and pattern required")
    if risk_level not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        raise HTTPException(status_code=400, detail="invalid risk_level")
    # Validate regex
    import re
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"invalid regex: {exc}")
    rule_id = await add_custom_rule(name=name, pattern=pattern, risk_level=risk_level, flag_name=flag_name)
    # Hot-reload
    from app.custom_rules import reload_rules
    reload_rules(await get_custom_rules())
    return JSONResponse(content={"id": rule_id, "name": name, "pattern": pattern,
                                  "risk_level": risk_level, "flag_name": flag_name})


@router.patch("/api/custom-rules/{rule_id}")
async def api_update_custom_rule(rule_id: int, request: Request, _: str = Depends(_check_auth)):
    body = await request.json()
    # Fetch existing rule to allow partial updates
    rules = await get_custom_rules()
    existing = next((r for r in rules if r["id"] == rule_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    merged = {**existing, **body}
    await update_custom_rule(
        rule_id,
        name=merged["name"],
        pattern=merged["pattern"],
        risk_level=merged["risk_level"],
        flag_name=merged["flag_name"],
        enabled=bool(merged["enabled"]),
    )
    from app.custom_rules import reload_rules
    reload_rules(await get_custom_rules())
    return JSONResponse(content={"id": rule_id, "updated": True})


@router.delete("/api/custom-rules/{rule_id}")
async def api_delete_custom_rule(rule_id: int, _: str = Depends(_check_auth)):
    await delete_custom_rule(rule_id)
    from app.custom_rules import reload_rules
    reload_rules(await get_custom_rules())
    return JSONResponse(content={"id": rule_id, "deleted": True})


# ── Deception callbacks ───────────────────────────────────────────────────────

@router.get("/api/deception/callbacks")
async def api_deception_callbacks(
    limit: int = Query(100, ge=1, le=1000),
    _: str = Depends(_check_auth),
):
    rows = await get_deception_callbacks(limit=limit)
    return JSONResponse(content=rows)


@router.get("/api/deception/token")
async def api_deception_token(_: str = Depends(_check_auth)):
    from app.deception import get_session_token
    token = get_session_token()
    # Build full callback URL — use the request host
    return JSONResponse(content={"token": token})


# ── Threat feed stats ─────────────────────────────────────────────────────────

@router.get("/api/threat-feeds")
async def api_threat_feeds(_: str = Depends(_check_auth)):
    from app.threatfeeds import feed_stats
    return JSONResponse(content=feed_stats())


# ── Full CSV export ───────────────────────────────────────────────────────────

@router.get("/api/export/requests.csv")
async def api_export_requests_csv(
    risk:     Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ip:       Optional[str] = Query(None),
    since:    Optional[str] = Query(None),
    limit:    int            = Query(50000, ge=1, le=500000),
    _: str = Depends(_check_auth),
):
    """Stream all (or filtered) requests as a CSV download."""
    filename = (
        f"honeypot_requests_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    return StreamingResponse(
        stream_requests_csv(risk=risk, category=category, ip=ip, since=since, limit=limit),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Intelligence charts ───────────────────────────────────────────────────────

@router.get("/api/stats/weekly")
async def api_weekly_trend(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_weekly_trend())


@router.get("/api/stats/heatmap")
async def api_hourly_heatmap(_: str = Depends(_check_auth)):
    return JSONResponse(content=await get_hourly_heatmap())


# ── Threat report ─────────────────────────────────────────────────────────────

@router.get("/api/report.html", response_class=HTMLResponse)
async def api_threat_report(_: str = Depends(_check_auth)):
    """Self-contained HTML threat report for download."""
    s = await get_stats()
    r = await get_threat_report_data()
    return HTMLResponse(content=_build_report_html(s, r))


def _build_report_html(s: dict, r: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_risk = s.get("by_risk", {})

    ip_rows = "".join(
        f"<tr><td>{h['ip']}</td><td>{h.get('country') or '—'}</td><td>{h.get('city') or '—'}</td>"
        f"<td>{h['cnt']:,}</td><td>{h.get('max_risk','?')}</td><td>{(h.get('last_seen') or '')[:19]}</td></tr>"
        for h in r["top_ips"]
    )
    path_rows = "".join(
        f"<tr><td style='font-family:monospace'>{h['path']}</td><td>{h['cnt']:,}</td><td>{h.get('max_risk','?')}</td></tr>"
        for h in r["top_paths"]
    )
    pat_rows = "".join(
        f"<tr><td style='font-family:monospace'>{p}</td><td>{c:,}</td></tr>"
        for p, c in r["top_patterns"]
    )
    geo_rows = "".join(
        f"<tr><td>{h.get('country') or '—'}</td><td>{h['cnt']:,}</td></tr>"
        for h in r["geo_breakdown"]
    )

    # Inline map data as JSON — safe because values come from our own DB
    map_points_json = json.dumps(r.get("map_points", []))
    max_cnt = max((p["cnt"] for p in r.get("map_points", []) if p.get("cnt")), default=1)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>AI Honeypot Threat Report — {now}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="anonymous">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:24px 28px}}
  h1{{color:#f85149;margin-bottom:4px;font-size:22px}}
  h2{{color:#58a6ff;font-size:12px;text-transform:uppercase;letter-spacing:1px;margin:28px 0 8px}}
  .meta{{color:#8b949e;font-size:13px;margin-bottom:24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px;margin-bottom:24px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;text-align:center}}
  .card .n{{font-size:24px;font-weight:700}}
  .card .l{{font-size:10px;color:#8b949e;text-transform:uppercase;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}}
  th{{text-align:left;padding:6px 10px;font-size:11px;color:#8b949e;background:#161b22;border-bottom:1px solid #30363d}}
  td{{padding:6px 10px;border-bottom:1px solid #21262d;word-break:break-all}}
  tr:hover td{{background:#161b22}}
  #report-map{{height:400px;border:1px solid #30363d;border-radius:6px;margin-bottom:8px;background:#0d1b2e}}
  .leaflet-container{{background:#0d1b2e!important}}
  .leaflet-popup-content-wrapper{{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px}}
  .leaflet-popup-tip{{background:#161b22}}
  .leaflet-popup-content{{font-size:12px;line-height:1.6}}
  .pdf-btn{{
    position:fixed;top:16px;right:16px;
    background:#21262d;border:1px solid #30363d;color:#e6edf3;
    font-size:12px;padding:6px 14px;border-radius:5px;cursor:pointer;
    font-family:inherit;z-index:9999;
  }}
  .pdf-btn:hover{{border-color:#58a6ff;color:#58a6ff}}
  @media print{{
    .pdf-btn,.no-print{{display:none!important}}
    body{{background:#fff;color:#000;padding:16px}}
    h1{{color:#c00}}
    h2{{color:#00f}}
    .card{{background:#f5f5f5;border-color:#ccc}}
    .card .l{{color:#666}}
    th{{background:#f0f0f0;color:#333}}
    td{{border-color:#ddd}}
    tr:hover td{{background:transparent}}
    table{{page-break-inside:avoid}}
  }}
</style>
</head><body>
<button class="pdf-btn no-print" onclick="window.print()">⬇ Save as PDF</button>
<h1>AI Honeypot — Threat Report</h1>
<div class="meta">Generated {now} &bull; {s.get('total',0):,} total requests &bull; {s.get('unique_ips',0):,} unique IPs</div>

<h2>Summary</h2>
<div class="grid">
  <div class="card"><div class="n">{s.get('total',0):,}</div><div class="l">Total</div></div>
  <div class="card"><div class="n">{s.get('last_24h',0):,}</div><div class="l">Last 24h</div></div>
  <div class="card"><div class="n">{s.get('unique_ips',0):,}</div><div class="l">Unique IPs</div></div>
  <div class="card"><div class="n" style="color:#f85149">{by_risk.get('CRITICAL',0):,}</div><div class="l">Critical</div></div>
  <div class="card"><div class="n" style="color:#d29922">{by_risk.get('HIGH',0):,}</div><div class="l">High</div></div>
  <div class="card"><div class="n" style="color:#e3b341">{by_risk.get('MEDIUM',0):,}</div><div class="l">Medium</div></div>
  <div class="card"><div class="n" style="color:#3fb950">{by_risk.get('LOW',0):,}</div><div class="l">Low</div></div>
</div>

<h2 class="no-print">Attacker Origins — World Map</h2>
<div id="report-map" class="no-print"></div>

<h2>Top Attacker IPs</h2>
<table><tr><th>IP</th><th>Country</th><th>City</th><th>Requests</th><th>Max Risk</th><th>Last Seen</th></tr>
{ip_rows or '<tr><td colspan="6" style="color:#8b949e">No data</td></tr>'}</table>

<h2>Top Attacked Paths</h2>
<table><tr><th>Path</th><th>Requests</th><th>Max Risk</th></tr>
{path_rows or '<tr><td colspan="3" style="color:#8b949e">No data</td></tr>'}</table>

<h2>Flagged Patterns (Top 15)</h2>
<table><tr><th>Pattern</th><th>Count</th></tr>
{pat_rows or '<tr><td colspan="2" style="color:#8b949e">No data</td></tr>'}</table>

<h2>Geographic Breakdown</h2>
<table><tr><th>Country</th><th>Requests</th></tr>
{geo_rows or '<tr><td colspan="2" style="color:#8b949e">No data</td></tr>'}</table>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin="anonymous"></script>
<script>
(function(){{
  var RISK_COLOR = {{CRITICAL:'#f85149',HIGH:'#d29922',MEDIUM:'#e3b341',LOW:'#3fb950'}};
  var points = {map_points_json};
  var maxCnt = {max_cnt};

  var map = L.map('report-map', {{zoomControl:true,attributionControl:false}});
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    maxZoom:18, subdomains:'abcd'
  }}).addTo(map);

  var bounds = [];
  points.forEach(function(p){{
    if (!p.lat || !p.lng) return;
    var r = Math.max(4, Math.min(18, 4 + 14 * Math.sqrt(p.cnt / maxCnt)));
    var color = RISK_COLOR[p.max_risk] || '#8b949e';
    var marker = L.circleMarker([p.lat, p.lng], {{
      radius: r,
      fillColor: color,
      color: color,
      weight: 1,
      opacity: 0.9,
      fillOpacity: 0.55,
    }}).addTo(map);
    marker.bindPopup(
      '<strong>' + (p.ip || '') + '</strong><br>' +
      (p.country || '') + '<br>' +
      p.cnt.toLocaleString() + ' request' + (p.cnt !== 1 ? 's' : '') + '<br>' +
      '<span style="color:' + color + '">' + p.max_risk + '</span>'
    );
    bounds.push([p.lat, p.lng]);
  }});

  if (bounds.length) {{
    map.fitBounds(bounds, {{padding:[24,24], maxZoom:6}});
  }} else {{
    map.setView([20, 0], 2);
  }}
}})();
</script>
</body></html>"""

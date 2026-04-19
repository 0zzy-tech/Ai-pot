"""
SMTP email alerting for high-severity honeypot events.
Uses Python's stdlib smtplib — no extra dependencies.

Configure via env vars:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_TO, SMTP_TLS
  EMAIL_RISK_LEVELS (default: CRITICAL)
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config

logger = logging.getLogger(__name__)

_RISK_COLOR = {
    "CRITICAL": "#f85149",
    "HIGH":     "#d29922",
    "MEDIUM":   "#e3b341",
    "LOW":      "#3fb950",
}


def _build_html(record: dict) -> str:
    risk    = record.get("risk_level", "?")
    color   = _RISK_COLOR.get(risk, "#8b949e")
    patterns = record.get("flagged_patterns", [])
    if isinstance(patterns, list):
        patterns = ", ".join(patterns) or "—"
    rows = [
        ("Risk",     f'<strong style="color:{color}">{risk}</strong>'),
        ("IP",       record.get("ip", "")),
        ("Path",     f'{record.get("method","")} {record.get("path","")}'),
        ("Country",  record.get("country") or "—"),
        ("City",     record.get("city") or "—"),
        ("Category", record.get("category", "")),
        ("Time",     record.get("timestamp", "")),
        ("Patterns", f'<span style="color:{color}">{patterns}</span>'),
    ]
    trs = "".join(
        f'<tr><td style="color:#8b949e;padding:4px 20px 4px 0;white-space:nowrap">{k}</td>'
        f'<td style="padding:4px 0">{v}</td></tr>'
        for k, v in rows
    )
    return f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',monospace;
background:#0d1117;color:#e6edf3;padding:24px;max-width:600px">
<h2 style="color:{color};margin-bottom:4px">⚠️ AI Honeypot Alert</h2>
<p style="color:#8b949e;font-size:13px;margin-bottom:20px">
  An attacker triggered a <strong style="color:{color}">{risk}</strong> event.
</p>
<table style="border-collapse:collapse;font-size:13px;width:100%">{trs}</table>
<hr style="border-color:#30363d;margin:20px 0">
<p style="color:#30363d;font-size:11px">AI Honeypot · auto-generated alert</p>
</body></html>"""


async def send_alert_email(record: dict) -> None:
    """Non-blocking alert — runs smtplib in executor."""
    if not Config.SMTP_HOST or not Config.SMTP_TO:
        return
    if record.get("risk_level") not in Config.EMAIL_RISK_LEVELS:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_sync, record)


def _send_sync(record: dict) -> None:
    try:
        risk = record.get("risk_level", "?")
        ip   = record.get("ip", "")
        path = record.get("path", "")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Honeypot] {risk} — {ip} → {path}"
        msg["From"]    = Config.SMTP_FROM
        msg["To"]      = Config.SMTP_TO
        msg.attach(MIMEText(_build_html(record), "html"))

        if Config.SMTP_TLS:
            server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)

        if Config.SMTP_USER:
            server.login(Config.SMTP_USER, Config.SMTP_PASS)

        server.send_message(msg)
        server.quit()
        logger.info("Alert email sent to %s", Config.SMTP_TO)
    except Exception as exc:
        logger.warning("Email alert failed: %s", exc)


async def send_report_email(subject: str, html_body: str, to: str) -> None:
    """Send an arbitrary HTML email (used for scheduled reports)."""
    if not Config.SMTP_HOST or not to:
        return
    loop = asyncio.get_event_loop()

    def _send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = Config.SMTP_FROM
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html"))
        if Config.SMTP_TLS:
            server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
            server.ehlo(); server.starttls(); server.ehlo()
        else:
            server = smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
        if Config.SMTP_USER:
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
        server.send_message(msg)
        server.quit()

    await loop.run_in_executor(None, _send)

"""
Background scheduler for:
  - Data retention: purge requests older than MAX_REQUEST_AGE_DAYS (runs hourly)
  - Scheduled threat reports: email HTML report daily or weekly via SMTP
"""

import asyncio
import logging
from datetime import datetime, timezone

from config import Config

logger = logging.getLogger(__name__)


async def _retention_loop() -> None:
    """Purge old requests every hour if MAX_REQUEST_AGE_DAYS is set."""
    while True:
        await asyncio.sleep(3600)
        if Config.MAX_REQUEST_AGE_DAYS > 0:
            try:
                from app.database import purge_old_requests
                deleted = await purge_old_requests(Config.MAX_REQUEST_AGE_DAYS)
                if deleted:
                    logger.info(
                        "Retention purge: removed %d requests older than %d days",
                        deleted, Config.MAX_REQUEST_AGE_DAYS,
                    )
            except Exception as exc:
                logger.warning("Retention purge failed: %s", exc)


async def _report_loop() -> None:
    """Send scheduled HTML threat reports via email."""
    if not Config.REPORT_SCHEDULE or not Config.REPORT_EMAIL_TO:
        return

    last_sent_day: int = -1

    while True:
        await asyncio.sleep(3600)
        now = datetime.now(timezone.utc)
        should_send = False

        if Config.REPORT_SCHEDULE == "daily":
            should_send = now.day != last_sent_day
        elif Config.REPORT_SCHEDULE == "weekly" and now.weekday() == 0:
            # Monday
            should_send = now.day != last_sent_day

        if should_send:
            try:
                from app.database import get_stats, get_threat_report_data
                from app.routes.dashboard import _build_report_html
                from app.emailer import send_report_email

                s = await get_stats()
                r = await get_threat_report_data()
                html = _build_report_html(s, r)
                subject = f"[Honeypot] {Config.REPORT_SCHEDULE.title()} Threat Report"
                await send_report_email(subject, html, Config.REPORT_EMAIL_TO)
                last_sent_day = now.day
                logger.info("Scheduled %s report sent to %s", Config.REPORT_SCHEDULE, Config.REPORT_EMAIL_TO)
            except Exception as exc:
                logger.warning("Scheduled report failed: %s", exc)


async def start_background_tasks() -> None:
    """Call once from the FastAPI lifespan — creates persistent background tasks."""
    asyncio.create_task(_retention_loop())
    asyncio.create_task(_report_loop())

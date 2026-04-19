"""
SQLite database layer using aiosqlite for non-blocking async access.
Single write lock prevents SQLite journal conflicts on a single-worker Pi.
"""

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import aiosqlite

from config import Config

_write_lock = asyncio.Lock()


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(Config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    async with get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT NOT NULL,
                ip               TEXT NOT NULL,
                method           TEXT NOT NULL,
                path             TEXT NOT NULL,
                headers          TEXT NOT NULL,
                body             TEXT,
                category         TEXT NOT NULL,
                risk_level       TEXT NOT NULL,
                user_agent       TEXT,
                country          TEXT,
                city             TEXT,
                lat              REAL,
                lng              REAL,
                asn              TEXT,
                flagged_patterns TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_timestamp ON requests(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_ip        ON requests(ip);
            CREATE INDEX IF NOT EXISTS idx_risk      ON requests(risk_level);
            CREATE INDEX IF NOT EXISTS idx_category  ON requests(category);

            CREATE TABLE IF NOT EXISTS ip_cache (
                ip         TEXT PRIMARY KEY,
                country    TEXT,
                city       TEXT,
                lat        REAL,
                lng        REAL,
                asn        TEXT,
                cached_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_states (
                name     TEXT PRIMARY KEY,
                enabled  INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS blocked_ips (
                ip         TEXT PRIMARY KEY,
                reason     TEXT,
                blocked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS allowed_ips (
                ip       TEXT PRIMARY KEY,
                label    TEXT,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ip_notes (
                ip         TEXT PRIMARY KEY,
                note       TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_rules (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                pattern    TEXT NOT NULL,
                risk_level TEXT NOT NULL DEFAULT 'HIGH',
                flag_name  TEXT NOT NULL,
                enabled    INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deception_callbacks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                token        TEXT NOT NULL,
                caller_ip    TEXT NOT NULL,
                original_ip  TEXT,
                timestamp    TEXT NOT NULL
            );
        """)
        await db.commit()

    # Idempotent migration: add tarpitted column to service_states
    try:
        async with _write_lock:
            async with get_db() as db:
                await db.execute(
                    "ALTER TABLE service_states ADD COLUMN tarpitted INTEGER NOT NULL DEFAULT 0"
                )
                await db.commit()
    except Exception:
        pass  # Column already exists

    # Idempotent migration: add AbuseIPDB reputation columns to ip_cache
    for col_def in [
        "abuse_score INTEGER",
        "abuse_reports INTEGER",
        "is_tor INTEGER",
        "isp TEXT",
        "hosting INTEGER",
        "reverse_dns TEXT",
        "threatfox_hit TEXT",
        "greynoise_noise INTEGER",
        "greynoise_riot INTEGER",
        "greynoise_classification TEXT",
        "greynoise_name TEXT",
    ]:
        try:
            async with _write_lock:
                async with get_db() as db:
                    await db.execute(f"ALTER TABLE ip_cache ADD COLUMN {col_def}")
                    await db.commit()
        except Exception:
            pass  # Column already exists


async def insert_request(record: dict) -> int:
    async with _write_lock:
        async with get_db() as db:
            cursor = await db.execute(
                """
                INSERT INTO requests
                    (timestamp, ip, method, path, headers, body,
                     category, risk_level, user_agent,
                     country, city, lat, lng, asn, flagged_patterns)
                VALUES
                    (:timestamp, :ip, :method, :path, :headers, :body,
                     :category, :risk_level, :user_agent,
                     :country, :city, :lat, :lng, :asn, :flagged_patterns)
                """,
                record,
            )
            await db.commit()
            row_id = cursor.lastrowid

            # Prune oldest rows if over limit
            await db.execute(
                """
                DELETE FROM requests WHERE id IN (
                    SELECT id FROM requests ORDER BY id ASC
                    LIMIT MAX(0, (SELECT COUNT(*) FROM requests) - ?)
                )
                """,
                (Config.MAX_REQUESTS_STORED,),
            )
            await db.commit()
            return row_id


async def get_requests(
    page: int = 1,
    limit: int = 50,
    risk: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
) -> list[dict]:
    offset = (page - 1) * limit
    conditions = []
    params: list = []

    if risk:
        conditions.append("risk_level = ?")
        params.append(risk)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if q:
        like = f"%{q}%"
        conditions.append("(body LIKE ? OR ip LIKE ? OR path LIKE ? OR country LIKE ?)")
        params.extend([like, like, like, like])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT id, timestamp, ip, method, path, category, risk_level,
                   user_agent, country, city, lat, lng, asn, flagged_patterns
            FROM requests
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_stats() -> dict:
    async with get_db() as db:
        # Total
        cur = await db.execute("SELECT COUNT(*) FROM requests")
        total = (await cur.fetchone())[0]

        # Last 24h
        since_24h = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        cur = await db.execute(
            "SELECT COUNT(*) FROM requests WHERE timestamp >= ?", (since_24h,)
        )
        last_24h = (await cur.fetchone())[0]

        # By risk
        cur = await db.execute(
            "SELECT risk_level, COUNT(*) FROM requests GROUP BY risk_level"
        )
        by_risk = {r[0]: r[1] for r in await cur.fetchall()}

        # By category
        cur = await db.execute(
            "SELECT category, COUNT(*) FROM requests GROUP BY category"
        )
        by_category = {r[0]: r[1] for r in await cur.fetchall()}

        # Top IPs
        cur = await db.execute(
            """
            SELECT ip, COUNT(*) as cnt, country, MAX(timestamp) as last_seen,
                   CASE MAX(CASE risk_level
                              WHEN 'CRITICAL' THEN 4
                              WHEN 'HIGH'     THEN 3
                              WHEN 'MEDIUM'   THEN 2
                              WHEN 'LOW'      THEN 1
                              ELSE 0 END)
                     WHEN 4 THEN 'CRITICAL'
                     WHEN 3 THEN 'HIGH'
                     WHEN 2 THEN 'MEDIUM'
                     WHEN 1 THEN 'LOW'
                   END as max_risk
            FROM requests
            GROUP BY ip
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        top_ips = [dict(r) for r in await cur.fetchall()]

        # Top countries
        cur = await db.execute(
            """
            SELECT country, COUNT(*) as cnt
            FROM requests
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        top_countries = [dict(r) for r in await cur.fetchall()]

        # Hourly trend (last 24 hours)
        cur = await db.execute(
            """
            SELECT strftime('%Y-%m-%dT%H:00', timestamp) as hour, COUNT(*) as cnt
            FROM requests
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY hour
            ORDER BY hour ASC
            """
        )
        hourly_trend = [dict(r) for r in await cur.fetchall()]

        # Unique IPs
        cur = await db.execute("SELECT COUNT(DISTINCT ip) FROM requests")
        unique_ips = (await cur.fetchone())[0]

        return {
            "total": total,
            "last_24h": last_24h,
            "unique_ips": unique_ips,
            "by_risk": by_risk,
            "by_category": by_category,
            "top_ips": top_ips,
            "top_countries": top_countries,
            "hourly_trend": hourly_trend,
        }


async def get_map_data() -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT ip, country, city, lat, lng, risk_level,
                   COUNT(*) as cnt, MAX(timestamp) as last_seen
            FROM requests
            WHERE lat IS NOT NULL AND lng IS NOT NULL
            GROUP BY ip
            ORDER BY cnt DESC
            LIMIT 2000
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_ip_cache(ip: str) -> Optional[dict]:
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT country, city, lat, lng, asn, cached_at,
                   abuse_score, abuse_reports, is_tor, isp,
                   hosting, reverse_dns, threatfox_hit,
                   greynoise_noise, greynoise_riot,
                   greynoise_classification, greynoise_name
            FROM ip_cache
            WHERE ip = ?
              AND cached_at >= datetime('now', ? || ' hours')
            """,
            (ip, f"-{Config.GEO_CACHE_TTL_HOURS}"),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_ip_cache(ip: str, geo: dict) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO ip_cache
                    (ip, country, city, lat, lng, asn, cached_at,
                     abuse_score, abuse_reports, is_tor, isp,
                     hosting, reverse_dns, threatfox_hit,
                     greynoise_noise, greynoise_riot,
                     greynoise_classification, greynoise_name)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ip,
                    geo.get("country"),
                    geo.get("city"),
                    geo.get("lat"),
                    geo.get("lng"),
                    geo.get("asn"),
                    geo.get("abuse_score"),
                    geo.get("abuse_reports"),
                    1 if geo.get("is_tor") else 0 if "is_tor" in geo else None,
                    geo.get("isp"),
                    1 if geo.get("hosting") else 0 if "hosting" in geo else None,
                    geo.get("reverse_dns"),
                    geo.get("threatfox_hit"),
                    1 if geo.get("greynoise_noise") else 0 if "greynoise_noise" in geo else None,
                    1 if geo.get("greynoise_riot") else 0 if "greynoise_riot" in geo else None,
                    geo.get("greynoise_classification"),
                    geo.get("greynoise_name"),
                ),
            )
            await db.commit()


async def clear_all_requests() -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM requests")
            await db.commit()


async def get_requests_for_export(prefixes: list, exact_paths: list) -> list:
    conditions: list = []
    params: list = []
    for p in exact_paths:
        conditions.append("path = ?")
        params.append(p)
    for p in prefixes:
        conditions.append("path LIKE ?")
        params.append(p.rstrip("/") + "/%")
        conditions.append("path = ?")
        params.append(p.rstrip("/"))
    where = ("WHERE " + " OR ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT timestamp, ip, method, path, category, risk_level,
               user_agent, country, city, asn, flagged_patterns, body
        FROM requests {where}
        ORDER BY timestamp DESC
    """
    async with get_db() as db:
        rows = await (await db.execute(sql, params)).fetchall()
    return [dict(r) for r in rows]


async def count_recent_requests(ip: str, window_secs: int) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT COUNT(*) FROM requests
            WHERE ip = ?
              AND timestamp >= datetime('now', ? || ' seconds')
            """,
            (ip, f"-{window_secs}"),
        )
        return (await cur.fetchone())[0]


async def get_request_by_id(request_id: int) -> dict | None:
    """Return the full record for a single request including headers and body."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT id, timestamp, ip, method, path, headers, body,
                   category, risk_level, user_agent, country, city,
                   lat, lng, asn, flagged_patterns
            FROM requests WHERE id = ?
            """,
            (request_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_requests_by_ip(ip: str, limit: int = 200) -> list[dict]:
    """Return all requests from a single IP, oldest-first, for session view."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT id, timestamp, method, path, category, risk_level,
                   user_agent, country, city, flagged_patterns, body
            FROM requests
            WHERE ip = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (ip, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_threat_report_data() -> dict:
    """Aggregate data for the downloadable threat report."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT ip, COUNT(*) as cnt, country, city,
                   MAX(risk_level) as max_risk, MAX(timestamp) as last_seen,
                   MAX(lat) as lat, MAX(lng) as lng
            FROM requests
            GROUP BY ip
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        top_ips = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            """
            SELECT path, COUNT(*) as cnt, MAX(risk_level) as max_risk
            FROM requests
            GROUP BY path
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        top_paths = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            "SELECT flagged_patterns FROM requests "
            "WHERE flagged_patterns IS NOT NULL AND flagged_patterns != '[]'"
        )
        pattern_counts: dict[str, int] = {}
        for row in await cur.fetchall():
            try:
                for p in json.loads(row[0]):
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1
            except Exception:
                pass
        top_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:15]

        cur = await db.execute(
            """
            SELECT country, COUNT(*) as cnt
            FROM requests
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY cnt DESC
            LIMIT 15
            """
        )
        geo_breakdown = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            """
            SELECT ip, country, MAX(lat) as lat, MAX(lng) as lng,
                   MAX(risk_level) as max_risk, COUNT(*) as cnt
            FROM requests
            WHERE lat IS NOT NULL AND lng IS NOT NULL
            GROUP BY ip
            ORDER BY cnt DESC
            LIMIT 500
            """
        )
        map_points = [dict(r) for r in await cur.fetchall()]

        return {
            "top_ips": top_ips,
            "top_paths": top_paths,
            "top_patterns": top_patterns,
            "geo_breakdown": geo_breakdown,
            "map_points": map_points,
        }


# ── Blocked IPs ────────────────────────────────────────────────────────────────

async def get_blocked_ips() -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT ip, reason, blocked_at FROM blocked_ips ORDER BY blocked_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def add_blocked_ip(ip: str, reason: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO blocked_ips (ip, reason, blocked_at) VALUES (?, ?, datetime('now'))",
                (ip, reason),
            )
            await db.commit()


async def remove_blocked_ip(ip: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
            await db.commit()


async def count_critical_requests_from_ip(ip: str, window_secs: int) -> int:
    """Count CRITICAL-risk requests from an IP in the last window_secs seconds."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT COUNT(*) FROM requests
            WHERE ip = ? AND risk_level = 'CRITICAL'
              AND timestamp >= datetime('now', ? || ' seconds')
            """,
            (ip, f"-{window_secs}"),
        )
        return (await cur.fetchone())[0]


# ── Intelligence charts ────────────────────────────────────────────────────────

async def get_weekly_trend() -> list[dict]:
    """Request counts per day for the last 7 days, split by risk level."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT date(timestamp) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN risk_level = 'CRITICAL' THEN 1 ELSE 0 END) as critical,
                   SUM(CASE WHEN risk_level = 'HIGH'     THEN 1 ELSE 0 END) as high,
                   SUM(CASE WHEN risk_level = 'MEDIUM'   THEN 1 ELSE 0 END) as medium,
                   SUM(CASE WHEN risk_level = 'LOW'      THEN 1 ELSE 0 END) as low
            FROM requests
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY day
            ORDER BY day ASC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_hourly_heatmap() -> list[dict]:
    """Request counts by day-of-week (0=Sun) and hour-of-day (00-23)."""
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT strftime('%w', timestamp) as dow,
                   strftime('%H', timestamp) as hour,
                   COUNT(*) as cnt
            FROM requests
            GROUP BY dow, hour
            ORDER BY dow, hour
            """
        )
        return [dict(r) for r in await cur.fetchall()]


# ── Allowed IPs ────────────────────────────────────────────────────────────────

async def get_allowed_ips() -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT ip, label, added_at FROM allowed_ips ORDER BY added_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def add_allowed_ip(ip: str, label: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO allowed_ips (ip, label, added_at) VALUES (?, ?, datetime('now'))",
                (ip, label),
            )
            await db.commit()


async def remove_allowed_ip(ip: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM allowed_ips WHERE ip = ?", (ip,))
            await db.commit()


# ── IP Notes ───────────────────────────────────────────────────────────────────

async def get_ip_note(ip: str) -> Optional[str]:
    async with get_db() as db:
        cur = await db.execute("SELECT note FROM ip_notes WHERE ip = ?", (ip,))
        row = await cur.fetchone()
        return row[0] if row else None


async def upsert_ip_note(ip: str, note: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO ip_notes (ip, note, updated_at) VALUES (?, ?, datetime('now'))",
                (ip, note),
            )
            await db.commit()


async def delete_ip_note(ip: str) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM ip_notes WHERE ip = ?", (ip,))
            await db.commit()


async def get_all_ip_notes() -> dict[str, str]:
    """Return all notes as {ip: note} dict — used for in-memory cache at startup."""
    async with get_db() as db:
        cur = await db.execute("SELECT ip, note FROM ip_notes")
        return {row[0]: row[1] for row in await cur.fetchall()}


# ── Custom detection rules ─────────────────────────────────────────────────────

async def get_custom_rules() -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, name, pattern, risk_level, flag_name, enabled, created_at "
            "FROM custom_rules ORDER BY created_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def add_custom_rule(name: str, pattern: str, risk_level: str, flag_name: str) -> int:
    async with _write_lock:
        async with get_db() as db:
            cur = await db.execute(
                "INSERT INTO custom_rules (name, pattern, risk_level, flag_name, enabled, created_at) "
                "VALUES (?, ?, ?, ?, 1, datetime('now'))",
                (name, pattern, risk_level.upper(), flag_name),
            )
            await db.commit()
            return cur.lastrowid


async def update_custom_rule(rule_id: int, name: str, pattern: str, risk_level: str, flag_name: str, enabled: bool) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "UPDATE custom_rules SET name=?, pattern=?, risk_level=?, flag_name=?, enabled=? WHERE id=?",
                (name, pattern, risk_level.upper(), flag_name, 1 if enabled else 0, rule_id),
            )
            await db.commit()


async def delete_custom_rule(rule_id: int) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute("DELETE FROM custom_rules WHERE id=?", (rule_id,))
            await db.commit()


# ── Deception callbacks ────────────────────────────────────────────────────────

async def log_deception_callback(token: str, caller_ip: str, original_ip: Optional[str]) -> None:
    async with _write_lock:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO deception_callbacks (token, caller_ip, original_ip, timestamp) "
                "VALUES (?, ?, ?, datetime('now'))",
                (token, caller_ip, original_ip),
            )
            await db.commit()


async def get_deception_callbacks(limit: int = 50) -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, token, caller_ip, original_ip, timestamp "
            "FROM deception_callbacks ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]


# ── Data retention ─────────────────────────────────────────────────────────────

async def purge_old_requests(max_age_days: int) -> int:
    """Delete requests older than max_age_days. Returns count deleted."""
    async with _write_lock:
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM requests WHERE timestamp < datetime('now', ? || ' days')",
                (f"-{max_age_days}",),
            )
            await db.commit()
            return cur.rowcount


# ── CSV export ─────────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "id", "timestamp", "ip", "method", "path", "category", "risk_level",
    "country", "city", "user_agent", "flagged_patterns", "body_snippet",
]


async def stream_requests_csv(
    risk: Optional[str] = None,
    category: Optional[str] = None,
    ip: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50000,
) -> AsyncIterator[str]:
    """Async generator that yields CSV rows (header first) for streaming export."""
    conditions: list[str] = []
    params: list = []
    if risk:
        conditions.append("risk_level = ?")
        params.append(risk.upper())
    if category:
        conditions.append("category = ?")
        params.append(category)
    if ip:
        conditions.append("ip = ?")
        params.append(ip)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    # Yield header
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_FIELDNAMES)
    yield buf.getvalue()

    async with get_db() as db:
        cur = await db.execute(
            f"""
            SELECT id, timestamp, ip, method, path, category, risk_level,
                   country, city, user_agent, flagged_patterns, body
            FROM requests
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params,
        )
        while True:
            rows = await cur.fetchmany(500)
            if not rows:
                break
            buf = io.StringIO()
            w = csv.writer(buf)
            for row in rows:
                body_snippet = (row[11] or "")[:200]
                w.writerow([
                    row[0], row[1], row[2], row[3], row[4],
                    row[5], row[6], row[7], row[8], row[9],
                    row[10], body_snippet,
                ])
            yield buf.getvalue()

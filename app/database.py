"""
SQLite database layer using aiosqlite for non-blocking async access.
Single write lock prevents SQLite journal conflicts on a single-worker Pi.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

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
        """)
        await db.commit()


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
            SELECT ip, COUNT(*) as cnt, country, MAX(timestamp) as last_seen
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
            SELECT country, city, lat, lng, asn, cached_at
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
                    (ip, country, city, lat, lng, asn, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    ip,
                    geo.get("country"),
                    geo.get("city"),
                    geo.get("lat"),
                    geo.get("lng"),
                    geo.get("asn"),
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

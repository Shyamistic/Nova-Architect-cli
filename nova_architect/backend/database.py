"""
Nova Architect — SQLite Build History
Stores completed builds locally. Survives server restarts.
"""

import sqlite3
import json
import uuid
import time
import logging
import os
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_url, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS builds (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                requirement TEXT NOT NULL,
                architecture TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                success_count INTEGER NOT NULL DEFAULT 0,
                total_count INTEGER NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                services_built TEXT NOT NULL DEFAULT '[]'
            )
        """)
        conn.commit()
    logger.info(f"Database initialized at {settings.database_url}")


def save_build(
    requirement: str,
    architecture: dict,
    status: str,
    success_count: int,
    total_count: int,
    duration_seconds: float,
    services_built: list,
) -> str:
    """Persist a completed build. Returns the generated build ID."""
    build_id = str(uuid.uuid4())
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO builds
               (id, timestamp, requirement, architecture, status,
                success_count, total_count, duration_seconds, services_built)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                build_id,
                time.time(),
                requirement[:500],
                json.dumps(architecture),
                status,
                success_count,
                total_count,
                round(duration_seconds, 1),
                json.dumps(services_built),
            ),
        )
        conn.commit()
    logger.info(f"Build {build_id} saved ({status}, {success_count}/{total_count})")
    return build_id


def list_builds(limit: int = 20) -> list:
    """Return last N builds (summary only — no full architecture JSON)."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT id, timestamp, requirement, status, success_count, total_count, duration_seconds
               FROM builds ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_build(build_id: str) -> Optional[dict]:
    """Return full build record including architecture JSON."""
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM builds WHERE id = ?", (build_id,)).fetchone()
    if not row:
        return None
    record = dict(row)
    record["architecture"] = json.loads(record["architecture"])
    record["services_built"] = json.loads(record["services_built"])
    return record


def delete_build(build_id: str) -> bool:
    """Delete a build record. Returns True if it existed."""
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM builds WHERE id = ?", (build_id,))
        conn.commit()
    return cursor.rowcount > 0


def builds_today() -> int:
    """Count builds in the last 24 hours."""
    cutoff = time.time() - 86400
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM builds WHERE timestamp > ?", (cutoff,)
        ).fetchone()
    return row["cnt"] if row else 0

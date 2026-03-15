"""SQLite database layer for Gossip."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gossip.config import get_config

SCHEMA = """
-- Groups (supports multi-group in future)
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    invite_token TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    settings_json TEXT
);

-- Members
CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES groups(id),
    display_name TEXT NOT NULL,
    discord_id TEXT,
    discord_username TEXT,
    telegram_id TEXT,
    telegram_username TEXT,
    portal_token TEXT UNIQUE NOT NULL,
    is_paused INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_members_discord_id ON members(discord_id);
CREATE INDEX IF NOT EXISTS idx_members_telegram_id ON members(telegram_id);
CREATE INDEX IF NOT EXISTS idx_members_group ON members(group_id);

-- OAuth tokens
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TEXT,
    scopes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(member_id, provider)
);

-- Gossip history
CREATE TABLE IF NOT EXISTS gossip_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL REFERENCES groups(id),
    gossip_text TEXT NOT NULL,
    context_summary TEXT,
    posted_at TEXT NOT NULL DEFAULT (datetime('now')),
    platform TEXT,
    channel_id TEXT,
    feedback_score INTEGER DEFAULT 0
);

-- Chat activity tracking
CREATE TABLE IF NOT EXISTS chat_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL REFERENCES groups(id),
    platform TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    last_human_message_at TEXT NOT NULL,
    last_human_author TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(group_id, platform, channel_id)
);

-- Data source sync state
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    last_sync_at TEXT,
    last_sync_status TEXT,
    last_error TEXT,
    sync_cursor TEXT,
    UNIQUE(member_id, source_type)
);

-- Manual input from members
CREATE TABLE IF NOT EXISTS manual_input (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'portal',
    used_in_gossip INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Action log
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Events (comprehensive logging for analysis)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    summary TEXT NOT NULL,
    payload_json TEXT,
    duration_ms INTEGER,
    session_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
"""


def _db_path() -> Path:
    cfg = get_config()
    path = cfg.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db() -> None:
    """Create all tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    _migrate_location_columns()


@contextmanager
def get_connection():
    """Get a SQLite connection with WAL mode and foreign keys."""
    conn = sqlite3.connect(str(_db_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Groups ──────────────────────────────────────────────────────────────


def create_group(name: str) -> dict[str, Any]:
    """Create a new group and return it."""
    group = {
        "id": _uuid(),
        "name": name,
        "invite_token": uuid.uuid4().hex[:12],
        "created_at": _now(),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO groups (id, name, invite_token, created_at) VALUES (?, ?, ?, ?)",
            (group["id"], group["name"], group["invite_token"], group["created_at"]),
        )
    return group


def get_group_by_invite(token: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM groups WHERE invite_token = ?", (token,)).fetchone()
        return dict(row) if row else None


def get_default_group() -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM groups ORDER BY created_at LIMIT 1").fetchone()
        return dict(row) if row else None


# ── Members ─────────────────────────────────────────────────────────────


def create_member(
    group_id: str,
    display_name: str,
    discord_username: str | None = None,
    telegram_username: str | None = None,
) -> dict[str, Any]:
    member = {
        "id": _uuid(),
        "group_id": group_id,
        "display_name": display_name,
        "discord_username": discord_username,
        "telegram_username": telegram_username,
        "portal_token": uuid.uuid4().hex[:16],
        "created_at": _now(),
        "updated_at": _now(),
    }
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO members
            (id, group_id, display_name, discord_username, telegram_username, portal_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                member["id"], member["group_id"], member["display_name"],
                member["discord_username"], member["telegram_username"],
                member["portal_token"], member["created_at"], member["updated_at"],
            ),
        )
    return member


def get_member_by_portal_token(token: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE portal_token = ?", (token,)).fetchone()
        return dict(row) if row else None


def get_member_by_discord_id(discord_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE discord_id = ?", (discord_id,)).fetchone()
        return dict(row) if row else None


def get_member_by_discord_username(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE discord_username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_member_by_telegram_id(telegram_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def get_members_by_group(group_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE group_id = ? ORDER BY display_name", (group_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_member(member_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [member_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE members SET {set_clause} WHERE id = ?", values)


def delete_member(member_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))


# ── Location ───────────────────────────────────────────────────────────


def _migrate_location_columns() -> None:
    """Add location columns to members table if they don't exist."""
    columns = [
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("location_name", "TEXT"),
        ("location_updated_at", "TEXT"),
    ]
    with get_connection() as conn:
        for col_name, col_type in columns:
            try:
                conn.execute(f"ALTER TABLE members ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists


def update_member_location(
    member_id: str, lat: float, lng: float, location_name: str
) -> None:
    """Update a member's location."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE members
            SET latitude = ?, longitude = ?, location_name = ?,
                location_updated_at = ?, updated_at = ?
            WHERE id = ?""",
            (lat, lng, location_name, _now(), _now(), member_id),
        )


def get_members_with_location(group_id: str) -> list[dict]:
    """Return members that have location data."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM members
            WHERE group_id = ? AND latitude IS NOT NULL
            ORDER BY display_name""",
            (group_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── OAuth Tokens ────────────────────────────────────────────────────────


def upsert_oauth_token(
    member_id: str,
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: str | None = None,
    scopes: str | None = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO oauth_tokens (member_id, provider, access_token, refresh_token, expires_at, scopes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(member_id, provider) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, oauth_tokens.refresh_token),
                expires_at = excluded.expires_at,
                scopes = excluded.scopes,
                updated_at = excluded.updated_at""",
            (member_id, provider, access_token, refresh_token, expires_at, scopes, now, now),
        )


def get_oauth_token(member_id: str, provider: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE member_id = ? AND provider = ?",
            (member_id, provider),
        ).fetchone()
        return dict(row) if row else None


def delete_oauth_token(member_id: str, provider: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM oauth_tokens WHERE member_id = ? AND provider = ?",
            (member_id, provider),
        )


# ── Gossip History ──────────────────────────────────────────────────────


def add_gossip(
    group_id: str,
    gossip_text: str,
    context_summary: str | None = None,
    platform: str | None = None,
    channel_id: str | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO gossip_history (group_id, gossip_text, context_summary, posted_at, platform, channel_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, gossip_text, context_summary, _now(), platform, channel_id),
        )
        return cursor.lastrowid


def get_recent_gossip(group_id: str, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM gossip_history WHERE group_id = ? ORDER BY posted_at DESC LIMIT ?",
            (group_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def update_gossip_feedback(gossip_id: int, delta: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE gossip_history SET feedback_score = feedback_score + ? WHERE id = ?",
            (delta, gossip_id),
        )


# ── Chat Activity ───────────────────────────────────────────────────────


def update_chat_activity(
    group_id: str, platform: str, channel_id: str, author: str | None = None
) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO chat_activity (group_id, platform, channel_id, last_human_message_at, last_human_author, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, platform, channel_id) DO UPDATE SET
                last_human_message_at = excluded.last_human_message_at,
                last_human_author = excluded.last_human_author,
                updated_at = excluded.updated_at""",
            (group_id, platform, channel_id, now, author, now),
        )


def get_chat_activity(group_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_activity WHERE group_id = ?", (group_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Manual Input ────────────────────────────────────────────────────────


def add_manual_input(member_id: str, content: str, source: str = "portal") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO manual_input (member_id, content, source, created_at) VALUES (?, ?, ?, ?)",
            (member_id, content, source, _now()),
        )
        return cursor.lastrowid


def get_unused_manual_input(member_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM manual_input WHERE member_id = ? AND used_in_gossip = 0 ORDER BY created_at",
            (member_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_manual_input_used(input_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE manual_input SET used_in_gossip = 1 WHERE id = ?", (input_id,))


# ── Action Log ──────────────────────────────────────────────────────────


def log_action(action_type: str, summary: str, details_json: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO action_log (action_type, summary, details_json, created_at) VALUES (?, ?, ?, ?)",
            (action_type, summary, details_json, _now()),
        )


# ── Events (comprehensive logging) ────────────────────────────────────


def log_event(
    event_type: str,
    summary: str,
    event_subtype: str | None = None,
    payload_json: str | None = None,
    duration_ms: int | None = None,
    session_id: str | None = None,
) -> int:
    """Log an event to the events table. Returns the event ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO events
            (event_type, event_subtype, summary, payload_json, duration_ms, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, event_subtype, summary, payload_json, duration_ms, session_id, _now()),
        )
        return cursor.lastrowid


def get_events(
    event_type: str | None = None,
    limit: int = 100,
    since: str | None = None,
) -> list[dict]:
    """Query events, optionally filtered by type and/or time."""
    with get_connection() as conn:
        query = "SELECT * FROM events"
        params: list[Any] = []
        clauses: list[str] = []

        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_events_by_session(session_id: str) -> list[dict]:
    """Get all events for a given session, ordered chronologically."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

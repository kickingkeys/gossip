"""Centralized event logging for Gossip.

Writes to three destinations:
1. SQLite events table (queryable analysis)
2. JSONL file (data/logs/events.jsonl — export/streaming)
3. Markdown file (data/logs/activity.md — human-readable)
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gossip.config import get_config

logger = logging.getLogger("gossip")


def get_current_session_id() -> str | None:
    """Return the Hermes session ID from the environment, or None if not set."""
    return os.environ.get("HERMES_SESSION_KEY")

# Emoji map for human-readable markdown log
_EMOJI = {
    "idle_check": "\U0001f551",       # clock
    "context_build": "\U0001f9e9",    # puzzle
    "gossip_drop": "\U0001f375",      # tea
    "dossier_read": "\U0001f4c4",     # page
    "dossier_update": "\U0001f464",   # person
    "member_lookup": "\U0001f50d",    # magnifying glass
    "calendar_sync": "\U0001f4c5",    # calendar
    "chat_message": "\U0001f4ac",     # speech bubble
    "portal_action": "\U0001f310",    # globe
    "session_link": "\U0001f517",     # link
    "error": "\U0000274c",            # cross mark
    "startup": "\U0001f680",          # rocket
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_iso_ms() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def setup_logging() -> None:
    """Configure Python logging for the gossip package."""
    cfg = get_config()
    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)

    gossip_logger = logging.getLogger("gossip")
    gossip_logger.setLevel(level)

    if not gossip_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        )
        gossip_logger.addHandler(handler)


def log_event(
    event_type: str,
    summary: str,
    event_subtype: str | None = None,
    payload: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    session_id: str | None = None,
) -> int | None:
    """Log an event to all configured destinations.

    Returns the event ID from the database, or None if DB logging is disabled.
    """
    cfg = get_config()
    if not cfg.logging.enabled:
        return None

    payload_json = json.dumps(payload, default=str) if payload else None
    event_id = None

    # 1. SQLite
    if cfg.logging.db_enabled:
        try:
            from gossip.db import log_event as db_log_event

            event_id = db_log_event(
                event_type=event_type,
                summary=summary,
                event_subtype=event_subtype,
                payload_json=payload_json,
                duration_ms=duration_ms,
                session_id=session_id,
            )
        except Exception as e:
            logger.warning("Failed to log event to DB: %s", e)

    # 2. JSONL
    if cfg.logging.jsonl_enabled:
        try:
            _write_jsonl(event_type, event_subtype, summary, payload, duration_ms, session_id)
        except Exception as e:
            logger.warning("Failed to log event to JSONL: %s", e)

    # 3. Human-readable markdown
    if cfg.logging.markdown_enabled:
        try:
            _write_markdown(event_type, event_subtype, summary, payload)
        except Exception as e:
            logger.warning("Failed to log event to markdown: %s", e)

    # Also emit to Python logging
    logger.info("[%s%s] %s", event_type, f":{event_subtype}" if event_subtype else "", summary)

    return event_id


def _ensure_log_dir() -> Path:
    cfg = get_config()
    log_dir = cfg.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _write_jsonl(
    event_type: str,
    event_subtype: str | None,
    summary: str,
    payload: dict | None,
    duration_ms: int | None,
    session_id: str | None,
) -> None:
    log_dir = _ensure_log_dir()
    entry = {
        "timestamp": _now_iso_ms(),
        "event_type": event_type,
        "summary": summary,
    }
    if event_subtype:
        entry["event_subtype"] = event_subtype
    if payload:
        entry["payload"] = payload
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    if session_id:
        entry["session_id"] = session_id

    jsonl_path = log_dir / "events.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _write_markdown(
    event_type: str,
    event_subtype: str | None,
    summary: str,
    payload: dict | None,
) -> None:
    log_dir = _ensure_log_dir()
    emoji = _EMOJI.get(event_type, "\U0001f4cc")  # pushpin fallback
    ts = _now_iso()

    label = event_type.upper().replace("_", " ")
    if event_subtype:
        label += f" ({event_subtype})"

    line = f"[{ts}] {emoji} **{label}** — {summary}\n"

    md_path = log_dir / "activity.md"
    with open(md_path, "a", encoding="utf-8") as f:
        f.write(line)


@contextmanager
def timed_event(
    event_type: str,
    summary: str,
    event_subtype: str | None = None,
    payload: dict[str, Any] | None = None,
    session_id: str | None = None,
):
    """Context manager that logs an event with its duration.

    Usage:
        with timed_event("context_build", "Assembling context") as ctx:
            # do work
            ctx["payload"]["extra_key"] = "value"  # optionally enrich payload
    """
    ctx = {
        "payload": payload or {},
        "start": time.monotonic(),
    }
    try:
        yield ctx
    finally:
        elapsed_ms = int((time.monotonic() - ctx["start"]) * 1000)
        log_event(
            event_type=event_type,
            summary=summary,
            event_subtype=event_subtype,
            payload=ctx["payload"] if ctx["payload"] else None,
            duration_ms=elapsed_ms,
            session_id=session_id,
        )

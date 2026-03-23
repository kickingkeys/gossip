"""Pre-check gate for cron jobs.

~80% of checks cost $0 (no LLM call needed).
Called by OpenClaw tools before invoking the agent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from gossip.db import get_default_group, get_dm_history, get_donny_memory
from gossip.engine import get_idle_hours, is_quiet_hours


def should_fire_idle_gossip() -> dict:
    """Rich state check for the heartbeat.

    Returns chat state info so the agent can decide what to do:
    - fire: True when chat is dead (3h+) — definitely speak
    - chat_active: True when messages in last 30min — consider commenting
    - nighttime: True when 1am-9am — speak rarely
    - hours_since_donny: hours since donny last spoke in group
    """
    from zoneinfo import ZoneInfo

    group = get_default_group()
    if not group:
        return {"fire": False, "reason": "no_group", "cost": 0}

    hours_idle = get_idle_hours(group["id"])
    if hours_idle == float("inf"):
        hours_idle = 999

    # Check nighttime (1am-9am ET)
    try:
        from gossip.config import get_config
        cfg = get_config()
        tz = ZoneInfo(cfg.gossip.timezone)
    except Exception:
        tz = ZoneInfo("America/New_York")

    current_hour = datetime.now(tz).hour
    nighttime = current_hour >= 1 and current_hour < 9

    # How long since Donny last spoke in group
    memories = get_donny_memory(channel_type="group", limit=1)
    hours_since_donny = 999
    if memories:
        last_spoke = datetime.fromisoformat(memories[0]["created_at"])
        if last_spoke.tzinfo is None:
            last_spoke = last_spoke.replace(tzinfo=timezone.utc)
        hours_since_donny = (datetime.now(timezone.utc) - last_spoke).total_seconds() / 3600

    # Chat state
    chat_active = hours_idle < 0.5      # messages in last 30 min
    chat_quiet = 0.5 <= hours_idle < 3  # quiet but not dead
    chat_dead = hours_idle >= 3         # dead

    return {
        "fire": chat_dead and not nighttime,
        "chat_active": chat_active,
        "chat_quiet": chat_quiet,
        "chat_dead": chat_dead,
        "nighttime": nighttime,
        "hours_idle": round(hours_idle, 1),
        "hours_since_donny": round(hours_since_donny, 1),
        "current_hour": current_hour,
        "reason": _describe_state(chat_active, chat_quiet, chat_dead, nighttime, hours_idle),
        "cost": 0,
    }


def _describe_state(active, quiet, dead, night, hours):
    parts = []
    if night:
        parts.append("nighttime")
    if active:
        parts.append(f"chat active ({hours:.1f}h idle)")
    elif quiet:
        parts.append(f"chat quiet ({hours:.1f}h idle)")
    elif dead:
        parts.append(f"chat dead ({hours:.1f}h idle)")
    return ", ".join(parts) if parts else "unknown"


def should_dm_checkin(member_id: str) -> dict:
    """Check if we should DM this member.

    Returns: {"fire": bool, "reason": str}
    """
    if is_quiet_hours():
        return {"fire": False, "reason": "quiet_hours"}

    history = get_dm_history(member_id, limit=1)
    if history:
        last = datetime.fromisoformat(history[0]["created_at"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if hours_since < 4:
            return {"fire": False, "reason": f"recent DM ({hours_since:.1f}h ago)"}

    return {"fire": True, "reason": "ready"}

"""Pre-check gate for cron jobs.

~80% of checks cost $0 (no LLM call needed).
Called by OpenClaw tools before invoking the agent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from gossip.db import get_default_group, get_dm_history
from gossip.engine import get_idle_hours, is_quiet_hours


def should_fire_idle_gossip() -> dict:
    """Code-level check before calling LLM for idle gossip.

    Returns: {"fire": bool, "reason": str, "cost": 0, ...}
    """
    if is_quiet_hours():
        return {"fire": False, "reason": "quiet_hours", "cost": 0}

    group = get_default_group()
    if not group:
        return {"fire": False, "reason": "no_group", "cost": 0}

    hours = get_idle_hours(group["id"])
    threshold = 3.0

    if hours < threshold:
        return {"fire": False, "reason": f"active ({hours:.1f}h)", "cost": 0}

    return {
        "fire": True,
        "reason": f"idle {hours:.1f}h",
        "hours_idle": round(hours, 1),
    }


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

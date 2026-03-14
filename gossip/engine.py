"""Core gossip engine — context assembly and gossip generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gossip.config import get_config
from gossip.db import (
    get_chat_activity,
    get_default_group,
    get_members_by_group,
    get_recent_gossip,
    get_unused_manual_input,
)
from gossip.dossiers import get_all_dossiers


def is_quiet_hours() -> bool:
    """Check if current time is within quiet hours."""
    cfg = get_config()
    hour = datetime.now().hour
    start = cfg.gossip.quiet_hours_start
    end = cfg.gossip.quiet_hours_end
    if start > end:
        # Wraps midnight (e.g., 23-9)
        return hour >= start or hour < end
    return hour >= start and hour < end


def get_idle_hours(group_id: str | None = None) -> float:
    """Get hours since last human message in any channel for the group."""
    if group_id is None:
        group = get_default_group()
        if not group:
            return 0.0
        group_id = group["id"]

    activities = get_chat_activity(group_id)
    if not activities:
        return float("inf")

    # Find the most recent human message across all channels
    latest = None
    for activity in activities:
        ts = datetime.fromisoformat(activity["last_human_message_at"])
        if latest is None or ts > latest:
            latest = ts

    if latest is None:
        return float("inf")

    # Make sure we compare in UTC
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    return (now - latest).total_seconds() / 3600


def should_gossip(group_id: str | None = None) -> dict:
    """Check if conditions are right for dropping gossip.

    Returns a dict with: should_fire, reason, hours_idle, is_quiet_hours.
    """
    cfg = get_config()

    if is_quiet_hours():
        return {
            "should_fire": False,
            "reason": "quiet_hours",
            "hours_idle": 0,
            "is_quiet_hours": True,
        }

    hours = get_idle_hours(group_id)
    threshold = cfg.gossip.inactivity_threshold_hours

    if hours < threshold:
        return {
            "should_fire": False,
            "reason": f"chat active ({hours:.1f}h idle, need {threshold}h)",
            "hours_idle": round(hours, 1),
            "is_quiet_hours": False,
        }

    return {
        "should_fire": True,
        "reason": f"chat idle for {hours:.1f}h (threshold: {threshold}h)",
        "hours_idle": round(hours, 1),
        "is_quiet_hours": False,
    }


def get_recent_chat(days: int | None = None) -> str:
    """Read recent chat transcripts from markdown files."""
    cfg = get_config()
    if days is None:
        days = cfg.gossip.chat_history_days

    chat_dir = cfg.chat_dir
    chat_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    now = datetime.now(timezone.utc)

    for i in range(days):
        d = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        from datetime import timedelta
        d = d - timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        file_path = chat_dir / f"{date_str}.md"
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                lines.append(f"# {date_str}\n{content}")

    return "\n\n".join(lines) if lines else "(no recent chat)"


def get_group_dynamics() -> str:
    """Read the group dynamics summary."""
    cfg = get_config()
    path = cfg.group_dynamics_path
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "(no group dynamics summary yet)"


def update_group_dynamics(content: str) -> None:
    """Write updated group dynamics summary."""
    cfg = get_config()
    path = cfg.group_dynamics_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def get_gossip_history_text(group_id: str | None = None) -> str:
    """Get recent gossip history as text for context."""
    cfg = get_config()
    if group_id is None:
        group = get_default_group()
        if not group:
            return "(no gossip history)"
        group_id = group["id"]

    gossips = get_recent_gossip(group_id, limit=cfg.gossip.history_context_limit)
    if not gossips:
        return "(no gossip history)"

    lines = []
    for g in reversed(gossips):  # Chronological order
        lines.append(f"[{g['posted_at']}] {g['gossip_text']}")
    return "\n".join(lines)


def get_manual_input_text(group_id: str | None = None) -> str:
    """Get unused manual input from all members as text."""
    if group_id is None:
        group = get_default_group()
        if not group:
            return ""
        group_id = group["id"]

    members = get_members_by_group(group_id)
    lines = []
    for member in members:
        inputs = get_unused_manual_input(member["id"])
        for inp in inputs:
            lines.append(f"- {member['display_name']}: {inp['content']}")
    return "\n".join(lines) if lines else ""


def build_gossip_context(group_id: str | None = None) -> str:
    """Assemble the full context window for gossip generation."""
    chat = get_recent_chat()
    dossiers = get_all_dossiers()
    dynamics = get_group_dynamics()
    history = get_gossip_history_text(group_id)
    manual = get_manual_input_text(group_id)

    parts = [
        "## Recent Chat",
        chat,
        "",
        "## Member Dossiers",
        dossiers,
        "",
        "## Group Dynamics",
        dynamics,
        "",
        "## Previous Gossip (don't repeat these)",
        history,
    ]

    if manual:
        parts.extend(["", "## Fresh Intel (from members directly)", manual])

    return "\n\n".join(parts)


def append_chat_log(username: str, content: str, timestamp: datetime | None = None) -> None:
    """Append a message to the daily chat log."""
    cfg = get_config()
    chat_dir = cfg.chat_dir
    chat_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H:%M")
    file_path = chat_dir / f"{date_str}.md"

    line = f"[{time_str}] {username}: {content}\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(line)

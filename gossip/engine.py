"""Core gossip engine — context assembly and gossip generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import math

from gossip.config import get_config
from gossip.db import (
    get_chat_activity,
    get_default_group,
    get_dm_history,
    get_last_dm,
    get_members_by_group,
    get_members_with_location,
    get_oauth_token,
    get_recent_gossip,
    get_unused_manual_input,
)
from gossip.dossiers import get_all_dossiers, read_dossier


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


def compact_group_dynamics(content: str, max_chars: int = 2000) -> str:
    """Compact group dynamics to stay under max_chars.

    Keeps the last 5 entries per section, summarizes older ones into a
    single line. Pure text manipulation — no LLM call needed.
    """
    if len(content) <= max_chars:
        return content

    import re

    sections: dict[str, list[str]] = {}
    section_names = []
    current_section = None

    for line in content.split("\n"):
        header_match = re.match(r"^## (.+)$", line)
        if header_match:
            current_section = header_match.group(1).strip()
            if current_section not in sections:
                sections[current_section] = []
                section_names.append(current_section)
            continue
        if current_section and line.strip():
            sections[current_section].append(line)

    # Keep last 5 entries per section, summarize rest
    compacted_sections = {}
    for name in section_names:
        entries = sections.get(name, [])
        if len(entries) > 5:
            older_count = len(entries) - 5
            compacted_sections[name] = [
                f"- ({older_count} earlier entries merged)",
            ] + entries[-5:]
        else:
            compacted_sections[name] = entries

    # Rebuild
    parts = []
    for name in section_names:
        parts.append(f"## {name}")
        entries = compacted_sections.get(name, [])
        if entries:
            parts.extend(entries)
        parts.append("")

    result = "\n".join(parts)

    # If still over limit, truncate each section more aggressively
    if len(result) > max_chars:
        parts = []
        for name in section_names:
            parts.append(f"## {name}")
            entries = compacted_sections.get(name, [])
            parts.extend(entries[-3:])
            parts.append("")
        result = "\n".join(parts)

    return result


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


def get_member_locations_text(group_id: str | None = None) -> str:
    """Get member locations as text for context."""
    if group_id is None:
        group = get_default_group()
        if not group:
            return "(no location data)"
        group_id = group["id"]

    members = get_members_with_location(group_id)
    if not members:
        return "(no location data)"

    lines = []
    for m in members:
        updated = m.get("location_updated_at", "unknown")
        lines.append(f"- {m['display_name']}: {m.get('location_name', '?')} (as of {updated})")

    # Add proximity summary
    def _haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            dist = _haversine_km(
                members[i]["latitude"], members[i]["longitude"],
                members[j]["latitude"], members[j]["longitude"],
            )
            if dist < 1:
                lines.append(f"  * {members[i]['display_name']} and {members[j]['display_name']}: same area!")
            elif dist < 5:
                lines.append(f"  * {members[i]['display_name']} and {members[j]['display_name']}: nearby ({dist:.1f}km)")

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


def get_investigation_notes(group_id: str | None = None) -> str:
    """Flag knowledge gaps for the LLM: thin dossiers, absent members, never-DM'd."""
    if group_id is None:
        group = get_default_group()
        if not group:
            return ""
        group_id = group["id"]

    members = get_members_by_group(group_id)
    if not members:
        return ""

    now = datetime.now(timezone.utc)
    notes: list[str] = []

    for m in members:
        if m.get("is_paused"):
            continue

        name = m["display_name"]
        flags: list[str] = []

        # Thin dossier
        dossier = read_dossier(name)
        dossier_len = len(dossier) if "(no info yet)" not in dossier else 0
        if dossier_len < 200:
            flags.append(f"thin dossier ({dossier_len} chars)")

        # Not seen in 2+ days (check chat activity)
        activities = get_chat_activity(group_id)
        last_seen = None
        for a in activities:
            if a.get("last_human_author") == name:
                ts = datetime.fromisoformat(a["last_human_message_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if last_seen is None or ts > last_seen:
                    last_seen = ts

        if last_seen is None:
            flags.append("never seen in chat")
        elif (now - last_seen).total_seconds() > 2 * 86400:
            days = (now - last_seen).total_seconds() / 86400
            flags.append(f"silent for {days:.0f} days")

        # Never DM'd
        last_dm = get_last_dm(m["id"])
        if last_dm is None:
            flags.append("never DM'd")

        # No Google connected
        google_token = get_oauth_token(m["id"], "google")
        if not google_token:
            flags.append("Google not connected — send them the onboarding link")

        if flags:
            notes.append(f"- **{name}**: {', '.join(flags)}")

    return "\n".join(notes) if notes else "(all members well-covered)"


def get_dm_conversations_text(group_id: str | None = None) -> str:
    """Get recent DM conversations with each member for context."""
    if group_id is None:
        group = get_default_group()
        if not group:
            return ""
        group_id = group["id"]

    members = get_members_by_group(group_id)
    if not members:
        return ""

    conversations: list[str] = []
    for m in members:
        history = get_dm_history(m["id"], limit=5)
        if not history:
            continue

        lines = [f"**{m['display_name']}**:"]
        for dm in reversed(history):  # Chronological order
            direction = "→" if dm["direction"] == "outbound" else "←"
            lines.append(f"  {direction} {dm['message_text'][:200]}")
        conversations.append("\n".join(lines))

    return "\n\n".join(conversations) if conversations else ""


def build_gossip_context(group_id: str | None = None) -> str:
    """Assemble the full context window for gossip generation."""
    from gossip.logger import log_event, get_current_session_id

    chat = get_recent_chat()
    dossiers = get_all_dossiers()
    dynamics = get_group_dynamics()
    history = get_gossip_history_text(group_id)
    manual = get_manual_input_text(group_id)
    locations = get_member_locations_text(group_id)
    investigation = get_investigation_notes(group_id)
    dm_convos = get_dm_conversations_text(group_id)

    parts = [
        "## Recent Chat",
        chat,
        "",
        "## Member Dossiers",
        dossiers,
        "",
        "## Member Locations",
        locations,
        "",
        "## Group Dynamics",
        dynamics,
        "",
        "## Investigation Notes",
        investigation,
    ]

    if dm_convos:
        parts.extend(["", "## Recent DM Conversations", dm_convos])

    parts.extend([
        "",
        "## Previous Gossip (don't repeat these)",
        history,
    ])

    if manual:
        parts.extend(["", "## Fresh Intel (from members directly)", manual])

    context = "\n\n".join(parts)

    log_event(
        event_type="context_build",
        summary="Assembled gossip context",
        payload={
            "chat_chars": len(chat),
            "dossiers_chars": len(dossiers),
            "dynamics_chars": len(dynamics),
            "history_chars": len(history),
            "manual_chars": len(manual),
            "locations_chars": len(locations),
            "investigation_chars": len(investigation),
            "dm_convos_chars": len(dm_convos),
            "total_chars": len(context),
            "has_manual_input": bool(manual),
        },
        session_id=get_current_session_id(),
    )

    return context


def append_chat_log(username: str, content: str, timestamp: datetime | None = None) -> None:
    """Append a message to the daily chat log."""
    from gossip.logger import log_event, get_current_session_id

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

    log_event(
        event_type="chat_message",
        event_subtype="human",
        summary=f"Chat from {username} ({len(content)} chars)",
        payload={
            "username": username,
            "char_count": len(content),
            "date": date_str,
        },
        session_id=get_current_session_id(),
    )

"""Hermes hook that links session IDs to gossip events and captures chat history.

Fires on agent:start, agent:step, and agent:end to correlate Hermes session
transcripts with gossip-specific decision logs in the events table.

On agent:start, also logs the incoming message to the daily chat log and
updates the chat activity timer so the idle check works correctly.

On agent:end, writes a per-session trace JSON file for later analysis.
"""

import json
import sys
from pathlib import Path

# Add gossip project root to path so we can import gossip modules
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def handle(event_type: str, context: dict) -> None:
    """Called by Hermes HookRegistry on agent:start, agent:step, and agent:end."""
    try:
        from gossip.logger import log_event

        session_id = context.get("session_id", "")
        platform = context.get("platform", "")
        user_id = context.get("user_id", "")

        if event_type == "agent:start":
            message = context.get("message", "")

            # Log the incoming message to the daily chat file
            if message and platform:
                _capture_chat_message(platform, user_id, message)

            log_event(
                event_type="session_link",
                event_subtype="start",
                summary=f"Hermes session started on {platform}",
                payload={
                    "platform": platform,
                    "user_id": user_id,
                    "message_preview": message[:200],
                },
                session_id=session_id,
            )

        elif event_type == "agent:step":
            iteration = context.get("iteration", 0)
            tool_names = context.get("tool_names", [])

            log_event(
                event_type="session_link",
                event_subtype="step",
                summary=f"Session step {iteration}: {', '.join(tool_names) if tool_names else 'no tools'}",
                payload={
                    "platform": platform,
                    "user_id": user_id,
                    "iteration": iteration,
                    "tool_names": tool_names,
                },
                session_id=session_id,
            )

        elif event_type == "agent:end":
            log_event(
                event_type="session_link",
                event_subtype="end",
                summary=f"Hermes session ended on {platform}",
                payload={
                    "platform": platform,
                    "user_id": user_id,
                    "response_preview": context.get("response", "")[:200],
                },
                session_id=session_id,
            )

            # Write per-session trace JSON
            if session_id:
                _write_trace(session_id, platform, user_id)

    except Exception as e:
        # Never block the main pipeline
        print(f"[gossip-logger hook] Error: {e}", flush=True)


def _capture_chat_message(platform: str, user_id: str, message: str) -> None:
    """Log an incoming chat message and update the idle timer."""
    try:
        from gossip.identity import resolve_member
        from gossip.engine import append_chat_log
        from gossip.db import update_chat_activity, get_default_group

        # Resolve user_id to a display name
        member = resolve_member(platform=platform, user_id=user_id)
        username = member["display_name"] if member else f"{platform}:{user_id}"

        # Write to daily chat log (data/chat/YYYY-MM-DD.md)
        append_chat_log(username=username, content=message)

        # Update the idle timer so gossip_check_idle sees recent activity
        group = get_default_group()
        if group:
            update_chat_activity(
                group_id=group["id"],
                platform=platform,
                channel_id=platform,  # use platform as default channel
                author=username,
            )

    except Exception as e:
        print(f"[gossip-logger hook] Chat capture error: {e}", flush=True)


def _write_trace(session_id: str, platform: str, user_id: str) -> None:
    """Write a per-session trace JSON file for analysis."""
    try:
        from gossip.db import get_events_by_session
        from gossip.config import get_config

        cfg = get_config()
        trace_dir = cfg.log_dir / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)

        events = get_events_by_session(session_id)

        started_at = None
        ended_at = None
        trace_events = []

        for ev in events:
            ts = ev.get("created_at", "")
            if ev.get("event_subtype") == "start" and ev.get("event_type") == "session_link":
                started_at = ts
            if ev.get("event_subtype") == "end" and ev.get("event_type") == "session_link":
                ended_at = ts

            payload = {}
            if ev.get("payload_json"):
                try:
                    payload = json.loads(ev["payload_json"])
                except (json.JSONDecodeError, TypeError):
                    payload = {}

            trace_events.append({
                "type": ev.get("event_type", ""),
                "subtype": ev.get("event_subtype", ""),
                "summary": ev.get("summary", ""),
                "payload": payload,
            })

        trace = {
            "session_id": session_id,
            "platform": platform,
            "user_id": user_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "events": trace_events,
        }

        trace_path = trace_dir / f"{session_id}.json"
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, indent=2, default=str)

    except Exception as e:
        print(f"[gossip-logger hook] Trace write error: {e}", flush=True)

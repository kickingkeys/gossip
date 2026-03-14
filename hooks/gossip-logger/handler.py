"""Hermes hook that links session IDs to gossip events.

Fires on agent:start and agent:end to correlate Hermes session transcripts
with gossip-specific decision logs in the events table.
"""

import json
import sys
from pathlib import Path

# Add gossip project root to path so we can import gossip.logger
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def handle(event_type: str, context: dict) -> None:
    """Called by Hermes HookRegistry on agent:start and agent:end."""
    try:
        from gossip.logger import log_event

        session_id = context.get("session_id", "")
        platform = context.get("platform", "")
        user_id = context.get("user_id", "")

        if event_type == "agent:start":
            log_event(
                event_type="session_link",
                event_subtype="start",
                summary=f"Hermes session started on {platform}",
                payload={
                    "platform": platform,
                    "user_id": user_id,
                    "message_preview": context.get("message", "")[:200],
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

    except Exception as e:
        # Never block the main pipeline
        print(f"[gossip-logger hook] Error: {e}", flush=True)

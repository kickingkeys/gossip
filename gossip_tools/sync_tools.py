"""Hermes tool: gossip_sync_sources — sync calendar + gmail for all members."""

import json
import sys
from pathlib import Path

_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.registry import registry  # noqa: E402

SCHEMA = {
    "name": "gossip_sync_sources",
    "description": (
        "Sync calendar events and emails for all members who have connected Google OAuth. "
        "Updates their dossiers with recent calendar events and email activity."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handler(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group
    from gossip.logger import log_event, get_current_session_id

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_by_group(group["id"])
    results = {"calendar_synced": 0, "gmail_synced": 0, "skipped": 0, "errors": []}

    for member in members:
        # Calendar sync
        try:
            from gossip.sources.calendar import sync_member_calendar
            events = sync_member_calendar(member["id"], member["display_name"])
            if events and "error" not in events[0]:
                results["calendar_synced"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            results["errors"].append(f"calendar:{member['display_name']}:{e}")

        # Gmail sync
        try:
            from gossip.sources.gmail import sync_member_gmail
            emails = sync_member_gmail(member["id"], member["display_name"])
            if emails and "error" not in emails[0]:
                results["gmail_synced"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            results["errors"].append(f"gmail:{member['display_name']}:{e}")

    log_event(
        event_type="source_sync",
        summary=f"Synced sources: {results['calendar_synced']} calendars, {results['gmail_synced']} emails",
        payload=results,
        session_id=get_current_session_id(),
    )

    return json.dumps(results)


def _check():
    return True


registry.register(
    name="gossip_sync_sources",
    toolset="gossip",
    schema=SCHEMA,
    handler=_handler,
    check_fn=_check,
    is_async=False,
)

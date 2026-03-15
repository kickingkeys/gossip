"""Hermes tools: gossip_read_dossier, gossip_update_dossier."""

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

# ── Read Dossier ────────────────────────────────────────────────────────

READ_SCHEMA = {
    "name": "gossip_read_dossier",
    "description": "Read a specific member's dossier (what the bot knows about them).",
    "parameters": {
        "type": "object",
        "properties": {
            "member_name": {
                "type": "string",
                "description": "The member's display name.",
            },
        },
        "required": ["member_name"],
    },
}


def _handle_read(args, **kwargs):
    from gossip.dossiers import read_dossier
    from gossip.logger import log_event, get_current_session_id

    name = args.get("member_name", "")
    if not name:
        return json.dumps({"error": "member_name is required"})

    content = read_dossier(name)

    log_event(
        event_type="dossier_read",
        summary=f"Read dossier for {name}",
        payload={"member_name": name, "char_count": len(content)},
        session_id=get_current_session_id(),
    )

    return json.dumps({"member_name": name, "dossier": content})


# ── Update Dossier ──────────────────────────────────────────────────────

UPDATE_SCHEMA = {
    "name": "gossip_update_dossier",
    "description": "Add a new entry to a member's dossier.",
    "parameters": {
        "type": "object",
        "properties": {
            "member_name": {
                "type": "string",
                "description": "The member's display name.",
            },
            "entry": {
                "type": "string",
                "description": "The new information to add to their dossier.",
            },
            "source": {
                "type": "string",
                "description": "Where this info came from (e.g., 'chat', 'calendar', 'manual').",
            },
        },
        "required": ["member_name", "entry"],
    },
}


def _handle_update(args, **kwargs):
    from gossip.dossiers import append_dossier_from_source
    from gossip.logger import log_event, get_current_session_id

    name = args.get("member_name", "")
    entry = args.get("entry", "")
    source = args.get("source", "observation")

    if not name or not entry:
        return json.dumps({"error": "member_name and entry are required"})

    append_dossier_from_source(name, source, entry)

    log_event(
        event_type="dossier_update",
        event_subtype=source,
        summary=f"Updated dossier for {name} from {source}",
        payload={
            "member_name": name,
            "source": source,
            "entry_preview": entry[:200],
            "entry_chars": len(entry),
        },
        session_id=get_current_session_id(),
    )

    return json.dumps({"success": True, "member_name": name, "source": source})


def _check():
    return True


registry.register(
    name="gossip_read_dossier",
    toolset="gossip",
    schema=READ_SCHEMA,
    handler=_handle_read,
    check_fn=_check,
    is_async=False,
)

registry.register(
    name="gossip_update_dossier",
    toolset="gossip",
    schema=UPDATE_SCHEMA,
    handler=_handle_update,
    check_fn=_check,
    is_async=False,
)

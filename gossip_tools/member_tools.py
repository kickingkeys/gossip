"""Hermes tools: gossip_list_members, gossip_get_member."""

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

# ── List Members ────────────────────────────────────────────────────────

LIST_SCHEMA = {
    "name": "gossip_list_members",
    "description": "List all members in the gossip group with their connected platforms.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_list(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured", "members": []})

    members = get_members_by_group(group["id"])
    result = []
    for m in members:
        result.append({
            "name": m["display_name"],
            "discord": m.get("discord_username") or None,
            "telegram": m.get("telegram_username") or None,
            "paused": bool(m.get("is_paused")),
        })

    return json.dumps({"group": group["name"], "members": result})


# ── Get Member ──────────────────────────────────────────────────────────

GET_SCHEMA = {
    "name": "gossip_get_member",
    "description": "Get detailed info about a specific member by name.",
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


def _handle_get(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group, get_unused_manual_input
    from gossip.dossiers import read_dossier, list_dossier_entries

    name = args.get("member_name", "")
    if not name:
        return json.dumps({"error": "member_name is required"})

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_by_group(group["id"])
    member = None
    for m in members:
        if m["display_name"].lower() == name.lower():
            member = m
            break

    if not member:
        return json.dumps({"error": f"member '{name}' not found"})

    dossier = read_dossier(member["display_name"])
    entries = list_dossier_entries(member["display_name"])
    manual = get_unused_manual_input(member["id"])

    return json.dumps({
        "name": member["display_name"],
        "discord": member.get("discord_username"),
        "telegram": member.get("telegram_username"),
        "paused": bool(member.get("is_paused")),
        "dossier": dossier,
        "dossier_entries": entries,
        "pending_manual_input": [m["content"] for m in manual],
    })


def _check():
    return True


registry.register(
    name="gossip_list_members",
    toolset="gossip",
    schema=LIST_SCHEMA,
    handler=_handle_list,
    check_fn=_check,
    is_async=False,
)

registry.register(
    name="gossip_get_member",
    toolset="gossip",
    schema=GET_SCHEMA,
    handler=_handle_get,
    check_fn=_check,
    is_async=False,
)

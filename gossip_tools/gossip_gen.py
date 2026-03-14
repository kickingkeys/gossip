"""Hermes tool: gossip_generate — generate gossip and log it."""

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
    "name": "gossip_generate",
    "description": (
        "Generate a gossip message based on context and log it to history. "
        "Call gossip_build_context first to get the context, then pass the "
        "generated gossip text here to log it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "gossip_text": {
                "type": "string",
                "description": "The gossip message to log and post.",
            },
            "context_summary": {
                "type": "string",
                "description": "Brief summary of why this gossip was generated (e.g., 'chat idle 4.2h').",
            },
        },
        "required": ["gossip_text"],
    },
}


def _handler(args, **kwargs):
    from gossip.db import add_gossip, get_default_group, log_action, update_chat_activity

    gossip_text = args.get("gossip_text", "").strip()
    if not gossip_text:
        return json.dumps({"error": "gossip_text is required"})

    context_summary = args.get("context_summary", "")

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    # Log the gossip
    gossip_id = add_gossip(
        group_id=group["id"],
        gossip_text=gossip_text,
        context_summary=context_summary,
    )

    # Reset inactivity timer (the gossip itself counts as activity... from the bot)
    # We don't reset here — only human messages reset the timer

    # Log the action
    log_action(
        "gossip_drop",
        f"Dropped gossip: {gossip_text[:100]}",
        json.dumps({"gossip_id": gossip_id, "context": context_summary}),
    )

    return json.dumps({
        "success": True,
        "gossip_id": gossip_id,
        "message": "Gossip logged. It will be delivered to the chat channel.",
    })


def _check():
    return True


registry.register(
    name="gossip_generate",
    toolset="gossip",
    schema=SCHEMA,
    handler=_handler,
    check_fn=_check,
    is_async=False,
)

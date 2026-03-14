"""Hermes tool: gossip_build_context — assemble full context for gossip generation."""

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
    "name": "gossip_build_context",
    "description": (
        "Build the full context window for gossip generation. "
        "Returns recent chat, member dossiers, group dynamics, gossip history, "
        "and any fresh intel from manual input."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handler(args, **kwargs):
    from gossip.engine import build_gossip_context
    from gossip.logger import timed_event

    with timed_event("context_build", "Assembling gossip context") as ctx:
        context = build_gossip_context()
        # Capture context stats for analysis
        sections = context.split("## ")
        ctx["payload"] = {
            "total_chars": len(context),
            "section_count": len(sections) - 1,  # first split is before first ##
        }

    return json.dumps({"context": context})


def _check():
    return True


registry.register(
    name="gossip_build_context",
    toolset="gossip",
    schema=SCHEMA,
    handler=_handler,
    check_fn=_check,
    is_async=False,
)

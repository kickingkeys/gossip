"""Hermes tool: gossip_check_idle — check if chat is idle enough for gossip."""

import json
import sys
from pathlib import Path

# Add hermes to path for registry access
_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

# Add project root for gossip package access
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.registry import registry  # noqa: E402

SCHEMA = {
    "name": "gossip_check_idle",
    "description": (
        "Check if the group chat has been idle long enough to drop gossip. "
        "Returns whether gossip should fire, hours idle, and quiet hours status."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handler(args, **kwargs):
    from gossip.engine import should_gossip

    result = should_gossip()
    return json.dumps(result)


def _check():
    return True


registry.register(
    name="gossip_check_idle",
    toolset="gossip",
    schema=SCHEMA,
    handler=_handler,
    check_fn=_check,
    is_async=False,
)

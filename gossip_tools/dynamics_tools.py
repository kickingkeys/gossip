"""Hermes tools: gossip_update_dynamics, gossip_read_dynamics."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.registry import registry  # noqa: E402

SECTIONS = [
    "Relationships",
    "Behavioral Patterns",
    "Running Jokes & References",
    "Recent Observations",
]

# ── Update Dynamics ────────────────────────────────────────────────────

UPDATE_SCHEMA = {
    "name": "gossip_update_dynamics",
    "description": (
        "Update group dynamics with new observations about relationships, "
        "behavioral patterns, running jokes, or recent observations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "relationships": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New relationship observations (e.g., 'Alex and Jordan: always hanging out').",
            },
            "behavioral_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New behavioral pattern observations (e.g., 'Alex: night owl, most active after 11pm').",
            },
            "running_jokes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New running jokes or references (e.g., '\"The ramen incident\" — Alex spilled ramen').",
            },
            "observations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recent timestamped observations.",
            },
        },
        "required": [],
    },
}


def _handle_update(args, **kwargs):
    from gossip.engine import get_group_dynamics, update_group_dynamics, compact_group_dynamics
    from gossip.logger import log_event, get_current_session_id

    current = get_group_dynamics()

    # Parse existing sections
    section_content = _parse_sections(current)

    # Map args to section names
    mapping = {
        "relationships": "Relationships",
        "behavioral_patterns": "Behavioral Patterns",
        "running_jokes": "Running Jokes & References",
        "observations": "Recent Observations",
    }

    added = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for arg_key, section_name in mapping.items():
        entries = args.get(arg_key, [])
        if not entries:
            continue
        for entry in entries:
            if arg_key == "observations":
                line = f"- [{today}] {entry}"
            else:
                line = f"- {entry}"
            section_content[section_name].append(line)
            added += 1

    # Rebuild markdown
    new_content = _build_markdown(section_content)

    # Compact if over limit
    new_content = compact_group_dynamics(new_content)

    update_group_dynamics(new_content)

    log_event(
        event_type="dynamics_update",
        summary=f"Updated group dynamics ({added} entries added)",
        payload={"entries_added": added, "total_chars": len(new_content)},
        session_id=get_current_session_id(),
    )

    return json.dumps({"success": True, "entries_added": added, "total_chars": len(new_content)})


# ── Read Dynamics ──────────────────────────────────────────────────────

READ_SCHEMA = {
    "name": "gossip_read_dynamics",
    "description": "Read the current group dynamics summary.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_read(args, **kwargs):
    from gossip.engine import get_group_dynamics
    from gossip.logger import log_event, get_current_session_id

    content = get_group_dynamics()

    log_event(
        event_type="dynamics_read",
        summary=f"Read group dynamics ({len(content)} chars)",
        payload={"char_count": len(content)},
        session_id=get_current_session_id(),
    )

    return json.dumps({"dynamics": content})


# ── Helpers ────────────────────────────────────────────────────────────

def _parse_sections(content: str) -> dict[str, list[str]]:
    """Parse group.md into section name -> list of lines."""
    result = {s: [] for s in SECTIONS}

    current_section = None
    for line in content.split("\n"):
        header_match = re.match(r"^## (.+)$", line)
        if header_match:
            name = header_match.group(1).strip()
            if name in result:
                current_section = name
            else:
                current_section = None
            continue
        if current_section and line.strip():
            result[current_section].append(line)

    return result


def _build_markdown(sections: dict[str, list[str]]) -> str:
    """Build group.md from section dict."""
    parts = []
    for name in SECTIONS:
        parts.append(f"## {name}")
        entries = sections.get(name, [])
        if entries:
            parts.extend(entries)
        parts.append("")
    return "\n".join(parts)


def _check():
    return True


registry.register(
    name="gossip_update_dynamics",
    toolset="gossip",
    schema=UPDATE_SCHEMA,
    handler=_handle_update,
    check_fn=_check,
    is_async=False,
)

"""Background synthesizer — generates structured member summaries.

Called by OpenClaw cron job via the tool API or directly after OAuth deep sync.
Uses Haiku. Never writes user-facing text.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from gossip.config import get_config
from gossip.db import (
    get_member_summary,
    get_members_by_group,
    get_default_group,
    upsert_member_summary,
)
from gossip.dossiers import read_dossier
from gossip.engine import get_recent_chat


SUMMARY_STRUCTURE = {
    "this_week": "",
    "patterns": "",
    "relationships": "",
    "recent": "",
    "flagged": "",
    "donny_notes": "",
    "updated": "",
}


def build_synthesizer_input(member_id: str, member_name: str) -> str:
    """Assemble raw data for the synthesizer. NO DM content included."""
    parts = []

    # Dossier (legacy, read-only)
    dossier = read_dossier(member_name)
    if "(no info yet)" not in dossier:
        parts.append(f"## Existing Dossier\n{dossier[:1000]}")

    # Previous summary (for continuity, especially donny_notes)
    prev = get_member_summary(member_id)
    if prev:
        parts.append(f"## Previous Summary\n{prev['summary_json']}")

    # Recent chat mentions
    chat = get_recent_chat(days=2)
    mention_lines = [
        line for line in chat.split("\n")
        if member_name.lower() in line.lower()
    ]
    if mention_lines:
        parts.append(
            "## Chat Mentions (last 2 days)\n" + "\n".join(mention_lines[-20:])
        )

    return "\n\n".join(parts) if parts else "(no data available)"


def get_synthesizer_prompt(member_name: str, raw_input: str) -> str:
    """Build the prompt for the Haiku synthesizer."""
    now = datetime.now(timezone.utc).isoformat()
    return f"""You are a background data processor. Analyze the following raw data about {member_name} and produce a structured JSON summary. Do NOT write any conversational text. Output ONLY valid JSON.

Raw data:
{raw_input}

Output this exact JSON structure:
{{
  "this_week": "brief summary of what's happening this week",
  "patterns": "behavioral patterns observed",
  "relationships": "who they interact with, dynamics",
  "recent": "last notable thing",
  "flagged": "anything sensitive or time-sensitive",
  "donny_notes": "running jokes, relationship dynamics to remember (PRESERVE from previous summary if exists)",
  "updated": "{now}"
}}

Rules:
- Keep each field under 200 chars
- Preserve donny_notes from previous summary — these are long-term memory
- Flag time-sensitive items (upcoming events, deadlines)
- Do NOT include any DM content
- Do NOT write conversational text
- Output ONLY the JSON object, nothing else"""


def run_synthesizer_for_member(member_id: str, member_name: str) -> dict | None:
    """Run the full synthesizer pipeline for one member.

    Calls Anthropic Haiku directly. Used for immediate synthesis
    (e.g., after OAuth deep sync) and by the cron job via API.
    Returns the parsed summary dict, or None on failure.
    """
    from gossip.logger import log_event

    raw_input = build_synthesizer_input(member_id, member_name)
    if raw_input == "(no data available)":
        return None

    prompt = get_synthesizer_prompt(member_name, raw_input)

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        summary = json.loads(content)

        # Save to DB
        summary_json = json.dumps(summary)
        upsert_member_summary(member_id, summary_json)

        # Save to file
        cfg = get_config()
        cfg.summaries_dir.mkdir(parents=True, exist_ok=True)
        summary_path = cfg.summaries_dir / f"{member_name.lower().replace(' ', '_')}.md"
        summary_path.write_text(
            f"# {member_name} — Summary\n\n"
            f"**This Week:** {summary.get('this_week', '')}\n\n"
            f"**Patterns:** {summary.get('patterns', '')}\n\n"
            f"**Relationships:** {summary.get('relationships', '')}\n\n"
            f"**Recent:** {summary.get('recent', '')}\n\n"
            f"**Flagged:** {summary.get('flagged', '')}\n\n"
            f"**Donny Notes:** {summary.get('donny_notes', '')}\n\n"
            f"*Updated: {summary.get('updated', '')}*\n",
            encoding="utf-8",
        )

        log_event(
            event_type="synthesizer",
            event_subtype="success",
            summary=f"Synthesized summary for {member_name}",
            payload={
                "member_name": member_name,
                "summary_chars": len(summary_json),
            },
        )

        return summary

    except Exception as e:
        log_event(
            event_type="synthesizer",
            event_subtype="error",
            summary=f"Synthesizer failed for {member_name}: {e}",
            payload={
                "member_name": member_name,
                "error": str(e),
            },
        )
        return None


def run_synthesizer_all() -> dict:
    """Run synthesizer for all members in the default group.

    Returns: {"synthesized": int, "failed": int, "members": [...]}
    """
    group = get_default_group()
    if not group:
        return {"synthesized": 0, "failed": 0, "members": []}

    members = get_members_by_group(group["id"])
    results = {"synthesized": 0, "failed": 0, "members": []}

    for m in members:
        if m.get("is_paused"):
            continue

        result = run_synthesizer_for_member(m["id"], m["display_name"])
        if result:
            results["synthesized"] += 1
            results["members"].append({"name": m["display_name"], "status": "ok"})
        else:
            results["failed"] += 1
            results["members"].append({"name": m["display_name"], "status": "failed"})

    return results

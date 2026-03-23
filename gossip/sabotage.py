"""Sabotage intelligence module — cross-references data to find ammunition.

Finds contradictions, overlaps, patterns, and gossip-worthy intel
by comparing calendars, DM statements, and chat activity across members.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from gossip.db import (
    get_default_group,
    get_dm_history,
    get_members_by_group,
    get_oauth_token,
)
from gossip.dossiers import read_dossier


def _normalize_place(place: str) -> str:
    """Normalize a place name for comparison."""
    # Strip everything after the first comma (remove city, state, zip)
    place = place.split(",")[0].strip()
    # Remove parenthetical dates/counts
    place = re.sub(r"\(.*?\)", "", place).strip()
    # Remove leading dashes/bullets
    place = place.lstrip("- ").strip()
    return place.lower()


def _parse_dossier_sections(dossier: str) -> dict:
    """Parse a dossier into sections by ## headers."""
    sections: dict[str, str] = {}
    current_section = ""
    current_lines: list[str] = []

    for line in dossier.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines)
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines)

    return sections


def find_calendar_overlaps(group_id: str | None = None) -> list[dict]:
    """Find members with events at the same place or shared events."""
    if not group_id:
        group = get_default_group()
        if not group:
            return []
        group_id = group["id"]

    members = get_members_by_group(group_id)
    overlaps = []

    member_places: dict[str, set[str]] = {}
    member_events: dict[str, list[str]] = {}

    for m in members:
        dossier = read_dossier(m["display_name"])
        # Skip only if dossier is ONLY the empty header (no real data)
        if dossier.strip() == f"# {m['display_name']}\n\n(no info yet)".strip():
            continue
        if len(dossier) < 50:
            continue

        name = m["display_name"]
        places: set[str] = set()
        events: list[str] = []

        # Scan the ENTIRE dossier for place and event data
        for line in dossier.split("\n"):
            line = line.strip()

            # "- 370 Jay St (5 visits)" pattern
            if "visits)" in line:
                place = _normalize_place(line)
                if place and len(place) > 3:
                    places.add(place)

            # "- Event Name @ Place (date)" — extract both event and place
            if "@ " in line and line.startswith("- "):
                parts = line.split("@")
                if len(parts) > 1:
                    place = _normalize_place(parts[-1])
                    if place and len(place) > 3:
                        places.add(place)
                    # Also capture event name
                    event_name = parts[0].strip("- ").strip().lower()
                    if event_name and len(event_name) > 3:
                        events.append(event_name)

            # "Coming up:" events without @
            if line.startswith("- ") and ("2026-" in line or "2025-" in line) and "@" not in line:
                event_name = line.split("(")[0].strip("- ").strip().lower()
                if event_name and len(event_name) > 3:
                    events.append(event_name)

        # Deduplicate events
        events = list(set(events))

        member_places[name] = places
        member_events[name] = events

    # Find place overlaps
    names = list(member_places.keys())
    seen_overlaps: set[str] = set()

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            shared = member_places.get(a, set()) & member_places.get(b, set())
            for place in shared:
                key = f"{min(a,b)}|{max(a,b)}|{place}"
                if key not in seen_overlaps:
                    seen_overlaps.add(key)
                    overlaps.append({
                        "members": [a, b],
                        "detail": f"both go to {place}",
                        "type": "same_place",
                    })

    # Find shared event names
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            events_a = set(member_events.get(a, []))
            events_b = set(member_events.get(b, []))
            shared = events_a & events_b
            for event in shared:
                key = f"{min(a,b)}|{max(a,b)}|{event}"
                if key not in seen_overlaps:
                    seen_overlaps.add(key)
                    overlaps.append({
                        "members": [a, b],
                        "detail": f"both have '{event}' on their calendar",
                        "type": "same_event",
                    })

    return overlaps


def find_contradictions(group_id: str | None = None) -> list[dict]:
    """Find contradictions between what people said and what their data shows."""
    if not group_id:
        group = get_default_group()
        if not group:
            return []
        group_id = group["id"]

    members = get_members_by_group(group_id)
    contradictions = []

    for m in members:
        name = m["display_name"]
        dossier = read_dossier(name)
        dm_history = get_dm_history(m["id"], limit=20)

        # Check DM statements against calendar
        for dm in dm_history:
            text = dm["message_text"].lower()
            if dm["direction"] != "inbound":
                continue

            # "staying in" / "not doing anything" contradictions
            staying_in = any(phrase in text for phrase in [
                "staying in", "not doing anything", "nothing planned",
                "just chilling", "no plans", "quiet weekend",
                "not going out", "staying home",
            ])

            if staying_in and "(no info yet)" not in dossier:
                sections = _parse_dossier_sections(dossier)
                for section_name, section_text in sections.items():
                    if "calendar" in section_name.lower() and "Coming up:" in section_text:
                        contradictions.append({
                            "member": name,
                            "said": dm["message_text"][:100],
                            "but": "calendar shows upcoming events",
                            "source": "dm_vs_calendar",
                        })
                        break

            # Check for specific place denials
            # e.g., "i haven't been to [place]" but dossier shows visits
            denial_match = re.search(r"(?:haven't|havent|never) (?:been to|gone to|visited) (.+)", text)
            if denial_match and "(no info yet)" not in dossier:
                denied_place = denial_match.group(1).strip().lower()
                if denied_place in dossier.lower():
                    contradictions.append({
                        "member": name,
                        "said": dm["message_text"][:100],
                        "but": f"dossier mentions '{denied_place}'",
                        "source": "dm_vs_dossier",
                    })

    return contradictions


def find_gossip_ammunition(group_id: str | None = None) -> dict:
    """Assemble all available ammunition for gossip."""
    overlaps = find_calendar_overlaps(group_id)
    contradictions = find_contradictions(group_id)

    if not group_id:
        group = get_default_group()
        if not group:
            return {"overlaps": [], "contradictions": [], "opportunities": []}
        group_id = group["id"]

    members = get_members_by_group(group_id)
    opportunities = []

    for m in members:
        dossier = read_dossier(m["display_name"])
        dossier_size = len(dossier) if len(dossier) > 100 else 0
        has_google = get_oauth_token(m["id"], "google") is not None

        # Inbound-only DM count (what they told us)
        all_dms = get_dm_history(m["id"], limit=50)
        inbound_count = sum(1 for d in all_dms if d["direction"] == "inbound")
        total_dm_count = len(all_dms)

        # Members with data but few inbound DMs = untapped intel
        if has_google and dossier_size > 200 and inbound_count < 2:
            opportunities.append({
                "member": m["display_name"],
                "reason": f"has {dossier_size} chars of data but only {inbound_count} inbound DMs — needs interrogation",
                "priority": "high",
            })

        # Members with no Google = blind spot
        if not has_google:
            opportunities.append({
                "member": m["display_name"],
                "reason": "no Google connected — operating blind on this person",
                "priority": "medium",
            })

        # Members who DM a lot = good source, keep cultivating
        if inbound_count > 3:
            opportunities.append({
                "member": m["display_name"],
                "reason": f"active source ({inbound_count} inbound DMs) — keep cultivating",
                "priority": "low",
            })

    return {
        "overlaps": overlaps,
        "contradictions": contradictions,
        "opportunities": opportunities,
    }

"""Dossier compaction — deduplicates, trims, and caps dossier size.

Runs after sync to prevent bloat. Keeps the most recent and unique data.
Target: ~10k tokens (40kb) per person max.
"""

from __future__ import annotations

import re
from pathlib import Path

from gossip.config import get_config

MAX_DOSSIER_BYTES = 40_000  # ~10k tokens


def compact_dossier(member_name: str) -> dict:
    """Compact a member's dossier: deduplicate sections, trim to size cap.

    Returns: {"before_bytes": int, "after_bytes": int, "sections_removed": int}
    """
    cfg = get_config()
    path = cfg.dossiers_dir / f"{member_name.lower().replace(' ', '_')}.md"

    if not path.exists():
        return {"before_bytes": 0, "after_bytes": 0, "sections_removed": 0}

    content = path.read_text(encoding="utf-8")
    before_bytes = len(content.encode("utf-8"))

    # Parse into header + sections
    lines = content.split("\n")
    header_lines = []
    sections = []
    current_section = None
    current_lines = []

    for line in lines:
        if line.startswith("## "):
            if current_section:
                sections.append({"title": current_section, "lines": current_lines})
            current_section = line
            current_lines = []
        elif current_section is None:
            header_lines.append(line)
        else:
            current_lines.append(line)

    if current_section:
        sections.append({"title": current_section, "lines": current_lines})

    # Deduplicate: keep only the LATEST section of each type
    # Section titles look like: ## Calendar (2026-03-19), ## Email (2026-03-20)
    # Group by base type (Calendar, Email, Location, etc.)
    type_groups: dict[str, list[dict]] = {}
    for sec in sections:
        # Extract base type: "Calendar (2026-03-19)" -> "Calendar"
        base = re.sub(r"\s*\(.*\)", "", sec["title"].lstrip("# ")).strip()
        if base not in type_groups:
            type_groups[base] = []
        type_groups[base].append(sec)

    # Keep only the LATEST section per type, deduplicate content
    kept_sections = []
    sections_removed = 0
    for base_type, secs in type_groups.items():
        # Take the latest section
        latest = secs[-1]

        # If there are multiple sections, merge unique lines from all into the latest
        if len(secs) > 1:
            all_lines = set()
            for s in secs:
                for line in s["lines"]:
                    stripped = line.strip()
                    if stripped:
                        all_lines.add(stripped)

            # Keep only unique lines in the latest section
            latest["lines"] = [line for line in latest["lines"] if line.strip()]
            existing = set(l.strip() for l in latest["lines"])
            for line in sorted(all_lines):
                if line not in existing and line.startswith("- "):
                    latest["lines"].append(line)

            sections_removed += len(secs) - 1

        kept_sections.append(latest)

    # Deduplicate lines within sections
    for sec in kept_sections:
        seen = set()
        unique_lines = []
        for line in sec["lines"]:
            stripped = line.strip()
            if stripped and stripped.startswith("- "):
                if stripped not in seen:
                    seen.add(stripped)
                    unique_lines.append(line)
            else:
                unique_lines.append(line)
        sec["lines"] = unique_lines

    # Rebuild content
    # Clean up header — remove "(no info yet)" if there's real data
    header_text = "\n".join(header_lines)
    if kept_sections and "(no info yet)" in header_text:
        header_text = header_text.replace("(no info yet)", "").strip()
        # Ensure it still has the # Name line
        if not header_text.startswith("# "):
            header_text = f"# {member_name}\n"

    parts = [header_text]
    for sec in kept_sections:
        parts.append(sec["title"])
        parts.extend(sec["lines"])

    new_content = "\n".join(parts).strip() + "\n"

    # If still over cap, truncate from the top (oldest sections)
    while len(new_content.encode("utf-8")) > MAX_DOSSIER_BYTES and len(kept_sections) > 1:
        kept_sections.pop(0)
        sections_removed += 1
        parts = [header_text]
        for sec in kept_sections:
            parts.append(sec["title"])
            parts.extend(sec["lines"])
        new_content = "\n".join(parts).strip() + "\n"

    path.write_text(new_content, encoding="utf-8")
    after_bytes = len(new_content.encode("utf-8"))

    return {
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "sections_removed": sections_removed,
    }


def compact_all_dossiers() -> dict:
    """Compact all dossiers. Returns summary."""
    cfg = get_config()
    dossiers_dir = cfg.dossiers_dir
    dossiers_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    total_before = 0
    total_after = 0

    for path in sorted(dossiers_dir.glob("*.md")):
        name = path.stem.replace("_", " ").title()
        result = compact_dossier(name)
        results[name] = result
        total_before += result["before_bytes"]
        total_after += result["after_bytes"]

    return {
        "members": results,
        "total_before": total_before,
        "total_after": total_after,
        "saved_bytes": total_before - total_after,
        "saved_pct": round((1 - total_after / total_before) * 100, 1) if total_before else 0,
    }

"""Markdown dossier management for group members."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gossip.config import get_config


def _dossier_path(member_name: str) -> Path:
    cfg = get_config()
    dir_path = cfg.dossiers_dir
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{member_name.lower().replace(' ', '_')}.md"


def read_dossier(member_name: str) -> str:
    """Read a member's dossier. Returns empty header if none exists."""
    path = _dossier_path(member_name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"# {member_name}\n\n(no info yet)\n"


def write_dossier(member_name: str, content: str) -> None:
    """Overwrite a member's dossier."""
    path = _dossier_path(member_name)
    path.write_text(content, encoding="utf-8")


def append_dossier(member_name: str, entry: str) -> None:
    """Append an entry to a member's dossier."""
    path = _dossier_path(member_name)
    existing = read_dossier(member_name)
    path.write_text(existing.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def append_dossier_from_source(
    member_name: str, source: str, content: str, subject: str | None = None
) -> None:
    """Append a structured entry from a data source (calendar, email, social, manual)."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"## {source.title()} ({date})"]
    if subject:
        lines.append(f"**Subject:** {subject}")
    lines.append("")
    lines.append(content.strip()[:500])  # Cap at 500 chars
    append_dossier(member_name, "\n".join(lines))


def get_all_dossiers() -> str:
    """Read all dossiers and return as a single string, separated by ---."""
    cfg = get_config()
    dir_path = cfg.dossiers_dir
    dir_path.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    for path in sorted(dir_path.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            # Truncate per dossier
            max_chars = cfg.gossip.dossier_max_chars
            if len(content) > max_chars:
                content = content[:max_chars] + "\n...(truncated)"
            parts.append(content)

    return "\n---\n".join(parts) if parts else "(no dossiers yet)"


def delete_dossier_entry(member_name: str, entry_index: int) -> bool:
    """Delete a specific section from a member's dossier by index.

    Sections are delimited by ## headers. Index 0 is the first ## section
    (not the # title).
    """
    content = read_dossier(member_name)
    lines = content.split("\n")

    # Find all ## section start indices
    section_starts: list[int] = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            section_starts.append(i)

    if entry_index < 0 or entry_index >= len(section_starts):
        return False

    # Determine section boundaries
    start = section_starts[entry_index]
    end = section_starts[entry_index + 1] if entry_index + 1 < len(section_starts) else len(lines)

    # Remove the section
    new_lines = lines[:start] + lines[end:]
    write_dossier(member_name, "\n".join(new_lines))
    return True


def list_dossier_entries(member_name: str) -> list[dict]:
    """List all ## sections in a dossier with their index and title."""
    content = read_dossier(member_name)
    entries = []
    for i, line in enumerate(content.split("\n")):
        if line.startswith("## "):
            entries.append({"index": len(entries), "title": line[3:].strip(), "line": i})
    return entries

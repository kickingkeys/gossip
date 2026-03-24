"""Google Calendar API connector.

Reads calendars shared with the bot's Google account,
and optionally per-member calendars via their OAuth tokens.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from gossip.config import get_config
from gossip.db import get_members_by_group, get_oauth_token
from gossip.dossiers import append_dossier_from_source


def _get_calendar_service(credentials=None):
    """Build a Google Calendar API service client."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if credentials is None:
        # Use bot's own credentials from environment
        creds = Credentials(
            token=os.getenv("GOOGLE_ACCESS_TOKEN"),
            refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )
    else:
        creds = credentials

    return build("calendar", "v3", credentials=creds)


def _extract_attendees(event: dict) -> list[dict[str, str]]:
    """Extract attendee emails and names from a Google Calendar event."""
    attendees = []
    for att in event.get("attendees", []):
        email = att.get("email", "")
        name = att.get("displayName", "")
        status = att.get("responseStatus", "needsAction")
        if email:
            attendees.append({
                "email": email,
                "name": name,
                "status": status,
            })
    return attendees


def fetch_upcoming_events(
    credentials=None,
    calendar_id: str = "primary",
    days_ahead: int = 3,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Fetch upcoming calendar events."""
    try:
        service = _get_calendar_service(credentials)
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for event in result.get("items", []):
            start = event.get("start", {})
            events.append({
                "summary": event.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": event.get("end", {}).get("dateTime", ""),
                "location": event.get("location", ""),
                "description": (event.get("description") or "")[:200],
                "attendees": _extract_attendees(event),
            })
        return events

    except Exception as e:
        from gossip.logger import log_event
        log_event(
            event_type="calendar_sync",
            event_subtype="error",
            summary=f"Calendar fetch failed: {e}",
            payload={"calendar_id": calendar_id, "error": str(e)},
        )
        return [{"error": str(e)}]


def fetch_shared_calendars() -> list[dict[str, str]]:
    """List all calendars shared with the bot's Google account."""
    try:
        service = _get_calendar_service()
        result = service.calendarList().list().execute()
        calendars = []
        for cal in result.get("items", []):
            calendars.append({
                "id": cal["id"],
                "summary": cal.get("summary", ""),
                "access_role": cal.get("accessRole", ""),
            })
        return calendars
    except Exception as e:
        return [{"error": str(e)}]


def _cross_reference_attendees(events: list[dict], member_name: str) -> list[str]:
    """Cross-reference attendee emails against known members.

    Returns lines describing shared events with other group members.
    """
    from gossip.db import get_default_group

    group = get_default_group()
    if not group:
        return []

    members = get_members_by_group(group["id"])

    # Build email-to-member lookup from OAuth tokens and known emails
    email_to_member: dict[str, str] = {}
    for m in members:
        if m["display_name"].lower() == member_name.lower():
            continue
        # Check if member has a Google token — their email is in the token record
        token = get_oauth_token(m["id"], "google")
        if token and token.get("scopes"):
            # The member's email can be inferred from their display name as fallback
            pass
        # Also check dossier for email patterns (rough heuristic)
        dn_lower = m["display_name"].lower().replace(" ", "")
        # We'll match on partial username in email
        email_to_member[dn_lower] = m["display_name"]

    shared_lines: list[str] = []
    seen: set[str] = set()

    for ev in events:
        attendees = ev.get("attendees", [])
        if not attendees:
            continue
        for att in attendees:
            email = att.get("email", "").lower()
            att_name = att.get("name", "")
            if not email:
                continue
            # Check against each known member
            for m in members:
                if m["display_name"].lower() == member_name.lower():
                    continue
                m_lower = m["display_name"].lower()
                # Match by name in attendee display name, or by username fragment in email
                name_match = (
                    m_lower in att_name.lower()
                    or m_lower.replace(" ", "") in email.split("@")[0]
                    or (m.get("discord_username") and m["discord_username"].lower() in email.split("@")[0])
                )
                if name_match:
                    key = f"{m['display_name']}|{ev['summary']}"
                    if key not in seen:
                        seen.add(key)
                        shared_lines.append(
                            f"- Shared event with {m['display_name']}: {ev['summary']} ({ev.get('start', '')[:10]})"
                        )

    return shared_lines


def sync_member_calendar(member_id: str, member_name: str) -> list[dict]:
    """Sync a member's calendar events into their dossier."""
    from gossip.logger import log_event

    token_data = get_oauth_token(member_id, "google")
    if not token_data:
        log_event(
            event_type="calendar_sync",
            event_subtype="skip",
            summary=f"No Google OAuth token for {member_name}",
            payload={"member_name": member_name, "member_id": member_id},
        )
        return []

    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )

    events = fetch_upcoming_events(credentials=creds, days_ahead=7)

    if events and "error" not in events[0]:
        # Build a summary of upcoming events for the dossier
        lines = []
        for ev in events[:5]:  # Top 5 events
            line = f"- {ev['summary']}"
            if ev.get("location"):
                line += f" @ {ev['location']}"
            if ev.get("start"):
                line += f" ({ev['start'][:16]})"
            # Note attendee count if present
            att_count = len(ev.get("attendees", []))
            if att_count > 1:
                line += f" [{att_count} attendees]"
            lines.append(line)

        # Cross-reference attendees against known members
        shared_lines = _cross_reference_attendees(events, member_name)
        if shared_lines:
            lines.append("\n**Shared events with group members:**")
            lines.extend(shared_lines)

        if lines:
            summary = "\n".join(lines)
            append_dossier_from_source(
                member_name, "calendar", summary, subject="Upcoming Events"
            )

        log_event(
            event_type="calendar_sync",
            event_subtype="success",
            summary=f"Synced {len(events)} events for {member_name}",
            payload={
                "member_name": member_name,
                "events_found": len(events),
                "events_added_to_dossier": min(len(events), 5),
                "shared_events_found": len(shared_lines),
            },
        )
    elif events and "error" in events[0]:
        log_event(
            event_type="calendar_sync",
            event_subtype="error",
            summary=f"Calendar sync failed for {member_name}: {events[0]['error']}",
            payload={
                "member_name": member_name,
                "error": events[0]["error"],
            },
        )

    return events


def fetch_past_events(
    credentials=None,
    calendar_id: str = "primary",
    days_back: int = 30,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Fetch past calendar events."""
    try:
        service = _get_calendar_service(credentials)
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days_back)).isoformat()
        time_max = now.isoformat()

        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for event in result.get("items", []):
            start = event.get("start", {})
            events.append({
                "summary": event.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": event.get("end", {}).get("dateTime", ""),
                "location": event.get("location", ""),
                "description": (event.get("description") or "")[:200],
                "attendees": _extract_attendees(event),
            })
        return events

    except Exception as e:
        from gossip.logger import log_event
        log_event(
            event_type="calendar_sync",
            event_subtype="error",
            summary=f"Calendar past fetch failed: {e}",
            payload={"calendar_id": calendar_id, "error": str(e)},
        )
        return [{"error": str(e)}]


def deep_sync_member_calendar(member_id: str, member_name: str) -> list[dict]:
    """One-time deep sync: pull 30 days past + 30 days future to bootstrap a dossier."""
    from gossip.logger import log_event

    token_data = get_oauth_token(member_id, "google")
    if not token_data:
        return []

    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )

    # Past events
    past = fetch_past_events(credentials=creds, days_back=30, max_results=50)
    # Future events
    future = fetch_upcoming_events(credentials=creds, days_ahead=30, max_results=30)

    lines = []

    # Analyze past events for patterns
    if past and "error" not in past[0]:
        location_counts: dict[str, int] = {}
        event_types: dict[str, int] = {}
        for ev in past:
            title = ev["summary"].lower()
            if ev.get("location"):
                loc = ev["location"].split(",")[0].strip()
                location_counts[loc] = location_counts.get(loc, 0) + 1
            # Simple categorization
            for keyword in ["dinner", "lunch", "coffee", "gym", "workout", "meeting", "call", "flight", "trip"]:
                if keyword in title:
                    event_types[keyword] = event_types.get(keyword, 0) + 1

        if event_types:
            lines.append("**What they've been up to (last 30 days):**")
            for etype, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {etype}: {count} times")

        top_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_locations:
            lines.append("\n**Frequent places:**")
            for loc, count in top_locations:
                lines.append(f"- {loc} ({count} visits)")

    # Upcoming events
    if future and "error" not in future[0]:
        upcoming = [ev for ev in future[:10]]
        if upcoming:
            lines.append("\n**Coming up:**")
            for ev in upcoming:
                line = f"- {ev['summary']}"
                if ev.get("location"):
                    line += f" @ {ev['location']}"
                if ev.get("start"):
                    line += f" ({ev['start'][:10]})"
                att_count = len(ev.get("attendees", []))
                if att_count > 1:
                    line += f" [{att_count} attendees]"
                lines.append(line)

    # Cross-reference attendees against known members (past + future)
    all_for_xref = (past if past and "error" not in past[0] else []) + \
                   (future if future and "error" not in future[0] else [])
    shared_lines = _cross_reference_attendees(all_for_xref, member_name)
    if shared_lines:
        lines.append("\n**Shared events with group members:**")
        lines.extend(shared_lines)

    if lines:
        summary = "\n".join(lines)
        append_dossier_from_source(
            member_name, "calendar", summary, subject="Calendar Overview (60 days)"
        )

    all_events = (past if past and "error" not in past[0] else []) + \
                 (future if future and "error" not in future[0] else [])

    log_event(
        event_type="calendar_sync",
        event_subtype="deep_sync",
        summary=f"Deep synced calendar for {member_name} ({len(all_events)} events)",
        payload={
            "member_name": member_name,
            "past_events": len(past) if past and "error" not in past[0] else 0,
            "future_events": len(future) if future and "error" not in future[0] else 0,
        },
    )

    return all_events


def format_events_for_context(events: list[dict]) -> str:
    """Format calendar events as readable text for the gossip context."""
    if not events or (events and "error" in events[0]):
        return "(no calendar data)"

    lines = []
    for ev in events:
        line = f"- {ev['summary']}"
        if ev.get("location"):
            line += f" at {ev['location']}"
        if ev.get("start"):
            line += f" ({ev['start'][:16]})"
        lines.append(line)

    return "\n".join(lines) if lines else "(no upcoming events)"

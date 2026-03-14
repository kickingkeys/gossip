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
            lines.append(line)

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

"""Gmail API connector.

Reads recent emails from members who granted Gmail OAuth access,
extracts gossip-worthy snippets, and feeds them into dossiers.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Any

from gossip.db import get_oauth_token
from gossip.dossiers import append_dossier_from_source


def _get_gmail_service(credentials):
    """Build a Gmail API service client."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials)


def fetch_recent_emails(
    credentials,
    max_results: int = 10,
    query: str = "newer_than:1d",
) -> list[dict[str, Any]]:
    """Fetch recent emails from a member's Gmail."""
    try:
        service = _get_gmail_service(credentials)

        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = []
        for msg_ref in result.get("messages", []):
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata",
                     metadataHeaders=["From", "To", "Subject", "Date"])
                .execute()
            )

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            snippet = msg.get("snippet", "")

            messages.append({
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": snippet[:300],
            })

        return messages

    except Exception as e:
        from gossip.logger import log_event

        log_event(
            event_type="gmail_sync",
            event_subtype="error",
            summary=f"Gmail fetch failed: {e}",
            payload={"error": str(e)},
        )
        return [{"error": str(e)}]


def sync_member_gmail(member_id: str, member_name: str) -> list[dict]:
    """Sync a member's recent emails into their dossier."""
    from gossip.logger import log_event

    token_data = get_oauth_token(member_id, "google")
    if not token_data:
        log_event(
            event_type="gmail_sync",
            event_subtype="skip",
            summary=f"No Google OAuth token for {member_name}",
            payload={"member_name": member_name, "member_id": member_id},
        )
        return []

    # Check if gmail scope was granted
    scopes = token_data.get("scopes", "")
    if "gmail" not in scopes:
        log_event(
            event_type="gmail_sync",
            event_subtype="skip",
            summary=f"No Gmail scope for {member_name}",
            payload={"member_name": member_name, "scopes": scopes},
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

    emails = fetch_recent_emails(creds, max_results=5, query="newer_than:1d")

    if emails and "error" not in emails[0]:
        lines = []
        for em in emails[:5]:
            sender = em["from"].split("<")[0].strip().strip('"')
            lines.append(f"- From {sender}: {em['subject']} — {em['snippet'][:100]}")

        if lines:
            summary = "\n".join(lines)
            append_dossier_from_source(
                member_name, "email", summary, subject="Recent Emails"
            )

        log_event(
            event_type="gmail_sync",
            event_subtype="success",
            summary=f"Synced {len(emails)} emails for {member_name}",
            payload={
                "member_name": member_name,
                "emails_found": len(emails),
            },
        )
    elif emails and "error" in emails[0]:
        log_event(
            event_type="gmail_sync",
            event_subtype="error",
            summary=f"Gmail sync failed for {member_name}: {emails[0]['error']}",
            payload={"member_name": member_name, "error": emails[0]["error"]},
        )

    return emails

"""Member identity resolution — map platform users to member profiles."""

from __future__ import annotations

from gossip.db import (
    get_member_by_discord_id,
    get_member_by_discord_username,
    get_member_by_telegram_id,
    update_member,
)


def resolve_member(
    platform: str,
    user_id: str | None = None,
    username: str | None = None,
) -> dict | None:
    """Resolve a platform user to a member profile.

    Tries ID first (exact match), then username (fuzzy).
    If found by username but missing platform ID, backfills it.
    """
    if platform == "discord":
        if user_id:
            member = get_member_by_discord_id(user_id)
            if member:
                return member

        if username:
            member = get_member_by_discord_username(username)
            if member:
                # Backfill discord_id if we now know it
                if user_id and not member.get("discord_id"):
                    update_member(member["id"], discord_id=user_id)
                return member

    elif platform == "telegram":
        if user_id:
            member = get_member_by_telegram_id(user_id)
            if member:
                return member

    return None

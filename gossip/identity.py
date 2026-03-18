"""Member identity resolution — 4-layer cascade.

Maps platform users to member profiles with case-insensitive matching
and nickname support. Always backfills platform IDs when found by a later layer.
"""

from __future__ import annotations

from gossip.db import (
    get_member_by_discord_id,
    get_member_by_discord_username_ci,
    get_member_by_display_name_ci,
    get_member_by_telegram_id,
    get_members_with_nicknames,
    update_member,
)


def resolve_member(
    platform: str,
    user_id: str | None = None,
    username: str | None = None,
    display_name: str | None = None,
) -> dict | None:
    """4-layer identity cascade. Always backfills platform ID when found.

    Layers (most specific wins):
      1. Platform ID exact match (discord_id / telegram_id)
      2. Platform username case-insensitive match
      3. Nicknames scan (comma-separated, case-insensitive)
      4. Display name case-insensitive match
    """
    if platform == "discord":
        # Layer 1: discord_id (exact)
        if user_id:
            member = get_member_by_discord_id(user_id)
            if member:
                return member

        # Layer 2: discord_username (case-insensitive)
        if username:
            member = get_member_by_discord_username_ci(username)
            if member:
                _backfill_discord_id(member, user_id)
                return member

        # Layer 3: nicknames (case-insensitive scan)
        search_name = username or display_name
        if search_name:
            member = _match_nickname(search_name)
            if member:
                _backfill_discord_id(member, user_id)
                return member

        # Layer 4: display_name (case-insensitive)
        name_to_check = display_name or username
        if name_to_check:
            member = get_member_by_display_name_ci(name_to_check)
            if member:
                _backfill_discord_id(member, user_id)
                return member

    elif platform == "telegram":
        # Layer 1: telegram_id (exact)
        if user_id:
            member = get_member_by_telegram_id(user_id)
            if member:
                return member

        # Layer 3: nicknames
        if username:
            member = _match_nickname(username)
            if member:
                if user_id and not member.get("telegram_id"):
                    update_member(member["id"], telegram_id=user_id)
                return member

        # Layer 4: display_name
        name_to_check = display_name or username
        if name_to_check:
            member = get_member_by_display_name_ci(name_to_check)
            if member:
                if user_id and not member.get("telegram_id"):
                    update_member(member["id"], telegram_id=user_id)
                return member

    return None


def _backfill_discord_id(member: dict, user_id: str | None) -> None:
    """Backfill discord_id if we now know it."""
    if user_id and not member.get("discord_id"):
        update_member(member["id"], discord_id=user_id)


def _match_nickname(name: str) -> dict | None:
    """Scan all members' nicknames for a case-insensitive match."""
    members = get_members_with_nicknames()
    name_lower = name.lower()
    for m in members:
        nicks = [n.strip().lower() for n in m["nicknames"].split(",")]
        if name_lower in nicks:
            return m
    return None

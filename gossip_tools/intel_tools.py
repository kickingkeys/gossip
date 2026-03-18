"""Hermes tools: gossip_pick_dm_target, gossip_log_dm."""

import json
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

# ── Pick DM Target ────────────────────────────────────────────────────

PICK_SCHEMA = {
    "name": "gossip_pick_dm_target",
    "description": (
        "Score group members by dossier thinness and days since last DM. "
        "Returns who to DM next, their discord ID, knowledge gaps, and a suggested angle."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_pick(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group, get_last_dm
    from gossip.dossiers import read_dossier
    from gossip.logger import log_event, get_current_session_id

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_by_group(group["id"])
    if not members:
        return json.dumps({"error": "no members in group"})

    now = datetime.now(timezone.utc)
    scored = []

    for m in members:
        if m.get("is_paused"):
            continue

        # Score dossier thinness
        dossier = read_dossier(m["display_name"])
        dossier_len = len(dossier) if "(no info yet)" not in dossier else 0
        thinness_score = max(0, 500 - dossier_len) / 500  # 1.0 = empty, 0.0 = 500+ chars

        # Score days since last DM
        last_dm = get_last_dm(m["id"])
        if last_dm is None:
            days_since_dm = 999
            dm_score = 1.0
        else:
            last_dm_time = datetime.fromisoformat(last_dm["created_at"])
            if last_dm_time.tzinfo is None:
                last_dm_time = last_dm_time.replace(tzinfo=timezone.utc)
            days_since_dm = (now - last_dm_time).total_seconds() / 86400
            dm_score = min(1.0, days_since_dm / 7)  # Max score at 7+ days

        total_score = (thinness_score * 0.4) + (dm_score * 0.6)

        # Identify knowledge gaps
        gaps = []
        if dossier_len < 100:
            gaps.append("barely know them")
        if "calendar" not in dossier.lower() and "schedule" not in dossier.lower():
            gaps.append("no schedule info")
        if "hobby" not in dossier.lower() and "interest" not in dossier.lower():
            gaps.append("no hobbies/interests")

        scored.append({
            "name": m["display_name"],
            "discord_id": m.get("discord_id"),
            "discord_dm_channel_id": m.get("discord_dm_channel_id"),
            "score": round(total_score, 3),
            "dossier_chars": dossier_len,
            "days_since_last_dm": round(days_since_dm, 1),
            "knowledge_gaps": gaps,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    if not scored:
        return json.dumps({"error": "no eligible members to DM"})

    target = scored[0]

    # Check if they've connected Google
    from gossip.db import get_oauth_token
    google_token = get_oauth_token(
        next(m["id"] for m in members if m["display_name"] == target["name"]),
        "google",
    )
    needs_onboarding = google_token is None

    # Suggest an angle based on gaps
    if needs_onboarding and target["days_since_last_dm"] >= 999:
        angle = "introduce yourself and share the onboarding link — they haven't connected Google yet"
    elif "barely know them" in target["knowledge_gaps"]:
        angle = "casual check-in — you barely know them, ask what they've been up to"
    elif "no schedule info" in target["knowledge_gaps"]:
        angle = "ask about their week — what's coming up, anything fun planned"
    elif "no hobbies/interests" in target["knowledge_gaps"]:
        angle = "find out what they're into — hobbies, shows, music, whatever"
    elif target["days_since_last_dm"] > 7:
        angle = "been a while since you talked — just checking in, drop something you noticed"
    else:
        angle = "follow up on something from the group chat — keep it natural"

    target["suggested_angle"] = angle
    target["needs_onboarding"] = needs_onboarding

    # Include onboarding URL if needed
    if needs_onboarding:
        try:
            from gossip.discord_commands import _get_public_url
            base_url = _get_public_url()
            target["onboarding_url"] = f"{base_url}/join/{group['invite_token']}"
        except Exception:
            target["onboarding_url"] = f"http://localhost:3000/join/{group['invite_token']}"

    log_event(
        event_type="intel_pick",
        summary=f"Picked DM target: {target['name']} (score: {target['score']})",
        payload={"target": target["name"], "score": target["score"], "gaps": target["knowledge_gaps"]},
        session_id=get_current_session_id(),
    )

    return json.dumps({"target": target, "all_scores": scored[:5]})


# ── Log DM ────────────────────────────────────────────────────────────

LOG_SCHEMA = {
    "name": "gossip_log_dm",
    "description": "Record that a DM was sent to a member.",
    "parameters": {
        "type": "object",
        "properties": {
            "member_name": {
                "type": "string",
                "description": "The member's display name.",
            },
            "message_text": {
                "type": "string",
                "description": "The message that was sent.",
            },
        },
        "required": ["member_name", "message_text"],
    },
}


def _handle_log_dm(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group, log_dm
    from gossip.logger import log_event, get_current_session_id

    name = args.get("member_name", "")
    text = args.get("message_text", "")

    if not name or not text:
        return json.dumps({"error": "member_name and message_text are required"})

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_by_group(group["id"])
    member = None
    for m in members:
        if m["display_name"].lower() == name.lower():
            member = m
            break

    if not member:
        return json.dumps({"error": f"member '{name}' not found"})

    dm_id = log_dm(member["id"], text, direction="outbound")

    log_event(
        event_type="dm_sent",
        summary=f"Logged outbound DM to {name}",
        payload={"member": name, "dm_id": dm_id, "text_length": len(text)},
        session_id=get_current_session_id(),
    )

    return json.dumps({"success": True, "dm_id": dm_id, "member": name})


# ── Discover Members ──────────────────────────────────────────────────

DISCOVER_SCHEMA = {
    "name": "gossip_discover_members",
    "description": (
        "Scan the Discord server for members not yet in the gossip group. "
        "Returns their Discord IDs and display names so you can DM them the onboarding link."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_discover(args, **kwargs):
    import os
    import requests
    from gossip.db import get_default_group, get_members_by_group
    from gossip.logger import log_event, get_current_session_id

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    # Get Discord bot token
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        # Try reading from .env
        try:
            from dotenv import dotenv_values
            env_path = Path(__file__).resolve().parent.parent / "config" / ".env"
            env = dotenv_values(env_path)
            token = env.get("DISCORD_BOT_TOKEN")
        except Exception:
            pass

    if not token:
        return json.dumps({"error": "DISCORD_BOT_TOKEN not found"})

    # Get bot's guilds
    headers = {"Authorization": f"Bot {token}"}
    try:
        guilds_resp = requests.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers=headers,
            timeout=10,
        )
        guilds_resp.raise_for_status()
        guilds = guilds_resp.json()
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch guilds: {e}"})

    if not guilds:
        return json.dumps({"error": "Bot is not in any guilds"})

    # Get existing gossip members
    existing_members = get_members_by_group(group["id"])
    existing_discord_ids = {m.get("discord_id") for m in existing_members if m.get("discord_id")}
    existing_usernames = {m.get("discord_username", "").lower() for m in existing_members if m.get("discord_username")}

    undiscovered = []

    for guild in guilds:
        try:
            # Fetch guild members (up to 1000)
            members_resp = requests.get(
                f"https://discord.com/api/v10/guilds/{guild['id']}/members?limit=1000",
                headers=headers,
                timeout=15,
            )
            members_resp.raise_for_status()
            guild_members = members_resp.json()
        except Exception as e:
            continue

        for gm in guild_members:
            user = gm.get("user", {})
            user_id = user.get("id", "")
            username = user.get("username", "")
            display_name = gm.get("nick") or user.get("global_name") or username

            # Skip bots
            if user.get("bot"):
                continue

            # Skip if already in gossip group
            if user_id in existing_discord_ids:
                continue
            if username.lower() in existing_usernames:
                continue

            undiscovered.append({
                "discord_id": user_id,
                "username": username,
                "display_name": display_name,
                "guild": guild.get("name", ""),
            })

    # Build onboarding link
    try:
        from gossip.discord_commands import _get_public_url
        base_url = _get_public_url()
        onboarding_url = f"{base_url}/join/{group['invite_token']}"
    except Exception:
        onboarding_url = f"http://localhost:3000/join/{group['invite_token']}"

    log_event(
        event_type="member_discover",
        summary=f"Found {len(undiscovered)} undiscovered server members",
        payload={"undiscovered_count": len(undiscovered), "guilds_checked": len(guilds)},
        session_id=get_current_session_id(),
    )

    return json.dumps({
        "undiscovered": undiscovered,
        "onboarding_url": onboarding_url,
        "total_found": len(undiscovered),
    })


def _check():
    return True


registry.register(
    name="gossip_pick_dm_target",
    toolset="gossip",
    schema=PICK_SCHEMA,
    handler=_handle_pick,
    check_fn=_check,
    is_async=False,
)

registry.register(
    name="gossip_log_dm",
    toolset="gossip",
    schema=LOG_SCHEMA,
    handler=_handle_log_dm,
    check_fn=_check,
    is_async=False,
)

registry.register(
    name="gossip_discover_members",
    toolset="gossip",
    schema=DISCOVER_SCHEMA,
    handler=_handle_discover,
    check_fn=_check,
    is_async=False,
)

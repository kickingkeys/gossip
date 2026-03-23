"""JSON API endpoints for OpenClaw gossip tools.

The OpenClaw TypeScript plugin calls these endpoints via HTTP.
All endpoints return JSON. POST endpoints accept JSON bodies.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gossip.config import get_config
from gossip.db import (
    add_gossip,
    get_default_group,
    get_dm_history,
    get_last_dm,
    get_members_by_group,
    get_oauth_token,
    get_unused_manual_input,
    log_dm,
    log_donny_memory,
    can_dm_undiscovered,
    upsert_member_summary,
)
from gossip.dossiers import append_dossier_from_source, read_dossier
from gossip.engine import gossip_context, update_group_dynamics, get_group_dynamics
from gossip.identity import resolve_member
from gossip.proactive import should_fire_idle_gossip

router = APIRouter(prefix="/api/gossip")


def _get_group_id() -> str | None:
    group = get_default_group()
    return group["id"] if group else None


@router.post("/context")
async def get_context(request: Request):
    """Get assembled context for the agent."""
    body = await request.json()
    context_type = body.get("type", "group")
    member = body.get("member")

    context = gossip_context(context_type, member)
    return JSONResponse({"context": context})


@router.post("/idle-check")
async def idle_check(request: Request):
    """Code-level pre-check for idle gossip. Costs $0 when not firing."""
    result = should_fire_idle_gossip()
    return JSONResponse(result)


@router.post("/generate")
async def generate(request: Request):
    """Log a gossip message that was posted."""
    body = await request.json()
    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"error": "no group"}, status_code=400)

    gossip_id = add_gossip(
        group_id=group_id,
        gossip_text=body["gossip_text"],
        context_summary=body.get("context_summary"),
    )

    return JSONResponse({"id": gossip_id, "posted_at": "ok"})


@router.post("/dossier/read")
async def read_dossier_api(request: Request):
    """Read a member's dossier."""
    body = await request.json()
    member_name = body["member_name"]
    dossier = read_dossier(member_name)
    return JSONResponse({"member_name": member_name, "dossier": dossier})


@router.post("/dossier/update")
async def update_dossier_api(request: Request):
    """Add an entry to a member's dossier."""
    body = await request.json()
    append_dossier_from_source(
        member_name=body["member_name"],
        source=body.get("source", "agent"),
        content=body["entry"],
    )
    return JSONResponse({"success": True})


@router.post("/pick-dm-target")
async def pick_dm_target(request: Request):
    """Pick a member to check in with via DM.

    Scoring: (hours since last DM) * 0.5 + (dossier thinness) * 0.3 + (activity bonus) * 0.2
    """
    from datetime import datetime, timezone
    from gossip.proactive import should_dm_checkin

    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"error": "no group"}, status_code=400)

    members = get_members_by_group(group_id)
    if not members:
        return JSONResponse({"error": "no members"}, status_code=400)

    now = datetime.now(timezone.utc)
    best = None
    best_score = -1

    for m in members:
        if m.get("is_paused"):
            continue

        # Check if we should DM
        check = should_dm_checkin(m["id"])
        if not check["fire"]:
            continue

        # Score: hours since last DM
        last = get_last_dm(m["id"])
        if last:
            last_ts = datetime.fromisoformat(last["created_at"])
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            hours_since_dm = (now - last_ts).total_seconds() / 3600
        else:
            hours_since_dm = 999

        # Score: dossier thinness
        dossier = read_dossier(m["display_name"])
        dossier_chars = len(dossier) if "(no info yet)" not in dossier else 0
        thinness = max(0, 500 - dossier_chars) / 500  # 1.0 = empty, 0.0 = 500+ chars

        score = hours_since_dm * 0.5 + thinness * 100 * 0.3

        if score > best_score:
            best_score = score
            # Build a suggested angle
            angles = []
            if dossier_chars < 100:
                angles.append("you don't know much about them — ask what they've been up to")
            if hours_since_dm > 48:
                angles.append("haven't talked in a while — casual check-in")

            # Check for recent manual input
            inputs = get_unused_manual_input(m["id"])
            if inputs:
                angles.append(f"they shared something: {inputs[0]['content'][:80]}")

            # Check if Google connected
            google = get_oauth_token(m["id"], "google")
            needs_onboarding = not google
            if needs_onboarding:
                angles.append("Google not connected — casually drop the setup link in conversation")

            # Build onboarding URL
            onboarding_url = None
            if needs_onboarding:
                import os
                group = get_default_group()
                try:
                    from dotenv import dotenv_values
                    from gossip.config import _project_root
                    env = dotenv_values(_project_root() / "config" / ".env")
                    base_url = (env.get("PORTAL_PUBLIC_URL") or "").rstrip("/")
                except Exception:
                    base_url = ""
                if not base_url:
                    base_url = os.environ.get("PORTAL_PUBLIC_URL", "http://localhost:3000").rstrip("/")
                onboarding_url = f"{base_url}/join/{group['invite_token']}"

            best = {
                "name": m["display_name"],
                "discord_id": m.get("discord_id"),
                "discord_dm_channel_id": m.get("discord_dm_channel_id"),
                "score": round(score, 1),
                "dossier_chars": dossier_chars,
                "hours_since_dm": round(hours_since_dm, 1),
                "suggested_angle": " | ".join(angles) if angles else "just say hey",
                "needs_onboarding": needs_onboarding,
                "onboarding_url": onboarding_url,
            }

    if not best:
        return JSONResponse({"error": "no eligible members"}, status_code=400)

    return JSONResponse(best)


@router.post("/log-dm")
async def log_dm_api(request: Request):
    """Record a DM sent or received."""
    body = await request.json()

    # Find member by name
    group_id = _get_group_id()
    members = get_members_by_group(group_id) if group_id else []
    member_record = None
    for m in members:
        if m["display_name"].lower() == body["member_name"].lower():
            member_record = m
            break

    if not member_record:
        return JSONResponse({"error": f"member '{body['member_name']}' not found"}, status_code=400)

    log_dm(
        member_id=member_record["id"],
        message_text=body["message_text"],
        direction=body.get("direction", "outbound"),
    )
    return JSONResponse({"success": True})


@router.post("/log-memory")
async def log_memory(request: Request):
    """Log something donny said for memory continuity."""
    body = await request.json()
    log_donny_memory(
        channel_type=body["channel_type"],
        target=body.get("target"),
        content=body["content"],
    )
    return JSONResponse({"success": True})


@router.post("/discover-members")
async def discover_members(request: Request):
    """Fetch Discord guild members, compare against DB, return undiscovered ones."""
    import os
    import requests as http_requests

    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"error": "no group"}, status_code=400)

    group = get_default_group()
    members = get_members_by_group(group_id)

    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        return JSONResponse({"error": "DISCORD_BOT_TOKEN not set"}, status_code=500)

    headers = {"Authorization": f"Bot {bot_token}"}

    # Fetch all guilds and their members
    try:
        guilds = http_requests.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers=headers, timeout=10,
        ).json()
    except Exception as e:
        return JSONResponse({"error": f"Discord API error: {e}"}, status_code=500)

    # Build lookup of existing member discord IDs and usernames
    existing_ids = {m.get("discord_id") for m in members if m.get("discord_id")}
    existing_usernames = {(m.get("discord_username") or "").lower() for m in members if m.get("discord_username")}

    undiscovered = []
    for guild_info in guilds:
        try:
            guild_members = http_requests.get(
                f"https://discord.com/api/v10/guilds/{guild_info['id']}/members?limit=1000",
                headers=headers, timeout=15,
            ).json()
            if not isinstance(guild_members, list):
                continue
        except Exception:
            continue

        for gm in guild_members:
            user = gm.get("user", {})
            if user.get("bot"):
                continue

            uid = user.get("id", "")
            username = user.get("username", "")
            display_name = gm.get("nick") or user.get("global_name") or username

            if uid in existing_ids or username.lower() in existing_usernames:
                continue

            can_dm = can_dm_undiscovered("discord", uid)
            undiscovered.append({
                "user_id": uid,
                "username": username,
                "display_name": display_name,
                "can_dm": can_dm,
            })

    # Build onboarding URL
    try:
        from dotenv import dotenv_values
        from gossip.config import _project_root
        env = dotenv_values(_project_root() / "config" / ".env")
        base_url = (env.get("PORTAL_PUBLIC_URL") or "").rstrip("/")
    except Exception:
        base_url = ""
    if not base_url:
        base_url = os.environ.get("PORTAL_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    onboarding_url = f"{base_url}/join/{group['invite_token']}"

    return JSONResponse({
        "undiscovered": undiscovered,
        "onboarding_url": onboarding_url,
        "total_found": len(undiscovered),
    })


@router.post("/sync-sources")
async def sync_sources(request: Request):
    """Sync calendar + email for all connected members."""
    from gossip.sources.calendar import sync_member_calendar
    from gossip.sources.gmail import sync_member_gmail

    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"synced": 0, "failed": 0, "members": []})

    members = get_members_by_group(group_id)
    results = {"synced": 0, "failed": 0, "members": []}

    for m in members:
        if m.get("is_paused"):
            continue

        token = get_oauth_token(m["id"], "google")
        if not token:
            continue

        try:
            sync_member_calendar(m["id"], m["display_name"])
            sync_member_gmail(m["id"], m["display_name"])
            # Compact dossier after sync to prevent bloat
            from gossip.compactor import compact_dossier
            compact_dossier(m["display_name"])
            results["synced"] += 1
            results["members"].append({"name": m["display_name"], "status": "ok"})
        except Exception as e:
            results["failed"] += 1
            results["members"].append({"name": m["display_name"], "status": str(e)})

    return JSONResponse(results)


@router.post("/synthesizer/run")
async def synthesizer_run(request: Request):
    """Build synthesizer input and prompt for a member."""
    from gossip.synthesizer import build_synthesizer_input, get_synthesizer_prompt

    body = await request.json()
    raw_input = build_synthesizer_input(body["member_id"], body["member_name"])
    prompt = get_synthesizer_prompt(body["member_name"], raw_input)

    return JSONResponse({"input": raw_input, "prompt": prompt})


@router.post("/synthesizer/save")
async def synthesizer_save(request: Request):
    """Save a synthesizer-generated summary."""
    body = await request.json()
    upsert_member_summary(body["member_id"], body["summary_json"])
    return JSONResponse({"success": True})


@router.post("/ammunition")
async def get_ammunition(request: Request):
    """Get sabotage ammunition — contradictions, overlaps, and opportunities."""
    from gossip.sabotage import find_gossip_ammunition

    group_id = _get_group_id()
    ammo = find_gossip_ammunition(group_id)
    return JSONResponse(ammo)


@router.post("/update-dynamics")
async def update_dynamics_api(request: Request):
    """Append an observation to group dynamics."""
    body = await request.json()
    from datetime import datetime, timezone

    current = get_group_dynamics()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n\n## Observation ({timestamp})\n{body['observation']}"

    if current == "(no group dynamics summary yet)":
        update_group_dynamics(f"# Group Dynamics{new_entry}")
    else:
        update_group_dynamics(current + new_entry)

    return JSONResponse({"success": True})


@router.get("/members")
async def list_members(request: Request):
    """List all members in the default group."""
    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"members": []})

    members = get_members_by_group(group_id)
    # Strip sensitive fields
    safe_members = []
    for m in members:
        safe_members.append({
            "id": m["id"],
            "display_name": m["display_name"],
            "discord_id": m.get("discord_id"),
            "discord_username": m.get("discord_username"),
            "discord_dm_channel_id": m.get("discord_dm_channel_id"),
            "nicknames": m.get("nicknames"),
            "is_paused": m.get("is_paused", 0),
        })

    return JSONResponse({"members": safe_members})


@router.post("/resolve-member")
async def resolve_member_api(request: Request):
    """Look up a member by platform ID, username, or display name."""
    body = await request.json()
    member = resolve_member(
        platform=body.get("platform", "discord"),
        user_id=body.get("user_id"),
        username=body.get("username"),
        display_name=body.get("display_name"),
    )

    if member:
        return JSONResponse({"member": {
            "id": member["id"],
            "display_name": member["display_name"],
            "discord_id": member.get("discord_id"),
            "discord_username": member.get("discord_username"),
            "nicknames": member.get("nicknames"),
        }})
    return JSONResponse({"member": None})

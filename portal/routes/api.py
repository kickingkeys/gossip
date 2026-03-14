"""JSON API endpoints for the portal."""

from fastapi import APIRouter, Body

from gossip.db import (
    add_manual_input,
    get_default_group,
    get_member_by_portal_token,
    get_members_by_group,
)
from gossip.dossiers import read_dossier

router = APIRouter()


@router.get("/members")
async def list_members():
    group = get_default_group()
    if not group:
        return {"error": "no group configured", "members": []}

    members = get_members_by_group(group["id"])
    return {
        "group": group["name"],
        "members": [
            {
                "name": m["display_name"],
                "discord": m.get("discord_username"),
                "telegram": m.get("telegram_username"),
                "paused": bool(m.get("is_paused")),
            }
            for m in members
        ],
    }


@router.get("/member/{portal_token}")
async def get_member(portal_token: str):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return {"error": "not found"}

    dossier = read_dossier(member["display_name"])
    return {
        "name": member["display_name"],
        "discord": member.get("discord_username"),
        "telegram": member.get("telegram_username"),
        "paused": bool(member.get("is_paused")),
        "dossier": dossier,
    }


@router.post("/member/{portal_token}/input")
async def submit_input(portal_token: str, content: str = Body(..., embed=True)):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return {"error": "not found"}

    if not content.strip():
        return {"error": "content is empty"}

    input_id = add_manual_input(member["id"], content.strip(), source="api")
    return {"success": True, "input_id": input_id}

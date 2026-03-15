"""Invite landing page — GET /join/{token}."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gossip.config import get_config
from gossip.db import get_group_by_invite
from portal.deps import get_templates

router = APIRouter()


@router.get("/join/{token}", response_class=HTMLResponse)
async def invite_page(request: Request, token: str):
    templates = get_templates()
    group = get_group_by_invite(token)

    if not group:
        return templates.TemplateResponse("invite.html", {
            "request": request,
            "error": "Invalid invite link.",
            "group": None,
            "bot_name": "",
        })

    cfg = get_config()
    return templates.TemplateResponse("invite.html", {
        "request": request,
        "error": None,
        "group": group,
        "bot_name": cfg.bot.name,
        "invite_token": token,
    })

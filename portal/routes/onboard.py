"""Onboarding flow — POST /onboard, GET /connect/{portal_token}."""

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gossip.config import get_config
from gossip.db import create_member, get_group_by_invite, get_member_by_portal_token
from portal.deps import get_templates

router = APIRouter()


@router.post("/onboard", response_class=HTMLResponse)
async def onboard_member(
    request: Request,
    invite_token: str = Form(...),
    display_name: str = Form(...),
    platform: str = Form(...),
    username: str = Form(""),
):
    templates = get_templates()
    group = get_group_by_invite(invite_token)

    if not group:
        return templates.TemplateResponse("invite.html", {
            "request": request,
            "error": "Invalid invite link.",
            "group": None,
            "bot_name": "",
        })

    # Create the member
    discord_username = username if platform in ("discord", "both") else None
    telegram_username = username if platform in ("telegram", "both") else None

    member = create_member(
        group_id=group["id"],
        display_name=display_name,
        discord_username=discord_username,
        telegram_username=telegram_username,
    )

    # Redirect to the connect sources page
    return RedirectResponse(
        url=f"/connect/{member['portal_token']}",
        status_code=303,
    )


@router.get("/connect/{portal_token}", response_class=HTMLResponse)
async def connect_sources_page(request: Request, portal_token: str):
    templates = get_templates()
    member = get_member_by_portal_token(portal_token)

    if not member:
        return templates.TemplateResponse("invite.html", {
            "request": request,
            "error": "Invalid profile link.",
            "group": None,
            "bot_name": "",
        })

    cfg = get_config()
    bot_email = os.getenv("GOSSIP_EMAIL", "gossipbot@gmail.com")

    google_oauth_enabled = bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID"))
    instagram_enabled = bool(os.getenv("INSTAGRAM_APP_ID"))
    twitter_enabled = bool(os.getenv("TWITTER_CLIENT_ID"))

    return templates.TemplateResponse("connect_sources.html", {
        "request": request,
        "member": member,
        "bot_name": cfg.bot.name,
        "bot_email": bot_email,
        "google_oauth_enabled": google_oauth_enabled,
        "instagram_enabled": instagram_enabled,
        "twitter_enabled": twitter_enabled,
    })

"""Member profile page — GET/POST /me/{portal_token}."""

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gossip.config import get_config
from gossip.db import (
    add_manual_input,
    delete_member,
    delete_oauth_token,
    get_member_by_portal_token,
    get_oauth_token,
    get_unused_manual_input,
    update_member,
)
from gossip.dossiers import (
    delete_dossier_entry,
    list_dossier_entries,
    read_dossier,
    write_dossier,
)
from portal.deps import get_templates

router = APIRouter()


@router.get("/me/{portal_token}", response_class=HTMLResponse)
async def profile_page(request: Request, portal_token: str):
    templates = get_templates()
    member = get_member_by_portal_token(portal_token)

    if not member:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "Invalid profile link.",
            "member": None,
        })

    cfg = get_config()
    dossier = read_dossier(member["display_name"])
    entries = list_dossier_entries(member["display_name"])
    manual_inputs = get_unused_manual_input(member["id"])

    # Check connected sources
    google_token = get_oauth_token(member["id"], "google")

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "error": None,
        "member": member,
        "bot_name": cfg.bot.name,
        "bot_email": os.getenv("GOSSIP_EMAIL", "gossipbot@gmail.com"),
        "dossier": dossier,
        "dossier_entries": entries,
        "manual_inputs": manual_inputs,
        "google_connected": google_token is not None,
    })


@router.post("/me/{portal_token}/input", response_class=HTMLResponse)
async def add_input(portal_token: str, content: str = Form(...)):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    if content.strip():
        add_manual_input(member["id"], content.strip(), source="portal")

    return RedirectResponse(url=f"/me/{portal_token}", status_code=303)


@router.post("/me/{portal_token}/delete-entry/{entry_index}")
async def remove_dossier_entry(portal_token: str, entry_index: int):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    delete_dossier_entry(member["display_name"], entry_index)
    return RedirectResponse(url=f"/me/{portal_token}", status_code=303)


@router.post("/me/{portal_token}/pause")
async def toggle_pause(portal_token: str):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    new_state = 0 if member.get("is_paused") else 1
    update_member(member["id"], is_paused=new_state)
    return RedirectResponse(url=f"/me/{portal_token}", status_code=303)


@router.post("/me/{portal_token}/disconnect/{provider}")
async def disconnect_source(portal_token: str, provider: str):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    delete_oauth_token(member["id"], provider)
    return RedirectResponse(url=f"/me/{portal_token}", status_code=303)


@router.post("/me/{portal_token}/delete-all")
async def delete_all_data(portal_token: str):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    # Clear dossier
    write_dossier(member["display_name"], f"# {member['display_name']}\n\n(data deleted)\n")
    # Delete member from DB (cascades to tokens, manual input)
    delete_member(member["id"])
    return HTMLResponse("<h2>All your data has been deleted.</h2><p>You can close this page.</p>")

"""Map view showing member locations."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gossip.db import get_group_by_invite
from portal.app import get_templates

router = APIRouter()


@router.get("/map/{invite_token}", response_class=HTMLResponse)
async def map_page(request: Request, invite_token: str):
    group = get_group_by_invite(invite_token)
    if not group:
        return HTMLResponse("<h1>Group not found</h1>", status_code=404)

    templates = get_templates()
    return templates.TemplateResponse("map.html", {
        "request": request,
        "group_name": group["name"],
    })

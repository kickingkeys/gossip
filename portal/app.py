"""FastAPI application for the Gossip onboarding portal."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from gossip.config import load_config
from gossip.db import init_db
from portal.routes import invite, onboard, profile, api, oauth_google, map_view

_portal_dir = Path(__file__).parent

app = FastAPI(title="Gossip Portal", docs_url=None, redoc_url=None)


@app.get("/")
async def root():
    return {
        "name": "Gossip Portal",
        "status": "running",
        "usage": "Use /join/{invite_token} to join a group",
    }


# Mount static files and templates
app.mount("/static", StaticFiles(directory=_portal_dir / "static"), name="static")
templates = Jinja2Templates(directory=_portal_dir / "templates")

# Include route modules
app.include_router(invite.router)
app.include_router(onboard.router)
app.include_router(profile.router)
app.include_router(api.router, prefix="/api")
app.include_router(oauth_google.router, prefix="/auth/google")
app.include_router(map_view.router)


@app.on_event("startup")
async def startup():
    load_config()
    init_db()


def get_templates() -> Jinja2Templates:
    return templates


def run():
    """Run the portal server."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "portal.app:app",
        host=cfg.portal.host,
        port=cfg.portal.port,
        reload=os.getenv("GOSSIP_DEV") == "1",
    )


if __name__ == "__main__":
    run()

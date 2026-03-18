"""Google OAuth flow for per-member Calendar + Gmail access."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from gossip.db import get_member_by_portal_token, upsert_oauth_token

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _get_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI, always re-reading .env for the tunnel URL.

    The tunnel URL changes on every restart and is written to .env AFTER
    the portal process starts, so we must read the file directly rather
    than trusting the process environment.
    """
    try:
        from dotenv import dotenv_values
        from gossip.config import _project_root
        env = dotenv_values(_project_root() / "config" / ".env")
        public_url = env.get("PORTAL_PUBLIC_URL", "").rstrip("/")
        if public_url:
            return f"{public_url}/auth/google/callback"
    except Exception:
        pass
    return str(request.url_for("google_callback"))


def _get_flow(redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    scopes = list(SCOPES)
    if os.getenv("GOOGLE_GMAIL_ENABLED", "").lower() in ("true", "1", "yes"):
        scopes.append("https://www.googleapis.com/auth/gmail.readonly")

    f = Flow.from_client_config(client_config, scopes=scopes, redirect_uri=redirect_uri)
    # Disable PKCE — we're a confidential client (have client_secret).
    # PKCE generates a code_verifier during authorization that must be present
    # during token exchange, but our callback creates a new Flow object so the
    # verifier is lost. Confidential clients don't need PKCE.
    f.autogenerate_code_verifier = False
    f.code_verifier = None
    return f


@router.get("/connect/{portal_token}")
async def start_google_oauth(request: Request, portal_token: str):
    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    redirect_uri = _get_redirect_uri(request)
    flow = _get_flow(redirect_uri)
    if not flow:
        return RedirectResponse(url=f"/me/{portal_token}?error=google_not_configured", status_code=303)

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=portal_token,
    )

    return RedirectResponse(url=auth_url)


@router.get("/callback", name="google_callback")
async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    portal_token = state

    if error:
        return RedirectResponse(url=f"/me/{portal_token}?error={error}", status_code=303)

    member = get_member_by_portal_token(portal_token)
    if not member:
        return RedirectResponse(url="/", status_code=303)

    redirect_uri = _get_redirect_uri(request)
    flow = _get_flow(redirect_uri)
    if not flow:
        return RedirectResponse(url=f"/me/{portal_token}?error=google_not_configured", status_code=303)

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        print(f"[OAuth] fetch_token FAILED: {e}", flush=True)
        print(f"[OAuth] redirect_uri used: {redirect_uri}", flush=True)
        return RedirectResponse(url=f"/me/{portal_token}?error=token_exchange_failed", status_code=303)

    credentials = flow.credentials

    # Store tokens
    upsert_oauth_token(
        member_id=member["id"],
        provider="google",
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        expires_at=credentials.expiry.isoformat() if credentials.expiry else None,
        scopes=",".join(credentials.scopes) if credentials.scopes else None,
    )

    # Trigger deep sync in background to bootstrap dossier
    import threading

    def _deep_sync():
        try:
            from gossip.sources.calendar import deep_sync_member_calendar
            from gossip.sources.gmail import deep_sync_member_gmail
            deep_sync_member_calendar(member["id"], member["display_name"])
            deep_sync_member_gmail(member["id"], member["display_name"])
        except Exception as e:
            print(f"[OAuth] Deep sync failed for {member['display_name']}: {e}", flush=True)

    threading.Thread(target=_deep_sync, daemon=True).start()

    return RedirectResponse(url=f"/me/{portal_token}?success=google", status_code=303)

"""Dashboard API endpoints for the Donny monitoring dashboard."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from gossip.config import get_config
from gossip.db import (
    get_default_group,
    get_dm_history,
    get_donny_memory,
    get_last_dm,
    get_members_by_group,
    get_member_summary,
    get_oauth_token,
    get_events,
)
from gossip.dossiers import read_dossier, list_dossier_entries

router = APIRouter()

_project_root = Path(__file__).resolve().parent.parent.parent


def _get_group_id() -> str | None:
    group = get_default_group()
    return group["id"] if group else None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the dashboard HTML."""
    from portal.deps import get_templates
    templates = get_templates()
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/api/gossip/dashboard/overview")
async def dashboard_overview():
    """Aggregate stats + member list for the dashboard."""
    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"error": "no group"})

    members = get_members_by_group(group_id)
    google_connected = 0
    total_dms = 0
    dms_delivered = 0
    total_dossier_bytes = 0
    dossier_count = 0
    member_list = []

    cfg = get_config()
    dossiers_dir = cfg.dossiers_dir

    for m in members:
        has_google = get_oauth_token(m["id"], "google") is not None
        if has_google:
            google_connected += 1

        dm_history = get_dm_history(m["id"], limit=50)
        dm_count = len(dm_history)
        total_dms += dm_count
        delivered = sum(1 for d in dm_history if "FAILED" not in d.get("message_text", "") and "failed" not in d.get("message_text", ""))
        dms_delivered += delivered

        last_dm = get_last_dm(m["id"])
        last_dm_text = ""
        if last_dm and "FAILED" not in last_dm.get("message_text", "") and "failed" not in last_dm.get("message_text", ""):
            last_dm_text = last_dm["message_text"][:80]

        # Dossier size
        dossier_path = dossiers_dir / f"{m['display_name'].lower().replace(' ', '_')}.md"
        dossier_bytes = 0
        if dossier_path.exists():
            dossier_bytes = dossier_path.stat().st_size
            total_dossier_bytes += dossier_bytes
            dossier_count += 1

        member_list.append({
            "name": m["display_name"],
            "username": m.get("discord_username"),
            "google": has_google,
            "dm_count": dm_count,
            "dossier_bytes": dossier_bytes,
            "last_dm": last_dm_text,
        })

    # Memory stats
    memories = get_donny_memory(limit=100)
    memory_channels = len(set(m["channel_type"] for m in memories))

    return JSONResponse({
        "total_members": len(members),
        "google_connected": google_connected,
        "total_dms": total_dms,
        "dms_delivered": dms_delivered,
        "total_memories": len(memories),
        "memory_channels": memory_channels,
        "total_dossier_bytes": total_dossier_bytes,
        "dossier_count": dossier_count,
        "members": member_list,
    })


@router.get("/api/gossip/dashboard/activity")
async def dashboard_activity():
    """Recent activity feed — DMs, memory logs, cron events."""
    events = []

    # DM activity
    group_id = _get_group_id()
    if group_id:
        members = get_members_by_group(group_id)
        for m in members:
            dms = get_dm_history(m["id"], limit=5)
            for dm in dms:
                direction = "→" if dm["direction"] == "outbound" else "←"
                failed = "FAILED" in dm.get("message_text", "") or "failed" in dm.get("message_text", "")
                events.append({
                    "type": "error" if failed else "dm",
                    "text": f"{direction} {m['display_name']}: {dm['message_text'][:100]}",
                    "time": dm["created_at"],
                })

    # Memory
    memories = get_donny_memory(limit=15)
    for mem in memories:
        events.append({
            "type": "memory",
            "text": f"[{mem['channel_type']}] {mem['content'][:100]}",
            "time": mem["created_at"],
        })

    # DB events
    db_events = get_events(limit=20)
    for ev in db_events:
        etype = "context"
        if "error" in (ev.get("event_subtype") or ""):
            etype = "error"
        elif "sync" in (ev.get("event_type") or ""):
            etype = "cron"
        elif "dm" in (ev.get("event_type") or ""):
            etype = "dm"

        events.append({
            "type": etype,
            "text": ev.get("summary", "")[:100],
            "time": ev.get("created_at"),
        })

    # Sort by time descending
    events.sort(key=lambda e: e.get("time") or "", reverse=True)

    return JSONResponse({"events": events[:50]})


@router.get("/api/gossip/dashboard/memory")
async def dashboard_memory():
    """Donny's memory entries."""
    memories = get_donny_memory(limit=50)
    return JSONResponse({
        "memories": [
            {
                "channel_type": m["channel_type"],
                "content": m["content"],
                "timestamp": m["created_at"],
                "target": m.get("target"),
            }
            for m in memories
        ]
    })


@router.get("/api/gossip/dashboard/dossiers")
async def dashboard_dossiers():
    """All dossier file contents."""
    cfg = get_config()
    dossiers_dir = cfg.dossiers_dir
    dossiers_dir.mkdir(parents=True, exist_ok=True)

    dossiers = []
    for path in sorted(dossiers_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        name = path.stem.replace("_", " ").title()
        dossiers.append({
            "name": name,
            "filename": path.name,
            "content": content,
            "size": len(content.encode("utf-8")),
        })

    return JSONResponse({"dossiers": dossiers})


@router.get("/api/gossip/dashboard/dms")
async def dashboard_dms():
    """All DM conversations grouped by member."""
    group_id = _get_group_id()
    if not group_id:
        return JSONResponse({"conversations": []})

    members = get_members_by_group(group_id)
    conversations = []

    for m in members:
        history = get_dm_history(m["id"], limit=20)
        if not history:
            continue

        messages = []
        for dm in reversed(history):
            messages.append({
                "direction": dm["direction"],
                "text": dm["message_text"][:200],
                "time": dm["created_at"],
            })

        conversations.append({
            "member": m["display_name"],
            "username": m.get("discord_username"),
            "message_count": len(history),
            "messages": messages,
        })

    return JSONResponse({"conversations": conversations})


@router.get("/api/gossip/dashboard/crons")
async def dashboard_crons():
    """Cron job status — reads from OpenClaw's cron store."""
    import json as json_mod

    cron_path = Path.home() / ".openclaw-gossip" / "cron" / "jobs.json"
    if not cron_path.exists():
        return JSONResponse({"jobs": []})

    try:
        data = json_mod.loads(cron_path.read_text())
        jobs = []
        for job in data.get("jobs", []):
            state = job.get("state", {})
            schedule = job.get("schedule", {})

            # Calculate next run
            next_ms = state.get("nextRunAtMs")
            last_ms = state.get("lastRunAtMs")

            import time
            now_ms = int(time.time() * 1000)

            next_in = ""
            if next_ms:
                diff = (next_ms - now_ms) // 60000
                if diff < 0:
                    next_in = "overdue"
                elif diff < 60:
                    next_in = f"{diff}m"
                else:
                    next_in = f"{diff // 60}h {diff % 60}m"

            last_ago = ""
            if last_ms:
                diff = (now_ms - last_ms) // 60000
                if diff < 60:
                    last_ago = f"{diff}m ago"
                else:
                    last_ago = f"{diff // 60}h {diff % 60}m ago"

            jobs.append({
                "id": job.get("id", ""),
                "name": job.get("name", ""),
                "schedule": schedule.get("display", f"every {schedule.get('everyMs', 0) // 60000}m"),
                "enabled": job.get("enabled", False),
                "next_in": next_in,
                "last_ago": last_ago,
                "last_status": state.get("lastStatus", "—"),
                "consecutive_errors": state.get("consecutiveErrors", 0),
                "last_error": state.get("lastError", ""),
            })

        return JSONResponse({"jobs": jobs})
    except Exception as e:
        return JSONResponse({"jobs": [], "error": str(e)})

# BUILD.md — Donny Gossip Bot on OpenClaw

> **What this is:** The complete implementation spec for building Donny on OpenClaw.
> Read this entire document before writing any code. It is the single source of truth.
> The `architecture.html` file in this repo has visual diagrams for reference.

---

## 1. What You're Building

Donny is a Discord bot that acts as a friend in a group chat. He pays attention, remembers things about people, connects dots between members, and proactively keeps conversations alive. He reads members' calendars and emails (with consent) to know what's going on in their lives. He DMs people to check in. He drops conversation starters when chat goes quiet.

From the user's perspective, Donny is just a member of the friend group who happens to know everything. He is NOT a bot, NOT an assistant. He's a friend who's always in the loop.

---

## 2. Architecture: One Donny Brain

### Core Principle
There is ONE Donny persona. Every message a user sees — in group chat, in DMs, in proactive outreach — comes from the same voice. There are no separate sub-agents with different personalities.

### Three Layers

**Layer 1: Donny Brain (Claude Sonnet)**
- Handles ALL user-facing text: group chat responses, DM conversations, proactive outreach
- Runs inside OpenClaw as the main agent
- Uses SOUL.md for personality, SKILL.md for behavior rules
- Gets context via custom tools that call the Python API

**Layer 2: Background Synthesizers (Claude Haiku)**
- Headless data processors with NO persona — they never write user-facing text
- Run as isolated OpenClaw cron jobs
- Take raw data (calendar events, email subjects, chat mentions) and produce structured member summaries
- Write summaries to `data/summaries/{member_name}.md`

**Layer 3: Python Data Layer**
- FastAPI portal serves web pages AND a JSON API
- SQLite database (WAL mode) shared between portal and OpenClaw tools
- Google API connectors (Calendar, Gmail)
- Core engine functions (context assembly, idle detection, identity resolution)
- Runs as a separate process alongside OpenClaw

### Session Model
- **Group chat:** Single shared session. All group messages go to the same OpenClaw session.
- **DMs:** Per-user isolated sessions. Use OpenClaw's `dmScope: "per-channel-peer"` config. Person A's DM history is NEVER visible when Donny responds to Person B.
- **Cron jobs:** Isolated sessions. Each cron job (synthesizer, DM check-in, discovery) runs in its own session with no main-context pollution.

### Privacy Rules
- DM content from person A is NEVER included in responses to person B
- DM content is NEVER fed to synthesizers — synthesizers only see calendar, pre-filtered email, chat mentions, and previous summary
- The email pre-filter runs in Python code BEFORE data reaches any LLM — it drops medical/financial/legal/romantic emails by pattern matching
- Donny "plays dumb" about calendar knowledge: asks "what are you up to friday?" not "oh you've got dinner at Nobu on friday"

---

## 3. Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent runtime | OpenClaw (Node.js) | Gateway, Discord adapter, cron, heartbeat, skills, sessions |
| Agent LLM | Claude Sonnet (user-facing), Claude Haiku (synthesizers) | Cost balance |
| Data layer | Python 3.11+ | Existing proven code, Google API libraries |
| Web portal | FastAPI + Jinja2 | Existing working portal |
| Database | SQLite (WAL mode, busy_timeout=5000) | Single file, shared between processes |
| Google APIs | google-api-python-client | Calendar + Gmail connectors |
| Tunnel | cloudflared (optional) | Public URL for OAuth callbacks |

### How They Connect

```
OpenClaw Gateway (Node.js)
  ├── Discord adapter (discord.js, built-in)
  ├── Donny agent (SOUL.md + SKILL.md)
  ├── Gossip plugin (TypeScript, calls Python API via HTTP)
  ├── Cron jobs (synthesizer, DM check-in, discovery)
  └── Heartbeat (idle gossip check)
         │
         │ HTTP (localhost:3000/api/*)
         ▼
Python Portal (FastAPI)
  ├── Web routes (/join, /me, /auth/google)
  ├── Tool API (/api/gossip/*)
  ├── Google Calendar connector
  ├── Gmail connector
  └── SQLite DB (data/gossip.db)
```

Both processes share the SQLite database via WAL mode.

---

## 4. What Exists vs. What to Build

### KEEP AS-IS (Python — proven, runtime-agnostic)
- `gossip/db.py` — SQLite schema + CRUD (needs minor additions, see Phase 2)
- `gossip/engine.py` — Context assembly, idle detection (needs refactoring, see Phase 3)
- `gossip/dossiers.py` — Markdown dossier I/O
- `gossip/config.py` — YAML config loader
- `gossip/logger.py` — Event logging
- `gossip/sources/calendar.py` — Google Calendar connector
- `gossip/sources/gmail.py` — Gmail connector
- `portal/` — FastAPI web portal (needs API endpoints added, see Phase 5)

### REMOVE (Hermes-specific, replaced by OpenClaw)
- `vendor/hermes-agent/` — Entire submodule (replaced by OpenClaw)
- `gossip_tools/` — Hermes tool registration (replaced by OpenClaw plugin)
- `gossip/discord_commands.py` — Hermes Discord patches (replaced by OpenClaw Discord adapter)
- `hooks/gossip-logger/` — Hermes hook (replaced by OpenClaw hooks if needed)
- `config/cron/jobs.json` — Hermes cron format (replaced by OpenClaw cron)

### CREATE NEW
- `openclaw/` — OpenClaw agent workspace (SOUL.md, SKILL.md, config)
- `openclaw/plugins/gossip/` — TypeScript plugin (thin bridge to Python API)
- `gossip/email_filter.py` — Code-level email sensitivity pre-filter
- `gossip/proactive.py` — Pre-check gate for cron jobs (costs $0 when not firing)
- `gossip/synthesizer.py` — Summary generation coordination
- `portal/routes/tool_api.py` — JSON API endpoints for OpenClaw tools
- `scripts/start.sh` — New launch script (OpenClaw + Python portal)

### MODIFY
- `gossip/db.py` — Add 3 new tables + 1 new column + busy_timeout
- `gossip/engine.py` — Add timezone support, refactor context assembly, add message-count windowing
- `gossip/identity.py` — Rewrite as 4-layer cascade with case-insensitive matching + nicknames

---

## 5. Environment Variables

Create `config/.env` on the target machine. These values are NOT in the repo.

```bash
# === REQUIRED ===

# Anthropic (LLM for Donny brain + synthesizers)
ANTHROPIC_API_KEY=sk-ant-...

# Discord
DISCORD_BOT_TOKEN=...
DISCORD_HOME_CHANNEL=...     # Channel ID where Donny drops idle gossip

# === REQUIRED FOR GOOGLE FEATURES ===

# Google OAuth (for members to connect calendar/email)
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...

# Bot's Google account (for shared calendars)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...

# === OPTIONAL ===

# Portal
PORTAL_PORT=3000
PORTAL_SECRET_KEY=...        # For session signing (generate with: python -c "import secrets; print(secrets.token_hex(32))")
PORTAL_PUBLIC_URL=...        # Set by tunnel script, or manual for production

# Bot email (for location sharing instructions)
GOSSIP_EMAIL=donny@gmail.com

# Telegram (Phase 2)
TELEGRAM_BOT_TOKEN=...

# Image generation
GOOGLE_GEMINI_API_KEY=...

# Token encryption key (for encrypting OAuth tokens at rest)
GOSSIP_TOKEN_KEY=...         # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 6. Project Structure (Target)

```
gossip/
├── openclaw/                          # NEW — OpenClaw agent workspace
│   ├── SOUL.md                        # Donny personality (copy from config/SOUL.md)
│   ├── SKILL.md                       # Donny behavior rules
│   ├── SYNTHESIZER_SKILL.md           # Synthesizer behavior (for cron jobs)
│   ├── HEARTBEAT.md                   # Idle gossip check config
│   ├── openclaw.json                  # OpenClaw configuration
│   └── plugins/
│       └── gossip/
│           ├── package.json
│           ├── tsconfig.json
│           ├── openclaw.plugin.json   # Plugin manifest
│           └── src/
│               └── index.ts           # Tool registrations (HTTP calls to Python API)
│
├── gossip/                            # Python core engine (KEEP + MODIFY)
│   ├── __init__.py
│   ├── db.py                          # +3 tables, +1 column, +busy_timeout
│   ├── engine.py                      # +timezone, +message windowing, +gossip_context()
│   ├── dossiers.py                    # unchanged
│   ├── identity.py                    # REWRITE: 4-layer cascade
│   ├── config.py                      # +timezone field
│   ├── logger.py                      # unchanged
│   ├── email_filter.py                # NEW: code-level email pre-filter
│   ├── proactive.py                   # NEW: pre-check gate
│   ├── synthesizer.py                 # NEW: summary generation coordinator
│   └── sources/
│       ├── __init__.py
│       ├── calendar.py                # +token refresh, +401 handling
│       └── gmail.py                   # +email_filter integration
│
├── portal/                            # Python web portal (KEEP + ADD API)
│   ├── __init__.py
│   ├── app.py
│   ├── deps.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── invite.py
│   │   ├── onboard.py                 # +nicknames field
│   │   ├── profile.py
│   │   ├── oauth_google.py            # +immediate synthesizer trigger after deep sync
│   │   ├── map_view.py
│   │   ├── api.py
│   │   └── tool_api.py               # NEW: JSON API for OpenClaw tools
│   ├── templates/
│   │   ├── base.html
│   │   ├── invite.html                # +nicknames field
│   │   ├── connect_sources.html       # remove "intel" and "gossip engine" language
│   │   └── profile.html
│   └── static/
│       └── style.css
│
├── config/
│   ├── .env                           # NOT in repo — create on target machine
│   ├── SOUL.md                        # Legacy location — copy to openclaw/SOUL.md
│   └── gossip.yaml                    # +timezone field
│
├── data/                              # Runtime data (gitignored)
│   ├── gossip.db
│   ├── dossiers/                      # Legacy dossiers (read-only after summaries exist)
│   ├── summaries/                     # NEW: synthesizer-generated member summaries
│   ├── chat/                          # Daily chat transcripts
│   ├── group.md                       # Group dynamics
│   └── logs/
│
├── scripts/
│   └── start.sh                       # REWRITE: launch OpenClaw + Python portal
│
├── skills/gossip/SKILL.md             # Legacy — behavior moves to openclaw/SKILL.md
├── architecture.html                  # Visual architecture diagrams (reference)
├── BUILD.md                           # THIS FILE
├── PRODUCT.md                         # Product spec
├── TODO.md                            # Status tracking
├── gossip.yaml                        # Symlink or copy to config/
├── pyproject.toml
├── .gitignore
└── README.md
```

---

## 7. Database Schema Changes

### New Tables (add to db.py SCHEMA)

```sql
-- Donny's memory of what he said (rolling log, auto-trim >48h)
CREATE TABLE IF NOT EXISTS donny_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    channel_type TEXT NOT NULL,   -- 'group', 'dm/{member_name}', 'proactive/{member_name}'
    target TEXT,                  -- member name or channel
    content TEXT NOT NULL,        -- what donny said
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_donny_memory_channel ON donny_memory(channel_type);
CREATE INDEX IF NOT EXISTS idx_donny_memory_created ON donny_memory(created_at);

-- Anti-spam for discovery outreach (max 1 DM per undiscovered user per 7 days)
CREATE TABLE IF NOT EXISTS discovery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    platform_username TEXT,
    dm_sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    outcome TEXT,                  -- 'joined', 'ignored', 'blocked'
    UNIQUE(platform, platform_user_id)
);

-- Member summaries (synthesizer output, replaces append-only dossiers)
CREATE TABLE IF NOT EXISTS member_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    summary_json TEXT NOT NULL,    -- JSON: {this_week, patterns, relationships, recent, flagged, donny_notes, updated}
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(member_id)
);
```

### New Column on members

```sql
ALTER TABLE members ADD COLUMN nicknames TEXT;  -- comma-separated alternative names
```

### Connection Changes

Add `busy_timeout` to `get_connection()`:

```python
conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
```

### CRUD Functions to Add

```python
# donny_memory
def log_donny_memory(channel_type: str, target: str | None, content: str) -> int
def get_donny_memory(channel_type: str | None = None, limit: int = 30) -> list[dict]
def trim_donny_memory(max_age_hours: int = 48) -> int  # returns rows deleted

# discovery_log
def log_discovery_attempt(platform: str, user_id: str, username: str | None = None) -> None
def get_discovery_attempt(platform: str, user_id: str) -> dict | None
def can_dm_undiscovered(platform: str, user_id: str, cooldown_days: int = 7) -> bool

# member_summaries
def upsert_member_summary(member_id: str, summary_json: str) -> None
def get_member_summary(member_id: str) -> dict | None
def get_all_member_summaries(group_id: str) -> list[dict]

# purge (GDPR-like deletion)
def purge_member(member_id: str, member_name: str) -> None
    # 1. delete member row (cascades oauth_tokens, dm_history, manual_input, sync_state, member_summaries)
    # 2. delete dossier file: data/dossiers/{name}.md
    # 3. delete summary file: data/summaries/{name}.md
    # 4. scrub name from donny_memory (replace with "[removed]")
```

---

## 8. Build Phases

### Phase 1: Project Setup

**On the target machine:**

1. Clone the repo
2. Create Python venv: `python -m venv .venv && source .venv/bin/activate`
3. Install Python deps: `pip install -e .` (uses pyproject.toml)
4. Create `config/.env` with the required environment variables
5. Ensure OpenClaw is installed: `openclaw doctor`
6. Create the OpenClaw agent workspace: `mkdir -p openclaw/plugins/gossip/src`

**Verify:** `python -c "from gossip.db import init_db; init_db()"` creates `data/gossip.db`

### Phase 2: Database + Identity Updates

1. Add the 3 new tables to `gossip/db.py` SCHEMA
2. Add `nicknames TEXT` migration to `init_db()`
3. Add `PRAGMA busy_timeout=5000` to `get_connection()`
4. Add CRUD functions for donny_memory, discovery_log, member_summaries, purge_member
5. Rewrite `gossip/identity.py` with 4-layer cascade:

```python
def resolve_member(platform: str, user_id=None, username=None, display_name=None) -> dict | None:
    """4-layer identity cascade. Always backfills platform ID when found."""
    if platform == "discord":
        # Layer 1: discord_id (exact match)
        if user_id:
            member = _query("SELECT * FROM members WHERE discord_id = ?", user_id)
            if member: return member

        # Layer 2: discord_username (case-insensitive)
        if username:
            member = _query("SELECT * FROM members WHERE LOWER(discord_username) = LOWER(?)", username)
            if member:
                if user_id and not member.get("discord_id"):
                    update_member(member["id"], discord_id=user_id)
                return member

        # Layer 3: nicknames (case-insensitive, comma-separated field)
        if username:
            members = _query_all("SELECT * FROM members WHERE nicknames IS NOT NULL")
            for m in members:
                nicks = [n.strip().lower() for n in m["nicknames"].split(",")]
                if username.lower() in nicks:
                    if user_id and not m.get("discord_id"):
                        update_member(m["id"], discord_id=user_id)
                    return m

        # Layer 4: display_name (case-insensitive fuzzy)
        if display_name or username:
            name = display_name or username
            member = _query("SELECT * FROM members WHERE LOWER(display_name) = LOWER(?)", name)
            if member:
                if user_id and not member.get("discord_id"):
                    update_member(member["id"], discord_id=user_id)
                return member

    return None
```

6. Add `timezone` field to `GossipConfig` in `config.py`:
```python
timezone: str = "America/Los_Angeles"  # Default, override in gossip.yaml
```

7. Update `is_quiet_hours()` in `engine.py` to use timezone:
```python
from zoneinfo import ZoneInfo
tz = ZoneInfo(cfg.gossip.timezone)
hour = datetime.now(tz).hour
```

**Verify:** `python -c "from gossip.db import init_db; init_db()"` — no errors, new tables exist

### Phase 3: Email Filter + Proactive Pre-Check

**Create `gossip/email_filter.py`:**

```python
"""Code-level email sensitivity pre-filter.
Drops sensitive emails BEFORE they reach any LLM.
This is a privacy gate, not an LLM call."""

SENSITIVE_DOMAINS = [
    "mychart", "patient", "health", "medical", "pharmacy",
    "bank", "chase", "wellsfargo", "payroll", "irs.gov",
    "courts.", "legal", "attorney",
]

SENSITIVE_SUBJECTS = [
    r"(?i)(diagnosis|prescription|lab results|appointment.*dr)",
    r"(?i)(statement|balance|payment due|wire transfer|tax return)",
    r"(?i)(court date|subpoena|legal notice|custody)",
    r"(?i)(std |hiv|pregnancy|therapy|counseling)",
]

def filter_emails(emails: list[dict]) -> list[dict]:
    """Remove sensitive emails. Returns only safe-to-process emails."""
    import re
    safe = []
    for em in emails:
        sender = em.get("from", "").lower()
        subject = em.get("subject", "")

        # Domain check
        if any(d in sender for d in SENSITIVE_DOMAINS):
            continue

        # Subject pattern check
        if any(re.search(p, subject) for p in SENSITIVE_SUBJECTS):
            continue

        safe.append(em)
    return safe
```

**Create `gossip/proactive.py`:**

```python
"""Pre-check gate for cron jobs. ~80% of checks cost $0 (no LLM call)."""

from gossip.db import get_chat_activity, get_default_group, get_dm_history, get_members_by_group
from gossip.engine import is_quiet_hours, get_idle_hours

def should_fire_idle_gossip() -> dict:
    """Code-level check before calling LLM for idle gossip."""
    if is_quiet_hours():
        return {"fire": False, "reason": "quiet_hours", "cost": 0}

    group = get_default_group()
    if not group:
        return {"fire": False, "reason": "no_group", "cost": 0}

    hours = get_idle_hours(group["id"])
    # Dynamic threshold: 3h base, shorter if high-activity day
    threshold = 3.0  # TODO: make dynamic based on daily message count
    if hours < threshold:
        return {"fire": False, "reason": f"active ({hours:.1f}h)", "cost": 0}

    return {"fire": True, "reason": f"idle {hours:.1f}h", "hours_idle": hours}

def should_dm_checkin(member_id: str) -> dict:
    """Check if we should DM this member."""
    if is_quiet_hours():
        return {"fire": False, "reason": "quiet_hours"}

    history = get_dm_history(member_id, limit=1)
    if history:
        from datetime import datetime, timezone
        last = datetime.fromisoformat(history[0]["created_at"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if hours_since < 4:  # Don't DM more than once every 4 hours
            return {"fire": False, "reason": f"recent DM ({hours_since:.1f}h ago)"}

    return {"fire": True, "reason": "ready"}
```

**Verify:** `python -c "from gossip.email_filter import filter_emails; print(filter_emails([{'from': 'chase@chase.com', 'subject': 'Statement'}]))"` — returns `[]`

### Phase 4: Synthesizer

**Create `gossip/synthesizer.py`:**

```python
"""Background synthesizer — generates structured member summaries from raw data.
Called by OpenClaw cron job via the tool API. Uses Haiku, never writes user-facing text."""

import json
from datetime import datetime, timezone
from gossip.db import get_member_summary, upsert_member_summary, get_members_by_group, get_default_group
from gossip.dossiers import read_dossier
from gossip.sources.calendar import sync_member_calendar
from gossip.sources.gmail import sync_member_gmail
from gossip.email_filter import filter_emails
from gossip.engine import get_recent_chat

SUMMARY_STRUCTURE = {
    "this_week": "",        # What's happening this week (calendar + recent activity)
    "patterns": "",         # Behavioral patterns (gym 3x/week, always late, etc.)
    "relationships": "",    # Who they interact with most, dynamics
    "recent": "",           # Last notable thing from chat/email/calendar
    "flagged": "",          # Anything sensitive or notable
    "donny_notes": "",      # Running jokes, relationship dynamics, persistent context
    "updated": "",          # ISO timestamp
}

def build_synthesizer_input(member_id: str, member_name: str) -> str:
    """Assemble raw data for the synthesizer. NO DM content included."""
    parts = []

    # Dossier (legacy, read-only)
    dossier = read_dossier(member_name)
    if "(no info yet)" not in dossier:
        parts.append(f"## Existing Dossier\n{dossier[:1000]}")

    # Previous summary (for continuity, especially donny_notes)
    prev = get_member_summary(member_id)
    if prev:
        parts.append(f"## Previous Summary\n{prev['summary_json']}")

    # Recent chat mentions (grep for their name in recent chat)
    chat = get_recent_chat(days=2)
    # Extract lines mentioning this member
    mention_lines = [l for l in chat.split("\n") if member_name.lower() in l.lower()]
    if mention_lines:
        parts.append(f"## Chat Mentions (last 2 days)\n" + "\n".join(mention_lines[-20:]))

    return "\n\n".join(parts) if parts else "(no data available)"

def get_synthesizer_prompt(member_name: str, raw_input: str) -> str:
    """Build the prompt for the Haiku synthesizer."""
    return f"""You are a background data processor. Analyze the following raw data about {member_name} and produce a structured JSON summary. Do NOT write any conversational text. Output ONLY valid JSON.

Raw data:
{raw_input}

Output this exact JSON structure:
{{
  "this_week": "brief summary of what's happening this week",
  "patterns": "behavioral patterns observed",
  "relationships": "who they interact with, dynamics",
  "recent": "last notable thing",
  "flagged": "anything sensitive or time-sensitive",
  "donny_notes": "running jokes, relationship dynamics to remember (PRESERVE from previous summary if exists)",
  "updated": "{datetime.now(timezone.utc).isoformat()}"
}}

Rules:
- Keep each field under 200 chars
- Preserve donny_notes from previous summary — these are long-term memory
- Flag time-sensitive items (upcoming events, deadlines)
- Do NOT include any DM content
- Do NOT write conversational text
- Output ONLY the JSON object, nothing else"""
```

**Verify:** `python -c "from gossip.synthesizer import build_synthesizer_input; print('ok')"` — no import errors

### Phase 5: Portal Tool API

**Create `portal/routes/tool_api.py`:**

This is the bridge between OpenClaw and the Python data layer. Every tool the OpenClaw plugin needs is exposed as a JSON endpoint.

```python
"""JSON API endpoints for OpenClaw gossip tools.
The OpenClaw TypeScript plugin calls these endpoints via HTTP."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/gossip")

# POST /api/gossip/context
# Body: {"type": "group"|"dm"|"proactive", "member": "name"|null}
# Returns: {"context": "assembled context string"}
@router.post("/context")
async def get_context(request: Request): ...

# POST /api/gossip/idle-check
# Body: {} (no params)
# Returns: {"should_fire": bool, "reason": str, "hours_idle": float, "is_quiet_hours": bool}
@router.post("/idle-check")
async def idle_check(request: Request): ...

# POST /api/gossip/generate
# Body: {"gossip_text": "...", "context_summary": "..."}
# Returns: {"id": int, "posted_at": str}
@router.post("/generate")
async def generate(request: Request): ...

# POST /api/gossip/dossier/read
# Body: {"member_name": "..."}
# Returns: {"member_name": str, "dossier": str}
@router.post("/dossier/read")
async def read_dossier_api(request: Request): ...

# POST /api/gossip/dossier/update
# Body: {"member_name": "...", "entry": "...", "source": "..."}
# Returns: {"success": bool}
@router.post("/dossier/update")
async def update_dossier_api(request: Request): ...

# POST /api/gossip/pick-dm-target
# Body: {} (no params)
# Returns: {"name": str, "discord_id": str, "score": float, "suggested_angle": str, ...}
@router.post("/pick-dm-target")
async def pick_dm_target(request: Request): ...

# POST /api/gossip/log-dm
# Body: {"member_name": "...", "message_text": "...", "direction": "outbound"|"inbound"}
# Returns: {"success": bool}
@router.post("/log-dm")
async def log_dm_api(request: Request): ...

# POST /api/gossip/log-memory
# Body: {"channel_type": "...", "target": "...", "content": "..."}
# Returns: {"success": bool}
@router.post("/log-memory")
async def log_memory(request: Request): ...

# POST /api/gossip/discover-members
# Body: {"platform": "discord", "known_user_ids": ["...", ...]}
# Returns: {"undiscovered": [{"user_id": str, "username": str, "can_dm": bool}]}
@router.post("/discover-members")
async def discover_members(request: Request): ...

# POST /api/gossip/sync-sources
# Body: {} (no params)
# Returns: {"synced": int, "failed": int, "members": [...]}
@router.post("/sync-sources")
async def sync_sources(request: Request): ...

# POST /api/gossip/synthesizer/run
# Body: {"member_id": "...", "member_name": "..."}
# Returns: {"input": str, "prompt": str}  (OpenClaw calls Haiku with this prompt)
@router.post("/synthesizer/run")
async def synthesizer_run(request: Request): ...

# POST /api/gossip/synthesizer/save
# Body: {"member_id": "...", "summary_json": "..."}
# Returns: {"success": bool}
@router.post("/synthesizer/save")
async def synthesizer_save(request: Request): ...

# POST /api/gossip/update-dynamics
# Body: {"observation": "..."}
# Returns: {"success": bool}
@router.post("/update-dynamics")
async def update_dynamics(request: Request): ...

# GET /api/gossip/members
# Returns: {"members": [{"id": str, "display_name": str, "discord_id": str, ...}]}
@router.get("/members")
async def list_members(request: Request): ...

# POST /api/gossip/resolve-member
# Body: {"platform": "discord", "user_id": "...", "username": "...", "display_name": "..."}
# Returns: {"member": {...} | null}
@router.post("/resolve-member")
async def resolve_member_api(request: Request): ...
```

**Register in `portal/app.py`:**
```python
from portal.routes.tool_api import router as tool_api_router
app.include_router(tool_api_router)
```

**Verify:** Start portal, `curl -X POST http://localhost:3000/api/gossip/idle-check` — returns JSON

### Phase 6: OpenClaw Configuration

**Create `openclaw/openclaw.json`:**

```json5
{
  // Agent identity
  "name": "donny",

  // Discord channel configuration
  "channels": {
    "discord": {
      "enabled": true,
      "token": { "source": "env", "id": "DISCORD_BOT_TOKEN" },
      "dmScope": "per-channel-peer",  // CRITICAL: isolates DM sessions per user
      "guilds": {
        // The guild ID will be filled in during setup
        // "GUILD_ID": {
        //   "channelIds": ["HOME_CHANNEL_ID"],
        //   "requireMention": false
        // }
      }
    }
  },

  // LLM configuration
  "providers": {
    "anthropic": {
      "apiKey": { "source": "env", "id": "ANTHROPIC_API_KEY" },
      "defaultModel": "claude-sonnet-4-20250514"
    }
  },

  // Agent defaults
  "agents": {
    "defaults": {
      "model": "claude-sonnet-4-20250514",
      "memorySearch": {
        "enabled": false  // We use SQLite, not OpenClaw's built-in memory
      }
    }
  }
}
```

**Create `openclaw/HEARTBEAT.md`:**

```markdown
---
interval_minutes: 30
quiet_hours_start: 23
quiet_hours_end: 9
---

Check if the group chat has been quiet long enough for you to say something.

1. Call `gossip_idle_check` to see if you should fire
2. If `should_fire` is false, stop — do nothing
3. If `should_fire` is true, call `gossip_context` with type "group"
4. Read the context carefully. Pick ONE interesting thing — ideally something that connects two people or would get someone to respond
5. Say it naturally, on one line, as donny
6. Call `gossip_log_memory` with what you said
7. Call `gossip_generate` to record it in history
```

**Verify:** `openclaw doctor` passes

### Phase 7: OpenClaw Plugin (TypeScript)

**Create `openclaw/plugins/gossip/openclaw.plugin.json`:**
```json
{
  "name": "gossip",
  "version": "1.0.0",
  "description": "Gossip bot tools — bridge to Python data layer",
  "capabilities": ["tools"]
}
```

**Create `openclaw/plugins/gossip/package.json`:**
```json
{
  "name": "gossip-plugin",
  "version": "1.0.0",
  "type": "module",
  "main": "src/index.ts"
}
```

**Create `openclaw/plugins/gossip/src/index.ts`:**

This is the thin bridge. Each tool makes an HTTP call to the Python portal API.

```typescript
const API_BASE = process.env.GOSSIP_API_URL || "http://localhost:3000/api/gossip";

async function callApi(endpoint: string, body: Record<string, unknown> = {}) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${await res.text()}`);
  return await res.json();
}

export default function register(api: any) {

  api.registerTool({
    name: "gossip_idle_check",
    description: "Check if chat is idle enough to drop gossip. Returns {should_fire, reason, hours_idle}.",
    parameters: {},
    execute: async () => callApi("/idle-check"),
  });

  api.registerTool({
    name: "gossip_context",
    description: "Get full context for responding. Type: 'group' (chat response/idle drop), 'dm' (DM conversation), 'proactive' (DM outreach).",
    parameters: {
      type: { type: "string", enum: ["group", "dm", "proactive"], required: true },
      member: { type: "string", description: "Member name (required for dm/proactive)", required: false },
    },
    execute: async (params: { type: string; member?: string }) => callApi("/context", params),
  });

  api.registerTool({
    name: "gossip_generate",
    description: "Log a gossip message you just said (for history tracking).",
    parameters: {
      gossip_text: { type: "string", required: true },
      context_summary: { type: "string", required: false },
    },
    execute: async (params: any) => callApi("/generate", params),
  });

  api.registerTool({
    name: "gossip_read_dossier",
    description: "Read what you know about a member.",
    parameters: {
      member_name: { type: "string", required: true },
    },
    execute: async (params: any) => callApi("/dossier/read", params),
  });

  api.registerTool({
    name: "gossip_update_dossier",
    description: "Remember something new about a member.",
    parameters: {
      member_name: { type: "string", required: true },
      entry: { type: "string", required: true },
      source: { type: "string", required: false },
    },
    execute: async (params: any) => callApi("/dossier/update", params),
  });

  api.registerTool({
    name: "gossip_pick_dm_target",
    description: "Pick a member to check in with via DM.",
    parameters: {},
    execute: async () => callApi("/pick-dm-target"),
  });

  api.registerTool({
    name: "gossip_log_dm",
    description: "Record a DM you sent or received.",
    parameters: {
      member_name: { type: "string", required: true },
      message_text: { type: "string", required: true },
      direction: { type: "string", enum: ["outbound", "inbound"], required: false },
    },
    execute: async (params: any) => callApi("/log-dm", params),
  });

  api.registerTool({
    name: "gossip_log_memory",
    description: "Log something donny said (for memory continuity).",
    parameters: {
      channel_type: { type: "string", required: true },
      target: { type: "string", required: false },
      content: { type: "string", required: true },
    },
    execute: async (params: any) => callApi("/log-memory", params),
  });

  api.registerTool({
    name: "gossip_sync_sources",
    description: "Sync calendar + email for all connected members.",
    parameters: {},
    execute: async () => callApi("/sync-sources"),
  });

  api.registerTool({
    name: "gossip_update_dynamics",
    description: "Note a relationship or behavior pattern you noticed.",
    parameters: {
      observation: { type: "string", required: true },
    },
    execute: async (params: any) => callApi("/update-dynamics", params),
  });

  api.registerTool({
    name: "gossip_discover_members",
    description: "Find new people on the Discord server who haven't joined yet.",
    parameters: {},
    execute: async () => callApi("/discover-members"),
  });

  api.registerTool({
    name: "gossip_resolve_member",
    description: "Look up a member by platform ID, username, or display name.",
    parameters: {
      platform: { type: "string", required: true },
      user_id: { type: "string", required: false },
      username: { type: "string", required: false },
      display_name: { type: "string", required: false },
    },
    execute: async (params: any) => callApi("/resolve-member", params),
  });
}
```

**Verify:** TypeScript compiles without errors

### Phase 8: Personality Files

**Create `openclaw/SOUL.md`:**
Copy the content from `config/SOUL.md` (already written, see the file in the repo). This is the personality definition. Do NOT modify it — it's been refined and works well.

**Create `openclaw/SKILL.md`:**

```markdown
---
name: donny
description: Friend group chat member who pays attention, connects people, and keeps conversations alive
version: 4.0.0
---

# Donny — Behavior Rules

## When You Respond
You only get called when someone @mentions you, DMs you, or says "donny" in the chat. You lurk otherwise.

**FIRST:** Call `gossip_context` with the right type:
- In group chat: `gossip_context(type="group")`
- In a DM: `gossip_context(type="dm", member="{their name}")`

**THEN:** Respond based on context. Keep it short — one or two sentences, all on one line. Type like you're texting.

## Referencing People
When someone says something, casually reference other people. "wait didn't ryan just say the same thing" or "this is literally what fabrizio was complaining about." Bring up people who aren't in the conversation. Notice overlaps — same place, same complaint, calendar contradicts what they said.

Don't direct people to each other. Just keep mentioning names and what they said or did. Let the connections happen naturally.

## Say One Thing, Not Everything
Just say the interesting part. One thing leads to a conversation. Everything at once kills it.

Bad: "Alex has 3 dinner reservations this week, went to the gym twice, and hasn't responded to Jordan's texts"
Good: "wait alex didn't you say you were staying in this weekend lol"

## Play Dumb About Sources
You know things from calendars and emails. NEVER reveal this. Instead:
- Ask leading questions: "what are you up to friday?" (not "oh you've got dinner friday")
- Say you "heard" or "noticed" things
- Act like someone mentioned it: "wait didn't someone say you were..."

## After You Speak
Call `gossip_log_memory` with what you said, so you remember it next time.

If you noticed something interesting about group dynamics, call `gossip_update_dynamics`.

## DM Conversations
When someone DMs you, be the same donny. Casual, curious, friend-like. Don't info-dump what you know about them. Ask one thing, follow up naturally.

What people tell you in DMs stays in DMs. Never reference DM content in group chat.

## Language Rules
NEVER use these words: gossip, tea, spill, dossier, intel, investigate, surveillance, target, asset, data, sync, algorithm.

NEVER explain your purpose or describe yourself as a bot. If someone asks what you do, deflect naturally. You're just donny.

## Available Tools
- `gossip_idle_check` — Check if chat is idle enough to say something
- `gossip_context` — Get full context (chat, summaries, dynamics, history)
- `gossip_generate` — Log what you said (for history)
- `gossip_read_dossier` — Read what you know about someone
- `gossip_update_dossier` — Remember something new about someone
- `gossip_pick_dm_target` — Pick who to check in with next
- `gossip_log_dm` — Record a DM you sent
- `gossip_log_memory` — Log something you said (for continuity)
- `gossip_update_dynamics` — Note relationship/behavior patterns
- `gossip_discover_members` — Find new people on the server
- `gossip_sync_sources` — Sync calendar + email for connected members
- `gossip_resolve_member` — Look up a member by ID/username/name
```

### Phase 9: Cron Jobs

OpenClaw cron jobs run in isolated sessions. Define them in `openclaw/openclaw.json` under a `cron` key (or however OpenClaw expects them — check OpenClaw docs).

**Job 1: Source Sync (every 2 hours)**
```
Prompt: "Call gossip_sync_sources to sync calendar and email data for all connected members."
Model: claude-haiku-4-5-20251001
```

**Job 2: DM Check-in (every 6 hours)**
```
Prompt: "Call gossip_pick_dm_target to find someone to check in with. If they have a suggested_angle, use it. Send them a casual DM as donny — one line, natural, like a friend checking in. Then call gossip_log_dm with what you said."
Model: claude-sonnet-4-20250514  (uses Sonnet because it writes user-facing text AS donny)
```

**Job 3: Member Discovery (every 12 hours)**
```
Prompt: "Call gossip_discover_members to find new people on the server. For anyone who can_dm is true, send them a casual intro DM. Don't explain what you are. Just be friendly."
Model: claude-sonnet-4-20250514
```

**Job 4: Synthesizer (every 2 hours)**
```
Prompt: "For each member, call gossip_synthesizer_run to get raw data and a prompt. Then generate the summary by following the prompt exactly. Save the result with gossip_synthesizer_save."
Model: claude-haiku-4-5-20251001
```

### Phase 10: Start Script

**Rewrite `scripts/start.sh`:**

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate Python venv
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Load environment
if [ -f "$PROJECT_ROOT/config/.env" ]; then
    set -a
    source "$PROJECT_ROOT/config/.env"
    set +a
fi

PORT="${PORTAL_PORT:-3000}"

echo ""
echo "  Starting Donny..."
echo ""

# Initialize database
python -c "from gossip.db import init_db; init_db()"

# Start Python portal in background
echo "  Starting portal on port $PORT..."
cd "$PROJECT_ROOT" && python -m portal.app &
PORTAL_PID=$!
sleep 2

# Start tunnel (optional)
TUNNEL_PID=""
PUBLIC_URL=""
if command -v cloudflared &>/dev/null; then
    echo "  Starting Cloudflare tunnel..."
    cloudflared tunnel --url "http://localhost:$PORT" 2>/tmp/cloudflared.log &
    TUNNEL_PID=$!
    for i in $(seq 1 15); do
        PUBLIC_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1)
        if [ -n "$PUBLIC_URL" ]; then break; fi
        sleep 1
    done
    if [ -n "$PUBLIC_URL" ]; then
        export PORTAL_PUBLIC_URL="$PUBLIC_URL"
    fi
fi

# Start OpenClaw gateway
echo "  Starting OpenClaw gateway..."
cd "$PROJECT_ROOT/openclaw"
openclaw gateway &
OPENCLAW_PID=$!

# Get invite token
INVITE_TOKEN=$(python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from gossip.config import load_config; load_config()
from gossip.db import get_default_group
g = get_default_group()
print(g['invite_token'] if g else 'NO_GROUP')
")

echo ""
echo "  Portal PID: $PORTAL_PID"
echo "  OpenClaw PID: $OPENCLAW_PID"
if [ -n "$TUNNEL_PID" ]; then echo "  Tunnel PID: $TUNNEL_PID"; fi
echo ""
echo "  Donny is running!"
echo "  Local: http://localhost:$PORT"
if [ -n "$PUBLIC_URL" ]; then
    echo "  Public: $PUBLIC_URL"
    echo "  Join:   $PUBLIC_URL/join/$INVITE_TOKEN"
fi
echo ""
echo "  Press Ctrl+C to stop"

trap "kill $PORTAL_PID $OPENCLAW_PID $TUNNEL_PID 2>/dev/null; echo '  Stopped.'; exit 0" INT TERM
wait
```

---

## 9. Context Assembly: `gossip_context(type, member)`

The `gossip_context` tool is the SINGLE entry point for all context. It replaces the old `build_gossip_context()` monolith. What it returns depends on `type`:

### type="group" (group chat response or idle drop)
```
## Recent Chat (last 60 messages)
[chat transcript]

## Member Summaries
[all member summaries from member_summaries table, max 700 chars each]

## Group Dynamics
[group.md content]

## Donny's Recent Memory
[last 30 entries from donny_memory WHERE channel_type = 'group']

## Previous Gossip (don't repeat these)
[last 20 from gossip_history]

## Investigation Notes
[knowledge gaps]
```

### type="dm" (DM conversation with specific member)
```
## About {member}
[their member summary only]

## Our DM History
[last 20 from dm_history WHERE member_id = this member]

## Donny's Memory (this DM)
[from donny_memory WHERE channel_type = 'dm/{member}']

## What's Happening in the Group
[brief group chat summary — last 10 messages only, no DM content from others]
```

### type="proactive" (DM outreach to specific member)
```
## About {member}
[their member summary]

## Our DM History
[last 10 from dm_history]

## Donny's Memory (this person)
[from donny_memory WHERE channel_type IN ('dm/{member}', 'proactive/{member}')]

## Suggested Angle
[from pick_dm_target's suggested_angle]
```

**Key rule:** DM history from OTHER members is NEVER included in any context type.

---

## 10. Key Architecture Decisions

1. **One Donny Brain** — Single Sonnet agent for all user-facing text. No sub-agent personas. Background Haiku workers are headless.

2. **Per-user DM sessions** — OpenClaw `dmScope: "per-channel-peer"`. Context loaded from shared DB, not from other sessions.

3. **Code-level pre-check gate** — Before cron calls the LLM, Python checks quiet hours, activity timestamps, DM counts. ~80% of checks cost $0.

4. **Email sensitivity pre-filter** — Pattern matching in `email_filter.py` drops medical/financial/legal emails BEFORE data reaches Haiku.

5. **Single tool call context assembly** — `gossip_context(type, member)` returns everything needed. No 3-4 separate tool calls.

6. **donny_memory in SQLite** — Rolling log of what Donny said. 30 most recent, auto-trim >48h. Concurrent-safe via WAL mode.

7. **Summaries replace dossiers** — Synthesizer generates structured summaries. Dossiers remain read-only for backward compat during transition.

8. **Play dumb about calendar** — Ask "what are you up to friday?" not "oh you've got dinner friday." Never reveal data sources.

9. **Discovery log anti-spam** — Max 1 DM per undiscovered user per 7 days.

10. **4-layer identity cascade** — discord_id → discord_username (case-insensitive) → nicknames → display_name.

11. **Prompt caching** — SOUL.md + skill at consistent prefix position for Anthropic cache read discount.

12. **Immediate synthesizer after OAuth** — Don't wait for 2h cron cycle after a member connects Google.

---

## 11. Testing Checklist

### Phase 1-2: Foundation
- [ ] `python -c "from gossip.db import init_db; init_db()"` creates DB with all tables
- [ ] New tables exist: `donny_memory`, `discovery_log`, `member_summaries`
- [ ] Members table has `nicknames` column
- [ ] `resolve_member("discord", username="TestUser")` matches case-insensitively
- [ ] Nickname matching works

### Phase 3-4: Engine
- [ ] `email_filter.filter_emails([...])` drops medical/financial emails
- [ ] `proactive.should_fire_idle_gossip()` returns `{"fire": False}` during quiet hours
- [ ] Synthesizer builds input without DM content

### Phase 5: Portal API
- [ ] `curl localhost:3000/api/gossip/idle-check` returns JSON
- [ ] `curl localhost:3000/api/gossip/context -d '{"type":"group"}'` returns context
- [ ] All API endpoints respond with correct JSON

### Phase 6-7: OpenClaw
- [ ] `openclaw doctor` passes
- [ ] OpenClaw connects to Discord
- [ ] @mentioning donny in Discord gets a response
- [ ] DM to donny gets a response
- [ ] DM sessions are isolated (DM person A, verify person B's DM has no cross-contamination)

### Phase 8-9: Cron + Personality
- [ ] Heartbeat fires after idle threshold — donny drops gossip in channel
- [ ] Donny never says "gossip", "intel", "dossier" etc.
- [ ] Donny keeps responses to 1-2 sentences
- [ ] DM check-in reaches a member
- [ ] Source sync updates dossiers/summaries

### End-to-End
- [ ] Open invite link in browser → see landing page
- [ ] Complete onboarding → member appears in DB
- [ ] Connect Google → deep sync triggers → summary generated
- [ ] Send messages in Discord → donny logs chat activity
- [ ] Wait for idle threshold → donny drops conversation starter
- [ ] @mention donny → context-aware response referencing members
- [ ] DM donny → isolated conversation with DM-specific context

---

## 12. Cost Model

| Component | Trigger | Model | Tokens | $/call | Calls/day | $/day |
|-----------|---------|-------|--------|--------|-----------|-------|
| Group chat response | @mention/name | Sonnet | ~8K eff | ~$0.04 | 5-10 | $0.20-0.40 |
| DM response | DM received | Sonnet | ~5K eff | ~$0.025 | 3-5 | $0.08-0.13 |
| Idle gossip drop | Heartbeat (30m) | Sonnet | ~8K eff | ~$0.04 | 2-4 | $0.08-0.16 |
| Proactive DM | Cron (6h) | Sonnet | ~5K eff | ~$0.025 | 2-4 | $0.05-0.10 |
| Synthesizer | Cron (2h) | Haiku | ~3K eff | ~$0.003 | 10 members x 4 | $0.12 |
| Source sync | Cron (2h) | None | 0 | $0 | 4 | $0 |
| Pre-check gate | Cron (30m) | None | 0 | $0 | ~38 | $0 |
| **TOTAL** | | | | | | **~$0.55-0.95/day** |

Estimated monthly: **$17-29/month** for a 5-15 member group.

---

## 13. Watch Items (From Architecture Review)

These are known issues to be aware of during implementation:

1. **OAuth token refresh** — Google testing mode tokens expire after 7 days. Add refresh logic + 401 handling to calendar.py and gmail.py. On refresh failure, mark source as disconnected and DM the member.

2. **Token encryption at rest** — OAuth tokens are plaintext in SQLite. Add Fernet encryption using `GOSSIP_TOKEN_KEY` env var before production use.

3. **Quiet hours use server timezone** — Fixed by adding `timezone` config field and using `ZoneInfo`. Make sure the gossip.yaml on the target machine has the correct timezone.

4. **Chat log rotation** — `data/chat/` files accumulate forever. Add a startup hook that deletes files older than 30 days.

5. **Context size at 30+ members** — Load only top-N most relevant summaries (recently active, mentioned in conversation, DM target) rather than all summaries.

6. **Crash recovery** — Synthesizer should write to temp file then atomic rename. Startup outreach should check dm_history before sending (idempotent).

7. **donny_memory cross-leakage** — Group-channel entries should only reference things said in group chat. DM-channel entries should only be loaded in that member's DM session.

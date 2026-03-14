# Removed from TypeScript Prototype

This documents what was removed from the original TypeScript gossip bot prototype and why, so we have the context for future reference.

## Original Prototype Location
`/Users/suryanarreddi/Downloads/gossip-project-extracted/gossip/`

---

## Removed: User Token Discord API (`src/discord/api.ts`)

**What it did:** Made raw REST API calls to Discord using a user account token (not a bot token). Fetched messages via `GET /channels/{id}/messages` and sent messages via `POST /channels/{id}/messages`.

**Why removed:** User tokens violate Discord's Terms of Service. Using a real user account as a bot risks the account being banned. The new codebase uses a proper Discord bot token via Hermes Agent's `discord.py` adapter, which connects via WebSocket (not polling) and is fully compliant with Discord's API.

**What replaced it:** Hermes Agent's `gateway/platforms/discord.py` — a 1900-line battle-tested Discord adapter using the `discord.py` library with proper bot authentication, reconnection handling, rate limiting, threading support, voice support, and reaction handling.

---

## Removed: Custom Polling Loop (`src/discord/monitor.ts`)

**What it did:** Polled Discord every 60 seconds via REST API, diffed messages against the last seen ID, logged new messages to markdown files, and tracked the last human message time for inactivity detection.

**Why removed:** Polling is inefficient and misses messages between intervals. Hermes Agent's Discord adapter uses WebSocket `on_message` events — the bot receives messages in real-time, zero delay.

**What replaced it:** Hermes gateway receives messages via WebSocket events. Chat logging and inactivity tracking are handled by our custom Hermes tools (`gossip_check_idle`, context builder) which read from the same data layer.

---

## Removed: Custom Cron/Interval System (`node-cron` + `setInterval` in `src/index.ts`)

**What it did:** Used `setInterval(60_000)` for polling and `node-cron` for email scanning schedule. The gossip check ran after every poll cycle.

**Why removed:** Hermes Agent provides a robust cron scheduler with file locking (prevents concurrent execution), delivery targets (can send results to specific Discord channels or Telegram chats), job persistence across restarts, and natural language schedule parsing.

**What replaced it:** Hermes cron system (`cron/scheduler.py`, `cron/jobs.py`). Gossip generation is a cron job that fires every 30 minutes, spawns an AIAgent that uses tools to check idle state, build context, and generate gossip.

**Note:** The original system logged "quiet hours" entries every 60 seconds (thousands of identical log lines). The new system checks only every 30 minutes via cron, and the idle check tool returns immediately during quiet hours without logging.

---

## Removed: Direct Anthropic API Calls (`src/gossip/engine.ts`)

**What it did:** Called `anthropic.messages.create()` directly with hardcoded system prompts and manually assembled context strings for gossip generation and mention replies.

**Why removed:** Hermes Agent manages the LLM interaction layer — model selection, provider routing, system prompt assembly (via SOUL.md), thinking support, and token management. Our gossip logic defines the personality via SOUL.md and SKILL.md instead of hardcoded prompt strings.

**What replaced it:** Hermes AIAgent with custom tools. The SOUL.md file defines the bot's personality. The SKILL.md defines behavior rules. Tools provide the gossip engine with data (dossiers, chat history, idle state). The agent generates gossip using its personality + the tool-provided context.

---

## Removed: `members.json`

**What it did:** Static JSON file mapping member names to Discord usernames, IDs, and email patterns.

**Why removed:** Member data now lives in SQLite with richer fields — portal tokens, OAuth tokens, multi-platform IDs (Discord + Telegram), pause state, group membership, timestamps. The onboarding portal manages member registration dynamically.

**What replaced it:** `members` table in SQLite (`data/gossip.db`), managed by the onboarding portal and accessible by the gossip engine.

---

## Removed: TypeScript / Node.js Runtime

**What it was:** The entire project was TypeScript compiled with `tsc`, run with `tsx` for development, using Node.js with `imapflow`, `node-cron`, `@anthropic-ai/sdk`, and `dotenv`.

**Why removed:** Hermes Agent is Python. To integrate with Hermes's tool registry, cron system, gateway adapters, and memory system, the gossip engine must be Python. All core logic has been ported from TypeScript to Python.

**What replaced it:** Python 3.11+ with FastAPI (portal), anthropic SDK (LLM), google-api-python-client (Calendar), and Hermes Agent (runtime).

---

## Removed: `package.json`, `tsconfig.json`, `package-lock.json`

**What they were:** Node.js package manifests and TypeScript configuration.

**Why removed:** Project is now Python. Dependencies are defined in `pyproject.toml`.

---

## Partially Retained: Markdown Context System

**Original:** `context/chat/*.md` (daily chat transcripts), `context/gossip_history.md`, `context/group.md`, `context/members/*.md` (dossiers), `context/logs/actions.jsonl` + `actions.md` + `decisions.md`.

**What changed:**
- Chat transcripts (`data/chat/*.md`) — **retained**, same format
- Dossiers (`data/dossiers/*.md`) — **retained**, same format, now editable via portal
- Group dynamics (`data/group.md`) — **retained**, same format
- Gossip history — **moved to SQLite** for queryability (dedup, feedback scores, timestamps)
- Action logs — **moved to SQLite** (`action_log` table) instead of append-only files
- Decisions log — **removed**, replaced by gossip_history with context_summary field

---

## Retained for Reference: Chat Transcripts and Gossip History

The original 10 days of chat transcripts (March 3-14, 2026) and 16 gossip drops are preserved in the original prototype directory. A migration script (`scripts/migrate_from_ts.py`, Phase 2) will import this historical data into the new SQLite database.

---

## Original Git History (4 commits)
```
435024f Initial commit                    (2026-03-01 15:43)
153e097 first                             (2026-03-01 16:20)
5768290 dash                              (2026-03-01 17:09)
666d0fb updated dashboard                 (2026-03-01 17:13)
```

The new project starts with a clean git history.

# Donny

An AI operative that embeds itself in a Discord friend group. It reads members' calendars and emails (with consent), builds dossiers, identifies contradictions and overlaps, and uses that information to create social dynamics — dropping observations, stirring conversations, and extracting intel through DMs.

Built on [OpenClaw](https://github.com/openclaw/openclaw) + Python. Runs locally. All data stays on your machine.

## How It Works

```
Google Calendar + Gmail ──→ Dossiers (per-member) ──→ Sabotage module finds
   (synced every 2h)         (filtered, compacted)      contradictions + overlaps
                                                              │
DM conversations ──→ Intel extraction ──→ Context assembly ──→ Donny speaks
   (ongoing)           (agent-driven)      (everything combined)   (group chat or DMs)
```

**Donny operates on three channels:**

1. **Group chat** — lurks in #general, responds to @mentions and "donny" keyword. Drops observations when chat goes quiet (heartbeat every 30min). References real data without revealing sources.

2. **DMs** — proactively reaches out to members every hour. Uses extraction tactics (leading questions, social proof, reciprocity) to learn things. What people say in DMs fuels group chat drops.

3. **Background** — syncs calendar/email every 2h, runs a sabotage module that cross-references everyone's data to find overlaps and contradictions, compacts dossiers to stay under 10k tokens per person.

## Architecture

```
gossip/
├── openclaw/                  # Agent workspace (OpenClaw reads these)
│   ├── SOUL.md                # Personality + sabotage playbook (13 tactics)
│   ├── SKILL.md               # Behavior rules + API tool reference
│   ├── HEARTBEAT.md           # Proactive drop logic (runs every 30min)
│   └── plugins/gossip/        # TypeScript plugin (tool bridge)
├── gossip/                    # Python core
│   ├── db.py                  # SQLite (members, DMs, memory, events)
│   ├── engine.py              # Context assembly (group/DM/proactive)
│   ├── sabotage.py            # Contradiction detector + calendar cross-ref
│   ├── compactor.py           # Dossier deduplication + size cap
│   ├── email_filter.py        # Drops spam/marketing/sensitive emails
│   ├── synthesizer.py         # Haiku-powered structured summaries
│   ├── proactive.py           # Pre-check gates for cron jobs
│   ├── sources/calendar.py    # Google Calendar sync + attendee extraction
│   └── sources/gmail.py       # Gmail sync (filtered)
├── portal/                    # FastAPI web app
│   ├── routes/tool_api.py     # 20+ JSON endpoints (tools for the agent)
│   ├── routes/dashboard.py    # Monitoring dashboard API
│   ├── routes/onboard.py      # Member onboarding flow
│   └── routes/oauth_google.py # Google OAuth + deep sync trigger
├── scripts/start.sh           # Launch script (portal + tunnel + OpenClaw)
├── config/.env                # API keys, bot tokens (gitignored)
└── data/                      # Runtime data (gitignored)
    ├── gossip.db              # SQLite database
    ├── dossiers/              # Per-member markdown files
    ├── chat/                  # Daily chat logs (auto-captured)
    ├── summaries/             # Synthesizer output
    └── group.md               # Group dynamics observations
```

## Quick Start

```bash
git clone https://github.com/kickingkeys/gossip.git
cd gossip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set up config/.env with your keys (see .env.example)
# Install OpenClaw: https://docs.openclaw.ai

# Configure OpenClaw for Discord
openclaw --profile gossip channels add --channel discord --token $DISCORD_BOT_TOKEN
openclaw --profile gossip config set agents.defaults.workspace "$PWD/openclaw"

# Launch
./scripts/start.sh
```

## Data Sources

| Source | How | What Donny gets |
|--------|-----|-----------------|
| Google Calendar | OAuth (members connect via onboarding link) | Events, locations, attendees, patterns |
| Gmail | OAuth (read-only, filtered for relevance) | Personal contacts, interests, plans |
| DM conversations | Ongoing — Donny initiates and responds | Secrets, opinions, contradictions |
| Group chat | Auto-captured every heartbeat via Discord API | Everything said in the channel |

Emails are filtered before reaching any LLM — medical, financial, legal, and marketing emails are dropped automatically.

## Cron Jobs

| Job | Frequency | What it does |
|-----|-----------|--------------|
| Heartbeat | 30min | Captures chat + DMs, checks idle state, drops observations |
| DM check-in | 1h | Picks a member to DM, extracts intel |
| Source sync | 2h | Syncs calendar + email, compacts dossiers |
| Synthesizer | 4h | Creates structured member summaries via Haiku |
| Discovery | 12h | Finds new Discord server members to onboard |

## Dashboard

Real-time monitoring at `http://localhost:3000/dashboard` (or via Cloudflare tunnel for public access).

Shows: member status, activity feed, DM conversations, Donny's memory, dossier contents, cron job status.

## Tech Stack

- **Agent runtime:** [OpenClaw](https://docs.openclaw.ai) (Node.js)
- **LLM:** Claude Opus (responses), Claude Haiku (synthesizer, reactions)
- **Data layer:** Python 3.11+ / FastAPI / SQLite
- **Platform:** Discord (via OpenClaw's discord.js adapter)
- **Tunnel:** Cloudflare (for OAuth callbacks + public dashboard)

## License

MIT

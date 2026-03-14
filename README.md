# Gossip

Open-source social utility bot that keeps group chats alive.

Members share context about their lives (calendar, social media, manual input), and the bot generates personalized, snarky gossip that keeps the group connected — even when everyone goes quiet.

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT). Runs locally on one person's machine. All data stays local.

## Quick Start

```bash
git clone https://github.com/[org]/gossip.git
cd gossip
./scripts/setup.sh
./scripts/start.sh
```

The setup wizard walks you through:
1. Naming your bot and picking a personality
2. Entering your Anthropic API key
3. Creating a Discord or Telegram bot
4. Optionally setting up Google Calendar integration
5. Creating your friend group and generating an invite link

## How It Works

```
Members share data ──→ Bot builds dossiers ──→ Chat goes quiet ──→ Bot drops gossip
     (calendar,              (per-member           (3+ hours          (1-3 sentences,
      social,                 markdown              idle)              in character)
      manual input)           files)
```

**The bot has two data paths:**

1. **Share with the bot's Google account** — members share their Google Calendar, Maps location, and forward emails to `gossipbot@gmail.com`. Zero OAuth, familiar UX.

2. **OAuth via web portal** — members connect Google, Instagram, or Twitter through the onboarding page for deeper access.

3. **Manual input** — members tell the bot stuff directly via the web portal or DMs. Always available, highest signal.

## Architecture

```
gossip/
├── vendor/hermes-agent/    # Bot runtime (Discord, Telegram, cron, memory)
├── gossip/                 # Core engine (context builder, dossiers, identity)
├── gossip_tools/           # Custom Hermes tools (idle check, gossip gen, etc.)
├── portal/                 # FastAPI onboarding web app
├── skills/gossip/          # Bot behavior definition (SKILL.md)
├── config/SOUL.md          # Bot personality
└── data/                   # Runtime data (SQLite + markdown, gitignored)
```

## Onboarding

### For the host (one person sets this up)
1. Run `./scripts/setup.sh` — interactive wizard, ~10 minutes
2. Add the bot to your Discord server or Telegram group
3. Share the invite link in the group chat

### For members (everyone else)
1. Open the invite link on your phone
2. Enter your name and platform username
3. Share your Google Calendar with the bot's email (optional)
4. Share your live location on Google Maps (optional)
5. Tell the bot something interesting (optional)
6. Done — visit your profile page anytime to see what the bot knows, edit it, or add more

## Data Sources

| Source | Method | What the bot gets |
|--------|--------|-------------------|
| Google Calendar | Share with bot's email or OAuth | Events, locations, travel plans |
| Google Maps | Share live location with bot's email | Real-time location |
| Gmail | Forward emails to bot's inbox | Email content for gossip fuel |
| Instagram | OAuth (Business/Creator accounts) | Posts, captions, geotags |
| Twitter/X | OAuth | Tweets, location metadata |
| Manual input | Web portal or DMs | Whatever you tell it |
| Chat | Bot monitors the group chat | Everything said in the group |

## Tech Stack

- **Runtime:** [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Python, MIT)
- **AI:** Anthropic Claude API
- **Portal:** FastAPI + Jinja2
- **Database:** SQLite (WAL mode)
- **Calendar:** Google Calendar API
- **Platforms:** Discord (discord.py), Telegram (python-telegram-bot)

## Configuration

- `gossip.yaml` — bot name, personality, thresholds, quiet hours
- `config/.env` — API keys, bot tokens, OAuth credentials
- `config/SOUL.md` — bot personality (editable markdown)
- `skills/gossip/SKILL.md` — behavior rules

## License

MIT

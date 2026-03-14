# Gossip — Open Source Social Utility Bot

> A locally-hosted AI bot that keeps group chats alive. Members share context about their lives, and the bot generates personalized, snarky gossip that keeps the group connected — even when everyone goes quiet.

## Positioning

**Moltbook** = bots performing for bots.
**Gossip** = a bot that makes humans connect with each other.

Gossip is a social utility with shared ownership. Everyone in the group opts in, feeds the bot context about their lives, and the bot uses that to generate authentic banter. It's not an assistant — it's a member of the group chat.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              MEMBER WEB PORTAL                  │
│      (one URL, works on any phone/browser)      │
│                                                 │
│  Google OAuth    Social OAuth     Manual Input   │
│  (Calendar,      (Instagram,     ("I just got   │
│   Gmail)          Twitter)        a new job")   │
│                                                 │
│  + Share with bot's Google account:             │
│    📍 Maps location  📅 Calendar  📧 Emails    │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │    GOSSIP ENGINE    │
            │  (Hermes Agent +    │
            │   custom skill)     │
            │                     │
            │  Runs locally on    │
            │  host's machine     │
            └──────────┬──────────┘
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
      ┌─────────┐ ┌────────┐ ┌───────┐
      │ Discord │ │Telegram│ │ Slack │  ...
      └─────────┘ └────────┘ └───────┘
```

**Key principle:** The chat platform is just where the bot talks. All data collection flows through the web portal + the bot's Google account. Medium-agnostic.

---

## Runtime: Hermes Agent (by Nous Research)

We build on top of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) rather than writing our own bot runtime. Hermes provides:

| Feature | Details |
|---------|---------|
| Platform adapters | Discord, Telegram, Slack, WhatsApp, Signal, Email — already built |
| Claude API | Direct Anthropic adapter with thinking support |
| Cron scheduling | Natural language ("every 2h") and cron expressions |
| Persistent memory | MEMORY.md, USER.md, session search across conversations |
| Skill system | Define bot behavior in a SKILL.md file — no code needed for personality |
| Image generation | fal.ai integration (Nano Banana / Flux for memes and visuals) |
| Browser automation | Playwright/Browserbase for scraping (Google Maps location) |
| Cross-platform messaging | Bot can read one platform and post to another |
| DM support | Bot can message individuals directly |
| Subagent delegation | Spawn parallel agents for different tasks |
| MCP support | Connect any external tool/data source |

**What we build on top:**
- Gossip skill (SKILL.md) — personality, behavior rules, gossip generation logic
- Onboarding web portal (FastAPI) — OAuth flows, member profiles, data connections
- Dossier system — member profiles built from all connected sources
- Group dynamics tracker — AI-maintained summary of relationships, jokes, vibes
- Data source connectors — Google Calendar API, Gmail API, Instagram, Twitter, Maps scraper

---

## Data Sources

### Two Paths for Members

**Path A — Share with the bot's Google account (zero OAuth, familiar UX):**
Members just share with an email address, the same way they'd share with a friend.

| Source | What members do | What the bot gets |
|--------|----------------|-------------------|
| Google Calendar | Share calendar with `gossipbot@gmail.com` | Event titles, times, locations, busy/free |
| Google Maps | Share live location with `gossipbot@gmail.com` | Real-time GPS coordinates |
| Gmail | Forward interesting emails to `gossipbot@gmail.com` | Email subjects, content, context |

**Path B — OAuth via the web portal (richer data, more sources):**
Members connect accounts through the onboarding page for deeper access.

| Source | OAuth Scope | What the bot gets |
|--------|------------|-------------------|
| Google Calendar | `calendar.readonly` | All calendar events (same as sharing, but automatic) |
| Gmail | `gmail.readonly` | Full inbox access — subjects, snippets, sender info |
| Instagram | Graph API (Business/Creator) | Posts, captions, geotags, timestamps |
| Twitter/X | API v2 (PKCE) | Tweets, retweets, location metadata |

**Path C — Manual input (always available):**
Members tell the bot things directly via the web portal or DMs.

### Feasibility Matrix

| Data Source | Method | Reliability | Cost | Notes |
|-------------|--------|-------------|------|-------|
| Calendar (sharing) | Bot's Google + Calendar API | Solid | Free | Clean API, well-documented |
| Calendar (OAuth) | Per-member OAuth | Solid | Free | Sensitive scope, manageable verification |
| Gmail (forwarding) | Bot's IMAP | Solid | Free | Already built in current codebase |
| Gmail (OAuth) | Per-member OAuth | Solid | Free | Restricted scope — needs security audit for hosted, fine for self-hosted |
| Location (Maps sharing) | Scraping bot's Maps page | Fragile | $7/mo (Workspace) | No API exists — headless browser scraping. Will need maintenance. |
| Location (inferred) | Calendar + social + chat NLP | Solid | Free | Passive — "Flight to Miami" in calendar = location context |
| Instagram | Graph API OAuth | Solid | Free | Requires Business/Creator account. App Review needed for >5 users. |
| Twitter/X | API v2 OAuth | Solid | $5-20/mo | Credit-based pricing, no free read tier |
| Manual input | Web portal + DMs | Bulletproof | Free | Highest signal, zero dependencies |
| Chat monitoring | Discord/Telegram bot API | Solid | Free | Hermes handles this out of the box |
| Image generation | fal.ai (Nano Banana 2) | Solid | ~$0.08/image | Great text rendering for memes. Flux Schnell at $0.003 for volume. |

### Location: The Full Picture

Live GPS from Google Maps scraping is the flashiest but most fragile source. Location is actually best understood as a **composite signal** from multiple sources:

- **Google Maps sharing** → live GPS (when scraper works)
- **Calendar events** → "Flight to Miami", "Dinner at XYZ Restaurant, Brooklyn"
- **Instagram geotags** → where they posted from
- **Twitter location** → tweet metadata
- **Chat messages** → "just landed in LA" (NLP extraction)
- **Manual input** → "I'm in Tokyo this week"

When the Maps scraper is healthy, the bot has precise real-time location. When it breaks, the bot still has strong location context from everything else. Graceful degradation.

---

## Bot Behavior

### When It Speaks
- **Chat idle 3+ hours** → drops a gossip message (1-3 sentences)
- **@mentioned** → replies with context-aware sass
- **Interesting event detected** → weaves it into conversation naturally (someone's calendar shows a flight, someone posted on Instagram, etc.)
- **Quiet hours (11pm-9am)** → stays silent unless something is too good to hold

### When It DMs Individuals
- "Hey, you haven't said anything in the group in 5 days. Everything good?"
- "Saw you have a flight tomorrow — safe travels"
- "Your Instagram post got a lot of engagement, the group might want to hear about it"
- Weekly digest: "Here's what you missed this week"

### When It Generates Images
- Memes about group dynamics
- Birthday/milestone graphics (auto-detected from calendar)
- Weekly recap visuals
- Roast images (when someone asks to be roasted)

### Privacy Rules
- DMs are private — bot never reveals what someone told it in DMs unless they say "share this"
- Members can see and edit their own dossier at any time via the web portal
- Members can pause or delete their data with one click
- Bot never reveals it reads emails/calendars — acts like it "heard" things

### Personality (defined in SKILL.md)
- Casual, lowercase, uses "ngl", "lmao", "..."
- Teasing but never mean or hurtful
- Knows things but never reveals sources
- 1-3 sentences max
- Never repeats gossip it's already dropped
- Part of the friend group, not a bot

---

## Onboarding: Layer 1 — Host Setup

One person in the friend group sets this up on their machine. Everything runs locally — no data leaves their computer.

### Prerequisites
- A computer that stays on (or a cheap VPS/Raspberry Pi)
- Node.js 18+ and Python 3.11+
- An Anthropic API key ($5-20/month depending on usage)

### Step 1: Clone and Install

```bash
git clone https://github.com/[org]/gossip.git
cd gossip
./setup.sh
```

The setup script installs dependencies (Hermes Agent, Python packages, Node modules) and launches an interactive setup wizard.

### Step 2: Create the Bot's Google Account

The wizard walks you through this:

1. Create a new Google account (e.g., `donnybotgossip@gmail.com`)
   - Or use a Google Workspace account ($7/mo) for better stability
2. Enable the Google Calendar API in Google Cloud Console
   - Create a new project
   - Enable "Google Calendar API"
   - Create OAuth 2.0 credentials (for the bot's own account)
   - Download the credentials JSON
3. Authenticate the bot's Google account (one-time browser OAuth flow)

The wizard provides step-by-step links and instructions for each of these. It takes ~10 minutes.

**What this unlocks:** The bot can now read any calendar shared with it via the Google Calendar API, and receive forwarded emails via IMAP. Location sharing via Maps will also target this account.

### Step 3: Create a Chat Platform Bot

The wizard asks which platform(s) you want:

**Discord:**
1. Go to [discord.com/developers](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" tab → create bot → copy token
4. Go to "OAuth2" → generate invite URL with these permissions:
   - Read Messages, Send Messages, Read Message History, Embed Links, Attach Files
5. Paste the token into the wizard

**Telegram:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`, pick a name and username
3. Copy the token BotFather gives you
4. Paste into the wizard

**Both?** You can connect multiple platforms. The bot will monitor and post to all of them.

### Step 4: Configure the Bot

The wizard asks:
- **Bot name**: what should it call itself? (e.g., "donnybotgossip")
- **Personality vibe**: pick a preset or write custom instructions
  - Messy gossip queen (default — casual, "ngl", "lmao", teasing)
  - Chill observer (laid back, dry humor)
  - Chaotic agent of chaos (unhinged energy)
  - Custom (write your own SKILL.md)
- **Anthropic API key**: for gossip generation (Claude Sonnet by default)
- **Inactivity threshold**: how long before the bot drops gossip (default: 3 hours)
- **Quiet hours**: when the bot should shut up (default: 11pm-9am)

### Step 5: Optional — Set Up OAuth for Member Connections

If you want members to be able to connect Instagram, Twitter, or do Google OAuth (beyond just sharing):

**Google OAuth (for members):**
- In the same Google Cloud project, add OAuth consent screen
- Add scopes: `calendar.readonly`, optionally `gmail.readonly`
- Add redirect URI: `http://localhost:3000/auth/google/callback`
- Copy Client ID and Client Secret into the wizard

**Instagram:**
- Create a Meta App at [developers.facebook.com](https://developers.facebook.com)
- Add Instagram Graph API product
- Set up OAuth redirect: `http://localhost:3000/auth/instagram/callback`
- Copy App ID and App Secret into the wizard
- Note: members need Business/Creator accounts (free to switch)

**Twitter/X:**
- Create a project at [developer.x.com](https://developer.x.com)
- Set up OAuth 2.0 with PKCE
- Set redirect URI: `http://localhost:3000/auth/twitter/callback`
- Copy Client ID into the wizard
- Note: reading tweets costs money (credit-based)

All of these are optional. The bot works with zero OAuth — sharing + forwarding + manual input are enough.

### Step 6: Start the Bot

```bash
./start.sh
```

This launches:
1. **Hermes Agent** — the bot runtime, connects to Discord/Telegram, starts monitoring
2. **Onboarding Portal** — a local web server at `http://localhost:3000` (or configured URL)
3. **Data sync cron** — periodically pulls from connected Google Calendar, email, social accounts

The bot is now running. Time for Layer 2.

---

## Onboarding: Layer 2 — Adding to the Group Chat

### Step 1: Bot Joins the Chat

**Discord:** The host clicks the OAuth invite URL generated during setup. Selects their server. The bot appears in the server's member list.

**Telegram:** The host adds the bot to their group chat via the group settings → Add Member → search for the bot's username.

### Step 2: Bot Introduces Itself

The host sends a trigger message (or the bot auto-introduces on first join):

```
/gossip start
```

The bot posts its introduction:

> hey everyone, i'm donnybotgossip 👋
>
> i'm here to keep this chat alive and talk shit (lovingly). i'll drop
> gossip when things get quiet, respond when you tag me, and generally
> be a menace in the best way possible.
>
> but i need to get to know you first. everyone tap this link to set up
> your profile — connect whatever you're comfortable sharing and i'll
> start paying attention:
>
> 🔗 **http://[host-ip]:3000/join/abc123**
>
> the more you share, the better the gossip. or don't share anything
> and i'll just roast you based on what you say in here lmao

The invite link is unique to this group. It contains a token that ties members to this specific bot instance.

### Step 3: Members Open the Invite Link

Each member opens the link on their phone or computer. They see a clean, mobile-first onboarding page:

```
╔══════════════════════════════════════╗
║                                      ║
║   donnybotgossip wants to            ║
║   get to know you                    ║
║                                      ║
║   ┌──────────────────────────────┐   ║
║   │  What's your name?           │   ║
║   │  [________________________]  │   ║
║   │                              │   ║
║   │  Which platform are you on?  │   ║
║   │  (○) Discord                 │   ║
║   │  (○) Telegram                │   ║
║   │  (○) Both                    │   ║
║   │                              │   ║
║   │  Your username:              │   ║
║   │  [________________________]  │   ║
║   └──────────────────────────────┘   ║
║                                      ║
║          [ Continue → ]              ║
║                                      ║
╚══════════════════════════════════════╝
```

### Step 4: Connect Data Sources

After basic info, the member sees the connection page:

```
╔══════════════════════════════════════╗
║                                      ║
║   Share with donnybotgossip's        ║
║   Google account                     ║
║   (donnybotgossip@gmail.com)         ║
║                                      ║
║   These are like sharing with a      ║
║   friend — no app permissions needed ║
║                                      ║
║   📅 Share your Google Calendar      ║
║      [ Show me how ]                 ║
║      Event titles, times, locations  ║
║                                      ║
║   📍 Share your live location        ║
║      [ Show me how ]                 ║
║      Real-time location on Maps      ║
║                                      ║
║   📧 Forward emails                  ║
║      [ Show me how ]                 ║
║      Forward interesting stuff to    ║
║      donnybotgossip@gmail.com        ║
║                                      ║
║   ─────── or connect directly ───────║
║                                      ║
║   [ 🔗 Connect Google (OAuth) ]      ║
║      Calendar + Gmail access         ║
║                                      ║
║   [ 📸 Connect Instagram ]           ║
║      Your posts and captions         ║
║                                      ║
║   [ 🐦 Connect Twitter/X ]          ║
║      Your tweets                     ║
║                                      ║
╚══════════════════════════════════════╝
```

The "Show me how" buttons expand inline instructions with screenshots:

**Share your Google Calendar:**
> 1. Open Google Calendar on your phone or computer
> 2. Go to Settings → [Your calendar] → "Share with specific people"
> 3. Add `donnybotgossip@gmail.com`
> 4. Select "See all event details"
> 5. Tap Save
>
> That's it — the bot can now see your calendar.

**Share your live location:**
> 1. Open Google Maps on your phone
> 2. Tap your profile picture → "Location sharing"
> 3. Tap "Share your real-time location"
> 4. Select "Until you turn it off"
> 5. Share with `donnybotgossip@gmail.com`
>
> The bot now knows where you are (city-level, not exact address).

**Connect Google (OAuth):**
Redirects to Google's standard OAuth consent screen. One click. Returns to the portal.

**Connect Instagram:**
Redirects to Instagram authorization. Returns to the portal.

**Connect Twitter/X:**
Redirects to Twitter OAuth. Returns to the portal.

### Step 5: Manual Input (Always Available)

At the bottom of the connection page (and always accessible from the member's profile):

```
╔══════════════════════════════════════╗
║                                      ║
║   Tell me something                  ║
║                                      ║
║   Drop facts, vibes, whatever.       ║
║   The bot uses this as gossip fuel.  ║
║                                      ║
║   ┌──────────────────────────────┐   ║
║   │                              │   ║
║   │                              │   ║
║   │                              │   ║
║   └──────────────────────────────┘   ║
║                                      ║
║   Examples:                          ║
║   • "I'm interviewing at Google"     ║
║   • "I've been into bouldering"      ║
║   • "Roast Osman about his 3am      ║
║     existential crisis"              ║
║                                      ║
║          [ Submit ]                  ║
║                                      ║
╚══════════════════════════════════════╝
```

### Step 6: Member Profile (Ongoing)

After onboarding, each member has a persistent profile page at `http://[host]:3000/me/[token]`:

```
╔══════════════════════════════════════╗
║                                      ║
║   Your Profile — Surya               ║
║   @kickingkeys on Discord            ║
║                                      ║
║   ── Connected Sources ──            ║
║   ✅ Google Calendar    [Disconnect] ║
║   ✅ Live Location      [Disconnect] ║
║   ✅ Instagram          [Disconnect] ║
║   ⬚  Twitter            [Connect]   ║
║   ✅ Email forwarding   (always on)  ║
║                                      ║
║   ── What the bot knows about you ── ║
║                                      ║
║   • Has a thesis deadline coming up  ║
║   • Was in Miami last week           ║
║   • Posted bouldering pics on IG     ║
║   • Asked the bot for weather once   ║
║   • "The email collector"            ║
║                                      ║
║   [ Edit ] [ Delete item ] [ Pause ] ║
║                                      ║
║   ── Tell me something new ──        ║
║   [________________________________] ║
║   [ Submit ]                         ║
║                                      ║
║   ── Settings ──                     ║
║   [ 🔴 Pause all data ]             ║
║   [ 🗑️ Delete all my data ]          ║
║                                      ║
╚══════════════════════════════════════╝
```

Members can visit this anytime to:
- See exactly what the bot knows (full transparency)
- Delete specific facts they don't want used
- Pause data collection temporarily
- Add new manual input
- Connect or disconnect sources

---

## What Happens After Onboarding

Once members are connected, the bot runs autonomously:

### Continuous Loop (via Hermes)
1. **Every 60s** — monitors the group chat, logs messages, tracks who said what
2. **Every 30min** — pulls fresh data from connected sources (calendar events, new social posts, location updates)
3. **Every 60s** — checks if chat has been idle past the threshold
4. **When idle** — builds context from all dossiers + recent chat + group dynamics → calls Claude → posts gossip
5. **When @mentioned** — generates a contextual reply
6. **When interesting event detected** — proactively drops a comment ("someone's got a flight to miami tomorrow...")

### Gossip Quality Improves Over Time
- More connected sources = richer context = better gossip
- The group dynamics summary evolves as the bot observes more interactions
- Running jokes and references accumulate naturally
- The bot learns what lands well (members can react to gossip with 👍/👎)

---

## Shared Ownership Features

What makes Gossip different from a regular bot:

1. **Everyone can configure** — not just the host. Any member can suggest personality changes, adjust their own data, or tell the bot to chill
2. **Transparent dossiers** — every member can see and edit what the bot knows about them
3. **Democratic personality** — the group can vote on the bot's vibe (future: in-app polls)
4. **Gossip feedback** — react to gossip with 👍/👎 to train the bot's taste
5. **No single owner** — if the host goes down, any member can take over hosting with an export/import flow

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Bot runtime | Hermes Agent (Python, MIT license) |
| AI | Anthropic Claude API (Sonnet for gossip, Opus for complex reasoning) |
| Image generation | fal.ai — Nano Banana 2 ($0.08/img) or Flux Schnell ($0.003/img) |
| Onboarding portal | FastAPI (Python) + Jinja2 templates or simple React |
| Database | SQLite (local, zero-config) |
| OAuth | Google (Calendar, Gmail), Instagram Graph API, Twitter/X API v2 |
| Calendar API | Google Calendar API (for reading shared calendars) |
| Location scraping | Playwright headless browser (for Google Maps location sharing) |
| Email | IMAP (for reading bot's Gmail inbox) |
| Scheduling | Hermes built-in cron |
| Chat platforms | Discord (discord.py), Telegram (python-telegram-bot) via Hermes gateway |

---

## File Structure

```
gossip/
├── hermes-agent/              # Submodule or fork of NousResearch/hermes-agent
│
├── skill/
│   └── SKILL.md               # Gossip bot personality and behavior
│
├── gossip/                    # Our custom gossip engine
│   ├── engine.py              # Context builder, gossip generator
│   ├── dossiers.py            # Member profile management
│   ├── dynamics.py            # Group dynamics tracker
│   ├── sources/               # Data source connectors
│   │   ├── calendar.py        # Google Calendar API reader
│   │   ├── gmail.py           # IMAP inbox scanner
│   │   ├── instagram.py       # Instagram Graph API
│   │   ├── twitter.py         # X API v2
│   │   ├── location.py        # Google Maps scraper
│   │   └── manual.py          # Manual input handler
│   └── media.py               # Image/meme generation
│
├── portal/                    # Onboarding web app
│   ├── app.py                 # FastAPI server
│   ├── oauth/                 # OAuth flow handlers
│   │   ├── google.py
│   │   ├── instagram.py
│   │   └── twitter.py
│   ├── templates/             # HTML pages
│   │   ├── invite.html        # Group invite landing
│   │   ├── onboard.html       # Data source connection
│   │   ├── profile.html       # Member profile / dossier view
│   │   └── setup.html         # Host setup wizard
│   └── static/                # CSS, images
│
├── data/                      # Local data (gitignored)
│   ├── gossip.db              # SQLite — members, tokens, history
│   ├── members/               # Per-member dossier markdown files
│   ├── chat/                  # Daily chat transcripts
│   └── group.md               # Group dynamics summary
│
├── SOUL.md                    # Hermes personality file
├── config.yaml                # All configuration
├── setup.sh                   # Interactive setup wizard
├── start.sh                   # Launch everything
├── docker-compose.yml         # Alternative: containerized deployment
├── .env.example               # Template for secrets
└── README.md                  # Quick start guide
```

---

## Future Additions (Post-MVP)

- **Voice channel participation** — Hermes Discord adapter already supports voice. Bot could listen and chime in verbally.
- **WhatsApp support** — via unofficial Baileys bridge (Hermes has this adapter). Fragile but works.
- **iMessage** — via BlueBubbles or Beeper bridge. Hard but possible.
- **Gossip newsletter** — weekly email digest sent to all members.
- **Cross-group gossip** — if someone is in multiple Gossip groups, the bot could (with permission) cross-reference.
- **Bot-to-bot** — if two friend groups have Gossip bots that share a member, the bots could gossip to each other.
- **Mobile PWA** — upgrade the web portal to a proper PWA with push notifications.
- **Hosted version** — `gossip.dev` for one-click deployment. Free tier: 1 bot, 5 members. Pro: $5/mo.

# Gossip Bot — Outstanding Tasks

## Done
- [x] Session traces (per-session JSON in data/logs/traces/)
- [x] Location tracking tools + DB + map page
- [x] Group dynamics auto-maintenance
- [x] Switch to Haiku model
- [x] Token reduction via platform_toolsets (44 → 20 tools)
- [x] Image generation via Google Gemini (gossip_generate_image)
- [x] Gmail sync code (gossip/sources/gmail.py)
- [x] Source sync tool + cron job (gossip_sync_sources, every 60 min)
- [x] Google OAuth credentials configured
- [x] Onboarding redesign (step-by-step, Google OAuth first)
- [x] Bot DM capability (tested — sent image to kickingkeys)
- [x] Cloudflare tunnel for public access
- [x] Portal + bot fully working on Discord
- [x] Clean member data for fresh start
- [x] Detective/breadcrumb refactor — stripped to 13 tools, 4 slash commands, agent-first model
- [x] DM infrastructure — dm_history table, DM check-in tools, 6h cron job
- [x] DM continuity — inbound DMs logged to dm_history, DM conversation history in context
- [x] Deep onboarding sync — 30 days email + 60 days calendar pulled on first OAuth connect
- [x] Auto-onboarding outreach — gossip_discover_members tool + 12h cron scans server, DMs new people
- [x] Removed redundant tools (gossip_list_members, gossip_get_member, gossip_member_locations, gossip_read_dynamics)
- [x] Removed 8 slash commands, kept 4 (/onboard, /reset, /stop, /sethome)
- [x] Removed browser-vision location cron (location-check-01)
- [x] SKILL.md rewritten as behavioral guide (natural tone, not spy/detective)
- [x] SOUL.md updated with natural friend personality (not "The Provocateur")
- [x] Investigation Notes + Recent DM Conversations sections in gossip context

## Come Back To Later
- [ ] **Permanent hosting** — Deploy to Fly.io/Railway for 24/7 uptime without laptop open. Eliminates rotating tunnel URLs.
- [ ] **Location tracking activation** — Members share Google Maps location with gossip.bot.tea@gmail.com, install agent-browser, re-add location cron job
- [ ] **Progressive tool discovery** — Send fewer tool schemas upfront, discover on demand. Low priority since platform_toolsets already cut tokens significantly.
- [ ] **Google OAuth app — add domain** — When on permanent hosting, add the fixed URL to OAuth redirect URIs so it never needs updating

## Key URLs (current session)
- Onboarding: https://diffs-organizational-coral-nested.trycloudflare.com/join/9e593496e451
- Map: https://diffs-organizational-coral-nested.trycloudflare.com/map/9e593496e451
- OAuth callback: https://diffs-organizational-coral-nested.trycloudflare.com/auth/google/callback
- Local: http://localhost:3000

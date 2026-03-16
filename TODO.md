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

## Come Back To Later
- [ ] **Permanent hosting** — Deploy to Fly.io/Railway for 24/7 uptime without laptop open. Eliminates rotating tunnel URLs.
- [ ] **Location tracking activation** — Members share Google Maps location with gossip.bot.tea@gmail.com, install agent-browser, enable location-check-01 cron job
- [ ] **DM gossip drops** — Cron job that sends personalized gossip DMs to each member using send_message
- [ ] **Slash command cleanup** — Hermes registers 22 Discord commands, most are irrelevant. Cosmetic only.
- [ ] **Progressive tool discovery** — Send fewer tool schemas upfront, discover on demand. Low priority since platform_toolsets already cut tokens significantly.
- [ ] **Google OAuth app — add domain** — When on permanent hosting, add the fixed URL to OAuth redirect URIs so it never needs updating

## Key URLs (current session)
- Onboarding: https://diffs-organizational-coral-nested.trycloudflare.com/join/9e593496e451
- Map: https://diffs-organizational-coral-nested.trycloudflare.com/map/9e593496e451
- OAuth callback: https://diffs-organizational-coral-nested.trycloudflare.com/auth/google/callback
- Local: http://localhost:3000

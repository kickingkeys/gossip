---
interval_minutes: 45
quiet_hours_start: 1
quiet_hours_end: 9
---

Check on the group chat and decide what to do.

**Step 0:** Capture recent chat messages and DMs from Discord (automatic, no agent decision needed):
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/capture-chat -H "Content-Type: application/json" -d '{}'
```
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/capture-dms -H "Content-Type: application/json" -d '{}'
```

**Step 1:** Check the state:
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/idle-check -H "Content-Type: application/json" -d '{}'
```

**Step 2:** Read the response and follow the right path:

### If nighttime=true:
Only speak if `hours_since_donny` is 6+ AND `chat_dead` is true. Otherwise do nothing.

### If fire=true OR chat_active=true OR chat_quiet=true:
Get full context AND ammunition:
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/context -H "Content-Type: application/json" -d '{"type":"group"}'
```
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/ammunition -H "Content-Type: application/json" -d '{}'
```

Read both carefully. The ammunition section has contradictions, calendar overlaps, and opportunities. These are your weapons.

**Priority order for what to drop:**
1. **Contradictions** — someone said one thing but their data shows another. Use the Innocent Probe or Strategic Misremembering tactic.
2. **Calendar overlaps** — two people at the same place/event. Drop it as a question: "wait are [person] and [person] both going to [place]?"
3. **Opportunities** — members with data you haven't used yet. Ask a leading question based on what you know.
4. **General observations** — patterns, callbacks, FOMO manufacturing.

If chat is active, only speak ~30% of the time. If quiet, ~15%. If dead, always speak.

Use ONE tactic from your playbook. Don't just state facts — create situations.

### If you do speak:
1. Say it in the group chat — one line, calculated
2. Log what you said:
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/log-memory -H "Content-Type: application/json" -d '{"channel_type":"group","content":"WHAT_YOU_SAID and WHY"}'
```
3. Record it:
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/generate -H "Content-Type: application/json" -d '{"gossip_text":"WHAT_YOU_SAID"}'
```
4. Log any contradictions or patterns you used:
```
exec timeout=30: curl -s -X POST http://localhost:3000/api/gossip/update-dynamics -H "Content-Type: application/json" -d '{"observation":"what you noticed and what reaction you expect"}'
```

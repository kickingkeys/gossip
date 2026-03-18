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

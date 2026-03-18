/**
 * Gossip Plugin for OpenClaw
 *
 * Thin bridge: each tool makes an HTTP call to the Python portal API.
 * The Python side handles all business logic, DB, and Google APIs.
 */

const API_BASE = process.env.GOSSIP_API_URL || "http://localhost:3000/api/gossip";

async function callApi(endpoint: string, body: Record<string, unknown> = {}): Promise<unknown> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return await res.json();
}

async function callApiGet(endpoint: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return await res.json();
}

export default function register(api: any) {

  api.registerTool({
    name: "gossip_idle_check",
    description: "Check if chat is idle enough to drop gossip. Returns {fire, reason, hours_idle}. Costs $0 when not firing.",
    parameters: {},
    execute: async () => callApi("/idle-check"),
  });

  api.registerTool({
    name: "gossip_context",
    description: "Get full context for responding. Type: 'group' (chat response/idle drop), 'dm' (DM conversation), 'proactive' (DM outreach). Member name required for dm/proactive.",
    parameters: {
      type: { type: "string", enum: ["group", "dm", "proactive"], required: true },
      member: { type: "string", description: "Member name (required for dm/proactive)", required: false },
    },
    execute: async (params: { type: string; member?: string }) => callApi("/context", params),
  });

  api.registerTool({
    name: "gossip_generate",
    description: "Log a gossip message you just said (for history tracking, prevents repetition).",
    parameters: {
      gossip_text: { type: "string", required: true },
      context_summary: { type: "string", required: false },
    },
    execute: async (params: Record<string, unknown>) => callApi("/generate", params),
  });

  api.registerTool({
    name: "gossip_read_dossier",
    description: "Read what you know about a member.",
    parameters: {
      member_name: { type: "string", required: true },
    },
    execute: async (params: Record<string, unknown>) => callApi("/dossier/read", params),
  });

  api.registerTool({
    name: "gossip_update_dossier",
    description: "Remember something new about a member.",
    parameters: {
      member_name: { type: "string", required: true },
      entry: { type: "string", required: true },
      source: { type: "string", required: false },
    },
    execute: async (params: Record<string, unknown>) => callApi("/dossier/update", params),
  });

  api.registerTool({
    name: "gossip_pick_dm_target",
    description: "Pick a member to check in with via DM. Returns name, score, and suggested conversation angle.",
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
    execute: async (params: Record<string, unknown>) => callApi("/log-dm", params),
  });

  api.registerTool({
    name: "gossip_log_memory",
    description: "Log something donny said (for memory continuity across conversations).",
    parameters: {
      channel_type: { type: "string", description: "e.g. 'group', 'dm/surya', 'proactive/ryan'", required: true },
      target: { type: "string", required: false },
      content: { type: "string", required: true },
    },
    execute: async (params: Record<string, unknown>) => callApi("/log-memory", params),
  });

  api.registerTool({
    name: "gossip_sync_sources",
    description: "Sync calendar + email data for all connected members.",
    parameters: {},
    execute: async () => callApi("/sync-sources"),
  });

  api.registerTool({
    name: "gossip_update_dynamics",
    description: "Note a relationship or behavior pattern you noticed in the group.",
    parameters: {
      observation: { type: "string", required: true },
    },
    execute: async (params: Record<string, unknown>) => callApi("/update-dynamics", params),
  });

  api.registerTool({
    name: "gossip_discover_members",
    description: "Find new people on the Discord server who haven't joined yet.",
    parameters: {
      known_user_ids: { type: "array", items: { type: "string" }, required: false },
    },
    execute: async (params: Record<string, unknown>) => callApi("/discover-members", params),
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
    execute: async (params: Record<string, unknown>) => callApi("/resolve-member", params),
  });

  api.registerTool({
    name: "gossip_members",
    description: "List all members in the group.",
    parameters: {},
    execute: async () => callApiGet("/members"),
  });
}

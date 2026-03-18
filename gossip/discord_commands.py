"""Discord adapter patches for Gossip Bot.

Single handler that gates messages, logs chat, triggers responses
only on @mentions/DMs/"donny" keyword, and fires startup outreach.
"""

import os
import threading
from pathlib import Path

import discord

_project_root = Path(__file__).resolve().parent.parent

# #welcome channel — the ONLY channel the bot actively participates in
HOME_CHANNEL_ID = "1483199527581253692"


def register_gossip_commands(adapter) -> None:
    """Register minimal slash commands, replacing Hermes defaults."""
    if not adapter._client:
        return

    tree = adapter._client.tree

    @tree.command(name="stop", description="Stop Donny if he's going off")
    async def slash_stop(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/stop", "ok ok i'll stop")


# ── Discord REST helpers ────────────────────────────────────────────────


def _get_discord_bot_token() -> str | None:
    """Get the Discord bot token from env or .env file."""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        try:
            from dotenv import dotenv_values
            env = dotenv_values(_project_root / "config" / ".env")
            token = env.get("DISCORD_BOT_TOKEN")
        except Exception:
            pass
    return token


def _get_public_url() -> str:
    """Get the public portal URL, re-reading .env for tunnel URL."""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(_project_root / "config" / ".env")
        url = env.get("PORTAL_PUBLIC_URL", "").rstrip("/")
        if url:
            return url
    except Exception:
        pass
    return os.getenv("PORTAL_PUBLIC_URL", "http://localhost:3000").rstrip("/")


def _send_discord_dm(bot_token: str, user_id: str, message: str) -> dict:
    """Send a DM to a Discord user via REST API."""
    import requests
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    dm_resp = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        headers=headers,
        json={"recipient_id": user_id},
        timeout=10,
    ).json()

    dm_channel_id = dm_resp.get("id")
    if not dm_channel_id:
        raise Exception(f"Can't open DM channel: {dm_resp}")

    send_resp = requests.post(
        f"https://discord.com/api/v10/channels/{dm_channel_id}/messages",
        headers=headers,
        json={"content": message},
        timeout=10,
    )
    send_resp.raise_for_status()

    return {"dm_channel_id": dm_channel_id, "message_id": send_resp.json().get("id")}


def _fetch_guild_members() -> list[dict]:
    """Fetch all members from the bot's Discord guilds."""
    import requests
    token = _get_discord_bot_token()
    if not token:
        return []

    headers = {"Authorization": f"Bot {token}"}

    guilds = requests.get(
        "https://discord.com/api/v10/users/@me/guilds",
        headers=headers, timeout=10,
    ).json()

    all_members = []
    for guild in guilds:
        try:
            members = requests.get(
                f"https://discord.com/api/v10/guilds/{guild['id']}/members?limit=1000",
                headers=headers, timeout=15,
            ).json()
            if isinstance(members, list):
                all_members.extend(members)
        except Exception:
            pass

    return all_members


# ── Startup outreach ────────────────────────────────────────────────────


def _run_startup_outreach():
    """DM every member who hasn't connected Google with an intro + onboarding link."""
    import time
    time.sleep(10)

    try:
        from gossip.db import (
            get_default_group, get_members_by_group, get_oauth_token,
            get_last_dm, log_dm, update_member,
        )
        from gossip.config import load_config
        load_config()

        group = get_default_group()
        if not group:
            print("[gossip] Startup outreach: no group configured", flush=True)
            return

        bot_token = _get_discord_bot_token()
        if not bot_token:
            print("[gossip] Startup outreach: no DISCORD_BOT_TOKEN", flush=True)
            return

        base_url = _get_public_url()
        onboarding_url = f"{base_url}/join/{group['invite_token']}"

        # Fetch guild members ONCE and build lookup maps
        guild_members = _fetch_guild_members()
        username_to_id = {}
        globalname_to_id = {}
        for gm in guild_members:
            user = gm.get("user", {})
            if user.get("bot"):
                continue
            uid = user.get("id")
            if user.get("username"):
                username_to_id[user["username"].lower()] = uid
            if user.get("global_name"):
                globalname_to_id[user["global_name"].lower()] = uid

        print(f"[gossip] Startup outreach: found {len(username_to_id)} server members", flush=True)

        members = get_members_by_group(group["id"])
        sent = 0

        for m in members:
            if get_oauth_token(m["id"], "google"):
                continue
            if get_last_dm(m["id"]):
                continue

            discord_id = m.get("discord_id")
            if not discord_id:
                uname = (m.get("discord_username") or "").lower()
                dname = m["display_name"].lower()
                discord_id = username_to_id.get(uname) or globalname_to_id.get(dname) or globalname_to_id.get(uname)

            if not discord_id:
                print(f"[gossip] Startup outreach: can't resolve {m['display_name']} (@{m.get('discord_username')})", flush=True)
                continue

            try:
                msg = (
                    f"hey i'm donny, i'm in the group chat. "
                    f"link your google here if you want: {onboarding_url}"
                )
                result = _send_discord_dm(bot_token, discord_id, msg)
                update_member(m["id"], discord_id=discord_id, discord_dm_channel_id=result["dm_channel_id"])
                log_dm(m["id"], msg, direction="outbound")
                sent += 1
                print(f"[gossip] Startup outreach: DM'd {m['display_name']}", flush=True)
                time.sleep(2)
            except Exception as e:
                print(f"[gossip] Startup outreach failed for {m['display_name']}: {e}", flush=True)

        print(f"[gossip] Startup outreach complete: {sent} DMs sent", flush=True)

    except Exception as e:
        print(f"[gossip] Startup outreach error: {e}", flush=True)


# ── Emoji reactions (Haiku) ─────────────────────────────────────────────


async def _maybe_react(message):
    """Cheap Haiku call to decide whether to emoji-react to a message."""
    content = message.content or ""
    if len(content) < 5 or message.author.bot:
        return

    try:
        from gossip.identity import resolve_member
        member = resolve_member(platform="discord", user_id=str(message.author.id))
        username = member["display_name"] if member else message.author.display_name

        from gossip.dossiers import read_dossier
        from gossip.engine import get_group_dynamics

        dossier = read_dossier(username) if member else ""
        dynamics = get_group_dynamics()

        import anthropic
        client_api = anthropic.Anthropic()

        response = client_api.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    f"You are Donny, a nosy friend in a group chat. "
                    f"Someone named {username} just said: \"{content}\"\n\n"
                    f"What you know about them: {dossier[:300]}\n"
                    f"Group dynamics: {dynamics[:300]}\n\n"
                    f"Should you react with an emoji? Most messages (80%+) you ignore. "
                    f"Only react if something is genuinely funny, suspicious, or noteworthy. "
                    f"If yes, respond with JUST the emoji. If no, respond with exactly: SKIP\n"
                    f"Choose from: 👀 💀 🤔 😭 🔥"
                ),
            }],
        )

        result = response.content[0].text.strip()
        if result != "SKIP" and len(result) <= 4:
            try:
                await message.add_reaction(result)
            except Exception:
                pass
    except Exception:
        pass


# ── Helpers ─────────────────────────────────────────────────────────────


def _find_member(user):
    """Find a gossip member by Discord user."""
    from gossip.db import get_default_group, get_members_by_group

    group = get_default_group()
    if not group:
        return None

    members = get_members_by_group(group["id"])
    for m in members:
        if m.get("discord_id") == str(user.id):
            return m
        if m.get("discord_username") == user.name:
            return m
    return None


# ── Main patch ──────────────────────────────────────────────────────────


def patch_discord_adapter():
    """Monkey-patch the DiscordAdapter with a single, clean handler."""
    from gateway.platforms.discord import DiscordAdapter
    import discord as _discord

    DiscordAdapter._register_slash_commands = lambda self: register_gossip_commands(self)

    _original_handle_message = DiscordAdapter._handle_message
    _outreach_fired = {"done": False}

    async def _gossip_handler(self, message):
        """Single handler: gate channels, log chat, respond to triggers only."""

        # ── Fire startup outreach once ──
        if not _outreach_fired["done"]:
            _outreach_fired["done"] = True
            threading.Thread(target=_run_startup_outreach, daemon=True).start()

        # ── Classify the message ──
        is_dm = isinstance(message.channel, _discord.DMChannel)
        is_mentioned = self._client.user in message.mentions if self._client.user else False
        in_home = str(getattr(message.channel, "id", "")) == HOME_CHANNEL_ID
        content = message.content or ""
        says_donny = "donny" in content.lower()

        # ── Gate: ignore messages outside #welcome unless DM or @mention ──
        if not is_dm and not is_mentioned and not in_home:
            return

        # ── Log to chat history (all #welcome messages + DMs) ──
        member = None
        try:
            from gossip.identity import resolve_member
            from gossip.engine import append_chat_log
            from gossip.db import update_chat_activity, get_default_group

            member = resolve_member(platform="discord", user_id=str(message.author.id))
            username = member["display_name"] if member else message.author.display_name

            append_chat_log(username=username, content=content)

            group = get_default_group()
            if group:
                update_chat_activity(
                    group_id=group["id"],
                    platform="discord",
                    channel_id=str(message.channel.id),
                    author=username,
                )
        except Exception as e:
            print(f"[gossip] Chat capture error: {e}", flush=True)

        # ── Log inbound DMs ──
        if is_dm and member:
            try:
                from gossip.db import log_dm
                log_dm(member["id"], content, direction="inbound")
            except Exception as e:
                print(f"[gossip] DM log error: {e}", flush=True)

        # ── Decide: respond or stay silent ──
        should_respond = is_dm or is_mentioned or says_donny

        if should_respond:
            await _original_handle_message(self, message)
        elif in_home and not message.author.bot:
            # Not triggered — just maybe react with emoji
            import asyncio
            asyncio.create_task(_maybe_react(message))

    DiscordAdapter._handle_message = _gossip_handler

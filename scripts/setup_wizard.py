#!/usr/bin/env python3
"""Interactive setup wizard for Gossip bot."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def ask(prompt: str, default: str = "") -> str:
    """Prompt the user for input with an optional default."""
    if default:
        result = input(f"  {prompt} [{default}]: ").strip()
        return result if result else default
    return input(f"  {prompt}: ").strip()


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    result = input(f"  {prompt} ({yn}): ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def main():
    print("─" * 50)
    print("  GOSSIP BOT SETUP WIZARD")
    print("─" * 50)

    env_lines: list[str] = []
    config_updates: dict = {}

    # ── Step 1: Bot Identity ──────────────────────────────────────────

    print("\n  Step 1: Bot Identity\n")
    bot_name = ask("Bot name", "gossipbot")
    config_updates["bot_name"] = bot_name

    print("\n  Personality presets:")
    print("    1. Messy gossip queen (casual, 'ngl', 'lmao', teasing)")
    print("    2. Chill observer (laid back, dry humor)")
    print("    3. Chaotic agent of chaos (unhinged energy)")
    print("    4. Custom (edit SOUL.md yourself)")
    personality = ask("Pick a number", "1")
    personality_map = {"1": "messy_gossip_queen", "2": "chill_observer", "3": "chaotic_agent", "4": "custom"}
    config_updates["personality"] = personality_map.get(personality, "messy_gossip_queen")

    # ── Step 2: LLM Provider ─────────────────────────────────────────

    print("\n  Step 2: LLM Provider\n")
    api_key = ask("Anthropic API key (starts with sk-ant-)")
    if api_key:
        env_lines.append(f"ANTHROPIC_API_KEY={api_key}")
        env_lines.append("HERMES_MODEL=anthropic/claude-sonnet-4-20250514")

    # ── Step 3: Chat Platform ─────────────────────────────────────────

    print("\n  Step 3: Chat Platform\n")
    print("    1. Discord")
    print("    2. Telegram")
    print("    3. Both")
    platform = ask("Pick a number", "1")

    if platform in ("1", "3"):
        print("\n  Discord Setup:")
        print("    Create a bot at https://discord.com/developers/applications")
        discord_token = ask("Discord bot token")
        if discord_token:
            env_lines.append(f"DISCORD_BOT_TOKEN={discord_token}")
        channel_id = ask("Discord channel ID for gossip")
        if channel_id:
            env_lines.append(f"DISCORD_FREE_RESPONSE_CHANNELS={channel_id}")
        env_lines.append("DISCORD_REQUIRE_MENTION=false")

    if platform in ("2", "3"):
        print("\n  Telegram Setup:")
        print("    Message @BotFather on Telegram and create a new bot")
        telegram_token = ask("Telegram bot token")
        if telegram_token:
            env_lines.append(f"TELEGRAM_BOT_TOKEN={telegram_token}")

    # ── Step 4: Bot's Google Account ──────────────────────────────────

    print("\n  Step 4: Bot's Google Account (for Calendar + Email)\n")
    if ask_yes_no("Set up Google Calendar integration?"):
        print("\n    To set up Google Calendar API:")
        print("    1. Go to https://console.cloud.google.com")
        print("    2. Create a project (or select existing)")
        print("    3. Enable 'Google Calendar API'")
        print("    4. Create OAuth 2.0 credentials (Desktop app type)")
        print("    5. Download the credentials JSON\n")

        client_id = ask("Google Client ID")
        client_secret = ask("Google Client Secret")
        if client_id and client_secret:
            env_lines.append(f"GOOGLE_CLIENT_ID={client_id}")
            env_lines.append(f"GOOGLE_CLIENT_SECRET={client_secret}")
            # Also use for member OAuth
            env_lines.append(f"GOOGLE_OAUTH_CLIENT_ID={client_id}")
            env_lines.append(f"GOOGLE_OAUTH_CLIENT_SECRET={client_secret}")

    # ── Step 5: Bot's Email ───────────────────────────────────────────

    print("\n  Step 5: Bot's Email (for forwarded emails)\n")
    bot_email = ask("Bot's Gmail address", "gossipbot@gmail.com")
    env_lines.append(f"GOSSIP_EMAIL={bot_email}")

    # ── Step 6: Gossip Settings ───────────────────────────────────────

    print("\n  Step 6: Gossip Settings\n")
    threshold = ask("Inactivity threshold (hours)", "3")
    quiet_start = ask("Quiet hours start (0-23)", "23")
    quiet_end = ask("Quiet hours end (0-23)", "9")

    config_updates["inactivity_threshold_hours"] = float(threshold)
    config_updates["quiet_hours_start"] = int(quiet_start)
    config_updates["quiet_hours_end"] = int(quiet_end)

    # ── Step 7: Create Group ──────────────────────────────────────────

    print("\n  Step 7: Create Your Group\n")
    group_name = ask("Name your friend group", "the squad")
    config_updates["group_name"] = group_name

    # ── Generate secret key ──────────────────────────────────────────

    env_lines.append(f"PORTAL_SECRET_KEY={secrets.token_hex(32)}")
    env_lines.append("PORTAL_HOST=0.0.0.0")
    env_lines.append("PORTAL_PORT=3000")

    # ── Write config/.env ─────────────────────────────────────────────

    env_path = PROJECT_ROOT / "config" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, "w") as f:
        f.write("# Gossip Bot Configuration (auto-generated)\n")
        f.write("# Edit this file to update credentials\n\n")
        for line in env_lines:
            f.write(line + "\n")
    print(f"\n  Wrote {env_path}")

    # ── Update gossip.yaml ────────────────────────────────────────────

    import yaml

    yaml_path = PROJECT_ROOT / "gossip.yaml"
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("bot", {})["name"] = config_updates.get("bot_name", "gossipbot")
    cfg["bot"]["personality"] = config_updates.get("personality", "messy_gossip_queen")
    cfg.setdefault("group", {})["name"] = config_updates.get("group_name", "the squad")
    cfg.setdefault("gossip", {})["inactivity_threshold_hours"] = config_updates.get("inactivity_threshold_hours", 3)
    cfg["gossip"]["quiet_hours_start"] = config_updates.get("quiet_hours_start", 23)
    cfg["gossip"]["quiet_hours_end"] = config_updates.get("quiet_hours_end", 9)

    with open(yaml_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote {yaml_path}")

    # ── Initialize database + create group ────────────────────────────

    from gossip.db import init_db, create_group

    init_db()
    group = create_group(config_updates.get("group_name", "the squad"))
    print(f"  Created group: {group['name']}")

    portal_port = 3000
    invite_url = f"http://localhost:{portal_port}/join/{group['invite_token']}"

    # ── Print summary ─────────────────────────────────────────────────

    print("\n" + "─" * 50)
    print("  SETUP COMPLETE")
    print("─" * 50)
    print(f"\n  Bot name: {config_updates.get('bot_name', 'gossipbot')}")
    print(f"  Group: {config_updates.get('group_name', 'the squad')}")
    print(f"\n  Invite link (share this in the group chat):")
    print(f"  {invite_url}")
    print(f"\n  Portal will run at: http://localhost:{portal_port}")
    print()


if __name__ == "__main__":
    main()

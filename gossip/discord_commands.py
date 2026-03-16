"""Custom Discord slash commands for Gossip Bot.

Monkey-patches the Hermes Discord adapter to replace the default
22 admin commands with gossip-relevant ones.
"""

import os
import json

import discord


def register_gossip_commands(adapter) -> None:
    """Register gossip-specific slash commands, replacing Hermes defaults."""
    if not adapter._client:
        return

    tree = adapter._client.tree

    @tree.command(name="tea", description="Ask Donny to spill some tea")
    @discord.app_commands.describe(topic="Optional topic or person to gossip about")
    async def slash_tea(interaction: discord.Interaction, topic: str = ""):
        prompt = topic if topic else "spill the tea"
        await interaction.response.defer()
        try:
            msg = discord.Message
            # Simulate a message event
            event = _build_event(adapter, interaction, prompt)
            response = await adapter._message_handler(event) if adapter._message_handler else None
            if response:
                await interaction.followup.send(response[:2000])
            else:
                await interaction.followup.send("hmm... nothing to spill rn. try again later")
        except Exception as e:
            try:
                await interaction.followup.send(f"oops: {e}"[:200])
            except Exception:
                pass

    @tree.command(name="onboard", description="Get the link to join the gossip group")
    async def slash_onboard(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from gossip.db import get_default_group
            from gossip.config import load_config
            load_config()

            group = get_default_group()
            if not group:
                await interaction.followup.send("No group configured yet!", ephemeral=True)
                return

            token = group["invite_token"]
            msg = (
                f"**Join the gossip group:**\n"
                f"http://localhost:3000/join/{token}\n\n"
                f"Sign up, connect your Google account, and let Donny get to know you."
            )
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    @tree.command(name="whois", description="What does Donny know about someone?")
    @discord.app_commands.describe(name="Person's name")
    async def slash_whois(interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            event = _build_event(adapter, interaction, f"what do you know about {name}? check their dossier")
            response = await adapter._message_handler(event) if adapter._message_handler else None
            if response:
                await interaction.followup.send(response[:2000])
            else:
                await interaction.followup.send(f"i got nothing on {name}... yet")
        except Exception as e:
            try:
                await interaction.followup.send(f"oops: {e}"[:200])
            except Exception:
                pass

    @tree.command(name="tip", description="Drop some gossip intel for Donny")
    @discord.app_commands.describe(intel="The tea you want to share")
    async def slash_tip(interaction: discord.Interaction, intel: str):
        await interaction.response.defer(ephemeral=True)
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from gossip.db import get_default_group, get_members_by_group, add_manual_input
            from gossip.config import load_config
            load_config()

            group = get_default_group()
            if not group:
                await interaction.followup.send("No group configured!", ephemeral=True)
                return

            # Try to find the member by discord ID
            members = get_members_by_group(group["id"])
            member = None
            for m in members:
                if m.get("discord_id") == str(interaction.user.id):
                    member = m
                    break
                if m.get("discord_username") == interaction.user.name:
                    member = m
                    break

            if member:
                add_manual_input(member["id"], intel, source="discord")
                await interaction.followup.send(
                    f"noted. donny will use this next time gossip drops.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "i don't know who you are yet! use /onboard to join first.",
                    ephemeral=True,
                )
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    @tree.command(name="reset", description="Start a fresh conversation with Donny")
    async def slash_reset(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/reset", "fresh start~")

    @tree.command(name="stop", description="Stop Donny if he's going off")
    async def slash_stop(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/stop", "ok ok i'll stop")

    @tree.command(name="sethome", description="Set this channel as Donny's home")
    async def slash_sethome(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/sethome")


def _build_event(adapter, interaction, text):
    """Build a MessageEvent from a slash command interaction."""
    from gateway.platforms.base import MessageEvent, SessionSource, MessageType, Platform

    source = adapter.build_source(
        chat_id=str(interaction.channel_id),
        chat_name=getattr(interaction.channel, "name", "unknown"),
        chat_type="group",
        user_id=str(interaction.user.id),
        user_name=interaction.user.display_name,
    )

    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=source,
        raw_message=None,
        message_id=str(interaction.id),
    )


def patch_discord_adapter():
    """Monkey-patch the DiscordAdapter to use gossip commands instead of Hermes defaults."""
    from gateway.platforms.discord import DiscordAdapter

    DiscordAdapter._register_slash_commands = lambda self: register_gossip_commands(self)

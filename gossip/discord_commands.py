"""Custom Discord slash commands for Gossip Bot.

Monkey-patches the Hermes Discord adapter to replace the default
22 admin commands with gossip-relevant ones.
"""

import os
import json
import time
from pathlib import Path

import discord

_project_root = Path(__file__).resolve().parent.parent


def register_gossip_commands(adapter) -> None:
    """Register gossip-specific slash commands, replacing Hermes defaults."""
    if not adapter._client:
        return

    tree = adapter._client.tree

    # ── /tea ────────────────────────────────────────────────────────────

    @tree.command(name="tea", description="Ask Donny to spill some tea")
    @discord.app_commands.describe(topic="Optional topic or person to gossip about")
    async def slash_tea(interaction: discord.Interaction, topic: str = ""):
        prompt = topic if topic else "spill the tea"
        await interaction.response.defer()
        try:
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

    # ── /onboard ────────────────────────────────────────────────────────

    @tree.command(name="onboard", description="Get the link to join the gossip group")
    async def slash_onboard(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            from gossip.db import get_default_group
            from gossip.config import load_config
            load_config()

            group = get_default_group()
            if not group:
                await interaction.followup.send("No group configured yet!", ephemeral=True)
                return

            token = group["invite_token"]

            # Use tunnel URL if available, fallback to localhost
            base_url = os.getenv("PORTAL_PUBLIC_URL", "").rstrip("/")
            if not base_url:
                base_url = "http://localhost:3000"

            msg = (
                f"**Join the gossip group:**\n"
                f"{base_url}/join/{token}\n\n"
                f"Sign up, connect your Google account, and let Donny get to know you."
            )
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    # ── /whois ──────────────────────────────────────────────────────────

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

    # ── /tip ────────────────────────────────────────────────────────────

    @tree.command(name="tip", description="Drop some gossip intel for Donny")
    @discord.app_commands.describe(intel="The tea you want to share")
    async def slash_tip(interaction: discord.Interaction, intel: str):
        await interaction.response.defer(ephemeral=True)
        try:
            from gossip.db import get_default_group, get_members_by_group, add_manual_input
            from gossip.config import load_config
            load_config()

            group = get_default_group()
            if not group:
                await interaction.followup.send("No group configured!", ephemeral=True)
                return

            member = _find_member(interaction.user)
            if member:
                add_manual_input(member["id"], intel, source="discord")
                await interaction.followup.send(
                    "noted. donny will use this next time gossip drops.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "i don't know who you are yet! use /onboard to join first.",
                    ephemeral=True,
                )
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    # ── /imagine ────────────────────────────────────────────────────────

    @tree.command(name="imagine", description="Generate an image with AI")
    @discord.app_commands.describe(
        prompt="What to generate (e.g., 'a cat wearing a crown')",
        about="Optional: person's name to make it about them",
    )
    async def slash_imagine(interaction: discord.Interaction, prompt: str, about: str = ""):
        await interaction.response.defer()
        try:
            from gossip.config import load_config
            load_config()

            # If about a person, enrich the prompt with their dossier context
            full_prompt = prompt
            if about:
                from gossip.dossiers import read_dossier
                dossier = read_dossier(about)
                if "(no info yet)" not in dossier:
                    # Extract key details from dossier for context
                    full_prompt = (
                        f"{prompt}. Context about {about}: {dossier[:300]}"
                    )

                # Check for saved photos of this person
                member_pics = _get_member_images(about)
                if member_pics:
                    full_prompt += f". Reference: this person has {len(member_pics)} saved photo(s)."

            # Generate via Gemini
            from gossip_tools.image_tools import _handler
            result = json.loads(_handler({"prompt": full_prompt}))

            if result.get("success"):
                image_path = result["image_path"]
                await interaction.followup.send(
                    f"*{prompt}*" + (f" (about {about})" if about else ""),
                    file=discord.File(image_path, filename="donny_creation.png"),
                )

                # Save to member's image folder if about someone
                if about:
                    _save_member_image(about, image_path, prompt)
            else:
                await interaction.followup.send(f"couldn't generate that: {result.get('error', 'unknown')}"[:500])
        except Exception as e:
            try:
                await interaction.followup.send(f"image gen failed: {e}"[:200])
            except Exception:
                pass

    # ── /savepic ────────────────────────────────────────────────────────

    @tree.command(name="savepic", description="Save an attached photo to someone's profile")
    @discord.app_commands.describe(
        name="Who is in this photo?",
        photo="The image to save",
    )
    async def slash_savepic(
        interaction: discord.Interaction,
        name: str,
        photo: discord.Attachment,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if not photo.content_type or not photo.content_type.startswith("image/"):
                await interaction.followup.send("That's not an image!", ephemeral=True)
                return

            from gossip.config import load_config
            load_config()

            # Download the image
            ext = photo.content_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"

            member_dir = _project_root / "data" / "images" / "members" / name.lower().replace(" ", "_")
            member_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{int(time.time())}.{ext}"
            save_path = member_dir / filename

            image_data = await photo.read()
            with open(save_path, "wb") as f:
                f.write(image_data)

            # Update dossier
            from gossip.dossiers import append_dossier_from_source
            append_dossier_from_source(
                name, "photo",
                f"Photo saved by {interaction.user.display_name} ({filename})",
            )

            count = len(list(member_dir.glob("*")))
            await interaction.followup.send(
                f"saved! donny now has {count} photo(s) of {name}. this will be used for context in image generation.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    # ── /help ────────────────────────────────────────────────────────────

    @tree.command(name="help", description="Show what Donny can do")
    async def slash_help(interaction: discord.Interaction):
        msg = (
            "**Donny — your group's gossip bot**\n\n"
            "**Chat Commands**\n"
            "`/tea [topic]` — ask Donny to spill gossip (optionally about someone)\n"
            "`/whois [name]` — what does Donny know about someone?\n"
            "`/tip [intel]` — drop gossip intel privately for Donny to use\n\n"
            "**Images**\n"
            "`/imagine [prompt]` — generate an AI image\n"
            "`/imagine [prompt] about:[name]` — generate using someone's context\n"
            "`/savepic [name] [photo]` — save a photo of someone for Donny\n\n"
            "**Account**\n"
            "`/onboard` — get the link to join the group\n"
            "`/status` — see what Donny knows about you + connected sources\n\n"
            "**Admin**\n"
            "`/reset` — fresh conversation\n"
            "`/stop` — stop Donny mid-response\n"
            "`/sethome` — set this channel for gossip drops\n\n"
            "You can also just `@Donny` in chat to talk directly."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ── /status ─────────────────────────────────────────────────────────

    @tree.command(name="status", description="See what Donny knows about you")
    async def slash_status(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            from gossip.db import get_default_group, get_oauth_token, get_unused_manual_input
            from gossip.dossiers import read_dossier, list_dossier_entries
            from gossip.config import load_config
            load_config()

            member = _find_member(interaction.user)
            if not member:
                await interaction.followup.send(
                    "You haven't onboarded yet! Use `/onboard` to get the invite link.",
                    ephemeral=True,
                )
                return

            name = member["display_name"]

            # Check connected sources
            google = get_oauth_token(member["id"], "google")
            entries = list_dossier_entries(name)
            tips = get_unused_manual_input(member["id"])
            photos = _get_member_images(name)

            # Location
            has_location = member.get("latitude") is not None
            loc_text = f"{member.get('location_name', '?')}" if has_location else "not shared"

            lines = [
                f"**{name}** (@{member.get('discord_username', '?')})\n",
                "**Connected Sources**",
                f"  Google (Calendar + Email): {'connected' if google else 'not connected'}",
                f"  Live Location: {loc_text}",
                f"  Photos saved: {len(photos)}",
                "",
                "**Dossier**",
                f"  {len(entries)} entries" if entries else "  empty — connect Google or use /tip!",
                "",
                f"**Pending tips**: {len(tips)}",
            ]

            if not google:
                lines.append("\nUse `/onboard` to get the link and connect Google.")

            await interaction.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}"[:200], ephemeral=True)

    # ── Admin commands ──────────────────────────────────────────────────

    @tree.command(name="reset", description="Start a fresh conversation with Donny")
    async def slash_reset(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/reset", "fresh start~")

    @tree.command(name="stop", description="Stop Donny if he's going off")
    async def slash_stop(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/stop", "ok ok i'll stop")

    @tree.command(name="sethome", description="Set this channel as Donny's home")
    async def slash_sethome(interaction: discord.Interaction):
        await adapter._run_simple_slash(interaction, "/sethome")


# ── Helpers ─────────────────────────────────────────────────────────────


def _build_event(adapter, interaction, text):
    """Build a MessageEvent from a slash command interaction."""
    from gateway.platforms.base import MessageEvent, MessageType

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


def _get_member_images(name: str) -> list[Path]:
    """Get all saved images for a member."""
    member_dir = _project_root / "data" / "images" / "members" / name.lower().replace(" ", "_")
    if not member_dir.exists():
        return []
    return sorted(member_dir.glob("*"))


def _save_member_image(name: str, source_path: str, prompt: str) -> None:
    """Copy a generated image to a member's image folder."""
    import shutil

    member_dir = _project_root / "data" / "images" / "members" / name.lower().replace(" ", "_")
    member_dir.mkdir(parents=True, exist_ok=True)

    filename = f"gen_{int(time.time())}.png"
    dest = member_dir / filename
    shutil.copy2(source_path, dest)


def patch_discord_adapter():
    """Monkey-patch the DiscordAdapter to use gossip commands instead of Hermes defaults."""
    from gateway.platforms.discord import DiscordAdapter

    DiscordAdapter._register_slash_commands = lambda self: register_gossip_commands(self)

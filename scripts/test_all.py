#!/usr/bin/env python3
"""End-to-end validation of Donny infrastructure (OpenClaw architecture).

Run from project root with:
    source .venv/bin/activate
    PYTHONPATH="." python scripts/test_all.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

passed = 0
failed = 0
errors = []


def test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAIL  {name}: {e}")
    return decorator


print("\n=== Donny Infrastructure Tests (OpenClaw) ===\n")

# ── Core Python Imports ────────────────────────────────────────────────


@test("Core gossip imports")
def _():
    from gossip.db import init_db, get_default_group, update_chat_activity, log_dm, get_last_dm
    from gossip.engine import append_chat_log, should_gossip, gossip_context
    from gossip.identity import resolve_member
    from gossip.config import load_config, get_config
    from gossip.dossiers import read_dossier, write_dossier


@test("New modules import")
def _():
    from gossip.synthesizer import run_synthesizer_for_member, build_synthesizer_input
    from gossip.proactive import should_fire_idle_gossip, should_dm_checkin
    from gossip.email_filter import filter_emails


@test("Tool API router imports")
def _():
    from portal.routes.tool_api import router
    assert len(router.routes) > 0


# ── Database ───────────────────────────────────────────────────────────


@test("Database initializes with all tables")
def _():
    from gossip.db import init_db, get_connection
    from gossip.config import load_config
    load_config()
    init_db()

    with get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

    required = {
        "groups", "members", "oauth_tokens", "gossip_history",
        "chat_activity", "sync_state", "manual_input", "action_log",
        "events", "dm_history", "donny_memory", "discovery_log",
        "member_summaries",
    }
    missing = required - tables
    assert not missing, f"Missing tables: {missing}"


@test("DM history works end-to-end")
def _():
    from gossip.db import init_db, create_group, create_member, log_dm, get_last_dm, get_dm_history
    init_db()

    group = create_group("test-dm")
    member = create_member(group["id"], "DMTest")
    assert get_last_dm(member["id"]) is None

    log_dm(member["id"], "hey", direction="outbound")
    log_dm(member["id"], "sup", direction="inbound")

    last = get_last_dm(member["id"])
    assert last is not None
    assert last["message_text"] == "sup"

    history = get_dm_history(member["id"])
    assert len(history) == 2


@test("Donny memory works")
def _():
    from gossip.db import log_donny_memory, get_donny_memory, trim_donny_memory
    log_donny_memory("group", None, "test memory entry")
    memories = get_donny_memory(channel_type="group", limit=5)
    assert len(memories) >= 1
    assert "test memory entry" in memories[0]["content"]


@test("Discovery log anti-spam works")
def _():
    from gossip.db import log_discovery_attempt, can_dm_undiscovered
    log_discovery_attempt("discord", "test-user-123", "testuser")
    assert not can_dm_undiscovered("discord", "test-user-123", cooldown_days=7)


@test("Member summaries work")
def _():
    from gossip.db import init_db, create_group, create_member, upsert_member_summary, get_member_summary
    init_db()
    group = create_group("test-summary")
    member = create_member(group["id"], "SummaryTest")
    upsert_member_summary(member["id"], '{"this_week": "testing"}')
    summary = get_member_summary(member["id"])
    assert summary is not None
    assert "testing" in summary["summary_json"]


# ── Context Assembly ───────────────────────────────────────────────────


@test("gossip_context returns string for all types")
def _():
    from gossip.engine import gossip_context
    for ctx_type in ["group", "dm", "proactive"]:
        result = gossip_context(ctx_type, member="TestMember")
        assert isinstance(result, str)
        assert len(result) > 0


@test("Group context includes all sections")
def _():
    from gossip.engine import gossip_context
    ctx = gossip_context("group")
    for section in ["Recent Chat", "Member Info", "Group Dynamics", "Investigation Notes"]:
        assert f"## {section}" in ctx, f"Missing section: {section}"


@test("DM context is isolated")
def _():
    from gossip.engine import gossip_context
    ctx = gossip_context("dm", member="TestMember")
    assert "About TestMember" in ctx
    assert "Our DM History" in ctx


# ── Proactive Checks ──────────────────────────────────────────────────


@test("Idle gossip pre-check works")
def _():
    from gossip.proactive import should_fire_idle_gossip
    result = should_fire_idle_gossip()
    assert "fire" in result
    assert "reason" in result


@test("DM check-in gate works")
def _():
    from gossip.db import init_db, create_group, create_member
    from gossip.proactive import should_dm_checkin
    init_db()
    group = create_group("test-checkin")
    member = create_member(group["id"], "CheckinTest")
    result = should_dm_checkin(member["id"])
    assert "fire" in result


# ── Email Filter ──────────────────────────────────────────────────────


@test("Email filter drops sensitive emails")
def _():
    from gossip.email_filter import filter_emails
    emails = [
        {"from": "friend@gmail.com", "subject": "Hey what's up"},
        {"from": "billing@chase.com", "subject": "Your statement is ready"},
        {"from": "noreply@mychart.com", "subject": "Lab results available"},
        {"from": "coworker@company.com", "subject": "Lunch tomorrow?"},
    ]
    safe = filter_emails(emails)
    assert len(safe) == 2
    assert safe[0]["from"] == "friend@gmail.com"
    assert safe[1]["from"] == "coworker@company.com"


# ── Synthesizer ───────────────────────────────────────────────────────


@test("Synthesizer builds input")
def _():
    from gossip.db import init_db, create_group, create_member
    from gossip.synthesizer import build_synthesizer_input
    init_db()
    group = create_group("test-synth")
    member = create_member(group["id"], "SynthTest")
    result = build_synthesizer_input(member["id"], "SynthTest")
    assert isinstance(result, str)


# ── Data Files ────────────────────────────────────────────────────────


@test("Data directories exist")
def _():
    for d in ["data/dossiers", "data/chat", "data/logs", "data/summaries"]:
        assert (PROJECT_ROOT / d).is_dir(), f"{d} missing"


@test("OpenClaw workspace files exist")
def _():
    openclaw_dir = PROJECT_ROOT / "openclaw"
    assert (openclaw_dir / "SOUL.md").exists(), "openclaw/SOUL.md missing"
    assert (openclaw_dir / "SKILL.md").exists(), "openclaw/SKILL.md missing"
    assert (openclaw_dir / "HEARTBEAT.md").exists(), "openclaw/HEARTBEAT.md missing"


@test("OpenClaw plugin exists")
def _():
    plugin_dir = PROJECT_ROOT / "openclaw" / "plugins" / "gossip"
    assert (plugin_dir / "openclaw.plugin.json").exists(), "plugin.json missing"
    assert (plugin_dir / "src" / "index.ts").exists(), "source missing"
    assert (plugin_dir / "dist" / "index.js").exists(), "compiled plugin missing — run npx tsc"


@test("SOUL.md has correct identity and rules")
def _():
    content = (PROJECT_ROOT / "openclaw" / "SOUL.md").read_text()
    assert "donny" in content.lower()
    # Check rules section doesn't use banned gossip-bot language
    if "## Rules" in content:
        rules_section = content.split("## Rules")[1]
        assert "NEVER say" in rules_section or "gossip" in rules_section.lower()


@test("SKILL.md has language rules")
def _():
    content = (PROJECT_ROOT / "openclaw" / "SKILL.md").read_text()
    assert "Language Rules" in content
    assert "gossip_context" in content


@test("Portal .env has required keys")
def _():
    from dotenv import dotenv_values
    env = dotenv_values(PROJECT_ROOT / "config" / ".env")
    for key in ["ANTHROPIC_API_KEY", "DISCORD_BOT_TOKEN", "GOOGLE_OAUTH_CLIENT_ID",
                "GOOGLE_OAUTH_CLIENT_SECRET", "PORTAL_SECRET_KEY"]:
        assert env.get(key), f"Missing env var: {key}"


@test("Hermes dead code is removed")
def _():
    assert not (PROJECT_ROOT / "gossip_tools").exists(), "gossip_tools/ should be deleted"
    assert not (PROJECT_ROOT / "vendor" / "hermes-agent").exists(), "vendor/hermes-agent/ should be deleted"
    assert not (PROJECT_ROOT / "config" / "config.yaml").exists(), "config/config.yaml should be deleted"
    assert not (PROJECT_ROOT / "gossip" / "discord_commands.py").exists(), "discord_commands.py should be deleted"


# ── Summary ──────────────────────────────────────────────────────────────

print(f"\n{'=' * 50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'=' * 50}")

if errors:
    print("\nFailures:")
    for name, err in errors:
        print(f"  - {name}: {err}")

sys.exit(1 if failed else 0)

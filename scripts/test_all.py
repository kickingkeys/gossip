#!/usr/bin/env python3
"""End-to-end validation of all Gossip Bot infrastructure.

Run from project root with:
    source .venv/bin/activate
    HERMES_HOME="$PWD/config" PYTHONPATH=".:vendor/hermes-agent" python scripts/test_all.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# Ensure HERMES_HOME is set for cron tests
if not os.getenv("HERMES_HOME"):
    os.environ["HERMES_HOME"] = str(PROJECT_ROOT / "config")

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


print("\n=== Gossip Bot Infrastructure Tests ===\n")

# ── Phase 0: Imports & Dependencies ─────────────────────────────────────


@test("Core gossip imports")
def _():
    from gossip.db import init_db, get_default_group, update_chat_activity, mark_manual_input_used
    from gossip.engine import append_chat_log, build_gossip_context, should_gossip
    from gossip.identity import resolve_member
    from gossip.logger import log_event, setup_logging
    from gossip.config import load_config, get_config
    from gossip.dossiers import read_dossier, write_dossier


@test("Gossip tools import (triggers registration)")
def _():
    import gossip_tools


@test("Hermes toolsets import")
def _():
    from toolsets import validate_toolset, get_toolset, create_custom_toolset, resolve_toolset


@test("Hermes cron import")
def _():
    from cron.jobs import load_jobs, create_job, get_due_jobs


@test("Hermes tools registry import")
def _():
    from tools.registry import registry


# ── Phase 1: Hermes Config ──────────────────────────────────────────────


@test("config/config.yaml exists and parses")
def _():
    import yaml
    path = PROJECT_ROOT / "config" / "config.yaml"
    assert path.exists(), "config.yaml not found"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    assert cfg["model"] == "anthropic/claude-sonnet-4-20250514"
    assert cfg["discord"]["require_mention"] is False
    assert cfg["discord"]["free_response_channels"] == "1482803423920521413"
    assert cfg["memory"]["memory_enabled"] is True
    assert cfg["agent"]["max_turns"] == 10


@test("Gossip toolset registered and valid")
def _():
    from toolsets import validate_toolset, get_toolset
    assert validate_toolset("gossip"), "gossip toolset not recognized"
    info = get_toolset("gossip")
    expected = {
        "gossip_check_idle", "gossip_build_context", "gossip_generate",
        "gossip_read_dossier", "gossip_update_dossier",
        "gossip_list_members", "gossip_get_member",
        "gossip_update_locations", "gossip_member_locations",
        "gossip_update_dynamics", "gossip_read_dynamics",
        "gossip_generate_image", "send_message",
    }
    actual = set(info["tools"])
    assert actual == expected, f"Tool mismatch: {actual.symmetric_difference(expected)}"


@test("All 11 gossip tools in Hermes registry")
def _():
    from tools.registry import registry
    all_tools = registry.get_all_tool_names()
    expected = [
        "gossip_check_idle", "gossip_build_context", "gossip_generate",
        "gossip_read_dossier", "gossip_update_dossier",
        "gossip_list_members", "gossip_get_member",
        "gossip_update_locations", "gossip_member_locations",
        "gossip_update_dynamics", "gossip_read_dynamics",
    ]
    for tool in expected:
        assert tool in all_tools, f"Tool {tool} not in registry"


@test("config/skills/gossip symlink resolves")
def _():
    link = PROJECT_ROOT / "config" / "skills" / "gossip"
    assert link.exists(), "symlink missing"
    assert (link / "SKILL.md").exists(), "SKILL.md not reachable through symlink"


@test("config/hooks/gossip-logger symlink resolves")
def _():
    link = PROJECT_ROOT / "config" / "hooks" / "gossip-logger"
    assert link.exists(), "symlink missing"
    assert (link / "handler.py").exists(), "handler.py not reachable through symlink"
    assert (link / "HOOK.yaml").exists(), "HOOK.yaml not reachable through symlink"


@test("PORTAL_SECRET_KEY is set in config/.env")
def _():
    from dotenv import dotenv_values
    env = dotenv_values(PROJECT_ROOT / "config" / ".env")
    key = env.get("PORTAL_SECRET_KEY", "")
    assert len(key) >= 32, f"PORTAL_SECRET_KEY too short ({len(key)} chars)"


@test("Data directories exist")
def _():
    for d in ["data/dossiers", "data/chat", "data/logs"]:
        assert (PROJECT_ROOT / d).is_dir(), f"{d} missing"


# ── Phase 2: Cron Jobs ──────────────────────────────────────────────────


@test("Cron jobs.json loads with correct jobs")
def _():
    from cron.jobs import load_jobs
    jobs = load_jobs()
    assert len(jobs) == 3, f"Expected 3 jobs, got {len(jobs)}"

    idle_job = next((j for j in jobs if j["id"] == "gossip-idle-01"), None)
    assert idle_job is not None, "gossip-idle-01 not found"
    assert idle_job["enabled"] is True
    assert idle_job["schedule"]["kind"] == "interval"
    assert idle_job["schedule"]["minutes"] == 30
    assert "1482803423920521413" in idle_job["deliver"]

    cal_job = next((j for j in jobs if j["id"] == "calendar-sync-01"), None)
    assert cal_job is not None, "calendar-sync-01 not found"
    assert cal_job["enabled"] is False

    loc_job = next((j for j in jobs if j["id"] == "location-check-01"), None)
    assert loc_job is not None, "location-check-01 not found"
    assert loc_job["enabled"] is False
    assert loc_job["schedule"]["minutes"] == 30


# ── Phase 3: Chat History Capture ────────────────────────────────────────


@test("Hook handler has chat capture function")
def _():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "handler", str(PROJECT_ROOT / "hooks" / "gossip-logger" / "handler.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "handle"), "handle() missing"
    assert hasattr(mod, "_capture_chat_message"), "_capture_chat_message() missing"
    assert hasattr(mod, "_write_trace"), "_write_trace() missing"


@test("Chat logging writes to daily file")
def _():
    from gossip.engine import append_chat_log
    from gossip.config import load_config

    load_config()
    ts = datetime(2099, 12, 31, 12, 0, tzinfo=timezone.utc)
    append_chat_log("TestUser", "Hello from test!", timestamp=ts)

    chat_file = PROJECT_ROOT / "data" / "chat" / "2099-12-31.md"
    assert chat_file.exists(), "Chat file not created"
    content = chat_file.read_text()
    assert "[12:00] TestUser: Hello from test!" in content
    # Cleanup
    chat_file.unlink()


@test("DB chat_activity updates correctly")
def _():
    from gossip.db import init_db, create_group, update_chat_activity, get_chat_activity
    from gossip.config import load_config

    load_config()
    init_db()

    # Create a test group
    group = create_group("test-chat-activity")
    update_chat_activity(group["id"], "discord", "test-channel", author="TestUser")

    activities = get_chat_activity(group["id"])
    assert len(activities) >= 1, "No chat activity recorded"
    assert activities[0]["last_human_author"] == "TestUser"


@test("SKILL.md has Silent Observation Mode")
def _():
    content = (PROJECT_ROOT / "skills" / "gossip" / "SKILL.md").read_text()
    assert "Silent Observation Mode" in content
    assert "return empty text" in content


# ── Phase 4: Portal & Gossip Gen ─────────────────────────────────────────


@test("Portal app.py has root route")
def _():
    content = (PROJECT_ROOT / "portal" / "app.py").read_text()
    assert '@app.get("/")' in content
    assert "async def root()" in content
    assert '"status"' in content


@test("gossip_gen marks manual inputs as used")
def _():
    content = (PROJECT_ROOT / "gossip_tools" / "gossip_gen.py").read_text()
    assert "mark_manual_input_used" in content
    assert "get_unused_manual_input" in content
    assert "get_members_by_group" in content


@test("Manual input marking works end-to-end")
def _():
    from gossip.db import (
        init_db, create_group, create_member,
        add_manual_input, get_unused_manual_input, mark_manual_input_used,
    )
    from gossip.config import load_config

    load_config()
    init_db()

    group = create_group("test-manual-input")
    member = create_member(group["id"], "TestMember")
    input_id = add_manual_input(member["id"], "secret gossip")

    unused = get_unused_manual_input(member["id"])
    assert len(unused) >= 1, "Manual input not found"

    mark_manual_input_used(input_id)
    unused_after = get_unused_manual_input(member["id"])
    assert len(unused_after) == 0, "Manual input not marked as used"


# ── Phase 5: start.sh Hook Path ─────────────────────────────────────────


@test("start.sh uses HERMES_HOME for hooks (not ~/.hermes)")
def _():
    content = (PROJECT_ROOT / "scripts" / "start.sh").read_text()
    assert 'HERMES_HOOKS_DIR="$HERMES_HOME/hooks"' in content
    assert "/.hermes/hooks" not in content


# ── Phase 6: Gossip Tool Chain Simulation ────────────────────────────────


@test("Idle check tool returns valid structure")
def _():
    from gossip_tools.idle_check import _handler
    result = json.loads(_handler({}))
    assert "should_fire" in result
    assert "hours_idle" in result
    assert "is_quiet_hours" in result


@test("Context builder returns non-empty string")
def _():
    from gossip_tools.context_builder import _handler
    result = json.loads(_handler({}))
    assert "context" in result
    assert len(result["context"]) > 0


@test("Gossip generate logs correctly")
def _():
    from gossip_tools.gossip_gen import _handler
    from gossip.db import get_default_group, get_recent_gossip

    result = json.loads(_handler({
        "gossip_text": "Test gossip from validation script",
        "context_summary": "test run",
    }))
    assert result.get("success") is True, f"Generate failed: {result}"
    assert result.get("gossip_id") is not None


# ── Phase 7: Trace Tests ────────────────────────────────────────────────


@test("get_current_session_id returns env var when set")
def _():
    from gossip.logger import get_current_session_id

    # When unset
    old = os.environ.pop("HERMES_SESSION_KEY", None)
    assert get_current_session_id() is None

    # When set
    os.environ["HERMES_SESSION_KEY"] = "test-session-123"
    assert get_current_session_id() == "test-session-123"

    # Cleanup
    if old is not None:
        os.environ["HERMES_SESSION_KEY"] = old
    else:
        os.environ.pop("HERMES_SESSION_KEY", None)


@test("Trace directory can be created")
def _():
    from gossip.config import get_config
    cfg = get_config()
    trace_dir = cfg.log_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    assert trace_dir.is_dir()


@test("Session events stored with session_id in DB")
def _():
    from gossip.db import init_db, get_events_by_session
    from gossip.logger import log_event

    init_db()

    test_session = "test-trace-session-abc"
    log_event(
        event_type="idle_check",
        event_subtype="fire",
        summary="Test trace event",
        payload={"test": True},
        session_id=test_session,
    )

    events = get_events_by_session(test_session)
    assert len(events) >= 1, "No events found for session"
    assert events[0]["session_id"] == test_session


@test("Trace JSON file can be written and read back")
def _():
    from gossip.config import get_config
    cfg = get_config()
    trace_dir = cfg.log_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    trace = {
        "session_id": "test-write-trace",
        "platform": "test",
        "user_id": "u123",
        "started_at": "2026-03-15T12:00:00",
        "ended_at": "2026-03-15T12:00:03",
        "events": [{"type": "idle_check", "subtype": "fire", "summary": "test", "payload": {}}],
    }

    path = trace_dir / "test-write-trace.json"
    with open(path, "w") as f:
        json.dump(trace, f)

    with open(path) as f:
        loaded = json.load(f)

    assert loaded["session_id"] == "test-write-trace"
    assert len(loaded["events"]) == 1

    # Cleanup
    path.unlink()


@test("HOOK.yaml includes agent:step event")
def _():
    import yaml
    hook_path = PROJECT_ROOT / "hooks" / "gossip-logger" / "HOOK.yaml"
    with open(hook_path) as f:
        hook = yaml.safe_load(f)
    assert "agent:step" in hook["events"], "agent:step not in HOOK.yaml events"


# ── Phase 8: Location Tests ─────────────────────────────────────────────


@test("Location columns exist in DB")
def _():
    from gossip.db import init_db, get_connection
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(members)")
        columns = {row[1] for row in cursor.fetchall()}
    for col in ["latitude", "longitude", "location_name", "location_updated_at"]:
        assert col in columns, f"Column {col} missing from members table"


@test("update_member_location stores and retrieves correctly")
def _():
    from gossip.db import (
        init_db, create_group, create_member,
        update_member_location, get_members_with_location,
    )
    init_db()

    group = create_group("test-location")
    member = create_member(group["id"], "LocationTest")
    update_member_location(member["id"], 40.7128, -74.0060, "New York City")

    located = get_members_with_location(group["id"])
    assert len(located) >= 1, "No located members found"
    m = next(l for l in located if l["display_name"] == "LocationTest")
    assert abs(m["latitude"] - 40.7128) < 0.001
    assert abs(m["longitude"] - (-74.0060)) < 0.001
    assert m["location_name"] == "New York City"


@test("get_members_with_location filters correctly")
def _():
    from gossip.db import (
        init_db, create_group, create_member,
        update_member_location, get_members_with_location,
    )
    init_db()

    group = create_group("test-location-filter")
    m1 = create_member(group["id"], "HasLocation")
    m2 = create_member(group["id"], "NoLocation")
    update_member_location(m1["id"], 51.5074, -0.1278, "London")

    located = get_members_with_location(group["id"])
    names = [m["display_name"] for m in located]
    assert "HasLocation" in names
    assert "NoLocation" not in names


@test("gossip_update_locations tool accepts valid input")
def _():
    from gossip_tools.location_tools import _handle_update
    from gossip.db import init_db, get_default_group, create_member

    init_db()
    group = get_default_group()
    assert group is not None, "No default group"
    create_member(group["id"], "LocToolTest")

    result = json.loads(_handle_update({
        "locations": [
            {"member_name": "LocToolTest", "latitude": 35.6762, "longitude": 139.6503, "location_name": "Tokyo"},
        ],
    }))
    assert result.get("success") is True, f"Tool failed: {result}"
    assert result["updated"] == 1, f"Expected 1 updated, got {result['updated']}"


@test("gossip_member_locations tool returns locations and distances")
def _():
    from gossip_tools.location_tools import _handle_locations
    result = json.loads(_handle_locations({}))
    assert "locations" in result
    assert "proximities" in result


@test("build_gossip_context includes Member Locations section")
def _():
    from gossip.engine import build_gossip_context
    context = build_gossip_context()
    assert "## Member Locations" in context


@test("Map route exists in portal")
def _():
    content = (PROJECT_ROOT / "portal" / "routes" / "map_view.py").read_text()
    assert "/map/{invite_token}" in content
    assert "map.html" in content


@test("Location cron job exists in jobs.json (disabled)")
def _():
    with open(PROJECT_ROOT / "config" / "cron" / "jobs.json") as f:
        data = json.load(f)
    loc_job = next((j for j in data["jobs"] if j["id"] == "location-check-01"), None)
    assert loc_job is not None, "location-check-01 not found"
    assert loc_job["enabled"] is False


# ── Phase 9: Group Dynamics Tests ────────────────────────────────────────


@test("gossip_update_dynamics tool writes to group.md")
def _():
    from gossip_tools.dynamics_tools import _handle_update

    result = json.loads(_handle_update({
        "relationships": ["TestA and TestB: best friends"],
        "observations": ["TestA was seen at the park"],
    }))
    assert result.get("success") is True
    assert result["entries_added"] == 2


@test("gossip_read_dynamics tool returns content")
def _():
    from gossip_tools.dynamics_tools import _handle_read

    result = json.loads(_handle_read({}))
    assert "dynamics" in result
    assert len(result["dynamics"]) > 0


@test("Compaction keeps content under 2000 chars")
def _():
    from gossip.engine import compact_group_dynamics

    # Build a large string
    lines = ["## Relationships"]
    for i in range(100):
        lines.append(f"- Person{i} and Person{i+1}: relationship {i}")
    lines.append("")
    lines.append("## Behavioral Patterns")
    lines.append("")
    lines.append("## Running Jokes & References")
    lines.append("")
    lines.append("## Recent Observations")
    big = "\n".join(lines)
    assert len(big) > 2000, "Test string should be over 2000 chars"

    compacted = compact_group_dynamics(big)
    assert len(compacted) <= 2000, f"Compacted is {len(compacted)} chars, expected <= 2000"


@test("group.md has correct section headers")
def _():
    path = PROJECT_ROOT / "data" / "group.md"
    assert path.exists(), "data/group.md missing"
    content = path.read_text()
    for section in ["## Relationships", "## Behavioral Patterns", "## Running Jokes & References", "## Recent Observations"]:
        assert section in content, f"Missing section: {section}"


@test("build_gossip_context includes group dynamics content")
def _():
    from gossip.engine import build_gossip_context
    context = build_gossip_context()
    assert "## Group Dynamics" in context


# ── Summary ──────────────────────────────────────────────────────────────

print(f"\n{'=' * 50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'=' * 50}")

if errors:
    print("\nFailures:")
    for name, err in errors:
        print(f"  - {name}: {err}")

sys.exit(1 if failed else 0)

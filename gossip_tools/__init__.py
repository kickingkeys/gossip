"""Gossip custom tools for Hermes Agent.

Importing this package registers all gossip tools with the Hermes ToolRegistry.
"""

import sys
from pathlib import Path

_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

from toolsets import create_custom_toolset  # noqa: E402

# Register "gossip" as a custom toolset so Hermes validate_toolset("gossip") passes
create_custom_toolset(
    name="gossip",
    description="Gossip bot tools for idle checking, context building, gossip generation, dossiers, location tracking, group dynamics, DM check-ins, and member discovery",
    tools=[
        "gossip_check_idle",
        "gossip_build_context",
        "gossip_generate",
        "gossip_read_dossier",
        "gossip_update_dossier",
        "gossip_update_locations",
        "gossip_update_dynamics",
        "gossip_generate_image",
        "gossip_sync_sources",
        "gossip_pick_dm_target",
        "gossip_log_dm",
        "gossip_discover_members",
        "send_message",
    ],
)

from gossip_tools import idle_check  # noqa: F401, E402
from gossip_tools import context_builder  # noqa: F401, E402
from gossip_tools import gossip_gen  # noqa: F401, E402
from gossip_tools import dossier_tools  # noqa: F401, E402
from gossip_tools import location_tools  # noqa: F401, E402
from gossip_tools import dynamics_tools  # noqa: F401, E402
from gossip_tools import image_tools  # noqa: F401, E402
from gossip_tools import sync_tools  # noqa: F401, E402
from gossip_tools import intel_tools  # noqa: F401, E402

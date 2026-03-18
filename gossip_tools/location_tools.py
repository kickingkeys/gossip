"""Hermes tools: gossip_update_locations, gossip_member_locations."""

import json
import math
import sys
from pathlib import Path

_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.registry import registry  # noqa: E402


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two lat/lng points in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Update Locations ───────────────────────────────────────────────────

UPDATE_SCHEMA = {
    "name": "gossip_update_locations",
    "description": (
        "Update member locations from browser vision data. "
        "Accepts a list of location objects with member_name, latitude, longitude, and location_name."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "locations": {
                "type": "array",
                "description": "List of location updates.",
                "items": {
                    "type": "object",
                    "properties": {
                        "member_name": {"type": "string", "description": "Member's display name."},
                        "latitude": {"type": "number", "description": "Latitude coordinate."},
                        "longitude": {"type": "number", "description": "Longitude coordinate."},
                        "location_name": {"type": "string", "description": "Human-readable place name."},
                    },
                    "required": ["member_name", "latitude", "longitude", "location_name"],
                },
            },
        },
        "required": ["locations"],
    },
}


def _handle_update(args, **kwargs):
    from gossip.db import get_default_group, get_members_by_group, update_member_location
    from gossip.dossiers import append_dossier_from_source
    from gossip.logger import log_event, get_current_session_id

    locations = args.get("locations", [])
    if not locations:
        return json.dumps({"error": "locations list is required"})

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_by_group(group["id"])
    members_by_name = {m["display_name"].lower(): m for m in members}

    updated = 0
    not_found = []

    for loc in locations:
        name = loc.get("member_name", "")
        member = members_by_name.get(name.lower())

        if not member:
            not_found.append(name)
            continue

        update_member_location(
            member["id"],
            lat=loc["latitude"],
            lng=loc["longitude"],
            location_name=loc["location_name"],
        )

        append_dossier_from_source(
            member["display_name"],
            "location",
            f"Seen at {loc['location_name']} ({loc['latitude']:.4f}, {loc['longitude']:.4f})",
        )
        updated += 1

    log_event(
        event_type="location_update",
        summary=f"Updated {updated} member locations",
        payload={
            "updated": updated,
            "not_found": not_found,
            "total_input": len(locations),
        },
        session_id=get_current_session_id(),
    )

    return json.dumps({
        "success": True,
        "updated": updated,
        "not_found": not_found,
    })


# ── Member Locations ───────────────────────────────────────────────────

LOCATIONS_SCHEMA = {
    "name": "gossip_member_locations",
    "description": "Get all member locations with pairwise distances.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _handle_locations(args, **kwargs):
    from gossip.db import get_default_group, get_members_with_location
    from gossip.logger import log_event, get_current_session_id

    group = get_default_group()
    if not group:
        return json.dumps({"error": "no group configured"})

    members = get_members_with_location(group["id"])

    result = []
    for m in members:
        result.append({
            "name": m["display_name"],
            "latitude": m["latitude"],
            "longitude": m["longitude"],
            "location_name": m.get("location_name", ""),
            "updated_at": m.get("location_updated_at", ""),
        })

    # Calculate pairwise distances
    proximities = []
    for i in range(len(result)):
        for j in range(i + 1, len(result)):
            dist = _haversine_km(
                result[i]["latitude"], result[i]["longitude"],
                result[j]["latitude"], result[j]["longitude"],
            )
            label = "same area" if dist < 1 else "nearby" if dist < 5 else f"{dist:.1f}km apart"
            proximities.append({
                "members": [result[i]["name"], result[j]["name"]],
                "distance_km": round(dist, 2),
                "label": label,
            })

    log_event(
        event_type="location_query",
        summary=f"Queried {len(result)} member locations",
        payload={"count": len(result)},
        session_id=get_current_session_id(),
    )

    return json.dumps({
        "locations": result,
        "proximities": proximities,
    })


def _check():
    return True


registry.register(
    name="gossip_update_locations",
    toolset="gossip",
    schema=UPDATE_SCHEMA,
    handler=_handle_update,
    check_fn=_check,
    is_async=False,
)

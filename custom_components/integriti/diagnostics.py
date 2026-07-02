"""Diagnostics support for Inner Range Integriti."""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_API_KEY
from .coordinator import IntegritiCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    """Return redacted diagnostics for a config entry."""
    coordinator: IntegritiCoordinator = entry.runtime_data
    return {
        "entry": {
            **{key: value for key, value in entry.data.items() if key != CONF_API_KEY},
            CONF_API_KEY: "REDACTED",
            "options": dict(entry.options),
        },
        "api_info": asdict(coordinator.data.api_info),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "door_count": len(coordinator.data.doors),
            "area_count": len(coordinator.data.areas),
        },
        "doors": [
            {
                "unique_id": door.unique_id,
                "control_id": door.control_id,
                "xml_control_id": door.xml_control_id,
                "state_id": door.state_id,
                "name": door.name,
                "address": door.address,
                "controller_id": door.controller_id,
                "state": door.state_raw,
                "licensed": door.licensed,
                "is_open": door.is_open,
                "dotl": door.dotl,
                "forced": door.forced,
                "module_missing": door.module_missing,
                "roller_state": door.roller_state_raw,
                "is_override_on": door.is_override_on,
            }
            for door in coordinator.data.doors.values()
        ],
        "areas": [
            {
                "unique_id": area.unique_id,
                "control_id": area.control_id,
                "xml_control_id": area.xml_control_id,
                "state_id": area.state_id,
                "name": area.name,
                "address": area.address,
                "controller_id": area.controller_id,
                "state": area.state_raw,
                "holdup": area.holdup,
                "entry_state": area.entry_state,
                "entry_state_raw": area.entry_state_raw,
                "exit_state": area.exit_state,
                "exit_state_raw": area.exit_state_raw,
                "siren": area.siren,
                "confirm": area.confirm,
                "defer": area.defer,
                "warn": area.warn,
                "siren_holdoff": area.siren_holdoff,
                "user_count": area.user_count,
            }
            for area in coordinator.data.areas.values()
        ],
    }

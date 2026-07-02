"""Select platform for Integriti door override modes."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_DOOR_CONTROL,
    DEFAULT_ENABLE_DOOR_CONTROL,
    DOOR_OVERRIDE_LOCKED,
    DOOR_OVERRIDE_NORMAL,
    DOOR_OVERRIDE_OPTIONS,
    DOOR_OVERRIDE_UNLOCKED,
)
from .coordinator import IntegritiCoordinator
from .entity import IntegritiDoorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IntegritiCoordinator = entry.runtime_data
    async_add_entities(
        IntegritiDoorOverrideSelect(coordinator, entry, door_id)
        for door_id in coordinator.data.doors
    )


class IntegritiDoorOverrideSelect(IntegritiDoorEntity, SelectEntity):
    """Persistent Integriti door override mode."""

    _attr_name = "Override mode"
    _attr_options = DOOR_OVERRIDE_OPTIONS

    def __init__(
        self, coordinator: IntegritiCoordinator, entry: ConfigEntry, door_id: str
    ) -> None:
        super().__init__(coordinator, entry, door_id, "override")

    @property
    def current_option(self) -> str | None:
        door = self.door
        return None if door is None else door.override_mode

    async def async_select_option(self, option: str) -> None:
        enabled = self._entry.options.get(
            CONF_ENABLE_DOOR_CONTROL,
            self._entry.data.get(CONF_ENABLE_DOOR_CONTROL, DEFAULT_ENABLE_DOOR_CONTROL),
        )
        if not enabled:
            raise HomeAssistantError("Door control is disabled in Integriti options")
        door = self.door
        if door is None:
            raise HomeAssistantError("Door is not available")
        if option == DOOR_OVERRIDE_NORMAL:
            await self.coordinator.client.async_remove_door_override(door.address)
        elif option == DOOR_OVERRIDE_LOCKED:
            await self.coordinator.client.async_override_door(door.address, locked=True)
        elif option == DOOR_OVERRIDE_UNLOCKED:
            await self.coordinator.client.async_override_door(door.address, locked=False)
        else:
            raise HomeAssistantError(f"Unsupported override mode: {option}")
        await self.coordinator.async_request_refresh()

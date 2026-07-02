"""Lock platform for Integriti doors."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_DOOR_CONTROL,
    CONF_GRANT_ACCESS_SECONDS,
    DEFAULT_ENABLE_DOOR_CONTROL,
    DEFAULT_GRANT_ACCESS_SECONDS,
)
from .coordinator import IntegritiCoordinator
from .entity import IntegritiDoorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Integriti door locks."""
    coordinator: IntegritiCoordinator = entry.runtime_data
    async_add_entities(
        IntegritiDoorLock(coordinator, entry, door_id)
        for door_id in coordinator.data.doors
    )


class IntegritiDoorLock(IntegritiDoorEntity, LockEntity):
    """An Integriti door locking mechanism."""

    _attr_name = None
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(
        self, coordinator: IntegritiCoordinator, entry: ConfigEntry, door_id: str
    ) -> None:
        super().__init__(coordinator, entry, door_id, "lock")

    @property
    def is_locked(self) -> bool | None:
        door = self.door
        return None if door is None else door.is_locked

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        door = self.door
        if door is None:
            return {}
        return {
            "integriti_address": door.address,
            "integriti_state": door.state_raw,
            "override_active": door.is_override_on,
            "licensed": door.licensed,
            "roller_state": door.roller_state_raw,
            "inside_area": door.inside_area,
            "outside_area": door.outside_area,
        }

    def _control_enabled(self) -> bool:
        return bool(
            self._entry.options.get(
                CONF_ENABLE_DOOR_CONTROL,
                self._entry.data.get(
                    CONF_ENABLE_DOOR_CONTROL, DEFAULT_ENABLE_DOOR_CONTROL
                ),
            )
        )

    def _require_control(self) -> None:
        if not self._control_enabled():
            raise HomeAssistantError("Door control is disabled in Integriti options")

    async def async_lock(self, **kwargs: object) -> None:
        """Apply an Integriti locked override."""
        self._require_control()
        door = self.door
        if door is None:
            raise HomeAssistantError("Door is not available")
        await self.coordinator.client.async_override_door(door.address, locked=True)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: object) -> None:
        """Apply an Integriti unlocked override."""
        self._require_control()
        door = self.door
        if door is None:
            raise HomeAssistantError("Door is not available")
        await self.coordinator.client.async_override_door(door.address, locked=False)
        await self.coordinator.async_request_refresh()

    async def async_open(self, **kwargs: object) -> None:
        """Momentarily grant access through the door."""
        self._require_control()
        door = self.door
        if door is None:
            raise HomeAssistantError("Door is not available")
        seconds = int(
            self._entry.options.get(
                CONF_GRANT_ACCESS_SECONDS,
                self._entry.data.get(
                    CONF_GRANT_ACCESS_SECONDS, DEFAULT_GRANT_ACCESS_SECONDS
                ),
            )
        )
        await self.coordinator.client.async_grant_access(door.address, seconds)
        await self.coordinator.async_request_refresh()

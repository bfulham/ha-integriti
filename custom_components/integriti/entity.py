"""Base entities for Inner Range Integriti."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import IntegritiCoordinator
from .models import IntegritiArea, IntegritiDoor


class IntegritiEntity(CoordinatorEntity[IntegritiCoordinator]):
    """Base Integriti coordinator entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IntegritiCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def _server_version(self) -> str | None:
        return self.coordinator.data.api_info.product_version


class IntegritiDoorEntity(IntegritiEntity):
    """Base entity tied to an Integriti door."""

    def __init__(
        self,
        coordinator: IntegritiCoordinator,
        entry: ConfigEntry,
        door_id: str,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._door_id = door_id
        self._attr_unique_id = f"{entry.entry_id}-door-{door_id}-{entity_key}"

    @property
    def door(self) -> IntegritiDoor | None:
        return self.coordinator.data.doors.get(self._door_id)

    @property
    def available(self) -> bool:
        return super().available and self.door is not None

    @property
    def device_info(self) -> DeviceInfo:
        door = self.door
        assert door is not None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}:door:{self._door_id}")},
            name=door.name,
            manufacturer="Inner Range",
            model="Integriti Door",
            sw_version=self._server_version,
            configuration_url=self.coordinator.client.base_url,
        )


class IntegritiAreaEntity(IntegritiEntity):
    """Base entity tied to an Integriti security area."""

    def __init__(
        self,
        coordinator: IntegritiCoordinator,
        entry: ConfigEntry,
        area_id: str,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._area_id = area_id
        self._attr_unique_id = f"{entry.entry_id}-area-{area_id}-{entity_key}"

    @property
    def area(self) -> IntegritiArea | None:
        return self.coordinator.data.areas.get(self._area_id)

    @property
    def available(self) -> bool:
        return super().available and self.area is not None

    @property
    def device_info(self) -> DeviceInfo:
        area = self.area
        assert area is not None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}:area:{self._area_id}")},
            name=area.name,
            manufacturer="Inner Range",
            model="Integriti Security Area",
            sw_version=self._server_version,
            configuration_url=self.coordinator.client.base_url,
        )

"""Sensors for Integriti doors and areas."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IntegritiCoordinator
from .entity import IntegritiAreaEntity, IntegritiDoorEntity
from .models import ROLLER_STATE_NAMES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IntegritiCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for door_id, door in coordinator.data.doors.items():
        if door.roller_state not in (None, 0):
            entities.append(IntegritiRollerStateSensor(coordinator, entry, door_id))
    for area_id in coordinator.data.areas:
        entities.extend(
            (
                IntegritiAreaEntryStateSensor(coordinator, entry, area_id),
                IntegritiAreaExitStateSensor(coordinator, entry, area_id),
                IntegritiAreaUserCountSensor(coordinator, entry, area_id),
            )
        )
    async_add_entities(entities)


class IntegritiRollerStateSensor(IntegritiDoorEntity, SensorEntity):
    _attr_name = "Roller state"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, door_id):
        super().__init__(coordinator, entry, door_id, "roller_state")

    @property
    def native_value(self) -> str | None:
        door = self.door
        if door is None:
            return None
        if door.roller_state is not None:
            return ROLLER_STATE_NAMES.get(door.roller_state, str(door.roller_state))
        return door.roller_state_raw


class IntegritiAreaEntryStateSensor(IntegritiAreaEntity, SensorEntity):
    _attr_name = "Entry delay"

    def __init__(self, coordinator, entry, area_id):
        super().__init__(coordinator, entry, area_id, "entry_state")

    @property
    def native_value(self) -> str | None:
        area = self.area
        if area is None or area.entry_state is None:
            return None
        return "active" if area.entry_state else "idle"


class IntegritiAreaExitStateSensor(IntegritiAreaEntity, SensorEntity):
    _attr_name = "Exit delay"

    def __init__(self, coordinator, entry, area_id):
        super().__init__(coordinator, entry, area_id, "exit_state")

    @property
    def native_value(self) -> str | None:
        area = self.area
        if area is None or area.exit_state is None:
            return None
        return "active" if area.exit_state else "idle"


class IntegritiAreaUserCountSensor(IntegritiAreaEntity, SensorEntity):
    _attr_name = "User count"
    _attr_native_unit_of_measurement = "users"

    def __init__(self, coordinator, entry, area_id):
        super().__init__(coordinator, entry, area_id, "user_count")

    @property
    def native_value(self) -> int | None:
        area = self.area
        return None if area is None else area.user_count

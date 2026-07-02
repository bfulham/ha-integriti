"""Binary sensors for Integriti doors and areas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IntegritiCoordinator
from .entity import IntegritiAreaEntity, IntegritiDoorEntity
from .models import IntegritiArea, IntegritiDoor


@dataclass(frozen=True, kw_only=True)
class DoorBinaryDescription:
    key: str
    name: str
    device_class: BinarySensorDeviceClass
    value_fn: Callable[[IntegritiDoor], bool | None]
    category: EntityCategory | None = None


DOOR_DESCRIPTIONS = (
    DoorBinaryDescription(
        key="contact",
        name="Contact",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda door: door.is_open,
    ),
    DoorBinaryDescription(
        key="held_open",
        name="Held open",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda door: door.dotl,
    ),
    DoorBinaryDescription(
        key="forced_open",
        name="Forced open",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda door: door.forced,
    ),
    DoorBinaryDescription(
        key="connectivity",
        name="Connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda door: None if door.module_missing is None else not door.module_missing,
        category=EntityCategory.DIAGNOSTIC,
    ),
)


@dataclass(frozen=True, kw_only=True)
class AreaBinaryDescription:
    key: str
    name: str
    device_class: BinarySensorDeviceClass
    value_fn: Callable[[IntegritiArea], bool | None]
    enabled_default: bool = True


AREA_DESCRIPTIONS = (
    AreaBinaryDescription(
        key="holdup",
        name="Holdup",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda area: area.holdup,
    ),
    AreaBinaryDescription(
        key="siren",
        name="Siren",
        device_class=BinarySensorDeviceClass.SOUND,
        value_fn=lambda area: area.siren,
    ),
    AreaBinaryDescription(
        key="warning",
        name="Warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda area: area.warn,
    ),
    AreaBinaryDescription(
        key="confirmation",
        name="Confirmation",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda area: area.confirm,
        enabled_default=False,
    ),
    AreaBinaryDescription(
        key="deferred",
        name="Deferred arming",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda area: area.defer,
        enabled_default=False,
    ),
    AreaBinaryDescription(
        key="siren_holdoff",
        name="Siren holdoff",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda area: area.siren_holdoff,
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IntegritiCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for door_id in coordinator.data.doors:
        entities.extend(
            IntegritiDoorBinarySensor(coordinator, entry, door_id, description)
            for description in DOOR_DESCRIPTIONS
        )
    for area_id in coordinator.data.areas:
        entities.extend(
            IntegritiAreaBinarySensor(coordinator, entry, area_id, description)
            for description in AREA_DESCRIPTIONS
        )
    async_add_entities(entities)


class IntegritiDoorBinarySensor(IntegritiDoorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, door_id, description: DoorBinaryDescription):
        super().__init__(coordinator, entry, door_id, description.key)
        self._description = description
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.category

    @property
    def is_on(self) -> bool | None:
        door = self.door
        return None if door is None else self._description.value_fn(door)


class IntegritiAreaBinarySensor(IntegritiAreaEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, area_id, description: AreaBinaryDescription):
        super().__init__(coordinator, entry, area_id, description.key)
        self._description = description
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def is_on(self) -> bool | None:
        area = self.area
        return None if area is None else self._description.value_fn(area)

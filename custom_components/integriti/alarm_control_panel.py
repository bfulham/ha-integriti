"""Alarm control panel platform for Integriti security areas."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_AREA_CONTROL, DEFAULT_ENABLE_AREA_CONTROL
from .coordinator import IntegritiCoordinator
from .entity import IntegritiAreaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IntegritiCoordinator = entry.runtime_data
    async_add_entities(
        IntegritiAreaAlarm(coordinator, entry, area_id)
        for area_id in coordinator.data.areas
    )


class IntegritiAreaAlarm(IntegritiAreaEntity, AlarmControlPanelEntity):
    """An Integriti security area."""

    _attr_name = None
    _attr_code_arm_required = False

    def __init__(
        self, coordinator: IntegritiCoordinator, entry: ConfigEntry, area_id: str
    ) -> None:
        super().__init__(coordinator, entry, area_id, "alarm")

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        enabled = self._entry.options.get(
            CONF_ENABLE_AREA_CONTROL,
            self._entry.data.get(CONF_ENABLE_AREA_CONTROL, DEFAULT_ENABLE_AREA_CONTROL),
        )
        if enabled:
            return AlarmControlPanelEntityFeature.ARM_AWAY
        return AlarmControlPanelEntityFeature(0)

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        area = self.area
        if area is None:
            return None
        if area.siren or area.holdup:
            return AlarmControlPanelState.TRIGGERED
        if area.exit_state:
            return AlarmControlPanelState.ARMING
        if area.entry_state:
            return AlarmControlPanelState.PENDING
        armed = area.is_armed
        if armed is True:
            return AlarmControlPanelState.ARMED_AWAY
        if armed is False:
            return AlarmControlPanelState.DISARMED
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        area = self.area
        if area is None:
            return {}
        return {
            "integriti_address": area.address,
            "integriti_state": area.state_raw,
            "holdup": area.holdup,
            "siren": area.siren,
            "deferred": area.defer,
            "warning": area.warn,
            "user_count": area.user_count,
        }

    def _require_control(self) -> None:
        enabled = self._entry.options.get(
            CONF_ENABLE_AREA_CONTROL,
            self._entry.data.get(CONF_ENABLE_AREA_CONTROL, DEFAULT_ENABLE_AREA_CONTROL),
        )
        if not enabled:
            raise HomeAssistantError("Area control is disabled in Integriti options")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        self._require_control()
        area = self.area
        if area is None:
            raise HomeAssistantError("Area is not available")
        await self.coordinator.client.async_control_area(area, arm=True)
        await self.coordinator.async_refresh_after_command()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        self._require_control()
        area = self.area
        if area is None:
            raise HomeAssistantError("Area is not available")
        await self.coordinator.client.async_control_area(area, arm=False)
        await self.coordinator.async_refresh_after_command()

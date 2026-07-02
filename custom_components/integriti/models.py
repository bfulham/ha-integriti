"""Data models for Inner Range Integriti."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class DoorStateValue(IntEnum):
    """Integriti DState values."""

    UNLOCKED = 0
    LOCKED = 1
    TIMED_LOCK = 2
    TIMED_UNLOCK = 3


class AreaStateValue(IntEnum):
    """Integriti AState values."""

    DISARMED = 0
    ARMED = 1
    ARMED_NO_24H = 2
    DISARMED_NO_24H = 3


class RollerStateValue(IntEnum):
    """Integriti roller-door state values."""

    NOT_A_ROLLER_DOOR = 0
    FAULT = 1
    DOWN = 2
    START_GOING_UP = 3
    GOING_UP = 4
    UP = 5
    DOWN_WARNING = 6
    START_GOING_DOWN = 7
    GOING_DOWN = 8
    INITIATE_UP = 9
    INITIATE_DOWN = 10
    INHIBITED = 11


ROLLER_STATE_NAMES: dict[int, str] = {
    0: "not_a_roller_door",
    1: "fault",
    2: "down",
    3: "starting_up",
    4: "going_up",
    5: "up",
    6: "down_warning",
    7: "starting_down",
    8: "going_down",
    9: "initiate_up",
    10: "initiate_down",
    11: "inhibited",
}


@dataclass(frozen=True, slots=True)
class ApiInfo:
    """Integriti API information."""

    protocol_version: str | None = None
    product_edition: str | None = None
    product_version: str | None = None


@dataclass(frozen=True, slots=True)
class IntegritiDoorStatus:
    """Basic-status row associated with an Integriti door."""

    entity_id: str | None = None
    row_id: str | None = None
    address: str | None = None
    state: int | None = None
    state_raw: str | None = None
    licensed: bool | None = None
    is_open: bool | None = None
    dotl: bool | None = None
    silent_dotl: bool | None = None
    forced: bool | None = None
    module_missing: bool | None = None
    roller_state: int | None = None
    roller_state_raw: str | None = None
    is_override_on: bool | None = None


@dataclass(frozen=True, slots=True)
class IntegritiAreaStatus:
    """Basic-status row associated with an Integriti area."""

    entity_id: str | None = None
    row_id: str | None = None
    address: str | None = None
    state: int | None = None
    state_raw: str | None = None
    holdup: bool | None = None
    entry_state: bool | None = None
    entry_state_raw: str | None = None
    exit_state: bool | None = None
    exit_state_raw: str | None = None
    siren: bool | None = None
    pulse: bool | None = None
    confirm: bool | None = None
    defer: bool | None = None
    warn: bool | None = None
    siren_holdoff: bool | None = None
    user_count: int | None = None


@dataclass(frozen=True, slots=True)
class IntegritiDoor:
    """An Integriti door and its current basic status."""

    unique_id: str
    address: str
    control_id: str
    name: str
    description: str | None = None
    controller_id: str | None = None
    state: int | None = None
    state_raw: str | None = None
    licensed: bool | None = None
    is_open: bool | None = None
    dotl: bool | None = None
    silent_dotl: bool | None = None
    forced: bool | None = None
    module_missing: bool | None = None
    roller_state: int | None = None
    roller_state_raw: str | None = None
    is_override_on: bool | None = None
    inside_area: str | None = None
    outside_area: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def is_locked(self) -> bool | None:
        """Return effective locked state."""
        if self.state is None:
            return None
        return self.state in (DoorStateValue.LOCKED, DoorStateValue.TIMED_LOCK)

    @property
    def override_mode(self) -> str:
        """Return inferred persistent override mode."""
        if not self.is_override_on:
            return "normal"
        if self.is_locked is True:
            return "locked"
        if self.is_locked is False:
            return "unlocked"
        return "normal"


@dataclass(frozen=True, slots=True)
class IntegritiArea:
    """An Integriti security area and its current basic status."""

    unique_id: str
    address: str
    control_id: str
    name: str
    description: str | None = None
    controller_id: str | None = None
    state: int | None = None
    state_raw: str | None = None
    holdup: bool | None = None
    entry_state: bool | None = None
    entry_state_raw: str | None = None
    exit_state: bool | None = None
    exit_state_raw: str | None = None
    siren: bool | None = None
    pulse: bool | None = None
    confirm: bool | None = None
    defer: bool | None = None
    warn: bool | None = None
    siren_holdoff: bool | None = None
    user_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def is_armed(self) -> bool | None:
        """Return whether the area is armed."""
        if self.state is None:
            return None
        return self.state in (AreaStateValue.ARMED, AreaStateValue.ARMED_NO_24H)


@dataclass(frozen=True, slots=True)
class IntegritiData:
    """Coordinator data."""

    api_info: ApiInfo
    doors: dict[str, IntegritiDoor]
    areas: dict[str, IntegritiArea]

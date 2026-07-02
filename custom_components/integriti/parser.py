"""XML parsing helpers for the Integriti REST API."""

from __future__ import annotations

from collections.abc import Iterable
from xml.etree import ElementTree as ET

from .models import (
    ApiInfo,
    AreaStateValue,
    DoorStateValue,
    IntegritiArea,
    IntegritiAreaStatus,
    IntegritiDoor,
    IntegritiDoorStatus,
)


class IntegritiParseError(ValueError):
    """Raised when an Integriti XML response cannot be parsed."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _children(node: ET.Element, name: str) -> Iterable[ET.Element]:
    wanted = name.casefold()
    for child in node:
        if _local_name(child.tag).casefold() == wanted:
            yield child


def _all_elements(node: ET.Element, name: str) -> Iterable[ET.Element]:
    wanted = name.casefold()
    for child in node.iter():
        if _local_name(child.tag).casefold() == wanted:
            yield child


def _element_text(element: ET.Element) -> str | None:
    """Return the most useful text from a property element."""
    if len(element) == 0:
        return _clean(element.text)

    # Polymorphic state properties are commonly serialized as
    # <State><State>Locked</State>...</State>.
    own_name = _local_name(element.tag).casefold()
    for child in element:
        if _local_name(child.tag).casefold() == own_name and len(child) == 0:
            value = _clean(child.text)
            if value is not None:
                return value

    for child in reversed(list(element.iter())):
        if child is element or len(child) != 0:
            continue
        value = _clean(child.text)
        if value is not None:
            return value
    return _clean(element.text)


def _text(node: ET.Element, *names: str) -> str | None:
    """Return a property value, preferring direct children."""
    for name in names:
        for candidate in _children(node, name):
            value = _element_text(candidate)
            if value is not None:
                return value

    for name in names:
        candidates = list(_all_elements(node, name))
        for candidate in reversed(candidates):
            value = _element_text(candidate)
            if value is not None:
                return value
    return None


def _direct_text(node: ET.Element, *names: str) -> str | None:
    for name in names:
        for candidate in _children(node, name):
            value = _element_text(candidate)
            if value is not None:
                return value
    return None


def _attribute(node: ET.Element, *names: str) -> str | None:
    folded = {_local_name(key).casefold(): value for key, value in node.attrib.items()}
    for name in names:
        value = _clean(folded.get(name.casefold()))
        if value is not None:
            return value
    return None


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normal = value.strip().casefold()
    if normal in {"true", "1", "yes", "on", "active"}:
        return True
    if normal in {"false", "0", "no", "off", "inactive"}:
        return False
    return None


def _active(value: str | None) -> bool | None:
    """Interpret a boolean or an entry/exit state enum as active/inactive."""
    boolean = _bool(value)
    if boolean is not None:
        return boolean
    number = _int(value)
    if number is not None:
        return number != 0
    if value is None:
        return None
    key = value.replace(" ", "").replace("_", "").replace("-", "").casefold()
    if key in {"none", "idle", "normal", "clear", "notactive", "stopped"}:
        return False
    if key in {
        "active",
        "entry",
        "entrydelay",
        "exit",
        "exitdelay",
        "running",
        "started",
    }:
        return True
    return None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip(), 0)
    except (TypeError, ValueError):
        return None


def _door_state(value: str | None) -> int | None:
    number = _int(value)
    if number is not None:
        return number
    if value is None:
        return None
    key = value.replace(" ", "_").replace("-", "_").casefold()
    return {
        "unlocked": DoorStateValue.UNLOCKED,
        "locked": DoorStateValue.LOCKED,
        "timed_lock": DoorStateValue.TIMED_LOCK,
        "timedlocked": DoorStateValue.TIMED_LOCK,
        "timed_unlock": DoorStateValue.TIMED_UNLOCK,
        "timedunlocked": DoorStateValue.TIMED_UNLOCK,
    }.get(key)


def _area_state(value: str | None) -> int | None:
    number = _int(value)
    if number is not None:
        return number
    if value is None:
        return None
    key = value.replace(" ", "").replace("_", "").replace("-", "").casefold()
    return {
        "disarmed": AreaStateValue.DISARMED,
        "armed": AreaStateValue.ARMED,
        "armedno24h": AreaStateValue.ARMED_NO_24H,
        "disarmedno24h": AreaStateValue.DISARMED_NO_24H,
    }.get(key)


def _xsi_type(node: ET.Element) -> str | None:
    for key, value in node.attrib.items():
        if _local_name(key).casefold() == "type":
            return _clean(value.rsplit(":", 1)[-1])
    return None


def _rows(root: ET.Element, entity_type: str) -> list[ET.Element]:
    """Find direct or polymorphically serialized rows of an entity type."""
    wanted = entity_type.casefold()
    found: list[ET.Element] = []
    for item in root.iter():
        tag_name = _local_name(item.tag).casefold()
        type_name = (_xsi_type(item) or "").casefold()
        if tag_name == wanted or type_name == wanted:
            found.append(item)
    return found


def _reference_id(
    node: ET.Element,
    property_name: str,
    *,
    expected_type: str | None = None,
) -> str | None:
    """Return the ID from a serialized DBObject reference property."""
    expected = expected_type.casefold() if expected_type else None
    properties = list(_children(node, property_name))
    for prop in properties:
        direct_id = _attribute(prop, "ID", "Id")
        if direct_id is not None:
            return direct_id
        for ref in prop.iter():
            if _local_name(ref.tag).casefold() != "ref":
                continue
            ref_type = _attribute(ref, "Type")
            if expected and ref_type and ref_type.casefold() != expected:
                continue
            ref_id = _attribute(ref, "ID", "Id") or _direct_text(ref, "ID", "Id")
            if ref_id is not None:
                return ref_id

    # Some serializers flatten the Ref rather than wrapping it in the named
    # property. Only accept a flattened ref when the expected type matches.
    if expected:
        for ref in node.iter():
            if _local_name(ref.tag).casefold() != "ref":
                continue
            ref_type = _attribute(ref, "Type")
            if ref_type and ref_type.casefold() == expected:
                ref_id = _attribute(ref, "ID", "Id")
                if ref_id is not None:
                    return ref_id
    return None


def parse_api_info(xml: str) -> ApiInfo:
    """Parse the ApiVersion response."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid ApiVersion XML: {err}") from err
    return ApiInfo(
        protocol_version=_text(root, "ProtocolVersion", "ApiProtocolVersion"),
        product_edition=_text(root, "ProductEdition"),
        product_version=_text(root, "ProductVersion", "Version"),
    )


def parse_page_metadata(xml: str) -> tuple[int | None, int | None, int | None]:
    """Return total records, page, and page size from a paged result."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid paged XML: {err}") from err

    total = _int(
        _attribute(root, "Count", "TotalRecords", "Total")
        or _direct_text(root, "TotalRecords", "Count", "Total")
    )
    page = _int(
        _attribute(root, "PageNumber", "Page")
        or _direct_text(root, "PageNumber", "Page")
    )
    size = _int(
        _attribute(root, "PageSize") or _direct_text(root, "PageSize", "QuerySize")
    )
    return total, page, size


def parse_doors(xml: str) -> list[IntegritiDoor]:
    """Parse Door rows from a paged or single-object response."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid Door XML: {err}") from err

    result: list[IntegritiDoor] = []
    for item in _rows(root, "Door"):
        address = _attribute(item, "Address") or _direct_text(item, "Address")
        object_id = _attribute(item, "ID", "Id") or _direct_text(item, "ID", "Id")
        unique_id = object_id or address
        if unique_id is None:
            continue
        address = address or unique_id
        control_id = object_id or address
        name = (
            _direct_text(item, "Name", "DisplayName")
            or _attribute(item, "Name")
            or address
        )
        state_raw = _text(item, "State")
        roller_raw = _text(item, "RollerState")
        result.append(
            IntegritiDoor(
                unique_id=unique_id,
                address=address,
                control_id=control_id,
                name=name,
                description=_direct_text(item, "Description", "Notes"),
                controller_id=_reference_id(
                    item, "Controller", expected_type="Controller"
                )
                or _direct_text(item, "Controller", "ControllerID", "ControllerId"),
                state_id=_reference_id(
                    item, "State", expected_type="DoorState"
                ),
                state=_door_state(state_raw),
                state_raw=state_raw,
                licensed=_bool(_text(item, "Licensed")),
                is_open=_bool(_text(item, "IsOpen")),
                dotl=_bool(_text(item, "DOTL")),
                silent_dotl=_bool(_text(item, "SilentDOTL")),
                forced=_bool(_text(item, "Forced")),
                module_missing=_bool(_text(item, "ModuleMissing")),
                roller_state=_int(roller_raw),
                roller_state_raw=roller_raw,
                is_override_on=_bool(_text(item, "IsOverrideOn")),
                inside_area=_text(item, "InsideArea"),
                outside_area=_text(item, "OutsideArea"),
                raw={"address": address, "id": object_id},
            )
        )
    return result


def parse_areas(xml: str) -> list[IntegritiArea]:
    """Parse Area rows from a paged or single-object response."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid Area XML: {err}") from err

    result: list[IntegritiArea] = []
    for item in _rows(root, "Area"):
        address = _attribute(item, "Address") or _direct_text(item, "Address")
        object_id = _attribute(item, "ID", "Id") or _direct_text(item, "ID", "Id")
        unique_id = object_id or address
        if unique_id is None:
            continue
        address = address or unique_id
        control_id = object_id or address
        name = (
            _direct_text(item, "Name", "DisplayName")
            or _attribute(item, "Name")
            or address
        )
        state_raw = _text(item, "State")
        entry_raw = _text(item, "EntryState")
        exit_raw = _text(item, "ExitState")
        result.append(
            IntegritiArea(
                unique_id=unique_id,
                address=address,
                control_id=control_id,
                name=name,
                description=_direct_text(item, "Description", "Notes"),
                controller_id=_reference_id(
                    item, "Controller", expected_type="Controller"
                )
                or _direct_text(item, "Controller", "ControllerID", "ControllerId"),
                state_id=_reference_id(
                    item, "State", expected_type="AreaState"
                ),
                state=_area_state(state_raw),
                state_raw=state_raw,
                holdup=_bool(_text(item, "Holdup")),
                entry_state=_active(entry_raw),
                entry_state_raw=entry_raw,
                exit_state=_active(exit_raw),
                exit_state_raw=exit_raw,
                siren=_bool(_text(item, "Siren")),
                pulse=_bool(_text(item, "Pulse")),
                confirm=_bool(_text(item, "Confirm")),
                defer=_bool(_text(item, "Defer")),
                warn=_bool(_text(item, "Warn")),
                siren_holdoff=_bool(_text(item, "SirenHoldoff")),
                user_count=_int(_text(item, "UserCount")),
                raw={"address": address, "id": object_id},
            )
        )
    return result


def parse_door_states(xml: str) -> list[IntegritiDoorStatus]:
    """Parse standalone DoorState/EntityState rows."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid DoorState XML: {err}") from err

    result: list[IntegritiDoorStatus] = []
    for item in _rows(root, "DoorState"):
        state_raw = _direct_text(item, "State") or _text(item, "State")
        roller_raw = _direct_text(item, "RollerState") or _text(item, "RollerState")
        result.append(
            IntegritiDoorStatus(
                entity_id=_reference_id(item, "Entity", expected_type="Door")
                or _direct_text(item, "DoorID", "DoorId", "EntityID", "EntityId"),
                row_id=_attribute(item, "ID", "Id")
                or _direct_text(item, "ID", "Id"),
                address=_attribute(item, "Address")
                or _direct_text(item, "Address", "EntityAddress"),
                state=_door_state(state_raw),
                state_raw=state_raw,
                licensed=_bool(_text(item, "Licensed")),
                is_open=_bool(_text(item, "IsOpen")),
                dotl=_bool(_text(item, "DOTL")),
                silent_dotl=_bool(_text(item, "SilentDOTL")),
                forced=_bool(_text(item, "Forced")),
                module_missing=_bool(_text(item, "ModuleMissing")),
                roller_state=_int(roller_raw),
                roller_state_raw=roller_raw,
                is_override_on=_bool(_text(item, "IsOverrideOn")),
            )
        )
    return result


def parse_area_states(xml: str) -> list[IntegritiAreaStatus]:
    """Parse standalone AreaState/EntityState rows."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid AreaState XML: {err}") from err

    result: list[IntegritiAreaStatus] = []
    for item in _rows(root, "AreaState"):
        state_raw = _direct_text(item, "State") or _text(item, "State")
        entry_raw = _direct_text(item, "EntryState") or _text(item, "EntryState")
        exit_raw = _direct_text(item, "ExitState") or _text(item, "ExitState")
        result.append(
            IntegritiAreaStatus(
                entity_id=_reference_id(item, "Entity", expected_type="Area")
                or _direct_text(item, "AreaID", "AreaId", "EntityID", "EntityId"),
                row_id=_attribute(item, "ID", "Id")
                or _direct_text(item, "ID", "Id"),
                address=_attribute(item, "Address")
                or _direct_text(item, "Address", "EntityAddress"),
                state=_area_state(state_raw),
                state_raw=state_raw,
                holdup=_bool(_text(item, "Holdup")),
                entry_state=_active(entry_raw),
                entry_state_raw=entry_raw,
                exit_state=_active(exit_raw),
                exit_state_raw=exit_raw,
                siren=_bool(_text(item, "Siren")),
                pulse=_bool(_text(item, "Pulse")),
                confirm=_bool(_text(item, "Confirm")),
                defer=_bool(_text(item, "Defer")),
                warn=_bool(_text(item, "Warn")),
                siren_holdoff=_bool(_text(item, "SirenHoldoff")),
                user_count=_int(_text(item, "UserCount")),
            )
        )
    return result

"""XML parsing helpers for the Integriti REST API."""

from __future__ import annotations

from collections.abc import Iterable
from xml.etree import ElementTree as ET

from .models import ApiInfo, AreaStateValue, DoorStateValue, IntegritiArea, IntegritiDoor


class IntegritiParseError(ValueError):
    """Raised when an Integriti XML response cannot be parsed."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _all_elements(node: ET.Element, name: str) -> Iterable[ET.Element]:
    wanted = name.casefold()
    for child in node.iter():
        if _local_name(child.tag).casefold() == wanted:
            yield child


def _text(node: ET.Element, *names: str) -> str | None:
    for name in names:
        candidates = list(_all_elements(node, name))
        # Prefer a leaf value. State containers often contain another State element.
        for candidate in reversed(candidates):
            if len(candidate) == 0:
                value = _clean(candidate.text)
                if value is not None:
                    return value
        for candidate in reversed(candidates):
            value = _clean(candidate.text)
            if value is not None:
                return value
    return None


def _attribute(node: ET.Element, *names: str) -> str | None:
    folded = {key.casefold(): value for key, value in node.attrib.items()}
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


def _rows(root: ET.Element, entity_type: str) -> list[ET.Element]:
    entity_type_cf = entity_type.casefold()
    rows_nodes = [item for item in root.iter() if _local_name(item.tag).casefold() == "rows"]
    scope = rows_nodes[0] if rows_nodes else root
    rows = [
        item
        for item in scope.iter()
        if _local_name(item.tag).casefold() == entity_type_cf
    ]
    if not rows and _local_name(root.tag).casefold() == entity_type_cf:
        rows = [root]
    return rows


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
    return (_int(_text(root, "TotalRecords")), _int(_text(root, "Page")), _int(_text(root, "PageSize")))


def parse_doors(xml: str) -> list[IntegritiDoor]:
    """Parse Door rows from a paged or single-object response."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as err:
        raise IntegritiParseError(f"Invalid Door XML: {err}") from err

    result: list[IntegritiDoor] = []
    for item in _rows(root, "Door"):
        address = _attribute(item, "Address") or _text(item, "Address")
        object_id = _attribute(item, "ID", "Id") or _text(item, "ID", "Id")
        unique_id = object_id or address
        if unique_id is None:
            continue
        address = address or unique_id
        control_id = object_id or address
        name = _text(item, "Name", "DisplayName") or _attribute(item, "Name") or address
        state_raw = _text(item, "State")
        roller_raw = _text(item, "RollerState")
        result.append(
            IntegritiDoor(
                unique_id=unique_id,
                address=address,
                control_id=control_id,
                name=name,
                description=_text(item, "Description", "Notes"),
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
        address = _attribute(item, "Address") or _text(item, "Address")
        object_id = _attribute(item, "ID", "Id") or _text(item, "ID", "Id")
        unique_id = object_id or address
        if unique_id is None:
            continue
        address = address or unique_id
        control_id = object_id or address
        name = _text(item, "Name", "DisplayName") or _attribute(item, "Name") or address
        state_raw = _text(item, "State")
        result.append(
            IntegritiArea(
                unique_id=unique_id,
                address=address,
                control_id=control_id,
                name=name,
                description=_text(item, "Description", "Notes"),
                state=_area_state(state_raw),
                state_raw=state_raw,
                holdup=_bool(_text(item, "Holdup")),
                entry_state=_bool(_text(item, "EntryState")),
                exit_state=_bool(_text(item, "ExitState")),
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

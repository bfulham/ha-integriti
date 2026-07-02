from xml.etree import ElementTree as ET

from custom_components.integriti.api import IntegritiClient


def _text(root: ET.Element, name: str) -> str | None:
    child = root.find(name)
    return None if child is None else child.text


def test_door_action_uses_database_object_id() -> None:
    root = ET.fromstring(
        IntegritiClient._build_door_action(
            "5066553875759108", on_assert=3, on_deassert=2, unlock_seconds=10
        )
    )
    ref = root.find("./Entity/Ref")
    assert ref is not None
    assert ref.attrib == {"Type": "Door", "ID": "5066553875759108"}
    assert _text(root, "OnAssert") == "3"
    assert _text(root, "OnDeAssert") == "2"
    assert _text(root, "UnlockTimeTicks") == "100000000"


def test_area_action_uses_database_object_id() -> None:
    root = ET.fromstring(
        IntegritiClient._build_area_action("5066553875759200", arm=False)
    )
    ref = root.find("./Entity/Ref")
    assert ref is not None
    assert ref.attrib == {"Type": "Area", "ID": "5066553875759200"}
    assert _text(root, "OnAssert") == "2"
    assert _text(root, "OnDeAssert") == "1"


def test_door_action_can_use_address_reference() -> None:
    root = ET.fromstring(
        IntegritiClient._build_door_action(
            None, address="D38", on_assert=2, on_deassert=1
        )
    )
    ref = root.find("./Entity/Ref")
    assert ref is not None
    assert ref.attrib == {"Type": "Door", "Address": "D38"}


def test_area_action_can_use_address_as_legacy_id() -> None:
    root = ET.fromstring(
        IntegritiClient._build_area_action(
            None, address="A47", address_as_id=True, arm=True
        )
    )
    ref = root.find("./Entity/Ref")
    assert ref is not None
    assert ref.attrib == {"Type": "Area", "ID": "A47"}


def test_address_filter_matches_system_designer_shape() -> None:
    root = ET.fromstring(IntegritiClient._build_address_filter("D38"))
    assert root.attrib[
        "{http://www.w3.org/2001/XMLSchema-instance}type"
    ] == "AggregateExpression"
    assert root.findtext("OperatorType") == "And"
    expression = root.find("./SubExpressions/FilterExpression")
    assert expression is not None
    assert expression.findtext("PropertyName") == "Address"
    assert expression.findtext("OperatorType") == "Equals"

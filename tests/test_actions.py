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

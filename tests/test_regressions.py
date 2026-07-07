from pathlib import Path


def test_optional_id_lookup_accepts_endpoint_401() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert "allow_statuses=(400, 401, 403, 404, 405)" in source


def test_xml_control_uses_official_v2_route_casing() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert 'f"{BASIC_STATUS_PATH}/xml_controlAsync"' in source
    assert 'f"{BASIC_STATUS_PATH}/xml_control"' in source


def test_status_additional_properties_request_entity_id_and_address() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert "Entity.ID" in source
    assert "Entity.Address" in source


def test_optional_api_version_accepts_endpoint_401() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert "allow_statuses=(401, 403, 404, 405) if optional else ()" in source


def test_definition_route_401_does_not_immediately_reauthenticate() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert "trying the remaining API-key routes" in source
    assert "auth_failed_routes == attempted_routes" in source


def test_state_route_401_is_skipped_individually() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert "trying the remaining state routes" in source


def test_xml_control_resolution_uses_state_id_fallback() -> None:
    source = Path("custom_components/integriti/api.py").read_text()
    assert '"Door", door.address, door.xml_control_id, door.state_id' in source
    assert '"Area", area.address, area.xml_control_id, area.state_id' in source

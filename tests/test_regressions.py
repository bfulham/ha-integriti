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

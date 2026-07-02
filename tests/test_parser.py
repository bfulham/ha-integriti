from custom_components.integriti.parser import (
    extract_database_object_id,
    parse_area_states,
    parse_areas,
    parse_door_states,
    parse_doors,
    parse_page_metadata,
)


def test_parse_door_page_with_nested_state():
    xml = """
    <PagedQueryResult>
      <TotalRecords>1</TotalRecords><Page>1</Page><PageSize>500</PageSize>
      <Rows><Door Address="c1.d1" ID="5066553875759108">
        <Name>Front Door</Name><State><State>Locked</State><Licensed>true</Licensed>
        <IsOpen>false</IsOpen><DOTL>false</DOTL><Forced>false</Forced>
        <ModuleMissing>false</ModuleMissing><RollerState>0</RollerState>
        <IsOverrideOn>true</IsOverrideOn></State>
      </Door></Rows>
    </PagedQueryResult>
    """
    door = parse_doors(xml)[0]
    assert door.address == "c1.d1"
    assert door.is_locked is True
    assert door.override_mode == "locked"


def test_parse_standalone_door_state_polymorphic():
    xml = """
    <Results Count="1" PageNumber="1" PageSize="500"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <EntityState xsi:type="DoorState" ID="9001">
        <Entity><Ref Type="Door" ID="5066553875759108" /></Entity>
        <State>Timed_Unlock</State>
        <Licensed>true</Licensed><IsOpen>true</IsOpen>
        <DOTL>false</DOTL><SilentDOTL>false</SilentDOTL>
        <Forced>false</Forced><ModuleMissing>false</ModuleMissing>
        <RollerState>0</RollerState><IsOverrideOn>false</IsOverrideOn>
      </EntityState>
    </Results>
    """
    status = parse_door_states(xml)[0]
    assert status.entity_id == "5066553875759108"
    assert status.state == 3
    assert status.is_open is True
    assert parse_page_metadata(xml) == (1, 1, 500)


def test_parse_area_page_with_nested_state():
    xml = """
    <PagedQueryResult><Rows><Area Address="A1" ID="1234">
      <Name>Main Building</Name><State><State>1</State><Holdup>false</Holdup>
      <EntryState>false</EntryState><ExitState>true</ExitState><Siren>false</Siren>
      <UserCount>4</UserCount></State>
    </Area></Rows></PagedQueryResult>
    """
    area = parse_areas(xml)[0]
    assert area.is_armed is True
    assert area.exit_state is True
    assert area.user_count == 4


def test_parse_standalone_area_state():
    xml = """
    <Results Count="1" PageNumber="1" PageSize="500">
      <AreaState ID="8001">
        <Entity><Ref Type="Area" ID="1234" /></Entity>
        <State>Disarmed</State><Holdup>false</Holdup>
        <EntryState>0</EntryState><ExitState>ExitDelay</ExitState>
        <Siren>false</Siren><Pulse>false</Pulse><Confirm>false</Confirm>
        <Defer>false</Defer><Warn>true</Warn><SirenHoldoff>false</SirenHoldoff>
        <UserCount>3</UserCount>
      </AreaState>
    </Results>
    """
    status = parse_area_states(xml)[0]
    assert status.entity_id == "1234"
    assert status.state == 0
    assert status.entry_state is False
    assert status.exit_state is True
    assert status.warn is True
    assert status.user_count == 3


def test_parse_door_state_reference() -> None:
    xml = """
    <Results Count="1" PageNumber="1" PageSize="1">
      <Door ID="door-1" Address="D01">
        <Name>Front Door</Name>
        <State><Ref Type="DoorState" ID="door-state-1" /></State>
      </Door>
    </Results>
    """
    door = parse_doors(xml)[0]
    assert door.state_id == "door-state-1"


def test_parse_area_state_reference() -> None:
    xml = """
    <Results Count="1" PageNumber="1" PageSize="1">
      <Area ID="area-1" Address="A01">
        <Name>Office</Name>
        <State><Ref Type="AreaState" ID="area-state-1" /></State>
      </Area>
    </Results>
    """
    area = parse_areas(xml)[0]
    assert area.state_id == "area-state-1"


def test_parse_generic_entity_state_with_value_and_summary():
    xml = """
    <Results Count="2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <EntityState xsi:type="DoorState" ID="door-state-1">
        <Entity><Ref Type="Door" Address="D38" /></Entity>
        <Summary>Workshop Entry</Summary>
        <Value>1</Value><IsOpen>false</IsOpen><IsOverrideOn>false</IsOverrideOn>
      </EntityState>
      <EntityState xsi:type="AreaState" ID="area-state-1">
        <Entity><Ref Type="Area" ID="area-1" /></Entity>
        <Summary>Workshop</Summary>
        <Value>0</Value><Siren>false</Siren><UserCount>2</UserCount>
      </EntityState>
    </Results>
    """
    door = parse_door_states(xml)[0]
    area = parse_area_states(xml)[0]
    assert door.entity_id == "D38"
    assert door.name == "Workshop Entry"
    assert door.state == 1
    assert area.entity_id == "area-1"
    assert area.name == "Workshop"
    assert area.state == 0


def test_parse_area_summary_name():
    xml = """
    <Results><Area ID="area-guid" Address="A01">
      <Summary>Main Building</Summary>
      <State><Ref Type="AreaState" ID="state-guid" /></State>
    </Area></Results>
    """
    area = parse_areas(xml)[0]
    assert area.name == "Main Building"
    assert area.state_id == "state-guid"


def test_reference_type_is_not_treated_as_a_door_row() -> None:
    xml = """
    <Results xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Door ID="5066553875759108" Address="D38">
        <Name>Workshop Entry</Name>
        <State><Ref Type="DoorState" ID="state-1" /></State>
        <InsideArea><Ref Type="Area" ID="area-1" /></InsideArea>
      </Door>
    </Results>
    """
    doors = parse_doors(xml)
    assert len(doors) == 1
    assert doors[0].xml_control_id == "5066553875759108"
    assert doors[0].address == "D38"


def test_reference_type_is_not_treated_as_an_area_row() -> None:
    xml = """
    <Results xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Area ID="5066553875759200" Address="A1">
        <Name>Main Building</Name>
        <State><Ref Type="AreaState" ID="state-2" /></State>
        <Parent><Ref Type="Area" ID="parent-area" /></Parent>
      </Area>
    </Results>
    """
    areas = parse_areas(xml)
    assert len(areas) == 1
    assert areas[0].xml_control_id == "5066553875759200"
    assert areas[0].name == "Main Building"


def test_polymorphic_entity_state_still_uses_xsi_type() -> None:
    xml = """
    <Results xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <EntityState xsi:type="DoorState" ID="state-1">
        <Entity><Ref Type="Door" ID="5066553875759108" Address="D38" /></Entity>
        <State>Locked</State>
      </EntityState>
    </Results>
    """
    rows = parse_door_states(xml)
    assert len(rows) == 1
    assert rows[0].entity_object_id == "5066553875759108"
    assert rows[0].address == "D38"


def test_extract_database_object_id_from_ref_response() -> None:
    xml = """
    <Results Count="1">
      <EntityState>
        <Entity><Ref Type="Door" ID="5066553875759108" Address="D38" /></Entity>
      </EntityState>
    </Results>
    """
    assert (
        extract_database_object_id(xml, "Door", "D38")
        == "5066553875759108"
    )


def test_extract_database_object_id_from_filtered_full_object() -> None:
    xml = """
    <Results Count="1">
      <Door>
        <EntityID>5066553875759108</EntityID>
        <Address>D38</Address>
        <Name>Workshop Entry</Name>
      </Door>
    </Results>
    """
    assert (
        extract_database_object_id(xml, "Door", "D38")
        == "5066553875759108"
    )


def test_parse_entity_id_element_as_xml_control_id() -> None:
    xml = """
    <Results><Area><EntityID>4785078899048449</EntityID>
      <Address>A47</Address><Name>Workshop</Name></Area></Results>
    """
    area = parse_areas(xml)[0]
    assert area.xml_control_id == "4785078899048449"

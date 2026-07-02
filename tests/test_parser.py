from custom_components.integriti.parser import (
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

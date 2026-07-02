from custom_components.integriti.parser import parse_areas, parse_doors


def test_parse_door_page():
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


def test_parse_area_page():
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

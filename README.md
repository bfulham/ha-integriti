# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.8

This release fixes database-ID discovery for normal DoorAction and AreaAction controls.

### Database-ID and control fixes

- Explicitly requests `Entity.ID` and `Entity.Address` with DoorState and AreaState.
- Supports multiple Integriti object-reference XML shapes, including nested full `Door`/`Area` objects and typed `Entity` elements.
- Merges state rows from `DoorState`/`AreaState` and polymorphic `EntityState` routes instead of stopping at the first non-empty response.
- Retains the long database object ID from state references and uses it in `<Ref Type="Door|Area" ID="..." />`.
- Does not send invalid `Address="D38"` or `ID="A47"` XML control fallbacks.
- One-shot actions continue to use the confirmed values:
  - Arm / lock: `OnAssert=1`, `OnDeAssert=0`
  - Disarm / unlock: `OnAssert=2`, `OnDeAssert=0`
- Dedicated Grant Access and persistent override controls are unchanged.
- Immediate and delayed state refreshes after commands remain enabled.

## Installation with HACS

1. Add `https://github.com/bfulham/ha-integriti` as a custom integration repository in HACS.
2. Install **Inner Range Integriti**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **Inner Range Integriti**.

For a manual installation, copy `custom_components/integriti` into the Home Assistant configuration directory and restart Home Assistant.

## Configuration

The setup flow asks for:

- Integriti host
- Port
- HTTP or HTTPS
- SSL certificate verification
- REST API path, normally `/restapi`
- API key

No username or password is used.

## API permissions

The API key should have permission to:

- Read Door and Area definitions
- Read `DoorState`, `AreaState`, or `EntityState`
- Execute Basic Status and Control actions
- Use XML control

Door override permissions are required only for the override select.

## Notes

- Door lock and unlock operations use normal XML actions, not persistent overrides.
- Persistent overrides are only applied from the door override select.
- Integriti security Areas are represented as Home Assistant alarm-control-panel entities.
- The API key is redacted from Home Assistant diagnostics.

# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.7

This release corrects one-shot XML DoorAction and AreaAction command generation.

### Control fix

- `OnAssert` now contains the requested action.
- `OnDeAssert` is now always `0` (`No Action`) for REST XML control.
- Area arm: `OnAssert=1`, `OnDeAssert=0`.
- Area disarm: `OnAssert=2`, `OnDeAssert=0`.
- Door lock: `OnAssert=1`, `OnDeAssert=0`.
- Door unlock: `OnAssert=2`, `OnDeAssert=0`.
- DoorAction grant-access fallback: `OnAssert=3`, `OnDeAssert=0`.
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

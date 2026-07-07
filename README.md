# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.10

This release fixes normal DoorAction and AreaAction control on systems where the API-key status response exposes the short Integriti address as `xml_control_id` and the long numeric object ID as `state_id`.

### Control fixes

- Door Lock and Unlock now try `door.state_id` as the XML control reference when `door.xml_control_id` is only the short address such as `D38`.
- Area Arm and Disarm now try `area.state_id` as the XML control reference when `area.xml_control_id` is only the short address such as `A47`.
- Keeps the one-shot XML action format confirmed from Integriti:
  - Arm / Lock: `OnAssert=1`, `OnDeAssert=0`
  - Disarm / Unlock: `OnAssert=2`, `OnDeAssert=0`
- Grant Access still uses the dedicated API endpoint first.
- Persistent Door Override remains separate and is only used by the override select.
- The false optional-route API-key failures fixed in v0.1.9 remain fixed.

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

# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.6

This release fixes a false “API key rejected” error when normal DoorAction or AreaAction control attempted optional database-ID lookup routes.

### Control fixes

- HTTP 401 from optional ID-resolution routes is now treated as “route unavailable”, not as a rejected API key.
- The integration continues to the XML control request using any discovered object ID or the compatible address reference fallbacks.
- Unavailable resolver routes are cached so they are not retried for every command.
- XML control now uses the exact lowercase route names from Inner Range's official Postman collection: `/xml_controlAsync` and `/xml_control`.
- If the actual XML control endpoint rejects API-key authentication, Home Assistant now reports a control-permission error instead of incorrectly starting API-key reauthentication.
- Grant Access and persistent override behavior are unchanged.
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

# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.9

This release fixes false API-key rejection and unwanted reauthentication.

### Authentication and route-permission fixes

- `ApiVersion` returning HTTP 401 is now treated as an unavailable optional
  metadata endpoint rather than an invalid API key.
- Door and Area discovery no longer stops when one optional route returns 401.
  Integriti can reject `/v2/user/...` while allowing `/v2/basicstatus/...` for
  the same valid API key.
- Reauthentication is only started when every usable definition route rejects
  the API key.
- DoorState, AreaState, and EntityState routes with separate permissions are
  skipped individually when they return 401.
- A valid response from any supported Door or Area definition route keeps the
  config entry loaded.

The database-ID, XML-control, Grant Access, override, and post-command refresh
changes from v0.1.8 remain included.

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

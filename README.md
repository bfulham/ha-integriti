# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.4

This release corrects generic XML door and area control targeting.

### XML control fixes

- Door and Area XML actions now use the Integriti database object ID, not an address such as `D38` or `A1`.
- If the normal discovery response omits the database ID, the integration resolves it with a filtered query immediately before the first XML command and caches it.
- XML control now tries the synchronous `/XML_Control` endpoint first, matching Integriti's generated REST command.
- XML bodies are sent as `application/xml`.
- The parser no longer mistakes `<Ref Type="Door">` or `<Ref Type="Area">` elements for full Door or Area records.
- Diagnostics show `control_id`, `xml_control_id`, address, and state ID separately.

### Controls

- The lock entity uses normal `DoorAction` XML commands for lock, unlock, and grant access.
- The override select alone uses persistent door overrides.
- Area arm and disarm use normal `AreaAction` XML commands.
- State refreshes run immediately and again after approximately 1, 3, and 7 seconds.

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

- Door lock/unlock and grant-access operations use XML actions.
- Persistent overrides are only applied from the door override select.
- Integriti security Areas are represented as Home Assistant alarm-control-panel entities.
- The API key is redacted from Home Assistant diagnostics.

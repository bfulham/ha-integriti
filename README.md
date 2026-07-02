# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.5

This release fixes DoorAction and AreaAction target resolution on servers that expose doors and areas by addresses such as `D38` and `A47` but omit the long Integriti database object ID from the normal discovery response.

### Control fixes

- Database IDs are now resolved through several compatible API paths:
  - Direct full-object lookup
  - Address-filtered GET lookup
  - The documented `GetFilteredEntities` AggregateExpression
  - DoorState or AreaState entity references
- Additional ID field names such as `EntityID`, `ObjectID`, and `DatabaseID` are recognised.
- XML control now tries `/XML_ControlAsync` first so Integriti can report an unresolved or failed action instead of the integration accepting an immediate acknowledgement.
- If a server does not expose the long object ID, the integration falls back to the alternate Address-based reference formats used by some Integriti serializers.
- Grant Access uses the dedicated `/GrantAccess/{door}` endpoint first and sends an explicit XML content type and XML declaration.
- Normal lock and unlock remain XML DoorActions; only the override select applies a persistent door override.
- Area arm and disarm remain XML AreaActions.
- State refreshes run immediately and again after approximately 1, 3, and 7 seconds after a successful command.

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

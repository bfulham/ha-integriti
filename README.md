# Inner Range Integriti for Home Assistant

A local Home Assistant integration for Inner Range Integriti using the REST API with **API-key-only authentication**.

## v0.1.3

This release provides native Home Assistant devices and entities for Integriti doors and security areas.

### Doors

- Lock entity using normal Integriti XML `DoorAction` commands
- Lock and unlock no longer apply persistent overrides
- Grant access through an XML `DoorAction`
- Separate override select for `Normal`, `Locked`, and `Unlocked`
- Door contact, held-open, forced-open, connectivity, and roller state entities
- Door state read from typed `DoorState` or polymorphic `EntityState` responses

### Areas

- Alarm control panel with Arm Away and Disarm
- XML `AreaAction` control using the System Designer serialization order
- Friendly area names from Area definitions or EntityState summaries
- Holdup, siren, warning, confirmation, deferred-arming, and siren-holdoff entities
- Entry delay, exit delay, and user-count sensors
- Area state read from typed `AreaState` or polymorphic `EntityState` responses

### State refresh after control

After a door or area command, the integration refreshes immediately and again after approximately 1, 3, and 7 seconds. This allows controller state changes to appear without waiting for the normal polling interval.

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

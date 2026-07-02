# Inner Range Integriti for Home Assistant

Experimental native-style Home Assistant integration for the Inner Range Integriti REST API.

## v0.1.0 features

- UI config flow with **API-key-only authentication**
- Multiple Integriti servers
- Reauthentication, reconfiguration, options flow, and diagnostics
- Automatic discovery of every API-visible door and security area
- One Home Assistant device per Integriti door or area
- Door lock entities with Lock, Unlock, and Open/Grant Access
- Door override-mode selects: Normal, Locked, and Unlocked
- Door contact, held-open, forced-open, and connectivity binary sensors
- Roller-door state sensor when a door reports roller state
- Area alarm control panels with Arm Away and Disarm
- Area holdup, siren, warning, confirmation, deferred, and siren-holdoff sensors
- Area entry delay, exit delay, and user-count sensors

## Installation with HACS

1. In HACS, open **Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add your repository URL and select **Integration**.
4. Install **Inner Range Integriti**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration** and search for `Integriti`.

For manual installation, copy `custom_components/integriti` into the Home Assistant `custom_components` directory and restart Home Assistant.

## Integriti configuration

Create an API key in Integriti with permission to read Basic Status for Door and Area objects. Add control permissions only when Home Assistant should be allowed to control doors or areas.

The default connection values are:

- Port: `80`
- REST path: `/restapi`
- API version routes: `/v2/basicstatus`, `/v2/user`, and `/ApiVersion`
- Authentication: `API-KEY` HTTP header only

No Integriti operator username or password is stored or sent.

## Entity behaviour

### Doors

- **Open** calls `GrantAccess` for the configured number of seconds.
- **Unlock** applies `OverrideUnlocked`.
- **Lock** applies `OverrideLocked`.
- Set **Override mode** to `Normal` to call `RemoveDoorOverride`.
- Physical open/closed state remains a separate door-contact binary sensor.

### Areas

- **Arm Away** sends a normal `AreaAction` with Arm on the asserted edge.
- **Disarm** sends a normal `AreaAction` with Disarm on the asserted edge.
- Siren or holdup state maps to Home Assistant `triggered`.
- Exit and entry states map to `arming` and `pending`.

## Important v0.1.0 notes

This release was built from the official Integriti v2 Postman collection and the API/action models included with Integriti. Integriti installations may differ by product version, REST licence, operator/API-key permissions, and enabled object properties.

The parser accepts both numeric and named Integriti state values and supports both Basic Status and User Management discovery routes. If your server returns a different XML shape, download diagnostics and include them with an issue after removing any site-sensitive names.

Area control is security-sensitive. It can be disabled under the integration options. Door control can also be disabled independently.

## Debug logging

```yaml
logger:
  default: info
  logs:
    custom_components.integriti: debug
```

## License

MIT

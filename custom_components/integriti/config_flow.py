"""Config flow for Inner Range Integriti."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    IntegritiAuthenticationError,
    IntegritiClient,
    IntegritiConnectionError,
    IntegritiError,
    IntegritiPermissionError,
)
from .const import (
    CONF_API_KEY,
    CONF_API_PATH,
    CONF_ENABLE_AREA_CONTROL,
    CONF_ENABLE_DOOR_CONTROL,
    CONF_GRANT_ACCESS_SECONDS,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_API_PATH,
    DEFAULT_ENABLE_AREA_CONTROL,
    DEFAULT_ENABLE_DOOR_CONTROL,
    DEFAULT_GRANT_ACCESS_SECONDS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL_PORT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _normalise_path(path: str) -> str:
    path = path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/")


def _clean_host(value: str) -> str:
    """Return only the hostname portion of a host or URL value."""
    value = value.strip().rstrip("/")
    parsed = urlsplit(value if "://" in value else f"//{value}")
    return parsed.hostname or value


def _make_url(data: dict[str, Any]) -> str:
    scheme = "https" if data[CONF_USE_SSL] else "http"
    host = _clean_host(str(data[CONF_HOST]))
    return f"{scheme}://{host}:{data[CONF_PORT]}{_normalise_path(data[CONF_API_PATH])}"


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    client = IntegritiClient(
        session=async_get_clientsession(hass),
        base_url=_make_url(data),
        api_key=data[CONF_API_KEY],
        verify_ssl=data[CONF_VERIFY_SSL],
    )
    # ApiVersion may be forbidden for an otherwise valid API-key role.
    await client.async_get_api_info(optional=True)
    doors = await client.async_get_doors()
    areas = await client.async_get_areas()
    if not doors and not areas:
        raise IntegritiPermissionError(
            "The API key cannot read any Door or Area entities"
        )


def _connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    use_ssl = bool(defaults.get(CONF_USE_SSL, False))
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT,
                default=defaults.get(
                    CONF_PORT, DEFAULT_SSL_PORT if use_ssl else DEFAULT_PORT
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_USE_SSL, default=use_ssl): bool,
            vol.Required(
                CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True)
            ): bool,
            vol.Required(
                CONF_API_PATH, default=defaults.get(CONF_API_PATH, DEFAULT_API_PATH)
            ): str,
            vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
        }
    )


class IntegritiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Integriti config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_API_PATH] = _normalise_path(user_input[CONF_API_PATH])
            try:
                await _validate(self.hass, user_input)
            except IntegritiAuthenticationError:
                errors["base"] = "invalid_auth"
            except IntegritiPermissionError:
                errors["base"] = "insufficient_permissions"
            except IntegritiConnectionError:
                errors["base"] = "cannot_connect"
            except IntegritiError:
                errors["base"] = "invalid_response"
            else:
                unique_id = _make_url(user_input).casefold()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Integriti ({user_input[CONF_HOST]})", data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None:
            new_data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            try:
                await _validate(self.hass, new_data)
            except IntegritiAuthenticationError:
                errors["base"] = "invalid_auth"
            except IntegritiPermissionError:
                errors["base"] = "insufficient_permissions"
            except IntegritiConnectionError:
                errors["base"] = "cannot_connect"
            except IntegritiError:
                errors["base"] = "invalid_response"
            else:
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_API_PATH] = _normalise_path(user_input[CONF_API_PATH])
            try:
                await _validate(self.hass, user_input)
            except IntegritiAuthenticationError:
                errors["base"] = "invalid_auth"
            except IntegritiPermissionError:
                errors["base"] = "insufficient_permissions"
            except IntegritiConnectionError:
                errors["base"] = "cannot_connect"
            except IntegritiError:
                errors["base"] = "invalid_response"
            else:
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return IntegritiOptionsFlow()


class IntegritiOptionsFlow(config_entries.OptionsFlow):
    """Handle Integriti runtime options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    CONF_GRANT_ACCESS_SECONDS,
                    default=data.get(
                        CONF_GRANT_ACCESS_SECONDS, DEFAULT_GRANT_ACCESS_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
                vol.Required(
                    CONF_ENABLE_DOOR_CONTROL,
                    default=data.get(
                        CONF_ENABLE_DOOR_CONTROL, DEFAULT_ENABLE_DOOR_CONTROL
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_AREA_CONTROL,
                    default=data.get(
                        CONF_ENABLE_AREA_CONTROL, DEFAULT_ENABLE_AREA_CONTROL
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

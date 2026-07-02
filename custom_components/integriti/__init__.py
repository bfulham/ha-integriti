"""Inner Range Integriti integration."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntegritiClient
from .const import (
    CONF_API_KEY,
    CONF_API_PATH,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_API_PATH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IntegritiCoordinator


def _base_url(entry: ConfigEntry) -> str:
    scheme = "https" if entry.data.get(CONF_USE_SSL, False) else "http"
    host_value = str(entry.data[CONF_HOST]).strip().rstrip("/")
    parsed = urlsplit(host_value if "://" in host_value else f"//{host_value}")
    host = parsed.hostname or host_value
    port = int(entry.data[CONF_PORT])
    path = str(entry.data.get(CONF_API_PATH, DEFAULT_API_PATH)).strip()
    if not path.startswith("/"):
        path = f"/{path}"
    path = path.rstrip("/")
    return f"{scheme}://{host}:{port}{path}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Integriti from a config entry."""
    session = async_get_clientsession(hass)
    client = IntegritiClient(
        session=session,
        base_url=_base_url(entry),
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    scan_interval = int(
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
    )
    coordinator = IntegritiCoordinator(
        hass,
        entry,
        client,
        timedelta(seconds=scan_interval),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Integriti config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when entry options change."""
    await hass.config_entries.async_reload(entry.entry_id)

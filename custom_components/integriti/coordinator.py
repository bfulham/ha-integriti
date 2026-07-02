"""Data coordinator for Inner Range Integriti."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    IntegritiAuthenticationError,
    IntegritiClient,
    IntegritiConnectionError,
    IntegritiError,
    IntegritiPermissionError,
)
from .const import DOMAIN
from .models import IntegritiData

_LOGGER = logging.getLogger(__name__)
_POST_COMMAND_DELAYS = (1.0, 3.0, 7.0)


class IntegritiCoordinator(DataUpdateCoordinator[IntegritiData]):
    """Coordinate Integriti API updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: IntegritiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=update_interval,
            config_entry=entry,
            always_update=False,
        )
        self.client = client
        self._delayed_refresh_tasks: set[asyncio.Task[None]] = set()

    async def _async_update_data(self) -> IntegritiData:
        try:
            api_info = await self.client.async_get_api_info(optional=True)
            doors = await self.client.async_get_doors()
            areas = await self.client.async_get_areas()
        except IntegritiAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IntegritiConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except IntegritiPermissionError as err:
            raise UpdateFailed(f"Integriti API permission denied: {err}") from err
        except IntegritiError as err:
            raise UpdateFailed(f"Integriti update failed: {err}") from err

        return IntegritiData(
            api_info=api_info,
            doors={door.unique_id: door for door in doors},
            areas={area.unique_id: area for area in areas},
        )

    async def _async_delayed_refresh(self, delay: float) -> None:
        """Refresh after Integriti has had time to publish a changed state."""
        try:
            await asyncio.sleep(delay)
            await self.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - refresh errors are recorded by coordinator
            _LOGGER.debug(
                "Delayed Integriti refresh after %.1f seconds failed",
                delay,
                exc_info=True,
            )

    async def async_refresh_after_command(self) -> None:
        """Refresh immediately and several times after a control command."""
        for delay in _POST_COMMAND_DELAYS:
            task = self.hass.async_create_task(self._async_delayed_refresh(delay))
            self._delayed_refresh_tasks.add(task)
            task.add_done_callback(self._delayed_refresh_tasks.discard)
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Cancel short-lived delayed refresh jobs on unload."""
        tasks = tuple(self._delayed_refresh_tasks)
        self._delayed_refresh_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

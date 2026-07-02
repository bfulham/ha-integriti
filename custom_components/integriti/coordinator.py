"""Data coordinator for Inner Range Integriti."""

from __future__ import annotations

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

    async def _async_update_data(self) -> IntegritiData:
        try:
            # ApiVersion is not granted to every API-key role, so it must not
            # prevent otherwise valid Basic Status access from loading.
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

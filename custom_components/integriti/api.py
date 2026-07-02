"""Asynchronous client for the Inner Range Integriti REST API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import TypeVar
from urllib.parse import quote
from uuid import uuid4
from xml.etree import ElementTree as ET

import aiohttp

from .const import (
    API_VERSION_PATH,
    BASIC_STATUS_PATH,
    DEFAULT_TIMEOUT,
    HEADER_API_KEY,
    USER_PATH,
)
from .models import ApiInfo, IntegritiArea, IntegritiDoor
from .parser import parse_api_info, parse_areas, parse_doors, parse_page_metadata

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class IntegritiError(Exception):
    """Base Integriti exception."""


class IntegritiAuthenticationError(IntegritiError):
    """The API key was rejected."""


class IntegritiConnectionError(IntegritiError):
    """The Integriti server could not be reached."""


class IntegritiResponseError(IntegritiError):
    """The Integriti server returned an invalid response."""


@dataclass(slots=True)
class IntegritiClient:
    """API-key-only Integriti REST client."""

    session: aiohttp.ClientSession
    base_url: str
    api_key: str
    verify_ssl: bool = True
    timeout: int = DEFAULT_TIMEOUT

    @property
    def headers(self) -> dict[str, str]:
        """Return common request headers."""
        return {
            "Accept": "application/xml",
            HEADER_API_KEY: self.api_key,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | bool] | None = None,
        data: str | bytes | None = None,
        allow_not_found: bool = False,
    ) -> str | None:
        url = f"{self.base_url}{path}"
        headers = self.headers
        if data is not None:
            headers = {**headers, "Content-Type": "application/xml; charset=utf-8"}
        ssl: bool | None = None if self.verify_ssl else False
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    ssl=ssl,
                ) as response:
                    body = await response.text()
                    if response.status in (401, 403):
                        raise IntegritiAuthenticationError(
                            "The Integriti API key was rejected or lacks permission"
                        )
                    if allow_not_found and response.status in (404, 405):
                        return None
                    if response.status < 200 or response.status >= 300:
                        excerpt = body.replace("\r", " ").replace("\n", " ")[:500]
                        raise IntegritiResponseError(
                            f"{method} {path} returned HTTP {response.status}: {excerpt}"
                        )
                    return body
        except IntegritiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise IntegritiConnectionError(f"Unable to reach {url}: {err}") from err

    async def async_get_api_info(self) -> ApiInfo:
        """Return API and product version information."""
        body = await self._request("GET", API_VERSION_PATH)
        if body is None:
            raise IntegritiResponseError("ApiVersion returned no response")
        return parse_api_info(body)

    async def _get_all_entities(
        self,
        entity_type: str,
        parser: Callable[[str], list[T]],
    ) -> list[T]:
        """Retrieve all visible entities, with a fallback discovery route."""
        paths = (
            f"{BASIC_STATUS_PATH}/{entity_type}",
            f"{USER_PATH}/{entity_type}",
        )
        last_error: IntegritiError | None = None
        for path in paths:
            try:
                entities: list[T] = []
                page = 1
                page_size = 500
                while page <= 100:
                    body = await self._request(
                        "GET",
                        path,
                        params={
                            "Page": page,
                            "PageSize": page_size,
                            "FullObject": "true",
                            "AdditionalProperties": "State",
                        },
                        allow_not_found=True,
                    )
                    if body is None:
                        break
                    rows = parser(body)
                    entities.extend(rows)
                    total, response_page, response_size = parse_page_metadata(body)
                    if total is None:
                        break
                    effective_size = response_size or page_size
                    effective_page = response_page or page
                    if effective_page * effective_size >= total or not rows:
                        break
                    page += 1
                if entities or body is not None:
                    return entities
            except IntegritiAuthenticationError:
                raise
            except IntegritiError as err:
                last_error = err
                _LOGGER.debug("Integriti entity route %s failed: %s", path, err)
        if last_error is not None:
            raise last_error
        return []

    async def async_get_doors(self) -> list[IntegritiDoor]:
        """Return all visible doors and their current states."""
        return await self._get_all_entities("Door", parse_doors)

    async def async_get_areas(self) -> list[IntegritiArea]:
        """Return all visible security areas and their current states."""
        return await self._get_all_entities("Area", parse_areas)

    async def async_grant_access(
        self,
        door_address: str,
        seconds: int,
        *,
        force_even_if_overridden: bool = False,
    ) -> None:
        """Momentarily grant access through a door."""
        root = ET.Element("GrantAccessActionOptions")
        ET.SubElement(root, "UnlockSeconds").text = str(seconds)
        ET.SubElement(root, "ForceEvenIfOverridden").text = str(
            force_even_if_overridden
        )
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/GrantAccess/{quote(door_address, safe='')}",
            data=ET.tostring(root, encoding="utf-8", xml_declaration=False),
        )

    async def async_override_door(self, door_address: str, *, locked: bool) -> None:
        """Apply a persistent locked or unlocked override."""
        root = ET.Element("OverrideDoorActionOptions")
        ET.SubElement(root, "OverrideDoorAction").text = (
            "OverrideLocked" if locked else "OverrideUnlocked"
        )
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/overridedoor/{quote(door_address, safe='')}",
            data=ET.tostring(root, encoding="utf-8", xml_declaration=False),
        )

    async def async_remove_door_override(self, door_address: str) -> None:
        """Return a door to normal Integriti control."""
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/RemoveDoorOverride/{quote(door_address, safe='')}",
            data=b"",
        )

    async def async_control_area(self, area_control_id: str, *, arm: bool) -> None:
        """Arm or disarm an area using a one-shot AreaAction assertion."""
        action_id = str(uuid4())
        root = ET.Element("AreaAction", {"ID": action_id})
        ET.SubElement(root, "ID").text = action_id
        # XML_Control asserts the supplied action. Put the requested operation on
        # the assert edge and retain the inverse on the deassert edge.
        ET.SubElement(root, "OnAssert").text = "1" if arm else "2"
        ET.SubElement(root, "OnDeAssert").text = "2" if arm else "1"
        ET.SubElement(root, "InvertQualifier").text = "False"
        ET.SubElement(root, "WaitUntilComplete").text = "False"
        ET.SubElement(root, "NoEnable").text = "False"
        entity = ET.SubElement(root, "Entity")
        ET.SubElement(entity, "Ref", {"Type": "Area", "ID": area_control_id})
        ET.SubElement(root, "AreaActionType").text = "0"
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=False)

        # Protocol revisions have used both of these casings/routes.
        for endpoint in (
            f"{BASIC_STATUS_PATH}/xml_controlAsync",
            f"{BASIC_STATUS_PATH}/XML_ControlAsync",
            f"{BASIC_STATUS_PATH}/xml_control",
        ):
            result = await self._request(
                "POST", endpoint, data=payload, allow_not_found=True
            )
            if result is not None:
                return
        raise IntegritiResponseError("No supported XML control endpoint was found")

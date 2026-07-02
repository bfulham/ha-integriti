"""Asynchronous client for the Inner Range Integriti REST API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
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
from .models import (
    ApiInfo,
    IntegritiArea,
    IntegritiAreaStatus,
    IntegritiDoor,
    IntegritiDoorStatus,
)
from .parser import (
    parse_api_info,
    parse_area_states,
    parse_areas,
    parse_door_states,
    parse_doors,
    parse_page_metadata,
)

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class IntegritiError(Exception):
    """Base Integriti exception."""


class IntegritiAuthenticationError(IntegritiError):
    """The API key was rejected."""


class IntegritiPermissionError(IntegritiError):
    """The API key is valid but lacks permission for a request."""


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
    _warned_missing_door_states: bool = field(default=False, init=False, repr=False)
    _warned_missing_area_states: bool = field(default=False, init=False, repr=False)

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
        allow_statuses: Iterable[int] = (),
    ) -> str | None:
        """Issue a request and return its response body."""
        url = f"{self.base_url}{path}"
        headers = self.headers
        if data is not None:
            headers = {**headers, "Content-Type": "application/xml; charset=utf-8"}
        ssl: bool | None = None if self.verify_ssl else False
        allowed = set(allow_statuses)
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
                    if response.status in allowed:
                        _LOGGER.debug(
                            "Optional Integriti request %s %s returned HTTP %s",
                            method,
                            path,
                            response.status,
                        )
                        return None
                    if response.status == 401:
                        raise IntegritiAuthenticationError(
                            "The Integriti API key was rejected"
                        )
                    if response.status == 403:
                        excerpt = body.replace("\r", " ").replace("\n", " ")[:500]
                        raise IntegritiPermissionError(
                            f"{method} {path} was forbidden by Integriti: {excerpt}"
                        )
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

    async def async_get_api_info(self, *, optional: bool = False) -> ApiInfo:
        """Return API and product version information.

        Some API-key roles can read Basic Status but are denied access to the
        ApiVersion route.  Version information is therefore optional during
        normal setup and polling.
        """
        body = await self._request(
            "GET",
            API_VERSION_PATH,
            allow_statuses=(403, 404, 405) if optional else (),
        )
        if body is None:
            return ApiInfo()
        return parse_api_info(body)

    async def _get_all_entities_from_path(
        self,
        path_prefix: str,
        entity_type: str,
        parser: Callable[[str], list[T]],
        *,
        optional: bool = False,
        extra_params: dict[str, str | int | bool] | None = None,
    ) -> list[T] | None:
        """Retrieve all pages of one entity type from one route."""
        entities: list[T] = []
        page = 1
        page_size = 500
        path = f"{path_prefix}/{entity_type}"
        while page <= 100:
            params: dict[str, str | int | bool] = {
                "Page": page,
                "PageSize": page_size,
                "FullObject": "true",
            }
            if extra_params:
                params.update(extra_params)
            body = await self._request(
                "GET",
                path,
                params=params,
                allow_statuses=(400, 403, 404, 405) if optional else (),
            )
            if body is None:
                return None
            rows = parser(body)
            entities.extend(rows)
            total, response_page, response_size = parse_page_metadata(body)
            if total is None:
                # Most installations return every row when PageSize is supplied.
                # If exactly a full page is returned, try the next page as well.
                if len(rows) < page_size:
                    break
                page += 1
                continue
            effective_size = response_size or page_size
            effective_page = response_page or page
            if effective_page * effective_size >= total or not rows:
                break
            page += 1
        return entities

    async def _get_legacy_states(
        self,
        entity_type: str,
        parser: Callable[[str], list[T]],
    ) -> list[T] | None:
        """Read state rows from the legacy REST/XML query route as fallback."""
        entities: list[T] = []
        page = 1
        page_size = 500
        path = f"/XML_Query/{entity_type}"
        while page <= 100:
            body = await self._request(
                "GET",
                path,
                params={"query_page": page, "query_size": page_size},
                # Older handlers may not allow API-key-only authentication.
                allow_statuses=(400, 401, 403, 404, 405),
            )
            if body is None:
                return None
            rows = parser(body)
            entities.extend(rows)
            total, response_page, response_size = parse_page_metadata(body)
            if total is None or not rows:
                break
            effective_size = response_size or page_size
            effective_page = response_page or page
            if effective_page * effective_size >= total:
                break
            page += 1
        return entities

    async def _get_definitions(
        self,
        entity_type: str,
        parser: Callable[[str], list[T]],
    ) -> list[T]:
        """Read entity definitions, preferring the User Management route."""
        last_error: IntegritiError | None = None
        for path_prefix in (USER_PATH, BASIC_STATUS_PATH):
            try:
                rows = await self._get_all_entities_from_path(
                    path_prefix,
                    entity_type,
                    parser,
                    optional=True,
                    extra_params={
                        "AdditionalProperties": (
                            "State,Controller,InsideArea,OutsideArea,"
                            "State.State,State.Licensed,State.IsOpen,State.DOTL,"
                            "State.SilentDOTL,State.Forced,State.ModuleMissing,"
                            "State.RollerState,State.IsOverrideOn,State.Holdup,"
                            "State.EntryState,State.ExitState,State.Siren,"
                            "State.Pulse,State.Confirm,State.Defer,State.Warn,"
                            "State.SirenHoldoff,State.UserCount"
                        )
                    },
                )
                if rows is not None and rows:
                    return rows
            except IntegritiAuthenticationError:
                raise
            except IntegritiError as err:
                last_error = err
                _LOGGER.debug(
                    "Integriti definition route %s/%s failed: %s",
                    path_prefix,
                    entity_type,
                    err,
                )
        if last_error is not None:
            raise last_error
        return []

    @staticmethod
    def _normalise_key(value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @classmethod
    def _door_lookup(cls, doors: list[IntegritiDoor]) -> dict[str, int]:
        lookup: dict[str, int] = {}
        for index, door in enumerate(doors):
            for value in (
                door.unique_id,
                door.control_id,
                door.address,
                door.state_id,
            ):
                key = cls._normalise_key(value)
                if key:
                    lookup[key] = index
        return lookup

    @classmethod
    def _area_lookup(cls, areas: list[IntegritiArea]) -> dict[str, int]:
        lookup: dict[str, int] = {}
        for index, area in enumerate(areas):
            for value in (
                area.unique_id,
                area.control_id,
                area.address,
                area.state_id,
            ):
                key = cls._normalise_key(value)
                if key:
                    lookup[key] = index
        return lookup

    @staticmethod
    def _merge_door_status(
        door: IntegritiDoor,
        status: IntegritiDoorStatus,
    ) -> IntegritiDoor:
        values = {
            field: value
            for field, value in {
                "state": status.state,
                "state_raw": status.state_raw,
                "licensed": status.licensed,
                "is_open": status.is_open,
                "dotl": status.dotl,
                "silent_dotl": status.silent_dotl,
                "forced": status.forced,
                "module_missing": status.module_missing,
                "roller_state": status.roller_state,
                "roller_state_raw": status.roller_state_raw,
                "is_override_on": status.is_override_on,
            }.items()
            if value is not None
        }
        return replace(door, **values) if values else door

    @staticmethod
    def _merge_area_status(
        area: IntegritiArea,
        status: IntegritiAreaStatus,
    ) -> IntegritiArea:
        values = {
            field: value
            for field, value in {
                "state": status.state,
                "state_raw": status.state_raw,
                "holdup": status.holdup,
                "entry_state": status.entry_state,
                "entry_state_raw": status.entry_state_raw,
                "exit_state": status.exit_state,
                "exit_state_raw": status.exit_state_raw,
                "siren": status.siren,
                "pulse": status.pulse,
                "confirm": status.confirm,
                "defer": status.defer,
                "warn": status.warn,
                "siren_holdoff": status.siren_holdoff,
                "user_count": status.user_count,
            }.items()
            if value is not None
        }
        return replace(area, **values) if values else area

    async def async_get_doors(self) -> list[IntegritiDoor]:
        """Return all visible doors merged with standalone DoorState rows."""
        doors = await self._get_definitions("Door", parse_doors)
        if not doors:
            return []

        statuses: list[IntegritiDoorStatus] | None = None
        for prefix in (BASIC_STATUS_PATH, USER_PATH):
            statuses = await self._get_all_entities_from_path(
                prefix,
                "DoorState",
                parse_door_states,
                optional=True,
                extra_params={"AdditionalProperties": "Entity"},
            )
            if statuses:
                break
        if not statuses:
            statuses = await self._get_legacy_states("DoorState", parse_door_states)

        if not statuses:
            if not self._warned_missing_door_states:
                _LOGGER.warning(
                    "Integriti returned %s doors but no DoorState rows; lock/contact "
                    "states will remain unknown. Check Basic Status read permissions.",
                    len(doors),
                )
                self._warned_missing_door_states = True
            return doors
        self._warned_missing_door_states = False

        lookup = self._door_lookup(doors)
        matched = 0
        for status in statuses:
            index: int | None = None
            for value in (status.entity_id, status.address, status.row_id):
                key = self._normalise_key(value)
                if key is not None and key in lookup:
                    index = lookup[key]
                    break
            if index is None:
                continue
            doors[index] = self._merge_door_status(doors[index], status)
            matched += 1
        _LOGGER.debug(
            "Merged %s of %s DoorState rows into %s doors",
            matched,
            len(statuses),
            len(doors),
        )
        return doors

    async def async_get_areas(self) -> list[IntegritiArea]:
        """Return all visible areas merged with standalone AreaState rows."""
        areas = await self._get_definitions("Area", parse_areas)
        if not areas:
            return []

        statuses: list[IntegritiAreaStatus] | None = None
        for prefix in (BASIC_STATUS_PATH, USER_PATH):
            statuses = await self._get_all_entities_from_path(
                prefix,
                "AreaState",
                parse_area_states,
                optional=True,
                extra_params={"AdditionalProperties": "Entity"},
            )
            if statuses:
                break
        if not statuses:
            statuses = await self._get_legacy_states("AreaState", parse_area_states)

        if not statuses:
            if not self._warned_missing_area_states:
                _LOGGER.warning(
                    "Integriti returned %s areas but no AreaState rows; alarm states "
                    "will remain unknown. Check Basic Status read permissions.",
                    len(areas),
                )
                self._warned_missing_area_states = True
            return areas
        self._warned_missing_area_states = False

        lookup = self._area_lookup(areas)
        matched = 0
        for status in statuses:
            index: int | None = None
            for value in (status.entity_id, status.address, status.row_id):
                key = self._normalise_key(value)
                if key is not None and key in lookup:
                    index = lookup[key]
                    break
            if index is None:
                continue
            areas[index] = self._merge_area_status(areas[index], status)
            matched += 1
        _LOGGER.debug(
            "Merged %s of %s AreaState rows into %s areas",
            matched,
            len(statuses),
            len(areas),
        )
        return areas

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

    async def _async_control_area_legacy(
        self,
        area: IntegritiArea,
        *,
        arm: bool,
    ) -> bool:
        """Use the documented REST/XML Control/Area command."""
        action = "arm" if arm else "disarm"
        candidates: list[dict[str, str]] = []
        if area.controller_id and area.address:
            candidates.append(
                {
                    "Controller": area.controller_id,
                    "Address": area.address,
                    "Action": action,
                }
            )
        if area.control_id:
            candidates.append({"ID": area.control_id, "Action": action})
        candidates.append({"Name": area.name, "Action": action})

        seen: set[tuple[tuple[str, str], ...]] = set()
        for params in candidates:
            marker = tuple(sorted(params.items()))
            if marker in seen:
                continue
            seen.add(marker)
            body = await self._request(
                "GET",
                "/Control/Area",
                params=params,
                # Some installations expose only the v2 API to API-key users.
                allow_statuses=(400, 401, 403, 404, 405),
            )
            if body is not None:
                return True
        return False

    async def _async_control_area_v2(
        self,
        area: IntegritiArea,
        *,
        arm: bool,
    ) -> None:
        """Control an area by posting a one-shot AreaAction."""
        action_id = str(uuid4())
        root = ET.Element("AreaAction", {"ID": action_id})
        ET.SubElement(root, "ID").text = action_id
        # XML_Control executes the assert edge. Swap the two configured actions
        # when a disarm operation is requested.
        ET.SubElement(root, "OnAssert").text = "1" if arm else "2"
        ET.SubElement(root, "OnDeAssert").text = "2" if arm else "1"
        ET.SubElement(root, "InvertQualifier").text = "False"
        ET.SubElement(root, "WaitUntilComplete").text = "False"
        ET.SubElement(root, "NoEnable").text = "False"
        ET.SubElement(root, "AreaActionType").text = "0"
        entity = ET.SubElement(root, "Entity")
        ET.SubElement(entity, "Ref", {"Type": "Area", "ID": area.control_id})
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=False)

        forbidden = False
        # The synchronous route is the generated System Designer command and
        # requires fewer API capabilities than XML_ControlAsync on some roles.
        for endpoint in (
            f"{BASIC_STATUS_PATH}/xml_control",
            f"{BASIC_STATUS_PATH}/xml_controlAsync",
        ):
            try:
                result = await self._request(
                    "POST",
                    endpoint,
                    data=payload,
                    allow_statuses=(400, 404, 405),
                )
            except IntegritiPermissionError:
                forbidden = True
                continue
            if result is not None:
                return
        if forbidden:
            raise IntegritiPermissionError(
                "The API key lacks permission to execute XML area actions"
            )
        raise IntegritiResponseError("No supported area control endpoint was found")

    async def async_control_area(self, area: IntegritiArea, *, arm: bool) -> None:
        """Arm or disarm an area through the API-key-capable v2 route."""
        await self._async_control_area_v2(area, arm=arm)

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
    _xml_control_id_cache: dict[tuple[str, str], str] = field(
        default_factory=dict, init=False, repr=False
    )

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
        content_type: str | None = "application/xml; charset=utf-8",
        allow_statuses: Iterable[int] = (),
    ) -> str | None:
        """Issue a request and return its response body."""
        url = f"{self.base_url}{path}"
        headers = self.headers
        if data is not None and content_type is not None:
            headers = {**headers, "Content-Type": content_type}
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
        """Return API and product version information."""
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

    @staticmethod
    def _normalise_key(value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @classmethod
    def _is_identifier_name(cls, entity: IntegritiDoor | IntegritiArea) -> bool:
        name = cls._normalise_key(entity.name)
        return name is None or name in {
            cls._normalise_key(entity.unique_id),
            cls._normalise_key(entity.control_id),
            cls._normalise_key(entity.address),
        }

    @classmethod
    def _merge_definition(cls, current: T, candidate: T) -> T:
        """Merge duplicate definition rows, preferring friendly and populated data."""
        updates: dict[str, object] = {}
        if isinstance(current, (IntegritiDoor, IntegritiArea)) and isinstance(
            candidate, (IntegritiDoor, IntegritiArea)
        ):
            if cls._is_identifier_name(current) and not cls._is_identifier_name(candidate):
                updates["name"] = candidate.name
            for field_name in (
                "description",
                "xml_control_id",
                "controller_id",
                "state_id",
                "state",
                "state_raw",
            ):
                if (
                    getattr(current, field_name) is None
                    and getattr(candidate, field_name) is not None
                ):
                    updates[field_name] = getattr(candidate, field_name)
            if isinstance(current, IntegritiDoor) and isinstance(candidate, IntegritiDoor):
                for field_name in (
                    "licensed",
                    "is_open",
                    "dotl",
                    "silent_dotl",
                    "forced",
                    "module_missing",
                    "roller_state",
                    "roller_state_raw",
                    "is_override_on",
                    "inside_area",
                    "outside_area",
                ):
                    if (
                        getattr(current, field_name) is None
                        and getattr(candidate, field_name) is not None
                    ):
                        updates[field_name] = getattr(candidate, field_name)
            if isinstance(current, IntegritiArea) and isinstance(candidate, IntegritiArea):
                for field_name in (
                    "holdup",
                    "entry_state",
                    "entry_state_raw",
                    "exit_state",
                    "exit_state_raw",
                    "siren",
                    "pulse",
                    "confirm",
                    "defer",
                    "warn",
                    "siren_holdoff",
                    "user_count",
                ):
                    if (
                        getattr(current, field_name) is None
                        and getattr(candidate, field_name) is not None
                    ):
                        updates[field_name] = getattr(candidate, field_name)
        return replace(current, **updates) if updates else current

    async def _get_definitions(
        self,
        entity_type: str,
        parser: Callable[[str], list[T]],
    ) -> list[T]:
        """Read and merge entity definitions from all API-key-capable routes."""
        merged_rows: list[T] = []
        lookup: dict[str, int] = {}
        last_error: IntegritiError | None = None
        additional = (
            "ID,Address,Name,DisplayName,Summary,Description,State,Controller,"
            "InsideArea,OutsideArea,State.State,State.Value,State.Licensed,"
            "State.IsOpen,State.DOTL,State.SilentDOTL,State.Forced,"
            "State.ModuleMissing,State.RollerState,State.IsOverrideOn,"
            "State.Holdup,State.EntryState,State.ExitState,State.Siren,"
            "State.Pulse,State.Confirm,State.Defer,State.Warn,"
            "State.SirenHoldoff,State.UserCount"
        )
        for path_prefix in (USER_PATH, BASIC_STATUS_PATH):
            try:
                rows = await self._get_all_entities_from_path(
                    path_prefix,
                    entity_type,
                    parser,
                    optional=True,
                    extra_params={"AdditionalProperties": additional},
                )
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
                continue
            if not rows:
                continue
            for row in rows:
                keys = [
                    self._normalise_key(getattr(row, field_name, None))
                    for field_name in (
                        "unique_id",
                        "control_id",
                        "xml_control_id",
                        "address",
                        "state_id",
                    )
                ]
                index = next(
                    (lookup[key] for key in keys if key is not None and key in lookup),
                    None,
                )
                if index is None:
                    index = len(merged_rows)
                    merged_rows.append(row)
                else:
                    merged_rows[index] = self._merge_definition(merged_rows[index], row)
                merged = merged_rows[index]
                for field_name in (
                    "unique_id",
                    "control_id",
                    "xml_control_id",
                    "address",
                    "state_id",
                ):
                    key = self._normalise_key(getattr(merged, field_name, None))
                    if key is not None:
                        lookup[key] = index

        if merged_rows:
            return merged_rows
        if last_error is not None:
            raise last_error
        return []

    @classmethod
    def _door_lookup(cls, doors: list[IntegritiDoor]) -> dict[str, int]:
        lookup: dict[str, int] = {}
        for index, door in enumerate(doors):
            for value in (
                door.unique_id,
                door.control_id,
                door.xml_control_id,
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
                area.xml_control_id,
                area.address,
                area.state_id,
            ):
                key = cls._normalise_key(value)
                if key:
                    lookup[key] = index
        return lookup

    @classmethod
    def _merge_door_status(
        cls,
        door: IntegritiDoor,
        status: IntegritiDoorStatus,
    ) -> IntegritiDoor:
        values: dict[str, object] = {
            field_name: value
            for field_name, value in {
                "xml_control_id": status.entity_object_id,
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
        if status.name and cls._is_identifier_name(door):
            values["name"] = status.name
        return replace(door, **values) if values else door

    @classmethod
    def _merge_area_status(
        cls,
        area: IntegritiArea,
        status: IntegritiAreaStatus,
    ) -> IntegritiArea:
        values: dict[str, object] = {
            field_name: value
            for field_name, value in {
                "xml_control_id": status.entity_object_id,
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
        if status.name and cls._is_identifier_name(area):
            values["name"] = status.name
        return replace(area, **values) if values else area

    async def _get_status_rows(
        self,
        preferred_type: str,
        parser: Callable[[str], list[T]],
    ) -> list[T] | None:
        """Read typed states, falling back to polymorphic EntityState."""
        additional = (
            "Entity,Summary,Name,State,Value,DisplayValue,Licensed,IsOpen,DOTL,"
            "SilentDOTL,Forced,ModuleMissing,RollerState,IsOverrideOn,Holdup,"
            "EntryState,ExitState,Siren,Pulse,Confirm,Defer,Warn,SirenHoldoff,UserCount"
        )
        for entity_type in (preferred_type, "EntityState"):
            for prefix in (BASIC_STATUS_PATH, USER_PATH):
                rows = await self._get_all_entities_from_path(
                    prefix,
                    entity_type,
                    parser,
                    optional=True,
                    extra_params={"AdditionalProperties": additional},
                )
                if rows:
                    return rows
        rows = await self._get_legacy_states(preferred_type, parser)
        if rows:
            return rows
        return await self._get_legacy_states("EntityState", parser)

    async def async_get_doors(self) -> list[IntegritiDoor]:
        """Return all visible doors merged with current state rows."""
        doors = await self._get_definitions("Door", parse_doors)
        if not doors:
            return []

        statuses = await self._get_status_rows("DoorState", parse_door_states)
        if not statuses:
            if any(door.state is not None for door in doors):
                return doors
            if not self._warned_missing_door_states:
                _LOGGER.warning(
                    "Integriti returned %s doors but no usable DoorState/EntityState "
                    "rows; lock and contact states will remain unknown",
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
        """Return all visible areas merged with current state rows."""
        areas = await self._get_definitions("Area", parse_areas)
        if not areas:
            return []

        statuses = await self._get_status_rows("AreaState", parse_area_states)
        if not statuses:
            if any(area.state is not None for area in areas):
                return areas
            if not self._warned_missing_area_states:
                _LOGGER.warning(
                    "Integriti returned %s areas but no usable AreaState/EntityState "
                    "rows; alarm states will remain unknown",
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

    @staticmethod
    def _build_address_filter(address: str) -> bytes:
        """Build a provided-filter query that resolves a DB object by address."""
        root = ET.Element(
            "FilterExpression",
            {
                "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:type": "PropertyExpression",
            },
        )
        ET.SubElement(root, "PropertyName").text = "Address"
        ET.SubElement(root, "OperatorType").text = "Equals"
        args = ET.SubElement(root, "Args")
        ET.SubElement(
            args,
            "anyType",
            {"xsi:type": "xsd:string"},
        ).text = address
        return ET.tostring(root, encoding="utf-8", xml_declaration=False)

    @classmethod
    def _usable_xml_control_id(
        cls, candidate: str | None, address: str
    ) -> str | None:
        """Return a DB object ID, rejecting an address used as an ID fallback."""
        value = candidate.strip() if candidate else None
        if not value:
            return None
        if cls._normalise_key(value) == cls._normalise_key(address):
            return None
        return value

    async def _async_resolve_xml_control_id(
        self,
        entity_type: str,
        address: str,
        known_id: str | None,
        parser: Callable[[str], list[IntegritiDoor | IntegritiArea]],
    ) -> str:
        """Resolve the database ID required by DoorAction and AreaAction."""
        if usable := self._usable_xml_control_id(known_id, address):
            return usable

        cache_key = (entity_type.casefold(), address.casefold())
        if cached := self._xml_control_id_cache.get(cache_key):
            return cached

        payload = self._build_address_filter(address)
        params: dict[str, str | int | bool] = {
            "query_page": 1,
            "query_size": 25,
            "Page": 1,
            "PageSize": 25,
            "FullObject": "true",
            "AdditionalProperties": "ID,Address,Name,DisplayName,Summary,Controller",
        }
        last_error: IntegritiError | None = None
        for prefix in (BASIC_STATUS_PATH, USER_PATH):
            path = f"{prefix}/GetFilteredEntities/{entity_type}"
            try:
                body = await self._request(
                    "POST",
                    path,
                    params=params,
                    data=payload,
                    allow_statuses=(400, 403, 404, 405),
                )
            except IntegritiAuthenticationError:
                raise
            except IntegritiError as err:
                last_error = err
                continue
            if not body:
                continue
            rows = parser(body)
            exact = [
                row
                for row in rows
                if self._normalise_key(row.address) == self._normalise_key(address)
            ]
            for row in exact or rows:
                candidate = self._usable_xml_control_id(
                    row.xml_control_id or row.unique_id, address
                )
                if candidate:
                    self._xml_control_id_cache[cache_key] = candidate
                    _LOGGER.debug(
                        "Resolved Integriti %s %s to XML control ID %s",
                        entity_type,
                        address,
                        candidate,
                    )
                    return candidate

        detail = f": {last_error}" if last_error else ""
        raise IntegritiResponseError(
            f"Unable to resolve the Integriti database ID for {entity_type} "
            f"address {address}. XML control cannot use the address as Ref ID{detail}"
        )

    @staticmethod
    def _validate_xml_control_response(body: str | None) -> None:
        """Raise when Integriti returns an XML error inside a successful HTTP response."""
        if not body or not body.strip():
            return
        text = body.strip()
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            if text.casefold() in {"false", "failed", "error"}:
                raise IntegritiResponseError(
                    f"Integriti rejected the XML control request: {text[:500]}"
                )
            return
        root_name = root.tag.rsplit("}", 1)[-1].casefold()
        message = next(
            (
                (element.text or "").strip()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].casefold()
                in {"message", "error", "description"}
                and (element.text or "").strip()
            ),
            None,
        )
        success = next(
            (
                (element.text or "").strip().casefold()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].casefold()
                in {"success", "succeeded"}
            ),
            None,
        )
        if root_name == "error" or success in {"false", "0", "no"}:
            raise IntegritiResponseError(
                "Integriti rejected the XML control request"
                + (f": {message}" if message else f": {text[:500]}")
            )

    async def _async_post_xml_control(self, payload: bytes) -> None:
        """Post an Integriti action XML payload."""
        permission_error: IntegritiPermissionError | None = None
        _LOGGER.debug(
            "Sending Integriti XML control payload: %s",
            payload.decode("utf-8", errors="replace"),
        )
        for endpoint in (
            f"{BASIC_STATUS_PATH}/XML_Control",
            f"{BASIC_STATUS_PATH}/XML_ControlAsync",
        ):
            try:
                result = await self._request(
                    "POST",
                    endpoint,
                    data=payload,
                    content_type="application/xml; charset=utf-8",
                    allow_statuses=(404, 405),
                )
            except IntegritiPermissionError as err:
                permission_error = err
                continue
            if result is not None:
                self._validate_xml_control_response(result)
                return
        if permission_error is not None:
            raise permission_error
        raise IntegritiResponseError("No supported XML control endpoint was found")

    @staticmethod
    def _build_door_action(
        door_id: str,
        *,
        on_assert: int,
        on_deassert: int,
        unlock_seconds: int = 0,
    ) -> bytes:
        """Build XML in the same property order as System Designer."""
        action_id = str(uuid4())
        root = ET.Element("DoorAction", {"ID": action_id})
        ET.SubElement(root, "ID").text = action_id
        ET.SubElement(root, "OnAssert").text = str(on_assert)
        ET.SubElement(root, "OnDeAssert").text = str(on_deassert)
        ET.SubElement(root, "InvertQualifier").text = "False"
        ET.SubElement(root, "WaitUntilComplete").text = "False"
        entity = ET.SubElement(root, "Entity")
        ET.SubElement(entity, "Ref", {"Type": "Door", "ID": door_id})
        ET.SubElement(root, "UnlockTimeTicks").text = str(
            max(0, unlock_seconds) * 10_000_000
        )
        ET.SubElement(root, "Genre").text = "0"
        ET.SubElement(root, "DisarmAreas").text = "False"
        ET.SubElement(root, "IgnoreInterlocks").text = "False"
        return ET.tostring(root, encoding="utf-8", xml_declaration=False)

    async def async_control_door(
        self,
        door: IntegritiDoor,
        *,
        action: str,
        unlock_seconds: int = 0,
    ) -> None:
        """Control a door with a one-shot XML DoorAction."""
        target_id = await self._async_resolve_xml_control_id(
            "Door", door.address, door.xml_control_id, parse_doors
        )
        if action == "lock":
            payload = self._build_door_action(
                target_id, on_assert=1, on_deassert=2
            )
        elif action == "unlock":
            payload = self._build_door_action(
                target_id, on_assert=2, on_deassert=1
            )
        elif action == "grant_access":
            payload = self._build_door_action(
                target_id,
                on_assert=3,
                on_deassert=2,
                unlock_seconds=unlock_seconds,
            )
        else:
            raise ValueError(f"Unsupported Integriti door action: {action}")
        await self._async_post_xml_control(payload)

    async def async_grant_access(self, door_id: str, seconds: int) -> None:
        """Use the dedicated grant-access endpoint as a compatibility fallback."""
        root = ET.Element("GrantAccessActionOptions")
        ET.SubElement(root, "UnlockSeconds").text = str(seconds)
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/GrantAccess/{quote(door_id, safe='')}",
            data=ET.tostring(root, encoding="utf-8", xml_declaration=False),
        )

    async def async_override_door(self, door_id: str, *, locked: bool) -> None:
        """Apply a persistent locked or unlocked override."""
        root = ET.Element("OverrideDoorActionOptions")
        ET.SubElement(root, "OverrideDoorAction").text = (
            "OverrideLocked" if locked else "OverrideUnlocked"
        )
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/overridedoor/{quote(door_id, safe='')}",
            data=ET.tostring(root, encoding="utf-8", xml_declaration=False),
        )

    async def async_remove_door_override(self, door_id: str) -> None:
        """Return a door to normal Integriti control."""
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/RemoveDoorOverride/{quote(door_id, safe='')}",
            data=b"",
        )

    @staticmethod
    def _build_area_action(area_id: str, *, arm: bool) -> bytes:
        """Build a one-shot AreaAction in Integriti serialization order."""
        action_id = str(uuid4())
        root = ET.Element("AreaAction", {"ID": action_id})
        ET.SubElement(root, "ID").text = action_id
        ET.SubElement(root, "OnAssert").text = "1" if arm else "2"
        ET.SubElement(root, "OnDeAssert").text = "2" if arm else "1"
        ET.SubElement(root, "InvertQualifier").text = "False"
        ET.SubElement(root, "WaitUntilComplete").text = "False"
        entity = ET.SubElement(root, "Entity")
        ET.SubElement(entity, "Ref", {"Type": "Area", "ID": area_id})
        ET.SubElement(root, "NoEnable").text = "False"
        ET.SubElement(root, "AreaActionType").text = "0"
        return ET.tostring(root, encoding="utf-8", xml_declaration=False)

    async def async_control_area(self, area: IntegritiArea, *, arm: bool) -> None:
        """Arm or disarm an area through an XML AreaAction."""
        target_id = await self._async_resolve_xml_control_id(
            "Area", area.address, area.xml_control_id, parse_areas
        )
        await self._async_post_xml_control(
            self._build_area_action(target_id, arm=arm)
        )

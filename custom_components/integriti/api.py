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
    extract_database_object_id,
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
    _unavailable_id_lookup_routes: set[tuple[str, str]] = field(
        default_factory=set, init=False, repr=False
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
                            f"Integriti returned HTTP 401 for {method} {path}"
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
            # Some otherwise-valid API-key roles return 401 specifically for
            # ApiVersion. Treat that endpoint as unavailable when it is only
            # being used for optional product metadata.
            allow_statuses=(401, 403, 404, 405) if optional else (),
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
        last_auth_error: IntegritiAuthenticationError | None = None
        attempted_routes = 0
        successful_routes = 0
        auth_failed_routes = 0
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
            attempted_routes += 1
            try:
                rows = await self._get_all_entities_from_path(
                    path_prefix,
                    entity_type,
                    parser,
                    optional=True,
                    extra_params={"AdditionalProperties": additional},
                )
            except IntegritiAuthenticationError as err:
                # Integriti commonly returns 401 for a route that the API-key
                # role is not allowed to use, while another route works with
                # the same key. Do not trigger reauthentication until every
                # candidate definition route rejected the key.
                auth_failed_routes += 1
                last_auth_error = err
                _LOGGER.debug(
                    "Integriti definition route %s/%s returned HTTP 401; "
                    "trying the remaining API-key routes",
                    path_prefix,
                    entity_type,
                )
                continue
            except IntegritiError as err:
                last_error = err
                _LOGGER.debug(
                    "Integriti definition route %s/%s failed: %s",
                    path_prefix,
                    entity_type,
                    err,
                )
                continue
            if rows is not None:
                successful_routes += 1
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
        if (
            successful_routes == 0
            and attempted_routes > 0
            and auth_failed_routes == attempted_routes
            and last_auth_error is not None
        ):
            raise last_auth_error
        if last_error is not None and successful_routes == 0:
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
        """Read and merge typed and polymorphic entity-state rows.

        Some Integriti builds return the live state from ``DoorState`` or
        ``AreaState`` but omit the referenced entity's long database ID. The
        polymorphic ``EntityState`` route may expose that ID. Do not stop at
        the first non-empty route; merge all API-key-permitted responses and
        fill missing fields from each serialization.
        """
        additional = (
            "Entity,Entity.ID,Entity.EntityID,Entity.ObjectID,Entity.DatabaseID,"
            "Entity.Address,Entity.Name,Entity.Summary,Summary,Name,State,Value,"
            "DisplayValue,Licensed,IsOpen,DOTL,SilentDOTL,Forced,ModuleMissing,"
            "RollerState,IsOverrideOn,Holdup,EntryState,ExitState,Siren,Pulse,"
            "Confirm,Defer,Warn,SirenHoldoff,UserCount"
        )
        merged: list[T] = []
        lookup: dict[str, int] = {}

        def merge_rows(rows: list[T] | None) -> None:
            if not rows:
                return
            for candidate in rows:
                keys = [
                    self._normalise_key(getattr(candidate, field_name, None))
                    for field_name in (
                        "entity_object_id",
                        "entity_id",
                        "address",
                        "row_id",
                    )
                ]
                index = next(
                    (lookup[key] for key in keys if key is not None and key in lookup),
                    None,
                )
                if index is None:
                    index = len(merged)
                    merged.append(candidate)
                else:
                    current = merged[index]
                    updates: dict[str, object] = {}
                    for field_name in current.__dataclass_fields__:
                        current_value = getattr(current, field_name)
                        candidate_value = getattr(candidate, field_name)
                        if current_value is None and candidate_value is not None:
                            updates[field_name] = candidate_value
                    if updates:
                        merged[index] = replace(current, **updates)

                current = merged[index]
                for field_name in (
                    "entity_object_id",
                    "entity_id",
                    "address",
                    "row_id",
                ):
                    key = self._normalise_key(getattr(current, field_name, None))
                    if key is not None:
                        lookup[key] = index

        for entity_type in (preferred_type, "EntityState"):
            for prefix in (BASIC_STATUS_PATH, USER_PATH):
                try:
                    rows = await self._get_all_entities_from_path(
                        prefix,
                        entity_type,
                        parser,
                        optional=True,
                        extra_params={"AdditionalProperties": additional},
                    )
                except IntegritiAuthenticationError:
                    # State tables can have different permissions from Door
                    # and Area definitions. A 401 here must not invalidate an
                    # API key that is already working on another route.
                    _LOGGER.debug(
                        "Integriti state route %s/%s returned HTTP 401; "
                        "trying the remaining state routes",
                        prefix,
                        entity_type,
                    )
                    continue
                merge_rows(rows)

        merge_rows(await self._get_legacy_states(preferred_type, parser))
        merge_rows(await self._get_legacy_states("EntityState", parser))
        return merged or None

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
    def _build_address_filter(
        address: str, *, property_name: str = "Address"
    ) -> bytes:
        """Build the AggregateExpression shape generated by System Designer."""
        root = ET.Element(
            "FilterExpression",
            {
                "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:type": "AggregateExpression",
            },
        )
        ET.SubElement(root, "OperatorType").text = "And"
        subexpressions = ET.SubElement(root, "SubExpressions")
        expression = ET.SubElement(
            subexpressions,
            "FilterExpression",
            {"xsi:type": "PropertyExpression"},
        )
        ET.SubElement(expression, "PropertyName").text = property_name
        ET.SubElement(expression, "OperatorType").text = "Equals"
        args = ET.SubElement(expression, "Args")
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
        *known_ids: str | None,
    ) -> str | None:
        """Resolve the long Integriti database ID used by action references.

        Integriti releases differ in how a full object is serialized. Try the
        single-object route, an Address-filtered GET, the documented POST
        filter, and finally the state table that references the entity.
        """
        # Try every ID we already have before making optional lookup calls.
        # Integriti status responses on some systems expose the long object ID
        # as the State reference ID, while the entity object itself is only
        # exposed as the short address (for example A47/D38). That long value
        # is the ID accepted by AreaAction/DoorAction XML references.
        for known_id in known_ids:
            if usable := self._usable_xml_control_id(known_id, address):
                return usable

        cache_key = (entity_type.casefold(), address.casefold())
        if cached := self._xml_control_id_cache.get(cache_key):
            return cached

        additional = (
            "ID,EntityID,ObjectID,DatabaseID,Address,Name,DisplayName,"
            "Summary,Controller,Partition,PartitionID,Entity,Entity.ID,"
            "Entity.EntityID,Entity.ObjectID,Entity.DatabaseID,Entity.Address"
        )
        common_params: dict[str, str | int | bool] = {
            "query_page": 1,
            "query_size": 25,
            "Page": 1,
            "PageSize": 25,
            "FullObject": "true",
            "AdditionalProperties": additional,
        }
        responses: list[tuple[str, str]] = []

        async def try_request(
            method: str,
            path: str,
            *,
            params: dict[str, str | int | bool] | None = None,
            data: bytes | None = None,
        ) -> None:
            route_key = (method, path)
            if route_key in self._unavailable_id_lookup_routes:
                return
            try:
                body = await self._request(
                    method,
                    path,
                    params=params,
                    data=data,
                    content_type="application/xml" if data is not None else None,
                    # These are optional discovery routes. Some Integriti builds
                    # return 401 for a route the same API key is not permitted to
                    # use, even though the key remains valid for status and control.
                    allow_statuses=(400, 401, 403, 404, 405),
                )
            except IntegritiError as err:
                _LOGGER.debug(
                    "Integriti ID resolution request %s %s failed: %s",
                    method,
                    path,
                    err,
                )
                return
            if body is None:
                self._unavailable_id_lookup_routes.add(route_key)
                return
            responses.append((path, body))

        quoted_address = quote(address, safe="")
        for prefix in (BASIC_STATUS_PATH, USER_PATH):
            # Some versions accept an entity Address in the single-object route.
            await try_request(
                "GET",
                f"{prefix}/{entity_type}/{quoted_address}",
                params={
                    "FullObject": "true",
                    "AdditionalProperties": additional,
                },
            )
            # GET field filters are retained by several v2 server builds.
            await try_request(
                "GET",
                f"{prefix}/{entity_type}",
                params={**common_params, "Address": address},
            )
            # Exact documented POST filter shape.
            await try_request(
                "POST",
                f"{prefix}/GetFilteredEntities/{entity_type}",
                params=common_params,
                data=self._build_address_filter(address),
            )

        state_type = f"{entity_type}State"
        for prefix in (BASIC_STATUS_PATH, USER_PATH):
            for property_name in ("Entity.Address", "Address", "EntityAddress"):
                await try_request(
                    "POST",
                    f"{prefix}/GetFilteredEntities/{state_type}",
                    params=common_params,
                    data=self._build_address_filter(
                        address, property_name=property_name
                    ),
                )

        for path, body in responses:
            candidate = extract_database_object_id(body, entity_type, address)
            candidate = self._usable_xml_control_id(candidate, address)
            if candidate:
                self._xml_control_id_cache[cache_key] = candidate
                _LOGGER.debug(
                    "Resolved Integriti %s %s to XML control ID %s using %s",
                    entity_type,
                    address,
                    candidate,
                    path,
                )
                return candidate

        _LOGGER.warning(
            "Could not resolve the Integriti database ID for %s %s; "
            "the server did not expose Entity.ID in any permitted status/query route",
            entity_type,
            address,
        )
        return None

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
        operation_state = next(
            (
                (element.text or "").strip().replace("_", "").casefold()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].casefold() == "state"
                and (element.text or "").strip()
            ),
            None,
        )
        failed_state = operation_state in {
            "donefail",
            "donecancelled",
            "failed",
            "failure",
            "error",
            "cancelled",
        }
        if (
            root_name == "error"
            or success in {"false", "0", "no"}
            or failed_state
        ):
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
        # Match the exact v2 route casing used by Inner Range's Postman
        # collection. Try the asynchronous endpoint first for a useful action
        # result, then the immediate endpoint as a compatibility fallback.
        authentication_error: IntegritiAuthenticationError | None = None
        for endpoint in (
            f"{BASIC_STATUS_PATH}/xml_controlAsync",
            f"{BASIC_STATUS_PATH}/xml_control",
        ):
            try:
                result = await self._request(
                    "POST",
                    endpoint,
                    data=payload,
                    content_type="application/xml",
                    allow_statuses=(404, 405),
                )
            except IntegritiAuthenticationError as err:
                # A key can be valid for polling and GrantAccess while one XML
                # control route is disabled. Try the other documented route
                # before reporting the endpoint-specific authentication failure.
                authentication_error = err
                continue
            except IntegritiPermissionError as err:
                permission_error = err
                continue
            if result is not None:
                self._validate_xml_control_response(result)
                return
        if permission_error is not None:
            raise permission_error
        if authentication_error is not None:
            raise IntegritiPermissionError(
                "The API key is valid for Integriti status requests, but the "
                "XML control endpoint rejected API-key authentication. Check "
                "the API key's Basic Status and Control permissions."
            ) from authentication_error
        raise IntegritiResponseError("No supported XML control endpoint was found")

    @staticmethod
    def _build_door_action(
        door_id: str | None,
        *,
        address: str | None = None,
        address_as_id: bool = False,
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
        ref_attributes = {"Type": "Door"}
        if door_id:
            ref_attributes["ID"] = door_id
        elif address:
            ref_attributes["ID" if address_as_id else "Address"] = address
        else:
            raise ValueError("A Door ID or address is required")
        ET.SubElement(entity, "Ref", ref_attributes)
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
        """Control a door without applying a persistent override."""
        if action == "grant_access":
            try:
                await self.async_grant_access(door.control_id, unlock_seconds)
                return
            except IntegritiResponseError as err:
                _LOGGER.debug(
                    "Dedicated GrantAccess failed for %s; trying DoorAction: %s",
                    door.address,
                    err,
                )

        target_id = await self._async_resolve_xml_control_id(
            "Door", door.address, door.xml_control_id, door.state_id
        )
        # REST XML control executes the asserted side of the action once.
        # OnDeAssert must be 0 (No Action); setting it to the opposite command
        # causes Integriti to treat the payload as a paired assert/deassert action.
        if action == "lock":
            on_assert, on_deassert = 1, 0
        elif action == "unlock":
            on_assert, on_deassert = 2, 0
        elif action == "grant_access":
            on_assert, on_deassert = 3, 0
        else:
            raise ValueError(f"Unsupported Integriti door action: {action}")

        if not target_id:
            raise IntegritiResponseError(
                f"Unable to obtain the Integriti database ID for Door "
                f"{door.address}. Download the integration diagnostics after "
                f"a refresh so the returned state-reference shape can be checked."
            )
        targets: list[tuple[str | None, bool]] = [(target_id, False)]

        last_error: IntegritiError | None = None
        for candidate_id, address_as_id in targets:
            payload = self._build_door_action(
                candidate_id,
                address=door.address,
                address_as_id=address_as_id,
                on_assert=on_assert,
                on_deassert=on_deassert,
                unlock_seconds=unlock_seconds,
            )
            try:
                await self._async_post_xml_control(payload)
                return
            except IntegritiError as err:
                last_error = err
                _LOGGER.debug(
                    "Integriti DoorAction target form failed for %s: %s",
                    door.address,
                    err,
                )

        if last_error is not None:
            raise last_error
        raise IntegritiResponseError(f"Unable to control Integriti door {door.address}")

    async def async_grant_access(self, door_id: str, seconds: int) -> None:
        """Momentarily release a door through the dedicated v2 endpoint."""
        root = ET.Element("GrantAccessActionOptions")
        ET.SubElement(root, "UnlockSeconds").text = str(max(0, seconds))
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        await self._request(
            "POST",
            f"{BASIC_STATUS_PATH}/GrantAccess/{quote(door_id, safe='')}",
            data=payload,
            content_type="application/xml",
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
    def _build_area_action(
        area_id: str | None,
        *,
        address: str | None = None,
        address_as_id: bool = False,
        arm: bool,
    ) -> bytes:
        """Build a one-shot AreaAction in Integriti serialization order."""
        action_id = str(uuid4())
        root = ET.Element("AreaAction", {"ID": action_id})
        ET.SubElement(root, "ID").text = action_id
        ET.SubElement(root, "OnAssert").text = "1" if arm else "2"
        # A REST control request is a one-shot assert. The working Integriti
        # payload uses 0 (No Action) for the deassert side.
        ET.SubElement(root, "OnDeAssert").text = "0"
        ET.SubElement(root, "InvertQualifier").text = "False"
        ET.SubElement(root, "WaitUntilComplete").text = "False"
        entity = ET.SubElement(root, "Entity")
        ref_attributes = {"Type": "Area"}
        if area_id:
            ref_attributes["ID"] = area_id
        elif address:
            ref_attributes["ID" if address_as_id else "Address"] = address
        else:
            raise ValueError("An Area ID or address is required")
        ET.SubElement(entity, "Ref", ref_attributes)
        ET.SubElement(root, "NoEnable").text = "False"
        ET.SubElement(root, "AreaActionType").text = "0"
        return ET.tostring(root, encoding="utf-8", xml_declaration=False)

    async def async_control_area(self, area: IntegritiArea, *, arm: bool) -> None:
        """Arm or disarm an area through an XML AreaAction."""
        target_id = await self._async_resolve_xml_control_id(
            "Area", area.address, area.xml_control_id, area.state_id
        )
        if not target_id:
            raise IntegritiResponseError(
                f"Unable to obtain the Integriti database ID for Area "
                f"{area.address}. Download the integration diagnostics after "
                f"a refresh so the returned state-reference shape can be checked."
            )
        targets: list[tuple[str | None, bool]] = [(target_id, False)]

        last_error: IntegritiError | None = None
        for candidate_id, address_as_id in targets:
            payload = self._build_area_action(
                candidate_id,
                address=area.address,
                address_as_id=address_as_id,
                arm=arm,
            )
            try:
                await self._async_post_xml_control(payload)
                return
            except IntegritiError as err:
                last_error = err
                _LOGGER.debug(
                    "Integriti AreaAction target form failed for %s: %s",
                    area.address,
                    err,
                )

        if last_error is not None:
            raise last_error
        raise IntegritiResponseError(f"Unable to control Integriti area {area.address}")


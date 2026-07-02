"""Constants for the Inner Range Integriti integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "integriti"
NAME: Final = "Inner Range Integriti"
VERSION: Final = "0.1.4"

CONF_API_KEY: Final = "api_key"
CONF_API_PATH: Final = "api_path"
CONF_USE_SSL: Final = "use_ssl"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_GRANT_ACCESS_SECONDS: Final = "grant_access_seconds"
CONF_ENABLE_AREA_CONTROL: Final = "enable_area_control"
CONF_ENABLE_DOOR_CONTROL: Final = "enable_door_control"

DEFAULT_PORT: Final = 80
DEFAULT_SSL_PORT: Final = 443
DEFAULT_API_PATH: Final = "/restapi"
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_GRANT_ACCESS_SECONDS: Final = 10
DEFAULT_ENABLE_AREA_CONTROL: Final = True
DEFAULT_ENABLE_DOOR_CONTROL: Final = True
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300
DEFAULT_TIMEOUT: Final = 20
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

API_VERSION_PATH: Final = "/ApiVersion"
BASIC_STATUS_PATH: Final = "/v2/basicstatus"
USER_PATH: Final = "/v2/user"
AUTH_PATH: Final = "/v2/authentication"

HEADER_API_KEY: Final = "API-KEY"

PLATFORMS: Final = [
    "alarm_control_panel",
    "binary_sensor",
    "lock",
    "select",
    "sensor",
]

DOOR_OVERRIDE_NORMAL: Final = "normal"
DOOR_OVERRIDE_LOCKED: Final = "locked"
DOOR_OVERRIDE_UNLOCKED: Final = "unlocked"
DOOR_OVERRIDE_OPTIONS: Final = [
    DOOR_OVERRIDE_NORMAL,
    DOOR_OVERRIDE_LOCKED,
    DOOR_OVERRIDE_UNLOCKED,
]

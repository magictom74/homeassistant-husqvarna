"""Constants for the Husqvarna integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "husqvarna"

# ConfigEntry data keys
CONF_API_KEY: Final = "api_key"
CONF_API_SECRET: Final = "api_secret"

# HA bus events fired for diagnostic / automation hooks
EVENT_MOWER_ERROR: Final = "husqvarna_mower_error"
EVENT_MOWER_ERROR_CLEARED: Final = "husqvarna_mower_error_cleared"

# Service names
SERVICE_PARK_FOR = "park_for"
SERVICE_START_FOR = "start_for"
SERVICE_START_IN_WORK_AREA = "start_in_work_area"
SERVICE_CONFIRM_ERROR = "confirm_error"
SERVICE_RESET_BLADE_USAGE_TIME = "reset_cutting_blade_usage_time"
SERVICE_REFRESH_MESSAGES = "refresh_messages"

# Device manufacturer constant (used in device registry)
MANUFACTURER = "Husqvarna"

# When using park/start actions originated from HA, the Husqvarna cloud
# expects an externalReason in the 3000-3999 range. We pick a fixed one
# so dashboards / logs can identify the source.
HA_EXTERNAL_REASON: Final = 3000

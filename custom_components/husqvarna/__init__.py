"""The Husqvarna integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from pyhusqvarna import (
    AuthError,
    AutomowerClient,
    HusqvarnaAuth,
    HusqvarnaConnectionError,
    HusqvarnaTimeoutError,
    NotFoundError,
    SimultaneousLoginsError,
)

from .const import (
    CONF_API_KEY,
    CONF_API_SECRET,
    DOMAIN,
    SERVICE_CONFIRM_ERROR,
    SERVICE_PARK_FOR,
    SERVICE_REFRESH_MESSAGES,
    SERVICE_RESET_BLADE_USAGE_TIME,
    SERVICE_START_FOR,
    SERVICE_START_IN_WORK_AREA,
)
from . import config_flow  # noqa: F401 - pre-import to avoid sync import_module in event loop
from .coordinator import HusqvarnaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SENSOR,
]

# ---------------------------------------------------------------------------
# Service schemas
# ---------------------------------------------------------------------------

PARK_FOR_SCHEMA = vol.Schema({
    vol.Required("mower_id"): cv.string,
    vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65000)),
})

START_FOR_SCHEMA = vol.Schema({
    vol.Required("mower_id"): cv.string,
    vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65000)),
})

START_IN_WORK_AREA_SCHEMA = vol.Schema({
    vol.Required("mower_id"): cv.string,
    vol.Required("work_area_id"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65000)),
})

MOWER_ONLY_SCHEMA = vol.Schema({vol.Required("mower_id"): cv.string})


# ---------------------------------------------------------------------------
# Setup / unload
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api_key: str = entry.data[CONF_API_KEY]
    api_secret: str = entry.data[CONF_API_SECRET]

    auth = HusqvarnaAuth(api_key=api_key, api_secret=api_secret)
    try:
        await auth.get_token()
    except SimultaneousLoginsError as exc:
        await auth.aclose()
        raise ConfigEntryNotReady(
            "Husqvarna cloud locked the application credentials with "
            "'simultaneous.logins'. Stop any other client using the same "
            "app key (e.g. ioBroker) for a few minutes and reload."
        ) from exc
    except AuthError as exc:
        await auth.aclose()
        raise ConfigEntryAuthFailed(f"Token request failed: {exc}") from exc
    except (HusqvarnaConnectionError, HusqvarnaTimeoutError) as exc:
        await auth.aclose()
        raise ConfigEntryNotReady(
            f"Cannot reach Husqvarna cloud: {exc}"
        ) from exc

    client = AutomowerClient(auth)
    coordinator = HusqvarnaCoordinator(hass, entry=entry, auth=auth, client=client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (HusqvarnaConnectionError, HusqvarnaTimeoutError, NotFoundError) as exc:
        await client.aclose()
        await auth.aclose()
        raise ConfigEntryNotReady(f"Initial mower fetch failed: {exc}") from exc

    # Start WebSocket as a background task. Reconnect-loop is internal.
    await coordinator.async_start_ws()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: HusqvarnaCoordinator = hass.data[DOMAIN][entry.entry_id]

    await coordinator.async_stop_ws()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await coordinator.client.aclose()
        await coordinator.auth.aclose()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_PARK_FOR,
                SERVICE_START_FOR,
                SERVICE_START_IN_WORK_AREA,
                SERVICE_CONFIRM_ERROR,
                SERVICE_RESET_BLADE_USAGE_TIME,
                SERVICE_REFRESH_MESSAGES,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_PARK_FOR):
        return

    def _coordinator_for(mower_id: str) -> HusqvarnaCoordinator | None:
        for c in hass.data.get(DOMAIN, {}).values():
            if c.get_mower(mower_id) is not None:
                return c
        return None

    async def _park_for(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        duration = int(call.data["duration_minutes"])
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.client.park_for(mower_id, duration_minutes=duration)

    async def _start_for(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        duration = int(call.data["duration_minutes"])
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.client.start_for(mower_id, duration_minutes=duration)

    async def _start_in_work_area(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.client.start_in_work_area(
            mower_id,
            work_area_id=int(call.data["work_area_id"]),
            duration_minutes=int(call.data["duration_minutes"]),
        )

    async def _confirm_error(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.client.confirm_error(mower_id)

    async def _reset_blade(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.client.reset_cutting_blade_usage_time(mower_id)

    async def _refresh_messages(call: ServiceCall) -> None:
        mower_id = call.data["mower_id"]
        coord = _coordinator_for(mower_id)
        if coord is None:
            raise ValueError(f"Unknown mower: {mower_id}")
        await coord.async_refresh_messages(mower_id)

    hass.services.async_register(DOMAIN, SERVICE_PARK_FOR, _park_for, schema=PARK_FOR_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_START_FOR, _start_for, schema=START_FOR_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_START_IN_WORK_AREA, _start_in_work_area, schema=START_IN_WORK_AREA_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CONFIRM_ERROR, _confirm_error, schema=MOWER_ONLY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_BLADE_USAGE_TIME, _reset_blade, schema=MOWER_ONLY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_MESSAGES, _refresh_messages, schema=MOWER_ONLY_SCHEMA
    )



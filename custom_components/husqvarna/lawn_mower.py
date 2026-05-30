"""Lawn-mower platform - the primary control entity per mower.

Maps Husqvarna activity/state onto HA's :class:`LawnMowerActivity` enum
and exposes the three core actions DOCK / PAUSE / START_MOWING. More
fine-grained actions (park_for, start_in_work_area, confirm_error)
live as Buttons + Services elsewhere.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyhusqvarna import MowerActivity, MowerState

from .const import DOMAIN
from .coordinator import HusqvarnaCoordinator
from .entity import HusqvarnaMowerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HusqvarnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.data is None:
        return
    async_add_entities(
        HusqvarnaLawnMower(coordinator, mower_id)
        for mower_id in coordinator.data
    )


# Husqvarna activity -> HA activity. Error/FatalError on the state side
# overrides this mapping; see HusqvarnaLawnMower.activity below.
_ACTIVITY_MAP: dict[MowerActivity, LawnMowerActivity | None] = {
    MowerActivity.MOWING: LawnMowerActivity.MOWING,
    MowerActivity.LEAVING: LawnMowerActivity.MOWING,
    MowerActivity.GOING_HOME: LawnMowerActivity.RETURNING,
    MowerActivity.CHARGING: LawnMowerActivity.DOCKED,
    MowerActivity.PARKED_IN_CS: LawnMowerActivity.DOCKED,
    MowerActivity.STOPPED_IN_GARDEN: LawnMowerActivity.ERROR,
    MowerActivity.UNKNOWN: None,
    MowerActivity.NOT_APPLICABLE: None,
}

_ERROR_STATES = {MowerState.ERROR, MowerState.FATAL_ERROR, MowerState.ERROR_AT_POWER_UP}
_PAUSED_STATES = {MowerState.PAUSED, MowerState.STOPPED}


class HusqvarnaLawnMower(HusqvarnaMowerEntity, LawnMowerEntity):
    """One Automower as a HA lawn-mower entity."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )
    _attr_name = None  # device name == mower name; entity has none of its own

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(coordinator, mower_id, unique_id_suffix="mower")

    @property
    def activity(self) -> LawnMowerActivity | None:
        m = self.mower
        if m is None:
            return None
        if m.state in _ERROR_STATES or m.has_error:
            return LawnMowerActivity.ERROR
        if m.state in _PAUSED_STATES:
            return LawnMowerActivity.PAUSED
        return _ACTIVITY_MAP.get(m.activity)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.mower
        if m is None:
            return {}
        return {
            "husqvarna_id": m.id,
            "mode": m.mode.value,
            "activity": m.activity.value,
            "state": m.state.value,
            "inactive_reason": m.inactive_reason.value,
            "restricted_reason": m.planner.restricted_reason.value,
            "override_action": m.planner.override_action.value,
            "external_reason": m.planner.external_reason,
            "next_start_ms": m.planner.next_start_ms,
            "error_code": m.error.code,
            "error_confirmable": m.error.confirmable,
            "online": m.is_online,
            "ws_state": self.coordinator.ws_state,
        }

    async def async_start_mowing(self) -> None:
        # No native "resume schedule"; HA's START_MOWING maps to resume.
        await self.coordinator.client.resume_schedule(self._mower_id)

    async def async_pause(self) -> None:
        await self.coordinator.client.pause(self._mower_id)

    async def async_dock(self) -> None:
        await self.coordinator.client.park_until_next_schedule(self._mower_id)

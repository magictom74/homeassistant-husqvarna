"""Device-tracker platform: live GPS position from the mower."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    # Only mowers whose capabilities.position is true get a tracker.
    trackers = [
        HusqvarnaPositionTracker(coordinator, mower_id)
        for mower_id, m in coordinator.data.items()
        if m.capabilities.position
    ]
    async_add_entities(trackers)


class HusqvarnaPositionTracker(HusqvarnaMowerEntity, TrackerEntity):
    """Tracks the latest GPS point pushed via WebSocket."""

    _attr_translation_key = "position"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="position",
            translation_key="position",
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        m = self.mower
        if m is None or m.latest_position is None:
            return None
        return m.latest_position.latitude

    @property
    def longitude(self) -> float | None:
        m = self.mower
        if m is None or m.latest_position is None:
            return None
        return m.latest_position.longitude

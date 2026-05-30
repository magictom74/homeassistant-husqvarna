"""Number platform: global cutting height (1-9)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    async_add_entities(
        CuttingHeightNumber(coordinator, mower_id) for mower_id in coordinator.data
    )


class CuttingHeightNumber(HusqvarnaMowerEntity, NumberEntity):
    """Global cutting height. 1 = lowest, 9 = highest.

    Work-area-specific cutting heights (0-100%) are not exposed as a
    Number entity - that surface is per-area and changes rarely; use
    the ``husqvarna`` service to set them.
    """

    _attr_native_min_value = 1
    _attr_native_max_value = 9
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "cutting_height"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="cutting_height",
            translation_key="cutting_height",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.settings.cutting_height if m is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_cutting_height(self._mower_id, int(value))

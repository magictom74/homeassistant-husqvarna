"""Common base class for all Husqvarna entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from pyhusqvarna import Mower

from .const import DOMAIN, MANUFACTURER
from .coordinator import HusqvarnaCoordinator


class HusqvarnaMowerEntity(CoordinatorEntity[HusqvarnaCoordinator]):
    """Base for per-mower entities.

    Holds the mower id and exposes ``mower`` as a typed Mower (or None
    if the mower has disappeared from the coordinator's snapshot - e.g.
    user removed it from the Husqvarna account).
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HusqvarnaCoordinator,
        mower_id: str,
        *,
        unique_id_suffix: str,
        translation_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._mower_id = mower_id
        self._attr_unique_id = f"{coordinator.entry_id}_{mower_id}_{unique_id_suffix}"
        if translation_key is not None:
            self._attr_translation_key = translation_key

    @property
    def mower(self) -> Mower | None:
        return self.coordinator.get_mower(self._mower_id)

    @property
    def available(self) -> bool:
        m = self.mower
        return m is not None and super().available

    @property
    def device_info(self) -> DeviceInfo:
        m = self.mower
        return DeviceInfo(
            identifiers={(DOMAIN, self._mower_id)},
            manufacturer=MANUFACTURER,
            name=m.name if m is not None else "Husqvarna mower",
            model=m.model if m is not None else None,
            serial_number=str(m.serial_number) if m is not None else None,
            sw_version=None,
        )

    def _extra_attrs(self) -> dict[str, Any]:
        """Convenience for subclasses adding entity-specific attributes."""
        return {}

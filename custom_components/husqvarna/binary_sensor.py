"""Binary sensors: cloud-connected, charging, problem state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    entities: list[BinarySensorEntity] = []
    for mower_id in coordinator.data:
        entities.extend([
            ConnectedSensor(coordinator, mower_id),
            ChargingSensor(coordinator, mower_id),
            ProblemSensor(coordinator, mower_id),
        ])
    async_add_entities(entities)


class ConnectedSensor(HusqvarnaMowerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connected"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="connected",
            translation_key="connected",
        )

    @property
    def is_on(self) -> bool:
        m = self.mower
        return bool(m and m.is_online)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.mower
        return {
            "status_timestamp_ms": m.metadata.status_timestamp_ms if m else 0,
            "ws_state": self.coordinator.ws_state,
        }


class ChargingSensor(HusqvarnaMowerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_translation_key = "charging"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="charging",
            translation_key="charging",
        )

    @property
    def is_on(self) -> bool:
        m = self.mower
        return bool(m and m.is_charging)


class ProblemSensor(HusqvarnaMowerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "problem"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="problem",
            translation_key="problem",
        )

    @property
    def is_on(self) -> bool:
        m = self.mower
        return bool(m and m.has_error)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.mower
        if m is None or not m.has_error:
            return {}
        return {
            "code": m.error.code,
            "confirmable": m.error.confirmable,
            "timestamp_ms": m.error.timestamp_ms,
        }

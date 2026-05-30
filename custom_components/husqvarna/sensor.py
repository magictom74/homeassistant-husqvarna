"""Sensor platform.

Per mower we expose:

* battery percent (with HA's battery device class)
* activity / mode / state / restricted-reason (strings - useful for
  templates and notifications)
* error code (integer; 0 when no error)
* next scheduled start (timestamp)
* total cutting time, charging cycles, collisions (diagnostic)
* alarms / message history (count + list of recent messages with
  severity, code, time and GPS)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
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

    entities: list[SensorEntity] = []
    for mower_id in coordinator.data:
        entities.extend([
            BatterySensor(coordinator, mower_id),
            ActivitySensor(coordinator, mower_id),
            ModeSensor(coordinator, mower_id),
            StateSensor(coordinator, mower_id),
            RestrictedReasonSensor(coordinator, mower_id),
            ErrorCodeSensor(coordinator, mower_id),
            NextStartSensor(coordinator, mower_id),
            CuttingTimeSensor(coordinator, mower_id),
            DistanceSensor(coordinator, mower_id),
            ChargingCyclesSensor(coordinator, mower_id),
            CollisionsSensor(coordinator, mower_id),
            MessagesSensor(coordinator, mower_id),
        ])
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Core state sensors
# ---------------------------------------------------------------------------


class BatterySensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "battery"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="battery",
            translation_key="battery",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.battery.percent if m is not None else None


class ActivitySensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_translation_key = "activity"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="activity",
            translation_key="activity",
        )

    @property
    def native_value(self) -> str | None:
        m = self.mower
        return m.activity.value if m is not None else None


class ModeSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_translation_key = "mode"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="mode",
            translation_key="mode",
        )

    @property
    def native_value(self) -> str | None:
        m = self.mower
        return m.mode.value if m is not None else None


class StateSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_translation_key = "state"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="state",
            translation_key="state",
        )

    @property
    def native_value(self) -> str | None:
        m = self.mower
        return m.state.value if m is not None else None


class RestrictedReasonSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_translation_key = "restricted_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="restricted_reason",
            translation_key="restricted_reason",
        )

    @property
    def native_value(self) -> str | None:
        m = self.mower
        return m.planner.restricted_reason.value if m is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.mower
        if m is None:
            return {}
        return {
            "override_action": m.planner.override_action.value,
            "external_reason": m.planner.external_reason,
        }


class ErrorCodeSensor(HusqvarnaMowerEntity, SensorEntity):
    """Husqvarna fault code, 0 = no error."""

    _attr_translation_key = "error_code"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="error_code",
            translation_key="error_code",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.error.code if m is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.mower
        if m is None or not m.has_error:
            return {}
        return {
            "confirmable": m.error.confirmable,
            "timestamp_ms": m.error.timestamp_ms,
        }


class NextStartSensor(HusqvarnaMowerEntity, SensorEntity):
    """Next scheduled mowing start as a timestamp (None = start now / unknown)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_start"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="next_start",
            translation_key="next_start",
        )

    @property
    def native_value(self) -> datetime | None:
        m = self.mower
        if m is None:
            return None
        ms = m.planner.next_start_ms
        if ms <= 0:
            return None
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Statistics (diagnostic)
# ---------------------------------------------------------------------------


class CuttingTimeSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "cutting_time"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="cutting_time",
            translation_key="cutting_time",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.statistics.total_cutting_seconds if m is not None else None


class DistanceSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = "m"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "distance"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="distance",
            translation_key="distance",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.statistics.total_drive_distance_m if m is not None else None


class ChargingCyclesSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "charging_cycles"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="charging_cycles",
            translation_key="charging_cycles",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.statistics.number_of_charging_cycles if m is not None else None


class CollisionsSensor(HusqvarnaMowerEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "collisions"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="collisions",
            translation_key="collisions",
        )

    @property
    def native_value(self) -> int | None:
        m = self.mower
        return m.statistics.number_of_collisions if m is not None else None


# ---------------------------------------------------------------------------
# Alarm history
# ---------------------------------------------------------------------------


class MessagesSensor(HusqvarnaMowerEntity, SensorEntity):
    """Number of messages currently cached + the recent ones as an attribute.

    Pull-only - the cloud doesn't push these. Use the
    ``husqvarna.refresh_messages`` service to fetch fresh history; the
    list is also populated at integration setup.
    """

    _attr_translation_key = "messages"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="messages",
            translation_key="messages",
        )

    @property
    def native_value(self) -> int:
        return len(self.coordinator.messages_for(self._mower_id))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        msgs = self.coordinator.messages_for(self._mower_id)
        recent = [
            {
                "time_ms": m.timestamp_ms,
                "code": m.code,
                "severity": m.severity.value,
                "latitude": m.latitude,
                "longitude": m.longitude,
            }
            for m in msgs[:10]
        ]
        return {"recent": recent}

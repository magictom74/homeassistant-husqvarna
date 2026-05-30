"""Automower Connect API domain types.

All shapes are derived from the Husqvarna Connect API JSON:API
envelope ``{"data": {"id": ..., "attributes": {...}}}``. The
:class:`Mower` factory accepts both the per-mower object and a
WebSocket delta frame (which only carries the changed attribute
sub-trees - see :meth:`Mower.with_delta`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, TypeVar

from .base import HusqvarnaDevice

_E = TypeVar("_E", bound="_StrEnum")

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class _StrEnum(str, Enum):
    """String-backed enum with a defensive parser.

    Unknown values from the cloud map to ``UNKNOWN`` so a new
    server-side enum value doesn't crash the library.
    """

    @classmethod
    def from_raw(cls: type[_E], value: Any) -> _E:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
        # Every subclass declares an UNKNOWN member; fall back to it.
        return cls("UNKNOWN")


class MowerMode(_StrEnum):
    MAIN_AREA = "MAIN_AREA"
    SECONDARY_AREA = "SECONDARY_AREA"
    HOME = "HOME"
    DEMO = "DEMO"
    POI = "POI"
    UNKNOWN = "UNKNOWN"


class MowerActivity(_StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MOWING = "MOWING"
    GOING_HOME = "GOING_HOME"
    CHARGING = "CHARGING"
    LEAVING = "LEAVING"
    PARKED_IN_CS = "PARKED_IN_CS"
    STOPPED_IN_GARDEN = "STOPPED_IN_GARDEN"


class MowerState(_StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PAUSED = "PAUSED"
    IN_OPERATION = "IN_OPERATION"
    WAIT_UPDATING = "WAIT_UPDATING"
    WAIT_POWER_UP = "WAIT_POWER_UP"
    RESTRICTED = "RESTRICTED"
    OFF = "OFF"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    FATAL_ERROR = "FATAL_ERROR"
    ERROR_AT_POWER_UP = "ERROR_AT_POWER_UP"


class OverrideAction(_StrEnum):
    NOT_ACTIVE = "NOT_ACTIVE"
    FORCE_PARK = "FORCE_PARK"
    FORCE_MOW = "FORCE_MOW"
    UNKNOWN = "UNKNOWN"


class RestrictedReason(_StrEnum):
    NONE = "NONE"
    WEEK_SCHEDULE = "WEEK_SCHEDULE"
    PARK_OVERRIDE = "PARK_OVERRIDE"
    SENSOR = "SENSOR"
    DAILY_LIMIT = "DAILY_LIMIT"
    FOTA = "FOTA"
    FROST = "FROST"
    UNKNOWN = "UNKNOWN"


class InactiveReason(_StrEnum):
    NONE = "NONE"
    PLANNING = "PLANNING"
    SEARCHING_FOR_SATELLITES = "SEARCHING_FOR_SATELLITES"
    UNKNOWN = "UNKNOWN"


class HeadlightMode(_StrEnum):
    ALWAYS_ON = "ALWAYS_ON"
    ALWAYS_OFF = "ALWAYS_OFF"
    EVENING_ONLY = "EVENING_ONLY"
    EVENING_AND_NIGHT = "EVENING_AND_NIGHT"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return default


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Nested types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class System:
    name: str = ""
    model: str = ""
    serial_number: int = 0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> System:
        return cls(
            name=_str(raw.get("name")),
            model=_str(raw.get("model")),
            serial_number=_int(raw.get("serialNumber")),
        )


@dataclass(frozen=True, slots=True)
class Battery:
    percent: int = 0
    remaining_charging_minutes: int = 0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Battery:
        return cls(
            percent=_int(raw.get("batteryPercent")),
            remaining_charging_minutes=_int(raw.get("remainingChargingTime")),
        )


@dataclass(frozen=True, slots=True)
class Capabilities:
    headlights: bool = False
    work_areas: bool = False
    position: bool = False
    can_confirm_error: bool = False
    stay_out_zones: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Capabilities:
        return cls(
            headlights=_bool(raw.get("headlights")),
            work_areas=_bool(raw.get("workAreas")),
            position=_bool(raw.get("position")),
            can_confirm_error=_bool(raw.get("canConfirmError")),
            stay_out_zones=_bool(raw.get("stayOutZones")),
        )


@dataclass(frozen=True, slots=True)
class MowerError:
    """Alarm / fault state of the mower.

    ``code == 0`` means "no error" - everything is fine. Anything else
    is a Husqvarna fault code; the catalogue is published in the
    Automower Connect API docs and can be looked up via the cloud's
    ``/v1/mowers/<id>/errors`` endpoint.

    ``confirmable`` matches the mower's ``canConfirmError`` capability:
    if true, calling :meth:`AutomowerClient.confirm_error` clears the
    alarm without a service visit.
    """

    code: int = 0
    timestamp_ms: int = 0
    confirmable: bool = False

    @property
    def is_active(self) -> bool:
        return self.code != 0

    @classmethod
    def from_mower_raw(cls, raw: dict[str, Any]) -> MowerError:
        return cls(
            code=_int(raw.get("errorCode")),
            timestamp_ms=_int(raw.get("errorCodeTimestamp")),
            confirmable=_bool(raw.get("isErrorConfirmable")),
        )


@dataclass(frozen=True, slots=True)
class Planner:
    next_start_ms: int = 0
    override_action: OverrideAction = OverrideAction.UNKNOWN
    restricted_reason: RestrictedReason = RestrictedReason.UNKNOWN

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Planner:
        override = _dict(raw.get("override"))
        return cls(
            next_start_ms=_int(raw.get("nextStartTimestamp")),
            override_action=OverrideAction.from_raw(override.get("action")),
            restricted_reason=RestrictedReason.from_raw(raw.get("restrictedReason")),
        )


@dataclass(frozen=True, slots=True)
class Metadata:
    connected: bool = False
    status_timestamp_ms: int = 0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Metadata:
        return cls(
            connected=_bool(raw.get("connected")),
            status_timestamp_ms=_int(raw.get("statusTimestamp")),
        )


@dataclass(frozen=True, slots=True)
class CalendarTask:
    start_minutes: int = 0
    duration_minutes: int = 0
    work_area_id: int = 0
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = False
    sunday: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> CalendarTask:
        return cls(
            start_minutes=_int(raw.get("start")),
            duration_minutes=_int(raw.get("duration")),
            work_area_id=_int(raw.get("workAreaId")),
            monday=_bool(raw.get("monday")),
            tuesday=_bool(raw.get("tuesday")),
            wednesday=_bool(raw.get("wednesday")),
            thursday=_bool(raw.get("thursday")),
            friday=_bool(raw.get("friday")),
            saturday=_bool(raw.get("saturday")),
            sunday=_bool(raw.get("sunday")),
        )


@dataclass(frozen=True, slots=True)
class Calendar:
    tasks: tuple[CalendarTask, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Calendar:
        tasks_raw = raw.get("tasks") or []
        if not isinstance(tasks_raw, list):
            return cls()
        return cls(
            tasks=tuple(
                CalendarTask.from_raw(t) for t in tasks_raw if isinstance(t, dict)
            )
        )


@dataclass(frozen=True, slots=True)
class Position:
    latitude: float = 0.0
    longitude: float = 0.0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Position:
        return cls(
            latitude=_float(raw.get("latitude")),
            longitude=_float(raw.get("longitude")),
        )


@dataclass(frozen=True, slots=True)
class WorkArea:
    id: int = 0
    name: str = ""
    type: str = ""
    cutting_height: int = 0
    enabled: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> WorkArea:
        return cls(
            id=_int(raw.get("workAreaId")),
            name=_str(raw.get("name")),
            type=_str(raw.get("type")),
            cutting_height=_int(raw.get("cuttingHeight")),
            enabled=_bool(raw.get("enabled")),
        )


@dataclass(frozen=True, slots=True)
class StayOutZone:
    id: str = ""
    name: str = ""
    enabled: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> StayOutZone:
        return cls(
            id=_str(raw.get("id")),
            name=_str(raw.get("name")),
            enabled=_bool(raw.get("enabled")),
        )


@dataclass(frozen=True, slots=True)
class Settings:
    cutting_height: int = 0
    headlight: HeadlightMode = HeadlightMode.UNKNOWN

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Settings:
        headlight_raw = _dict(raw.get("headlight"))
        return cls(
            cutting_height=_int(raw.get("cuttingHeight")),
            headlight=HeadlightMode.from_raw(headlight_raw.get("mode")),
        )


@dataclass(frozen=True, slots=True)
class Statistics:
    cutting_blade_usage_seconds: int = 0
    down_time_seconds: int = 0
    number_of_charging_cycles: int = 0
    number_of_collisions: int = 0
    total_charging_seconds: int = 0
    total_cutting_seconds: int = 0
    total_drive_distance_m: int = 0
    total_running_seconds: int = 0
    total_searching_seconds: int = 0
    up_time_seconds: int = 0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Statistics:
        return cls(
            cutting_blade_usage_seconds=_int(raw.get("cuttingBladeUsageTime")),
            down_time_seconds=_int(raw.get("downTime")),
            number_of_charging_cycles=_int(raw.get("numberOfChargingCycles")),
            number_of_collisions=_int(raw.get("numberOfCollisions")),
            total_charging_seconds=_int(raw.get("totalChargingTime")),
            total_cutting_seconds=_int(raw.get("totalCuttingTime")),
            total_drive_distance_m=_int(raw.get("totalDriveDistance")),
            total_running_seconds=_int(raw.get("totalRunningTime")),
            total_searching_seconds=_int(raw.get("totalSearchingTime")),
            up_time_seconds=_int(raw.get("upTime")),
        )


# ---------------------------------------------------------------------------
# Top-level Mower
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mower(HusqvarnaDevice):
    """One Automower with the full state snapshot from /v1/mowers."""

    mode: MowerMode = MowerMode.UNKNOWN
    activity: MowerActivity = MowerActivity.UNKNOWN
    state: MowerState = MowerState.UNKNOWN
    inactive_reason: InactiveReason = InactiveReason.UNKNOWN
    work_area_id: int = 0

    battery: Battery = field(default_factory=Battery)
    capabilities: Capabilities = field(default_factory=Capabilities)
    error: MowerError = field(default_factory=MowerError)
    planner: Planner = field(default_factory=Planner)
    metadata: Metadata = field(default_factory=Metadata)
    calendar: Calendar = field(default_factory=Calendar)
    settings: Settings = field(default_factory=Settings)
    statistics: Statistics = field(default_factory=Statistics)

    positions: tuple[Position, ...] = ()
    work_areas: tuple[WorkArea, ...] = ()
    stay_out_zones: tuple[StayOutZone, ...] = ()

    # ------------------------------------------------------------------
    # convenience properties (read-only)
    # ------------------------------------------------------------------

    @property
    def battery_percent(self) -> int:
        return self.battery.percent

    @property
    def is_online(self) -> bool:
        return self.metadata.connected

    @property
    def is_charging(self) -> bool:
        return self.activity is MowerActivity.CHARGING

    @property
    def is_mowing(self) -> bool:
        return self.activity is MowerActivity.MOWING

    @property
    def has_error(self) -> bool:
        return self.error.is_active

    @property
    def error_confirmable(self) -> bool:
        return self.error.is_active and self.error.confirmable

    @property
    def latest_position(self) -> Position | None:
        return self.positions[0] if self.positions else None

    # ------------------------------------------------------------------
    # constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Mower:
        """Parse one JSON:API mower entry.

        Accepts both shapes::

            {"id": "...", "attributes": {...}}                  # direct
            {"data": {"id": "...", "attributes": {...}}}        # single-wrapped
        """
        if "data" in raw and isinstance(raw["data"], dict):
            raw = raw["data"]

        attrs = _dict(raw.get("attributes"))
        system = System.from_raw(_dict(attrs.get("system")))
        metadata = Metadata.from_raw(_dict(attrs.get("metadata")))
        mower_attrs = _dict(attrs.get("mower"))

        return cls(
            id=_str(raw.get("id")),
            name=system.name,
            model=system.model,
            serial_number=system.serial_number,
            online=metadata.connected,
            mode=MowerMode.from_raw(mower_attrs.get("mode")),
            activity=MowerActivity.from_raw(mower_attrs.get("activity")),
            state=MowerState.from_raw(mower_attrs.get("state")),
            inactive_reason=InactiveReason.from_raw(mower_attrs.get("inactiveReason")),
            work_area_id=_int(mower_attrs.get("workAreaId")),
            battery=Battery.from_raw(_dict(attrs.get("battery"))),
            capabilities=Capabilities.from_raw(_dict(attrs.get("capabilities"))),
            error=MowerError.from_mower_raw(mower_attrs),
            planner=Planner.from_raw(_dict(attrs.get("planner"))),
            metadata=metadata,
            calendar=Calendar.from_raw(_dict(attrs.get("calendar"))),
            settings=Settings.from_raw(_dict(attrs.get("settings"))),
            statistics=Statistics.from_raw(_dict(attrs.get("statistics"))),
            positions=tuple(
                Position.from_raw(p)
                for p in (attrs.get("positions") or [])
                if isinstance(p, dict)
            ),
            work_areas=tuple(
                WorkArea.from_raw(w)
                for w in (attrs.get("workAreas") or [])
                if isinstance(w, dict)
            ),
            stay_out_zones=tuple(
                StayOutZone.from_raw(z)
                for z in (attrs.get("stayOutZones") or [])
                if isinstance(z, dict)
            ),
        )

    def with_delta(self, frame: dict[str, Any]) -> Mower:
        """Apply a WebSocket delta frame and return an updated copy.

        The cloud's WS pushes only the changed attribute sub-trees,
        not the full mower object. We merge them onto a copy of the
        current state and re-derive the convenience surface
        (``online`` from ``metadata.connected``, etc.).

        Frame shape::

            {"id": "<mower-id>", "type": "<event-type>", "attributes": {...}}
        """
        attrs = _dict(frame.get("attributes"))
        if not attrs:
            return self

        changes: dict[str, Any] = {}

        if "mower" in attrs:
            m = _dict(attrs["mower"])
            if "mode" in m:
                changes["mode"] = MowerMode.from_raw(m["mode"])
            if "activity" in m:
                changes["activity"] = MowerActivity.from_raw(m["activity"])
            if "state" in m:
                changes["state"] = MowerState.from_raw(m["state"])
            if "inactiveReason" in m:
                changes["inactive_reason"] = InactiveReason.from_raw(m["inactiveReason"])
            if "workAreaId" in m:
                changes["work_area_id"] = _int(m["workAreaId"])
            if any(k in m for k in ("errorCode", "errorCodeTimestamp", "isErrorConfirmable")):
                merged = {
                    "errorCode": m.get("errorCode", self.error.code),
                    "errorCodeTimestamp": m.get(
                        "errorCodeTimestamp", self.error.timestamp_ms
                    ),
                    "isErrorConfirmable": m.get(
                        "isErrorConfirmable", self.error.confirmable
                    ),
                }
                changes["error"] = MowerError.from_mower_raw(merged)

        if "battery" in attrs:
            changes["battery"] = Battery.from_raw(_dict(attrs["battery"]))

        if "planner" in attrs:
            changes["planner"] = Planner.from_raw(_dict(attrs["planner"]))

        if "metadata" in attrs:
            metadata = Metadata.from_raw(_dict(attrs["metadata"]))
            changes["metadata"] = metadata
            changes["online"] = metadata.connected

        if "calendar" in attrs:
            changes["calendar"] = Calendar.from_raw(_dict(attrs["calendar"]))

        if "settings" in attrs:
            changes["settings"] = Settings.from_raw(_dict(attrs["settings"]))

        if "statistics" in attrs:
            changes["statistics"] = Statistics.from_raw(_dict(attrs["statistics"]))

        if "positions" in attrs and isinstance(attrs["positions"], list):
            changes["positions"] = tuple(
                Position.from_raw(p) for p in attrs["positions"] if isinstance(p, dict)
            )

        return replace(self, **changes) if changes else self

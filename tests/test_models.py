"""Unit tests for the Automower dataclass models."""

from __future__ import annotations

import pytest

from pyhusqvarna import (
    HeadlightMode,
    InactiveReason,
    MessageSeverity,
    Mower,
    MowerActivity,
    MowerError,
    MowerMessage,
    MowerMode,
    MowerState,
    OverrideAction,
    Planner,
    RestrictedReason,
)


def make_full_raw() -> dict[str, object]:
    """One mower payload close to a real /v1/mowers entry."""
    return {
        "type": "mower",
        "id": "<MOWER_UUID>",
        "attributes": {
            "system": {
                "name": "Test Mower",
                "model": "Husqvarna Automower 305E NERA",
                "serialNumber": 12345678,
            },
            "battery": {"batteryPercent": 87, "remainingChargingTime": 0},
            "capabilities": {
                "headlights": False,
                "workAreas": True,
                "position": True,
                "canConfirmError": True,
                "stayOutZones": True,
            },
            "mower": {
                "mode": "MAIN_AREA",
                "activity": "MOWING",
                "inactiveReason": "NONE",
                "state": "IN_OPERATION",
                "workAreaId": 0,
                "errorCode": 0,
                "errorCodeTimestamp": 0,
                "isErrorConfirmable": False,
            },
            "calendar": {
                "tasks": [
                    {
                        "start": 570, "duration": 150,
                        "monday": True, "tuesday": False, "wednesday": True,
                        "thursday": False, "friday": True, "saturday": False,
                        "sunday": False, "workAreaId": 0,
                    },
                ],
            },
            "planner": {
                "nextStartTimestamp": 1779874200000,
                "override": {"action": "NOT_ACTIVE"},
                "restrictedReason": "NONE",
            },
            "metadata": {
                "connected": True,
                "statusTimestamp": 1779825307733,
            },
            "workAreas": [
                {"workAreaId": 0, "name": "", "type": "RANDOM",
                 "cuttingHeight": 100, "enabled": True},
            ],
            "positions": [
                {"latitude": 47.3, "longitude": 8.4},
                {"latitude": 47.31, "longitude": 8.41},
            ],
            "settings": {"cuttingHeight": 8, "headlight": {"mode": None}},
            "statistics": {
                "cuttingBladeUsageTime": 516863,
                "downTime": 2172729,
                "numberOfChargingCycles": 180,
                "numberOfCollisions": 6191,
                "totalChargingTime": 335905,
                "totalCuttingTime": 516863,
                "totalDriveDistance": 246110,
                "totalRunningTime": 585975,
                "totalSearchingTime": 56566,
                "upTime": 4720245,
            },
        },
    }


class TestEnums:
    def test_known_modes_parse(self) -> None:
        assert MowerMode.from_raw("MAIN_AREA") is MowerMode.MAIN_AREA
        assert MowerMode.from_raw("HOME") is MowerMode.HOME

    def test_unknown_mode_falls_back(self) -> None:
        assert MowerMode.from_raw("FUTURE_VALUE") is MowerMode.UNKNOWN
        assert MowerMode.from_raw(None) is MowerMode.UNKNOWN
        assert MowerMode.from_raw(123) is MowerMode.UNKNOWN

    def test_activity_charging(self) -> None:
        assert MowerActivity.from_raw("CHARGING") is MowerActivity.CHARGING

    def test_state_fatal_error(self) -> None:
        assert MowerState.from_raw("FATAL_ERROR") is MowerState.FATAL_ERROR

    def test_override_action(self) -> None:
        assert OverrideAction.from_raw("FORCE_PARK") is OverrideAction.FORCE_PARK

    def test_restricted_reason(self) -> None:
        assert RestrictedReason.from_raw("FROST") is RestrictedReason.FROST

    def test_inactive_reason(self) -> None:
        assert InactiveReason.from_raw("SEARCHING_FOR_SATELLITES") is (
            InactiveReason.SEARCHING_FOR_SATELLITES
        )

    def test_headlight_mode(self) -> None:
        assert HeadlightMode.from_raw("EVENING_ONLY") is HeadlightMode.EVENING_ONLY


class TestMowerFromRaw:
    def test_full_payload(self) -> None:
        m = Mower.from_raw(make_full_raw())
        assert m.id == "<MOWER_UUID>"
        assert m.name == "Test Mower"
        assert m.model == "Husqvarna Automower 305E NERA"
        assert m.serial_number == 12345678
        assert m.online is True
        assert m.mode is MowerMode.MAIN_AREA
        assert m.activity is MowerActivity.MOWING
        assert m.state is MowerState.IN_OPERATION
        assert m.battery.percent == 87
        assert m.capabilities.position is True
        assert m.capabilities.can_confirm_error is True
        assert m.error.is_active is False
        assert m.planner.next_start_ms > 0
        assert m.planner.override_action is OverrideAction.NOT_ACTIVE
        assert m.calendar.tasks[0].start_minutes == 570
        assert m.calendar.tasks[0].monday is True
        assert len(m.positions) == 2
        assert m.latest_position is not None
        assert m.settings.cutting_height == 8
        assert m.statistics.number_of_collisions == 6191

    def test_data_wrapper_is_accepted(self) -> None:
        wrapped = {"data": make_full_raw()}
        m = Mower.from_raw(wrapped)
        assert m.id == "<MOWER_UUID>"

    def test_convenience_properties(self) -> None:
        m = Mower.from_raw(make_full_raw())
        assert m.battery_percent == 87
        assert m.is_online is True
        assert m.is_mowing is True
        assert m.is_charging is False
        assert m.has_error is False
        assert m.error_confirmable is False

    def test_mower_with_active_error(self) -> None:
        raw = make_full_raw()
        raw["attributes"]["mower"].update({  # type: ignore[index]
            "state": "ERROR",
            "activity": "STOPPED_IN_GARDEN",
            "errorCode": 15,
            "errorCodeTimestamp": 1779800000000,
            "isErrorConfirmable": True,
        })
        m = Mower.from_raw(raw)
        assert m.has_error is True
        assert m.error.code == 15
        assert m.error.confirmable is True
        assert m.error_confirmable is True
        assert m.state is MowerState.ERROR
        assert m.activity is MowerActivity.STOPPED_IN_GARDEN

    def test_missing_attributes_defaults(self) -> None:
        m = Mower.from_raw({"id": "x"})
        assert m.id == "x"
        assert m.name == ""
        assert m.mode is MowerMode.UNKNOWN
        assert m.activity is MowerActivity.UNKNOWN
        assert m.battery.percent == 0
        assert m.has_error is False

    def test_mower_is_frozen(self) -> None:
        m = Mower.from_raw(make_full_raw())
        with pytest.raises(Exception):
            m.name = "other"  # type: ignore[misc]


class TestMowerWithDelta:
    def test_battery_delta_only(self) -> None:
        m = Mower.from_raw(make_full_raw())
        updated = m.with_delta({
            "id": m.id, "type": "battery-event-v1",
            "attributes": {"battery": {"batteryPercent": 42}},
        })
        # Battery dropped
        assert updated.battery.percent == 42
        # Everything else is unchanged
        assert updated.activity is MowerActivity.MOWING
        assert updated.serial_number == m.serial_number
        # And the originals are unchanged (frozen+copy semantics)
        assert m.battery.percent == 87

    def test_mode_and_activity_delta(self) -> None:
        m = Mower.from_raw(make_full_raw())
        updated = m.with_delta({
            "id": m.id, "type": "status-event-v1",
            "attributes": {
                "mower": {"mode": "HOME", "activity": "GOING_HOME"},
            },
        })
        assert updated.mode is MowerMode.HOME
        assert updated.activity is MowerActivity.GOING_HOME
        # state must be left alone since it wasn't in the delta
        assert updated.state is MowerState.IN_OPERATION

    def test_error_partial_delta_preserves_other_error_fields(self) -> None:
        m = Mower.from_raw(make_full_raw())
        updated = m.with_delta({
            "id": m.id, "type": "status-event-v1",
            "attributes": {
                "mower": {"errorCode": 7, "isErrorConfirmable": True},
            },
        })
        assert updated.error.code == 7
        assert updated.error.confirmable is True
        # timestamp wasn't in the delta - kept from the previous state
        assert updated.error.timestamp_ms == m.error.timestamp_ms

    def test_metadata_connected_propagates_to_online(self) -> None:
        m = Mower.from_raw(make_full_raw())
        updated = m.with_delta({
            "id": m.id, "type": "status-event-v1",
            "attributes": {
                "metadata": {"connected": False, "statusTimestamp": 1779999999000},
            },
        })
        assert updated.online is False
        assert updated.is_online is False

    def test_empty_delta_returns_same(self) -> None:
        m = Mower.from_raw(make_full_raw())
        assert m.with_delta({"id": m.id, "type": "noop"}) is m

    def test_position_delta_replaces(self) -> None:
        m = Mower.from_raw(make_full_raw())
        updated = m.with_delta({
            "id": m.id, "type": "positions-event-v1",
            "attributes": {"positions": [{"latitude": 47.99, "longitude": 8.99}]},
        })
        assert len(updated.positions) == 1
        assert updated.positions[0].latitude == 47.99

    def test_position_event_v2_singular_is_prepended(self) -> None:
        # Real shape captured 2026-05-30 from the live WS: a single point
        # under "position" (singular), not the "positions" array shape.
        m = Mower.from_raw(make_full_raw())
        initial_count = len(m.positions)
        first_point = m.positions[0]
        updated = m.with_delta({
            "id": m.id, "type": "position-event-v2",
            "attributes": {"position": {"latitude": 47.5, "longitude": 8.5}},
        })
        # New point is at the front, history is preserved
        assert len(updated.positions) == initial_count + 1
        assert updated.positions[0].latitude == 47.5
        assert updated.positions[0].longitude == 8.5
        assert updated.positions[1] == first_point

    def test_position_event_v2_caps_at_50(self) -> None:
        # Build a Mower with 50 already-known positions; the new point
        # must push one off the end.
        raw = make_full_raw()
        raw["attributes"]["positions"] = [  # type: ignore[index]
            {"latitude": float(i), "longitude": float(i)} for i in range(50)
        ]
        m = Mower.from_raw(raw)
        assert len(m.positions) == 50
        updated = m.with_delta({
            "id": m.id, "type": "position-event-v2",
            "attributes": {"position": {"latitude": 99.0, "longitude": 99.0}},
        })
        assert len(updated.positions) == 50
        assert updated.positions[0].latitude == 99.0


class TestPlanner:
    def test_external_reason_parsed(self) -> None:
        p = Planner.from_raw({
            "nextStartTimestamp": 0,
            "override": {"action": "FORCE_PARK"},
            "restrictedReason": "EXTERNAL",
            "externalReason": 200042,
        })
        assert p.restricted_reason is RestrictedReason.EXTERNAL
        assert p.external_reason == 200042

    def test_external_reason_defaults_to_zero(self) -> None:
        p = Planner.from_raw({
            "nextStartTimestamp": 0,
            "override": {"action": "NOT_ACTIVE"},
            "restrictedReason": "NONE",
        })
        assert p.external_reason == 0

    def test_new_restricted_reasons(self) -> None:
        for raw, expected in [
            ("ALL_WORK_AREAS_COMPLETED", RestrictedReason.ALL_WORK_AREAS_COMPLETED),
            ("EXTERNAL", RestrictedReason.EXTERNAL),
            ("WORK_AREA_ABANDONED", RestrictedReason.WORK_AREA_ABANDONED),
        ]:
            assert RestrictedReason.from_raw(raw) is expected


class TestMowerMessage:
    def test_full_message(self) -> None:
        msg = MowerMessage.from_raw({
            "time": 1724158848,
            "code": 49,
            "severity": "WARNING",
            "latitude": 58.3855176,
            "longitude": 15.4201136,
        })
        assert msg.timestamp_ms == 1724158848
        assert msg.code == 49
        assert msg.severity is MessageSeverity.WARNING
        assert msg.latitude == 58.3855176
        assert msg.longitude == 15.4201136

    def test_message_without_position(self) -> None:
        msg = MowerMessage.from_raw({"time": 0, "code": 15, "severity": "ERROR"})
        assert msg.latitude is None
        assert msg.longitude is None

    def test_severity_unknown_falls_back(self) -> None:
        msg = MowerMessage.from_raw({"time": 0, "code": 0, "severity": "FUTURE"})
        assert msg.severity is MessageSeverity.UNKNOWN

"""Domain models for the Husqvarna cloud APIs.

The model hierarchy is split per product family so additional ones
(Husqvarna Connect outdoor-power-equipment, future tools) can be
added without touching the mower types::

    pyhusqvarna.models.base       - cross-family abstractions
    pyhusqvarna.models.automower  - Automower-specific dataclasses + enums
"""

from __future__ import annotations

from .automower import (
    Battery,
    Calendar,
    CalendarTask,
    Capabilities,
    HeadlightMode,
    InactiveReason,
    Metadata,
    Mower,
    MowerActivity,
    MowerError,
    MowerMode,
    MowerState,
    OverrideAction,
    Planner,
    Position,
    RestrictedReason,
    Settings,
    Statistics,
    StayOutZone,
    System,
    WorkArea,
)
from .base import HusqvarnaDevice

__all__ = [
    "Battery",
    "Calendar",
    "CalendarTask",
    "Capabilities",
    "HeadlightMode",
    "HusqvarnaDevice",
    "InactiveReason",
    "Metadata",
    "Mower",
    "MowerActivity",
    "MowerError",
    "MowerMode",
    "MowerState",
    "OverrideAction",
    "Planner",
    "Position",
    "RestrictedReason",
    "Settings",
    "Statistics",
    "StayOutZone",
    "System",
    "WorkArea",
]

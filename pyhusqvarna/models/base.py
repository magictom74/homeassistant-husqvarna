"""Cross-family device base.

Every Husqvarna cloud product exposes at minimum a stable device id,
a user-facing name, an online indicator, and a model string. Product
families derive from :class:`HusqvarnaDevice` and add their own
domain fields (mower state for Automower, water-flow for a future
irrigation product, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HusqvarnaDevice:
    """The minimal cross-family device shape."""

    id: str
    name: str
    model: str
    serial_number: int
    online: bool

"""API-family clients.

Each Husqvarna cloud product family gets its own client module
here. They all share :class:`pyhusqvarna.auth.HusqvarnaAuth` for
OAuth and the WebSocket plumbing.
"""

from __future__ import annotations

from .automower import (
    DEFAULT_REST_TIMEOUT,
    AutomowerClient,
)

__all__ = ["DEFAULT_REST_TIMEOUT", "AutomowerClient"]

"""pyhusqvarna - async Python library for the Husqvarna cloud APIs.

Today covers the Automower Connect API end-to-end (REST + WebSocket).
The package layout (``pyhusqvarna.api.*``, ``pyhusqvarna.models.*``)
keeps room for further Husqvarna Connect product families behind the
same auth and WebSocket plumbing.
"""

from __future__ import annotations

from .api import DEFAULT_REST_TIMEOUT, AutomowerClient
from .auth import (
    DEFAULT_AUTH_TIMEOUT,
    TOKEN_SAFETY_MARGIN_SECONDS,
    TOKEN_URL,
    AccessToken,
    HusqvarnaAuth,
)
from .exceptions import (
    AuthError,
    HusqvarnaConnectionError,
    HusqvarnaError,
    HusqvarnaTimeoutError,
    NotFoundError,
    ProtocolError,
    RateLimitError,
    SimultaneousLoginsError,
    WebSocketError,
)
from .models import (
    Battery,
    Calendar,
    CalendarTask,
    Capabilities,
    HeadlightMode,
    HusqvarnaDevice,
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
from .ws import (
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_RECEIVE_TIMEOUT,
    WS_URL,
    FrameHandler,
    HusqvarnaWebSocketClient,
    StateHandler,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_AUTH_TIMEOUT",
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_RECEIVE_TIMEOUT",
    "DEFAULT_REST_TIMEOUT",
    "TOKEN_SAFETY_MARGIN_SECONDS",
    "TOKEN_URL",
    "WS_URL",
    "AccessToken",
    "AuthError",
    "AutomowerClient",
    "Battery",
    "Calendar",
    "CalendarTask",
    "Capabilities",
    "FrameHandler",
    "HeadlightMode",
    "HusqvarnaAuth",
    "HusqvarnaConnectionError",
    "HusqvarnaDevice",
    "HusqvarnaError",
    "HusqvarnaTimeoutError",
    "HusqvarnaWebSocketClient",
    "InactiveReason",
    "Metadata",
    "Mower",
    "MowerActivity",
    "MowerError",
    "MowerMode",
    "MowerState",
    "NotFoundError",
    "OverrideAction",
    "Planner",
    "Position",
    "ProtocolError",
    "RateLimitError",
    "RestrictedReason",
    "Settings",
    "SimultaneousLoginsError",
    "StateHandler",
    "Statistics",
    "StayOutZone",
    "System",
    "WebSocketError",
    "WorkArea",
]

"""Exceptions raised by pyhusqvarna."""

from __future__ import annotations


class HusqvarnaError(Exception):
    """Base class for all pyhusqvarna errors."""


class AuthError(HusqvarnaError):
    """OAuth2 token request failed."""


class SimultaneousLoginsError(AuthError):
    """Cloud rejected a token request because another login is in progress.

    Husqvarna locks the client_id for a few minutes when multiple
    parallel auth requests come from the same app. The cure is to
    *not* re-authenticate aggressively - cache the 24-hour token and
    only refresh when it actually expires or returns 401.
    """


class HusqvarnaConnectionError(HusqvarnaError):
    """Cloud REST endpoint is unreachable or refused the connection."""


class HusqvarnaTimeoutError(HusqvarnaError):
    """A request to the cloud timed out."""


class NotFoundError(HusqvarnaError):
    """The requested resource (mower id, work area, zone) does not exist."""


class RateLimitError(HusqvarnaError):
    """Husqvarna returned 429 - too many requests this month/hour."""


class ProtocolError(HusqvarnaError):
    """Cloud returned an unexpected response shape."""


class WebSocketError(HusqvarnaError):
    """WebSocket handshake or transport failure."""

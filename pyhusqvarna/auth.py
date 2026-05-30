"""OAuth2 client-credentials auth against the Husqvarna Group identity provider.

The token returned here covers every Husqvarna Connect product (Automower
today, more in future) because the cloud uses a single Group-wide
identity provider. The class is therefore intentionally not
Automower-specific - it lives at the top of pyhusqvarna and is shared
by every API-family client.

Critical behaviour:

* **Cache the 24-hour token aggressively.** Husqvarna locks the
  ``client_id`` (``simultaneous.logins`` error) when several parallel
  auth requests come in for the same app. Many existing integrations
  hit this by re-authenticating on every WebSocket reconnect; we
  refresh only when the token has actually expired or after a 401.
* **Safety margin.** We refresh 5 minutes *before* the cloud-claimed
  expiry so a near-edge token doesn't get used for a long-running WS
  handshake.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .exceptions import (
    AuthError,
    HusqvarnaConnectionError,
    HusqvarnaTimeoutError,
    SimultaneousLoginsError,
)

_LOGGER = logging.getLogger(__name__)

TOKEN_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
TOKEN_SAFETY_MARGIN_SECONDS = 300  # 5 min before stated expiry
DEFAULT_AUTH_TIMEOUT = 15.0


@dataclass(frozen=True, slots=True)
class AccessToken:
    """A cached Husqvarna access token plus its expiry deadline."""

    value: str
    provider: str
    user_id: str
    expires_at: float  # monotonic clock seconds

    def is_valid(self, *, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock < self.expires_at


class HusqvarnaAuth:
    """OAuth2 client-credentials with caching.

    Usage::

        auth = HusqvarnaAuth(api_key="...", api_secret="...")
        token = await auth.get_token()
        # use token.value in Authorization: Bearer header

    All API clients (AutomowerClient, future Husqvarna-Connect clients)
    share one auth instance.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        timeout: float = DEFAULT_AUTH_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret are required")
        self._api_key = api_key
        self._api_secret = api_secret
        self._timeout = timeout
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self._token: AccessToken | None = None
        self._lock = asyncio.Lock()

    @property
    def api_key(self) -> str:
        """The Application Key. Used as the ``X-Api-Key`` header value."""
        return self._api_key

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> HusqvarnaAuth:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def get_token(self, *, force_refresh: bool = False) -> AccessToken:
        """Return a valid token, fetching a new one only when needed.

        Set ``force_refresh=True`` to invalidate the cached token -
        the cloud signals this is necessary by returning 401 on a
        REST call or 4001/4003 on the WebSocket. **Do not** use it
        on every reconnect.
        """
        async with self._lock:
            if (
                not force_refresh
                and self._token is not None
                and self._token.is_valid()
            ):
                return self._token
            self._token = await self._request_new_token()
            return self._token

    async def _request_new_token(self) -> AccessToken:
        _LOGGER.debug("[husqvarna.auth] Requesting new access token")
        try:
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._api_key,
                    "client_secret": self._api_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException as exc:
            raise HusqvarnaTimeoutError(f"Token request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise HusqvarnaConnectionError(f"Token request connection error: {exc}") from exc

        if response.status_code == 400:
            payload = _safe_json(response)
            if (
                isinstance(payload, dict)
                and payload.get("error_code") == "simultaneous.logins"
            ):
                raise SimultaneousLoginsError(
                    "Husqvarna locked client_id for simultaneous logins. "
                    "Stop any other process using the same app key and "
                    "wait a few minutes before retrying."
                )
            raise AuthError(
                f"Token request rejected: {response.status_code} {response.text!r}"
            )
        if response.status_code != 200:
            raise AuthError(
                f"Token request returned {response.status_code}: {response.text!r}"
            )

        payload = _safe_json(response)
        if not isinstance(payload, dict) or "access_token" not in payload:
            raise AuthError(f"Token response had unexpected shape: {payload!r}")

        expires_in = payload.get("expires_in", 86400)
        if not isinstance(expires_in, (int, float)):
            expires_in = 86400
        expires_at = time.monotonic() + max(60, int(expires_in) - TOKEN_SAFETY_MARGIN_SECONDS)

        return AccessToken(
            value=str(payload["access_token"]),
            provider=str(payload.get("provider") or "husqvarna"),
            user_id=str(payload.get("user_id") or ""),
            expires_at=expires_at,
        )

    def auth_headers(self, token: AccessToken) -> dict[str, str]:
        """All three required headers in one place.

        Use these for every REST call AND for the WebSocket handshake.
        Missing any one of them yields ``403 Forbidden`` - that's the
        bug behind most third-party integrations stuck in a reconnect
        loop.
        """
        return {
            "Authorization": f"Bearer {token.value}",
            "X-Api-Key": self._api_key,
            "Authorization-Provider": token.provider,
        }


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None

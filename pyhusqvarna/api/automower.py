"""REST client for the Automower Connect API.

The four use-cases the user wants covered are explicit methods on
this client:

* **Remote control** - :meth:`park_until_next_schedule`,
  :meth:`park_until_further_notice`, :meth:`park_for`,
  :meth:`resume_schedule`, :meth:`pause`, :meth:`start_for`.
* **Error confirmation** - :meth:`confirm_error` (only valid when
  ``Mower.error_confirmable`` is true).
* **Alarms** - surfaced via the :class:`~pyhusqvarna.models.MowerError`
  on the mower itself (no separate endpoint needed - the error code,
  timestamp, and ``confirmable`` flag are part of every state read
  and every WebSocket frame that touches the ``mower`` sub-tree).
* **State** - :meth:`list_mowers` / :meth:`get_mower` returns the
  full :class:`~pyhusqvarna.models.Mower` snapshot.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from ..auth import HusqvarnaAuth
from ..exceptions import (
    HusqvarnaConnectionError,
    HusqvarnaTimeoutError,
    NotFoundError,
    ProtocolError,
    RateLimitError,
)
from ..models import HeadlightMode, Mower, MowerMessage, StayOutZone, WorkArea

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.amc.husqvarna.dev"
DEFAULT_REST_TIMEOUT = 15.0


class AutomowerClient:
    """Async REST client for the Automower Connect API.

    Usage::

        auth = HusqvarnaAuth(api_key=..., api_secret=...)
        async with AutomowerClient(auth) as client:
            mowers = await client.list_mowers()
            await client.park_until_next_schedule(mowers[0].id)
            if mowers[0].error_confirmable:
                await client.confirm_error(mowers[0].id)
    """

    def __init__(
        self,
        auth: HusqvarnaAuth,
        *,
        timeout: float = DEFAULT_REST_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth = auth
        self._timeout = timeout
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    @property
    def auth(self) -> HusqvarnaAuth:
        return self._auth

    async def __aenter__(self) -> AutomowerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # low-level transport
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        url = f"{BASE_URL}{path}"
        token = await self._auth.get_token()
        headers = self._auth.auth_headers(token)
        if json_body is not None:
            headers["Content-Type"] = "application/vnd.api+json"

        try:
            response = await self._http.request(
                method, url, headers=headers, json=json_body
            )
        except httpx.TimeoutException as exc:
            raise HusqvarnaTimeoutError(f"{method} {url} timed out") from exc
        except httpx.HTTPError as exc:
            raise HusqvarnaConnectionError(f"{method} {url}: {exc}") from exc

        # 401 -> our cached token has been revoked. Refresh once and retry.
        if response.status_code == 401 and retry_on_401:
            _LOGGER.debug("[husqvarna.automower] 401 - refreshing token and retrying")
            await self._auth.get_token(force_refresh=True)
            return await self._request(
                method, path, json_body=json_body, retry_on_401=False
            )

        if response.status_code == 404:
            raise NotFoundError(f"{method} {url} returned 404")
        if response.status_code == 429:
            raise RateLimitError(f"{method} {url} returned 429 (rate-limited)")
        if response.status_code >= 400:
            raise ProtocolError(
                f"{method} {url} returned {response.status_code}: {response.text!r}"
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ProtocolError(
                f"{method} {url} returned non-JSON: {response.text!r}"
            ) from exc

    # ------------------------------------------------------------------
    # state reads
    # ------------------------------------------------------------------

    async def list_mowers(self) -> tuple[Mower, ...]:
        """GET /v1/mowers - returns every mower the app has access to."""
        raw = await self._request("GET", "/v1/mowers")
        if not isinstance(raw, dict) or "data" not in raw:
            raise ProtocolError(f"/v1/mowers returned unexpected shape: {raw!r}")
        items = raw.get("data") or []
        if not isinstance(items, list):
            raise ProtocolError(f"/v1/mowers data was not a list: {items!r}")
        return tuple(Mower.from_raw(item) for item in items if isinstance(item, dict))

    async def get_mower(self, mower_id: str) -> Mower:
        """GET /v1/mowers/<id> - single mower state."""
        raw = await self._request("GET", f"/v1/mowers/{mower_id}")
        if not isinstance(raw, dict):
            raise ProtocolError(f"get_mower returned non-dict: {raw!r}")
        return Mower.from_raw(raw)

    # ------------------------------------------------------------------
    # remote control (the "fernsteuerung" surface)
    # ------------------------------------------------------------------

    async def park_until_next_schedule(self, mower_id: str) -> None:
        """Park until the next scheduled mowing window starts."""
        await self._action(mower_id, "ParkUntilNextSchedule")

    async def park_until_further_notice(self, mower_id: str) -> None:
        """Park until explicitly resumed. Schedule is ignored."""
        await self._action(mower_id, "ParkUntilFurtherNotice")

    async def park_for(self, mower_id: str, *, duration_minutes: int) -> None:
        """Park for a fixed duration, then resume the schedule."""
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be > 0")
        await self._action(
            mower_id, "Park", attributes={"duration": int(duration_minutes)}
        )

    async def resume_schedule(self, mower_id: str) -> None:
        """Resume the configured weekly schedule."""
        await self._action(mower_id, "ResumeSchedule")

    async def pause(self, mower_id: str) -> None:
        """Pause immediately. Mower stays in the field."""
        await self._action(mower_id, "Pause")

    async def start_for(self, mower_id: str, *, duration_minutes: int) -> None:
        """Start mowing now for *duration_minutes*, overriding the schedule."""
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be > 0")
        await self._action(
            mower_id, "Start", attributes={"duration": int(duration_minutes)}
        )

    async def start_in_work_area(
        self, mower_id: str, *, work_area_id: int, duration_minutes: int
    ) -> None:
        """Start mowing in a specific work area for *duration_minutes*."""
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be > 0")
        await self._action(
            mower_id,
            "StartInWorkArea",
            attributes={
                "duration": int(duration_minutes),
                "workAreaId": int(work_area_id),
            },
        )

    # ------------------------------------------------------------------
    # error confirmation (the "fehler ruechstellung" surface)
    # ------------------------------------------------------------------

    async def confirm_error(self, mower_id: str) -> None:
        """Clear the current error via the dedicated /errors/confirm endpoint.

        Only succeeds when the mower's last reported state had
        ``isErrorConfirmable: true``. Available on 405X, 415X, 435X AWD,
        535 AWD and all Ceora / EPOS / NERA models.

        Note: this is **not** an ``/actions`` POST despite what older
        third-party adapters do. The cloud's REST schema (v1.0.0) makes
        this a separate endpoint, and ``/actions`` with type
        ``ConfirmError`` is not in the action enum.
        """
        await self._request(
            "POST", f"/v1/mowers/{mower_id}/errors/confirm", json_body={}
        )

    # ------------------------------------------------------------------
    # alarms / message history
    # ------------------------------------------------------------------

    async def get_messages(self, mower_id: str) -> tuple[MowerMessage, ...]:
        """GET /v1/mowers/<id>/messages - up to 50 latest mower messages.

        Pull-only (not pushed via WebSocket). Returned newest-first.
        """
        raw = await self._request("GET", f"/v1/mowers/{mower_id}/messages")
        if not isinstance(raw, dict):
            raise ProtocolError(f"get_messages returned non-dict: {raw!r}")
        data = raw.get("data")
        if not isinstance(data, dict):
            return ()
        attrs = data.get("attributes")
        if not isinstance(attrs, dict):
            return ()
        msgs = attrs.get("messages")
        if not isinstance(msgs, list):
            return ()
        return tuple(MowerMessage.from_raw(m) for m in msgs if isinstance(m, dict))

    # ------------------------------------------------------------------
    # settings (cutting height, headlight) - POST, not PATCH!
    # ------------------------------------------------------------------

    async def set_cutting_height(self, mower_id: str, height: int) -> None:
        """Set the global cutting height (1-9)."""
        if not 1 <= height <= 9:
            raise ValueError("cutting height must be in 1..9")
        await self._post_settings(mower_id, {"cuttingHeight": int(height)})

    async def set_headlight_mode(self, mower_id: str, mode: HeadlightMode) -> None:
        """Set the headlight mode (only useful when capability.headlights)."""
        if mode is HeadlightMode.UNKNOWN:
            raise ValueError("UNKNOWN is not a settable headlight mode")
        await self._post_settings(mower_id, {"headlight": {"mode": mode.value}})

    # ------------------------------------------------------------------
    # statistics
    # ------------------------------------------------------------------

    async def reset_cutting_blade_usage_time(self, mower_id: str) -> None:
        """Reset the cutting-blade usage timer (after a blade change)."""
        await self._request(
            "POST",
            f"/v1/mowers/{mower_id}/statistics/resetCuttingBladeUsageTime",
            json_body={},
        )

    # ------------------------------------------------------------------
    # stay-out zones
    # ------------------------------------------------------------------

    async def get_stay_out_zones(self, mower_id: str) -> tuple[StayOutZone, ...]:
        """GET /v1/mowers/<id>/stayOutZones - all defined stay-out zones."""
        raw = await self._request("GET", f"/v1/mowers/{mower_id}/stayOutZones")
        if not isinstance(raw, dict):
            return ()
        data = raw.get("data")
        if not isinstance(data, dict):
            return ()
        attrs = data.get("attributes")
        if not isinstance(attrs, dict):
            return ()
        zones = attrs.get("zones")
        if not isinstance(zones, list):
            return ()
        return tuple(StayOutZone.from_raw(z) for z in zones if isinstance(z, dict))

    async def set_stay_out_zone_enabled(
        self, mower_id: str, zone_id: str, *, enabled: bool
    ) -> None:
        """Enable or disable a stay-out zone (PATCH per OpenAPI spec)."""
        body = {
            "data": {
                "type": "stayOutZone",
                "id": zone_id,
                "attributes": {"enable": bool(enabled)},
            }
        }
        await self._request(
            "PATCH",
            f"/v1/mowers/{mower_id}/stayOutZones/{zone_id}",
            json_body=body,
        )

    # ------------------------------------------------------------------
    # work areas (detail endpoint + PATCH)
    # ------------------------------------------------------------------

    async def get_work_areas(self, mower_id: str) -> tuple[WorkArea, ...]:
        """GET /v1/mowers/<id>/workAreas - all work areas with detail."""
        raw = await self._request("GET", f"/v1/mowers/{mower_id}/workAreas")
        if not isinstance(raw, dict):
            return ()
        items = raw.get("data")
        if not isinstance(items, list):
            return ()
        result: list[WorkArea] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes")
            if isinstance(attrs, dict):
                result.append(WorkArea.from_raw(attrs))
        return tuple(result)

    async def set_work_area_cutting_height(
        self, mower_id: str, work_area_id: int, *, cutting_height_percent: int
    ) -> None:
        """Update a work area's cutting height (0-100 percent, not 1-9)."""
        if not 0 <= cutting_height_percent <= 100:
            raise ValueError("cutting_height_percent must be in 0..100")
        body = {
            "data": {
                "type": "workArea",
                "id": int(work_area_id),
                "attributes": {"cuttingHeight": int(cutting_height_percent)},
            }
        }
        await self._request(
            "PATCH",
            f"/v1/mowers/{mower_id}/workAreas/{work_area_id}",
            json_body=body,
        )

    async def set_work_area_enabled(
        self, mower_id: str, work_area_id: int, *, enabled: bool
    ) -> None:
        """Enable or disable a work area."""
        body = {
            "data": {
                "type": "workArea",
                "id": int(work_area_id),
                "attributes": {"enable": bool(enabled)},
            }
        }
        await self._request(
            "PATCH",
            f"/v1/mowers/{mower_id}/workAreas/{work_area_id}",
            json_body=body,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _action(
        self,
        mower_id: str,
        action: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {"data": {"type": action}}
        if attributes:
            body["data"]["attributes"] = attributes
        await self._request(
            "POST", f"/v1/mowers/{mower_id}/actions", json_body=body
        )

    async def _post_settings(
        self, mower_id: str, attributes: dict[str, Any]
    ) -> None:
        body = {"data": {"type": "settings", "attributes": attributes}}
        await self._request(
            "POST", f"/v1/mowers/{mower_id}/settings", json_body=body
        )

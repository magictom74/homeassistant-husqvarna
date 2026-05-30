"""State container for one Husqvarna account.

One config entry = one Husqvarna application credentials pair = one
WebSocket connection. The coordinator holds the live mower snapshots
(id -> :class:`Mower`) and updates them in place from the WebSocket
push stream. Initial REST snapshot is fetched once via
``async_config_entry_first_refresh``; afterwards there is no polling.

The cloud's auth has a quirk: it locks the ``client_id`` ('simultaneous
logins') when several parallel auth requests come in. The token cache
in :class:`HusqvarnaAuth` handles that for us as long as we **don't**
force a refresh on every reconnect - the WebSocket client follows the
same policy (only refresh on 4001/4003).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pyhusqvarna import (
    AutomowerClient,
    HusqvarnaAuth,
    HusqvarnaWebSocketClient,
    Mower,
    MowerMessage,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HusqvarnaCoordinator(DataUpdateCoordinator[dict[str, Mower]]):
    """Holds the live mower map for one Husqvarna account."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
        auth: HusqvarnaAuth,
        client: AutomowerClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=None,  # push-driven
        )
        self.entry = entry
        self.entry_id = entry.entry_id
        self.auth = auth
        self.client = client
        self._ws: HusqvarnaWebSocketClient | None = None
        self._ws_state: str = "stopped"
        self._last_event_at: datetime | None = None
        self._messages: dict[str, tuple[MowerMessage, ...]] = {}

    # ------------------------------------------------------------------
    # initial fetch
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Mower]:
        """Initial REST snapshot. Called once at setup."""
        _LOGGER.debug("[husqvarna.coordinator] fetching mower list")
        mowers = await self.client.list_mowers()
        snapshot = {m.id: m for m in mowers}
        _LOGGER.info(
            "[husqvarna.coordinator] %d mower(s) on the account", len(snapshot)
        )
        return snapshot

    # ------------------------------------------------------------------
    # WebSocket lifecycle (driven by __init__.async_setup_entry)
    # ------------------------------------------------------------------

    async def async_start_ws(self) -> None:
        if self._ws is not None and self._ws.is_running:
            return
        self._ws = HusqvarnaWebSocketClient(
            self.auth,
            on_frame=self._on_ws_frame,
            on_state_change=self._on_ws_state,
        )
        await self._ws.start()

    async def async_stop_ws(self) -> None:
        if self._ws is None:
            return
        await self._ws.stop()
        self._ws = None
        self._ws_state = "stopped"

    @property
    def ws_state(self) -> str:
        return self._ws_state

    @property
    def last_event_at(self) -> datetime | None:
        return self._last_event_at

    # ------------------------------------------------------------------
    # state inspection (used by entities)
    # ------------------------------------------------------------------

    def get_mower(self, mower_id: str) -> Mower | None:
        if self.data is None:
            return None
        return self.data.get(mower_id)

    def messages_for(self, mower_id: str) -> tuple[MowerMessage, ...]:
        return self._messages.get(mower_id, ())

    # ------------------------------------------------------------------
    # WebSocket push handler
    # ------------------------------------------------------------------

    async def _on_ws_frame(self, frame: dict[str, Any]) -> None:
        mower_id = frame.get("id")
        if not isinstance(mower_id, str) or mower_id not in (self.data or {}):
            _LOGGER.debug(
                "[husqvarna.coordinator] WS frame for unknown mower %r: %s",
                mower_id,
                frame.get("type"),
            )
            return
        current = self.data[mower_id]
        updated = current.with_delta(frame)
        # DataUpdateCoordinator.data is the dict; mutate then notify
        self.data[mower_id] = updated
        self._last_event_at = datetime.now(timezone.utc)
        self.async_update_listeners()

    async def _on_ws_state(self, state: str) -> None:
        self._ws_state = state
        # Push the state to entities so the connectivity-binary-sensor
        # updates instantly when the WS drops or reconnects.
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # explicit pull endpoints (messages, fresh inventory) for services
    # ------------------------------------------------------------------

    async def async_refresh_inventory(self) -> None:
        """Re-fetch the mower list from REST.

        Called from a service hook after the user has reconfigured the
        mower in the Husqvarna app and HA's coordinator doesn't know
        about it yet. NOT a polling loop.
        """
        mowers = await self.client.list_mowers()
        self.data = {m.id: m for m in mowers}
        self.async_update_listeners()

    async def async_refresh_messages(self, mower_id: str) -> tuple[MowerMessage, ...]:
        """Pull the mower-message history (alarm log) for one mower."""
        msgs = await self.client.get_messages(mower_id)
        self._messages[mower_id] = msgs
        self.async_update_listeners()
        return msgs

    # ------------------------------------------------------------------
    # diagnostics helper
    # ------------------------------------------------------------------

    def diagnostics(self) -> dict[str, Any]:
        return {
            "ws_state": self._ws_state,
            "last_event_at": (
                self._last_event_at.isoformat()
                if self._last_event_at is not None
                else None
            ),
            "mower_count": len(self.data) if self.data is not None else 0,
            "mower_ids": list((self.data or {}).keys()),
            "message_count_by_mower": {
                k: len(v) for k, v in self._messages.items()
            },
        }

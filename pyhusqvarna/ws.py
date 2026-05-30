"""Husqvarna cloud WebSocket client.

Single endpoint, single connection per app key, push-only:

    wss://ws.openapi.husqvarna.dev/v1

All three Husqvarna headers (``Authorization`` + ``X-Api-Key`` +
``Authorization-Provider``) are sent in the WebSocket handshake. This
is the failure mode behind most stuck third-party integrations - the
server returns 403 if any of the three is missing.

Reconnect policy:

* **1000** (normal closure) - we don't reconnect; the user closed it.
* **1001** ("going away") - server-initiated drop, fires roughly every
  two hours. Immediate reconnect, no token refresh.
* **1006** (abnormal closure) - usually a transient network drop or
  the ~24h cloud-side rotation. Exponential backoff, no token refresh.
* **4001 / 4003** - token rejected. Force-refresh the token, then
  reconnect.
* anything else - exponential backoff with the same no-refresh
  policy as 1006.

The connection is mutually exclusive: before each reconnect attempt
we close the previous one cleanly so the cloud doesn't reject the
new handshake with ``Already connected``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

from .auth import HusqvarnaAuth
from .exceptions import WebSocketError

_LOGGER = logging.getLogger(__name__)

WS_URL = "wss://ws.openapi.husqvarna.dev/v1"
DEFAULT_HEARTBEAT_SECONDS = 60.0
DEFAULT_RECEIVE_TIMEOUT = 180.0

# Close codes that mean "go refresh your token"
TOKEN_REFRESH_CLOSE_CODES = {4001, 4003}
# Close codes we should not reconnect after
INTENTIONAL_CLOSE_CODES = {1000}

# Exponential backoff schedule (seconds)
RECONNECT_BACKOFF = (1, 2, 5, 15, 30, 60, 120, 300)

FrameHandler = Callable[[dict[str, Any]], Awaitable[None]]
StateHandler = Callable[[str], Awaitable[None]]


class HusqvarnaWebSocketClient:
    """Long-lived push client for the Husqvarna cloud WebSocket."""

    def __init__(
        self,
        auth: HusqvarnaAuth,
        *,
        on_frame: FrameHandler,
        on_state_change: StateHandler | None = None,
        heartbeat: float = DEFAULT_HEARTBEAT_SECONDS,
        receive_timeout: float = DEFAULT_RECEIVE_TIMEOUT,
    ) -> None:
        self._auth = auth
        self._on_frame = on_frame
        self._on_state_change = on_state_change
        self._heartbeat = heartbeat
        self._receive_timeout = receive_timeout
        self._task: asyncio.Task[None] | None = None
        self._session: ClientSession | None = None
        self._ws: ClientWebSocketResponse | None = None
        self._stopped = asyncio.Event()
        self._state: str = "stopped"

    @property
    def state(self) -> str:
        """Current connection state: ``stopped`` / ``connecting`` / ``connected`` / ``backoff``."""
        return self._state

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopped.clear()
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run(), name="husqvarna-ws")

    async def stop(self) -> None:
        self._stopped.set()
        await self._close_ws()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._session is not None:
            await self._session.close()
            self._session = None
        await self._set_state("stopped")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _set_state(self, new_state: str) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        _LOGGER.debug("[husqvarna.ws] state=%s", new_state)
        if self._on_state_change is not None:
            try:
                await self._on_state_change(new_state)
            except Exception:
                _LOGGER.exception("[husqvarna.ws] on_state_change handler raised")

    async def _close_ws(self) -> None:
        if self._ws is not None and not self._ws.closed:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._ws = None

    async def _run(self) -> None:
        backoff_index = 0
        while not self._stopped.is_set():
            try:
                await self._set_state("connecting")
                await self._connect_and_consume()
                backoff_index = 0  # successful run resets backoff
            except _TokenRefreshNeededError:
                _LOGGER.info("[husqvarna.ws] Server signalled token-refresh; refreshing")
                with contextlib.suppress(Exception):
                    await self._auth.get_token(force_refresh=True)
                # No backoff - reconnect immediately with the new token
                continue
            except _ImmediateReconnectError:
                # 1001 - server going away
                continue
            except _ReconnectWithBackoffError as exc:
                _LOGGER.info("[husqvarna.ws] reconnecting after %s", exc)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("[husqvarna.ws] unexpected error in run loop")

            if self._stopped.is_set():
                break

            delay = RECONNECT_BACKOFF[min(backoff_index, len(RECONNECT_BACKOFF) - 1)]
            backoff_index += 1
            await self._set_state("backoff")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)

    async def _connect_and_consume(self) -> None:
        if self._session is None:
            raise WebSocketError("Session is not initialised")
        await self._close_ws()  # belt and braces - one connection only

        token = await self._auth.get_token()
        headers = self._auth.auth_headers(token)

        _LOGGER.debug("[husqvarna.ws] Connecting to %s", WS_URL)
        try:
            ws = await self._session.ws_connect(
                WS_URL,
                headers=headers,
                heartbeat=self._heartbeat,
                receive_timeout=self._receive_timeout,
                autoclose=True,
                autoping=True,
            )
        except aiohttp.WSServerHandshakeError as exc:
            if exc.status == 403:
                raise WebSocketError(
                    "WebSocket handshake returned 403 - missing or wrong "
                    "auth headers. All three of Authorization, X-Api-Key "
                    "and Authorization-Provider are required."
                ) from exc
            if exc.status == 401:
                raise _TokenRefreshNeededError("401 on WS handshake") from exc
            raise WebSocketError(
                f"WebSocket handshake failed: {exc.status} {exc.message}"
            ) from exc
        except aiohttp.ClientError as exc:
            raise _ReconnectWithBackoffError(f"connect error: {exc}") from exc

        self._ws = ws
        await self._set_state("connected")

        try:
            async for msg in ws:
                if msg.type is WSMsgType.TEXT:
                    await self._handle_text(msg.data)
                elif msg.type is WSMsgType.BINARY:
                    # Husqvarna sends text-only; binary is unexpected
                    _LOGGER.debug("[husqvarna.ws] unexpected binary frame")
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSE, WSMsgType.CLOSING):
                    break
                elif msg.type is WSMsgType.ERROR:
                    raise _ReconnectWithBackoffError(f"transport error: {ws.exception()!r}")
        finally:
            close_code = ws.close_code
            await self._close_ws()
            self._classify_close(close_code)

    async def _handle_text(self, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except ValueError:
            _LOGGER.warning("[husqvarna.ws] non-JSON frame: %r", raw[:200])
            return
        if not isinstance(frame, dict):
            _LOGGER.warning("[husqvarna.ws] non-object frame: %r", frame)
            return
        try:
            await self._on_frame(frame)
        except Exception:
            _LOGGER.exception("[husqvarna.ws] on_frame handler raised")

    def _classify_close(self, code: int | None) -> None:
        """Translate a close code into one of the loop's flow exceptions."""
        if code is None:
            raise _ReconnectWithBackoffError("close without code")
        if code in INTENTIONAL_CLOSE_CODES:
            # We don't reconnect; let the loop see _stopped.
            self._stopped.set()
            return
        if code in TOKEN_REFRESH_CLOSE_CODES:
            raise _TokenRefreshNeededError(f"close code {code}")
        if code == 1001:
            raise _ImmediateReconnectError("server going away (1001)")
        raise _ReconnectWithBackoffError(f"close code {code}")


class _TokenRefreshNeededError(Exception):
    pass


class _ImmediateReconnectError(Exception):
    pass


class _ReconnectWithBackoffError(Exception):
    pass

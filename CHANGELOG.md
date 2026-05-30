# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Alarm history** via `AutomowerClient.get_messages()` -
  returns up to 50 `MowerMessage` entries with severity
  (`FATAL` / `ERROR` / `WARNING` / `INFO` / `DEBUG` / `SW` /
  `UNKNOWN`), Husqvarna fault code, timestamp and GPS position of
  the fault. Live-verified against a real 305E NERA (returned 41
  historical messages).
- **`StartInWorkArea`** action via
  `AutomowerClient.start_in_work_area(mower_id, work_area_id=..., duration_minutes=...)`.
- **Statistics reset** via
  `AutomowerClient.reset_cutting_blade_usage_time()`.
- **Stay-out-zone toggle** via `get_stay_out_zones()` and
  `set_stay_out_zone_enabled()` (PATCH).
- **Detailed work-area endpoints** via `get_work_areas()` and
  `set_work_area_cutting_height()` / `set_work_area_enabled()`.
  `WorkArea` now exposes the extended fields
  (`use_global_cutting_height`, `progress`, `last_time_completed`,
  `last_time_abandoned`).
- **`Planner.external_reason`** field for parking-source tracking
  (3000-3999 = Home Assistant, 200000-299999 = Developer Portal apps).
- **Three new `RestrictedReason` values** from the OpenAPI spec:
  `ALL_WORK_AREAS_COMPLETED`, `EXTERNAL`, `WORK_AREA_ABANDONED`.
- **`MessageSeverity`** enum for the alarm-history endpoint.
- `docs/openapi-automower-connect-v1.0.yaml` - the official spec
  (path-level) at the time of v0.1.

### Changed

- **WebSocket `with_delta`** now handles the `position-event-v2`
  frame shape (singular `attributes.position`) correctly: the new
  point is prepended to the in-memory history, capped at 50.
  Previously the WS position pushes were silently dropped because
  the merger only looked for `positions` (array).
- **WS server-hello frame** (`{ready, connectionId}`) is now logged
  at DEBUG instead of being passed to user frame handlers.
- `docs/HUSQVARNA_API_NOTES.md` substantially expanded with the
  Connectivity-API subscription requirement, the verified WS frame
  shapes, and the full Husqvarna enum catalogue with German prose.

### Fixed

- **`confirm_error` was hitting the wrong endpoint.** It used to
  POST to `/v1/mowers/<id>/actions` with `type=ConfirmError`, but the
  OpenAPI spec defines a dedicated `POST /v1/mowers/<id>/errors/confirm`
  endpoint and `ConfirmError` is not in the action enum at all. Now
  uses the correct endpoint.
- **`set_cutting_height` / `set_headlight_mode` used PATCH** for
  `/v1/mowers/<id>/settings`. The spec says POST. Now uses POST.

## [0.1.0] - 2026-05-30

### Added

- Initial release of `pyhusqvarna`, async Python library for the
  Husqvarna cloud APIs. Today covers the Automower Connect API
  end-to-end. Repo layout is namespaced
  (`pyhusqvarna.api.*`, `pyhusqvarna.models.*`) so further Husqvarna
  Connect product families can slot in later.
- **OAuth2 client-credentials** auth (`HusqvarnaAuth`) with 24-hour
  token cache and a 5-minute safety margin so a near-edge token
  isn't reused mid-handshake. Surfaces the cloud's
  ``simultaneous.logins`` lock as a typed `SimultaneousLoginsError`
  so callers can avoid the reconnect loop that triggers it.
- **All three required headers** (`Authorization`, `X-Api-Key`,
  `Authorization-Provider`) consistently applied to REST and to the
  WebSocket handshake. Missing any one of them yields 403; this
  was the bug behind the stuck reconnect loop in the existing
  `iobroker.husqvarna-automower` adapter.
- **REST client** (`AutomowerClient`): `list_mowers`, `get_mower`,
  the full remote-control surface (`park_until_next_schedule`,
  `park_until_further_notice`, `park_for`, `resume_schedule`,
  `pause`, `start_for`), `confirm_error`, plus settings PATCH
  (`set_cutting_height`, `set_headlight_mode`). 401 triggers a
  one-shot token refresh and retry.
- **WebSocket client** (`HusqvarnaWebSocketClient`) with reconnect
  policy: immediate retry on 1001 (server going-away), exponential
  backoff on 1006, and force-refresh-then-reconnect only on
  4001/4003 token-rejections. Single connection per app key,
  enforced by closing any previous WS before each reconnect.
- **Frozen-dataclass domain model** for the mower and all sub-trees
  (`Battery`, `Capabilities`, `MowerError`, `Planner`, `Metadata`,
  `Calendar`, `Settings`, `Statistics`, `Position`, `WorkArea`,
  `StayOutZone`). Convenience properties (`is_online`, `is_charging`,
  `is_mowing`, `has_error`, `error_confirmable`, `latest_position`)
  ride on top.
- **WebSocket delta merger** (`Mower.with_delta`) that applies the
  partial sub-trees the cloud pushes onto an existing snapshot and
  returns a new frozen copy.
- **PEP 561 `py.typed`** marker. Passes `mypy --strict`.

[Unreleased]: https://github.com/magictom74/homeassistant-husqvarna/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/magictom74/homeassistant-husqvarna/releases/tag/v0.1.0

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

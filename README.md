# homeassistant-husqvarna

Home Assistant custom integration for the Husqvarna cloud ecosystem,
plus the async Python library `pyhusqvarna` that powers it. The
library is HA-agnostic and usable from any Python codebase.

Today the integration covers the **Automower Connect API** with full
remote control, error confirmation, alarms and detailed state
reporting. The architecture is deliberately built so further Husqvarna
Connect product families can slot in later without a rewrite.

**Status:** Alpha. The public API may still change before 1.0.

## Why this exists

The HA-Core `husqvarna_automower` integration uses the OAuth
authorization-code flow, which assumes interactive Browser-Redirect.
For a headless smart-home setup that's already running on the
**client-credentials** flow (App Key + Secret from the
[Husqvarna Developer Portal](https://developer.husqvarnagroup.cloud/))
that's a step backwards. This project keeps client-credentials, sets
**all three** required headers (`Authorization` + `X-Api-Key` +
`Authorization-Provider`) on every request including the WebSocket
handshake, and stays under a single connection per app key so the
cloud's `simultaneous.logins` lock never fires.

## Features (pyhusqvarna, v0.1)

- **OAuth2 client-credentials** with a 24-hour token cache. No
  re-login on every reconnect; that's what gets the cloud to lock
  you out.
- **REST client** for the Automower endpoints:
  `list_mowers`, `get_mower`, action POSTs (Park / Resume / Pause /
  Start / ConfirmError), settings PATCH, stay-out-zones, work-areas.
- **WebSocket client** (`wss://ws.openapi.husqvarna.dev/v1`) with
  reconnect-on-close and *no* token refresh on the reconnect path -
  refresh only on 4001/4003 or after expiry.
- **Frozen-dataclass domain model** for `Mower` and friends (battery,
  capabilities, planner, calendar, work areas, positions, errors).
- **Strict typing** - passes `mypy --strict`. PEP 561 `py.typed`
  marker so downstream consumers get full type inference.

## Features (Home Assistant integration, v0.1)

Drop `custom_components/husqvarna/` into your HA config directory (or
install via HACS once published), then add the integration from
*Settings -> Integrations* and paste the Application Key + Application
Secret from your Husqvarna Developer-Portal app. Per mower you get:

- **`lawn_mower`** entity - HA's built-in mower platform with
  DOCK / PAUSE / START_MOWING mapped onto park-until-next-schedule /
  pause / resume-schedule.
- **Sensors** for battery, activity, mode, state, restricted-reason,
  error code, next start (as a timestamp), and lifetime statistics
  (cutting time, distance, charging cycles, collisions).
- **Alarm history sensor** showing the count of cached mower
  messages plus the 10 most recent as an attribute - each with
  severity, fault code, timestamp and GPS position of the fault.
- **Binary sensors** for cloud-connected, charging and problem state.
- **Device tracker** with the latest GPS point (pushed live via
  WebSocket).
- **Buttons** for park / pause / resume, confirm-error (only when an
  error is currently confirmable), and refresh-messages.
- **Number** for the global cutting height (1-9).
- **Services** for park-for-duration, start-for-duration,
  start-in-work-area, reset-blade-usage-time and refresh-messages.

Coexists with the official HA-Core `husqvarna_automower` integration
- this one uses the *client-credentials* OAuth flow (App Key + Secret),
the Core one uses the *authorization-code* flow. Pick whichever
matches how you registered your developer-portal application.

## Extensibility

The library namespaces every product family under `pyhusqvarna.api.*`
and `pyhusqvarna.models.*`:

- `pyhusqvarna.api.automower` - the Automower Connect API surface.
- `pyhusqvarna.models.automower` - mower-specific dataclasses.

Adding another Husqvarna Connect product (anything that shares the
Group OAuth2) means adding a new sibling module under those
namespaces and a new HA platform layer over it. The auth / WebSocket
plumbing is shared.

## Installing

```bash
pip install pyhusqvarna           # not yet on PyPI - use editable install
```

For local development:

```bash
git clone git@github.com:magictom74/homeassistant-husqvarna.git
cd homeassistant-husqvarna
pip install -e ".[dev]"
```

## Quickstart

```python
import asyncio
from pyhusqvarna import HusqvarnaAuth
from pyhusqvarna.api.automower import AutomowerClient

async def main() -> None:
    auth = HusqvarnaAuth(api_key="<your-app-key>",
                         api_secret="<your-app-secret>")
    async with AutomowerClient(auth) as client:
        mowers = await client.list_mowers()
        for m in mowers:
            print(f"{m.name} ({m.model}) - {m.activity}, battery {m.battery_percent}%")

asyncio.run(main())
```

## Getting credentials

1. Go to the [Husqvarna Developer Portal](https://developer.husqvarnagroup.cloud/).
2. Create an Application and enable the **Authentication API** and
   **Automower Connect API** for it.
3. Copy the **Application Key** and **Application Secret** - those
   are the `api_key` / `api_secret` the library expects.
4. The library uses the OAuth2 *client-credentials* flow, so there's
   no interactive consent step.

## Why no polling?

Husqvarna publishes a WebSocket endpoint that pushes every state
delta in real time. Hammering the REST API with poll cycles instead
- as some older integrations do - eats into the 10 000 req/month
rate limit and produces stale state in between polls. This library
has one rule: **no polling**. Initial REST snapshot once, then
WebSocket push.

## License

MIT - see [LICENSE](LICENSE).

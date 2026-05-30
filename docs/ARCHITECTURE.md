# Architektur: HA-Integration Husqvarna Automower

## Grundprinzip

```
┌─────────────────────────────────────────────────────────────┐
│            Husqvarna Cloud (api.amc.husqvarna.dev)           │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  Auth-API       │  │  Connect-API    │  │  WebSocket   │ │
│  │  /v1/oauth2/    │  │  /v1/mowers/... │  │  ws.openapi  │ │
│  │  token          │  │                 │  │  .husqvarna  │ │
│  │                 │  │  - Read mowers  │  │  .dev/v1     │ │
│  │  client_cred.   │  │  - POST actions │  │              │ │
│  │  → access_token │  │  - PATCH settings│ │  Push events │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└────┬──────────────────────┬───────────────────────┬─────────┘
     │ POST                 │ GET/POST/PATCH        │ WebSocket
     │ Token-Refresh        │ Commands              │ Live-Push
     │ (max 1x/24h)         │ (on-demand)           │ (persistent)
     ↓                      ↓                       ↑
┌─────────────────────────────────────────────────────────────┐
│              pyhusqvarna (Library)                 │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  Auth       │  │  REST-Client │  │  WS-Client          │ │
│  │             │  │              │  │                     │ │
│  │  - Token-   │  │  - Headers:  │  │  - Headers:         │ │
│  │    Cache    │  │    Bearer +  │  │    Bearer +         │ │
│  │  - Refresh- │  │    X-Api-Key │  │    X-Api-Key +      │ │
│  │    Lock     │  │    + Auth-   │  │    Auth-Provider    │ │
│  │  - 401-Auto │  │    Provider  │  │  - Ping/Pong        │ │
│  │             │  │              │  │  - Reconnect-Strat  │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ Python async API
                           │ + Event-Callbacks
                           ↓
┌─────────────────────────────────────────────────────────────┐
│   custom_components/husqvarna (HA Integration)     │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  Setup      │  │  Entities    │  │  Services           │ │
│  │             │  │              │  │                     │ │
│  │  - __init__ │  │  - LawnMower │  │  - park             │ │
│  │  - config_  │  │  - Sensors   │  │  - park_for         │ │
│  │    flow     │  │  - Binary    │  │  - resume_schedule  │ │
│  │    (App-Key │  │    Sensors   │  │  - start            │ │
│  │     + Sec.) │  │  - Device-   │  │  - pause            │ │
│  │  - coord-   │  │    Tracker   │  │  - confirm_error    │ │
│  │    inator   │  │  - Number    │  │  - set_schedule     │ │
│  │             │  │  - Select    │  │                     │ │
│  │             │  │  - Button    │  │                     │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ HA Entity-API / Service-Registry
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              Home Assistant Core / Frontend                  │
└─────────────────────────────────────────────────────────────┘
```

## Schichten-Trennung

### Library `pyhusqvarna/`

Reines API-Wrapping, **null HA-Abhaengigkeit**:
- `auth.py` - Token-Lifecycle (Cache, Refresh-Lock, 401-Retry)
- `client.py` - REST-Operations (httpx)
- `ws.py` - WebSocket-Lifecycle (Connect, Ping/Pong, Reconnect-Strategy, Event-Dispatch)
- `models.py` - Dataclasses: Mower, Battery, Calendar, Position, WorkArea, Settings, Statistics
- `exceptions.py` - HusqvarnaError, HusqvarnaAuthError, HusqvarnaRateLimitError, HusqvarnaWebSocketError

Library ist **standalone testbar** und kann von anderen Python-Projekten benutzt werden.

### Integration `custom_components/husqvarna/`

HA-spezifischer Glue-Code:
- `__init__.py` - Setup-Logik, Coordinator, WebSocket-Task
- `config_flow.py` - "Add Integration"-Dialog: App-Key + Secret eingeben, Verbindungs-Test
- `coordinator.py` - Combined Push (WS) + Refresh-Coordinator
- `manifest.json` - Metadaten, Dependencies (pyhusqvarna)
- `const.py` - DOMAIN, Event-Names, Service-Names
- `lawn_mower.py` - Primaere Entity (HA lawn_mower-Platform)
- `sensor.py`, `binary_sensor.py`, `device_tracker.py`, `number.py`, `select.py`, `button.py`
- `services.yaml` - Service-Definitionen
- `strings.json` + `translations/`

## Event-Flow im Detail

### Befehl (HA → Husqvarna)

```
User klickt "Park" in HA
    → button.async_press()
    → Integration → coordinator.async_park(mower_id)
    → pyhusqvarna.Client.send_action(mower_id, "ParkUntilNextSchedule")
    → HTTP POST /v1/mowers/<id>/actions
       Headers: Authorization, X-Api-Key, Authorization-Provider
       Body: {"data": {"type": "ParkUntilNextSchedule"}}
    → Husqvarna Cloud schaltet → Mower wird parken
    → HTTP 202 Accepted (asynchron)
    → coordinator wartet auf naechstes WS-Event → state-update folgt automatisch
```

Latenz: 200ms - 2s (Cloud-Roundtrip).

### Aenderung am Mower (Husqvarna → HA)

```
Mower wechselt Activity (z.B. CHARGING → LEAVING)
    → Husqvarna Cloud erkennt via Connect-Modul
    → Cloud pushed JSON-Frame ueber unsere WebSocket-Connection
    → pyhusqvarna.ws receives frame
    → Event-Dispatcher → coordinator.async_handle_event(payload)
    → Coordinator merged Delta in Mower-Model
    → HA Entities feuern state_changed → Frontend updated
```

Latenz: typ. < 1s (laut Husqvarna), bestaetigt durch Discovery-Run.

## Authentication-Flow

```
1. (Einmalig im Husqvarna Developer Portal) User legt App "HomeAssistant" an
   → erhaelt application_key (UUID) + application_secret (UUID)
   → API "Authentication API" + "Automower Connect API" verbinden

2. (Bei HA-Integration-Setup) User gibt Key + Secret im Config-Flow ein

3. (Bei jedem Token-Bedarf) Integration ruft:
   POST https://api.authentication.husqvarnagroup.dev/v1/oauth2/token
   Body: grant_type=client_credentials&client_id=<KEY>&client_secret=<SECRET>
   → erhaelt access_token (24h gueltig)

4. Token wird im Memory gecached, NUR bei:
   - Expiry (vor 24h-Ablauf, mit 5min Safety-Buffer)
   - 401 Unauthorized von API
   neu geholt.

5. (Bei jedem API-Call + WebSocket-Connect) drei Header senden:
   - Authorization: Bearer <ACCESS_TOKEN>
   - X-Api-Key: <APPLICATION_KEY>
   - Authorization-Provider: husqvarna
```

**KRITISCH:** NIEMALS Token-Refresh pro Reconnect-Versuch ausloesen. Das war der Bug im ioBroker-Adapter und triggert Husqvarnas `simultaneous.logins`-Sperre.

## WebSocket-Lifecycle

### Verbindungsaufbau

```python
ws = await session.ws_connect(
    "wss://ws.openapi.husqvarna.dev/v1",
    headers={
        "Authorization": f"Bearer {token}",
        "X-Api-Key": application_key,
        "Authorization-Provider": "husqvarna",
    },
    heartbeat=60,  # aiohttp-internes Ping
)
```

### Reconnect-Strategie

| Close-Code | Bedeutung | Reaktion |
|------------|-----------|----------|
| 1000 | Normal closure (von uns ausgeloest) | KEIN Reconnect (Shutdown) |
| 1001 | Going away (Server ~alle 2h) | Sofort Reconnect mit BESTEHENDEM Token |
| 1006 | Abnormal closure (~alle 24h, Token-Expiry assoziiert) | Token refreshen FALLS abgelaufen, dann Reconnect |
| 1012 | Service Restart | Exponential-Backoff (1s → 60s), Reconnect |
| 4001/4003 | Auth-Errors | Token zwingend refreshen, dann Reconnect |
| Connection Error | TCP-Drop | Exponential-Backoff (1s, 2s, 5s, 10s, 30s, 60s max) |

**Wichtig:** Kein blindes `getAccessToken()` bei jedem Close. Token-Status pruefen.

### Ping/Pong

Husqvarna scheint kein Pong zu senden bei Ping (zu verifizieren in Discovery). Stattdessen: aiohttp-internes heartbeat (~60s) + Server-Disconnect-Detection ueber TCP-Timeout.

## Reconnect / Resilience

| Szenario | Strategy |
|----------|----------|
| Mower offline (connectivity_issue) | Entity bleibt "available=True", state spiegelt letzten bekannten Zustand, `binary_sensor.connected=off` |
| WS-Disconnect Code 1001 | Sofort reconnect mit altem Token |
| WS-Disconnect Code 1006 | Token-Pruefung → ggf. Refresh → Reconnect mit Backoff |
| API 429 Rate-Limit | Backoff laut `Retry-After`-Header (Husqvarna limitiert auf 10k req/Monat) |
| API 500/503 | Retry mit Backoff (max 3x) |
| Token-Refresh-Fehler 400 (simultaneous.logins) | Pause 60s, dann Re-Auth (passiert wenn Parallel-Adapter laeuft) |
| HA-Reboot | Re-Auth + Initial-Fetch + WS-Connect |

## Datenfluss bei Setup

```
HA Start
  → ConfigEntry geladen (App-Key + Secret aus Storage)
  → __init__.async_setup_entry()
  → pyhusqvarna.Client erstellt
  → Initial: Token holen + Mower-Liste fetchen
  → Coordinator gefuellt
  → Device-Registry: pro Mower ein Device (Hersteller=Husqvarna, Model + Serial aus der API-Response)
  → Platform-Forwards: lawn_mower, sensor, binary_sensor, device_tracker, number, select, button
  → WS-Task gestartet als Background-Task
  → Setup-Complete-Signal
```

## Rate-Limit-Beobachtung

Husqvarna Connect-API: **10.000 Requests/Monat pro App**. Das ist ca. 1 Request alle 4.3 Minuten.

→ Polling waere selbst mit 5min-Intervall am Limit. WebSocket ist Pflicht.

Statistics-Endpoint manuell abfragen (z.B. 1x/Stunde fuer cuttingTime etc.) → ~720 Requests/Monat ist OK.

## Tests-Strategie

- **Unit-Tests** (pyhusqvarna): Mock-HTTPClient, isolierte Modell-Tests
- **Integration-Tests** (pyhusqvarna): VCR-Recordings von echten API-Responses
- **WS-Tests:** Local Mock-WS-Server der die Cloud nachstellt (Reconnect-Szenarien testen)
- **HA-Integration-Tests** (custom_components): pytest-homeassistant-custom-component
- **End-to-End:** gegen echte Mower-Hardware in Test-Phasen

## Distribution

- **GitHub-Repo:** `homeassistant-husqvarna` (Mono-Repo, magictom74/)
- **HACS:** `hacs.json` im Root, integration-Type
- **PyPI:** `pyhusqvarna` separat (optional)
- **HA Brand:** falls Submission an HA Core - aber moeglicherweise Konflikt mit bestehender Core-Integration

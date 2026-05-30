# Husqvarna Connect API Notes

Sammlung der relevanten Endpoints + Eigenheiten. Basiert auf:
- Live-Diagnose `iobroker.husqvarna-automower` v0.5.0 auf dolphin (2026-05-26)
- Husqvarna Developer Portal Docs (https://developer.husqvarnagroup.cloud/)
- Code-Analyse `aioautomower` (HA-Core-Library)
- Code-Analyse `iobroker.husqvarna-automower`

## Connection-Basics

- **Protokoll:** HTTPS (REST) + WSS (WebSocket)
- **Host REST:** `api.amc.husqvarna.dev` (Connect-API) + `api.authentication.husqvarnagroup.dev` (Auth)
- **Host WS:** `ws.openapi.husqvarna.dev`
- **Content-Type:** JSON in/out

## Pflicht-Headers (ALLE drei, ueberall - auch im WebSocket!)

```
Authorization: Bearer <ACCESS_TOKEN>
X-Api-Key: <APPLICATION_KEY>
Authorization-Provider: husqvarna
```

**Bug-Trigger:** ioBroker-Adapter v0.5.0 sendet im WebSocket-Handshake NUR `Authorization` → Server antwortet `403 Forbidden`. Siehe Diagnose unten.

## Authentication

### Token holen (client_credentials)

```
POST https://api.authentication.husqvarnagroup.dev/v1/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=<APP_KEY>&client_secret=<APP_SECRET>
```

**Response 200:**
```json
{
  "access_token": "eyJhbGc...",
  "scope": "iam:read",
  "expires_in": 86399,
  "provider": "husqvarna",
  "user_id": "d87ce4f5-...",
  "token_type": "Bearer",
  "refresh_token": null
}
```

- Token gueltig: 24h (86400s)
- `refresh_token: null` bei client_credentials - jeder Refresh = neuer Login

### Token loeschen

```
DELETE https://api.authentication.husqvarnagroup.dev/v1/token/<ACCESS_TOKEN>
Headers: X-Api-Key, Authorization-Provider
```

Wird im ioBroker-Adapter auf `onUnload` gerufen - aber liefert oft `500 AUTHORIZER_CONFIGURATION_ERROR`. Praktisch nicht zuverlaessig nutzbar, daher: einfach Token ausgehen lassen.

### "Simultaneous Logins" Sperre

Wenn parallel mehrere Auth-Requests vom selben `client_id` kommen (z.B. ioBroker-Adapter mit Reconnect-Loop), antwortet die Auth-API:

```
HTTP 400
{
  "error": "invalid_request",
  "error_description": "Simultaneous logins detected for client[id=...], user[id=..., email=...]",
  "error_code": "simultaneous.logins"
}
```

→ **Strategie:** Token aggressive cachen (24h - 5min Safety-Margin), kein Re-Auth bei jedem Reconnect, max 1 Auth-Request pro Stunde.

## REST Endpoints

### Mower-Liste

```
GET https://api.amc.husqvarna.dev/v1/mowers
Headers: Authorization, X-Api-Key, Authorization-Provider
```

**Response 200 (anonymisiertes Beispiel eines 305E NERA mit GPS+3G):**
```json
{
  "data": [{
    "type": "mower",
    "id": "<MOWER_UUID>",
    "attributes": {
      "system": {
        "name": "<MOWER_NAME>",
        "model": "Husqvarna Automower® 305E NERA",
        "serialNumber": 0
      },
      "battery": {
        "batteryPercent": 100,
        "remainingChargingTime": 0
      },
      "capabilities": {
        "headlights": false,
        "workAreas": true,
        "position": true,
        "canConfirmError": true,
        "stayOutZones": true
      },
      "mower": {
        "mode": "MAIN_AREA",
        "activity": "PARKED_IN_CS",
        "inactiveReason": "NONE",
        "state": "RESTRICTED",
        "workAreaId": 0,
        "errorCode": 0,
        "errorCodeTimestamp": 0,
        "isErrorConfirmable": false
      },
      "calendar": {
        "tasks": [
          {"start": 570, "duration": 150, "monday": true, ..., "workAreaId": 0},
          {"start": 795, "duration": 285, "monday": true, ..., "workAreaId": 0}
        ]
      },
      "planner": {
        "nextStartTimestamp": 1779874200000,
        "override": {"action": "FORCE_PARK"},
        "restrictedReason": "PARK_OVERRIDE"
      },
      "metadata": {
        "connected": true,
        "statusTimestamp": 1779825307733
      },
      "workAreas": [{"workAreaId": 0, "name": "", "type": "RANDOM", "cuttingHeight": 100, "enabled": true, ...}],
      "positions": [{"latitude": 47.30..., "longitude": 8.44...}, ...],
      "settings": {
        "cuttingHeight": 8,
        "headlight": {"mode": null}
      },
      "statistics": {
        "cuttingBladeUsageTime": 516863,
        "downTime": 2172729,
        "numberOfChargingCycles": 180,
        "numberOfCollisions": 6191,
        "totalChargingTime": 335905,
        "totalCuttingTime": 516863,
        "totalDriveDistance": 246110,
        "totalRunningTime": 585975,
        "totalSearchingTime": 56566,
        "upTime": 4720245
      }
    }
  }]
}
```

### Aktion senden

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/actions
Content-Type: application/vnd.api+json

{"data": {"type": "<ACTION>", "attributes": {<OPTIONAL>}}}
```

**Action-Typen:**

| Action | Body | Wirkung |
|--------|------|---------|
| `ResumeSchedule` | `{}` | Schedule wieder aktiv |
| `Pause` | `{}` | Sofort pausieren |
| `ParkUntilNextSchedule` | `{}` | Bis zur naechsten Schedule parken |
| `ParkUntilFurtherNotice` | `{}` | Dauerhaft parken bis explizit resumed |
| `Park` | `{"attributes": {"duration": <minutes>}}` | Fuer X Minuten parken |
| `Start` | `{"attributes": {"duration": <minutes>}}` | Sofort X Minuten ausserhalb Schedule starten |
| `ConfirmError` | `{}` | Fehler bestaetigen (nur wenn `isErrorConfirmable: true`) |

**Response 202 Accepted** - asynchrone Ausfuehrung, State-Aenderung via WebSocket abwarten.

### Settings aendern

```
PATCH https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/settings
Content-Type: application/vnd.api+json

{"data": {"type": "settings", "attributes": {"cuttingHeight": 5}}}
```

Felder: `cuttingHeight` (1-9), `headlight.mode` (`ALWAYS_ON`, `ALWAYS_OFF`, `EVENING_ONLY`, `EVENING_AND_NIGHT`).

### Schedule (Calendar) aendern

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/calendar/tasks
{"data": {"type": "calendar", "attributes": {"tasks": [...]}}}
```

Schreibt komplette Task-Liste neu (kein partielles Update).

### Stay-Out-Zones

```
GET /v1/mowers/<id>/stayOutZones
PATCH /v1/mowers/<id>/stayOutZones/<zoneId>  (enable/disable)
```

### Work-Areas

```
GET /v1/mowers/<id>/workAreas
PATCH /v1/mowers/<id>/workAreas/<workAreaId>  (cuttingHeight, enabled)
```

## WebSocket

### Endpoint

```
wss://ws.openapi.husqvarna.dev/v1
Headers (im Handshake):
  Authorization: Bearer <TOKEN>
  X-Api-Key: <APP_KEY>
  Authorization-Provider: husqvarna
```

### Event-Frames

Server sendet JSON-Frames vom Format:

```json
{
  "id": "<MOWER_ID>",
  "type": "<EVENT_TYPE>",
  "attributes": {
    "<changed_field>": <new_value>
  }
}
```

Beispiel-Event-Felder die im ioBroker-Code referenziert sind (zu verifizieren in Discovery):
- `battery` → `batteryPercent`, `remainingChargingTime`
- `mower` → `mode`, `activity`, `state`, `errorCode`, `errorCodeTimestamp`, `isErrorConfirmable`
- `cuttingHeight`
- `headlight` → `mode`
- `calendar` → `tasks[]`
- `positions[]` → `latitude`, `longitude`
- `planner` → `nextStartTimestamp`, `override`, `restrictedReason`
- `metadata` → `connected`, `statusTimestamp`

WebSocket sendet i.d.R. **Delta** (nur geaenderte Felder), nicht das komplette Mower-Objekt.

### Close-Codes (aus iobroker-Adapter-Code dokumentiert)

| Code | Bedeutung | Frequenz |
|------|-----------|----------|
| 1000 | Normal closure | nur bei expliziter Trennung |
| 1001 | Going away | ~alle 2h (servergewollt) |
| 1006 | Abnormal closure | ~alle 24h (Token-bezogen) |
| 1012 | Service restart | seltene Server-Restarts |
| 4001/4003 | Auth-Errors | Token tot oder revoked |

### Ping/Pong

Im ioBroker-Code: Client sendet alle 9.5min `ws.ping('ping')`. Husqvarna-Server scheint NICHT mit `pong` zu antworten (`[wss.on - pong]` Log-Eintrag in 6 Adapter-Runs nie gesehen). aiohttp internes `heartbeat` waere die robustere Loesung.

## Rate-Limits

- **REST:** 10.000 Requests/Monat pro App-Key (= ~14 Req/Stunde)
- **WebSocket:** keine offiziellen Limits, aber EINE Connection pro Token
- **Auth:** keine harten Limits, aber `simultaneous.logins` triggern wenn zu viele parallele Token-Refreshes

## Diagnose iobroker.husqvarna-automower v0.5.0 (2026-05-26)

### Bug 1: WebSocket 403 Forbidden

**Code (`main.js:1595`):**
```javascript
this.wss = new WebSocket('wss://ws.openapi.husqvarna.dev/v1', {
    headers: { Authorization: `Bearer ${this.access_token}` },  // FEHLT: X-Api-Key + Authorization-Provider
});
```

**Effekt:** WebSocket-Handshake schlaegt fehl mit:
```
[wss.on - error]: Error: Unexpected server response: 403
[wss.on - close]: readyState: 3; data: 1006; reason: 
```

→ Adapter erhaelt NIE WebSocket-Events. State-Updates kommen ausschliesslich aus dem initialen `GET /v1/mowers` beim Start.

### Bug 2: Reconnect-Loop triggert simultaneous.logins

**Code (`main.js:1830-1845`, `wss.on('close')` Handler):**
```javascript
} else if (data === 1006) {
    await this.getAccessToken();  // Token neu holen
    await this.autoRestart();      // 5s Pause → connectToWS()
}
```

Da der WebSocket SOFORT wieder mit 1006 schliesst, entsteht die Endlos-Schleife:
```
getAccessToken → connectToWS → 403 → close 1006 → getAccessToken → ...
```

Im Live-Log sichtbar: alle ~5s ein neuer Token. Nach kurzer Zeit (10-20 Tokens) sperrt Husqvarna:
```
[getAccessToken]: HTTP status response: 400
data: {"error":"invalid_request","error_description":"Simultaneous logins detected...","error_code":"simultaneous.logins"}
```

### Bug 3: Token-Refresh blockiert Token vom anderen Adapter

Wenn ioBroker-Adapter und HA-Custom-Integration parallel laufen wuerden, blockieren sie sich gegenseitig via `simultaneous.logins`.

### Konsequenz fuer Eigenentwicklung

1. **Alle 3 Headers** im WS-Handshake setzen
2. **Token-Cache** mit 24h-Lifetime, NICHT pro Reconnect refreshen
3. **Reconnect-Backoff** statt 5s-Fixed-Delay
4. **Vor Discovery:** ioBroker-Adapter stoppen (sonst gegenseitige Sperre)
5. **Optional:** neue App "HomeAssistant" im Developer Portal anlegen → parallele Tests moeglich

## Mower-Datentypen / Enumerationen (zu verifizieren in Discovery)

### `mower.mode`
- `MAIN_AREA`
- `SECONDARY_AREA`
- `HOME`
- `DEMO`
- `POI`
- `UNKNOWN`

### `mower.activity`
- `UNKNOWN`
- `NOT_APPLICABLE`
- `MOWING`
- `GOING_HOME`
- `CHARGING`
- `LEAVING`
- `PARKED_IN_CS`
- `STOPPED_IN_GARDEN`

### `mower.state`
- `UNKNOWN`
- `NOT_APPLICABLE`
- `PAUSED`
- `IN_OPERATION`
- `WAIT_UPDATING`
- `WAIT_POWER_UP`
- `RESTRICTED`
- `OFF`
- `STOPPED`
- `ERROR`
- `FATAL_ERROR`
- `ERROR_AT_POWER_UP`

### `planner.override.action`
- `NOT_ACTIVE`
- `FORCE_PARK`
- `FORCE_MOW`

### `planner.restrictedReason`
- `NONE`
- `WEEK_SCHEDULE`
- `PARK_OVERRIDE`
- `SENSOR`
- `DAILY_LIMIT`
- `FOTA`
- `FROST`

### `inactiveReason`
- `NONE`
- `PLANNING`
- `SEARCHING_FOR_SATELLITES`

## Open Questions (in Discovery klaeren)

1. WS-Frame-Format: kommt `id` als JSON:API-style `data.id` oder flat? Genaue Schema-Struktur?
2. WS sendet bei Mode-Wechsel komplette `attributes.mower` oder nur Delta?
3. Triggern POST-Actions ein WS-Event (Confirm via Push) oder muss man pollen?
4. PATCH-Settings: Wartet API auf Mower-Ack (synchron) oder asynchron?
5. Rate-Limit Header (X-RateLimit-Remaining etc.) - vorhanden?
6. WS-Heartbeat: Funktioniert aiohttp's `heartbeat=60` ohne Antwort vom Server? (TCP-Keepalive ausreichend?)
7. Position-Events: kommen die pro neuer Position oder nur Snapshots?
8. Statistics: ueber WS oder nur REST-Pull?

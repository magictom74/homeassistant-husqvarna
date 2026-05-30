# Husqvarna Connect API Notes

Sammlung der relevanten Endpoints + Eigenheiten. Basiert auf:
- **Offizielle OpenAPI-Spec v1.0.0** (`docs/openapi-automower-connect-v1.0.yaml`,
  bezogen aus dem Husqvarna Developer Portal am 2026-05-30)
- Eigene Live-Validierung pyhusqvarna v0.1 gegen einen 305E NERA (2026-05-30)
- Husqvarna Developer Portal Docs (https://developer.husqvarnagroup.cloud/)
- Code-Analyse `aioautomower` (HA-Core-Library) als Cross-Reference

## Pflicht-Subscriptions im Husqvarna Developer Portal

Die Application im Portal braucht **alle drei** der folgenden Connected APIs.
Fehlt eine, schlagen Teile fehl - ohne dass der Fehler im Application-Log
des Adapters offensichtlich wird:

| Subscription | Was es ermoeglicht |
|---|---|
| **Authentication API** | OAuth2-Token holen (`/oauth2/token`) |
| **Automower Connect API** | REST gegen `api.amc.husqvarna.dev/v1/...` |
| **Connectivity API** | WebSocket gegen `wss://ws.openapi.husqvarna.dev/v1` |

Symptome bei fehlender Subscription:
- Fehlt **Connectivity API** -> WS-Handshake liefert
  `403 {"message":"User is not authorized to access this resource with an explicit deny in an identity-based policy"}`.
  REST funktioniert in dem Zustand weiterhin.
- Token-Response hat `scope: "iam:read"` (zeigt nur die Authentication-API
  Subscription) **auch wenn** die anderen Subscriptions tatsaechlich aktiv
  sind - das `scope`-Feld ist also kein verlaesslicher Indikator. Nur der
  HTTP-Status auf konkreten Endpoints zeigt den wahren Stand.

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

### Aktion senden (POST /actions)

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/actions
Content-Type: application/vnd.api+json

{"data": {"type": "<ACTION>", "attributes": {<OPTIONAL>}}}
```

**Action-Typen (laut OpenAPI-Spec):**

| Action | Body | Wirkung |
|--------|------|---------|
| `ResumeSchedule` | `{}` | Schedule wieder aktiv |
| `Pause` | `{}` | Sofort pausieren |
| `ParkUntilNextSchedule` | `{}` | Bis zur naechsten Schedule parken |
| `ParkUntilFurtherNotice` | `{}` | Dauerhaft parken bis explizit resumed |
| `Park` | `{"attributes": {"duration": <minutes>}}` ODER `{"attributes": {"externalReason": <200000-299999>}}` | Fuer X Minuten parken / mit External-Reason |
| `Start` | `{"attributes": {"duration": <minutes>}}` | Sofort X Minuten ausserhalb Schedule starten |
| `StartInWorkArea` | `{"attributes": {"duration": <minutes>, "workAreaId": <int>}}` | Start in einem bestimmten Work-Area |

**ACHTUNG - ConfirmError ist KEIN `/actions`-Typ.** Eigener Endpoint:

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/errors/confirm
```

Kein Request-Body. Nur erfolgreich wenn `isErrorConfirmable: true` aktuell
auf dem Mower steht. Verfuegbar bei 405X, 415X, 435X AWD, 535 AWD, sowie
**allen Ceora, EPOS und NERA Modellen** (also auch unser 305E NERA).

**Response 202 Accepted** auf allen Action- und ConfirmError-Aufrufen.
State-Aenderung kommt asynchron via WebSocket.

### Settings aendern (POST, nicht PATCH)

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/settings
Content-Type: application/vnd.api+json

{"data": {"type": "settings", "attributes": {"cuttingHeight": 5}}}
```

**Spec-Korrektur:** Settings nutzt **POST**, nicht PATCH wie urspruenglich
angenommen. Felder:

- `cuttingHeight` (1-9)
- `headlight.mode` (`ALWAYS_ON`, `ALWAYS_OFF`, `EVENING_ONLY`, `EVENING_AND_NIGHT`)
- `timer: { dateTime, timeZone }` - fuer Mower ohne Work-Areas, um die
  Mower-interne Uhrzeit zu setzen; Mower mit Work-Areas ignorieren das.

Response ist `JsonApiDataDocumentListCommandResult` (Liste von command-ids,
weil mehrere Settings in einem Request kombiniert werden koennen).

### Calendar aendern

```
POST https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/calendar
{"data": {"type": "calendar", "attributes": {"tasks": [...]}}}
```

Achtung: Spec-Korrektur, der Endpoint ist `/calendar` (nicht
`/calendar/tasks`). Schreibt komplette Task-Liste neu (kein partielles
Update). Fuer Mower mit Work-Areas: pro Work-Area gibt es einen eigenen
Calendar-Endpoint `/v1/mowers/<id>/workAreas/<workAreaId>/calendar`.

### Alarm-/Fehler-History (Messages)

```
GET https://api.amc.husqvarna.dev/v1/mowers/<MOWER_ID>/messages
```

Liefert die letzten bis zu 50 Messages des Mowers - mit Code, Severity
und (falls verfuegbar) GPS-Position der Fehlerstelle. Wird **nicht** ueber
WebSocket gepusht; nur per Pull abrufbar.

Schema:

```json
{
  "data": {
    "type": "messages",
    "id": "messages",
    "attributes": {
      "messages": [
        {
          "time": 1724158848,         // ms since epoch, mower-local
          "code": 49,                  // siehe Husqvarna error-code catalog
          "severity": "WARNING",       // FATAL|ERROR|WARNING|INFO|DEBUG|SW|UNKNOWN
          "latitude": 58.3855176,
          "longitude": 15.4201136
        }
      ]
    }
  }
}
```

Error-Code-Katalog:
https://developer.husqvarnagroup.cloud/apis/automower-connect-api?tab=status%20description%20and%20error%20codes

### Stay-Out-Zones

```
GET   /v1/mowers/<id>/stayOutZones
PATCH /v1/mowers/<id>/stayOutZones/<zoneId>    -> enable/disable
```

PATCH-Body: `{"data": {"type": "stayOutZone", "id": "<zoneId>", "attributes": {"enable": true|false}}}`.

Stay-Out-Zones sind auf EPOS-Mowern **nicht** verfuegbar.

### Work-Areas

```
GET   /v1/mowers/<id>/workAreas              -> alle Work-Areas mit Detail
GET   /v1/mowers/<id>/workAreas/<id>         -> ein Work-Area
PATCH /v1/mowers/<id>/workAreas/<id>         -> cuttingHeight / enabled / name / orientation
POST  /v1/mowers/<id>/workAreas/<id>/calendar -> Task-Liste pro Work-Area
```

WorkArea-Felder (vollstaendig):

- `workAreaId` (int64), `name`, `type` (`RANDOM` | `SYSTEMATIC`)
- `cuttingHeight` **0-100 (Prozent)** - NICHT 1-9 wie das globale Setting!
- `enabled` (bool), `useGlobalCuttingHeight` (bool)
- `orientation` / `orientationShift` / `currentOrientation` (nur EPOS,
  fuer SYSTEMATIC-Mowing-Pattern)
- `progress` (0-100, nur EPOS), `lastTimeCompleted`, `lastTimeAbandoned`
  (Unix-Sekunden, mower-local)

### Profile

```
GET    /v1/mowers/<id>/profiles
POST   /v1/mowers/<id>/profiles                -> neues Profil anlegen
GET    /v1/mowers/<id>/profiles/current
PATCH  /v1/mowers/<id>/profiles/current        -> aktuelles Profil umbenennen
POST   /v1/mowers/<id>/profiles/<profileId>    -> dieses Profil als current setzen
DELETE /v1/mowers/<id>/profiles/<profileId>
```

Profile sind verschiedene Sets an Work-Areas. Nur eines kann gleichzeitig
aktiv sein. Profile-Wechsel laed neue Map-Daten - kann mehrere Sekunden
dauern, kein Push wenn fertig.

### Statistics-Reset

```
POST /v1/mowers/<id>/statistics/resetCuttingBladeUsageTime
```

Setzt nur den `cuttingBladeUsageTime`-Counter zurueck - z.B. nach
Klingenwechsel.

## WebSocket

### Endpoint

```
wss://ws.openapi.husqvarna.dev/v1
Headers (im Handshake):
  Authorization: Bearer <TOKEN>
  X-Api-Key: <APP_KEY>
  Authorization-Provider: husqvarna
```

### Event-Frames (live verifiziert 2026-05-30)

**Initial-Frame (Server-Hello)** - direkt nach erfolgreichem Handshake:

```json
{"ready": true, "connectionId": "<aws-apigw-id>"}
```

Kein `type`, kein `id`. Library sollte den ignorieren (nur loggen) und auf
typed Frames warten.

**Typed Event-Frames** vom Format:

```json
{
  "id": "<MOWER_ID>",
  "type": "<EVENT_TYPE>",
  "attributes": { ... }
}
```

**WICHTIG - Position kommt als Singular:**

```json
{
  "id": "a9693dac-...",
  "type": "position-event-v2",
  "attributes": {
    "position": { "latitude": 47.30, "longitude": 8.45 }
  }
}
```

Die REST-Response (`/mowers`) hat `positions: [...]` als Array (bis 50
Punkte History). Der WebSocket pusht aber **ein einzelnes Position-Update**
unter `position` (Singular). Library muss beim Delta-Merge das neue
Position-Objekt vor die History-Liste prependen (max 50 behalten).

Andere im ioBroker-Code referenzierte (und teils in Discovery zu
verifizierende) WS-Event-Typen:

- `status-event-v2` (Annahme) → `attributes.mower`, `attributes.battery`,
  `attributes.planner`, `attributes.metadata`
- `settings-event-v2` (Annahme) → `attributes.settings`
- `calendar-event-v2` (Annahme) → `attributes.calendar`

Konkrete Event-Type-Namen im neuen `-v2`-Schema werden im naechsten
Live-Run mit aktivem Mower bestaetigt.

WebSocket sendet **immer Delta** (nur geaenderte Sub-Trees), nicht das
komplette Mower-Objekt.

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

## Mower-Datentypen / Enumerationen (laut OpenAPI v1.0.0)

### `mower.mode`
- `MAIN_AREA` - Mowt bis Akku leer, geht heim, laedt, geht wieder raus
- `SECONDARY_AREA` - Mowt bis Akku leer oder Zeit-Limit, stoppt dann im Garten
- `HOME` - Geht heim und parkt dauerhaft
- `DEMO` - Wie MAIN_AREA aber kuerzere Zyklen, **Klingen aus**
- `POI` - Point of Interest
- `UNKNOWN`

### `mower.activity`
- `UNKNOWN`, `NOT_APPLICABLE`
- `MOWING`
- `GOING_HOME` - Auf dem Weg zur Charging-Station
- `CHARGING` - Laedt, **weil er selbst entschieden hat heimzugehen**
  (laed er wegen Restriction, ist activity `PARKED_IN_CS`!)
- `LEAVING` - Verlaesst Station, Richtung Startpunkt
- `PARKED_IN_CS` - Parkt in der Station
- `STOPPED_IN_GARDEN` - Im Garten gestoppt (z.B. nach manuellem Task)

### `mower.state`
- `UNKNOWN`, `PAUSED`
- `IN_OPERATION` - Laeuft normal gemaess Mode (activity zeigt was genau)
- `WAIT_UPDATING`, `WAIT_POWER_UP`
- `RESTRICTED` - Aktuell gesperrt; activity zeigt was er gerade macht
- `OFF`, `STOPPED`
- `ERROR` - Temporaerer Fehler (z.B. Loop-Signal weg), wird auto-resumed
- `FATAL_ERROR` - Muss bestaetigt werden um zu verlassen
- `ERROR_AT_POWER_UP`

### `planner.override.action`
- `NOT_ACTIVE`
- `FORCE_PARK` - Park bis naechster geplanter Task
- `FORCE_MOW` - Erzwungenes Mowing fuer X Minuten, danach zurueck zur Calendar

### `planner.restrictedReason`
- `NONE`
- `WEEK_SCHEDULE` - Aktuell kein Task im Calendar
- `PARK_OVERRIDE` - Jemand hat manuell geparkt (Override-Feature)
- `SENSOR` - Sensor sagt: Gras kurz genug
- `DAILY_LIMIT` - Tageslimit erreicht
- `FOTA` - Firmware-Update wird uebertragen
- `FROST` - Frost-Sensor: zu kalt
- `ALL_WORK_AREAS_COMPLETED` - Alle Work-Areas fertig
- `EXTERNAL` - Externes Tool hat geparkt; siehe `externalReason` fuer Detail
- `WORK_AREA_ABANDONED` - Work-Area konnte nicht fertiggestellt werden

### `planner.externalReason` (int, nur wenn restrictedReason=EXTERNAL)

Code-Range zeigt **wer** den Mower geparkt hat:

| Range | Quelle |
|---|---|
| `1000-1999` | Google Assistant |
| `2000-2999` | Amazon Alexa |
| `3000-3999` | **Home Assistant** |
| `4000-4999` | IFTTT (z.B. 4000 Wildlife, 4001 Frost/Rain) |
| `5000-5999` | GARDENA Smart System |
| `6000-6999` | Smart Routine (6000 Rain, 6001 Frost, 6500 Wildlife) |
| `100000-199999` | IFTTT applets |
| `200000-299999` | Developer Portal Apps (z.B. unsere App) |

Wir verwenden `200000-299999` wenn pyhusqvarna selbst einen Park-Befehl
mit externalReason absendet.

### `mower.inactiveReason`
- `NONE`
- `PLANNING` - Mower plant Pfad/Work-Area
- `SEARCHING_FOR_SATELLITES` - EPOS wartet auf GPS-Fix

### `message.severity` (vom `/messages`-Endpoint)
- `FATAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `SW`, `UNKNOWN`

## Discovery-Status (Stand 2026-05-30)

| Frage | Antwort |
|---|---|
| WS-Frame-Format | Flach: `{id, type, attributes}` (kein JSON:API-data-Wrapper). Initial-Frame ist `{ready, connectionId}` ohne id/type. |
| Position via WS | Pusht jede neue Position einzeln als `position-event-v2` mit `attributes.position` **Singular**. REST-Snapshot hat `positions` als 50er-Array. |
| WS sendet Delta | Ja - nur die geaenderten Sub-Trees. Volle Snapshots nur via REST. |
| POST-Actions -> WS-Event | Live noch zu verifizieren - vermutet ja, weil andere Klienten (App, IFTTT) auch State-Aenderungen verursachen und der eigene Push gleich aussieht. |
| WS-Heartbeat | aiohttp `heartbeat=60` setzt Ping; Husqvarna-Server pongt nicht aber TCP bleibt offen. In Live-Run >2h validieren. |
| Statistics ueber WS | Vermutet nein - nur via REST-Pull. |
| Messages ueber WS | Nein - nur per Pull (`/mowers/<id>/messages`). |
| Rate-Limit-Header | Live zu pruefen (Husqvarna nennt 10000 Req/Monat als Limit). |

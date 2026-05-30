"""Tests for AutomowerClient against a mocked cloud."""

from __future__ import annotations

import httpx
import pytest
import respx

from pyhusqvarna import (
    TOKEN_URL,
    AutomowerClient,
    HeadlightMode,
    HusqvarnaAuth,
    MessageSeverity,
    NotFoundError,
    ProtocolError,
    RateLimitError,
)

BASE = "https://api.amc.husqvarna.dev"
MOWER_ID = "<MOWER_UUID>"


@pytest.fixture
def auth() -> HusqvarnaAuth:
    return HusqvarnaAuth(api_key="K", api_secret="S")


def _stub_token() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok-A", "expires_in": 86400,
        "provider": "husqvarna", "user_id": "u",
    }))


def _stub_one_mower() -> dict[str, object]:
    return {
        "data": [{
            "type": "mower",
            "id": MOWER_ID,
            "attributes": {
                "system": {"name": "Test", "model": "305E NERA", "serialNumber": 1},
                "battery": {"batteryPercent": 50},
                "capabilities": {"canConfirmError": True, "position": True},
                "mower": {
                    "mode": "MAIN_AREA", "activity": "MOWING", "state": "IN_OPERATION",
                    "errorCode": 0, "isErrorConfirmable": False,
                },
                "metadata": {"connected": True, "statusTimestamp": 0},
            },
        }],
    }


@respx.mock
async def test_list_mowers(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers").mock(
        return_value=httpx.Response(200, json=_stub_one_mower())
    )
    async with AutomowerClient(auth) as client:
        mowers = await client.list_mowers()
    assert len(mowers) == 1
    assert mowers[0].id == MOWER_ID
    assert mowers[0].battery_percent == 50


@respx.mock
async def test_list_mowers_sends_all_three_headers(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.get(f"{BASE}/v1/mowers").mock(
        return_value=httpx.Response(200, json=_stub_one_mower())
    )
    async with AutomowerClient(auth) as client:
        await client.list_mowers()
    request = route.calls[0].request
    assert request.headers.get("authorization") == "Bearer tok-A"
    assert request.headers.get("x-api-key") == "K"
    assert request.headers.get("authorization-provider") == "husqvarna"


@respx.mock
async def test_get_mower(auth: HusqvarnaAuth) -> None:
    _stub_token()
    payload = _stub_one_mower()["data"][0]  # type: ignore[index]
    respx.get(f"{BASE}/v1/mowers/{MOWER_ID}").mock(
        return_value=httpx.Response(200, json={"data": payload})
    )
    async with AutomowerClient(auth) as client:
        mower = await client.get_mower(MOWER_ID)
    assert mower.id == MOWER_ID
    assert mower.is_mowing


@respx.mock
async def test_park_until_next_schedule(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions").mock(
        return_value=httpx.Response(202)
    )
    async with AutomowerClient(auth) as client:
        await client.park_until_next_schedule(MOWER_ID)
    body = route.calls[0].request.read()
    assert b'"type": "ParkUntilNextSchedule"' in body or b'"type":"ParkUntilNextSchedule"' in body


@respx.mock
async def test_park_for_includes_duration(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions").mock(
        return_value=httpx.Response(202)
    )
    async with AutomowerClient(auth) as client:
        await client.park_for(MOWER_ID, duration_minutes=45)
    body = route.calls[0].request.read()
    assert b'"Park"' in body
    assert b'"duration": 45' in body or b'"duration":45' in body


@respx.mock
async def test_resume_pause_start(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions").mock(
        return_value=httpx.Response(202)
    )
    async with AutomowerClient(auth) as client:
        await client.resume_schedule(MOWER_ID)
        await client.pause(MOWER_ID)
        await client.start_for(MOWER_ID, duration_minutes=30)
    actions = [c.request.read() for c in route.calls]
    assert any(b'"ResumeSchedule"' in a for a in actions)
    assert any(b'"Pause"' in a for a in actions)
    assert any(b'"Start"' in a for a in actions)


@respx.mock
async def test_start_in_work_area(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions").mock(
        return_value=httpx.Response(202)
    )
    async with AutomowerClient(auth) as client:
        await client.start_in_work_area(MOWER_ID, work_area_id=42, duration_minutes=60)
        with pytest.raises(ValueError):
            await client.start_in_work_area(MOWER_ID, work_area_id=42, duration_minutes=0)
    body = route.calls[0].request.read()
    assert b'"StartInWorkArea"' in body
    assert b'"workAreaId": 42' in body or b'"workAreaId":42' in body
    assert b'"duration": 60' in body or b'"duration":60' in body


@respx.mock
async def test_confirm_error_uses_dedicated_endpoint(auth: HusqvarnaAuth) -> None:
    # ConfirmError is /errors/confirm per OpenAPI v1.0.0, NOT /actions
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/errors/confirm").mock(
        return_value=httpx.Response(202)
    )
    actions_route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions")
    async with AutomowerClient(auth) as client:
        await client.confirm_error(MOWER_ID)
    assert route.called
    assert not actions_route.called


@respx.mock
async def test_invalid_durations_raise(auth: HusqvarnaAuth) -> None:
    async with AutomowerClient(auth) as client:
        with pytest.raises(ValueError):
            await client.park_for(MOWER_ID, duration_minutes=0)
        with pytest.raises(ValueError):
            await client.start_for(MOWER_ID, duration_minutes=-5)


@respx.mock
async def test_set_cutting_height_range(auth: HusqvarnaAuth) -> None:
    _stub_token()
    # Settings uses POST per OpenAPI v1.0.0, not PATCH
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/settings").mock(
        return_value=httpx.Response(200)
    )
    async with AutomowerClient(auth) as client:
        await client.set_cutting_height(MOWER_ID, 5)
        with pytest.raises(ValueError):
            await client.set_cutting_height(MOWER_ID, 0)
        with pytest.raises(ValueError):
            await client.set_cutting_height(MOWER_ID, 10)
    body = route.calls[0].request.read()
    assert b'"cuttingHeight": 5' in body or b'"cuttingHeight":5' in body


@respx.mock
async def test_set_headlight_mode(auth: HusqvarnaAuth) -> None:
    _stub_token()
    # Settings uses POST per OpenAPI v1.0.0, not PATCH
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/settings").mock(
        return_value=httpx.Response(200)
    )
    async with AutomowerClient(auth) as client:
        await client.set_headlight_mode(MOWER_ID, HeadlightMode.EVENING_ONLY)
        with pytest.raises(ValueError):
            await client.set_headlight_mode(MOWER_ID, HeadlightMode.UNKNOWN)
    body = route.calls[0].request.read()
    assert b'"EVENING_ONLY"' in body


@respx.mock
async def test_get_messages(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers/{MOWER_ID}/messages").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "type": "messages",
                "id": "messages",
                "attributes": {
                    "messages": [
                        {"time": 1724158848, "code": 49, "severity": "WARNING",
                         "latitude": 47.30, "longitude": 8.45},
                        {"time": 1724148000, "code": 15, "severity": "ERROR"},
                    ],
                },
            },
        })
    )
    async with AutomowerClient(auth) as client:
        msgs = await client.get_messages(MOWER_ID)
    assert len(msgs) == 2
    assert msgs[0].code == 49
    assert msgs[0].severity is MessageSeverity.WARNING
    assert msgs[0].latitude == 47.30
    assert msgs[1].latitude is None  # no position on this one


@respx.mock
async def test_reset_cutting_blade(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(
        f"{BASE}/v1/mowers/{MOWER_ID}/statistics/resetCuttingBladeUsageTime"
    ).mock(return_value=httpx.Response(202))
    async with AutomowerClient(auth) as client:
        await client.reset_cutting_blade_usage_time(MOWER_ID)
    assert route.called


@respx.mock
async def test_stay_out_zones_get_and_toggle(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers/{MOWER_ID}/stayOutZones").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "type": "stayOutZones",
                "id": "stayOutZones",
                "attributes": {
                    "dirty": False,
                    "zones": [
                        {"id": "zone-1", "name": "Flowers", "enabled": True},
                    ],
                },
            },
        })
    )
    zone_id = "zone-1"
    patch_route = respx.patch(
        f"{BASE}/v1/mowers/{MOWER_ID}/stayOutZones/{zone_id}"
    ).mock(return_value=httpx.Response(202))

    async with AutomowerClient(auth) as client:
        zones = await client.get_stay_out_zones(MOWER_ID)
        await client.set_stay_out_zone_enabled(MOWER_ID, zone_id, enabled=False)

    assert len(zones) == 1
    assert zones[0].name == "Flowers"
    body = patch_route.calls[0].request.read()
    assert b'"enable": false' in body or b'"enable":false' in body


@respx.mock
async def test_work_areas_get_and_patch(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers/{MOWER_ID}/workAreas").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"type": "workArea", "id": 1, "attributes": {
                    "workAreaId": 1, "name": "Front", "cuttingHeight": 60,
                    "enabled": True,
                }},
            ],
        })
    )
    patch_route = respx.patch(f"{BASE}/v1/mowers/{MOWER_ID}/workAreas/1").mock(
        return_value=httpx.Response(202)
    )

    async with AutomowerClient(auth) as client:
        areas = await client.get_work_areas(MOWER_ID)
        await client.set_work_area_cutting_height(
            MOWER_ID, 1, cutting_height_percent=80
        )
        with pytest.raises(ValueError):
            await client.set_work_area_cutting_height(
                MOWER_ID, 1, cutting_height_percent=101
            )

    assert len(areas) == 1
    assert areas[0].name == "Front"
    assert areas[0].cutting_height == 60
    body = patch_route.calls[0].request.read()
    assert b'"cuttingHeight": 80' in body or b'"cuttingHeight":80' in body


@respx.mock
async def test_404_raises_not_found(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers/missing").mock(return_value=httpx.Response(404))
    async with AutomowerClient(auth) as client:
        with pytest.raises(NotFoundError):
            await client.get_mower("missing")


@respx.mock
async def test_429_raises_rate_limit(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers").mock(return_value=httpx.Response(429))
    async with AutomowerClient(auth) as client:
        with pytest.raises(RateLimitError):
            await client.list_mowers()


@respx.mock
async def test_5xx_raises_protocol_error(auth: HusqvarnaAuth) -> None:
    _stub_token()
    respx.get(f"{BASE}/v1/mowers").mock(return_value=httpx.Response(503))
    async with AutomowerClient(auth) as client:
        with pytest.raises(ProtocolError):
            await client.list_mowers()


@respx.mock
async def test_401_triggers_token_refresh_and_retry(auth: HusqvarnaAuth) -> None:
    # Two token requests: initial + force-refresh after 401
    token_route = respx.post(TOKEN_URL).mock(side_effect=[
        httpx.Response(200, json={
            "access_token": "old", "expires_in": 86400,
            "provider": "husqvarna", "user_id": "u",
        }),
        httpx.Response(200, json={
            "access_token": "new", "expires_in": 86400,
            "provider": "husqvarna", "user_id": "u",
        }),
    ])
    # First request 401, retry succeeds
    list_route = respx.get(f"{BASE}/v1/mowers").mock(side_effect=[
        httpx.Response(401),
        httpx.Response(200, json=_stub_one_mower()),
    ])
    async with AutomowerClient(auth) as client:
        mowers = await client.list_mowers()
    assert len(mowers) == 1
    assert token_route.call_count == 2
    assert list_route.call_count == 2
    # Second list call must use the new token
    assert list_route.calls[1].request.headers.get("authorization") == "Bearer new"

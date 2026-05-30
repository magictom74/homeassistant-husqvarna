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
async def test_resume_pause_start_confirm(auth: HusqvarnaAuth) -> None:
    _stub_token()
    route = respx.post(f"{BASE}/v1/mowers/{MOWER_ID}/actions").mock(
        return_value=httpx.Response(202)
    )
    async with AutomowerClient(auth) as client:
        await client.resume_schedule(MOWER_ID)
        await client.pause(MOWER_ID)
        await client.start_for(MOWER_ID, duration_minutes=30)
        await client.confirm_error(MOWER_ID)
    actions = [c.request.read() for c in route.calls]
    assert any(b'"ResumeSchedule"' in a for a in actions)
    assert any(b'"Pause"' in a for a in actions)
    assert any(b'"Start"' in a for a in actions)
    assert any(b'"ConfirmError"' in a for a in actions)


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
    route = respx.patch(f"{BASE}/v1/mowers/{MOWER_ID}/settings").mock(
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
    route = respx.patch(f"{BASE}/v1/mowers/{MOWER_ID}/settings").mock(
        return_value=httpx.Response(200)
    )
    async with AutomowerClient(auth) as client:
        await client.set_headlight_mode(MOWER_ID, HeadlightMode.EVENING_ONLY)
        with pytest.raises(ValueError):
            await client.set_headlight_mode(MOWER_ID, HeadlightMode.UNKNOWN)
    body = route.calls[0].request.read()
    assert b'"EVENING_ONLY"' in body


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

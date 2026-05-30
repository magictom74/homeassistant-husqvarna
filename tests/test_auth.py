"""Tests for HusqvarnaAuth - token request, caching, simultaneous-login error."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from pyhusqvarna import (
    TOKEN_URL,
    AuthError,
    HusqvarnaAuth,
    SimultaneousLoginsError,
)


@respx.mock
async def test_get_token_caches_for_24h() -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={
            "access_token": "tok-A",
            "scope": "iam:read",
            "expires_in": 86400,
            "provider": "husqvarna",
            "user_id": "user-1",
            "token_type": "Bearer",
        })
    )
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    first = await auth.get_token()
    second = await auth.get_token()  # served from cache
    assert first.value == "tok-A"
    assert second is first
    assert route.call_count == 1
    await auth.aclose()


@respx.mock
async def test_force_refresh_re_requests() -> None:
    route = respx.post(TOKEN_URL).mock(side_effect=[
        httpx.Response(200, json={
            "access_token": "tok-A", "expires_in": 86400,
            "provider": "husqvarna", "user_id": "u",
        }),
        httpx.Response(200, json={
            "access_token": "tok-B", "expires_in": 86400,
            "provider": "husqvarna", "user_id": "u",
        }),
    ])
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    a = await auth.get_token()
    b = await auth.get_token(force_refresh=True)
    assert a.value == "tok-A"
    assert b.value == "tok-B"
    assert route.call_count == 2
    await auth.aclose()


@respx.mock
async def test_simultaneous_logins_raises_typed_error() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={
        "error": "invalid_request",
        "error_description": "Simultaneous logins detected ...",
        "error_code": "simultaneous.logins",
    }))
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    with pytest.raises(SimultaneousLoginsError):
        await auth.get_token()
    await auth.aclose()


@respx.mock
async def test_other_400_raises_generic_auth_error() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={
        "error": "invalid_request",
        "error_description": "bad client_id",
    }))
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    with pytest.raises(AuthError):
        await auth.get_token()
    await auth.aclose()


@respx.mock
async def test_500_raises_auth_error() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(500, text="boom"))
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    with pytest.raises(AuthError):
        await auth.get_token()
    await auth.aclose()


@respx.mock
async def test_auth_headers_shape() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok-A", "expires_in": 86400,
        "provider": "husqvarna", "user_id": "u",
    }))
    auth = HusqvarnaAuth(api_key="api-key-XYZ", api_secret="S")
    token = await auth.get_token()
    headers = auth.auth_headers(token)
    # All three required headers - the bug behind most failures
    assert headers["Authorization"] == "Bearer tok-A"
    assert headers["X-Api-Key"] == "api-key-XYZ"
    assert headers["Authorization-Provider"] == "husqvarna"
    await auth.aclose()


def test_constructor_rejects_empty_credentials() -> None:
    with pytest.raises(ValueError):
        HusqvarnaAuth(api_key="", api_secret="S")
    with pytest.raises(ValueError):
        HusqvarnaAuth(api_key="K", api_secret="")


@respx.mock
async def test_safety_margin_applied() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={
        "access_token": "tok", "expires_in": 3600,  # 1 hour
        "provider": "husqvarna", "user_id": "u",
    }))
    auth = HusqvarnaAuth(api_key="K", api_secret="S")
    token = await auth.get_token()
    # Safety margin is 5 min, so expires_at < now + 3600 - 300 + epsilon
    now = time.monotonic()
    assert token.expires_at - now < 3600 - 299
    assert token.expires_at - now > 3600 - 301
    await auth.aclose()

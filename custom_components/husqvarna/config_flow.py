"""Config flow for the Husqvarna integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from pyhusqvarna import (
    AuthError,
    AutomowerClient,
    HusqvarnaAuth,
    HusqvarnaConnectionError,
    HusqvarnaTimeoutError,
    SimultaneousLoginsError,
)

from .const import CONF_API_KEY, CONF_API_SECRET, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_API_SECRET): cv.string,
    }
)


class HusqvarnaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for one Husqvarna Developer-Portal application.

    The user pastes the Application Key + Application Secret from
    https://developer.husqvarnagroup.cloud/. We validate the credentials
    by requesting an access token and listing mowers; that also gives us
    a stable ``user_id`` to use as ``unique_id`` so re-adding the same
    account is detected.

    Required portal subscriptions for the application:

    * Authentication API
    * Automower Connect API
    * Connectivity API  (required for the WebSocket)

    Missing the Connectivity API only manifests on WebSocket connect
    (403), not at config-flow time - REST works without it.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id, account_label = await self._probe(
                user_input[CONF_API_KEY],
                user_input[CONF_API_SECRET],
                errors,
            )
            if unique_id is not None:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=account_label or "Husqvarna",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_API_SECRET: user_input[CONF_API_SECRET],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def _probe(
        self, api_key: str, api_secret: str, errors: dict[str, str]
    ) -> tuple[str | None, str]:
        """Validate credentials and return (unique_id, friendly_label)."""
        auth = HusqvarnaAuth(api_key=api_key, api_secret=api_secret)
        try:
            token = await auth.get_token()
        except SimultaneousLoginsError:
            errors["base"] = "simultaneous_logins"
            return None, ""
        except AuthError:
            errors["base"] = "invalid_auth"
            return None, ""
        except (HusqvarnaConnectionError, HusqvarnaTimeoutError):
            errors["base"] = "cannot_connect"
            return None, ""
        except Exception:
            _LOGGER.exception("[husqvarna.config_flow] Unexpected probe failure")
            errors["base"] = "unknown"
            return None, ""

        # Use the cloud-side user_id as unique_id - that's the Husqvarna
        # account, which is what we really want to dedupe on (same
        # account can have multiple apps with different keys).
        unique_id = token.user_id or api_key

        # Also try to list mowers so the user gets early feedback if the
        # account has none paired. We tolerate failure here - REST might
        # be down even if auth worked.
        try:
            async with AutomowerClient(auth) as client:
                mowers = await client.list_mowers()
            label = (
                f"Husqvarna ({len(mowers)} mower"
                f"{'s' if len(mowers) != 1 else ''})"
                if mowers else "Husqvarna"
            )
        except Exception as exc:
            _LOGGER.debug("[husqvarna.config_flow] list_mowers failed: %s", exc)
            label = "Husqvarna"
        finally:
            await auth.aclose()

        return unique_id, label

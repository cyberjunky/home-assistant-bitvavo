"""Config flow for the Bitvavo integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from bitvavo.BitvavoClient import BitvavoClient
from bitvavo.BitvavoExceptions import BitvavoAuthError, BitvavoException
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_API_SECRET, CONF_MARKETS, CONF_SHOW_EMPTY_ASSETS, DOMAIN, REQUEST_TIMEOUT
from .coordinator import BitvavoConfigEntry
from .errors import CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(),
        vol.Required(CONF_API_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _markets_schema(markets: list[str] | None, default: list[str] | None = None) -> vol.Schema:
    """Markets selection schema."""
    return vol.Schema(
        {
            vol.Required(CONF_MARKETS, default=default or []): SelectSelector(
                SelectSelectorConfig(
                    options=markets or [],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            )
        }
    )


async def validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the API key and get the available markets and balances."""
    client = BitvavoClient(
        data[CONF_API_KEY],
        data[CONF_API_SECRET],
        session=async_get_clientsession(hass),
        timeout=REQUEST_TIMEOUT,
    )

    try:
        # A signed call validates the key and its View permission
        balances = await client.get_balance()
        markets = await client.get_price_ticker()
    except BitvavoAuthError as error:
        raise InvalidAuth from error
    except BitvavoException as error:
        raise CannotConnect from error

    return {
        "markets": sorted(market["market"] for market in markets),
        "balances": sorted(balance["symbol"] for balance in balances),
    }


class BitvavoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bitvavo."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the Bitvavo config flow."""
        self.bitvavo_config: dict[str, Any] = {}
        self.markets: list[str] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: BitvavoConfigEntry) -> BitvavoOptionsFlowHandler:
        """Get the options flow for this handler."""
        return BitvavoOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            info, errors = await self._async_validate_or_error(user_input)

            if not errors:
                self.bitvavo_config.update(user_input)
                self.markets = info["markets"]

                return await self.async_step_markets()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_markets(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the picking of the markets."""
        if user_input is not None:
            self.bitvavo_config.update(user_input)
            return self.async_create_entry(title="Bitvavo", data=self.bitvavo_config)

        return self.async_show_form(
            step_id="markets",
            data_schema=_markets_schema(self.markets),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle a rejected API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key and secret."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _, errors = await self._async_validate_or_error(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data={**self._get_reauth_entry().data, **user_input},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA,
                user_input or {CONF_API_KEY: self._get_reauth_entry().data[CONF_API_KEY]},
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the tracked markets."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, CONF_MARKETS: user_input[CONF_MARKETS]},
            )

        info, errors = await self._async_validate_or_error(entry.data)
        if errors:
            return self.async_abort(reason=errors["base"])

        current = list(entry.data.get(CONF_MARKETS, []))
        # Keep markets that are currently not trading selectable
        options = sorted(set(info["markets"]) | set(current))

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_markets_schema(options, current),
        )

    async def _async_validate_or_error(
        self, config: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        errors: dict[str, str] = {}
        info: dict[str, Any] = {}

        try:
            info = await validate_input(self.hass, config)
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        return info, errors


class BitvavoOptionsFlowHandler(OptionsFlow):
    """Handle Bitvavo options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage Bitvavo options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_SHOW_EMPTY_ASSETS,
                default=self.config_entry.options.get(CONF_SHOW_EMPTY_ASSETS, True),
            ): bool,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))

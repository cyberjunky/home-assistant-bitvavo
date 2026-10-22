"""DataUpdateCoordinator for the Bitvavo integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from bitvavo.BitvavoClient import BitvavoClient
from bitvavo.BitvavoExceptions import (
    BitvavoAuthError,
    BitvavoException,
    BitvavoRateLimitError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ASSET_VALUE_BASE,
    ASSET_VALUE_CURRENCIES,
    CONF_ASSET_TICKERS,
    CONF_BALANCES,
    CONF_MARKETS,
    CONF_OPEN_ORDERS,
    CONF_SHOW_EMPTY_ASSETS,
    CONF_TICKERS,
    DATA_FEES,
    DATA_STAKING,
    DATA_TOTAL_BASE_ASSET,
    DOMAIN,
    FEES_REFRESH_INTERVAL,
    MARKETS_REFRESH_INTERVAL,
    OPEN_ORDERS_REFRESH_INTERVAL,
    SCAN_INTERVAL,
    STAKING_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type BitvavoConfigEntry = ConfigEntry[BitvavoDataUpdateCoordinator]


def _as_list(response: Any) -> list[dict[str, Any]]:
    """Return an API response as a list of dicts."""
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        return [response]
    return []


def _to_float(value: Any) -> float | None:
    """Convert an API string value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _Cached:
    """A value that is only refreshed after a given interval."""

    def __init__(self, interval: timedelta, default: Any) -> None:
        self.interval = interval
        self.value = default
        self.updated: datetime | None = None

    async def async_get(self, fetch: Callable[[], Awaitable[Any]]) -> Any:
        now = dt_util.utcnow()
        if self.updated is None or now - self.updated >= self.interval:
            self.value = await fetch()
            self.updated = now
        return self.value


class BitvavoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to get the latest data from Bitvavo."""

    config_entry: BitvavoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BitvavoConfigEntry, client: BitvavoClient
    ) -> None:
        """Initialize the data object."""
        self._client = client
        self._show_empty_assets: bool = entry.options.get(CONF_SHOW_EMPTY_ASSETS, True)
        self._markets: list[str] = entry.data[CONF_MARKETS]

        self.asset_currencies = ASSET_VALUE_CURRENCIES

        self._market_info = _Cached(MARKETS_REFRESH_INTERVAL, [])
        self._open_orders = _Cached(OPEN_ORDERS_REFRESH_INTERVAL, [])
        self._staking = _Cached(STAKING_REFRESH_INTERVAL, [])
        self._fees = _Cached(FEES_REFRESH_INTERVAL, {})

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    @property
    def client(self) -> BitvavoClient:
        """Return the API client."""
        return self._client

    @staticmethod
    def _prep_markets(
        marketscfg: list[str],
        tickers: list[dict[str, Any]],
        markets: list[dict[str, Any]],
        tickers_24h: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Prepare markets data.

        Markets that are not trading (halted, delisted) are not returned by the
        ticker endpoints and are left out, which makes their sensors unavailable.
        """
        tickers_by_market = {item.get("market"): item for item in tickers}
        markets_by_market = {item.get("market"): item for item in markets}
        stats_by_market = {item.get("market"): item for item in tickers_24h}

        tickers_dict: dict[str, dict[str, Any]] = {}
        for market in marketscfg:
            ticker = tickers_by_market.get(market)
            if ticker is None:
                continue
            tickers_dict[market] = {
                **markets_by_market.get(market, {}),
                **stats_by_market.get(market, {}),
                **ticker,
            }

        return tickers_dict

    @staticmethod
    def _prep_tickers(
        asset_currencies: set[str], tickers: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Prepare tickers data."""
        tickers_by_market = {item.get("market"): item for item in tickers}

        return {
            f"{asset}-{ASSET_VALUE_BASE}": dict(
                tickers_by_market.get(f"{asset}-{ASSET_VALUE_BASE}", {})
            )
            for asset in asset_currencies
            # Skip the ASSET_VALUE_BASE as we calculate it differently
            if asset != ASSET_VALUE_BASE
        }

    @staticmethod
    def _prep_balances(
        balances: list[dict[str, Any]],
        tickers: list[dict[str, Any]],
        show_empty_assets: bool,
        staking: list[dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Prepare balances data."""
        tickers_by_market = {item.get("market"): item for item in tickers}
        staked = {
            item["symbol"]: _to_float(item.get("amount")) or 0.0
            for item in staking or []
            if "symbol" in item
        }

        balances_dict: dict[str, dict[str, Any]] = {}

        for balance in balances:
            symbol = balance.get("symbol")
            if symbol is None or symbol in balances_dict:
                continue

            total_balance = (_to_float(balance.get("available")) or 0.0) + (
                _to_float(balance.get("inOrder")) or 0.0
            )

            if not show_empty_assets and total_balance == 0.0:
                continue

            balances_dict[symbol] = dict(balance)
            if symbol in staked:
                balances_dict[symbol]["staked"] = staked[symbol]

            if symbol == ASSET_VALUE_BASE:
                balances_dict[symbol]["asset_value_in_base_asset"] = total_balance
                continue

            # If we can find a pair with ASSET_VALUE_BASE, include it in the dict
            base_asset_ticker = tickers_by_market.get(f"{symbol}-{ASSET_VALUE_BASE}")
            price = _to_float(base_asset_ticker.get("price")) if base_asset_ticker else None
            if base_asset_ticker is None or price is None:
                continue

            balances_dict[symbol][ASSET_VALUE_BASE] = dict(base_asset_ticker)
            balances_dict[symbol]["asset_value_in_base_asset"] = total_balance * price

        return balances_dict

    @staticmethod
    def _prep_total_base_asset(balances: dict[str, dict[str, Any]]) -> float:
        """Prepare total base asset value data."""
        return sum(
            float(balance["asset_value_in_base_asset"])
            for balance in balances.values()
            if "asset_value_in_base_asset" in balance
        )

    async def _async_fetch_staking(self) -> list[dict[str, Any]]:
        """Fetch staking balances; optional, never fails the update."""
        try:
            return _as_list(await self._client.get_staking_balance())
        except BitvavoException as err:
            _LOGGER.debug("Could not fetch staking balance: %s", err)
            return []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch Bitvavo data."""
        try:
            # Public endpoints (no API key, counted per IP)
            tickers = _as_list(await self._client.get_price_ticker())
            tickers_24h = _as_list(await self._client.get_24h_price_ticker())
            markets = _as_list(await self._market_info.async_get(self._client.get_markets))

            # Private endpoints (counted against the account rate limit)
            balances = _as_list(await self._client.get_balance())
            open_orders = _as_list(await self._open_orders.async_get(self._client.get_open_orders))
            staking = await self._staking.async_get(self._async_fetch_staking)
            account = await self._fees.async_get(self._client.get_account)
        except BitvavoAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Bitvavo rejected the API key: {err.error or err.message}"
            ) from err
        except BitvavoRateLimitError as err:
            raise UpdateFailed(f"Bitvavo rate limit exceeded: {err.error or err.message}") from err
        except BitvavoException as err:
            raise UpdateFailed(f"Error communicating with Bitvavo: {err}") from err

        balances_dict = self._prep_balances(balances, tickers, self._show_empty_assets, staking)

        return {
            CONF_TICKERS: self._prep_markets(self._markets, tickers, markets, tickers_24h),
            CONF_ASSET_TICKERS: self._prep_tickers(self.asset_currencies, tickers),
            CONF_BALANCES: balances_dict,
            DATA_TOTAL_BASE_ASSET: self._prep_total_base_asset(balances_dict),
            CONF_OPEN_ORDERS: open_orders,
            DATA_STAKING: staking,
            DATA_FEES: account.get("fees", {}) if isinstance(account, dict) else {},
        }

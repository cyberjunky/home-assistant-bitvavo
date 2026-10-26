"""Fixtures for the Bitvavo tests."""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bitvavo.const import CONF_API_SECRET, CONF_MARKETS, DOMAIN

PRICE_TICKER = [
    {"market": "BTC-EUR", "price": "50000"},
    {"market": "ETH-EUR", "price": "2000"},
    {"market": "USDC-EUR", "price": "0.9"},
    {"market": "ETH-BTC", "price": "0.04"},
    {"market": "EURC-EUR", "price": "1"},
]
TICKER_24H = [
    {
        "market": "BTC-EUR",
        "open": "40000",
        "high": "51000",
        "low": "39000",
        "last": "50000",
        "volume": "100",
        "volumeQuote": "5000000",
        "bid": "49999",
        "bidSize": "1",
        "ask": "50001",
        "askSize": "2",
    },
]
MARKETS = [
    {"market": "BTC-EUR", "status": "trading", "base": "BTC", "quote": "EUR", "tickSize": "1.00"},
    {
        "market": "ETH-BTC",
        "status": "trading",
        "base": "ETH",
        "quote": "BTC",
        "tickSize": "0.00001",
    },
]
BALANCES = [
    {"symbol": "EUR", "available": "100", "inOrder": "0"},
    {"symbol": "BTC", "available": "0.5", "inOrder": "0.5"},
    {"symbol": "EURC", "available": "10", "inOrder": "0"},
]
OPEN_ORDERS = [
    {
        "orderId": "1",
        "market": "BTC-EUR",
        "side": "buy",
        "orderType": "limit",
        "amount": "1",
        "price": "1",
    },
    {
        "orderId": "2",
        "market": "BTC-EUR",
        "side": "sell",
        "orderType": "limit",
        "amount": "1",
        "price": "9",
    },
    {
        "orderId": "3",
        "market": "ETH-EUR",
        "side": "sell",
        "orderType": "limit",
        "amount": "1",
        "price": "9",
    },
]
STAKING = [{"symbol": "BTC", "amount": "0.25"}, {"symbol": "ETH", "amount": "2"}]
ACCOUNT = {"fees": {"taker": "0.0025", "maker": "0.0015", "volume": "1000.00"}}

ENTRY_DATA = {
    "api_key": "key",
    CONF_API_SECRET: "secret",
    CONF_MARKETS: ["BTC-EUR", "ETH-BTC"],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Mock the Bitvavo client in both setup and the config flow."""
    with (
        patch("custom_components.bitvavo.BitvavoClient", autospec=True) as client_cls,
        patch("custom_components.bitvavo.config_flow.BitvavoClient", new=client_cls),
    ):
        client = client_cls.return_value
        client.rate_limit_remaining = 900
        client.get_price_ticker.return_value = deepcopy(PRICE_TICKER)
        client.get_24h_price_ticker.return_value = deepcopy(TICKER_24H)
        client.get_markets.return_value = deepcopy(MARKETS)
        client.get_balance.return_value = deepcopy(BALANCES)
        client.get_open_orders.return_value = deepcopy(OPEN_ORDERS)
        client.get_staking_balance.return_value = deepcopy(STAKING)
        client.get_account.return_value = deepcopy(ACCOUNT)
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up the entry from the config flow."""
    with patch("custom_components.bitvavo.async_setup_entry", return_value=True) as mock:
        yield mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bitvavo",
        data=dict(ENTRY_DATA),
        version=1,
        minor_version=2,
    )


def balances_with(**symbols: Any) -> list[dict[str, Any]]:
    """Return balance data for the given symbols and amounts."""
    return [
        {"symbol": symbol, "available": amount, "inOrder": "0"}
        for symbol, amount in symbols.items()
    ]

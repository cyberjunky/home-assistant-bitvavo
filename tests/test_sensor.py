"""Tests for the Bitvavo sensors."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from bitvavo.BitvavoExceptions import BitvavoConnectionError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.bitvavo.const import SCAN_INTERVAL

from .conftest import balances_with


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_ticker(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    state = hass.states.get("sensor.bitvavo_ticker_btc_eur")
    assert state.state == "50000.0"
    assert state.name == "Bitvavo Ticker - BTC-EUR"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"
    assert state.attributes["bid_price"] == "49999"
    assert state.attributes["high_24h"] == "51000"
    assert state.attributes["market_status"] == "trading"
    assert state.attributes["attribution"] == "Data provided by Bitvavo.com"

    # ETH-BTC has no 24h data in the fixture but is still shown from the price ticker
    assert hass.states.get("sensor.bitvavo_ticker_eth_btc").state == "0.04"


async def test_ticker_precision(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    entry = entity_registry.async_get("sensor.bitvavo_ticker_eth_btc")
    assert entry.options["sensor"]["suggested_display_precision"] == 5


async def test_change_24h(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    state = hass.states.get("sensor.bitvavo_change_24h_btc_eur")
    assert state.state == "25.0"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "%"
    # No 24h stats available
    assert hass.states.get("sensor.bitvavo_change_24h_eth_btc").state == "unknown"


async def test_balances(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    btc = hass.states.get("sensor.bitvavo_balance_btc")
    assert btc.state == "1.0"
    assert btc.attributes["staked"] == 0.25
    assert btc.attributes["value_eur"] == 50000.0
    assert btc.attributes["in order"] == "0.5"
    assert hass.states.get("sensor.bitvavo_balance_eur").state == "100.0"
    # EURC must not be treated as the EUR base asset (value comes from its own pair)
    assert hass.states.get("sensor.bitvavo_balance_eurc").attributes["value_eur"] == 10.0


async def test_total_asset_value(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    # 100 EUR + 1 BTC * 50000 + 10 EURC * 1
    assert hass.states.get("sensor.bitvavo_total_asset_value_eur").state == "50110.0"
    assert hass.states.get("sensor.bitvavo_total_asset_value_btc").state == "1.0022"
    assert float(hass.states.get("sensor.bitvavo_total_asset_value_usdc").state) == pytest.approx(
        50110 / 0.9
    )


async def test_open_orders(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    state = hass.states.get("sensor.bitvavo_open_orders")
    assert state.state == "3"
    assert state.attributes["buy orders"] == 1
    assert state.attributes["sell orders"] == 2
    assert len(state.attributes["orders"]) == 3


async def test_fee_sensors_disabled_by_default(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    entry = entity_registry.async_get("sensor.bitvavo_taker_fee")
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.bitvavo_taker_fee") is None


async def test_new_balance_added_and_sold_balance_is_zero(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    assert hass.states.get("sensor.bitvavo_balance_eth") is None

    # Sold all BTC (Bitvavo no longer returns it) and bought ETH
    mock_client.get_balance.return_value = balances_with(EUR="10", ETH="2")
    await _tick(hass, freezer, SCAN_INTERVAL)

    assert hass.states.get("sensor.bitvavo_balance_eth").state == "2.0"
    assert hass.states.get("sensor.bitvavo_balance_btc").state == "0.0"
    # 10 EUR + 2 ETH * 2000
    assert hass.states.get("sensor.bitvavo_total_asset_value_eur").state == "4010.0"


async def test_halted_market_unavailable(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.get_price_ticker.return_value = [{"market": "BTC-EUR", "price": "1"}]
    await _tick(hass, freezer, SCAN_INTERVAL)
    assert hass.states.get("sensor.bitvavo_ticker_eth_btc").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bitvavo_ticker_btc_eur").state == "1.0"


async def test_update_failure_marks_unavailable(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.get_price_ticker.side_effect = BitvavoConnectionError("down")
    await _tick(hass, freezer, SCAN_INTERVAL)
    assert hass.states.get("sensor.bitvavo_ticker_btc_eur").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bitvavo_balance_btc").state == STATE_UNAVAILABLE


async def test_expensive_calls_are_throttled(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _tick(hass, freezer, SCAN_INTERVAL)
    assert mock_client.get_price_ticker.call_count == 2
    assert mock_client.get_open_orders.call_count == 1
    assert mock_client.get_markets.call_count == 1

    await _tick(hass, freezer, timedelta(seconds=60))
    assert mock_client.get_open_orders.call_count == 2
    assert mock_client.get_markets.call_count == 1


async def test_staking_failure_is_ignored(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    mock_client.get_staking_balance.side_effect = BitvavoConnectionError("nope")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bitvavo_balance_btc").attributes["staked"] == 0.0

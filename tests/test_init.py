"""Tests for setting up the Bitvavo integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

from bitvavo.BitvavoExceptions import BitvavoAuthError, BitvavoConnectionError
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bitvavo.const import DOMAIN

from .conftest import ENTRY_DATA


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_connection_error(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    mock_client.get_price_ticker.side_effect = BitvavoConnectionError("down")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_error_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    mock_client.get_balance.side_effect = BitvavoAuthError(403, {"errorCode": 305})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH


async def test_migrate_unique_ids(
    hass: HomeAssistant, mock_client: AsyncMock, entity_registry: er.EntityRegistry
) -> None:
    """Old versions created unique ids with a trailing ')'."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(ENTRY_DATA), version=1, minor_version=1)
    entry.add_to_hass(hass)
    ticker = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "bitvavo_ticker_BTC-EUR)",
        config_entry=entry,
        suggested_object_id="bitvavo_ticker_btc_eur",
    )
    balance = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "bitvavo_balance_BTC)",
        config_entry=entry,
        suggested_object_id="my_btc",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert entity_registry.async_get(ticker.entity_id).unique_id == "bitvavo_ticker_BTC-EUR"
    assert entity_registry.async_get(balance.entity_id).unique_id == "bitvavo_balance_BTC"
    # Entity ids are kept and no duplicates were created
    assert hass.states.get("sensor.my_btc").state == "1.25"
    assert hass.states.get("sensor.bitvavo_balance_btc") is None
    assert hass.states.get("sensor.bitvavo_ticker_btc_eur").state == "50000.0"

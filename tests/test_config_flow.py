"""Tests for the Bitvavo config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from bitvavo.BitvavoExceptions import BitvavoAuthError, BitvavoConnectionError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bitvavo.const import CONF_MARKETS, CONF_SHOW_EMPTY_ASSETS, DOMAIN

from .conftest import ENTRY_DATA

USER_INPUT = {"api_key": "key", "api_secret": "secret"}


async def test_user_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_setup_entry: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "markets"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MARKETS: ["BTC-EUR"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bitvavo"
    assert result["data"] == {**USER_INPUT, CONF_MARKETS: ["BTC-EUR"]}
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (BitvavoAuthError(403, {"errorCode": 309, "error": "bad"}), "invalid_auth"),
        (BitvavoConnectionError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_setup_entry: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    mock_client.get_balance.side_effect = exception
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    # Recovers after the error is fixed
    mock_client.get_balance.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "markets"


async def test_single_instance(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reauth_flow(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_client.get_balance.side_effect = BitvavoAuthError(403, {"errorCode": 305})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "new", "api_secret": "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.get_balance.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "new", "api_secret": "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == "new"
    assert config_entry.data["api_secret"] == "new-secret"
    assert config_entry.data[CONF_MARKETS] == ENTRY_DATA[CONF_MARKETS]


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MARKETS: ["ETH-EUR"]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_MARKETS] == ["ETH-EUR"]
    assert config_entry.data["api_key"] == "key"

    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_reconfigure_flow_cannot_connect(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_client.get_balance.side_effect = BitvavoConnectionError("down")
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_options_flow_reloads(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bitvavo_balance_eurc") is not None

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"
    mock_client.get_balance.return_value = [
        {"symbol": "EUR", "available": "0", "inOrder": "0"},
        {"symbol": "BTC", "available": "1", "inOrder": "0"},
    ]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SHOW_EMPTY_ASSETS: False}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SHOW_EMPTY_ASSETS: False}
    # Entry was reloaded with the new option, the empty EUR balance gets no new data
    assert mock_client.get_balance.call_count == 2

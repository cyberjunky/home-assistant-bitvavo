"""Tests for the Bitvavo diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bitvavo.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, config_entry)
    assert result["entry"]["data"]["api_key"] == "**REDACTED**"
    assert result["entry"]["data"]["api_secret"] == "**REDACTED**"
    assert result["data"]["balances"]["BTC"]["available"] == "**REDACTED**"
    assert result["data"]["total_base_asset"] == "**REDACTED**"
    assert result["rate_limit_remaining"] == 900
    assert "'secret'" not in str(result)
    assert "'key'" not in str(result)

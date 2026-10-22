"""Diagnostics support for the Bitvavo integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .const import CONF_API_SECRET, DATA_TOTAL_BASE_ASSET
from .coordinator import BitvavoConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    CONF_API_SECRET,
    # Amounts and values of the account
    "available",
    "inOrder",
    "staked",
    "amount",
    "amountRemaining",
    "amountQuote",
    "amountQuoteRemaining",
    "filledAmount",
    "filledAmountQuote",
    "onHold",
    "asset_value_in_base_asset",
    DATA_TOTAL_BASE_ASSET,
    "volume",
    "orderId",
    "clientOrderId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BitvavoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    client = coordinator.client

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "version": f"{entry.version}.{entry.minor_version}",
        },
        "rate_limit_remaining": client.rate_limit_remaining,
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }

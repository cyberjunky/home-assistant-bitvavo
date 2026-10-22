"""Gather the market details from Bitvavo."""

from __future__ import annotations

import inspect
import logging
from typing import Any

from bitvavo.BitvavoClient import BitvavoClient
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_SECRET, PLATFORMS, REQUEST_TIMEOUT
from .coordinator import BitvavoConfigEntry, BitvavoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

__all__ = ["BitvavoConfigEntry", "BitvavoDataUpdateCoordinator"]


async def async_setup_entry(hass: HomeAssistant, entry: BitvavoConfigEntry) -> bool:
    """Set up Bitvavo from a config entry."""
    client = BitvavoClient(
        entry.data[CONF_API_KEY],
        entry.data[CONF_API_SECRET],
        session=async_get_clientsession(hass),
        timeout=REQUEST_TIMEOUT,
    )

    coordinator = BitvavoDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: BitvavoConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BitvavoConfigEntry) -> bool:
    """Unload Bitvavo config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: BitvavoConfigEntry) -> bool:
    """Migrate old config entries."""
    _LOGGER.debug("Migrating from version %s.%s", entry.version, entry.minor_version)

    if entry.version > 1:
        # Downgraded from a future version
        return False

    if entry.minor_version < 2:
        # Versions <= 1.0.6 created unique ids with a stray ")" such as
        # "bitvavo_ticker_BTC-EUR)". Strip it while keeping the entity ids.
        ent_reg = er.async_get(hass)

        @callback
        def _fix_unique_id(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
            unique_id = entity_entry.unique_id
            if not unique_id.endswith(")"):
                return None
            new_unique_id = unique_id.removesuffix(")")
            if ent_reg.async_get_entity_id(
                entity_entry.domain, entity_entry.platform, new_unique_id
            ):
                _LOGGER.warning(
                    "Cannot migrate unique id of %s, %s already exists",
                    entity_entry.entity_id,
                    new_unique_id,
                )
                return None
            return {"new_unique_id": new_unique_id}

        await er.async_migrate_entries(hass, entry.entry_id, _fix_unique_id)
        _async_set_statistics_units(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)

    _LOGGER.debug("Migration to version %s.%s successful", entry.version, entry.minor_version)
    return True


def _unit_from_unique_id(unique_id: str) -> str | None:
    """Return the unit a sensor reports since version 1.1.0, based on its unique id."""
    if unique_id.startswith("bitvavo_ticker_"):
        # The quote currency of the market, e.g. EUR for BTC-EUR
        return unique_id.removeprefix("bitvavo_ticker_").partition("-")[2] or None
    if unique_id.startswith("bitvavo_balance_"):
        return unique_id.removeprefix("bitvavo_balance_")
    if unique_id.startswith("bitvavo_total_asset_value_"):
        return unique_id.removeprefix("bitvavo_total_asset_value_").upper()
    return None


@callback
def _async_set_statistics_units(hass: HomeAssistant, entry: BitvavoConfigEntry) -> None:
    """Set the unit of existing long term statistics.

    Versions <= 1.0.6 set the unit the wrong way, so Home Assistant recorded the
    sensors without a unit. Label the existing statistics with the (unchanged)
    currency so history continues without a "unit changed" repair issue.
    """
    if "recorder" not in hass.config.components:
        return

    from homeassistant.components.recorder import get_instance

    recorder = get_instance(hass)
    # Home Assistant 2025.10+ only updates the unit together with the unit class.
    # Currencies have no unit converter, so their unit class is None.
    extra: dict[str, Any] = {}
    if "new_unit_class" in inspect.signature(recorder.async_update_statistics_metadata).parameters:
        extra["new_unit_class"] = None

    for entity_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if entity_entry.domain != "sensor":
            continue
        if (unit := _unit_from_unique_id(entity_entry.unique_id)) is None:
            continue
        recorder.async_update_statistics_metadata(
            entity_entry.entity_id, new_unit_of_measurement=unit, **extra
        )

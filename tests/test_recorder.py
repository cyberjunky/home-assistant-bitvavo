"""Tests for the migration of long term statistics."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.models import StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics, get_metadata
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.bitvavo.const import DOMAIN

from .conftest import ENTRY_DATA


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """Enable custom integrations, the recorder must be set up before hass."""


async def test_migrate_statistics_units(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Statistics recorded without a unit by old versions get the currency unit."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(ENTRY_DATA), version=1, minor_version=1)
    entry.add_to_hass(hass)
    for unique_id, object_id in (
        ("bitvavo_ticker_BTC-EUR)", "bitvavo_ticker_btc_eur"),
        ("bitvavo_total_asset_value_btc", "bitvavo_total_asset_value_btc"),
        ("bitvavo_orders_open", "bitvavo_open_orders"),
    ):
        entity_registry.async_get_or_create(
            "sensor", DOMAIN, unique_id, config_entry=entry, suggested_object_id=object_id
        )

    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    for statistic_id in ("sensor.bitvavo_ticker_btc_eur", "sensor.bitvavo_total_asset_value_btc"):
        metadata: dict[str, Any] = {
            "has_mean": True,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": statistic_id,
            "unit_of_measurement": None,
        }
        if "mean_type" in StatisticMetaData.__annotations__:
            metadata["mean_type"] = 1  # StatisticMeanType.ARITHMETIC
            metadata["unit_class"] = None
        async_import_statistics(
            hass, metadata, [{"start": start, "mean": 1.0, "min": 1.0, "max": 1.0}]
        )
    await async_wait_recording_done(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    metadata_by_id = await recorder_mock.async_add_executor_job(
        get_metadata,
        hass,
    )
    assert metadata_by_id["sensor.bitvavo_ticker_btc_eur"][1]["unit_of_measurement"] == "EUR"
    assert metadata_by_id["sensor.bitvavo_total_asset_value_btc"][1]["unit_of_measurement"] == "BTC"
    assert (
        hass.states.get("sensor.bitvavo_ticker_btc_eur").attributes["unit_of_measurement"] == "EUR"
    )

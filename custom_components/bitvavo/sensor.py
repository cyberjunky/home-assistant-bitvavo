"""Sensor for the Bitvavo integration."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ASSET_VALUE_BASE,
    ASSET_VALUE_CURRENCIES,
    CONF_ASSET_TICKERS,
    CONF_BALANCES,
    CONF_MARKETS,
    CONF_OPEN_ORDERS,
    CONF_TICKERS,
    CURRENCY_ICONS,
    DATA_FEES,
    DATA_TOTAL_BASE_ASSET,
    DEFAULT_COIN_ICON,
    FIAT_LIKE_CURRENCIES,
)
from .coordinator import BitvavoConfigEntry, BitvavoDataUpdateCoordinator
from .entity import BitvavoEntity

# Coordinator data is shared, entities do no I/O
PARALLEL_UPDATES = 0

# Maximum number of orders listed in the open orders attributes
MAX_LISTED_ORDERS = 25


def _to_float(value: Any) -> float | None:
    """Convert an API string value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _currency_precision(currency: str | None) -> int:
    """Return a sensible display precision for an amount in a currency."""
    return 2 if currency in FIAT_LIKE_CURRENCIES else 8


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitvavoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bitvavo sensors."""
    coordinator = entry.runtime_data
    markets: list[str] = entry.data.get(CONF_MARKETS, [])

    entities: list[SensorEntity] = []
    for market in markets:
        entities.append(Ticker(coordinator, market))
        entities.append(TickerChange24h(coordinator, market))

    entities.extend(TotalAssetValue(coordinator, currency) for currency in ASSET_VALUE_CURRENCIES)
    entities.append(OpenOrders(coordinator))
    entities.extend(TradingFee(coordinator, fee_type) for fee_type in ("maker", "taker"))

    async_add_entities(entities)

    # Balances come and go when assets are bought or sold, add new ones on the fly
    known_balances: set[str] = set()

    @callback
    def _async_add_new_balances() -> None:
        new_balances = [
            symbol
            for symbol in coordinator.data.get(CONF_BALANCES, {})
            if symbol not in known_balances
        ]
        if new_balances:
            known_balances.update(new_balances)
            async_add_entities(Balance(coordinator, symbol) for symbol in new_balances)

    _async_add_new_balances()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_balances))


class _MarketSensor(BitvavoEntity, SensorEntity):
    """Base class for sensors of a single market such as BTC-EUR."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, symbol: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._symbol = symbol
        self._base, _, self._quote = symbol.partition("-")
        self._attr_translation_placeholders = {"market": symbol}

    @property
    def _ticker(self) -> dict[str, Any]:
        """Return the ticker data of this market (empty when not trading)."""
        ticker: dict[str, Any] = self.coordinator.data.get(CONF_TICKERS, {}).get(self._symbol, {})
        return ticker

    @property
    def available(self) -> bool:
        """Return if the market is trading and has a price."""
        return super().available and _to_float(self._ticker.get("price")) is not None


class Ticker(_MarketSensor):
    """Implementation of the ticker sensor."""

    _attr_translation_key = "ticker"

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, symbol: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, symbol)
        self._attr_icon = CURRENCY_ICONS.get(self._quote, DEFAULT_COIN_ICON)
        self._attr_native_unit_of_measurement = self._quote
        self._attr_unique_id = f"bitvavo_ticker_{symbol}"

    @property
    def suggested_display_precision(self) -> int:
        """Determine display precision from Bitvavo tickSize."""
        tick_size = self._ticker.get("tickSize")

        try:
            size = Decimal(str(tick_size))
            if not size.is_finite() or size <= 0:
                return 4
            return max(0, -int(size.normalize().as_tuple().exponent))
        except (InvalidOperation, TypeError, ValueError):
            return 4

    @property
    def native_value(self) -> float | None:
        """Return the ticker price without rounding."""
        return _to_float(self._ticker.get("price"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        ticker = self._ticker
        return {
            "symbol": self._symbol,
            "bid_price": ticker.get("bid"),
            "ask_price": ticker.get("ask"),
            "bid_size": ticker.get("bidSize"),
            "ask_size": ticker.get("askSize"),
            "currency": ticker.get("base", self._base),
            "quote_asset": ticker.get("quote", self._quote),
            "open_24h": ticker.get("open"),
            "high_24h": ticker.get("high"),
            "low_24h": ticker.get("low"),
            "volume_24h": ticker.get("volume"),
            "volume_quote_24h": ticker.get("volumeQuote"),
            "market_status": ticker.get("status"),
        }


class TickerChange24h(_MarketSensor):
    """Price change of a market over the last 24 hours."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 2
    _attr_translation_key = "change_24h"

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, symbol: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, symbol)
        self._attr_unique_id = f"bitvavo_change_24h_{symbol}"

    @property
    def native_value(self) -> float | None:
        """Return the 24h change in percent."""
        last = _to_float(self._ticker.get("price"))
        opened = _to_float(self._ticker.get("open"))
        if last is None or not opened:
            return None
        return round((last - opened) / opened * 100, 4)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "symbol": self._symbol,
            "open_24h": self._ticker.get("open"),
            "last": self._ticker.get("price"),
        }


class Balance(BitvavoEntity, SensorEntity):
    """Implementation of the balance sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "balance"

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, balance: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._balance = balance

        self._attr_icon = CURRENCY_ICONS.get(balance, DEFAULT_COIN_ICON)
        self._attr_native_unit_of_measurement = balance
        self._attr_suggested_display_precision = _currency_precision(balance)
        self._attr_unique_id = f"bitvavo_balance_{balance}"
        self._attr_translation_placeholders = {"symbol": balance}

    @property
    def _data(self) -> dict[str, Any]:
        """Return the balance data; empty once the asset is sold completely."""
        data: dict[str, Any] = self.coordinator.data.get(CONF_BALANCES, {}).get(self._balance, {})
        return data

    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        return (
            (_to_float(self._data.get("available")) or 0.0)
            + (_to_float(self._data.get("inOrder")) or 0.0)
            + (_to_float(self._data.get("staked")) or 0.0)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        value = self._data.get("asset_value_in_base_asset")
        return {
            "available": self._data.get("available", "0"),
            "in order": self._data.get("inOrder", "0"),
            "staked": self._data.get("staked", 0.0),
            f"value_{ASSET_VALUE_BASE.lower()}": round(value, 2) if value is not None else None,
        }


class OpenOrders(BitvavoEntity, SensorEntity):
    """Implementation of the open orders sensor."""

    _attr_icon = "mdi:format-list-bulleted"
    _attr_translation_key = "open_orders"
    _attr_unique_id = "bitvavo_orders_open"
    _unrecorded_attributes = frozenset({"orders"})

    @property
    def _orders(self) -> list[dict[str, Any]]:
        """Return the open orders."""
        orders: list[dict[str, Any]] = self.coordinator.data.get(CONF_OPEN_ORDERS, [])
        return orders

    def _type_orders(self, side: str) -> int:
        """Return the number of orders per type."""
        return sum(1 for order in self._orders if order.get("side") == side)

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return len(self._orders)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "buy orders": self._type_orders("buy"),
            "sell orders": self._type_orders("sell"),
            "orders": [
                {
                    "market": order.get("market"),
                    "side": order.get("side"),
                    "type": order.get("orderType"),
                    "status": order.get("status"),
                    "amount": order.get("amount"),
                    "amount_remaining": order.get("amountRemaining"),
                    "price": order.get("price"),
                    "trigger_price": order.get("triggerPrice"),
                }
                for order in self._orders[:MAX_LISTED_ORDERS]
            ],
        }


class TotalAssetValue(BitvavoEntity, SensorEntity):
    """Implementation of the total asset value sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "total_asset_value"

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, currency: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._currency = currency

        self._attr_icon = CURRENCY_ICONS.get(currency, DEFAULT_COIN_ICON)
        self._attr_native_unit_of_measurement = currency
        self._attr_suggested_display_precision = _currency_precision(currency)
        self._attr_unique_id = f"bitvavo_total_asset_value_{currency.lower()}"
        self._attr_translation_placeholders = {"currency": currency.upper()}
        self._attr_extra_state_attributes = {
            "note": (
                f"Value is based on the last {currency}-{ASSET_VALUE_BASE} price "
                "of all coins in balance"
            ),
        }

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        total_base_asset_value = float(self.coordinator.data.get(DATA_TOTAL_BASE_ASSET, 0.0))

        if self._currency == ASSET_VALUE_BASE:
            return round(total_base_asset_value, 4)

        asset_value_pair_name = f"{self._currency}-{ASSET_VALUE_BASE}".upper()
        last_price = _to_float(
            self.coordinator.data.get(CONF_ASSET_TICKERS, {})
            .get(asset_value_pair_name, {})
            .get("price")
        )
        if not last_price:
            return None

        return round(total_base_asset_value / last_price, 8)


class TradingFee(BitvavoEntity, SensorEntity):
    """Current maker or taker fee of the account."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator, fee_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._fee_type = fee_type
        self._attr_translation_key = f"{fee_type}_fee"
        self._attr_unique_id = f"bitvavo_{fee_type}_fee"

    @property
    def native_value(self) -> float | None:
        """Return the fee in percent."""
        fee = _to_float(self.coordinator.data.get(DATA_FEES, {}).get(self._fee_type))
        return round(fee * 100, 4) if fee is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {"volume_30d": self.coordinator.data.get(DATA_FEES, {}).get("volume")}

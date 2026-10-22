"""Constants for the Bitvavo integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "bitvavo"

# Config
CONF_API_SECRET = "api_secret"

CONF_BALANCES = "balances"
CONF_MARKETS = "markets"
CONF_OPEN_ORDERS = "open_orders"
CONF_TICKERS = "tickers"
CONF_ASSET_TICKERS = "asset_tickers"
CONF_SHOW_EMPTY_ASSETS = "show_empty_assets"

# Coordinator data keys
DATA_TOTAL_BASE_ASSET = "total_base_asset"
DATA_FEES = "fees"
DATA_STAKING = "staking"

PLATFORMS = [Platform.SENSOR]

# Currency
CURRENCY_ICONS = {
    "BTC": "mdi:currency-btc",
    "ETH": "mdi:currency-eth",
    "EUR": "mdi:currency-eur",
    "LTC": "mdi:litecoin",
    "USDC": "mdi:currency-usd",
}

DEFAULT_COIN_ICON = "mdi:currency-usd"

ASSET_VALUE_CURRENCIES = {"USDC", "EUR", "BTC"}
ASSET_VALUE_BASE = "EUR"
# Currencies shown with 2 decimals, everything else with 8
FIAT_LIKE_CURRENCIES = {"EUR", "USDC"}
ATTRIBUTION = "Data provided by Bitvavo.com"

# Setup
SCAN_INTERVAL = timedelta(seconds=20)
# Slower moving or expensive (rate limit weight) data is refreshed less often.
# /ordersOpen costs 100 of the 1000 weight per minute budget, /markets and
# /account/fees rarely change.
MARKETS_REFRESH_INTERVAL = timedelta(hours=1)
OPEN_ORDERS_REFRESH_INTERVAL = timedelta(seconds=60)
STAKING_REFRESH_INTERVAL = timedelta(minutes=5)
FEES_REFRESH_INTERVAL = timedelta(hours=1)
REQUEST_TIMEOUT = 15

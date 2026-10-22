# Changelog

## 1.1.0

Requires `bitvavo-aio` 1.1.0. Existing installations keep their entities, entity ids and history.

### Added
- 24h change sensor per market and 24h open/high/low/volume and market status attributes on tickers
- Staked amount and EUR value attributes on balance sensors
- Order list attribute on the open orders sensor
- Maker/taker fee sensors (diagnostic, disabled by default)
- Balance sensors for newly bought assets are added automatically
- Re-authentication flow when Bitvavo rejects the API key
- Reconfigure flow to change the tracked markets
- Diagnostics download (API key, secret and amounts redacted)
- Dev container, linting, tests, dependabot and HACS validation

### Fixed
- Ticker, balance and open order attributes never updated after startup
- Balance sensors failed after an asset was sold completely, they now report 0
- Assets such as `EURC` were valued as if they were euros
- Invalid `enum` device class on balance and total asset value sensors
- Sensors showed no unit (EUR, BTC, ...) because it was set the wrong way, and overrode `state` instead of `native_value`. Existing long term statistics are relabelled with the unit automatically, values are unchanged
- Unique ids contained a stray `)`; they are migrated automatically
- The options flow used the deprecated way of storing the config entry and changes did not reload the integration
- Missing translation for unexpected errors and no "cannot connect" error in the config flow
- The API client created its own HTTP session that was never closed, it now uses the Home Assistant session and a request timeout
- API errors are reported as update failures instead of unexpected exceptions

### Changed
- Open orders refresh every minute instead of every 20 seconds, Bitvavo now charges 100 rate limit weight for that call
- Market details and fees are cached for an hour
- Uses `entry.runtime_data`, a coordinator module, a shared base entity, entity name translations and `single_config_entry`

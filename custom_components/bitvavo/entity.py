"""Base entity for the Bitvavo integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import BitvavoDataUpdateCoordinator


class BitvavoEntity(CoordinatorEntity[BitvavoDataUpdateCoordinator]):
    """Base class for Bitvavo entities."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: BitvavoDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        # Register all Bitvavo entities under one device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Bitvavo",
            manufacturer="Bitvavo",
            model="Crypto Exchange",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://account.bitvavo.com/user/api",
        )

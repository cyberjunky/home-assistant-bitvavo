"""Errors for the Bitvavo integration."""

from homeassistant.exceptions import HomeAssistantError


class BitvavoError(HomeAssistantError):
    """Base class for Bitvavo exceptions."""


class InvalidAuth(BitvavoError):
    """Error to indicate there is invalid auth."""


class CannotConnect(BitvavoError):
    """Error to indicate the API cannot be reached or returned an error."""


# Kept for backwards compatibility
BitvavoException = BitvavoError
InvalidResponse = CannotConnect

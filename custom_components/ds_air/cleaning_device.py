"""Shared Home Assistant device info for DS-AIR self-cleaning controls."""

from .const import DOMAIN

CLEANING_DEVICE_UID = "heat_exchange_cleaning"


def cleaning_device_info():
    """Return the virtual DS-AIR self-cleaning device."""
    return {
        "identifiers": {(DOMAIN, CLEANING_DEVICE_UID)},
        "name": "DS-AIR 自清洁",
        "manufacturer": "Daikin Industries, Ltd.",
    }

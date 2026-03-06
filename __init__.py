"""Anova Precision Cooker Mini - BLE Custom Integration."""
from __future__ import annotations

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .anova_ble import AnovaMiniClient

DOMAIN = "anova_mini"
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Anova Mini from a config entry."""
    address: str = entry.data["address"]

    ble_device = async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"Could not find Anova Mini BLE device at {address}. "
            "Make sure the device is powered on and in range."
        )

    client = AnovaMiniClient(ble_device)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"client": client}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        client = data.get("client")
        if client:
            await client.disconnect()
    return unloaded

"""Select entity for Anova Precision Cooker Mini timer mode."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

TIMER_MODE_KEY = "timer_mode"
TIMER_MODE_HOLD = "Hold Temperature"
TIMER_MODE_FOLLOW = "Stop When Done"
TIMER_MODE_OPTIONS = [TIMER_MODE_HOLD, TIMER_MODE_FOLLOW]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data[DOMAIN][entry.entry_id][TIMER_MODE_KEY] = TIMER_MODE_HOLD
    device_info = {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Anova Precision Cooker Mini",
        "manufacturer": "Anova Culinary",
        "model": "Precision Cooker Mini",
    }
    async_add_entities([AnovaMiniTimerMode(entry, device_info)], False)


class AnovaMiniTimerMode(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Timer Mode"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_options = TIMER_MODE_OPTIONS

    def __init__(self, entry: ConfigEntry, device_info: dict) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_timer_mode"
        self._attr_device_info = device_info
        self._attr_current_option = TIMER_MODE_HOLD

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.hass.data[DOMAIN][self._entry.entry_id][TIMER_MODE_KEY] = option
        _LOGGER.info("Timer mode set to: %s", option)
        self.async_write_ha_state()

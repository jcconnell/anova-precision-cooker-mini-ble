"""Number entities for Anova Precision Cooker Mini cook timer (hours + minutes)."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

TIMER_HOURS_KEY = "timer_hours"
TIMER_MINUTES_KEY = "timer_minutes"

DEVICE_INFO = {
    "manufacturer": "Anova Culinary",
    "model": "Precision Cooker Mini",
}


def get_timer_seconds(hass_data: dict) -> int:
    """Return total timer duration in seconds from shared data."""
    hours = int(hass_data.get(TIMER_HOURS_KEY, 0))
    minutes = int(hass_data.get(TIMER_MINUTES_KEY, 0))
    return (hours * 3600) + (minutes * 60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hass.data[DOMAIN][entry.entry_id][TIMER_HOURS_KEY] = 1
    hass.data[DOMAIN][entry.entry_id][TIMER_MINUTES_KEY] = 30
    device_info = {
        **DEVICE_INFO,
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Anova Precision Cooker Mini",
    }
    async_add_entities([
        AnovaMiniTimerHours(entry, device_info),
        AnovaMiniTimerMinutes(entry, device_info),
    ], False)


class _AnovaMiniTimerBase(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES  # overridden per subclass
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_icon = "mdi:timer-outline"
    _data_key: str = ""

    def __init__(self, entry: ConfigEntry, device_info: dict) -> None:
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_native_value = 1.0  # overridden per subclass

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.hass.data[DOMAIN][self._entry.entry_id][self._data_key] = int(value)
        total = get_timer_seconds(self.hass.data[DOMAIN][self._entry.entry_id])
        _LOGGER.debug(
            "Timer updated: %s=%d → total=%ds",
            self._data_key, int(value), total,
        )
        self.async_write_ha_state()


class AnovaMiniTimerHours(_AnovaMiniTimerBase):
    _attr_name = "Cook Timer Hours"
    _attr_native_max_value = 999
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _data_key = TIMER_HOURS_KEY

    def __init__(self, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_timer_hours"
        self._attr_native_value = 1.0


class AnovaMiniTimerMinutes(_AnovaMiniTimerBase):
    _attr_name = "Cook Timer Minutes"
    _attr_native_max_value = 59
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _data_key = TIMER_MINUTES_KEY

    def __init__(self, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_timer_minutes"
        self._attr_native_value = 30.0

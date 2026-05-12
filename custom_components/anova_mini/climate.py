"""Climate entity for Anova Precision Cooker Mini."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import AnovaMiniCoordinator
from .number import get_timer_seconds

_LOGGER = logging.getLogger(__name__)

MIN_TEMP_F = 41.0
MAX_TEMP_F = 210.0
COMMAND_LOCK_SECS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnovaMiniCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([AnovaMiniClimate(coordinator, entry)], False)


class AnovaMiniClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Anova Precision Cooker Mini",
            "manufacturer": "Anova Culinary",
            "model": "Precision Cooker Mini",
        }
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_current_temperature: float | None = None
        self._attr_target_temperature: float | None = 135.0  # °F
        self._command_time: datetime | None = None

    def _command_pending(self) -> bool:
        if self._command_time is None:
            return False
        return (datetime.now(timezone.utc) - self._command_time).total_seconds() < COMMAND_LOCK_SECS

    def _mark_command(self) -> None:
        self._command_time = datetime.now(timezone.utc)

    def _handle_coordinator_update(self) -> None:
        # Don't overwrite optimistic state during a command window
        if self._command_pending():
            self.async_write_ha_state()
            return

        data = self.coordinator.data
        if data is None:
            self.async_write_ha_state()
            return

        current_c = data.get("current_temperature")
        if current_c:
            self._attr_current_temperature = round(float(current_c) * 9 / 5 + 32, 1)

        setpoint_c = data.get("target_temperature")
        if setpoint_c is not None:
            self._attr_target_temperature = round(float(setpoint_c) * 9 / 5 + 32, 1)

        self.async_write_ha_state()

    async def _ensure_connected(self) -> None:
        client = self.coordinator.client
        if not client.is_connected:
            if not await client.connect():
                raise HomeAssistantError("Cannot reach Anova Mini — device is offline")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """User-initiated on/off. hvac_mode is ONLY ever changed here, never by polls."""
        self._mark_command()
        await self._ensure_connected()

        client = self.coordinator.client
        if hvac_mode == HVACMode.HEAT:
            setpoint_f = self._attr_target_temperature or 135.0
            setpoint_c = round((setpoint_f - 32) * 5 / 9, 2)
            timer_seconds = get_timer_seconds(self.hass.data[DOMAIN][self._entry_id])
            _LOGGER.info("Starting cook: %.1f°F → %.2f°C, timer=%ds", setpoint_f, setpoint_c, timer_seconds)
            await client.start_cook(setpoint_c, timer_seconds)
        else:
            _LOGGER.info("Stopping cook")
            await client.stop_cook()

        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        self._mark_command()
        self._attr_target_temperature = temp

        await self._ensure_connected()
        client = self.coordinator.client

        temp_c = round((temp - 32) * 5 / 9, 2)
        await client.set_temperature(temp_c)

        # Re-issue start to update the running setpoint if already cooking
        if self._attr_hvac_mode == HVACMode.HEAT:
            timer_seconds = get_timer_seconds(self.hass.data[DOMAIN][self._entry_id])
            await client.start_cook(temp_c, timer_seconds)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

"""Climate entity for Anova Precision Cooker Mini."""
from __future__ import annotations

import asyncio
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .anova_ble import AnovaMiniClient
from . import DOMAIN
from .number import get_timer_seconds

_LOGGER = logging.getLogger(__name__)

MIN_TEMP_F = 41.0
MAX_TEMP_F = 210.0
POLL_INTERVAL = 30
COMMAND_LOCK_SECS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: AnovaMiniClient = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([AnovaMiniClimate(client, entry)], True)


class AnovaMiniClimate(ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_target_temperature_step = 0.5

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry) -> None:
        self._client = client
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
        self._poll_task: asyncio.Task | None = None
        self._command_time: datetime | None = None

    def _command_pending(self) -> bool:
        if self._command_time is None:
            return False
        return (datetime.now(timezone.utc) - self._command_time).total_seconds() < COMMAND_LOCK_SECS

    def _mark_command(self) -> None:
        self._command_time = datetime.now(timezone.utc)

    async def async_added_to_hass(self) -> None:
        self._poll_task = self.hass.loop.create_task(self._startup())

    async def _startup(self) -> None:
        """Delayed startup: let HA register the entity, then connect and read temps only."""
        await asyncio.sleep(5)
        await self._poll_temperatures()
        self.async_write_ha_state()
        self._poll_task = self.hass.loop.create_task(self._poll_loop())

    async def async_will_remove_from_hass(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        await self._client.disconnect()

    async def _poll_temperatures(self) -> None:
        """Read temperatures from device using get_full_state(). Never touches hvac_mode."""
        try:
            if not self._client.is_connected:
                if not await self._client.connect():
                    return

            # get_full_state merges STATE + CURRENT_TEMP + TIMER in one logical read
            full = await self._client.get_full_state()

            current_temp_c = full.get("currentTemperature")
            if current_temp_c:
                self._attr_current_temperature = round(float(current_temp_c) * 9 / 5 + 32, 1)

            # Setpoint lives in CHAR_SET_TEMPERATURE, not STATE
            setpoint_c = await self._client.get_setpoint()
            if setpoint_c is not None:
                self._attr_target_temperature = round(setpoint_c * 9 / 5 + 32, 1)

            _LOGGER.info(
                "Poll: current=%.1f°F target=%.1f°F | mode=%s | full_state=%s",
                self._attr_current_temperature or 0,
                self._attr_target_temperature or 0,
                full.get("mode") or full.get("state"),
                full,
            )
        except Exception as err:
            _LOGGER.warning("Temperature poll failed: %s", err)
            await self._client.disconnect()

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            if self.entity_id is None:
                continue
            if self._command_pending():
                _LOGGER.debug("Skipping poll — within command lock window")
                continue
            await self._poll_temperatures()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """User-initiated on/off. hvac_mode is ONLY ever changed here, never by polls."""
        self._mark_command()

        if not self._client.is_connected:
            if not await self._client.connect():
                _LOGGER.error("Cannot set HVAC mode — device not reachable")
                return

        if hvac_mode == HVACMode.HEAT:
            setpoint_f = self._attr_target_temperature or 135.0
            setpoint_c = round((setpoint_f - 32) * 5 / 9, 2)
            timer_seconds = get_timer_seconds(self.hass.data[DOMAIN][self._entry_id])
            _LOGGER.info("Starting cook: %.1f°F → %.2f°C, timer=%ds", setpoint_f, setpoint_c, timer_seconds)
            await self._client.start_cook(setpoint_c, timer_seconds)
        else:
            _LOGGER.info("Stopping cook")
            await self._client.stop_cook()

        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        self._mark_command()
        self._attr_target_temperature = temp

        if not self._client.is_connected:
            if not await self._client.connect():
                _LOGGER.error("Cannot set temperature — device not reachable")
                return

        temp_c = round((temp - 32) * 5 / 9, 2)
        await self._client.set_temperature(temp_c)

        # If already cooking, re-issue start to update the running setpoint
        if self._attr_hvac_mode == HVACMode.HEAT:
            timer_seconds = get_timer_seconds(self.hass.data[DOMAIN][self._entry_id])
            await self._client.start_cook(temp_c, timer_seconds)

        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Called by HA update coordinator — only poll temps, never hvac_mode."""
        if not self._command_pending() and self.entity_id is not None:
            await self._poll_temperatures()

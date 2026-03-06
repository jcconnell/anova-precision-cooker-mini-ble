"""Sensor entities for Anova Precision Cooker Mini."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .anova_ble import AnovaMiniClient
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Cook states the device can report
COOK_STATES = ["idle", "cooking", "preheating", "heating", "low water", "error"]


def _device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Anova Precision Cooker Mini",
        "manufacturer": "Anova Culinary",
        "model": "Precision Cooker Mini",
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: AnovaMiniClient = hass.data[DOMAIN][entry.entry_id]["client"]
    di = _device_info(entry)

    # Patch device_info with system_info once available
    fw = client.system_info.get("firmwareVersion")
    sn = client.system_info.get("serialNumber")
    if fw:
        di["sw_version"] = fw
    if sn:
        di["serial_number"] = sn

    async_add_entities([
        AnovaMiniTempSensor(client, entry, di),
        AnovaMiniStateSensor(client, entry, di),
        AnovaMiniTargetTempSensor(client, entry, di),
        AnovaMiniTimerRemainingSensor(client, entry, di),
        AnovaMiniFirmwareSensor(client, entry, di),
    ], update_before_add=False)


class AnovaMiniTempSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Current Temperature"
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry, device_info: dict) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_current_temp"
        self._attr_device_info = device_info

    async def async_update(self) -> None:
        if self._client.is_connected:
            self._attr_native_value = await self._client.get_current_temperature()


class AnovaMiniTargetTempSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Target Temperature"
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry, device_info: dict) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_target_temp"
        self._attr_device_info = device_info

    async def async_update(self) -> None:
        if self._client.is_connected:
            try:
                # Setpoint lives in CHAR_SET_TEMPERATURE, not STATE
                raw = await self._client.get_setpoint()
                if raw is not None:
                    self._attr_native_value = float(raw)
                    _LOGGER.info("Target temp: %.2f°C", float(raw))
                else:
                    _LOGGER.warning("No setpoint returned from device")
            except Exception as e:
                _LOGGER.warning("Target temp read failed: %s", e)


class AnovaMiniStateSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Cook State"
    _attr_icon = "mdi:pot-steam"

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry, device_info: dict) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_cook_state"
        self._attr_device_info = device_info

    async def async_update(self) -> None:
        if not self._client.is_connected:
            self._attr_native_value = "disconnected"
            return
        try:
            # get_full_state merges STATE + CURRENT_TEMP + TIMER
            full = await self._client.get_full_state()
            # Device returns "mode" (e.g. "cook") not "state"
            raw_state = (full.get("mode") or full.get("state") or "unknown").lower().strip()
            # Ensure we never set None or empty string — HA treats those as "unknown"
            self._attr_native_value = raw_state if raw_state else "unknown"
            # Keep all fields as attributes for debugging, including mode
            self._attr_extra_state_attributes = dict(full)
            _LOGGER.info("Cook state set to: %r | full_state: %s", raw_state, full)
        except Exception as e:
            _LOGGER.warning("Could not read cook state: %s", e)
            self._attr_native_value = "unavailable"


class AnovaMiniTimerRemainingSensor(SensorEntity):
    """
    Timer remaining sensor. The device does not provide a live countdown —
    it returns {mode: idle|running|completed, initial: <seconds>}.
    We compute remaining = initial - elapsed, tracked from when mode first
    became 'running'.
    """
    _attr_has_entity_name = True
    _attr_name = "Timer Remaining"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer"

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry, device_info: dict) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_timer_remaining"
        self._attr_device_info = device_info
        self._timer_start: float | None = None   # monotonic time when running started
        self._timer_initial: int = 0             # initial seconds from device
        self._last_mode: str = "idle"

    async def async_update(self) -> None:
        if not self._client.is_connected:
            return
        try:
            import time
            timer_data = await self._client.get_timer()
            mode = timer_data.get("mode", "idle").lower()
            initial = int(timer_data.get("initial", 0))

            if mode == "running":
                if self._last_mode != "running" or initial != self._timer_initial:
                    # Timer just started or was reset — record start time
                    self._timer_start = time.monotonic()
                    self._timer_initial = initial
                elapsed = int(time.monotonic() - self._timer_start) if self._timer_start else 0
                remaining_secs = max(0, self._timer_initial - elapsed)
                self._attr_native_value = round(remaining_secs / 60, 1)
            elif mode == "completed":
                self._attr_native_value = 0
                self._timer_start = None
            else:
                # idle — no timer set or cleared
                self._timer_start = None
                self._timer_initial = initial
                self._attr_native_value = round(initial / 60, 1) if initial else 0

            self._last_mode = mode
            self._attr_extra_state_attributes = {
                "mode": mode,
                "initial_minutes": round(initial / 60, 1) if initial else 0,
            }
            _LOGGER.debug("Timer: mode=%s initial=%ds remaining=%.1fmin",
                         mode, initial, self._attr_native_value or 0)
        except Exception as e:
            _LOGGER.debug("Could not read timer: %s", e)


class AnovaMiniFirmwareSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Firmware Version"
    _attr_icon = "mdi:chip"
    _attr_entity_registry_enabled_default = False  # hidden by default, diagnostic use

    def __init__(self, client: AnovaMiniClient, entry: ConfigEntry, device_info: dict) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_firmware"
        self._attr_device_info = device_info
        # Set from cached system_info immediately — no poll needed
        self._attr_native_value = client.system_info.get("firmwareVersion", "unknown")
        self._attr_extra_state_attributes = {
            k: v for k, v in client.system_info.items()
            if k != "firmwareVersion"
        }

    async def async_update(self) -> None:
        # Only re-read if we don't have it yet
        if self._attr_native_value == "unknown" and self._client.is_connected:
            try:
                info = await self._client.get_system_info()
                self._client.system_info = info
                self._attr_native_value = info.get("firmwareVersion", "unknown")
                self._attr_extra_state_attributes = {
                    k: v for k, v in info.items() if k != "firmwareVersion"
                }
            except Exception as e:
                _LOGGER.debug("Could not read system info: %s", e)

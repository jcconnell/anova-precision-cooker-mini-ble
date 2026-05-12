"""Sensor entities for Anova Precision Cooker Mini."""
from __future__ import annotations

import logging
import time

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import AnovaMiniCoordinator

_LOGGER = logging.getLogger(__name__)


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
    coordinator: AnovaMiniCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    di = _device_info(entry)

    # Patch device_info with system_info once available
    system_info = coordinator.client.system_info
    if fw := system_info.get("firmwareVersion"):
        di["sw_version"] = fw
    if sn := system_info.get("serialNumber"):
        di["serial_number"] = sn

    async_add_entities([
        AnovaMiniTempSensor(coordinator, entry, di),
        AnovaMiniStateSensor(coordinator, entry, di),
        AnovaMiniTargetTempSensor(coordinator, entry, di),
        AnovaMiniTimerRemainingSensor(coordinator, entry, di),
        AnovaMiniFirmwareSensor(coordinator, entry, di),
    ], False)


class AnovaMiniTempSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Current Temperature"
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_temp"
        self._attr_device_info = device_info

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            current_c = data.get("current_temperature")
            self._attr_native_value = float(current_c) if current_c else None
        self.async_write_ha_state()


class AnovaMiniTargetTempSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Target Temperature"
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_target_temp"
        self._attr_device_info = device_info

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            raw = data.get("target_temperature")
            self._attr_native_value = float(raw) if raw is not None else None
        self.async_write_ha_state()


class AnovaMiniStateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Cook State"
    _attr_icon = "mdi:pot-steam"

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_cook_state"
        self._attr_device_info = device_info

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is None:
            self._attr_native_value = "disconnected"
        else:
            self._attr_native_value = data.get("mode") or "unknown"
            self._attr_extra_state_attributes = dict(data.get("full_state", {}))
        self.async_write_ha_state()


class AnovaMiniTimerRemainingSensor(CoordinatorEntity, SensorEntity):
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

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_timer_remaining"
        self._attr_device_info = device_info
        self._timer_start: float | None = None
        self._timer_initial: int = 0
        self._last_mode: str = "idle"

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is None:
            self.async_write_ha_state()
            return

        timer_data = data.get("timer", {})
        mode = timer_data.get("mode", "idle").lower()
        initial = int(timer_data.get("initial", 0))

        if mode == "running":
            if self._last_mode != "running" or initial != self._timer_initial:
                self._timer_start = time.monotonic()
                self._timer_initial = initial
            elapsed = int(time.monotonic() - self._timer_start) if self._timer_start else 0
            remaining_secs = max(0, self._timer_initial - elapsed)
            self._attr_native_value = round(remaining_secs / 60, 1)
        elif mode == "completed":
            self._attr_native_value = 0
            self._timer_start = None
        else:
            self._timer_start = None
            self._timer_initial = initial
            self._attr_native_value = round(initial / 60, 1) if initial else 0

        self._last_mode = mode
        self._attr_extra_state_attributes = {
            "mode": mode,
            "initial_minutes": round(initial / 60, 1) if initial else 0,
        }
        self.async_write_ha_state()


class AnovaMiniFirmwareSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Firmware Version"
    _attr_icon = "mdi:chip"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: AnovaMiniCoordinator, entry: ConfigEntry, device_info: dict) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_firmware"
        self._attr_device_info = device_info
        self._attr_native_value = coordinator.client.system_info.get("firmwareVersion", "unknown")

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            info = data.get("system_info", {})
            self._attr_native_value = info.get("firmwareVersion", self._attr_native_value)
            self._attr_extra_state_attributes = {
                k: v for k, v in info.items() if k != "firmwareVersion"
            }
        self.async_write_ha_state()

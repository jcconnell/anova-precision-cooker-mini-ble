"""Anova Mini Gen3 BLE protocol client — based on official developer reference."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

SERVICE_UUID         = "910772a8-a5e7-49a7-bc6d-701e9a783a5c"
CHAR_SET_TEMPERATURE = "0f5639f7-3c4e-47d0-9496-0672c89ea48a"
CHAR_CURRENT_TEMP    = "6ffdca46-d6a8-4fb2-8fd9-c6330f1939e3"
CHAR_TIMER           = "a2b179f8-944e-436f-a246-c66caaf7061f"
CHAR_STATE           = "54e53c60-367a-4783-a5c1-b1770c54142b"
CHAR_SET_CLOCK       = "d8a89692-cae8-4b74-96e3-0b99d3637793"
CHAR_SYSTEM_INFO     = "153c9432-7c83-4b88-9252-7588229d5473"

CONNECT_TIMEOUT  = 20.0
READ_TIMEOUT     = 10.0


def _encode(payload: dict) -> bytes:
    return base64.b64encode(json.dumps(payload).encode("utf-8"))


def _decode(data: bytes | bytearray) -> dict:
    try:
        return json.loads(base64.b64decode(data).decode("utf-8"))
    except Exception as e:
        _LOGGER.error("BLE decode error: %s | raw=%s", e, data)
        return {}


class AnovaMiniClient:
    def __init__(self, ble_device: BLEDevice) -> None:
        self._device = ble_device
        self._client: BleakClient | None = None
        self.reported_unit: str = "C"
        self.system_info: dict = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        try:
            self._client = BleakClient(
                self._device,
                timeout=CONNECT_TIMEOUT,
                disconnected_callback=self._on_disconnect,
            )
            await self._client.connect()
            _LOGGER.info("Connected to Anova Mini %s", self._device.address)

            # Set clock immediately on connect (required by protocol)
            await self._set_clock()

            # Cache system info once per connection
            try:
                self.system_info = await self._read(CHAR_SYSTEM_INFO)
                _LOGGER.debug("System info: %s", self.system_info)
            except Exception as e:
                _LOGGER.warning("Could not read system info: %s", e)

            # Read initial state to get temperature unit
            try:
                state = await self._read(CHAR_STATE)
                self.reported_unit = state.get("temperatureUnit", "C").upper()
                _LOGGER.debug("Device state on connect: %s", state)
            except Exception as e:
                _LOGGER.warning("Could not read initial state: %s", e)

            return True
        except Exception as err:
            _LOGGER.error("Connection failed: %s", err)
            self._client = None
            return False

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    def _on_disconnect(self, client: BleakClient) -> None:
        _LOGGER.warning("Anova Mini disconnected unexpectedly")
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Low-level BLE read/write
    # Use response=False for writes — matches official reference implementation
    # ------------------------------------------------------------------

    async def _write(self, char_uuid: str, payload: dict) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        data = _encode(payload)
        _LOGGER.debug("BLE WRITE -> %s: %s", char_uuid[-8:], payload)
        try:
            await asyncio.wait_for(
                self._client.write_gatt_char(char_uuid, data, response=False),
                timeout=READ_TIMEOUT,
            )
        except asyncio.TimeoutError:
            _LOGGER.error("BLE WRITE TIMEOUT -> %s", char_uuid[-8:])
            raise
        except Exception as e:
            _LOGGER.error("BLE WRITE FAILED -> %s: %s", char_uuid[-8:], e)
            raise

    async def _read(self, char_uuid: str) -> dict:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        try:
            raw = await asyncio.wait_for(
                self._client.read_gatt_char(char_uuid),
                timeout=READ_TIMEOUT,
            )
            decoded = _decode(raw)
            _LOGGER.debug("BLE READ <- %s: %s", char_uuid[-8:], decoded)
            return decoded
        except asyncio.TimeoutError:
            _LOGGER.error("BLE READ TIMEOUT <- %s", char_uuid[-8:])
            raise
        except Exception as e:
            _LOGGER.error("BLE READ FAILED <- %s: %s", char_uuid[-8:], e)
            raise

    # ------------------------------------------------------------------
    # Protocol commands — matching official reference exactly
    # ------------------------------------------------------------------

    async def _set_clock(self) -> None:
        # Match official format: remove microseconds, use isoformat
        now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        await self._write(CHAR_SET_CLOCK, {"currentTime": now_utc})
        _LOGGER.info("Clock set to %s", now_utc)

    async def set_unit(self, unit: str) -> None:
        """Change device temperature unit. unit should be 'C' or 'F'."""
        await self._write(CHAR_STATE, {
            "command": "changeUnit",
            "payload": {"temperatureUnit": unit.upper()},
        })

    async def get_system_info(self) -> dict[str, Any]:
        return await self._read(CHAR_SYSTEM_INFO)

    async def get_state(self) -> dict[str, Any]:
        data = await self._read(CHAR_STATE)
        self.reported_unit = data.get("temperatureUnit", self.reported_unit).upper()
        return data

    async def get_current_temperature(self) -> float | None:
        try:
            data = await self._read(CHAR_CURRENT_TEMP)
            raw = data.get("current")
            if raw is None:
                return None
            val = float(raw)
            return val if val != 0.0 else None
        except Exception as err:
            _LOGGER.warning("Could not read current temp: %s", err)
            return None

    async def get_timer(self) -> dict:
        try:
            return await self._read(CHAR_TIMER)
        except Exception as e:
            _LOGGER.warning("Could not read timer: %s", e)
            return {"running": False, "remaining": 0}

    async def get_full_state(self) -> dict[str, Any]:
        """
        Merge STATE + CURRENT_TEMPERATURE + TIMER into one dict.
        Matches the official get_full_state() pattern.
        """
        state_data = await self.get_state()
        temp_data = await self._read(CHAR_CURRENT_TEMP)
        timer_data = await self.get_timer()

        state_data["currentTemperature"] = temp_data.get("current", 0)
        state_data["timer"] = timer_data

        _LOGGER.info("Full state: %s", state_data)
        return state_data

    async def get_setpoint(self) -> float | None:
        """Read current target setpoint from CHAR_SET_TEMPERATURE."""
        try:
            data = await self._read(CHAR_SET_TEMPERATURE)
            raw = data.get("setpoint")
            return float(raw) if raw is not None else None
        except Exception as e:
            _LOGGER.warning("Could not read setpoint: %s", e)
            return None

    async def set_temperature(self, setpoint: float) -> None:
        await self._write(CHAR_SET_TEMPERATURE, {"setpoint": round(setpoint, 1)})

    async def start_cook(self, setpoint: float, timer_seconds: int = 0) -> None:
        sp = round(setpoint, 1)
        _LOGGER.info("start_cook: setpoint=%.1f°C timer=%ds", sp, timer_seconds)
        # Official reference writes SET_TEMPERATURE first, then STATE
        await self._write(CHAR_SET_TEMPERATURE, {"setpoint": sp})
        await self._write(CHAR_STATE, {
            "command": "start",
            "payload": {
                "setpoint": sp,
                "timer": timer_seconds,
                "cookableId": "recipe123",   # matches official reference
                "cookableType": "recipe",    # matches official reference
            },
        })
        # Read back full state to confirm transition and log
        await asyncio.sleep(1.0)
        try:
            full = await self.get_full_state()
            _LOGGER.info("Full state after start_cook: %s", full)
        except Exception as e:
            _LOGGER.warning("Could not read state after start_cook: %s", e)

    async def stop_cook(self) -> None:
        _LOGGER.info("stop_cook")
        await self._write(CHAR_STATE, {"command": "stop"})
        await asyncio.sleep(1.0)
        try:
            full = await self.get_full_state()
            _LOGGER.info("Full state after stop_cook: %s", full)
        except Exception as e:
            _LOGGER.warning("Could not read state after stop_cook: %s", e)

"""DataUpdateCoordinator for Anova Mini BLE."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .anova_ble import AnovaMiniClient

_LOGGER = logging.getLogger(__name__)

NORMAL_INTERVAL = timedelta(seconds=30)
BACKOFF_INTERVAL = timedelta(minutes=5)
BACKOFF_AFTER_FAILURES = 5


class AnovaMiniCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: AnovaMiniClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Anova Mini",
            update_interval=NORMAL_INTERVAL,
        )
        self._client = client
        self._consecutive_failures = 0
        self._backoff_until: datetime | None = None

    @property
    def client(self) -> AnovaMiniClient:
        return self._client

    async def _async_update_data(self) -> dict:
        if self._backoff_until and datetime.now(timezone.utc) < self._backoff_until:
            remaining = int((self._backoff_until - datetime.now(timezone.utc)).total_seconds())
            _LOGGER.debug("Skipping BLE fetch — in backoff (%ds remaining)", remaining)
            raise UpdateFailed("Device offline — in backoff period")

        try:
            if not self._client.is_connected:
                if not await self._client.connect():
                    raise UpdateFailed("Cannot connect to device")

            full = await self._client.get_full_state()
            setpoint = await self._client.get_setpoint()

            self._consecutive_failures = 0
            self._backoff_until = None

            return {
                "current_temperature": full.get("currentTemperature"),
                "target_temperature": setpoint,
                "mode": (full.get("mode") or full.get("state") or "unknown").lower().strip(),
                "timer": full.get("timer", {}),
                "system_info": self._client.system_info,
                "full_state": full,
            }
        except UpdateFailed:
            raise
        except Exception as err:
            await self._client.disconnect()
            self._consecutive_failures += 1
            if self._consecutive_failures >= BACKOFF_AFTER_FAILURES:
                self._backoff_until = datetime.now(timezone.utc) + BACKOFF_INTERVAL
                _LOGGER.warning(
                    "Anova Mini unreachable after %d consecutive failures — "
                    "backing off for %s",
                    self._consecutive_failures,
                    BACKOFF_INTERVAL,
                )
            raise UpdateFailed(f"BLE fetch failed: {err}") from err

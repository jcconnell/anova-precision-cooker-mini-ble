"""Config flow for Anova Precision Cooker Mini."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_scanner_count,
)
from homeassistant.data_entry_flow import FlowResult

from .anova_ble import SERVICE_UUID
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_ADDRESS = "address"
MANUAL_MAC = "manual_mac"


class AnovaMiniConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Anova Mini."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}
        self._address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle BLE auto-discovery (triggered by manifest service UUID filter)."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_confirm()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup — collect MAC directly or pick from cache."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS) or user_input.get(MANUAL_MAC, "").strip().upper()
            if not address:
                errors["base"] = "no_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                self._address = address
                return self.async_create_entry(
                    title="Anova Precision Cooker Mini",
                    data={CONF_ADDRESS: self._address},
                )

        # Check passive cache first (may already have the device)
        current_ids = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            if info.address in current_ids:
                continue
            if SERVICE_UUID.lower() in [u.lower() for u in (info.service_uuids or [])]:
                self._discovered[info.address] = info

        # Build schema — offer dropdown if we found devices, otherwise free-text MAC
        if self._discovered:
            choices = {
                addr: f"{info.name or 'Anova Mini'} ({addr})"
                for addr, info in self._discovered.items()
            }
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)})
            description = "Select your Anova Mini from the list below."
        else:
            schema = vol.Schema({vol.Required(MANUAL_MAC): str})
            description = (
                "No Anova Mini found in BLE cache yet. "
                "Make sure the device is powered on and your BLE proxy is running, "
                "then enter the MAC address manually (e.g. F8:64:65:16:C4:2E)."
            )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"description": description},
            errors=errors,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm auto-discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title="Anova Precision Cooker Mini",
                data={CONF_ADDRESS: self._address},
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"address": self._address},
        )

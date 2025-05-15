"""Config flow for IR Remote integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    DEFAULT_CLUSTER_ID,
    DEFAULT_ENDPOINT_ID,
    ERROR_NO_DEVICE,
    ERROR_NO_ZHA,
)

_LOGGER = logging.getLogger(__name__)


async def get_zha_devices(hass: HomeAssistant) -> dict[str, str]:
    """Get ZHA devices list."""
    _LOGGER.debug("Getting ZHA devices")
    
    try:
        # Call zha_toolkit service
        result = await hass.services.async_call(
            "zha_toolkit",
            "zha_devices",
            {},
            blocking=True,
            return_response=True
        )
        
        if not result:
            _LOGGER.error("No response from zha_toolkit")
            return {}

        devices = {}
        for device in result.get("devices", []):
            ieee = device.get("ieee")
            device_name = (
                device.get("user_given_name") or 
                device.get("model") or 
                device.get("name", "Unknown Device")
            )
            devices[ieee] = f"{device_name} ({ieee})"
            _LOGGER.debug("Found device: %s", device_name)

        return devices

    except Exception as e:
        _LOGGER.error("Error getting ZHA devices: %s", e)
        return {}


class IRRemoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IR Remote."""

    VERSION = 1
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step - device selection."""
        errors = {}

        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Get ZHA devices
        zha_devices = await get_zha_devices(self.hass)
        if not zha_devices:
            return self.async_abort(reason=ERROR_NO_ZHA)

        if user_input is not None:
            self.data[CONF_IEEE] = user_input[CONF_IEEE]
            # Move to next step
            return await self.async_step_clusters()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IEEE): vol.In(zha_devices)
            }),
            errors=errors
        )

    async def async_step_clusters(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle cluster configuration."""
        errors = {}

        if user_input is not None:
            # Save configuration
            self.data.update(user_input)
            return self.async_create_entry(
                title="IR Remote",
                data=self.data
            )

        return self.async_show_form(
            step_id="clusters",
            data_schema=vol.Schema({
                vol.Required(CONF_ENDPOINT, default=DEFAULT_ENDPOINT_ID): cv.positive_int,
                vol.Required(CONF_CLUSTER, default=DEFAULT_CLUSTER_ID): cv.positive_int,
            }),
            errors=errors
        )
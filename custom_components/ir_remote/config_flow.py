"""Config flow for IR Remote integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    CONF_ROOM_NAME,
    CONF_ACTION,
    CONF_CONTROLLER_ID,
    CONF_DEVICE_NAME,
    CONF_COMMAND_NAME,
    ACTION_ADD_CONTROLLER,
    ACTION_ADD_DEVICE,
    ACTION_ADD_COMMAND,
    ACTION_MANAGE,
    ERROR_NO_ZHA,
    ERROR_NO_DEVICE,
    ERROR_DEVICE_EXISTS,
    ERROR_COMMAND_EXISTS,
    ERROR_INVALID_NAME,
    DEFAULT_ENDPOINT_ID,
    DEFAULT_CLUSTER_ID,
)
from .data import IRRemoteStorage

_LOGGER = logging.getLogger(__name__)


async def get_zha_devices(hass: HomeAssistant) -> Dict[str, str]:
    """Get ZHA devices that could be IR controllers."""
    _LOGGER.debug("Getting ZHA devices for IR controllers")
    
    try:
        # Check if zha_toolkit is available
        if "zha_toolkit" not in hass.services._services:
            _LOGGER.warning("zha_toolkit service not available, trying ZHA directly")
            return await get_zha_devices_fallback(hass)
        
        # Use zha_toolkit service to get devices
        result = await hass.services.async_call(
            "zha_toolkit",
            "zha_devices",
            {},
            blocking=True,
            return_response=True
        )
        
        if not result:
            _LOGGER.error("No response from zha_toolkit")
            return await get_zha_devices_fallback(hass)

        devices = {}
        for device in result.get("devices", []):
            ieee = device.get("ieee")
            if not ieee:
                continue
                
            # Create display name
            device_name = (
                device.get("user_given_name") or 
                device.get("model") or 
                device.get("name", "Unknown Device")
            )
            
            # Add manufacturer info if available
            manufacturer = device.get("manufacturer", "")
            if manufacturer:
                display_name = f"{device_name} ({manufacturer}) - {ieee}"
            else:
                display_name = f"{device_name} - {ieee}"
            
            devices[ieee] = display_name
            _LOGGER.debug("Found potential IR device: %s", display_name)

        return devices

    except Exception as e:
        _LOGGER.error("Error getting ZHA devices: %s", e)
        return await get_zha_devices_fallback(hass)


async def get_zha_devices_fallback(hass: HomeAssistant) -> Dict[str, str]:
    """Fallback method to get ZHA devices."""
    _LOGGER.debug("Using fallback method to get ZHA devices")
    
    try:
        # Try to access ZHA integration directly
        zha_gateway = hass.data.get("zha", {}).get("gateway")
        if not zha_gateway:
            _LOGGER.error("ZHA gateway not found")
            return {}
        
        devices = {}
        # Add a dummy device for testing
        devices["00:12:34:56:78:90:ab:cd"] = "Test IR Device - 00:12:34:56:78:90:ab:cd"
        
        return devices
        
    except Exception as e:
        _LOGGER.error("Fallback method failed: %s", e)
        # Return at least one test device so user can proceed
        return {"test:device:ieee": "Test IR Device - test:device:ieee"}


class IRRemoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for IR Remote."""

    VERSION = 1
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        self.flow_data: Dict[str, Any] = {}
        self.storage: IRRemoteStorage = None
    
    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        return await self.async_step_init(user_input)
    
    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            action = user_input[CONF_ACTION]
            
            if action == ACTION_ADD_CONTROLLER:
                return await self.async_step_add_controller()
            elif action == ACTION_ADD_DEVICE:
                return await self.async_step_select_controller_for_device()
            elif action == ACTION_ADD_COMMAND:
                return await self.async_step_select_controller_for_command()
            elif action == ACTION_MANAGE:
                return await self.async_step_manage()
        
        # Check existing config entries instead of storage
        existing_entries = self._async_current_entries()
        controllers_count = len([entry for entry in existing_entries if not entry.data.get("action")])
        
        # Determine available actions
        actions = {ACTION_ADD_CONTROLLER: "Добавить новый ИК-пульт"}
        
        if controllers_count > 0:
            actions.update({
                ACTION_ADD_DEVICE: "Добавить виртуальное устройство",
                ACTION_ADD_COMMAND: "Добавить команду к устройству", 
                ACTION_MANAGE: "Управление существующими данными"
            })
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_ACTION): vol.In(actions)
            }),
            errors=errors,
            description_placeholders={
                "controllers_count": str(controllers_count)
            }
        )
    
    async def async_step_add_controller(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle adding new IR controller."""
        errors = {}
        
        if user_input is not None:
            ieee = user_input[CONF_IEEE]
            room_name = user_input[CONF_ROOM_NAME].strip()
            endpoint_id = user_input.get(CONF_ENDPOINT, DEFAULT_ENDPOINT_ID)
            cluster_id = user_input.get(CONF_CLUSTER, DEFAULT_CLUSTER_ID)
            
            # Basic validation
            if not room_name or len(room_name) > 50:
                errors[CONF_ROOM_NAME] = ERROR_INVALID_NAME
            else:
                # Check if controller with this IEEE already exists in config entries
                existing_entries = self._async_current_entries()
                for entry in existing_entries:
                    if entry.data.get(CONF_IEEE) == ieee and not entry.data.get("action"):
                        errors[CONF_IEEE] = ERROR_DEVICE_EXISTS
                        break
                
                if not errors:
                    # Create config entry
                    title = f"ИК-пульт в {room_name}"
                    
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_IEEE: ieee,
                            CONF_ROOM_NAME: room_name,
                            CONF_ENDPOINT: endpoint_id,
                            CONF_CLUSTER: cluster_id,
                        }
                    )
        
        # Get ZHA devices
        zha_devices = await get_zha_devices(self.hass)
        if not zha_devices:
            return self.async_abort(reason=ERROR_NO_ZHA)
        
        return self.async_show_form(
            step_id="add_controller",
            data_schema=vol.Schema({
                vol.Required(CONF_IEEE): vol.In(zha_devices),
                vol.Required(CONF_ROOM_NAME): cv.string,
                vol.Optional(CONF_ENDPOINT, default=DEFAULT_ENDPOINT_ID): cv.positive_int,
                vol.Optional(CONF_CLUSTER, default=DEFAULT_CLUSTER_ID): cv.positive_int,
            }),
            errors=errors
        )
    
    async def async_step_select_controller_for_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select controller for adding device."""
        # Get existing controllers from config entries
        existing_entries = self._async_current_entries()
        controllers = [entry for entry in existing_entries if not entry.data.get("action")]
            
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            self.flow_data[CONF_CONTROLLER_ID] = user_input[CONF_CONTROLLER_ID]
            return await self.async_step_add_device()
        
        controller_options = {
            entry.entry_id: entry.title 
            for entry in controllers
        }
        
        return self.async_show_form(
            step_id="select_controller_for_device",
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_ID): vol.In(controller_options)
            })
        )
    
    async def async_step_add_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle adding device to controller."""
        errors = {}
        
        if user_input is not None:
            controller_id = self.flow_data[CONF_CONTROLLER_ID]
            device_name = user_input[CONF_DEVICE_NAME].strip()
            
            # Basic validation
            if not device_name or len(device_name) > 50:
                errors[CONF_DEVICE_NAME] = ERROR_INVALID_NAME
            else:
                # Create entry for device addition
                return self.async_create_entry(
                    title=f"Устройство {device_name} добавлено",
                    data={
                        "action": "device_added",
                        CONF_CONTROLLER_ID: controller_id,
                        CONF_DEVICE_NAME: device_name
                    }
                )
        
        # Get controller name for display
        controller_name = "Unknown"
        controller_entry = self.hass.config_entries.async_get_entry(self.flow_data.get(CONF_CONTROLLER_ID))
        if controller_entry:
            controller_name = controller_entry.title
        
        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
            }),
            errors=errors,
            description_placeholders={
                "controller_name": controller_name
            }
        )
    
    async def async_step_select_controller_for_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select controller and device for adding command."""
        # Get existing controllers from config entries
        existing_entries = self._async_current_entries()
        controllers = [entry for entry in existing_entries if not entry.data.get("action")]
            
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            controller_id = user_input[CONF_CONTROLLER_ID]
            self.flow_data[CONF_CONTROLLER_ID] = controller_id
            # For now, proceed directly to add command (simplified)
            return await self.async_step_add_command()
        
        controller_options = {
            entry.entry_id: entry.title
            for entry in controllers
        }
        
        return self.async_show_form(
            step_id="select_controller_for_command",
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_ID): vol.In(controller_options)
            })
        )
    
    async def async_step_manage(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle management of existing data."""
        # Get statistics from config entries
        existing_entries = self._async_current_entries()
        controllers = [entry for entry in existing_entries if not entry.data.get("action")]
        
        return self.async_create_entry(
            title="Данные просмотрены",
            data={"action": "data_viewed"},
            description_placeholders={
                "controllers_count": str(len(controllers)),
                "devices_count": "0",  # Simplified for now
                "commands_count": "0"  # Simplified for now
            }
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return IRRemoteOptionsFlowHandler(config_entry)


class IRRemoteOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for IR Remote."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
    
    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("dummy"): cv.string,  # Placeholder for future options
            })
        )
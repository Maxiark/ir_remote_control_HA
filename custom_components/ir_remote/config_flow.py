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
    STEP_INIT,
    STEP_ADD_CONTROLLER,
    STEP_ADD_DEVICE,
    STEP_ADD_COMMAND,
    STEP_LEARN_COMMAND,
    STEP_MANAGE,
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
            return {}

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
        return {}


class IRRemoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for IR Remote."""

    VERSION = 1
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        self.flow_data: Dict[str, Any] = {}
        self.storage: IRRemoteStorage = None
    
    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        # Initialize storage
        if self.storage is None:
            self.storage = IRRemoteStorage(self.hass)
            await self.storage.async_load()
        
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
        
        # Get existing controllers for display
        controllers = self.storage.get_controllers()
        
        # Determine available actions
        actions = {ACTION_ADD_CONTROLLER: "Добавить новый ИК-пульт"}
        
        if controllers:
            actions.update({
                ACTION_ADD_DEVICE: "Добавить виртуальное устройство",
                ACTION_ADD_COMMAND: "Добавить команду к устройству", 
                ACTION_MANAGE: "Управление существующими данными"
            })
        
        return self.async_show_form(
            step_id=STEP_INIT,
            data_schema=vol.Schema({
                vol.Required(CONF_ACTION): vol.In(actions)
            }),
            errors=errors,
            description_placeholders={
                "controllers_count": str(len(controllers))
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
            
            # Validate room name
            if not self.storage._validate_name(room_name):
                errors[CONF_ROOM_NAME] = ERROR_INVALID_NAME
            else:
                # Check if controller with this IEEE already exists
                controllers = self.storage.get_controllers()
                for controller in controllers:
                    if controller["ieee"] == ieee:
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
            step_id=STEP_ADD_CONTROLLER,
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
        controllers = self.storage.get_controllers()
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            self.flow_data[CONF_CONTROLLER_ID] = user_input[CONF_CONTROLLER_ID]
            return await self.async_step_add_device()
        
        controller_options = {
            controller["id"]: controller["name"] 
            for controller in controllers
        }
        
        return self.async_show_form(
            step_id="select_controller",
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
            
            # Validate device name
            if not self.storage._validate_name(device_name):
                errors[CONF_DEVICE_NAME] = ERROR_INVALID_NAME
            else:
                # Generate device ID from name
                device_id = device_name.lower().replace(" ", "_").replace("-", "_")
                
                # Check if device already exists
                devices = self.storage.get_devices(controller_id)
                for device in devices:
                    if device["id"] == device_id:
                        errors[CONF_DEVICE_NAME] = ERROR_DEVICE_EXISTS
                        break
                
                if not errors:
                    # Add device
                    success = await self.storage.async_add_device(controller_id, device_id, device_name)
                    
                    if success:
                        return self.async_create_entry(
                            title=f"Устройство {device_name} добавлено",
                            data={}
                        )
                    else:
                        errors["base"] = "add_device_failed"
        
        controller = self.storage.get_controller(self.flow_data[CONF_CONTROLLER_ID])
        controller_name = controller["name"] if controller else "Unknown"
        
        return self.async_show_form(
            step_id=STEP_ADD_DEVICE,
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
        controllers = self.storage.get_controllers()
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            controller_id = user_input[CONF_CONTROLLER_ID]
            self.flow_data[CONF_CONTROLLER_ID] = controller_id
            
            # Get devices for this controller
            devices = self.storage.get_devices(controller_id)
            if not devices:
                return self.async_abort(reason="no_devices")
            
            # If only one device, auto-select it
            if len(devices) == 1:
                self.flow_data["device_id"] = devices[0]["id"]
                return await self.async_step_add_command()
            
            # Multiple devices - show selection
            return await self.async_step_select_device_for_command()
        
        controller_options = {
            controller["id"]: f"{controller['name']} ({controller['device_count']} устройств)"
            for controller in controllers
        }
        
        return self.async_show_form(
            step_id="select_controller_for_command",
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_ID): vol.In(controller_options)
            })
        )
    
    async def async_step_select_device_for_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select device for adding command."""
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_add_command()
        
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        devices = self.storage.get_devices(controller_id)
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices
        }
        
        return self.async_show_form(
            step_id="select_device_for_command",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(device_options)
            })
        )
    
    async def async_step_add_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle adding command to device."""
        errors = {}
        
        if user_input is not None:
            command_name = user_input[CONF_COMMAND_NAME].strip()
            
            # Validate command name
            if not self.storage._validate_name(command_name):
                errors[CONF_COMMAND_NAME] = ERROR_INVALID_NAME
            else:
                # Generate command ID from name
                command_id = command_name.lower().replace(" ", "_").replace("-", "_")
                
                # Check if command already exists
                controller_id = self.flow_data[CONF_CONTROLLER_ID]
                device_id = self.flow_data["device_id"]
                commands = self.storage.get_commands(controller_id, device_id)
                
                for command in commands:
                    if command["id"] == command_id:
                        errors[CONF_COMMAND_NAME] = ERROR_COMMAND_EXISTS
                        break
                
                if not errors:
                    # Store command info and proceed to learning
                    self.flow_data[CONF_COMMAND_NAME] = command_name
                    self.flow_data["command_id"] = command_id
                    return await self.async_step_learn_command()
        
        controller = self.storage.get_controller(self.flow_data[CONF_CONTROLLER_ID])
        device = self.storage.get_device(self.flow_data[CONF_CONTROLLER_ID], self.flow_data["device_id"])
        
        return self.async_show_form(
            step_id=STEP_ADD_COMMAND,
            data_schema=vol.Schema({
                vol.Required(CONF_COMMAND_NAME): cv.string,
            }),
            errors=errors,
            description_placeholders={
                "controller_name": controller["name"] if controller else "Unknown",
                "device_name": device["name"] if device else "Unknown"
            }
        )
    
    async def async_step_learn_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle IR learning process."""
        if user_input is not None:
            # User confirmed they're ready to learn
            # This would trigger the actual IR learning process
            # For now, we'll just complete the flow
            return self.async_create_entry(
                title=f"Команда {self.flow_data[CONF_COMMAND_NAME]} добавлена",
                data={
                    CONF_CONTROLLER_ID: self.flow_data[CONF_CONTROLLER_ID],
                    "device_id": self.flow_data["device_id"],
                    "command_id": self.flow_data["command_id"],
                    CONF_COMMAND_NAME: self.flow_data[CONF_COMMAND_NAME],
                    "learn_mode": True
                }
            )
        
        controller = self.storage.get_controller(self.flow_data[CONF_CONTROLLER_ID])
        device = self.storage.get_device(self.flow_data[CONF_CONTROLLER_ID], self.flow_data["device_id"])
        
        return self.async_show_form(
            step_id=STEP_LEARN_COMMAND,
            data_schema=vol.Schema({
                vol.Required("ready"): bool,
            }),
            description_placeholders={
                "controller_name": controller["name"] if controller else "Unknown",
                "device_name": device["name"] if device else "Unknown",
                "command_name": self.flow_data[CONF_COMMAND_NAME]
            }
        )
    
    async def async_step_manage(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle management of existing data."""
        # This could show statistics and options for bulk operations
        controllers = self.storage.get_controllers()
        
        total_devices = sum(controller["device_count"] for controller in controllers)
        total_commands = 0
        
        for controller in controllers:
            controller_id = controller["id"]
            devices = self.storage.get_devices(controller_id)
            for device in devices:
                device_id = device["id"]
                commands = self.storage.get_commands(controller_id, device_id)
                total_commands += len(commands)
        
        return self.async_create_entry(
            title="Данные просмотрены",
            data={},
            description_placeholders={
                "controllers_count": str(len(controllers)),
                "devices_count": str(total_devices),
                "commands_count": str(total_commands)
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
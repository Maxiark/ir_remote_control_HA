"""Config flow for IR Remote integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, device_registry as dr 


from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    CONF_ROOM_NAME,
    CONF_ACTION,
    CONF_CONTROLLER_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,  
    CONF_COMMAND_NAME,
    ACTION_ADD_CONTROLLER,
    ACTION_ADD_DEVICE,
    ACTION_ADD_COMMAND,
    ACTION_COPY,
    ACTION_REMOVE_DEVICE,                     
    ACTION_REMOVE_COMMAND,                    
    STEP_SELECT_CONTROLLER_FOR_REMOVE_DEVICE, 
    STEP_SELECT_DEVICE_FOR_REMOVE,            
    STEP_CONFIRM_REMOVE_DEVICE,               
    STEP_SELECT_CONTROLLER_FOR_REMOVE_COMMAND,
    STEP_SELECT_DEVICE_FOR_REMOVE_COMMAND,    
    STEP_SELECT_COMMAND_FOR_REMOVE,           
    STEP_CONFIRM_REMOVE_COMMAND,              
    ERROR_REMOVE_FAILED,
    STEP_INIT,
    STEP_ADD_CONTROLLER,
    STEP_ADD_DEVICE,
    STEP_SELECT_DEVICE_TYPE,  
    STEP_ADD_COMMAND,
    STEP_LEARN_COMMAND,

    STEP_COPY_SELECT_TYPE,
    STEP_COPY_SELECT_SOURCE_CONTROLLER,
    STEP_COPY_SELECT_SOURCE_DEVICE,
    STEP_COPY_SELECT_SOURCE_COMMANDS,
    STEP_COPY_SELECT_TARGET_CONTROLLER,
    STEP_COPY_SELECT_TARGET_DEVICE,
    STEP_COPY_DEVICE_NAME,
    STEP_COPY_CONFIRM,
    COPY_TYPE_DEVICE,
    COPY_TYPE_COMMANDS,
    COPY_TYPES,
    CONF_COPY_TYPE,
    CONF_SOURCE_CONTROLLER_ID,
    CONF_SOURCE_DEVICE_ID,
    CONF_SOURCE_COMMANDS,
    CONF_TARGET_CONTROLLER_ID,
    CONF_TARGET_DEVICE_ID,
    CONF_NEW_DEVICE_NAME,

    ERROR_NO_ZHA,
    ERROR_NO_DEVICE,
    ERROR_DEVICE_EXISTS,
    ERROR_COMMAND_EXISTS,
    ERROR_INVALID_NAME,
    ERROR_COPY_FAILED,
    ERROR_NO_SOURCE_DATA,
    ERROR_SAME_TARGET,

    DEFAULT_ENDPOINT_ID,
    DEFAULT_CLUSTER_ID,
    DEVICE_TYPES,  
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
    
    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the user step."""
        return await self.async_step_init(user_input)
    
    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            action = user_input[CONF_ACTION]
            
            if action == ACTION_ADD_CONTROLLER:
                return await self.async_step_add_controller()
            elif action == ACTION_COPY:
                return await self.async_step_copy_select_type()
        
        # Initialize storage and clean up orphaned data
        controllers = await self._get_valid_controllers()
        
        # Determine available actions
        actions = {ACTION_ADD_CONTROLLER: "Добавить новый ИК-пульт"}
        
        if controllers:
            actions.update({
                ACTION_COPY: "Копировать устройства/команды" 
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
    
    async def _get_valid_controllers(self):
        """Get valid controllers and clean up orphaned ones."""
        # Initialize storage for checking existing controllers
        if self.storage is None:
            self.storage = IRRemoteStorage(self.hass)
            try:
                await self.storage.async_load()
            except Exception as e:
                _LOGGER.debug("Could not load storage in config flow: %s", e)
                return []
        
        controllers = []
        try:
            all_controllers = self.storage.get_controllers()
            # Filter out controllers that don't have corresponding config entries
            existing_entries = {entry.entry_id for entry in self.hass.config_entries.async_entries(DOMAIN)}
            controllers = [c for c in all_controllers if c["id"] in existing_entries]
            
            # Clean up orphaned controllers
            orphaned_controllers = [c for c in all_controllers if c["id"] not in existing_entries]
            if orphaned_controllers:
                _LOGGER.info("Found %d orphaned controllers, cleaning up...", len(orphaned_controllers))
                for orphaned in orphaned_controllers:
                    await self.storage.async_remove_controller(orphaned["id"])
                    _LOGGER.info("Removed orphaned controller: %s", orphaned["name"])
                
        except Exception as e:
            _LOGGER.debug("Could not get controllers: %s", e)
        
        return controllers
    
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
                # Check if controller with this IEEE already exists AND has config entry
                controllers = self.storage.get_controllers()
                existing_entries = {entry.entry_id for entry in self.hass.config_entries.async_entries(DOMAIN)}
                
                for controller in controllers:
                    if (controller["ieee"] == ieee and 
                        controller["id"] in existing_entries):
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
        
    async def async_step_copy_select_type(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select what to copy: device or commands."""
        if user_input is not None:
            self.flow_data[CONF_COPY_TYPE] = user_input[CONF_COPY_TYPE]
            return await self.async_step_copy_select_source_controller()
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_TYPE,
            data_schema=vol.Schema({
                vol.Required(CONF_COPY_TYPE): vol.In(COPY_TYPES)
            })
        )
    
    async def async_step_copy_select_source_controller(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select source controller for copying."""
        controllers = await self._get_valid_controllers()
        
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            self.flow_data[CONF_SOURCE_CONTROLLER_ID] = user_input[CONF_SOURCE_CONTROLLER_ID]
            return await self.async_step_copy_select_source_device()
        
        controller_options = {
            controller["id"]: f"{controller['name']} ({controller['device_count']} устройств)"
            for controller in controllers if controller["device_count"] > 0
        }
        
        if not controller_options:
            return self.async_abort(reason="no_devices")
        
        copy_type_name = COPY_TYPES.get(self.flow_data[CONF_COPY_TYPE], "")
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_SOURCE_CONTROLLER,
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_CONTROLLER_ID): vol.In(controller_options)
            }),
            description_placeholders={
                "copy_type": copy_type_name
            }
        )
    
    async def async_step_copy_select_source_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select source device for copying."""
        source_controller_id = self.flow_data[CONF_SOURCE_CONTROLLER_ID]
        devices = self.storage.get_devices(source_controller_id)
        
        if not devices:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data[CONF_SOURCE_DEVICE_ID] = user_input[CONF_SOURCE_DEVICE_ID]
            
            # If copying commands, go to command selection
            if self.flow_data[CONF_COPY_TYPE] == COPY_TYPE_COMMANDS:
                return await self.async_step_copy_select_source_commands()
            # If copying device, go to target controller selection
            else:
                return await self.async_step_copy_select_target_controller()
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices if device["command_count"] > 0
        }
        
        if not device_options:
            return self.async_abort(reason="no_devices")
        
        source_controller = self.storage.get_controller(source_controller_id)
        copy_type_name = COPY_TYPES.get(self.flow_data[CONF_COPY_TYPE], "")
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_SOURCE_DEVICE,
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_DEVICE_ID): vol.In(device_options)
            }),
            description_placeholders={
                "copy_type": copy_type_name,
                "controller_name": source_controller["name"] if source_controller else "Unknown"
            }
        )
    
    async def async_step_copy_select_source_commands(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select source commands for copying."""
        source_controller_id = self.flow_data[CONF_SOURCE_CONTROLLER_ID]
        source_device_id = self.flow_data[CONF_SOURCE_DEVICE_ID]
        commands = self.storage.get_commands(source_controller_id, source_device_id)
        
        if not commands:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            selected_commands = user_input.get(CONF_SOURCE_COMMANDS, [])
            if not selected_commands:
                return self.async_show_form(
                    step_id=STEP_COPY_SELECT_SOURCE_COMMANDS,
                    errors={"base": "no_commands_selected"}
                )
            
            self.flow_data[CONF_SOURCE_COMMANDS] = selected_commands
            return await self.async_step_copy_select_target_controller()
        
        command_options = {
            command["id"]: command["name"]
            for command in commands
        }
        
        source_device = self.storage.get_device(source_controller_id, source_device_id)
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_SOURCE_COMMANDS,
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_COMMANDS): cv.multi_select(command_options)
            }),
            description_placeholders={
                "device_name": source_device["name"] if source_device else "Unknown"
            }
        )
    
    async def async_step_copy_select_target_controller(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select target controller for copying."""
        controllers = await self._get_valid_controllers()
        
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            self.flow_data[CONF_TARGET_CONTROLLER_ID] = user_input[CONF_TARGET_CONTROLLER_ID]
            
            # If copying device, go to device name input
            if self.flow_data[CONF_COPY_TYPE] == COPY_TYPE_DEVICE:
                return await self.async_step_copy_device_name()
            # If copying commands, go to target device selection
            else:
                return await self.async_step_copy_select_target_device()
        
        controller_options = {
            controller["id"]: f"{controller['name']} ({controller['device_count']} устройств)"
            for controller in controllers
        }
        
        copy_type_name = COPY_TYPES.get(self.flow_data[CONF_COPY_TYPE], "")
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_TARGET_CONTROLLER,
            data_schema=vol.Schema({
                vol.Required(CONF_TARGET_CONTROLLER_ID): vol.In(controller_options)
            }),
            description_placeholders={
                "copy_type": copy_type_name
            }
        )
    
    async def async_step_copy_select_target_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select target device for copying commands."""
        target_controller_id = self.flow_data[CONF_TARGET_CONTROLLER_ID]
        devices = self.storage.get_devices(target_controller_id)
        
        if not devices:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data[CONF_TARGET_DEVICE_ID] = user_input[CONF_TARGET_DEVICE_ID]
            return await self.async_step_copy_confirm()
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices
        }
        
        target_controller = self.storage.get_controller(target_controller_id)
        
        return self.async_show_form(
            step_id=STEP_COPY_SELECT_TARGET_DEVICE,
            data_schema=vol.Schema({
                vol.Required(CONF_TARGET_DEVICE_ID): vol.In(device_options)
            }),
            description_placeholders={
                "controller_name": target_controller["name"] if target_controller else "Unknown"
            }
        )
    
    async def async_step_copy_device_name(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Input new name for copied device."""
        if user_input is not None:
            new_device_name = user_input[CONF_NEW_DEVICE_NAME].strip()
            
            if not self.storage._validate_name(new_device_name):
                return self.async_show_form(
                    step_id=STEP_COPY_DEVICE_NAME,
                    errors={CONF_NEW_DEVICE_NAME: ERROR_INVALID_NAME}
                )
            
            self.flow_data[CONF_NEW_DEVICE_NAME] = new_device_name
            return await self.async_step_copy_confirm()
        
        # Generate default name
        source_controller_id = self.flow_data[CONF_SOURCE_CONTROLLER_ID]
        source_device_id = self.flow_data[CONF_SOURCE_DEVICE_ID]
        source_device = self.storage.get_device(source_controller_id, source_device_id)
        default_name = f"{source_device['name']} копия" if source_device else "Копия устройства"
        
        target_controller = self.storage.get_controller(self.flow_data[CONF_TARGET_CONTROLLER_ID])
        
        return self.async_show_form(
            step_id=STEP_COPY_DEVICE_NAME,
            data_schema=vol.Schema({
                vol.Required(CONF_NEW_DEVICE_NAME, default=default_name): cv.string
            }),
            description_placeholders={
                "source_device_name": source_device["name"] if source_device else "Unknown",
                "target_controller_name": target_controller["name"] if target_controller else "Unknown"
            }
        )
    
    async def async_step_copy_confirm(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Confirm and execute copying."""
        if user_input is not None and user_input.get("confirm", False):
            try:
                copy_type = self.flow_data[CONF_COPY_TYPE]
                source_controller_id = self.flow_data[CONF_SOURCE_CONTROLLER_ID]
                source_device_id = self.flow_data[CONF_SOURCE_DEVICE_ID]
                target_controller_id = self.flow_data[CONF_TARGET_CONTROLLER_ID]
                
                if copy_type == COPY_TYPE_DEVICE:
                    # Copy entire device
                    new_device_name = self.flow_data[CONF_NEW_DEVICE_NAME]
                    success = await self.storage.async_copy_device(
                        source_controller_id=source_controller_id,
                        source_device_id=source_device_id,
                        target_controller_id=target_controller_id,
                        new_device_name=new_device_name
                    )
                    
                    if success:
                        # Reload target controller entry
                    #    self.hass.async_create_task(
                    #        self._reload_entry_after_delay(target_controller_id)
                    #    )
                        config_entry = self.hass.config_entries.async_get_entry(target_controller_id)
                        if config_entry:
                            self.hass.async_create_task(
                                self.hass.config_entries.async_reload(target_controller_id)
                            )
                        
                        return self.async_abort(
                            reason="device_copied",
                            description_placeholders={
                                "device_name": new_device_name
                            }
                        )
                
                else:
                    # Copy commands
                    target_device_id = self.flow_data[CONF_TARGET_DEVICE_ID]
                    source_commands = self.flow_data.get(CONF_SOURCE_COMMANDS)
                    
                    success = await self.storage.async_copy_commands(
                        source_controller_id=source_controller_id,
                        source_device_id=source_device_id,
                        target_controller_id=target_controller_id,
                        target_device_id=target_device_id,
                        command_ids=source_commands
                    )
                    
                    if success:
                        # Reload target controller entry
                    #    self.hass.async_create_task(
                    #        self._reload_entry_after_delay(target_controller_id)
                    #    )
                        config_entry = self.hass.config_entries.async_get_entry(target_controller_id)
                        if config_entry:
                            self.hass.async_create_task(
                                self.hass.config_entries.async_reload(target_controller_id)
                            )
                        
                        command_count = len(source_commands) if source_commands else 0
                        return self.async_abort(
                            reason="commands_copied",
                            description_placeholders={
                                "command_count": str(command_count)
                            }
                        )
                
                # If we get here, copying failed
                return self.async_show_form(
                    step_id=STEP_COPY_CONFIRM,
                    errors={"base": ERROR_COPY_FAILED}
                )
                
            except Exception as e:
                _LOGGER.error("Copy operation failed: %s", e)
                return self.async_show_form(
                    step_id=STEP_COPY_CONFIRM,
                    errors={"base": ERROR_COPY_FAILED}
                )
        
        # Show confirmation dialog
        copy_type = self.flow_data[CONF_COPY_TYPE]
        source_controller_id = self.flow_data[CONF_SOURCE_CONTROLLER_ID]
        source_device_id = self.flow_data[CONF_SOURCE_DEVICE_ID]
        target_controller_id = self.flow_data[CONF_TARGET_CONTROLLER_ID]
        
        source_controller = self.storage.get_controller(source_controller_id)
        source_device = self.storage.get_device(source_controller_id, source_device_id)
        target_controller = self.storage.get_controller(target_controller_id)
        
        placeholders = {
            "copy_type": COPY_TYPES.get(copy_type, ""),
            "source_controller_name": source_controller["name"] if source_controller else "Unknown",
            "source_device_name": source_device["name"] if source_device else "Unknown",
            "target_controller_name": target_controller["name"] if target_controller else "Unknown",
        }
        
        if copy_type == COPY_TYPE_DEVICE:
            placeholders["new_device_name"] = self.flow_data[CONF_NEW_DEVICE_NAME]
        else:
            target_device_id = self.flow_data[CONF_TARGET_DEVICE_ID]
            target_device = self.storage.get_device(target_controller_id, target_device_id)
            placeholders["target_device_name"] = target_device["name"] if target_device else "Unknown"
            
            source_commands = self.flow_data.get(CONF_SOURCE_COMMANDS, [])
            placeholders["command_count"] = str(len(source_commands))
        
        return self.async_show_form(
            step_id=STEP_COPY_CONFIRM,
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders=placeholders
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

class IRRemoteOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for IR Remote."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.flow_data: Dict[str, Any] = {}
        self.storage: IRRemoteStorage = None
    
    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial options step."""
        errors = {}
        
        # Initialize storage
        if self.storage is None:
            self.storage = IRRemoteStorage(self.hass)
            try:
                await self.storage.async_load()
            except Exception as e:
                _LOGGER.debug("Could not load storage in options flow: %s", e)
                return self.async_abort(reason="storage_error")
        
        # Get controller data
        controller_id = self.config_entry.entry_id
        controller = self.storage.get_controller(controller_id)
        
        if not controller:
            return self.async_abort(reason="controller_not_found")
        
        if user_input is not None:
            action = user_input["action"]
            
            if action == "add_device":
                return await self.async_step_add_device()
            elif action == "add_command":
                return await self.async_step_select_device_for_command()
            elif action == "remove_device":
                return await self.async_step_select_device_for_remove()
            elif action == "remove_command":
                return await self.async_step_select_device_for_remove_command()
        
        # Get statistics for this controller
        devices = self.storage.get_devices(controller_id)
        total_commands = sum(device["command_count"] for device in devices)
        
        # Determine available actions
        actions = {"add_device": "Добавить виртуальное устройство"}
        
        if devices:
            actions.update({
                "add_command": "Добавить команду к устройству",
                "remove_device": "Удалить виртуальное устройство",
                "remove_command": "Удалить команду устройства"
            })
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In(actions)
            }),
            errors=errors,
            description_placeholders={
                "controller_name": controller.get("name", "Неизвестный пульт"),
                "devices_count": str(len(devices)),
                "commands_count": str(total_commands)
            }
        )
    
    async def async_step_add_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle adding device to controller."""
        errors = {}
        controller_id = self.config_entry.entry_id
        
        if user_input is not None:
            device_name = user_input["device_name"].strip()
            
            # Validate device name
            if not self.storage or not self.storage._validate_name(device_name):
                errors["device_name"] = ERROR_INVALID_NAME
            else:
                # Generate device ID from name
                device_id = device_name.lower().replace(" ", "_").replace("-", "_")
                
                # Check if device already exists
                try:
                    devices = self.storage.get_devices(controller_id)
                    for device in devices:
                        if device["id"] == device_id:
                            errors["device_name"] = ERROR_DEVICE_EXISTS
                            break
                except Exception:
                    pass
                
                if not errors:
                    # Store device info and proceed to type selection
                    self.flow_data[CONF_DEVICE_NAME] = device_name
                    self.flow_data["device_id"] = device_id
                    return await self.async_step_select_device_type()
        
        controller_name = "Unknown"
        if self.storage:
            try:
                controller = self.storage.get_controller(self.flow_data[CONF_CONTROLLER_ID])
                if controller:
                    controller_name = controller["name"]
            except Exception:
                pass
        
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
    
    async def async_step_select_device_type(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle device type selection.""" 
        controller_id = self.config_entry.entry_id

        if user_input is not None:
            device_id = self.flow_data["device_id"]
            device_name = self.flow_data[CONF_DEVICE_NAME]
            device_type = user_input[CONF_DEVICE_TYPE]
            
            try:
                # Add device with selected type
                success = await self.storage.async_add_device(controller_id, device_id, device_name, device_type)
                
                if success:
                    # Schedule reload after current flow completes
                    self.hass.async_create_task(
                        self._reload_entry_after_delay(controller_id)
                    )
                    
                    return self.async_abort(
                        reason="device_added",
                        description_placeholders={
                            "device_name": device_name
                        }
                    )
                else:
                    return self.async_show_form(
                        step_id=STEP_SELECT_DEVICE_TYPE,
                        errors={"base": "add_device_failed"}
                    )
            except Exception:
                return self.async_show_form(
                    step_id=STEP_SELECT_DEVICE_TYPE,
                    errors={"base": "add_device_failed"}
                )
        
        return self.async_show_form(
            step_id=STEP_SELECT_DEVICE_TYPE,
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_TYPE): vol.In(DEVICE_TYPES),
            }),
            description_placeholders={
                "device_name": self.flow_data.get(CONF_DEVICE_NAME, "Unknown")
            }
        )
    
    async def async_step_select_device_for_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select device for adding command."""
        controller_id = self.config_entry.entry_id
        devices = self.storage.get_devices(controller_id)
        
        if not devices:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_add_command()
        
        # If only one device, auto-select it
        if len(devices) == 1:
            self.flow_data["device_id"] = devices[0]["id"]
            return await self.async_step_add_command()
        
        # Multiple devices - show selection
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
        controller_id = self.config_entry.entry_id
        
        if user_input is not None:
            command_name = user_input["command_name"].strip()
            
            # Validate command name
            if not self.storage._validate_name(command_name):
                errors["command_name"] = ERROR_INVALID_NAME
            else:
                # Generate command ID from name
                command_id = command_name.lower().replace(" ", "_").replace("-", "_")
                
                # Check if command already exists
                device_id = self.flow_data["device_id"]
                commands = self.storage.get_commands(controller_id, device_id)
                
                for command in commands:
                    if command["id"] == command_id:
                        errors["command_name"] = ERROR_COMMAND_EXISTS
                        break
                
                if not errors:
                    # Store command info and proceed to learning
                    self.flow_data["command_name"] = command_name
                    self.flow_data["command_id"] = command_id
                    return await self.async_step_learn_command()
        
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, self.flow_data["device_id"])
        
        return self.async_show_form(
            step_id="add_command",
            data_schema=vol.Schema({
                vol.Required("command_name"): cv.string,
            }),
            errors=errors,
            description_placeholders={
                "controller_name": controller["name"] if controller else "Неизвестный пульт",
                "device_name": device["name"] if device else "Неизвестное устройство"
            }
        )
    
    async def async_step_learn_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle IR learning process."""
        controller_id = self.config_entry.entry_id
        
        if user_input is not None:
            device_id = self.flow_data["device_id"]
            command_id = self.flow_data["command_id"]
            command_name = self.flow_data["command_name"]
            
            try:
                # Check if service exists, if not - start learning directly
                if self.hass.services.has_service("ir_remote", "learn_command"):
                    await self.hass.services.async_call(
                        "ir_remote",
                        "learn_command",
                        {
                            "controller_id": controller_id,
                            "device": device_id,
                            "command": command_id,
                        },
                        blocking=False
                    )
                else:
                    # Start learning directly through the controller
                    await self._start_learning_directly(controller_id, device_id, command_id, command_name)
                    
            except Exception as e:
                _LOGGER.error("Failed to start learning: %s", e)
            
            return self.async_create_entry(
                title="",
                data={}
            )
        
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, self.flow_data["device_id"])
        
        return self.async_show_form(
            step_id="learn_command",
            data_schema=vol.Schema({}),
            description_placeholders={
                "controller_name": controller["name"] if controller else "Неизвестный пульт",
                "device_name": device["name"] if device else "Неизвестное устройство",
                "command_name": self.flow_data.get("command_name", "Неизвестная команда")
            }
        )
    
    async def async_step_select_device_for_remove(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select device for removal."""
        controller_id = self.config_entry.entry_id
        devices = self.storage.get_devices(controller_id)
        
        if not devices:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_confirm_remove_device()
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices
        }
        
        return self.async_show_form(
            step_id="select_device_for_remove",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(device_options)
            })
        )
    
    async def async_step_confirm_remove_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Confirm device removal."""
        controller_id = self.config_entry.entry_id
        
        if user_input is not None and user_input.get("confirm", False):
            device_id = self.flow_data["device_id"]
            
            # Get device name and commands before removal
            device = self.storage.get_device(controller_id, device_id)
            commands = self.storage.get_commands(controller_id, device_id)
            
            try:
                success = await self.storage.async_remove_device(controller_id, device_id)
                
                if success:
                    # Clean up entities and device
                    await self._cleanup_device_entities(controller_id, device_id, commands)
                    await self._cleanup_virtual_device(controller_id, device_id)
                    # Reload integration to update entities  
                    self.hass.async_create_task(
                        self._reload_entry_after_delay(controller_id)
                    )

                    return self.async_create_entry(
                        title="",
                        data={}
                    )
                else:
                    return self.async_show_form(
                        step_id="confirm_remove_device",
                        errors={"base": ERROR_REMOVE_FAILED}
                    )
            except Exception:
                return self.async_show_form(
                    step_id="confirm_remove_device",
                    errors={"base": ERROR_REMOVE_FAILED}
                )
        
        # Show confirmation dialog
        device_id = self.flow_data["device_id"]
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, device_id)
        commands = self.storage.get_commands(controller_id, device_id)
        
        return self.async_show_form(
            step_id="confirm_remove_device",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={
                "controller_name": controller["name"] if controller else "Неизвестный пульт",
                "device_name": device["name"] if device else "Неизвестное устройство",
                "commands_count": str(len(commands))
            }
        )
    
    async def async_step_select_device_for_remove_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select device for removing command."""
        controller_id = self.config_entry.entry_id
        devices = self.storage.get_devices(controller_id)
        
        # Only show devices that have commands
        devices_with_commands = [d for d in devices if d["command_count"] > 0]
        
        if not devices_with_commands:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_select_command_for_remove()
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices_with_commands
        }
        
        return self.async_show_form(
            step_id="select_device_for_remove_command",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(device_options)
            })
        )
    
    async def async_step_select_command_for_remove(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select command for removal."""
        controller_id = self.config_entry.entry_id
        device_id = self.flow_data["device_id"]
        commands = self.storage.get_commands(controller_id, device_id)
        
        if not commands:
            return self.async_abort(reason="no_devices")
        
        if user_input is not None:
            self.flow_data["command_id"] = user_input["command_id"]
            return await self.async_step_confirm_remove_command()
        
        command_options = {
            command["id"]: command["name"]
            for command in commands
        }
        
        return self.async_show_form(
            step_id="select_command_for_remove",
            data_schema=vol.Schema({
                vol.Required("command_id"): vol.In(command_options)
            })
        )
    
    async def async_step_confirm_remove_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Confirm command removal."""
        controller_id = self.config_entry.entry_id
        
        if user_input is not None and user_input.get("confirm", False):
            device_id = self.flow_data["device_id"]
            command_id = self.flow_data["command_id"]
            
            try:
                success = await self.storage.async_remove_command(controller_id, device_id, command_id)
                
                if success:
                    # Clean up entity
                    await self._cleanup_command_entity(controller_id, device_id, command_id)
                    # Reload integration to update entities
                    self.hass.async_create_task(
                        self._reload_entry_after_delay(controller_id)
                    )

                    return self.async_create_entry(
                        title="",
                        data={}
                    )
                else:
                    return self.async_show_form(
                        step_id="confirm_remove_command",
                        errors={"base": ERROR_REMOVE_FAILED}
                    )
            except Exception:
                return self.async_show_form(
                    step_id="confirm_remove_command",
                    errors={"base": ERROR_REMOVE_FAILED}
                )
        
        # Show confirmation dialog
        device_id = self.flow_data["device_id"]
        command_id = self.flow_data["command_id"]
        
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, device_id)
        commands = self.storage.get_commands(controller_id, device_id)
        
        command_name = "Неизвестная команда"
        for cmd in commands:
            if cmd["id"] == command_id:
                command_name = cmd["name"]
                break
        
        return self.async_show_form(
            step_id="confirm_remove_command",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={
                "controller_name": controller["name"] if controller else "Неизвестный пульт",
                "device_name": device["name"] if device else "Неизвестное устройство",
                "command_name": command_name
            }
        )
    
    # Helper methods (copied from main config flow)
    
    async def _reload_entry_after_delay(self, controller_id: str) -> None:
        """Reload entry after a short delay."""
        await asyncio.sleep(0.5)
        await self.hass.config_entries.async_reload(controller_id)
    
    async def _start_learning_directly(self, controller_id: str, device_id: str, command_id: str, command_name: str) -> None:
        """Start learning directly without using service."""
        try:
            _LOGGER.info("Starting learning process for %s - %s", device_id, command_name)
            
            controller = self.storage.get_controller(controller_id)
            if not controller:
                _LOGGER.error("Controller not found: %s", controller_id)
                return
            
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": controller["ieee"],
                    "endpoint_id": controller["endpoint_id"],
                    "cluster_id": controller["cluster_id"],
                    "cluster_type": "in",
                    "command": 1,
                    "command_type": "server",
                    "params": {"on_off": True}
                },
                blocking=True
            )
            
            # Schedule code reading after delay
            self.hass.async_create_task(
                self._read_learned_code_after_delay(controller, controller_id, device_id, command_id, command_name)
            )
            
        except Exception as e:
            _LOGGER.error("Failed to start learning directly: %s", e)
    
    async def _read_learned_code_after_delay(self, controller: dict, controller_id: str, device_id: str, command_id: str, command_name: str) -> None:
        """Read learned IR code after delay."""
        await asyncio.sleep(10)
        
        try:
            result = await self.hass.services.async_call(
                "zha_toolkit",
                "attr_read",
                {
                    "ieee": controller["ieee"],
                    "endpoint": controller["endpoint_id"],
                    "cluster": controller["cluster_id"],
                    "attribute": 0,
                    "use_cache": False
                },
                blocking=True,
                return_response=True
            )
            
            ir_code = None
            if result and "result_read" in result:
                result_read = result["result_read"]
                if isinstance(result_read, (list, tuple)) and len(result_read) > 0:
                    attributes_dict = result_read[0]
                    if isinstance(attributes_dict, dict) and 0 in attributes_dict:
                        ir_code = attributes_dict[0]
            
            if ir_code:
                success = await self.storage.async_add_command(
                    controller_id, device_id, command_id, command_name, str(ir_code)
                )
                
                if success:
                    _LOGGER.info("Successfully saved learned command: %s - %s", device_id, command_name)
                    await self.hass.config_entries.async_reload(controller_id)
                else:
                    _LOGGER.error("Failed to save learned command")
            else:
                _LOGGER.error("No IR code found in response")
                
        except Exception as e:
            _LOGGER.error("Error reading learned code: %s", e)
    
    async def _cleanup_command_entity(self, controller_id: str, device_id: str, command_id: str) -> None:
        """Remove command button entity from Entity Registry."""
        entity_registry = er.async_get(self.hass)
        unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"
        entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)

    async def _cleanup_device_entities(self, controller_id: str, device_id: str, commands: list) -> None:
        """Remove all button entities for a device from Entity Registry."""
        entity_registry = er.async_get(self.hass)
        
        for command in commands:
            command_id = command["id"]
            unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"
            entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)

    async def _cleanup_virtual_device(self, controller_id: str, device_id: str) -> None:
        """Remove virtual device from Device Registry."""
        device_registry = dr.async_get(self.hass)
        device_identifier = (DOMAIN, f"{controller_id}_{device_id}")
        device_entry = device_registry.async_get_device(identifiers={device_identifier})
        if device_entry:
            device_registry.async_remove_device(device_entry.id)

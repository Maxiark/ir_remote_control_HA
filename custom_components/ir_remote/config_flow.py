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
    ACTION_MANAGE,
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
    STEP_MANAGE,
    ERROR_NO_ZHA,
    ERROR_NO_DEVICE,
    ERROR_DEVICE_EXISTS,
    ERROR_COMMAND_EXISTS,
    ERROR_INVALID_NAME,
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
            elif action == ACTION_ADD_DEVICE:
                return await self.async_step_select_controller_for_device()
            elif action == ACTION_ADD_COMMAND:
                return await self.async_step_select_controller_for_command()
            elif action == ACTION_REMOVE_DEVICE:                           
                return await self.async_step_select_controller_for_remove_device() 
            elif action == ACTION_REMOVE_COMMAND:
                return await self.async_step_select_controller_for_remove_command()
            elif action == ACTION_MANAGE:
                return await self.async_step_manage()
        
        # Initialize storage and clean up orphaned data
        controllers = await self._get_valid_controllers()
        
        # Determine available actions
        actions = {ACTION_ADD_CONTROLLER: "Добавить новый ИК-пульт"}
        
        if controllers:
            actions.update({
                ACTION_ADD_DEVICE: "Добавить виртуальное устройство",
                ACTION_ADD_COMMAND: "Добавить команду к устройству", 
                ACTION_REMOVE_DEVICE: "Удалить виртуальное устройство",
                ACTION_REMOVE_COMMAND: "Удалить команду устройства",
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
    
    async def async_step_select_controller_for_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select controller for adding device."""
        controllers = await self._get_valid_controllers()
        
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
            
            # Validate device name
            if not self.storage or not self.storage._validate_name(device_name):
                errors[CONF_DEVICE_NAME] = ERROR_INVALID_NAME
            else:
                # Generate device ID from name
                device_id = device_name.lower().replace(" ", "_").replace("-", "_")
                
                # Check if device already exists
                try:
                    devices = self.storage.get_devices(controller_id)
                    for device in devices:
                        if device["id"] == device_id:
                            errors[CONF_DEVICE_NAME] = ERROR_DEVICE_EXISTS
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
        if user_input is not None:
            controller_id = self.flow_data[CONF_CONTROLLER_ID]
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
    
    async def _read_learned_code_after_delay(self, controller: dict, controller_id: str, device_id: str, command_id: str, command_name: str) -> None:
        """Read learned IR code after delay."""
        await asyncio.sleep(10)  # Wait for learning to complete
        
        try:
            # Read the learned IR code from attribute 0
            await self.hass.services.async_call(
                "zha_toolkit",
                "attr_read",
                {
                    "ieee": controller["ieee"],
                    "endpoint": controller["endpoint_id"],
                    "cluster": controller["cluster_id"],
                    "attribute": 0,
                    "state_id": f"ir_remote.learned_code_{controller_id}",
                    "allow_create": True,
                    "use_cache": False
                },
                blocking=True
            )
            
            # Wait for state to be updated
            await asyncio.sleep(1)
            
            # Retrieve and save the code
            state_id = f"ir_remote.learned_code_{controller_id}"
            state = self.hass.states.get(state_id)
            
            if state and state.state:
                ir_code = state.state
                _LOGGER.info("Retrieved learned IR code (length: %d) for %s - %s", len(ir_code), device_id, command_name)
                
                # Save the learned code
                success = await self.storage.async_add_command(
                    controller_id, device_id, command_id, command_name, ir_code
                )
                
                if success:
                    _LOGGER.info("Successfully saved learned command: %s - %s", device_id, command_name)
                    # Reload config entry to update button entity
                    await self.hass.config_entries.async_reload(controller_id)
                    
                    # Clean up temporary state
                    self.hass.states.async_remove(state_id)
                else:
                    _LOGGER.error("Failed to save learned command: %s - %s", device_id, command_name)
            else:
                _LOGGER.warning("No learned code found in state %s", state_id)
                
        except Exception as e:
            _LOGGER.error("Error reading learned code: %s", e)
    
    async def _reload_entry_after_delay(self, controller_id: str) -> None:
        """Reload entry after a short delay."""
        import asyncio
        await asyncio.sleep(0.5)  # Short delay to let config flow complete
        
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == controller_id:
                await self.hass.config_entries.async_reload(entry.entry_id)
                break
    
    async def async_step_select_controller_for_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Select controller and device for adding command."""
        controllers = await self._get_valid_controllers()
        
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
            # Пользователь нажал "продолжить" - сразу запускаем обучение
            controller_id = self.flow_data[CONF_CONTROLLER_ID]
            device_id = self.flow_data["device_id"]
            command_id = self.flow_data["command_id"]
            command_name = self.flow_data[CONF_COMMAND_NAME]
            
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
            
            return self.async_abort(
                reason="command_learning_started",
                description_placeholders={
                    "command_name": command_name
                }
            )
        
        controller_name = "Unknown"
        device_name = "Unknown"
        
        if self.storage:
            try:
                controller = self.storage.get_controller(self.flow_data[CONF_CONTROLLER_ID])
                if controller:
                    controller_name = controller["name"]
                
                device = self.storage.get_device(self.flow_data[CONF_CONTROLLER_ID], self.flow_data["device_id"])
                if device:
                    device_name = device["name"]
            except Exception:
                pass
        
        # Показываем только инструкцию без полей формы - только кнопка "продолжить"
        return self.async_show_form(
            step_id=STEP_LEARN_COMMAND,
            data_schema=vol.Schema({}),  # Пустая схема = только кнопка "продолжить"
            description_placeholders={
                "controller_name": controller_name,
                "device_name": device_name,
                "command_name": self.flow_data.get(CONF_COMMAND_NAME, "Unknown")
            }
        )
    
    
    async def _start_learning_directly(self, controller_id: str, device_id: str, command_id: str, command_name: str) -> None:
        """Start learning directly without using service."""
        try:
            # Don't create command placeholder - we'll create it after learning
            _LOGGER.info("Starting learning process for %s - %s", device_id, command_name)
            
            # Get controller data from storage
            controller = self.storage.get_controller(controller_id)
            if not controller:
                _LOGGER.error("Controller not found: %s", controller_id)
                return
            
            # Send ZHA command directly
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": controller["ieee"],
                    "endpoint_id": controller["endpoint_id"],
                    "cluster_id": controller["cluster_id"],
                    "cluster_type": "in",
                    "command": 1,  # ZHA_COMMAND_LEARN
                    "command_type": "server",
                    "params": {"on_off": True}  # Required parameter for learning mode
                },
                blocking=True
            )
            _LOGGER.info("Learning command sent directly for %s - %s", device_id, command_name)
            
            # Schedule code reading after delay
            self.hass.async_create_task(
                self._read_learned_code_after_delay(controller, controller_id, device_id, command_id, command_name)
            )
            
        except Exception as e:
            _LOGGER.error("Failed to start learning directly: %s", e)
    
    async def async_step_manage(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle management of existing data."""
        controllers = await self._get_valid_controllers()
        
        total_devices = sum(controller["device_count"] for controller in controllers)
        total_commands = 0
        
        for controller in controllers:
            controller_id = controller["id"]
            devices = self.storage.get_devices(controller_id)
            for device in devices:
                device_id = device["id"]
                commands = self.storage.get_commands(controller_id, device_id)
                total_commands += len(commands)
        
        return self.async_abort(
            reason="manage_completed",
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


    # ==========  МЕТОДЫ ДЛЯ УДАЛЕНИЯ УСТРОЙСТВ ==========
    
    async def async_step_select_controller_for_remove_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Select controller for removing device."""
        controllers = await self._get_valid_controllers()
        
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            self.flow_data[CONF_CONTROLLER_ID] = user_input[CONF_CONTROLLER_ID]
            return await self.async_step_select_device_for_remove()
        
        controller_options = {
            controller["id"]: f"{controller['name']} ({controller['device_count']} устройств)" 
            for controller in controllers if controller["device_count"] > 0
        }
        
        if not controller_options:
            return self.async_abort(reason="no_devices")
        
        return self.async_show_form(
            step_id=STEP_SELECT_CONTROLLER_FOR_REMOVE_DEVICE,
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_ID): vol.In(controller_options)
            })
        )
    
    async def async_step_select_device_for_remove(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Select device for removal."""
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_confirm_remove_device()
        
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        devices = self.storage.get_devices(controller_id)
        
        if not devices:
            return self.async_abort(reason="no_devices")
        
        controller = self.storage.get_controller(controller_id)
        controller_name = controller["name"] if controller else "Unknown"
        
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices
        }
        
        return self.async_show_form(
            step_id=STEP_SELECT_DEVICE_FOR_REMOVE,
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(device_options)
            }),
            description_placeholders={
                "controller_name": controller_name
            }
        )
    
    async def async_step_confirm_remove_device(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Confirm device removal."""
        if user_input is not None and user_input.get("confirm", False):
            # User confirmed removal
            controller_id = self.flow_data[CONF_CONTROLLER_ID]
            device_id = self.flow_data["device_id"]
            
            # Get device name and commands before removal
            device = self.storage.get_device(controller_id, device_id)
            device_name = device["name"] if device else "Unknown"
            commands = self.storage.get_commands(controller_id, device_id)
            
            try:
                success = await self.storage.async_remove_device(controller_id, device_id)
                
                if success:
                    # Clean up entities and device
                    await self._cleanup_device_entities(controller_id, device_id, commands)
                    await self._cleanup_virtual_device(controller_id, device_id)
                    
                    return self.async_abort(
                        reason="device_removed",
                        description_placeholders={"device_name": device_name}
                    )
                else:
                    return self.async_show_form(
                        step_id=STEP_CONFIRM_REMOVE_DEVICE,
                        errors={"base": ERROR_REMOVE_FAILED}
                    )
            except Exception:
                return self.async_show_form(
                    step_id=STEP_CONFIRM_REMOVE_DEVICE,
                    errors={"base": ERROR_REMOVE_FAILED}
                )
        
        # Show confirmation dialog
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        device_id = self.flow_data["device_id"]
        
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, device_id)
        commands = self.storage.get_commands(controller_id, device_id)
        
        controller_name = controller["name"] if controller else "Unknown"
        device_name = device["name"] if device else "Unknown"
        commands_count = len(commands)
        
        return self.async_show_form(
            step_id=STEP_CONFIRM_REMOVE_DEVICE,
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={
                "controller_name": controller_name,
                "device_name": device_name,
                "commands_count": str(commands_count)
            }
        )

    # ==========  МЕТОДЫ ДЛЯ УДАЛЕНИЯ КОМАНД ==========
    
    async def async_step_select_controller_for_remove_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Select controller for removing command."""
        controllers = await self._get_valid_controllers()
        
        if not controllers:
            return self.async_abort(reason=ERROR_NO_DEVICE)
        
        if user_input is not None:
            controller_id = user_input[CONF_CONTROLLER_ID]
            self.flow_data[CONF_CONTROLLER_ID] = controller_id
            return await self.async_step_select_device_for_remove_command()
        
        # Only show controllers that have devices with commands
        controller_options = {}
        for controller in controllers:
            devices = self.storage.get_devices(controller["id"])
            total_commands = sum(device["command_count"] for device in devices)
            if total_commands > 0:
                controller_options[controller["id"]] = f"{controller['name']} ({total_commands} команд)"
        
        if not controller_options:
            return self.async_abort(reason="no_devices")
        
        return self.async_show_form(
            step_id=STEP_SELECT_CONTROLLER_FOR_REMOVE_COMMAND,
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_ID): vol.In(controller_options)
            })
        )
    
    async def async_step_select_device_for_remove_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Select device for removing command."""
        if user_input is not None:
            self.flow_data["device_id"] = user_input["device_id"]
            return await self.async_step_select_command_for_remove()
        
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        devices = self.storage.get_devices(controller_id)
        controller = self.storage.get_controller(controller_id)
        controller_name = controller["name"] if controller else "Unknown"
        
        # Only show devices that have commands
        device_options = {
            device["id"]: f"{device['name']} ({device['command_count']} команд)"
            for device in devices if device["command_count"] > 0
        }
        
        if not device_options:
            return self.async_abort(reason="no_devices")
        
        return self.async_show_form(
            step_id=STEP_SELECT_DEVICE_FOR_REMOVE_COMMAND,
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(device_options)
            }),
            description_placeholders={
                "controller_name": controller_name
            }
        )
    
    async def async_step_select_command_for_remove(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Select command for removal."""
        if user_input is not None:
            self.flow_data["command_id"] = user_input["command_id"]
            return await self.async_step_confirm_remove_command()
        
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        device_id = self.flow_data["device_id"]
        commands = self.storage.get_commands(controller_id, device_id)
        device = self.storage.get_device(controller_id, device_id)
        device_name = device["name"] if device else "Unknown"
        
        if not commands:
            return self.async_abort(reason="no_devices")
        
        command_options = {
            command["id"]: command["name"]
            for command in commands
        }
        
        return self.async_show_form(
            step_id=STEP_SELECT_COMMAND_FOR_REMOVE,
            data_schema=vol.Schema({
                vol.Required("command_id"): vol.In(command_options)
            }),
            description_placeholders={
                "device_name": device_name
            }
        )
    
    async def async_step_confirm_remove_command(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """ДОБАВЛЕНО: Confirm command removal."""
        if user_input is not None and user_input.get("confirm", False):
            # User confirmed removal
            controller_id = self.flow_data[CONF_CONTROLLER_ID]
            device_id = self.flow_data["device_id"]
            command_id = self.flow_data["command_id"]
            
            # Get command name before removal
            commands = self.storage.get_commands(controller_id, device_id)
            command_name = "Unknown"
            for cmd in commands:
                if cmd["id"] == command_id:
                    command_name = cmd["name"]
                    break
            
            try:
                success = await self.storage.async_remove_command(controller_id, device_id, command_id)
                
                if success:
                    # Clean up entity
                    await self._cleanup_command_entity(controller_id, device_id, command_id)
                    
                    return self.async_abort(
                        reason="command_removed",
                        description_placeholders={"command_name": command_name}
                    )
                else:
                    return self.async_show_form(
                        step_id=STEP_CONFIRM_REMOVE_COMMAND,
                        errors={"base": ERROR_REMOVE_FAILED}
                    )
            except Exception:
                return self.async_show_form(
                    step_id=STEP_CONFIRM_REMOVE_COMMAND,
                    errors={"base": ERROR_REMOVE_FAILED}
                )
        
        # Show confirmation dialog
        controller_id = self.flow_data[CONF_CONTROLLER_ID]
        device_id = self.flow_data["device_id"]
        command_id = self.flow_data["command_id"]
        
        controller = self.storage.get_controller(controller_id)
        device = self.storage.get_device(controller_id, device_id)
        commands = self.storage.get_commands(controller_id, device_id)
        
        controller_name = controller["name"] if controller else "Unknown"
        device_name = device["name"] if device else "Unknown"
        command_name = "Unknown"
        
        for cmd in commands:
            if cmd["id"] == command_id:
                command_name = cmd["name"]
                break
        
        return self.async_show_form(
            step_id=STEP_CONFIRM_REMOVE_COMMAND,
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={
                "controller_name": controller_name,
                "device_name": device_name,
                "command_name": command_name
            }
        )

    # ========== HELPER МЕТОДЫ ДЛЯ ОЧИСТКИ СУЩНОСТЕЙ ==========
    
    async def _cleanup_command_entity(self, controller_id: str, device_id: str, command_id: str) -> None:
        """ДОБАВЛЕНО: Remove command button entity from Entity Registry."""
        entity_registry = er.async_get(self.hass)
        unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"
        entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)

    async def _cleanup_device_entities(self, controller_id: str, device_id: str, commands: list) -> None:
        """ДОБАВЛЕНО: Remove all button entities for a device from Entity Registry."""
        entity_registry = er.async_get(self.hass)
        
        # Remove all command button entities
        for command in commands:
            command_id = command["id"]
            unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"
            entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)
        
        # Remove "add command" button entity
        add_command_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_add_command"
        add_command_entity_id = entity_registry.async_get_entity_id("button", DOMAIN, add_command_unique_id)
        if add_command_entity_id:
            entity_registry.async_remove(add_command_entity_id)

    async def _cleanup_virtual_device(self, controller_id: str, device_id: str) -> None:
        """ДОБАВЛЕНО: Remove virtual device from Device Registry."""
        device_registry = dr.async_get(self.hass)
        device_identifier = (DOMAIN, f"{controller_id}_{device_id}")
        device_entry = device_registry.async_get_device(identifiers={device_identifier})
        if device_entry:
            device_registry.async_remove_device(device_entry.id)


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
        self.config_entry = config_entry
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
            elif action == "manage":
                return await self.async_step_manage()
        
        # Get statistics for this controller
        devices = self.storage.get_devices(controller_id)
        total_commands = sum(device["command_count"] for device in devices)
        
        # Determine available actions
        actions = {"add_device": "Добавить виртуальное устройство"}
        
        if devices:
            actions.update({
                "add_command": "Добавить команду к устройству",
                "remove_device": "Удалить виртуальное устройство",
                "remove_command": "Удалить команду устройства",
                "manage": "Просмотр данных пульта"
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
                    # Add device
                    try:
                        success = await self.storage.async_add_device(controller_id, device_id, device_name)
                        
                        if success:
                            # Schedule reload after current flow completes
                            self.hass.async_create_task(
                                self._reload_entry_after_delay(controller_id)
                            )
                            
                            return self.async_create_entry(
                                title="",
                                data={}
                            )
                        else:
                            errors["base"] = "add_device_failed"
                    except Exception:
                        errors["base"] = "add_device_failed"
        
        controller = self.storage.get_controller(controller_id)
        controller_name = controller.get("name", "Неизвестный пульт") if controller else "Неизвестный пульт"
        
        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({
                vol.Required("device_name"): cv.string,
            }),
            errors=errors,
            description_placeholders={
                "controller_name": controller_name
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
    
    async def async_step_manage(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle management of existing data for this controller."""
        controller_id = self.config_entry.entry_id
        controller = self.storage.get_controller(controller_id)
        devices = self.storage.get_devices(controller_id)
        
        total_commands = sum(device["command_count"] for device in devices)
        
        return self.async_create_entry(
            title="",
            data={},
            description_placeholders={
                "controller_name": controller["name"] if controller else "Неизвестный пульт",
                "devices_count": str(len(devices)),
                "commands_count": str(total_commands)
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
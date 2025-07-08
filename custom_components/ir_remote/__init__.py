"""IR Remote integration for Home Assistant."""
import logging
import asyncio
from typing import Any, Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    CONF_ROOM_NAME,
    CONF_CONTROLLER_ID,
    CONF_DEVICE_NAME,
    CONF_COMMAND_NAME,
    DEFAULT_CLUSTER_TYPE,
    DEFAULT_COMMAND_TYPE,
    SERVICE_LEARN_COMMAND,
    SERVICE_SEND_CODE,
    SERVICE_SEND_COMMAND,
    SERVICE_ADD_DEVICE,
    SERVICE_ADD_COMMAND,
    SERVICE_REMOVE_DEVICE,
    SERVICE_REMOVE_COMMAND,
    SERVICE_GET_DATA,
    ATTR_CONTROLLER_ID,
    ATTR_DEVICE,
    ATTR_COMMAND,
    ATTR_CODE,
    ATTR_DEVICE_NAME,
    ATTR_COMMAND_NAME,
    ZHA_COMMAND_LEARN,
    ZHA_COMMAND_SEND,
    MANUFACTURER,
    MODEL_CONTROLLER,
    MODEL_VIRTUAL_DEVICE,
)
from .data import IRRemoteStorage

_LOGGER = logging.getLogger(__name__)

# Platforms to load
PLATFORMS = [Platform.BUTTON]

# Config schema - integration only works with config entries
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Service schemas
LEARN_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required(ATTR_COMMAND): cv.string,
})

SEND_CODE_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_CODE): cv.string,
})

SEND_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required(ATTR_COMMAND): cv.string,
})

ADD_DEVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE_NAME): cv.string,
})

ADD_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required(ATTR_COMMAND_NAME): cv.string,
    vol.Required(ATTR_CODE): cv.string,
})

REMOVE_DEVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE): cv.string,
})

REMOVE_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_CONTROLLER_ID): cv.string,
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required(ATTR_COMMAND): cv.string,
})

GET_DATA_SCHEMA = vol.Schema({
    vol.Optional(ATTR_CONTROLLER_ID): cv.string,
})


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.info("Setting up IR Remote integration")
    
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    
    # Register services
    await _register_services(hass)
    
    _LOGGER.info("IR Remote integration setup completed")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.info("Setting up IR Remote entry: %s", entry.title)
    
    try:
        # Check ZHA availability
        if "zha" not in hass.data:
            _LOGGER.error("ZHA integration not found")
            raise ConfigEntryNotReady("ZHA integration not available")
        
        # Handle special actions from config flow
        action = entry.data.get("action")
        if action:
            _LOGGER.info("Processing action: %s", action)
            
            try:
                if action == "device_added":
                    await _handle_device_addition(hass, entry)
                elif action == "command_learning_started":
                    await _handle_command_learning_start(hass, entry)
                elif action == "data_viewed":
                    pass  # No action needed for viewing data
                
                # Remove this temporary entry after processing
                await hass.config_entries.async_remove(entry.entry_id)
                return True
            except Exception as e:
                _LOGGER.error("Error processing action %s: %s", action, e, exc_info=True)
                await hass.config_entries.async_remove(entry.entry_id)
                return False
        
        # This is a real controller entry
        _LOGGER.info("Setting up real controller: %s", entry.entry_id)
        
        # Initialize storage for this controller
        try:
            storage = IRRemoteStorage(hass)
            await storage.async_load()
            _LOGGER.info("Storage loaded successfully")
        except Exception as e:
            _LOGGER.error("Failed to load storage: %s", e, exc_info=True)
            return False
        
        # Add controller to storage if not exists
        controller_id = entry.entry_id
        ieee = entry.data[CONF_IEEE]
        room_name = entry.data[CONF_ROOM_NAME]
        endpoint_id = entry.data.get(CONF_ENDPOINT, 1)
        cluster_id = entry.data.get(CONF_CLUSTER, 57348)
        
        _LOGGER.info("Adding controller: %s, IEEE: %s", controller_id, ieee)
        
        try:
            # Add controller if not exists
            controllers = storage.get_controllers()
            controller_exists = any(c["id"] == controller_id for c in controllers)
            
            if not controller_exists:
                success = await storage.async_add_controller(
                    controller_id, ieee, room_name, endpoint_id, cluster_id
                )
                if not success:
                    _LOGGER.error("Failed to add controller to storage")
                    return False
                _LOGGER.info("Controller added to storage successfully")
            else:
                _LOGGER.info("Controller already exists in storage")
        except Exception as e:
            _LOGGER.error("Error adding controller to storage: %s", e, exc_info=True)
            return False
        
        # Store data for this entry
        hass.data[DOMAIN][entry.entry_id] = {
            "storage": storage,
            "config": entry.data,
        }
        
        try:
            # Register device
            await _register_ir_controller_device(hass, entry)
            _LOGGER.info("Controller device registered")
            
            # Setup event handler for ZHA events
            await _setup_zha_event_handler(hass, entry)
            _LOGGER.info("ZHA event handler setup")
            
            # Create virtual devices
            await _create_virtual_devices(hass, entry, storage)
            _LOGGER.info("Virtual devices created")
            
            # Forward to platforms
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            _LOGGER.info("Platforms loaded")
            
        except Exception as e:
            _LOGGER.error("Error during entry setup: %s", e, exc_info=True)
            return False
        
        _LOGGER.info("IR Remote entry setup completed: %s", entry.title)
        return True
        
    except Exception as e:
        _LOGGER.error("Unexpected error in async_setup_entry: %s", e, exc_info=True)
        return False


async def _handle_device_addition(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle device addition from config flow."""
    controller_id = entry.data[CONF_CONTROLLER_ID]
    device_name = entry.data[CONF_DEVICE_NAME]
    
    _LOGGER.info("Adding device: %s to controller %s", device_name, controller_id)
    
    # Get the controller's storage
    entry_data = hass.data[DOMAIN].get(controller_id)
    if not entry_data:
        _LOGGER.error("Controller %s not found for device addition", controller_id)
        return
    
    storage = entry_data["storage"]
    
    # Generate device ID
    device_id = device_name.lower().replace(" ", "_").replace("-", "_")
    
    # Add device
    success = await storage.async_add_device(controller_id, device_id, device_name)
    if success:
        _LOGGER.info("Successfully added device: %s", device_name)
        # Reload the controller config entry to create new entities
        config_entry = hass.config_entries.async_get_entry(controller_id)
        if config_entry:
            await hass.config_entries.async_reload(controller_id)
    else:
        _LOGGER.error("Failed to add device: %s", device_name)


async def _handle_command_learning_start(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle command learning start from config flow."""
    controller_id = entry.data[CONF_CONTROLLER_ID]
    device_name = entry.data[CONF_DEVICE_NAME]
    command_name = entry.data[CONF_COMMAND_NAME]
    
    _LOGGER.info("Starting command learning: %s - %s for controller %s", device_name, command_name, controller_id)
    
    # Get the controller's storage
    entry_data = hass.data[DOMAIN].get(controller_id)
    if not entry_data:
        _LOGGER.error("Controller %s not found for command learning", controller_id)
        return
    
    storage = entry_data["storage"]
    
    # Generate IDs
    device_id = device_name.lower().replace(" ", "_").replace("-", "_")
    command_id = command_name.lower().replace(" ", "_").replace("-", "_")
    
    # Ensure device exists
    devices = storage.get_devices(controller_id)
    device_exists = any(d["id"] == device_id for d in devices)
    
    if not device_exists:
        # Add device first
        success = await storage.async_add_device(controller_id, device_id, device_name)
        if not success:
            _LOGGER.error("Failed to create device for command learning")
            return
    
    # Get controller data for ZHA command
    controller = storage.get_controller(controller_id)
    if not controller:
        _LOGGER.error("Controller data not found: %s", controller_id)
        return
    
    try:
        # Send ZHA command to start learning
        await hass.services.async_call(
            "zha",
            "issue_zigbee_cluster_command",
            {
                "ieee": controller["ieee"],
                "endpoint_id": controller["endpoint_id"],
                "cluster_id": controller["cluster_id"],
                "cluster_type": DEFAULT_CLUSTER_TYPE,
                "command": ZHA_COMMAND_LEARN,
                "command_type": DEFAULT_COMMAND_TYPE,
                "params": {
                    "controller_id": controller_id,
                    "device_id": device_id,
                    "command_id": command_id,
                    "command_name": command_name
                }
            },
            blocking=True
        )
        _LOGGER.info("Learning command sent for %s - %s", device_name, command_name)
    except Exception as e:
        _LOGGER.error("Failed to start learning: %s", e)


async def _register_services(hass: HomeAssistant) -> None:
    """Register services for IR Remote."""
    
    async def learn_command_service(call: ServiceCall) -> None:
        """Service to learn IR command."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]
        command_id = call.data[ATTR_COMMAND]
        
        _LOGGER.info("Learning command: %s - %s", device_id, command_id)
        
        # Get storage and controller
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            return
        
        storage = entry_data["storage"]
        controller = storage.get_controller(controller_id)
        
        if not controller:
            _LOGGER.error("Controller data not found: %s", controller_id)
            return
        
        try:
            # Send ZHA command to start learning
            await hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": controller["ieee"],
                    "endpoint_id": controller["endpoint_id"],
                    "cluster_id": controller["cluster_id"],
                    "cluster_type": DEFAULT_CLUSTER_TYPE,
                    "command": ZHA_COMMAND_LEARN,
                    "command_type": DEFAULT_COMMAND_TYPE,
                    "params": {
                        "controller_id": controller_id,
                        "device_id": device_id,
                        "command_id": command_id
                    }
                },
                blocking=True
            )
            _LOGGER.info("Learning command sent for %s - %s", device_id, command_id)
        except Exception as e:
            _LOGGER.error("Failed to send learning command: %s", e)
            raise HomeAssistantError(f"Failed to start learning: {e}") from e
    
    async def send_code_service(call: ServiceCall) -> None:
        """Service to send IR code."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        code = call.data[ATTR_CODE]
        
        _LOGGER.debug("Sending IR code (length: %d)", len(code))
        
        # Get controller config
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            return
        
        storage = entry_data["storage"]
        controller = storage.get_controller(controller_id)
        
        if not controller:
            _LOGGER.error("Controller data not found: %s", controller_id)
            return
        
        try:
            # Send ZHA command
            await hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": controller["ieee"],
                    "endpoint_id": controller["endpoint_id"],
                    "cluster_id": controller["cluster_id"],
                    "cluster_type": DEFAULT_CLUSTER_TYPE,
                    "command": ZHA_COMMAND_SEND,
                    "command_type": DEFAULT_COMMAND_TYPE,
                    "params": {"code": code}
                },
                blocking=True
            )
            _LOGGER.info("IR code sent successfully")
        except Exception as e:
            _LOGGER.error("Failed to send IR code: %s", e)
            raise HomeAssistantError(f"Failed to send IR code: {e}") from e
    
    async def send_command_service(call: ServiceCall) -> None:
        """Service to send command by name."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]
        command_id = call.data[ATTR_COMMAND]
        
        _LOGGER.info("Sending command: %s - %s", device_id, command_id)
        
        # Get storage
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            return
        
        storage = entry_data["storage"]
        
        # Get command code
        code = storage.get_command_code(controller_id, device_id, command_id)
        if not code:
            _LOGGER.error("Command code not found: %s - %s", device_id, command_id)
            return
        
        # Send the code
        await send_code_service(ServiceCall(DOMAIN, SERVICE_SEND_CODE, {
            ATTR_CONTROLLER_ID: controller_id,
            ATTR_CODE: code
        }))
    
    async def add_device_service(call: ServiceCall) -> None:
        """Service to add virtual device."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_name = call.data[ATTR_DEVICE_NAME]
        
        _LOGGER.info("Adding device: %s to controller %s", device_name, controller_id)
        
        # Get storage
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            return
        
        storage = entry_data["storage"]
        
        # Generate device ID
        device_id = device_name.lower().replace(" ", "_").replace("-", "_")
        
        # Add device
        success = await storage.async_add_device(controller_id, device_id, device_name)
        if success:
            # Reload the config entry to create new entities
            config_entry = hass.config_entries.async_get_entry(controller_id)
            if config_entry:
                await hass.config_entries.async_reload(controller_id)
        else:
            _LOGGER.error("Failed to add device: %s", device_name)
    
    async def add_command_service(call: ServiceCall) -> None:
        """Service to add command."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]
        command_name = call.data[ATTR_COMMAND_NAME]
        code = call.data[ATTR_CODE]
        
        _LOGGER.info("Adding command: %s to device %s", command_name, device_id)
        
        # Get storage
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            return
        
        storage = entry_data["storage"]
        
        # Generate command ID
        command_id = command_name.lower().replace(" ", "_").replace("-", "_")
        
        # Add command
        success = await storage.async_add_command(controller_id, device_id, command_id, command_name, code)
        if success:
            # Reload the config entry to create new entities
            config_entry = hass.config_entries.async_get_entry(controller_id)
            if config_entry:
                await hass.config_entries.async_reload(controller_id)
        else:
            _LOGGER.error("Failed to add command: %s", command_name)
    
    async def get_data_service(call: ServiceCall) -> Dict[str, Any]:
        """Service to get IR Remote data."""
        controller_id = call.data.get(ATTR_CONTROLLER_ID)
        
        if controller_id:
            # Get data for specific controller
            entry_data = hass.data[DOMAIN].get(controller_id)
            if not entry_data:
                return {"error": "Controller not found"}
            
            storage = entry_data["storage"]
            controller = storage.get_controller(controller_id)
            return {"controller": controller}
        else:
            # Get data for all controllers
            all_data = {}
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if isinstance(entry_data, dict) and "storage" in entry_data:
                    storage = entry_data["storage"]
                    controllers = storage.get_controllers()
                    all_data[entry_id] = controllers
            return all_data
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_LEARN_COMMAND, learn_command_service, schema=LEARN_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_CODE, send_code_service, schema=SEND_CODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, send_command_service, schema=SEND_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_DEVICE, add_device_service, schema=ADD_DEVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_COMMAND, add_command_service, schema=ADD_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_DATA, get_data_service, schema=GET_DATA_SCHEMA, supports_response=True
    )
    
    _LOGGER.info("IR Remote services registered")


async def _setup_zha_event_handler(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup ZHA event handler for IR learning."""
    
    async def handle_zha_event(event) -> None:
        """Handle ZHA events for IR code learning."""
        device_ieee = event.data.get("device_ieee")
        endpoint_id = event.data.get("endpoint_id")
        cluster_id = event.data.get("cluster_id")
        args = event.data.get("args", {})
        
        # Check if this event is from our controller
        if (device_ieee == entry.data[CONF_IEEE] and
            endpoint_id == entry.data.get(CONF_ENDPOINT, 1) and
            cluster_id == entry.data.get(CONF_CLUSTER, 57348)):
            
            _LOGGER.info("Received ZHA event from IR controller")
            
            # Check if this is a learned IR code
            if "code" in args:
                controller_id = args.get("controller_id", entry.entry_id)
                device_id = args.get("device_id")
                command_id = args.get("command_id")
                command_name = args.get("command_name", command_id)
                ir_code = args["code"]
                
                _LOGGER.info("Learned IR code: %s - %s (length: %d)", 
                           device_id, command_name, len(ir_code))
                
                # Save the learned code
                entry_data = hass.data[DOMAIN].get(controller_id)
                if entry_data:
                    storage = entry_data["storage"]
                    success = await storage.async_add_command(
                        controller_id, device_id, command_id, command_name, ir_code
                    )
                    
                    if success:
                        _LOGGER.info("Successfully saved learned command")
                        # Reload config entry to create button entity
                        await hass.config_entries.async_reload(controller_id)
                    else:
                        _LOGGER.error("Failed to save learned command")
    
    # Register event listener
    remove_listener = hass.bus.async_listen("zha_event", handle_zha_event)
    
    # Store listener remover
    hass.data[DOMAIN][entry.entry_id]["zha_listener"] = remove_listener


async def _register_ir_controller_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register IR controller device in device registry."""
    device_registry = dr.async_get(hass)
    
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL_CONTROLLER,
        sw_version="2.0.0",
    )
    
    _LOGGER.debug("Registered IR controller device: %s", entry.title)


async def _create_virtual_devices(hass: HomeAssistant, entry: ConfigEntry, storage: IRRemoteStorage) -> None:
    """Create virtual devices in device registry."""
    device_registry = dr.async_get(hass)
    controller_id = entry.entry_id
    
    # Get devices from storage
    devices = storage.get_devices(controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        
        # Create virtual device
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_VIRTUAL_DEVICE,
            via_device=(DOMAIN, controller_id),
        )
        
        _LOGGER.debug("Created virtual device: %s", device_name)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading IR Remote entry: %s", entry.title)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove ZHA event listener
        entry_data = hass.data[DOMAIN].get(entry.entry_id)
        if entry_data and "zha_listener" in entry_data:
            entry_data["zha_listener"]()
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # Remove services if no more entries
        if not hass.data[DOMAIN]:
            services = [
                SERVICE_LEARN_COMMAND, SERVICE_SEND_CODE, SERVICE_SEND_COMMAND,
                SERVICE_ADD_DEVICE, SERVICE_ADD_COMMAND, SERVICE_GET_DATA
            ]
            for service in services:
                hass.services.async_remove(DOMAIN, service)
            
            _LOGGER.info("Removed IR Remote services")
    
    _LOGGER.info("IR Remote entry unloaded: %s", unload_ok)
    return unload_ok
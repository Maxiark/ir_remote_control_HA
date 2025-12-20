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
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    CONF_ROOM_NAME,
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
    DEVICE_TYPE_UNIVERSAL,
)
from .data import IRRemoteStorage

_LOGGER = logging.getLogger(__name__)

# Platforms to load - REMOTE удалён!
PLATFORMS = [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.CLIMATE]

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
    
    # НЕ регистрируем сервисы здесь - они будут регистрироваться в async_setup_entry
    
    _LOGGER.info("IR Remote integration setup completed")
    return True


def _is_real_controller_entry(entry_data: Dict[str, Any]) -> bool:
    """Check if config entry is a real controller (not temporary from config flow)."""
    if not isinstance(entry_data, dict):
        return False
    
    # Проверяем, что это не временная запись из config flow
    config = entry_data.get("config", {})
    if config.get("action") in ["device_added", "command_learning_started"]:
        return False
    
    # Проверяем, что есть storage
    return "storage" in entry_data


def _count_active_controllers(hass: HomeAssistant) -> int:
    """Count active controller entries (excluding temporary config flow entries)."""
    count = 0
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if _is_real_controller_entry(entry_data):
            count += 1
    return count


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.info("Setting up IR Remote entry: %s", entry.title)
    
    # Check ZHA availability
    if "zha" not in hass.data:
        _LOGGER.error("ZHA integration not found")
        raise ConfigEntryNotReady("ZHA integration not available")
    
    # Skip setup for temporary config flow entries
    if entry.data.get("action") in ["device_added", "command_learning_started"]:
        # This is a temporary entry from config flow, remove it
        _LOGGER.debug("Removing temporary config flow entry: %s", entry.data.get("action"))
        await hass.config_entries.async_remove(entry.entry_id)
        return True
    
    # Initialize storage for this controller
    storage = IRRemoteStorage(hass)
    await storage.async_load()
    
    # Add controller to storage if not exists
    controller_id = entry.entry_id
    ieee = entry.data[CONF_IEEE]
    room_name = entry.data[CONF_ROOM_NAME]
    endpoint_id = entry.data.get(CONF_ENDPOINT, 1)
    cluster_id = entry.data.get(CONF_CLUSTER, 57348)
    
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
    
    # Store data for this entry
    hass.data[DOMAIN][entry.entry_id] = {
        "storage": storage,
        "config": entry.data,
    }
    
    # Регистрируем сервисы только при добавлении первого реального контроллера
    active_controllers_count = _count_active_controllers(hass)
    _LOGGER.debug("Active controllers count: %d", active_controllers_count)
    
    if active_controllers_count == 1:
        _LOGGER.info("Registering IR Remote services (first controller)")
        await _register_services(hass)
    else:
        _LOGGER.debug("Services already registered, skipping registration")
    
    # Register device
    await _register_ir_controller_device(hass, entry)
    
    # Setup event handler for ZHA events
    await _setup_zha_event_handler(hass, entry)
    
    # Create virtual devices
    await _create_virtual_devices(hass, entry, storage)
    
    # Migrate old Remote entities to Media Player for Universal devices
    _LOGGER.debug("Starting migration from Remote to Media Player")
    await _migrate_remote_to_media_player(hass, controller_id, storage)
    
    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("IR Remote entry setup completed: %s", entry.title)
    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register services for IR Remote."""
    _LOGGER.debug("Starting service registration")
    
    async def learn_command_service(call: ServiceCall) -> None:
        """Service to learn IR command."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]
        command_id = call.data[ATTR_COMMAND]
        
        _LOGGER.info("Learning command: %s - %s (controller: %s)", device_id, command_id, controller_id)
        
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
        
        _LOGGER.debug("Controller info: ieee=%s, endpoint=%s, cluster=%s", 
                     controller["ieee"], controller["endpoint_id"], controller["cluster_id"])
        
        try:
            # Send ZHA command to start learning (always with on_off: true)
            zha_params = {
                "ieee": controller["ieee"],
                "endpoint_id": controller["endpoint_id"],
                "cluster_id": controller["cluster_id"],
                "cluster_type": DEFAULT_CLUSTER_TYPE,
                "command": ZHA_COMMAND_LEARN,
                "command_type": DEFAULT_COMMAND_TYPE,
                "params": {
                    "on_off": True  # Always required for IR learning
                }
            }
            
            _LOGGER.debug("Sending ZHA learning command with params: %s", zha_params)
            
            await hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                zha_params,
                blocking=True
            )
            _LOGGER.info("Learning mode activated for %s - %s", device_id, command_id)
            
            # Wait for user to press the button on original remote
            await asyncio.sleep(10)
            
            # Read the learned IR code from attribute 0
            _LOGGER.debug("Reading learned IR code from attribute 0")
            
            result = await hass.services.async_call(
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
            
            _LOGGER.debug("ZHA toolkit response: %s", result)
            
            ir_code = None
            if result and "result_read" in result:
                # result_read is a tuple: (dict_with_attributes, dict_with_other_data)
                result_read = result["result_read"]
                if isinstance(result_read, (list, tuple)) and len(result_read) > 0:
                    attributes_dict = result_read[0]
                    if isinstance(attributes_dict, dict) and 0 in attributes_dict:
                        ir_code = attributes_dict[0]
                        _LOGGER.info("Successfully read IR code from attribute 0 (length: %d)", len(str(ir_code)))
            
            if ir_code:
                # Save the learned code
                success = await storage.async_add_command(
                    controller_id, device_id, command_id, command_id, str(ir_code)
                )
                
                if success:
                    _LOGGER.info("Successfully saved learned command: %s - %s", device_id, command_id)
                    # Reload config entry to create button entity and update media player
                    config_entry = hass.config_entries.async_get_entry(controller_id)
                    if config_entry:
                        await hass.config_entries.async_reload(controller_id)
                else:
                    _LOGGER.error("Failed to save learned command")
                    raise HomeAssistantError("Failed to save learned command")
            else:
                _LOGGER.error("No IR code found in response. Full response: %s", result)
                raise HomeAssistantError("No IR code received during learning")
                
        except Exception as e:
            _LOGGER.error("Failed to learn IR command: %s", e, exc_info=True)
            raise HomeAssistantError(f"Failed to learn IR command: {e}") from e
    
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
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_CODE,
            {
                ATTR_CONTROLLER_ID: controller_id,
                ATTR_CODE: code
            },
            blocking=True
        )
    
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
        success = await storage.async_add_device(controller_id, device_id, device_name, DEVICE_TYPE_UNIVERSAL)
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
            # Reload the config entry to create new button entity and update media player
            config_entry = hass.config_entries.async_get_entry(controller_id)
            if config_entry:
                await hass.config_entries.async_reload(controller_id)
        else:
            _LOGGER.error("Failed to add command: %s", command_name)
    
    async def remove_device_service(call: ServiceCall) -> None:
        """Service to remove virtual device."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]

        _LOGGER.info("Removing device: %s from controller %s", device_id, controller_id)

        # Get storage
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            raise HomeAssistantError(f"Controller {controller_id} not found")

        storage = entry_data["storage"]

        # Get all commands for this device before removal (for entity cleanup)
        commands = storage.get_commands(controller_id, device_id)

        # Remove device from storage
        success = await storage.async_remove_device(controller_id, device_id)
        if success:
            _LOGGER.info("Successfully removed device: %s", device_id)

            # Clean up entities from Entity Registry
            await _cleanup_device_entities(hass, controller_id, device_id, commands)

            # Clean up device from Device Registry
            await _cleanup_virtual_device(hass, controller_id, device_id)
            # Reload integration to update entities
            config_entry = hass.config_entries.async_get_entry(controller_id) 
            if config_entry:
                await hass.config_entries.async_reload(controller_id)
                
        else:
            _LOGGER.error("Failed to remove device: %s", device_id)
            raise HomeAssistantError(f"Failed to remove device {device_id}")

    async def remove_command_service(call: ServiceCall) -> None:
        """Service to remove command."""
        controller_id = call.data[ATTR_CONTROLLER_ID]
        device_id = call.data[ATTR_DEVICE]
        command_id = call.data[ATTR_COMMAND]

        _LOGGER.info("Removing command: %s from device %s", command_id, device_id)

        # Get storage
        entry_data = hass.data[DOMAIN].get(controller_id)
        if not entry_data:
            _LOGGER.error("Controller %s not found", controller_id)
            raise HomeAssistantError(f"Controller {controller_id} not found")

        storage = entry_data["storage"]

        # Remove command from storage
        success = await storage.async_remove_command(controller_id, device_id, command_id)
        if success:
            _LOGGER.info("Successfully removed command: %s", command_id)

            # Clean up entity from Entity Registry
            await _cleanup_command_entity(hass, controller_id, device_id, command_id)
            # Reload integration to update entities (including media player source list)
            config_entry = hass.config_entries.async_get_entry(controller_id)
            if config_entry:
                await hass.config_entries.async_reload(controller_id)

        else:
            _LOGGER.error("Failed to remove command: %s", command_id)
            raise HomeAssistantError(f"Failed to remove command {command_id}")

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
                if _is_real_controller_entry(entry_data):
                    storage = entry_data["storage"]
                    controllers = storage.get_controllers()
                    all_data[entry_id] = controllers
            return all_data
    
    # Register services
    services_to_register = [
        (SERVICE_LEARN_COMMAND, learn_command_service, LEARN_COMMAND_SCHEMA),
        (SERVICE_SEND_CODE, send_code_service, SEND_CODE_SCHEMA),
        (SERVICE_SEND_COMMAND, send_command_service, SEND_COMMAND_SCHEMA),
        (SERVICE_ADD_DEVICE, add_device_service, ADD_DEVICE_SCHEMA),
        (SERVICE_ADD_COMMAND, add_command_service, ADD_COMMAND_SCHEMA),
        (SERVICE_REMOVE_DEVICE, remove_device_service, REMOVE_DEVICE_SCHEMA),
        (SERVICE_REMOVE_COMMAND, remove_command_service, REMOVE_COMMAND_SCHEMA),
        (SERVICE_GET_DATA, get_data_service, GET_DATA_SCHEMA),
    ]
    
    for service_name, service_func, schema in services_to_register:
        if hass.services.has_service(DOMAIN, service_name):
            _LOGGER.debug("Service %s already exists, skipping", service_name)
            continue
        
        extra_kwargs = {}
        if service_name == SERVICE_GET_DATA:
            extra_kwargs["supports_response"] = True
        
        hass.services.async_register(
            DOMAIN, service_name, service_func, schema=schema, **extra_kwargs
        )
        _LOGGER.debug("Registered service: %s", service_name)
    
    _LOGGER.info("IR Remote services registration completed")


async def _setup_zha_event_handler(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup ZHA event handler for IR learning."""
    # IR learning now uses direct attribute reading instead of events
    # This function is kept for compatibility but does nothing
    _LOGGER.debug("ZHA event handler setup (using direct attribute reading)")
    
    # Store empty listener remover for compatibility
    hass.data[DOMAIN][entry.entry_id]["zha_listener"] = lambda: None


async def _register_ir_controller_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register IR controller device in device registry."""
    device_registry = dr.async_get(hass)
    
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL_CONTROLLER,
        sw_version="2.1.0",
    )
    
    _LOGGER.debug("Registered IR controller device: %s", entry.title)


async def _migrate_remote_to_media_player(hass: HomeAssistant, controller_id: str, storage: IRRemoteStorage) -> None:
    """Migrate old Remote entities to Media Player for Universal devices.
    
    This function removes old remote.* entities for Universal type devices.
    Media Player entities will be created automatically by the platform.
    """
    entity_registry = er.async_get(hass)
    
    # Get all Universal devices for this controller
    devices = storage.get_devices(controller_id)
    universal_devices = [d for d in devices if d.get("type") == DEVICE_TYPE_UNIVERSAL]
    
    if not universal_devices:
        _LOGGER.debug("No Universal devices found for migration")
        return
    
    migrated_count = 0
    
    for device in universal_devices:
        device_id = device["id"]
        device_name = device["name"]
        
        # Check if old Remote entity exists
        old_remote_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_remote"
        old_remote_entity_id = entity_registry.async_get_entity_id("remote", DOMAIN, old_remote_unique_id)
        
        if old_remote_entity_id:
            _LOGGER.info("Migrating device '%s': removing old Remote entity %s", device_name, old_remote_entity_id)
            entity_registry.async_remove(old_remote_entity_id)
            migrated_count += 1
            _LOGGER.debug("Removed old Remote entity: %s", old_remote_entity_id)
    
    if migrated_count > 0:
        _LOGGER.info("Migration completed: removed %d old Remote entities. Media Player entities will be created automatically.", migrated_count)
    else:
        _LOGGER.debug("Migration: no old Remote entities found")


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

async def _cleanup_command_entity(hass: HomeAssistant, controller_id: str, device_id: str, command_id: str) -> None:
    """Remove command button entity from Entity Registry."""
    entity_registry = er.async_get(hass)

    # Unique ID for command button
    unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"

    # Find and remove entity
    entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
    if entity_id:
        entity_registry.async_remove(entity_id)
        _LOGGER.debug("Removed command entity: %s", entity_id)
    else:
        _LOGGER.debug("Command entity not found for cleanup: %s", unique_id)


async def _cleanup_device_entities(hass: HomeAssistant, controller_id: str, device_id: str, commands: list) -> None:
    """Remove all button entities for a device from Entity Registry."""
    entity_registry = er.async_get(hass)

    # Remove all command button entities
    for command in commands:
        command_id = command["id"]
        unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"

        entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)
            _LOGGER.debug("Removed command entity: %s", entity_id)

    # Remove media player entity (было remote, теперь media_player для universal)
    media_player_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_player"
    media_player_entity_id = entity_registry.async_get_entity_id("media_player", DOMAIN, media_player_unique_id)
    if media_player_entity_id:
        entity_registry.async_remove(media_player_entity_id)
        _LOGGER.debug("Removed media player entity: %s", media_player_entity_id)
    
    # Remove climate entity if exists
    climate_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_climate"
    climate_entity_id = entity_registry.async_get_entity_id("climate", DOMAIN, climate_unique_id)
    if climate_entity_id:
        entity_registry.async_remove(climate_entity_id)
        _LOGGER.debug("Removed climate entity: %s", climate_entity_id)


async def _cleanup_virtual_device(hass: HomeAssistant, controller_id: str, device_id: str) -> None:
    """Remove virtual device from Device Registry."""
    device_registry = dr.async_get(hass)

    # Device identifier for virtual device
    device_identifier = (DOMAIN, f"{controller_id}_{device_id}")

    # Find and remove device
    device_entry = device_registry.async_get_device(identifiers={device_identifier})
    if device_entry:
        device_registry.async_remove_device(device_entry.id)
        _LOGGER.debug("Removed virtual device: %s", device_entry.name)
    else:
        _LOGGER.debug("Virtual device not found for cleanup: %s", device_identifier)

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
            _LOGGER.debug("Removed ZHA event listener for %s", entry.entry_id)
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # Подсчитываем оставшиеся активные контроллеры
        active_controllers_count = _count_active_controllers(hass)
        _LOGGER.debug("Active controllers count after removal: %d", active_controllers_count)
        
        # Remove services if no more active controllers
        if active_controllers_count == 0:
            _LOGGER.info("Removing IR Remote services (no active controllers)")
            services = [
                SERVICE_LEARN_COMMAND, SERVICE_SEND_CODE, SERVICE_SEND_COMMAND,
                SERVICE_ADD_DEVICE, SERVICE_ADD_COMMAND, SERVICE_REMOVE_DEVICE,
                SERVICE_REMOVE_COMMAND, SERVICE_GET_DATA
            ]
            for service in services:
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
                    _LOGGER.debug("Removed service: %s", service)
                else:
                    _LOGGER.debug("Service %s was not registered", service)
            
            _LOGGER.info("All IR Remote services removed")
        else:
            _LOGGER.debug("Services kept (still have %d active controllers)", active_controllers_count)
    
    _LOGGER.info("IR Remote entry unloaded: %s", unload_ok)
    return unload_ok
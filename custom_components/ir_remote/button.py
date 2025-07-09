"""Button platform for IR Remote integration."""
import logging
from typing import Any, List

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    ATTR_CONTROLLER_ID,
    ATTR_CODE,
    SERVICE_SEND_CODE,
    MANUFACTURER,
    MODEL_VIRTUAL_DEVICE,
    TRANSLATION_KEY_ADD_COMMAND,
    TRANSLATION_KEY_DEVICE_COMMAND,
)
from .data import IRRemoteStorage

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote button entities."""
    _LOGGER.info("Button platform: Starting setup for: %s", config_entry.title)
    
    # Get storage for this controller
    entry_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not entry_data:
        _LOGGER.error("Button platform: No entry data found for %s", config_entry.entry_id)
        return
    
    _LOGGER.info("Button platform: Got entry data")
    
    storage: IRRemoteStorage = entry_data["storage"]
    controller_id = config_entry.entry_id
    
    # Get controller data
    controller = storage.get_controller(controller_id)
    if not controller:
        _LOGGER.warning("Button platform: No controller data found for %s", controller_id)
        return
    
    _LOGGER.info("Button platform: Got controller data")
    
    buttons: List[ButtonEntity] = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.info("Button platform: Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        
        _LOGGER.debug("Button platform: Processing device: %s (%s)", device_name, device_id)
        
        # Create "Add Command" button for this device
        add_command_button = IRRemoteAddCommandButton(
            hass=hass,
            config_entry=config_entry,
            controller_id=controller_id,
            device_id=device_id,
            device_name=device_name,
        )
        buttons.append(add_command_button)
        _LOGGER.debug("Button platform: Created add command button for device %s", device_name)
        
        # Get all commands for this device
        commands = storage.get_commands(controller_id, device_id)
        _LOGGER.debug("Button platform: Found %d commands for device %s", len(commands), device_name)
        
        for command in commands:
            command_id = command["id"]
            command_name = command["name"]
            command_code = command["code"]
            
            # Create command button
            command_button = IRRemoteCommandButton(
                hass=hass,
                config_entry=config_entry,
                controller_id=controller_id,
                device_id=device_id,
                device_name=device_name,
                command_id=command_id,
                command_name=command_name,
                command_code=command_code,
            )
            buttons.append(command_button)
            _LOGGER.debug("Button platform: Created command button: %s - %s", device_name, command_name)
    
    _LOGGER.info("Button platform: Created %d buttons for controller %s", len(buttons), controller_id)
    
    # Add all buttons
    _LOGGER.info("Button platform: Adding entities to HA...")
    async_add_entities(buttons)
    _LOGGER.info("Button platform: Setup completed for %s", config_entry.title)


class IRRemoteCommandButton(ButtonEntity):
    """Button entity for IR command."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
        command_id: str,
        command_name: str,
        command_code: str,
    ) -> None:
        """Initialize the command button."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        self._command_id = command_id
        self._command_name = command_name
        self._command_code = command_code
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_{command_id}"
        self._attr_name = command_name
        self._attr_translation_key = TRANSLATION_KEY_DEVICE_COMMAND
        self._attr_should_poll = False
        
        # Device info - link to virtual device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_VIRTUAL_DEVICE,
            via_device=(DOMAIN, controller_id),
        )
        
        _LOGGER.debug("Initialized command button: %s - %s", device_name, command_name)
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the button."""
        # You can customize icons based on command name
        command_lower = self._command_name.lower()
        
        if "power" in command_lower or "on" in command_lower or "off" in command_lower:
            return "mdi:power"
        elif "volume" in command_lower or "vol" in command_lower:
            if "+" in command_lower or "up" in command_lower:
                return "mdi:volume-plus"
            elif "-" in command_lower or "down" in command_lower:
                return "mdi:volume-minus"
            else:
                return "mdi:volume-high"
        elif "channel" in command_lower or "ch" in command_lower:
            return "mdi:television-guide"
        elif "mute" in command_lower:
            return "mdi:volume-mute"
        elif "play" in command_lower:
            return "mdi:play"
        elif "pause" in command_lower:
            return "mdi:pause"
        elif "stop" in command_lower:
            return "mdi:stop"
        else:
            return "mdi:remote"
    
    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info("Pressed button: %s - %s", self._device_name, self._command_name)
        
        try:
            # Try using service first, fallback to direct ZHA call
            if self.hass.services.has_service("ir_remote", "send_code"):
                await self.hass.services.async_call(
                    "ir_remote",
                    "send_code",
                    {
                        "controller_id": self._controller_id,
                        "code": self._command_code,
                    },
                    blocking=True
                )
                _LOGGER.debug("Successfully sent IR code via service for %s - %s", 
                             self._device_name, self._command_name)
            else:
                # Direct ZHA call as fallback
                await self._send_code_directly()
                
        except Exception as e:
            _LOGGER.error("Failed to send IR code for %s - %s: %s", 
                         self._device_name, self._command_name, e)
    
    async def _send_code_directly(self) -> None:
        """Send IR code directly via ZHA."""
        try:
            # Get controller data from integration
            entry_data = self.hass.data.get("ir_remote", {}).get(self._controller_id)
            if not entry_data:
                _LOGGER.error("Controller data not found for %s", self._controller_id)
                return
            
            storage = entry_data["storage"]
            controller = storage.get_controller(self._controller_id)
            
            if not controller:
                _LOGGER.error("Controller not found in storage: %s", self._controller_id)
                return
            
            # Send ZHA command directly (like in your script)
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": controller["ieee"],
                    "endpoint_id": controller["endpoint_id"],
                    "cluster_id": controller["cluster_id"],
                    "cluster_type": "in",
                    "command": 2,  # Command for sending (as in your script)
                    "command_type": "server",
                    "params": {
                        "code": self._command_code
                    }
                },
                blocking=True
            )
            _LOGGER.info("Successfully sent IR code directly via ZHA for %s - %s", 
                        self._device_name, self._command_name)
            
        except Exception as e:
            _LOGGER.error("Failed to send IR code directly: %s", e)


class IRRemoteAddCommandButton(ButtonEntity):
    """Button entity for adding new commands."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the add command button."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_add_command"
        self._attr_name = f"Добавить команду"
        self._attr_translation_key = TRANSLATION_KEY_ADD_COMMAND
        self._attr_should_poll = False
        
        # Device info - link to virtual device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_VIRTUAL_DEVICE,
            via_device=(DOMAIN, controller_id),
        )
        
        _LOGGER.debug("Initialized add command button for device: %s", device_name)
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the button."""
        return "mdi:plus-circle"
    
    async def async_press(self) -> None:
        """Handle button press - show instructions for adding command."""
        _LOGGER.info("Pressed add command button for device: %s", self._device_name)
        
        # For now, just log the action
        # Users will need to use config flow or services to add commands
        _LOGGER.info("To add commands, use the integration configuration or Developer Tools services")
        
        # TODO: Future improvement - create a service call or notification
        # For now, this is a placeholder for manual command addition
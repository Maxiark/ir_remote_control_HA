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
    _LOGGER.info("Setting up IR Remote buttons for: %s", config_entry.title)
    
    # Get storage for this controller
    entry_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not entry_data:
        _LOGGER.error("No entry data found for %s", config_entry.entry_id)
        return
    
    storage: IRRemoteStorage = entry_data["storage"]
    controller_id = config_entry.entry_id
    
    # Get controller data
    controller = storage.get_controller(controller_id)
    if not controller:
        _LOGGER.warning("No controller data found for %s", controller_id)
        return
    
    buttons: List[ButtonEntity] = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.debug("Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        
        _LOGGER.debug("Processing device: %s (%s)", device_name, device_id)
        
        # Get all commands for this device
        commands = storage.get_commands(controller_id, device_id)
        _LOGGER.debug("Found %d commands for device %s", len(commands), device_name)
        
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
            _LOGGER.debug("Created command button: %s - %s", device_name, command_name)
    
    _LOGGER.info("Created %d buttons for controller %s", len(buttons), controller_id)
    
    # Add all buttons
    async_add_entities(buttons)


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
            # Send IR code through service
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_CODE,
                {
                    ATTR_CONTROLLER_ID: self._controller_id,
                    ATTR_CODE: self._command_code,
                },
                blocking=True
            )
            _LOGGER.debug("Successfully sent IR code for %s - %s", 
                         self._device_name, self._command_name)
            
        except Exception as e:
            _LOGGER.error("Failed to send IR code for %s - %s: %s", 
                         self._device_name, self._command_name, e)
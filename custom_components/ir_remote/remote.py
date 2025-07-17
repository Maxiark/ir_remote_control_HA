"""Remote platform for IR Remote integration (Universal devices)."""
import logging
from typing import Any, Iterable, Optional

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    ATTR_CONTROLLER_ID,
    ATTR_DEVICE,
    ATTR_COMMAND,
    SERVICE_SEND_COMMAND,
    MANUFACTURER,
    MODEL_REMOTE_DEVICE,
    TRANSLATION_KEY_REMOTE_DEVICE,
    DEVICE_TYPE_UNIVERSAL,
    POWER_ON_COMMANDS,
    POWER_OFF_COMMANDS,
)
from .data import IRRemoteStorage

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote remote entities."""
    _LOGGER.info("Setting up IR Remote remotes for: %s", config_entry.title)
    
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
    
    remotes = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.debug("Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        device_type = device.get("type", "universal")
        
        _LOGGER.info("Processing device: %s (%s) - type: %s", device_name, device_id, device_type)
        
        # Only create remote entity for universal devices
        if device_type == DEVICE_TYPE_UNIVERSAL:
            _LOGGER.debug("Creating remote entity for device: %s", device_name)
            
            # Create remote entity for this device
            remote = IRRemoteDevice(
                hass=hass,
                config_entry=config_entry,
                controller_id=controller_id,
                device_id=device_id,
                device_name=device_name,
                storage=storage,
            )
            remotes.append(remote)
            _LOGGER.debug("Created remote entity for device %s", device_name)
    
    _LOGGER.info("Created %d remote entities for controller %s", len(remotes), controller_id)
    
    # Add all remotes
    async_add_entities(remotes)


class IRRemoteDevice(RemoteEntity):
    """Remote entity for universal IR devices."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
        storage: IRRemoteStorage,
    ) -> None:
        """Initialize the remote device."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        self._storage = storage
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_remote"
        self._attr_name = f"{device_name} Remote"
        self._attr_translation_key = TRANSLATION_KEY_REMOTE_DEVICE
        self._attr_should_poll = False
        
        # Device info - link to the same virtual device as buttons
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_REMOTE_DEVICE,
            via_device=(DOMAIN, controller_id),
        )
        
        # Track activity state
        self._is_on = None
        self._last_command = None
        
        # Initialize activity list
        self._update_activity_list()
        
        _LOGGER.debug("Initialized remote device: %s", device_name)
    
    def _update_activity_list(self) -> None:
        """Update activity list with current commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        self._attr_activity_list = [command["id"] for command in commands]
        _LOGGER.debug("Updated activity list for %s: %s", self._device_name, self._attr_activity_list)
    
    def _find_power_command(self, command_list: list) -> Optional[str]:
        """Find power command from available commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        available_commands = {cmd["id"].lower(): cmd["id"] for cmd in commands}
        
        for power_cmd in command_list:
            if power_cmd in available_commands:
                return available_commands[power_cmd]
        
        return None
    
    @property
    def is_on(self) -> Optional[bool]:
        """Return true if device is on."""
        return self._is_on
    
    @property
    def current_activity(self) -> Optional[str]:
        """Return current activity."""
        return self._last_command
    
    @property
    def activity_list(self) -> Optional[list]:
        """Return list of available activities."""
        # Refresh activity list in case commands were added
        self._update_activity_list()
        return self._attr_activity_list
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the remote."""
        return "mdi:remote"
    
    async def async_turn_on(self, activity: Optional[str] = None, **kwargs: Any) -> None:
        """Turn the device on."""
        _LOGGER.info("Turning on device: %s", self._device_name)
        
        # If specific activity provided, use it
        if activity:
            await self.async_send_command([activity])
            return
        
        # Find power on command
        power_on_command = self._find_power_command(POWER_ON_COMMANDS)
        
        if power_on_command:
            await self.async_send_command([power_on_command])
            self._is_on = True
            self._last_command = power_on_command
            self.async_write_ha_state()
            _LOGGER.info("Sent power on command: %s", power_on_command)
        else:
            _LOGGER.warning("No power on command found for device %s", self._device_name)
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        _LOGGER.info("Turning off device: %s", self._device_name)
        
        # Find power off command
        power_off_command = self._find_power_command(POWER_OFF_COMMANDS)
        
        if power_off_command:
            await self.async_send_command([power_off_command])
            self._is_on = False
            self._last_command = power_off_command
            self.async_write_ha_state()
            _LOGGER.info("Sent power off command: %s", power_off_command)
        else:
            _LOGGER.warning("No power off command found for device %s", self._device_name)
    
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send commands to device."""
        for cmd in command:
            _LOGGER.info("Sending command '%s' to device %s", cmd, self._device_name)
            
            try:
                # Use existing service to send command
                await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_SEND_COMMAND,
                    {
                        ATTR_CONTROLLER_ID: self._controller_id,
                        ATTR_DEVICE: self._device_id,
                        ATTR_COMMAND: cmd,
                    },
                    blocking=True
                )
                
                # Update activity state
                self._last_command = cmd
                
                # Update power state if this was a power command
                if cmd.lower() in POWER_ON_COMMANDS:
                    self._is_on = True
                elif cmd.lower() in POWER_OFF_COMMANDS:
                    self._is_on = False
                
                self.async_write_ha_state()
                _LOGGER.debug("Successfully sent command %s to %s", cmd, self._device_name)
                
            except Exception as e:
                _LOGGER.error("Failed to send command %s to %s: %s", cmd, self._device_name, e)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        # Получаем актуальный тип устройства из storage
        device_data = self._storage.get_device(self._controller_id, self._device_id)
        device_type = device_data.get("type", "universal") if device_data else "universal"
        
        return {
            "device_id": self._device_id,
            "controller_id": self._controller_id,
            "last_command": self._last_command,
            "available_commands": len(self._attr_activity_list or []),
            "device_type": device_type,
        }
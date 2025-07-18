"""Climate platform for IR Remote integration."""
import logging
from typing import Any, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature

from .const import (
    DOMAIN,
    ATTR_CONTROLLER_ID,
    ATTR_DEVICE,
    ATTR_COMMAND,
    SERVICE_SEND_COMMAND,
    MANUFACTURER,
    MODEL_CLIMATE,
    TRANSLATION_KEY_CLIMATE,
    DEVICE_TYPE_AC,
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
    """Set up IR Remote climate entities."""
    _LOGGER.info("Setting up IR Remote climate entities for: %s", config_entry.title)
    
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
    
    climate_entities = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.debug("Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        device_type = device.get("type", "universal")
        
        _LOGGER.info("Processing device: %s (%s) - type: %s", device_name, device_id, device_type)
        
        # Only create climate entity for AC devices
        if device_type == DEVICE_TYPE_AC:
            _LOGGER.debug("Creating climate entity for device: %s", device_name)
            
            # Create climate entity for this device
            climate_entity = IRClimate(
                hass=hass,
                config_entry=config_entry,
                controller_id=controller_id,
                device_id=device_id,
                device_name=device_name,
                storage=storage,
            )
            climate_entities.append(climate_entity)
            _LOGGER.debug("Created climate entity for device %s", device_name)
    
    _LOGGER.info("Created %d climate entities for controller %s", len(climate_entities), controller_id)
    
    # Add all climate entities
    async_add_entities(climate_entities)


class IRClimate(ClimateEntity):
    """Climate entity for IR air conditioners."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
        storage: IRRemoteStorage,
    ) -> None:
        """Initialize the climate entity."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        self._storage = storage
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_climate"
        self._attr_name = device_name
        self._attr_translation_key = TRANSLATION_KEY_CLIMATE
        self._attr_should_poll = False
        
        # Device info - link to the same virtual device as buttons
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_CLIMATE,
            via_device=(DOMAIN, controller_id),
        )
        
        # Climate settings - будут обновлены из доступных команд
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 1
        
        # Current state
        self._hvac_mode = HVACMode.OFF
        self._current_temperature = 22
        self._target_temperature = 22
        self._current_hvac_action = HVACAction.OFF
        self._fan_mode = "auto"
        
        # Available modes and features
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.AUTO,
            HVACMode.FAN_ONLY,
            HVACMode.DRY,
        ]
        
        self._attr_fan_modes = ["auto", "low", "medium", "high"]
        
        # Analyze available commands and set temperature range
        _LOGGER.info("Initializing climate entity: controller_id=%s, device_id=%s, device_name=%s", 
                    controller_id, device_id, device_name)
        self._update_temperature_range()
        
        # Set supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE |
            ClimateEntityFeature.TURN_ON |
            ClimateEntityFeature.TURN_OFF
        )
        
        _LOGGER.debug("Initialized climate entity: %s (temp range: %s-%s)", 
                     device_name, self._attr_min_temp, self._attr_max_temp)
    
    def _find_command(self, command_names: list) -> Optional[str]:
        """Find command from available commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        available_commands = {cmd["id"].lower(): cmd["id"] for cmd in commands}
        
        for cmd_name in command_names:
            if cmd_name.lower() in available_commands:
                return available_commands[cmd_name.lower()]
        
        return None
    
    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        return self._hvac_mode
    
    @property
    def hvac_action(self) -> HVACAction:
        """Return current action."""
        return self._current_hvac_action
    
    @property
    def current_temperature(self) -> Optional[float]:
        """Return current temperature."""
        return self._current_temperature
    
    @property
    def target_temperature(self) -> Optional[float]:
        """Return target temperature."""
        return self._target_temperature
    
    @property
    def fan_mode(self) -> Optional[str]:
        """Return current fan mode."""
        return self._fan_mode
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the climate entity."""
        return "mdi:air-conditioner"
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        _LOGGER.info("Setting HVAC mode to %s for %s", hvac_mode, self._device_name)
        
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        elif hvac_mode == HVACMode.COOL:
            command = self._find_command(["mode_cool", "cool", "cooling"])
        elif hvac_mode == HVACMode.HEAT:
            command = self._find_command(["mode_heat", "heat", "heating"])
        elif hvac_mode == HVACMode.AUTO:
            command = self._find_command(["mode_auto", "auto"])
        elif hvac_mode == HVACMode.FAN_ONLY:
            command = self._find_command(["mode_fan", "fan", "fan_only"])
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return
        
        if command:
            await self._send_command(command)
            self._hvac_mode = hvac_mode
            
            # Update action based on mode
            if hvac_mode == HVACMode.COOL:
                self._current_hvac_action = HVACAction.COOLING
            elif hvac_mode == HVACMode.HEAT:
                self._current_hvac_action = HVACAction.HEATING
            elif hvac_mode == HVACMode.FAN_ONLY:
                self._current_hvac_action = HVACAction.FAN
            else:
                self._current_hvac_action = HVACAction.IDLE
            
            self.async_write_ha_state()
            _LOGGER.info("Set HVAC mode to %s with command %s", hvac_mode, command)
        else:
            _LOGGER.warning("No command found for HVAC mode %s", hvac_mode)
    
    def _update_temperature_range(self) -> None:
        """Update temperature range based on available commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        temp_commands = []
        
        _LOGGER.debug("Analyzing commands for temperature range:")
        
        # Find all temperature commands with flexible patterns
        for command in commands:
            command_id = command["id"].lower()
            _LOGGER.debug("  Checking command: %s", command_id)
            
            # Extract temperature from various patterns
            temp_value = None
            
            # Pattern 1: temp_XX or temperature_XX
            if command_id.startswith("temp_") or command_id.startswith("temperature_"):
                try:
                    temp_value = int(command_id.split("_")[1])
                except (ValueError, IndexError):
                    continue
            
            # Pattern 2: tempXX or temperatureXX
            elif command_id.startswith("temp") and command_id[4:].isdigit():
                try:
                    temp_value = int(command_id[4:])
                except ValueError:
                    continue
            elif command_id.startswith("temperature") and command_id[11:].isdigit():
                try:
                    temp_value = int(command_id[11:])
                except ValueError:
                    continue
            
            # Pattern 3: XXc or XX°c (like 24c, 24°c)
            elif command_id.endswith("c") or command_id.endswith("°c"):
                try:
                    temp_str = command_id.replace("°c", "").replace("c", "")
                    if temp_str.isdigit():
                        temp_value = int(temp_str)
                except ValueError:
                    continue
            
            # Pattern 4: Pure numbers that might be temperature
            elif command_id.isdigit():
                try:
                    temp_value = int(command_id)
                    # Only consider reasonable temperature values
                    if 10 <= temp_value <= 40:
                        pass  # Keep this temperature
                    else:
                        temp_value = None
                except ValueError:
                    continue
            
            if temp_value is not None and 10 <= temp_value <= 40:
                temp_commands.append(temp_value)
                _LOGGER.debug("    Found temperature: %s°C", temp_value)
        
        if temp_commands:
            # Set range based on available commands
            self._attr_min_temp = min(temp_commands)
            self._attr_max_temp = max(temp_commands)
            _LOGGER.info("Found temperature commands for %s: %s°C to %s°C (commands: %s)", 
                        self._device_name, self._attr_min_temp, self._attr_max_temp, sorted(temp_commands))
        else:
            # Default range if no temp commands found
            self._attr_min_temp = 16
            self._attr_max_temp = 30
            _LOGGER.info("No temperature commands found for %s, using default range: %s-%s°C", 
                        self._device_name, self._attr_min_temp, self._attr_max_temp)
    
    def _find_temperature_command(self, temperature: int) -> Optional[str]:
        """Find exact temperature command with flexible matching."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        
        _LOGGER.debug("Looking for temperature %s°C. Available commands:", temperature)
        for command in commands:
            _LOGGER.debug("  - %s (%s)", command["id"], command["name"])
        
        # Try different naming patterns for temperature commands
        possible_names = [
            f"temp_{temperature}",           # temp_24
            f"temperature_{temperature}",    # temperature_24
            f"temp{temperature}",            # temp24
            f"temperature{temperature}",     # temperature24
            f"{temperature}c",               # 24c
            f"{temperature}°c",              # 24°c
            f"{temperature}",                # 24
        ]
        
        _LOGGER.debug("Searching for temperature commands: %s", possible_names)
        
        for command in commands:
            command_id_lower = command["id"].lower()
            
            # Check exact matches
            for possible_name in possible_names:
                if command_id_lower == possible_name.lower():
                    _LOGGER.info("Found temperature command: %s for %s°C", command["id"], temperature)
                    return command["id"]
            
            # Check if command contains temperature value
            if str(temperature) in command_id_lower and any(keyword in command_id_lower for keyword in ["temp", "temperature"]):
                _LOGGER.info("Found temperature command by pattern: %s for %s°C", command["id"], temperature)
                return command["id"]
        
        _LOGGER.warning("No command found for temperature %s°C. Searched patterns: %s", temperature, possible_names)
        return None
    
    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            _LOGGER.warning("No temperature provided in kwargs: %s", kwargs)
            return
        
        # Round to nearest integer
        temperature = round(temperature)
        
        _LOGGER.info("Setting temperature to %s°C for %s", temperature, self._device_name)
        _LOGGER.info("Climate entity info: controller_id=%s, device_id=%s", self._controller_id, self._device_id)
        
        # DEBUG: Check if storage is accessible
        if not self._storage:
            _LOGGER.error("Storage is None!")
            return
        
        # DEBUG: Get all commands and show them
        try:
            commands = self._storage.get_commands(self._controller_id, self._device_id)
            _LOGGER.info("Retrieved %d commands from storage:", len(commands))
            for i, cmd in enumerate(commands):
                _LOGGER.info("  Command %d: id='%s', name='%s'", i+1, cmd.get("id", "NO_ID"), cmd.get("name", "NO_NAME"))
        except Exception as e:
            _LOGGER.error("Failed to get commands from storage: %s", e)
            return
        
        # Check if temperature is in allowed range
        if temperature < self._attr_min_temp or temperature > self._attr_max_temp:
            _LOGGER.error("Temperature %s°C is outside allowed range %s-%s°C", 
                         temperature, self._attr_min_temp, self._attr_max_temp)
            return
        
        # Find exact temperature command
        _LOGGER.info("Looking for temperature command for %s°C...", temperature)
        temp_command = self._find_temperature_command(temperature)
        
        if temp_command:
            try:
                _LOGGER.info("Found temperature command: %s, sending...", temp_command)
                await self._send_command(temp_command)
                self._target_temperature = temperature
                self.async_write_ha_state()
                _LOGGER.info("Successfully set target temperature to %s°C with command %s", temperature, temp_command)
            except Exception as e:
                _LOGGER.error("Failed to send temperature command %s: %s", temp_command, e)
        else:
            _LOGGER.error("No temperature command found for %s°C", temperature)
    
    
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        _LOGGER.info("Setting fan mode to %s for %s", fan_mode, self._device_name)
        
        command = self._find_command([f"fan_{fan_mode}", f"fan_speed_{fan_mode}", "fan_speed"])
        
        if command:
            await self._send_command(command)
            self._fan_mode = fan_mode
            self.async_write_ha_state()
            _LOGGER.info("Set fan mode to %s with command %s", fan_mode, command)
        else:
            _LOGGER.warning("No command found for fan mode %s", fan_mode)
    
    async def async_turn_on(self) -> None:
        """Turn the climate entity on."""
        _LOGGER.info("Turning on climate: %s", self._device_name)
        
        power_command = self._find_command(POWER_ON_COMMANDS)
        if not power_command:
            power_command = self._find_command(["power"])
        
        if power_command:
            await self._send_command(power_command)
            if self._hvac_mode == HVACMode.OFF:
                self._hvac_mode = HVACMode.AUTO
            self._current_hvac_action = HVACAction.IDLE
            self.async_write_ha_state()
            _LOGGER.info("Turned on climate with command %s", power_command)
        else:
            _LOGGER.warning("No power on command found for %s", self._device_name)
    
    async def async_turn_off(self) -> None:
        """Turn the climate entity off."""
        _LOGGER.info("Turning off climate: %s", self._device_name)
        
        power_command = self._find_command(POWER_OFF_COMMANDS)
        if not power_command:
            power_command = self._find_command(["power"])
        
        if power_command:
            await self._send_command(power_command)
            self._hvac_mode = HVACMode.OFF
            self._current_hvac_action = HVACAction.OFF
            self.async_write_ha_state()
            _LOGGER.info("Turned off climate with command %s", power_command)
        else:
            _LOGGER.warning("No power off command found for %s", self._device_name)
    
    async def _send_command(self, command: str) -> None:
        """Send IR command."""
        _LOGGER.debug("Sending command '%s' to device %s", command, self._device_name)
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_COMMAND,
                {
                    ATTR_CONTROLLER_ID: self._controller_id,
                    ATTR_DEVICE: self._device_id,
                    ATTR_COMMAND: command,
                },
                blocking=True
            )
            _LOGGER.debug("Successfully sent command %s", command)
            
        except Exception as e:
            _LOGGER.error("Failed to send command %s: %s", command, e)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_id": self._device_id,
            "controller_id": self._controller_id,
            "device_type": "ac",
        }
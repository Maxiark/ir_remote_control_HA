"""Light platform for IR Remote integration."""
import logging
from typing import Any, Optional, List

from homeassistant.components.light import (
    LightEntity,
    LightEntityFeature,
    ColorMode,
)
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
    MODEL_LIGHT,
    TRANSLATION_KEY_LIGHT,
    DEVICE_TYPE_LIGHT,
    LIGHT_TYPES,
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
    """Set up IR Remote light entities."""
    _LOGGER.info("Setting up IR Remote lights for: %s", config_entry.title)
    
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
    
    lights = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.debug("Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        device_type = device.get("type", "light")  # По умолчанию light
        
        _LOGGER.info("Processing device: %s (%s) - type: %s", device_name, device_id, device_type)
        
        # Создаём Light entity только для типа Light
        if device_type in LIGHT_TYPES:
            _LOGGER.debug("Creating light entity for device: %s", device_name)
            
            # Create light entity for this device
            light = IRLight(
                hass=hass,
                config_entry=config_entry,
                controller_id=controller_id,
                device_id=device_id,
                device_name=device_name,
                storage=storage,
            )
            lights.append(light)
            _LOGGER.debug("Created light entity for device %s", device_name)
    
    _LOGGER.info("Created %d light entities for controller %s", len(lights), controller_id)
    
    # Add all lights
    async_add_entities(lights)


class IRLight(LightEntity):
    """Light entity for IR devices (гирлянды, ленты, лампы)."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
        storage: IRRemoteStorage,
    ) -> None:
        """Initialize the light."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        self._storage = storage
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_light"
        self._attr_name = device_name
        self._attr_translation_key = TRANSLATION_KEY_LIGHT
        self._attr_should_poll = False
        
        # Device info - link to the same virtual device as buttons
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_LIGHT,
            via_device=(DOMAIN, controller_id),
        )
        
        # Light settings
        self._attr_color_mode = ColorMode.ONOFF  # Только вкл/выкл (без яркости пока)
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_supported_features = LightEntityFeature.EFFECT  # Поддержка эффектов!
        
        # State
        self._attr_is_on = False
        self._attr_effect = None
        
        # Initialize effect list
        self._update_effect_list()
        
        _LOGGER.debug("Initialized light: %s with %d effects", device_name, len(self._attr_effect_list or []))
    
    def _update_effect_list(self) -> None:
        """Update effect list from available commands.
        
        Excludes power commands (on/off) as they are handled by turn_on/turn_off methods.
        """
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        
        # Фильтруем команды питания - они не должны быть в эффектах
        all_power_commands = set(POWER_ON_COMMANDS + POWER_OFF_COMMANDS)
        
        self._attr_effect_list = [
            command["name"] for command in commands  # Используем name, не id!
            if command["id"].lower() not in all_power_commands
        ]
        
        _LOGGER.debug("Updated effect list for %s: %s (filtered out power commands)", 
                     self._device_name, self._attr_effect_list)
    
    def _find_command_by_name(self, effect_name: str) -> Optional[str]:
        """Find command ID by effect name."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        
        for command in commands:
            if command["name"] == effect_name:
                return command["id"]
        
        return None
    
    def _find_command(self, command_names: list) -> Optional[str]:
        """Find command from available commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        available_commands = {cmd["id"].lower(): cmd["id"] for cmd in commands}
        
        for cmd_name in command_names:
            if cmd_name.lower() in available_commands:
                return available_commands[cmd_name.lower()]
        
        return None
    
    @property
    def effect_list(self) -> Optional[List[str]]:
        """Return the list of supported effects (эффекты/режимы)."""
        # Обновляем список при каждом запросе на случай если команды изменились
        self._update_effect_list()
        return self._attr_effect_list
    
    @property
    def effect(self) -> Optional[str]:
        """Return the current effect (текущий эффект)."""
        return self._attr_effect
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the light."""
        return "mdi:lightbulb-on" if self.is_on else "mdi:lightbulb-outline"
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        effect = kwargs.get("effect")
        
        if effect:
            # Включение с конкретным эффектом
            _LOGGER.info("Turning on %s with effect '%s'", self._device_name, effect)
            
            # Проверяем что эффект существует
            if effect not in self.effect_list:
                _LOGGER.warning("Effect '%s' not found in available effects for %s", effect, self._device_name)
                return
            
            # Находим ID команды по названию эффекта
            command_id = self._find_command_by_name(effect)
            if not command_id:
                _LOGGER.warning("Command not found for effect '%s'", effect)
                return
            
            # Отправляем команду
            await self._send_command(command_id)
            
            # Обновляем состояние
            self._attr_is_on = True
            self._attr_effect = effect
            self.async_write_ha_state()
            
            _LOGGER.debug("Light %s turned on with effect '%s' (command: %s)", 
                         self._device_name, effect, command_id)
        else:
            # Простое включение (без эффекта)
            _LOGGER.info("Turning on %s (no effect specified)", self._device_name)
            
            power_command = self._find_command(POWER_ON_COMMANDS)
            
            if power_command:
                await self._send_command(power_command)
                self._attr_is_on = True
                # Эффект остаётся тем же или None
                self.async_write_ha_state()
                _LOGGER.info("Sent power on command: %s", power_command)
            else:
                _LOGGER.warning("No power on command found for %s", self._device_name)
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.info("Turning off %s", self._device_name)
        
        power_command = self._find_command(POWER_OFF_COMMANDS)
        
        if power_command:
            await self._send_command(power_command)
            self._attr_is_on = False
            # Эффект остаётся в памяти (для повторного включения)
            self.async_write_ha_state()
            _LOGGER.info("Sent power off command: %s", power_command)
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
            "device_type": "light",
            "available_effects": len(self._attr_effect_list or []),
        }
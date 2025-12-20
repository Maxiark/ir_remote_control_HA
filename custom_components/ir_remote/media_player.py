"""Media Player platform for IR Remote integration."""
import logging
from typing import Any, Optional, List

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
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
    MODEL_MEDIA_PLAYER,
    TRANSLATION_KEY_MEDIA_PLAYER,
    DEVICE_TYPE_TV,
    DEVICE_TYPE_AUDIO,
    DEVICE_TYPE_PROJECTOR,
    DEVICE_TYPE_UNIVERSAL,
    MEDIA_PLAYER_TYPES,
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
    """Set up IR Remote media player entities."""
    _LOGGER.info("Setting up IR Remote media players for: %s", config_entry.title)
    
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
    
    media_players = []
    
    # Get all devices for this controller
    devices = storage.get_devices(controller_id)
    _LOGGER.debug("Found %d devices for controller %s", len(devices), controller_id)
    
    for device in devices:
        device_id = device["id"]
        device_name = device["name"]
        device_type = device.get("type", "universal")
        
        _LOGGER.info("Processing device: %s (%s) - type: %s", device_name, device_id, device_type)
        
        # Создаём Media Player для ВСЕХ типов устройств (включая Universal!)
        # Для TV/Audio/Projector - стандартный функционал
        # Для Universal - source_list с командами
        if device_type in MEDIA_PLAYER_TYPES or device_type == DEVICE_TYPE_UNIVERSAL:
            _LOGGER.debug("Creating media player for device: %s (%s)", device_name, device_type)
            
            # Create media player entity for this device
            media_player = IRMediaPlayer(
                hass=hass,
                config_entry=config_entry,
                controller_id=controller_id,
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                storage=storage,
            )
            media_players.append(media_player)
            _LOGGER.debug("Created media player for device %s", device_name)
    
    _LOGGER.info("Created %d media player entities for controller %s", len(media_players), controller_id)
    
    # Add all media players
    async_add_entities(media_players)


class IRMediaPlayer(MediaPlayerEntity):
    """Media Player entity for IR devices (TV, Audio, Projector, Universal)."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        controller_id: str,
        device_id: str,
        device_name: str,
        device_type: str,
        storage: IRRemoteStorage,
    ) -> None:
        """Initialize the media player."""
        self.hass = hass
        self.config_entry = config_entry
        self._controller_id = controller_id
        self._device_id = device_id
        self._device_name = device_name
        self._device_type = device_type
        self._storage = storage
        
        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{controller_id}_{device_id}_player"
        self._attr_name = device_name
        self._attr_translation_key = TRANSLATION_KEY_MEDIA_PLAYER
        self._attr_should_poll = False
        
        # Device info - link to the same virtual device as buttons
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}_{device_id}")},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=MODEL_MEDIA_PLAYER,
            via_device=(DOMAIN, controller_id),
        )
        
        # Media player state
        self._state = MediaPlayerState.IDLE
        self._volume_level = 0.5
        self._is_volume_muted = False
        self._current_source = None
        
        # Set supported features based on device type
        self._set_supported_features()
        
        # Initialize source list (для всех типов, особенно для Universal)
        self._update_source_list()
        
        _LOGGER.debug("Initialized media player: %s (%s)", device_name, device_type)
    
    def _update_source_list(self) -> None:
        """Update source list from available commands.
        
        Excludes power commands (on/off) as they are handled by turn_on/turn_off methods.
        """
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        
        # Фильтруем команды питания - они не должны быть в источниках
        all_power_commands = set(POWER_ON_COMMANDS + POWER_OFF_COMMANDS)
        
        self._attr_source_list = [
            command["id"] for command in commands
            if command["id"].lower() not in all_power_commands
        ]
        
        _LOGGER.debug("Updated source list for %s: %s (filtered out power commands)", 
                     self._device_name, self._attr_source_list)
    
    def _set_supported_features(self) -> None:
        """Set supported features based on device type."""
        # Базовые возможности для всех типов
        features = (
            MediaPlayerEntityFeature.TURN_ON |
            MediaPlayerEntityFeature.TURN_OFF |
            MediaPlayerEntityFeature.SELECT_SOURCE  # Источники для всех!
        )
        
        # Дополнительные возможности для специализированных типов
        if self._device_type in [DEVICE_TYPE_TV, DEVICE_TYPE_AUDIO, DEVICE_TYPE_PROJECTOR]:
            features |= (
                MediaPlayerEntityFeature.VOLUME_STEP |
                MediaPlayerEntityFeature.VOLUME_MUTE
            )
        
        if self._device_type == DEVICE_TYPE_TV:
            features |= (
                MediaPlayerEntityFeature.NEXT_TRACK |  # Channel +
                MediaPlayerEntityFeature.PREVIOUS_TRACK  # Channel -
            )
        elif self._device_type == DEVICE_TYPE_AUDIO:
            features |= (
                MediaPlayerEntityFeature.PLAY |
                MediaPlayerEntityFeature.PAUSE |
                MediaPlayerEntityFeature.STOP |
                MediaPlayerEntityFeature.NEXT_TRACK |
                MediaPlayerEntityFeature.PREVIOUS_TRACK
            )
        
        self._attr_supported_features = features
    
    def _find_command(self, command_names: list) -> Optional[str]:
        """Find command from available commands."""
        commands = self._storage.get_commands(self._controller_id, self._device_id)
        available_commands = {cmd["id"].lower(): cmd["id"] for cmd in commands}
        
        for cmd_name in command_names:
            if cmd_name.lower() in available_commands:
                return available_commands[cmd_name.lower()]
        
        return None
    
    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media player."""
        return self._state
    
    @property
    def volume_level(self) -> Optional[float]:
        """Volume level of the media player (0..1)."""
        return self._volume_level
    
    @property
    def is_volume_muted(self) -> Optional[bool]:
        """Boolean if volume is currently muted."""
        return self._is_volume_muted
    
    @property
    def source(self) -> Optional[str]:
        """Name of the current input source (последняя команда)."""
        return self._current_source
    
    @property
    def source_list(self) -> Optional[List[str]]:
        """List of available input sources (команды устройства)."""
        # Обновляем список при каждом запросе на случай если команды изменились
        self._update_source_list()
        return self._attr_source_list
    
    async def async_select_source(self, source: str) -> None:
        """Select input source (выполнить команду)."""
        _LOGGER.info("Selecting source (executing command) '%s' for %s", source, self._device_name)
        
        # Проверяем что команда существует
        if source not in self.source_list:
            _LOGGER.warning("Source %s not found in available sources for %s", source, self._device_name)
            return
        
        # Выполняем команду
        await self._send_command(source)
        
        # Обновляем текущий источник
        self._current_source = source
        self.async_write_ha_state()
        
        _LOGGER.debug("Successfully selected source %s for %s", source, self._device_name)
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
    
    @property
    def icon(self) -> str:
        """Return the icon for the media player."""
        if self._device_type == DEVICE_TYPE_TV:
            return "mdi:television"
        elif self._device_type == DEVICE_TYPE_AUDIO:
            return "mdi:speaker"
        elif self._device_type == DEVICE_TYPE_PROJECTOR:
            return "mdi:projector"
        elif self._device_type == DEVICE_TYPE_UNIVERSAL:
            return "mdi:remote"  # Иконка пульта для универсальных устройств
        else:
            return "mdi:remote"
    
    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        _LOGGER.info("Turning on media player: %s", self._device_name)
        
        power_command = self._find_command(POWER_ON_COMMANDS)
        if not power_command:
            power_command = self._find_command(["power"])
        
        if power_command:
            await self._send_command(power_command)
            self._state = MediaPlayerState.IDLE
            self._current_source = power_command
            self.async_write_ha_state()
            _LOGGER.info("Sent power on command: %s", power_command)
        else:
            _LOGGER.warning("No power on command found for %s", self._device_name)
    
    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        _LOGGER.info("Turning off media player: %s", self._device_name)
        
        power_command = self._find_command(POWER_OFF_COMMANDS)
        if not power_command:
            power_command = self._find_command(["power"])
        
        if power_command:
            await self._send_command(power_command)
            self._state = MediaPlayerState.IDLE
            self._current_source = power_command
            self.async_write_ha_state()
            _LOGGER.info("Sent power off command: %s", power_command)
        else:
            _LOGGER.warning("No power off command found for %s", self._device_name)
    
    async def async_volume_up(self) -> None:
        """Volume up media player."""
        command = self._find_command(["volume_up", "vol_up", "vol+"])
        if command:
            await self._send_command(command)
            self._volume_level = min(1.0, self._volume_level + 0.1)
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No volume up command found for %s", self._device_name)
    
    async def async_volume_down(self) -> None:
        """Volume down media player."""
        command = self._find_command(["volume_down", "vol_down", "vol-"])
        if command:
            await self._send_command(command)
            self._volume_level = max(0.0, self._volume_level - 0.1)
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No volume down command found for %s", self._device_name)
    
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute media player."""
        command = self._find_command(["mute"])
        if command:
            await self._send_command(command)
            self._is_volume_muted = mute
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No mute command found for %s", self._device_name)
    
    async def async_media_play(self) -> None:
        """Send play command."""
        command = self._find_command(["play"])
        if command:
            await self._send_command(command)
            self._state = MediaPlayerState.PLAYING
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No play command found for %s", self._device_name)
    
    async def async_media_pause(self) -> None:
        """Send pause command."""
        command = self._find_command(["pause"])
        if command:
            await self._send_command(command)
            self._state = MediaPlayerState.PAUSED
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No pause command found for %s", self._device_name)
    
    async def async_media_stop(self) -> None:
        """Send stop command."""
        command = self._find_command(["stop"])
        if command:
            await self._send_command(command)
            self._state = MediaPlayerState.IDLE
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No stop command found for %s", self._device_name)
    
    async def async_media_next_track(self) -> None:
        """Send next track/channel command."""
        if self._device_type == DEVICE_TYPE_TV:
            command = self._find_command(["channel_up", "ch_up", "ch+"])
        else:
            command = self._find_command(["next", "next_track"])
        
        if command:
            await self._send_command(command)
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No next track/channel command found for %s", self._device_name)
    
    async def async_media_previous_track(self) -> None:
        """Send previous track/channel command."""
        if self._device_type == DEVICE_TYPE_TV:
            command = self._find_command(["channel_down", "ch_down", "ch-"])
        else:
            command = self._find_command(["previous", "prev_track"])
        
        if command:
            await self._send_command(command)
            self._current_source = command
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No previous track/channel command found for %s", self._device_name)
    
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
        # Создаём словарь соответствия номеров источников их названиям
        source_name_map = {}
        if self._attr_source_list:
            for idx, source in enumerate(self._attr_source_list, start=1):
                source_name_map[f"Источник {idx}"] = source
        
        return {
            "device_id": self._device_id,
            "controller_id": self._controller_id,
            "device_type": self._device_type,
            "available_commands": len(self._attr_source_list or []),
            "source_name_map": source_name_map,  # Mapping для пользователя
        }
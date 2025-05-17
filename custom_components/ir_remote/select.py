"""Select platform for IR Remote integration."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote select entities."""
    _LOGGER.debug("Setting up IR Remote selectors")

    # Создаем селекторы с минимальным набором параметров
    selectors = [
        BasicIRRemoteSelector(
            hass, 
            config_entry, 
            "01_10_send_device", 
            "Устройство для отправки",
            ["none", "tv", "audio"]
        ),
        BasicIRRemoteSelector(
            hass, 
            config_entry, 
            "01_11_command_selector", 
            "Команда",
            ["none", "power", "volume_up", "volume_down"]
        ),
        BasicIRRemoteSelector(
            hass, 
            config_entry, 
            "02_20_learn_device", 
            "Устройство для обучения",
            ["none", "tv", "audio"]
        ),
    ]
    
    _LOGGER.debug(f"Добавляем {len(selectors)} селекторов")
    for selector in selectors:
        _LOGGER.debug(f"Добавляем селектор: {selector.unique_id} ({selector.name})")
    
    async_add_entities(selectors)


class BasicIRRemoteSelector(SelectEntity):
    """Basic selector for IR Remote."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        id_suffix: str,
        name: str,
        options: list,
    ) -> None:
        """Initialize select entity."""
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_{id_suffix}"
        self._attr_name = name
        self._attr_options = options
        self._attr_current_option = options[0]
        
        # Важные атрибуты для правильной регистрации
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        
        _LOGGER.debug(f"Создан селектор: {self._attr_unique_id} с именем {name}")

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        _LOGGER.debug(f"Выбрана опция {option} в селекторе {self.name}")
        self._attr_current_option = option
        self.async_write_ha_state()
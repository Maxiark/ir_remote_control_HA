"""Text platform for IR Remote integration."""
import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote text entities."""
    _LOGGER.debug("Setting up IR Remote text entities")

    # Создаем текстовые поля с минимальным набором параметров
    text_entities = [
        BasicIRRemoteText(
            hass, 
            config_entry, 
            "02_21_button_input", 
            "Название кнопки"
        ),
        BasicIRRemoteText(
            hass, 
            config_entry, 
            "03_30_new_device_input", 
            "Название нового устройства"
        ),
    ]
    
    _LOGGER.debug(f"Добавляем {len(text_entities)} текстовых полей")
    for entity in text_entities:
        _LOGGER.debug(f"Добавляем текстовое поле: {entity.unique_id} ({entity.name})")
    
    async_add_entities(text_entities)


class BasicIRRemoteText(TextEntity):
    """Basic text entity for IR Remote."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        id_suffix: str,
        name: str,
    ) -> None:
        """Initialize text entity."""
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_{id_suffix}"
        self._attr_name = name
        self._attr_native_value = ""
        
        # Важные атрибуты для правильной регистрации
        self._attr_mode = "text"  # Обязательный атрибут для TextEntity
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        
        _LOGGER.debug(f"Создано текстовое поле: {self._attr_unique_id} с именем {name}")

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

    async def async_set_value(self, value: str) -> None:
        """Set value of text entity."""
        _LOGGER.debug(f"Установлено значение '{value}' в поле {self.name}")
        self._attr_native_value = value
        self.async_write_ha_state()
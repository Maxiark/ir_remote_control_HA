"""Text platform for IR Remote integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entities import IRRemoteButtonInput, IRRemoteNewDeviceInput

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote text entities."""
    _LOGGER.debug("Setting up IR Remote text entities")

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    # Создаем текстовые поля
    entities = [
        IRRemoteButtonInput(
            coordinator,
            config_entry,
            "02_21_button_input",
            "Название кнопки"
        ),
        IRRemoteNewDeviceInput(
            coordinator,
            config_entry,
            "03_30_new_device_input",
            "Название нового устройства"
        ),
    ]
    
    async_add_entities(entities)
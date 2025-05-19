"""Select platform for IR Remote integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entities import IRRemoteDeviceSelector, IRRemoteCommandSelector

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote select entities."""
    _LOGGER.debug("Setting up IR Remote select entities")

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    # Создаем селекторы
    entities = [
        IRRemoteDeviceSelector(
            coordinator,
            config_entry,
            "01_10_send_device",
            "Устройство для отправки",
            "send"
        ),
        IRRemoteCommandSelector(
            coordinator,
            config_entry,
            "01_11_command_selector",
            "Команда"
        ),
        IRRemoteDeviceSelector(
            coordinator,
            config_entry,
            "02_20_learn_device",
            "Устройство для обучения",
            "learn"
        ),
    ]
    
    async_add_entities(entities)
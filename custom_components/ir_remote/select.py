"""Select platform for IR Remote integration - исправленные импорты."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entities import IRRemoteDeviceSelector, IRRemoteCommandSelector

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote select entities."""
    _LOGGER.debug("=== Setting up IR Remote select entities ===")
    _LOGGER.debug("Config entry ID: %s", config_entry.entry_id)

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    _LOGGER.debug("Coordinator data: %s", coordinator.data)
    
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
    
    _LOGGER.debug("Created %d select entities", len(entities))
    for entity in entities:
        _LOGGER.debug("Select entity: %s (unique_id: %s)", entity.name, entity.unique_id)
    
    async_add_entities(entities)
    
    _LOGGER.debug("=== IR Remote select entities setup completed ===")
    
    # Проверяем, что сущности действительно добавлены
    entity_registry = er.async_get(hass)
    entities_count = 0
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_entry.config_entry_id == config_entry.entry_id and entity_entry.domain == "select":
            entities_count += 1
            _LOGGER.debug("Registered select entity: %s (%s)", entity_id, entity_entry.unique_id)
    
    _LOGGER.debug("Total select entities registered: %d", entities_count)
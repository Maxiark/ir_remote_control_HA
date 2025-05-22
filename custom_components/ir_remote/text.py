"""Text platform for IR Remote integration - полная исправленная версия."""
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
    _LOGGER.debug("=== Setting up IR Remote text entities ===")
    _LOGGER.debug("Config entry ID: %s", config_entry.entry_id)

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    _LOGGER.debug("Coordinator data: %s", coordinator.data)
    
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
    
    _LOGGER.debug("Created %d text entities", len(entities))
    for entity in entities:
        _LOGGER.debug("Text entity: %s (unique_id: %s)", entity.name, entity.unique_id)
    
    async_add_entities(entities)
    
    _LOGGER.debug("=== IR Remote text entities setup completed ===")
    
    # Проверяем, что сущности действительно добавлены
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entities_count = 0
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_entry.config_entry_id == config_entry.entry_id and entity_entry.domain == "text":
            entities_count += 1
            _LOGGER.debug("Registered text entity: %s (%s)", entity_id, entity_entry.unique_id)
    
    _LOGGER.debug("Total text entities registered: %d", entities_count)
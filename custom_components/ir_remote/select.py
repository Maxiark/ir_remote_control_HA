"""Select platform for IR Remote integration - с INFO логированием."""
import logging
import asyncio

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
    _LOGGER.info("=== Setting up IR Remote select entities ===")
    _LOGGER.info("Config entry ID: %s", config_entry.entry_id)

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    _LOGGER.info("Coordinator found for select entities")
    
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
    
    _LOGGER.info("Created %d select entities", len(entities))
    for entity in entities:
        _LOGGER.info("Select entity: %s (unique_id: %s), options: %s", 
                    entity.name, entity.unique_id, getattr(entity, '_attr_options', 'None'))
    
    async_add_entities(entities)
    
    # Принудительно обновляем каждую сущность
    async def force_update():
        await asyncio.sleep(1)
        _LOGGER.info("=== Forcing select entity updates ===")
        for entity in entities:
            if hasattr(entity, '_handle_coordinator_update'):
                entity._handle_coordinator_update()
                _LOGGER.info("Updated entity %s, new options: %s", 
                           entity.name, getattr(entity, '_attr_options', 'None'))
    
    hass.async_create_task(force_update())
    
    _LOGGER.info("=== IR Remote select entities setup completed ===")
    
    # Проверяем, что сущности действительно добавлены (через 1 секунду)
    async def check_entities():
        import asyncio
        await asyncio.sleep(1)
        entity_registry = er.async_get(hass)
        entities_count = 0
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_entry.config_entry_id == config_entry.entry_id and entity_entry.domain == "select":
                entities_count += 1
                _LOGGER.info("Registered select entity: %s", entity_id)
        
        _LOGGER.info("Total select entities registered: %d", entities_count)
    
    hass.async_create_task(check_entities())
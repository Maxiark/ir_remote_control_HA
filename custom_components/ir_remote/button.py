"""Button platform for IR Remote integration - исправленные импорты."""
import logging
import json
from pathlib import Path

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entities import IRRemoteLearnButton, IRRemoteSendButton, IRRemoteAddDeviceButton, IRRemoteDeviceButton

_LOGGER = logging.getLogger(__name__)

# Максимальное количество кнопок на устройство
MAX_BUTTONS_PER_DEVICE = 50


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote buttons."""
    _LOGGER.debug("=== Setting up IR Remote buttons ===")
    _LOGGER.debug("Config entry ID: %s", config_entry.entry_id)
    _LOGGER.debug("Config entry data: %s", config_entry.data)

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
    _LOGGER.debug("Coordinator data: %s", coordinator.data)
    
    # Создаем основные кнопки управления
    ui_buttons = [
        IRRemoteSendButton(
            coordinator,
            config_entry,
            "01_12_send_button",
            "Отправить команду"
        ),
        IRRemoteLearnButton(
            coordinator,
            config_entry,
            "02_22_learn_button",
            "Начать обучение"
        ),
        IRRemoteAddDeviceButton(
            coordinator,
            config_entry,
            "03_31_add_device_button",
            "Добавить устройство"
        ),
    ]
    
    _LOGGER.debug("Created %d UI buttons", len(ui_buttons))
    for button in ui_buttons:
        _LOGGER.debug("UI Button: %s (unique_id: %s)", button.name, button.unique_id)
    
    # Создаем кнопки устройств из сохраненных кодов
    device_buttons = []
    total_buttons = 0
    
    # Получаем данные о кодах из координатора
    if coordinator.data and "codes" in coordinator.data:
        codes = coordinator.data["codes"]
        _LOGGER.debug("Found codes data: %s", codes)
        
        for device_name, commands in codes.items():
            device_button_count = 0
            _LOGGER.debug("Processing device: %s with commands: %s", device_name, list(commands.keys()))
            
            # Сортируем команды для стабильного порядка
            sorted_commands = sorted(commands.items())
            
            for command_name, command_data in sorted_commands:
                # Ограничиваем количество кнопок на устройство
                if device_button_count >= MAX_BUTTONS_PER_DEVICE:
                    _LOGGER.warning(
                        "Достигнут лимит кнопок для устройства %s (%d кнопок). Пропущено: %s",
                        device_name, MAX_BUTTONS_PER_DEVICE, command_name
                    )
                    continue
                
                device_button = IRRemoteDeviceButton(
                    hass,
                    config_entry,
                    device_name,
                    command_name,
                    command_data,
                )
                device_buttons.append(device_button)
                device_button_count += 1
                total_buttons += 1
                _LOGGER.debug("Created device button: %s - %s (unique_id: %s)", 
                             device_name, command_name, device_button.unique_id)
    else:
        _LOGGER.debug("No codes data found in coordinator")
    
    _LOGGER.debug("Created %d device buttons total", total_buttons)
    
    # Добавляем все кнопки
    all_buttons = ui_buttons + device_buttons
    _LOGGER.debug("Adding %d total buttons to Home Assistant", len(all_buttons))
    
    async_add_entities(all_buttons)
    
    _LOGGER.debug("=== IR Remote buttons setup completed ===")
    
    # Проверяем, что сущности действительно добавлены
    entity_registry = er.async_get(hass)
    entities_count = 0
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_entry.config_entry_id == config_entry.entry_id and entity_entry.domain == "button":
            entities_count += 1
            _LOGGER.debug("Registered button entity: %s (%s)", entity_id, entity_entry.unique_id)
    
    _LOGGER.debug("Total button entities registered: %d", entities_count)
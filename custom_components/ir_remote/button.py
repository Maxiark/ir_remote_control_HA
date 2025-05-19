"""Button platform for IR Remote integration."""
import logging
import json
from pathlib import Path

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entities import IRRemoteLearnButton, IRRemoteSendButton, IRRemoteAddDeviceButton, IRRemoteDeviceButton

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote buttons."""
    _LOGGER.debug("Setting up IR Remote buttons")

    # Получаем координатор данных из настроек компонента
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных не инициализирован")
        return
    
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
    
    # Создаем кнопки устройств из сохраненных кодов
    device_buttons = []
    
    # Получаем данные о кодах из координатора
    if coordinator.data and "codes" in coordinator.data:
        codes = coordinator.data["codes"]
        
        for device_name, commands in codes.items():
            for command_name, command_data in commands.items():
                device_buttons.append(
                    IRRemoteDeviceButton(
                        hass,
                        config_entry,
                        device_name,
                        command_name,
                        command_data,
                    )
                )
    
    # Добавляем все кнопки
    async_add_entities(ui_buttons + device_buttons)
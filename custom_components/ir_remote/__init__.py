"""IR Remote integration for Home Assistant."""
import logging
import os
from typing import Any
from pathlib import Path

import aiofiles
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    DEFAULT_CLUSTER_TYPE,
    DEFAULT_COMMAND_TYPE,
    SERVICE_LEARN_CODE,
    SERVICE_SEND_CODE,
    ATTR_DEVICE,
    ATTR_BUTTON,
    ATTR_CODE,
    ZHA_COMMAND_LEARN,
    ZHA_COMMAND_SEND,
)

_LOGGER = logging.getLogger(__name__)

# Define platforms to load
PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.TEXT]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Service schemas
LEARN_CODE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required(ATTR_BUTTON): cv.string,
})

SEND_CODE_SCHEMA = vol.Schema({
    vol.Required(ATTR_CODE): cv.string,
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.debug("Setting up IR Remote integration (domain: %s)", DOMAIN)
    
    # Initialize data structure
    hass.data.setdefault(DOMAIN, {})
    
    # Create scripts directory if not exist
    scripts_dir = Path(__file__).parent / "scripts"
    try:
        await hass.async_add_executor_job(lambda: scripts_dir.mkdir(exist_ok=True))
        
        # Create ir_codes.json if not exist
        config_path = scripts_dir / "ir_codes.json"
        if not await hass.async_add_executor_job(lambda: config_path.exists()):
            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write("{}")
        _LOGGER.debug("IR codes file created/checked at %s", config_path)
    except Exception as e:
        _LOGGER.error("Failed to initialize IR Remote files: %s", e)
        return False
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.debug("Setting up IR Remote entry: %s", entry.entry_id)
    
    if "zha" not in hass.data:
        _LOGGER.error("ZHA integration not found")
        return False
    
    # Store configuration
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
    }
    
    # Register services
    async def learn_ir_code(call: ServiceCall) -> None:
        """Сервис обучения ИК-кодам."""
        device = call.data.get(ATTR_DEVICE)
        button = call.data.get(ATTR_BUTTON)
        
        _LOGGER.debug("Обучение ИК-коду для устройства '%s', кнопки '%s'", device, button)
        
        ieee = entry.data.get(CONF_IEEE)
        endpoint_id = entry.data.get(CONF_ENDPOINT)
        cluster_id = entry.data.get(CONF_CLUSTER)
        
        if not ieee or not endpoint_id or not cluster_id:
            _LOGGER.error("Отсутствует конфигурация для ИК-пульта")
            return
        
        try:
            # Отправляем ZHA-команду для начала обучения
            await hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": ieee,
                    "endpoint_id": endpoint_id,
                    "cluster_id": cluster_id,
                    "cluster_type": DEFAULT_CLUSTER_TYPE,
                    "command": ZHA_COMMAND_LEARN,
                    "command_type": DEFAULT_COMMAND_TYPE,
                    "params": {"on_off": True, "device": device, "button": button}
                },
                blocking=True
            )
            _LOGGER.debug("Команда обучения ИК-коду успешно отправлена")
            
            # После этого предполагается, что устройство отправит ответ с кодом
            # Этот код нужно будет сохранить с помощью функции save_ir_code
            
        except Exception as e:
            _LOGGER.error("Ошибка отправки команды обучения ИК-коду: %s", e)
            raise HomeAssistantError(f"Не удалось отправить команду обучения ИК-коду: {e}") from e
    
    
    async def send_ir_code(call: ServiceCall) -> None:
        """Service to send IR codes."""
        code = call.data.get(ATTR_CODE)
        
        _LOGGER.debug("Sending IR code: %s", code[:10] + "..." if len(code) > 10 else code)
        
        ieee = entry.data.get(CONF_IEEE)
        endpoint_id = entry.data.get(CONF_ENDPOINT)
        cluster_id = entry.data.get(CONF_CLUSTER)
        
        if not ieee or not endpoint_id or not cluster_id:
            _LOGGER.error("Missing configuration for IR Remote")
            return
        
        try:
            # Send ZHA command with IR code
            await hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": ieee,
                    "endpoint_id": endpoint_id,
                    "cluster_id": cluster_id,
                    "cluster_type": DEFAULT_CLUSTER_TYPE,
                    "command": ZHA_COMMAND_SEND,
                    "command_type": DEFAULT_COMMAND_TYPE,
                    "params": {"code": code}
                },
                blocking=True
            )
            _LOGGER.debug("IR code sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending IR code: %s", e)
            raise HomeAssistantError(f"Failed to send IR code: {e}") from e
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_CODE,
        learn_ir_code,
        schema=LEARN_CODE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_CODE,
        send_ir_code,
        schema=SEND_CODE_SCHEMA
    )
    
    _LOGGER.debug("Registered services: %s.%s, %s.%s",
                DOMAIN, SERVICE_LEARN_CODE, DOMAIN, SERVICE_SEND_CODE)
    
    # Set up platforms - this will create the UI automatically
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Create Lovelace card template
    card_config = {
        "type": "entities",
        "title": "ИК-пульт",
        "entities": [
            # Группа отправки команд
            {"type": "section", "label": "Отправка команд"},
            {"entity": "select.ir_remote_01_10_send_device"},
            {"entity": "select.ir_remote_01_11_command_selector"},
            {"entity": "button.ir_remote_01_12_send_button"},
            
            # Группа обучения
            {"type": "section", "label": "Обучение новым командам"},
            {"entity": "select.ir_remote_02_20_learn_device"},
            {"entity": "text.ir_remote_02_21_button_input"},
            {"entity": "button.ir_remote_02_22_learn_button"},
            
            # Группа добавления устройств
            {"type": "section", "label": "Добавление устройств"},
            {"entity": "text.ir_remote_03_30_new_device_input"},
            {"entity": "button.ir_remote_03_31_add_device_button"}
        ]
    }
    
    # Store card template for user reference
    hass.data[DOMAIN]["lovelace_card"] = card_config
    
    # Log instruction for adding the card to Lovelace
    _LOGGER.info(
        "IR Remote настроен! Чтобы добавить карточку управления в интерфейс, можно использовать "
        "кнопку 'Добавить карточку' в режиме редактирования на любой панели инструментов. "
        "Также можно добавить сущности устройства 'ИК-пульт' на любую панель мониторинга."
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading IR Remote entry: %s", entry.entry_id)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up
    if unload_ok:
        # Remove services
        hass.services.async_remove(DOMAIN, SERVICE_LEARN_CODE)
        hass.services.async_remove(DOMAIN, SERVICE_SEND_CODE)
        
        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
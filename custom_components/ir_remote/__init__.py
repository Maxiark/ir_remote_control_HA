"""IR Remote integration for Home Assistant."""
import logging
import os
from typing import Any
import json
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
    SERVICE_SEND_COMMAND,
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

SEND_COMMAND_SCHEMA = vol.Schema({
    vol.Required("device"): cv.string,  
    vol.Required("command"): cv.string,
})

GET_DATA_SCHEMA = vol.Schema({})

ADD_DEVICE_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
})


async def learn_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис обучения ИК-кодам."""
    device = call.data.get(ATTR_DEVICE)
    button = call.data.get(ATTR_BUTTON)
    
    _LOGGER.debug("Обучение ИК-коду для устройства '%s', кнопки '%s'", device, button)
    
    # Получаем конфигурацию из data[DOMAIN]
    config = hass.data[DOMAIN].get("config", {})
    ieee = config.get(CONF_IEEE)
    endpoint_id = config.get(CONF_ENDPOINT)
    cluster_id = config.get(CONF_CLUSTER)
    
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
    except Exception as e:
        _LOGGER.error("Ошибка отправки команды обучения ИК-коду: %s", e)
        raise HomeAssistantError(f"Не удалось отправить команду обучения ИК-коду: {e}") from e


async def send_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки ИК-кодов."""
    code = call.data.get(ATTR_CODE)
    
    _LOGGER.debug("Отправка ИК-кода: %s", code[:10] + "..." if len(code) > 10 else code)
    
    # Получаем конфигурацию из data[DOMAIN]
    config = hass.data[DOMAIN].get("config", {})
    ieee = config.get(CONF_IEEE)
    endpoint_id = config.get(CONF_ENDPOINT)
    cluster_id = config.get(CONF_CLUSTER)
    
    if not ieee or not endpoint_id or not cluster_id:
        _LOGGER.error("Отсутствует конфигурация для ИК-пульта")
        return
    
    try:
        # Отправляем ZHA-команду с ИК-кодом
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
        _LOGGER.debug("ИК-код успешно отправлен")
    except Exception as e:
        _LOGGER.error("Ошибка отправки ИК-кода: %s", e)
        raise HomeAssistantError(f"Не удалось отправить ИК-код: {e}") from e


async def send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки команд по имени устройства и команды."""
    device = call.data.get("device")
    command = call.data.get("command")
    
    if not device or not command or device == "none" or command == "none":
        _LOGGER.error("Не указано устройство или команда")
        return
    
    # Получаем код из ir_codes.json
    scripts_dir = Path(__file__).parent / "scripts"
    ir_codes_path = scripts_dir / "ir_codes.json"
    
    try:
        if await hass.async_add_executor_job(lambda: ir_codes_path.exists()):
            async with aiofiles.open(ir_codes_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
                
                if device in codes and command in codes[device]:
                    code = codes[device][command].get("code")
                    
                    if code:
                        # Отправляем ZHA-команду с IR-кодом
                        config = hass.data[DOMAIN].get("config", {})
                        ieee = config.get(CONF_IEEE)
                        endpoint_id = config.get(CONF_ENDPOINT)
                        cluster_id = config.get(CONF_CLUSTER)
                        
                        if not ieee or not endpoint_id or not cluster_id:
                            _LOGGER.error("Отсутствует конфигурация для ИК-пульта")
                            return
                        
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
                        _LOGGER.debug("ИК-код для %s - %s успешно отправлен", device, command)
                        return
                
                _LOGGER.error("ИК-код не найден для %s - %s", device, command)
        else:
            _LOGGER.error("Файл IR-кодов не найден: %s", ir_codes_path)
            
    except Exception as e:
        _LOGGER.error("Ошибка при отправке команды: %s", e, exc_info=True)
        raise HomeAssistantError(f"Не удалось отправить команду: {e}") from e


async def get_data(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Сервис для получения данных об устройствах и командах."""
    data = {
        "devices": [],
        "commands": {}
    }
    
    scripts_dir = Path(__file__).parent / "scripts"
    ir_codes_path = scripts_dir / "ir_codes.json"
    
    try:
        if await hass.async_add_executor_job(lambda: ir_codes_path.exists()):
            async with aiofiles.open(ir_codes_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
                
                # Формируем список устройств
                device_list = sorted(list(codes.keys()))
                data["devices"] = device_list
                
                # Формируем списки команд для каждого устройства
                for device in device_list:
                    commands = list(codes[device].keys())
                    data["commands"][device] = commands
    except Exception as e:
        _LOGGER.error("Ошибка получения данных: %s", e, exc_info=True)
    
    return data


async def add_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для добавления нового устройства."""
    device_name = call.data.get("name")
    
    if not device_name:
        _LOGGER.error("Имя устройства не может быть пустым")
        return
    
    scripts_dir = Path(__file__).parent / "scripts"
    ir_codes_path = scripts_dir / "ir_codes.json"
    
    try:
        codes = {}
        
        if await hass.async_add_executor_job(lambda: ir_codes_path.exists()):
            async with aiofiles.open(ir_codes_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
        
        if device_name in codes:
            _LOGGER.warning(f"Устройство {device_name} уже существует")
            return
        
        codes[device_name] = {}
        
        async with aiofiles.open(ir_codes_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(codes, indent=2, ensure_ascii=False))
        
        _LOGGER.info(f"Устройство {device_name} успешно добавлено")
    except Exception as e:
        _LOGGER.error(f"Ошибка добавления устройства: {e}", exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.debug("Setting up IR Remote integration (domain: %s)", DOMAIN)
    
    # Инициализируем структуру данных
    hass.data.setdefault(DOMAIN, {})
    
    # Создаем директорию scripts, если её нет
    scripts_dir = Path(__file__).parent / "scripts"
    _LOGGER.debug("Scripts directory: %s", scripts_dir)
    
    try:
        await hass.async_add_executor_job(lambda: scripts_dir.mkdir(exist_ok=True))
        
        # Создаем ir_codes.json, если его нет
        config_path = scripts_dir / "ir_codes.json"
        _LOGGER.debug("IR codes path: %s", config_path)
        
        if not await hass.async_add_executor_job(lambda: config_path.exists()):
            _LOGGER.debug("Creating empty ir_codes.json file")
            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write("{}")
            _LOGGER.debug("IR codes file created at %s", config_path)
        else:
            _LOGGER.debug("IR codes file already exists")
        
        # Создаем директорию www для карточки, если её нет
        www_dir = Path(__file__).parent / "www"
        _LOGGER.debug("Frontend directory: %s", www_dir)
        
        await hass.async_add_executor_job(lambda: www_dir.mkdir(exist_ok=True))
        _LOGGER.debug("Frontend directory created/checked")
        
    except Exception as e:
        _LOGGER.error("Failed to initialize IR Remote files: %s", e, exc_info=True)
        return False
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.debug("Setting up IR Remote entry: %s", entry.entry_id)
    
    if "zha" not in hass.data:
        _LOGGER.error("ZHA integration not found")
        return False
    
    # Инициализация структуры данных
    hass.data[DOMAIN] = {
        "config": entry.data,
    }
    
    # Регистрация сервисов
    await _register_services(hass, entry)
    
    # Настройка пользовательского интерфейса
    try:
        from .frontend import async_setup_frontend
        frontend_setup_ok = await async_setup_frontend(hass, entry)
        
        if not frontend_setup_ok:
            _LOGGER.warning("Failed to setup IR Remote frontend")
    except ImportError:
        _LOGGER.warning("Frontend module not found, skipping UI setup")
    
    # Настраиваем платформы - это создаст UI автоматически
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Создаем шаблон карточки Lovelace
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
    
    # Сохраняем шаблон карточки для справки пользователя
    hass.data[DOMAIN]["lovelace_card"] = card_config
    
    # Логируем инструкцию для добавления карточки в Lovelace
    _LOGGER.info(
        "IR Remote настроен! Для управления используйте карточку 'ИК-пульт' или "
        "добавьте сущности устройства 'ИК-пульт' на любую панель мониторинга."
    )
    
    return True


async def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Регистрация сервисов IR Remote."""
    # Регистрация сервисов
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
    
    # Регистрация новых сервисов
    hass.services.async_register(
        DOMAIN,
        "get_data",
        get_data,
        schema=GET_DATA_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        "add_device",
        add_device,
        schema=ADD_DEVICE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        send_command,
        schema=SEND_COMMAND_SCHEMA
    )
    
    _LOGGER.debug("Registered services: %s.%s, %s.%s, %s.%s, %s.%s, %s.%s",
                DOMAIN, SERVICE_LEARN_CODE, 
                DOMAIN, SERVICE_SEND_CODE,
                DOMAIN, "get_data",
                DOMAIN, "add_device",
                DOMAIN, SERVICE_SEND_COMMAND)


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
        hass.services.async_remove(DOMAIN, "get_data")
        hass.services.async_remove(DOMAIN, "add_device")
        hass.services.async_remove(DOMAIN, SERVICE_SEND_COMMAND)
        
        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
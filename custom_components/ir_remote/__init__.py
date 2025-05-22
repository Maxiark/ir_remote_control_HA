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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

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
    SERVICE_GET_DATA,
    SERVICE_ADD_DEVICE,
    ATTR_DEVICE,
    ATTR_BUTTON,
    ATTR_CODE,
    ZHA_COMMAND_LEARN,
    ZHA_COMMAND_SEND,
)
from .data import IRRemoteData, setup_ir_data_coordinator

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
    vol.Required(ATTR_DEVICE): cv.string,  
    vol.Required("command"): cv.string,
})

GET_DATA_SCHEMA = vol.Schema({})

ADD_DEVICE_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
})


async def async_learn_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис обучения ИК-кодам."""
    device = call.data.get(ATTR_DEVICE)
    button = call.data.get(ATTR_BUTTON)
    
    _LOGGER.debug("Обучение ИК-коду для устройства '%s', кнопки '%s'", device, button)
    
    # Получаем конфигурацию
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
        
        # Добавим уведомление для пользователя
        hass.components.persistent_notification.create(
            f"Ожидание сигнала ИК-пульта для устройства {device}, кнопки {button}. "
            "Направьте пульт на ИК-приемник и нажмите кнопку, которой хотите обучить.",
            "IR Remote: Режим обучения",
            f"{DOMAIN}_learning"
        )
    except Exception as e:
        _LOGGER.error("Ошибка отправки команды обучения ИК-коду: %s", e)
        raise HomeAssistantError(f"Не удалось отправить команду обучения ИК-коду: {e}") from e


async def async_send_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки ИК-кодов."""
    code = call.data.get(ATTR_CODE)
    
    _LOGGER.debug("Отправка ИК-кода: %s", code[:10] + "..." if len(code) > 10 else code)
    
    # Получаем конфигурацию
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


async def async_send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки команд по имени устройства и команды."""
    device = call.data.get(ATTR_DEVICE)
    command = call.data.get("command")
    
    if not device or not command or device == "none" or command == "none":
        _LOGGER.error("Не указано устройство или команда")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Получаем ИК-код
    code = ir_data.get_code(device, command)
    
    if not code:
        _LOGGER.error("ИК-код не найден для %s - %s", device, command)
        return
    
    # Отправляем ИК-код
    await async_send_ir_code(hass, ServiceCall(DOMAIN, SERVICE_SEND_CODE, {ATTR_CODE: code}))


async def async_get_data(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Сервис для получения данных об устройствах и командах."""
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("Координатор данных IR не инициализирован")
        return {}
    
    # Обновляем данные
    await coordinator.async_refresh()
    
    # Формируем упрощенную структуру данных для возврата
    data = {
        "devices": coordinator.data.get("devices", [])[1:],  # Исключаем "none"
        "commands": {}
    }
    
    # Формируем списки команд для каждого устройства
    for device in data["devices"]:
        commands = coordinator.data.get("commands", {}).get(device, [])[1:]  # Исключаем "none"
        data["commands"][device] = commands
    
    return data


async def async_add_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для добавления нового устройства."""
    device_name = call.data.get("name")
    
    if not device_name:
        _LOGGER.error("Имя устройства не может быть пустым")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Добавляем устройство
    success = await ir_data.async_add_device(device_name)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
    else:
        _LOGGER.error("Не удалось добавить устройство %s", device_name)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.debug("Setting up IR Remote integration (domain: %s)", DOMAIN)
    
    # Инициализируем структуру данных
    hass.data.setdefault(DOMAIN, {})
    
    # Создаем директорию scripts, если её нет
    scripts_dir = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts"
    _LOGGER.debug("Scripts directory: %s", scripts_dir)
    
    try:
        await hass.async_add_executor_job(lambda: scripts_dir.mkdir(exist_ok=True))
        _LOGGER.debug("Scripts directory created/checked")
    except Exception as e:
        _LOGGER.error("Failed to initialize IR Remote files: %s", e, exc_info=True)
        return False
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.debug("=== Setting up IR Remote entry ===")
    _LOGGER.debug("Entry ID: %s", entry.entry_id)
    _LOGGER.debug("Entry data: %s", entry.data)
    
    if "zha" not in hass.data:
        _LOGGER.error("ZHA integration not found")
        return False
    
    # Инициализация структуры данных
    hass.data[DOMAIN] = {
        "config": entry.data,
    }
    _LOGGER.debug("Initialized domain data structure")
    
    # Регистрируем устройство пульта в реестре устройств
    await async_register_ir_remote_device(hass, entry)
    
    # Настройка хранилища данных и координатора
    _LOGGER.debug("Setting up data coordinator...")
    coordinator = await setup_ir_data_coordinator(hass)
    hass.data[DOMAIN]["coordinator"] = coordinator
    _LOGGER.debug("Coordinator setup completed, data: %s", coordinator.data)
    
    # Настраиваем обработчик событий для сохранения IR-кодов
    async def handle_ir_code_learned(event):
        """Обработчик события обучения IR-коду."""
        _LOGGER.debug("IR code learned event received: %s", event.data)
        device = event.data.get("device")
        button = event.data.get("button")
        code = event.data.get("code")
        
        if not device or not button or not code:
            _LOGGER.error("Получены неполные данные для сохранения IR-кода")
            return
        
        # Получаем хранилище данных
        ir_data = hass.data[DOMAIN].get("data")
        if not ir_data:
            _LOGGER.error("Хранилище данных IR не инициализировано")
            return
        
        # Сохраняем код
        success = await ir_data.async_add_command(device, button, code)
        
        if success:
            _LOGGER.info("IR-код для %s - %s успешно сохранен", device, button)
            # Обновляем координатор
            await coordinator.async_refresh()
        else:
            _LOGGER.error("Не удалось сохранить IR-код для %s - %s", device, button)
    
    # Регистрируем обработчик события
    hass.bus.async_listen(f"{DOMAIN}_ir_code_learned", handle_ir_code_learned)
    _LOGGER.debug("Event handler registered")
    
    # Регистрация сервисов
    await _register_services(hass)
    _LOGGER.debug("Services registered")
    
    # Настраиваем платформы
    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Platforms setup completed")
    
    # Проверяем результат регистрации сущностей
    await _debug_check_entities(hass, entry)
    
    # Логируем инструкцию для добавления карточки в Lovelace
    _LOGGER.info(
        "IR Remote настроен! Для управления используйте сущности устройства 'ИК-пульт', "
        "которые можно добавить на любую панель мониторинга."
    )
    
    return True


async def async_register_ir_remote_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Регистрация устройства ИК-пульта в реестре устройств."""
    _LOGGER.debug("=== Registering IR Remote device ===")
    
    device_registry = dr.async_get(hass)
    ieee = entry.data.get(CONF_IEEE)
    entry_id = entry.entry_id
    
    _LOGGER.debug("IEEE: %s, Entry ID: %s", ieee, entry_id)
    
    # Получаем информацию об устройстве из ZHA
    zha_device_info = await get_zha_device_info(hass, ieee)
    _LOGGER.debug("ZHA device info: %s", zha_device_info)
    
    # Регистрируем устройство
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry_id)},  # Используем entry_id как основной идентификатор
        name="ИК-пульт",
        manufacturer=zha_device_info.get("manufacturer", "IR Remote Integration"),
        model=zha_device_info.get("model", "IR Controller"),
        sw_version="1.1.0",
        hw_version=zha_device_info.get("hw_version"),
    )
    
    _LOGGER.debug("IR Remote device registered: %s", device)
    _LOGGER.debug("Device identifiers: %s", device.identifiers)


async def get_zha_device_info(hass: HomeAssistant, ieee: str) -> dict:
    """Получение информации об устройстве из ZHA."""
    try:
        # Пытаемся получить информацию через zha_toolkit
        result = await hass.services.async_call(
            "zha_toolkit",
            "zha_devices",
            {},
            blocking=True,
            return_response=True
        )
        
        if result and "devices" in result:
            for device in result["devices"]:
                if device.get("ieee") == ieee:
                    _LOGGER.debug("Found ZHA device info for %s: %s", ieee, device)
                    return {
                        "manufacturer": device.get("manufacturer"),
                        "model": device.get("model"),
                        "sw_version": device.get("sw_version"),
                        "hw_version": device.get("hw_version"),
                    }
    except Exception as e:
        _LOGGER.warning("Could not get ZHA device info: %s", e)
    
    return {}


async def _debug_check_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Отладочная функция для проверки созданных сущностей."""
    _LOGGER.debug("=== Checking registered entities ===")
    
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    
    # Проверяем устройства
    devices = device_registry.devices.values()
    ir_devices = [d for d in devices if entry.entry_id in [e.id for e in d.config_entries]]
    _LOGGER.debug("Found %d devices for this integration:", len(ir_devices))
    for device in ir_devices:
        _LOGGER.debug("  Device: %s (identifiers: %s)", device.name, device.identifiers)
    
    # Проверяем сущности
    entities = [e for e in entity_registry.entities.values() if e.config_entry_id == entry.entry_id]
    _LOGGER.debug("Found %d entities for this integration:", len(entities))
    
    by_domain = {}
    for entity in entities:
        domain = entity.domain
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(entity)
    
    for domain, domain_entities in by_domain.items():
        _LOGGER.debug("  %s domain: %d entities", domain, len(domain_entities))
        for entity in domain_entities:
            _LOGGER.debug("    %s: %s (unique_id: %s, device_id: %s)", 
                         entity.entity_id, entity.original_name, entity.unique_id, entity.device_id)
    
    _LOGGER.debug("=== Entity check completed ===")



async def _register_services(hass: HomeAssistant) -> None:
    """Регистрация сервисов IR Remote."""
    # Регистрация сервисов
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_CODE,
        async_learn_ir_code,
        schema=LEARN_CODE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_CODE,
        async_send_ir_code,
        schema=SEND_CODE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=SEND_COMMAND_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DATA,
        async_get_data,
        schema=GET_DATA_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_DEVICE,
        async_add_device,
        schema=ADD_DEVICE_SCHEMA
    )
    
    # Сервис для обновления списка команд
    async def async_update_commands(call: ServiceCall) -> None:
        """Сервис для обновления списка команд устройства."""
        device = call.data.get(ATTR_DEVICE)
        
        # Находим селектор команд
        for entity_id, entity in hass.data.get("entity_components", {}).get("select", {}).entities.items():
            from .entities import IRRemoteCommandSelector
            if isinstance(entity, IRRemoteCommandSelector):
                await entity.async_update_commands(device)
                break
    
    hass.services.async_register(
        DOMAIN,
        "update_commands",
        async_update_commands,
        schema=vol.Schema({
            vol.Required(ATTR_DEVICE): cv.string,
        })
    )
    
    _LOGGER.debug("Registered services: %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s",
                DOMAIN, SERVICE_LEARN_CODE, 
                DOMAIN, SERVICE_SEND_CODE,
                DOMAIN, SERVICE_SEND_COMMAND,
                DOMAIN, SERVICE_GET_DATA,
                DOMAIN, SERVICE_ADD_DEVICE,
                DOMAIN, "update_commands")


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
        hass.services.async_remove(DOMAIN, SERVICE_SEND_COMMAND)
        hass.services.async_remove(DOMAIN, SERVICE_GET_DATA)
        hass.services.async_remove(DOMAIN, SERVICE_ADD_DEVICE)
        
        # Remove data
        hass.data.pop(DOMAIN, None)
    
    return unload_ok

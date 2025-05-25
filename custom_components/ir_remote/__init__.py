"""IR Remote integration for Home Assistant - исправленная версия."""
import logging
import os
from typing import Any
from pathlib import Path

import aiofiles
import asyncio
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
    SERVICE_REMOVE_DEVICE,
    SERVICE_REMOVE_COMMAND,
    SERVICE_EXPORT_CONFIG,
    SERVICE_IMPORT_CONFIG,
    ATTR_DEVICE,
    ATTR_BUTTON,
    ATTR_CODE,
    ZHA_COMMAND_LEARN,
    ZHA_COMMAND_SEND,
)
from .data import IRRemoteData, setup_ir_data_coordinator

_LOGGER = logging.getLogger(__name__)

async def async_create_notification(hass: HomeAssistant, message: str, title: str, notification_id: str) -> None:
    """Создать уведомление пользователю."""
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": message,
                "title": title,
                "notification_id": notification_id
            }
        )
    except Exception as e:
        _LOGGER.debug("Could not create notification: %s", e)
        # Если не получается создать уведомление, просто логируем
        _LOGGER.info("Notification: %s - %s", title, message)
        
# Define platforms to load
PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.TEXT]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Service schemas - остаются те же самые
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

REMOVE_DEVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE): cv.string,
})

REMOVE_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE): cv.string,
    vol.Required("command"): cv.string,
})

EXPORT_CONFIG_SCHEMA = vol.Schema({})

IMPORT_CONFIG_SCHEMA = vol.Schema({
    vol.Required("config"): dict,
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
        await async_create_notification(
            hass,
            "Ошибка: отсутствует конфигурация ИК-пульта",
            "IR Remote: Ошибка",
            f"{DOMAIN}_error"
        )
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
        _LOGGER.info("Команда обучения ИК-коду успешно отправлена для %s - %s", device, button)
        
        # Добавим уведомление для пользователя
        await async_create_notification(
            hass,
            f"Ожидание сигнала ИК-пульта для устройства {device}, кнопки {button}. "
            "Направьте пульт на ИК-приемник и нажмите кнопку, которой хотите обучить.",
            "IR Remote: Режим обучения",
            f"{DOMAIN}_learning"
        )
    except Exception as e:
        _LOGGER.error("Ошибка отправки команды обучения ИК-коду: %s", e)
        # Добавим уведомление об ошибке
        await async_create_notification(
            hass,
            f"Ошибка при отправке команды обучения: {e}",
            "IR Remote: Ошибка",
            f"{DOMAIN}_error"
        )
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
        await async_create_notification(
            hass,
            "Ошибка: отсутствует конфигурация ИК-пульта",
            "IR Remote: Ошибка",
            f"{DOMAIN}_error"
        )
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
        _LOGGER.info("ИК-код успешно отправлен (длина кода: %d символов)", len(code))
    except Exception as e:
        _LOGGER.error("Ошибка отправки ИК-кода: %s", e)
        # Добавим уведомление об ошибке
        await async_create_notification(
            hass,
            f"Ошибка при отправке ИК-кода: {e}",
            "IR Remote: Ошибка",
            f"{DOMAIN}_error"
        )
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

async def async_remove_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для удаления устройства."""
    device_name = call.data.get(ATTR_DEVICE)
    
    if not device_name:
        _LOGGER.error("Имя устройства не может быть пустым")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Удаляем устройство
    success = await ir_data.async_remove_device(device_name)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        await hass.config_entries.async_reload(hass.data[DOMAIN].get("config_entry_id"))
    else:
        _LOGGER.error("Не удалось удалить устройство %s", device_name)


async def async_remove_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для удаления команды."""
    device_name = call.data.get(ATTR_DEVICE)
    command = call.data.get("command")
    
    if not device_name or not command:
        _LOGGER.error("Имя устройства и команда не могут быть пустыми")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Удаляем команду
    success = await ir_data.async_remove_command(device_name, command)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        await hass.config_entries.async_reload(hass.data[DOMAIN].get("config_entry_id"))
    else:
        _LOGGER.error("Не удалось удалить команду %s для устройства %s", command, device_name)



async def async_export_config(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Сервис для экспорта конфигурации."""
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return {"error": "Data storage not initialized"}
    
    # Экспортируем конфигурацию
    config = await ir_data.async_export_config()
    
    _LOGGER.info("Экспортирована конфигурация с %d устройствами", len(config.get("devices", {})))
    
    return config


async def async_import_config(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для импорта конфигурации."""
    config = call.data.get("config")
    
    if not config:
        _LOGGER.error("Конфигурация не предоставлена")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Импортируем конфигурацию
    success = await ir_data.async_import_config(config)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        await hass.config_entries.async_reload(hass.data[DOMAIN].get("config_entry_id"))
    else:
        _LOGGER.error("Не удалось импортировать конфигурацию")


async def async_import_config(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для импорта конфигурации."""
    config = call.data.get("config")
    
    if not config:
        _LOGGER.error("Конфигурация не предоставлена")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return
    
    # Импортируем конфигурацию
    success = await ir_data.async_import_config(config)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        await hass.config_entries.async_reload(hass.data[DOMAIN].get("config_entry_id"))
    else:
        _LOGGER.error("Не удалось импортировать конфигурацию")


async def _update_device_buttons(hass: HomeAssistant, entry: ConfigEntry, device_name: str, command_name: str) -> None:
    """Динамически обновляет кнопки устройства при добавлении новой команды."""
    try:
        from .entities import IRRemoteDeviceButton
        
        # Получаем данные о новой команде
        ir_data = hass.data[DOMAIN].get("data")
        if not ir_data:
            _LOGGER.warning("IR data not available for dynamic button update")
            return
        
        # Загружаем данные
        await ir_data.async_load()
        codes = ir_data._data
        
        if not codes or device_name not in codes or command_name not in codes[device_name]:
            _LOGGER.warning("Command data not found for %s - %s", device_name, command_name)
            return
        
        command_data = codes[device_name][command_name]
        
        # Создаем новую кнопку
        new_button = IRRemoteDeviceButton(
            hass,
            entry,
            device_name,
            command_name,
            command_data,
        )
        
        # Добавляем кнопку через entity platform
        if "entity_components" in hass.data and "button" in hass.data["entity_components"]:
            entity_platform = hass.data["entity_components"]["button"]
            await entity_platform.async_add_entities([new_button])
            _LOGGER.info("Динамически добавлена кнопка: %s - %s", device_name, command_name)
        else:
            _LOGGER.warning("Button entity platform not available for dynamic button creation")
            
    except Exception as e:
        _LOGGER.error("Error updating device buttons dynamically: %s", e, exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.info("Setting up IR Remote integration (domain: %s)", DOMAIN)
    
    # Инициализируем структуру данных
    hass.data.setdefault(DOMAIN, {})
    
    # Создаем директорию scripts, если её нет
    scripts_dir = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts"
    _LOGGER.debug("Scripts directory: %s", scripts_dir)
    
    try:
        await hass.async_add_executor_job(lambda: scripts_dir.mkdir(parents=True, exist_ok=True))
        _LOGGER.info("Scripts directory created/checked")
    except Exception as e:
        _LOGGER.error("Failed to initialize IR Remote files: %s", e, exc_info=True)
        return False
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.info("=== Setting up IR Remote entry ===")
    _LOGGER.info("Entry ID: %s", entry.entry_id)
    
    # Проверяем доступность ZHA
    if "zha" not in hass.data:
        _LOGGER.error("ZHA integration not found")
        raise ConfigEntryNotReady("ZHA integration not available")
    
    # Инициализация структуры данных
    hass.data[DOMAIN] = {
        "config": entry.data,
        "config_entry_id": entry.entry_id,
    }
    _LOGGER.info("Initialized domain data structure")
    
    try:
        # Настройка хранилища данных и координатора (СНАЧАЛА)
        _LOGGER.info("Setting up data coordinator...")
        coordinator = await setup_ir_data_coordinator(hass)
        hass.data[DOMAIN]["coordinator"] = coordinator
        _LOGGER.info("Coordinator setup completed")
        
        # Регистрируем устройство ПОСЛЕ того, как координатор готов
        device = await async_register_ir_remote_device(hass, entry)  
        _LOGGER.info("Device registered successfully: %s", device.id)
        
        # Настраиваем обработчик событий для сохранения IR-кодов
        async def handle_ir_code_learned(event):
            """Обработчик события обучения IR-коду."""
            device_name = event.data.get("device")
            button = event.data.get("button")
            code = event.data.get("code")
            
            if not device_name or not button or not code:
                _LOGGER.error("Получены неполные данные для сохранения IR-кода")
                return
            
            # Получаем хранилище данных
            ir_data = hass.data[DOMAIN].get("data")
            if not ir_data:
                _LOGGER.error("Хранилище данных IR не инициализировано")
                return
            
            # Сохраняем код
            success = await ir_data.async_add_command(device_name, button, code)
            
            if success:
                _LOGGER.info("IR-код для %s - %s успешно сохранен", device_name, button)
                # Обновляем координатор
                await coordinator.async_refresh()
                
                # Создаем уведомление об успешном сохранении
                await async_create_notification(
                    hass,
                    f"ИК-код для устройства '{device_name}', кнопки '{button}' успешно сохранен!",
                    "IR Remote: Код сохранен",
                    f"{DOMAIN}_saved"
                )
                
                # Обновляем кнопки устройств динамически
                await _update_device_buttons(hass, entry, device_name, button)
            else:
                _LOGGER.error("Не удалось сохранить IR-код для %s - %s", device_name, button)
                # Создаем уведомление об ошибке
                await async_create_notification(
                    hass,
                    f"Не удалось сохранить ИК-код для устройства '{device_name}', кнопки '{button}'",
                    "IR Remote: Ошибка",
                    f"{DOMAIN}_error"
                )

        
        # Регистрируем обработчик события
        hass.bus.async_listen(f"{DOMAIN}_ir_code_learned", handle_ir_code_learned)
        _LOGGER.info("Event handler registered")
        
        # Настраиваем обработчик событий ZHA
        async def handle_zha_event(event):
            """Обработчик событий от ZHA устройства."""
            device_ieee = event.data.get("device_ieee")
            endpoint_id = event.data.get("endpoint_id")
            cluster_id = event.data.get("cluster_id")
            command = event.data.get("command")
            args = event.data.get("args", {})
            
            # Проверяем, что это событие от нашего ИК-устройства
            if (device_ieee == entry.data.get(CONF_IEEE) and
                endpoint_id == entry.data.get(CONF_ENDPOINT) and
                cluster_id == entry.data.get(CONF_CLUSTER)):
                
                _LOGGER.debug("Получено событие ZHA от ИК-устройства: command=%s, args=%s", command, args)
                
                # Обрабатываем полученный ИК-код
                if "code" in args:
                    ir_code = args["code"]
                    device_name = args.get("device", "unknown")
                    button_name = args.get("button", "unknown")
                    
                    _LOGGER.info("Получен ИК-код от устройства: device=%s, button=%s", device_name, button_name)
                    
                    # Генерируем событие для сохранения кода
                    hass.bus.async_fire(f"{DOMAIN}_ir_code_learned", {
                        "device": device_name,
                        "button": button_name,
                        "code": ir_code
                    })
        
        # Регистрируем обработчик событий ZHA
        zha_listener = hass.bus.async_listen("zha_event", handle_zha_event)
        hass.data[DOMAIN]["zha_listener"] = zha_listener
        _LOGGER.info("ZHA event handler registered")
        
        # Регистрация сервисов
        await _register_services(hass)
        _LOGGER.info("Services registered")
        
        # Настраиваем платформы ПОСЛЕ всех других компонентов
        _LOGGER.info("Setting up platforms: %s", PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Platforms setup completed")
        
        # Даём время сущностям инициализироваться и принудительно обновляем координатор
        async def final_update():
            await asyncio.sleep(3)  # Увеличиваем время ожидания
            _LOGGER.info("Performing final coordinator update...")
            
            try:
                await coordinator.async_refresh()
                _LOGGER.info("Final coordinator update completed successfully")
                
                # Создаем уведомление об успешной настройке
                await async_create_notification(
                    hass,
                    "ИК-пульт успешно настроен и готов к использованию!",
                    "IR Remote: Настройка завершена",
                    f"{DOMAIN}_ready"
                )
            except Exception as e:
                _LOGGER.error("Error in final coordinator update: %s", e)
        
        hass.async_create_task(final_update())
        
        _LOGGER.info("IR Remote настроен успешно!")
        
        return True
        
    except Exception as e:
        _LOGGER.error("Error setting up IR Remote: %s", e, exc_info=True)
        
        # Очищаем данные при ошибке
        if DOMAIN in hass.data:
            hass.data.pop(DOMAIN, None)
        
        raise


async def async_register_ir_remote_device(hass: HomeAssistant, entry: ConfigEntry):
    """Регистрация устройства ИК-пульта в реестре устройств."""
    _LOGGER.info("=== Registering IR Remote device ===")
    
    device_registry = dr.async_get(hass)
    entry_id = entry.entry_id
    
    _LOGGER.info("Registering device with entry_id: %s", entry_id)
    
    # Получаем информацию о ZHA устройстве
    zha_device_info = await get_zha_device_info(hass, entry.data.get(CONF_IEEE))
    
    # Регистрируем устройство
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry_id)},  
        name="ИК-пульт",
        manufacturer=zha_device_info.get("manufacturer", "IR Remote Integration"),
        model=zha_device_info.get("model", "IR Controller"),
        sw_version=zha_device_info.get("sw_version", "1.2.0"),
        hw_version=zha_device_info.get("hw_version"),
    )
    
    _LOGGER.info("Device registered successfully")
    _LOGGER.info("Device ID: %s", device.id)
    _LOGGER.info("Device identifiers: %s", device.identifiers)
    
    return device


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
        _LOGGER.debug("Could not get ZHA device info: %s", e)
    
    return {}






async def _debug_check_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Отладочная функция для проверки созданных сущностей."""
    _LOGGER.debug("=== Checking registered entities ===")
    
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    
    # Проверяем устройства
    devices = device_registry.devices.values()
    ir_devices = [d for d in devices if entry.entry_id in d.config_entries]
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
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_DEVICE,
        async_remove_device,
        schema=REMOVE_DEVICE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_COMMAND,
        async_remove_command,
        schema=REMOVE_COMMAND_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_CONFIG,
        async_export_config,
        schema=EXPORT_CONFIG_SCHEMA,
        supports_response=True
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_CONFIG,
        async_import_config,
        schema=IMPORT_CONFIG_SCHEMA
    )
    
    _LOGGER.debug("Registered services: %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s",
                DOMAIN, SERVICE_LEARN_CODE, 
                DOMAIN, SERVICE_SEND_CODE,
                DOMAIN, SERVICE_SEND_COMMAND,
                DOMAIN, SERVICE_GET_DATA,
                DOMAIN, SERVICE_ADD_DEVICE,
                DOMAIN, SERVICE_REMOVE_DEVICE,
                DOMAIN, SERVICE_REMOVE_COMMAND,
                DOMAIN, SERVICE_EXPORT_CONFIG,
                DOMAIN, SERVICE_IMPORT_CONFIG)



async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading IR Remote entry: %s", entry.entry_id)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up
    if unload_ok:
        # Remove services
        for service in [SERVICE_LEARN_CODE, SERVICE_SEND_CODE, SERVICE_SEND_COMMAND, 
                       SERVICE_GET_DATA, SERVICE_ADD_DEVICE, SERVICE_REMOVE_DEVICE,
                       SERVICE_REMOVE_COMMAND, SERVICE_EXPORT_CONFIG, SERVICE_IMPORT_CONFIG]:
            hass.services.async_remove(DOMAIN, service)
        
        # Remove event listeners
        if DOMAIN in hass.data and "zha_listener" in hass.data[DOMAIN]:
            hass.data[DOMAIN]["zha_listener"]()
            _LOGGER.debug("Removed ZHA event listener")
        
        # Remove data
        hass.data.pop(DOMAIN, None)
    
    _LOGGER.info("IR Remote entry unloaded: %s", unload_ok)
    return unload_ok
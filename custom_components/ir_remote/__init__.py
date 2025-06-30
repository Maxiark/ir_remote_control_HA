"""IR Remote integration for Home Assistant - исправленная версия."""
import logging
import os
from typing import Any
from pathlib import Path

from functools import wraps
import aiofiles
import asyncio
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError, ConfigEntryNotReady
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

def service_handler(func):
    @wraps(func)
    async def wrapper(call: ServiceCall):
        hass = call.hass  # Получаем hass из call
        return await func(hass, call)
    return wrapper

@service_handler
async def async_learn_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис обучения ИК-кодам."""
    device = call.data.get(ATTR_DEVICE)
    button = call.data.get(ATTR_BUTTON)
    
    _LOGGER.info("🎓 НАЧАЛО ОБУЧЕНИЯ: устройство='%s', кнопка='%s'", device, button)
    
    # Получаем конфигурацию
    config = hass.data[DOMAIN].get("config", {})
    ieee = config.get(CONF_IEEE)
    endpoint_id = config.get(CONF_ENDPOINT)
    cluster_id = config.get(CONF_CLUSTER)
    
    _LOGGER.debug("📋 Конфигурация ZHA: ieee=%s, endpoint=%s, cluster=%s", ieee, endpoint_id, cluster_id)
    
    if not ieee or not endpoint_id or not cluster_id:
        _LOGGER.error("❌ Отсутствует конфигурация для ИК-пульта: ieee=%s, endpoint=%s, cluster=%s", 
                     ieee, endpoint_id, cluster_id)
        return
    
    try:
        _LOGGER.info("📤 Отправка команды обучения в ZHA...")
        _LOGGER.debug("📤 ZHA команда: ieee=%s, endpoint=%s, cluster=%s, command=%s, params=%s", 
                     ieee, endpoint_id, cluster_id, ZHA_COMMAND_LEARN, 
                     {"on_off": True, "device": device, "button": button})
        
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
        _LOGGER.info("✅ Команда обучения успешно отправлена для %s - %s", device, button)
        _LOGGER.info("⏳ Ожидание ИК-сигнала от пульта...")
        
    except Exception as e:
        _LOGGER.error("❌ Ошибка отправки команды обучения ИК-коду: %s", e, exc_info=True)
        raise HomeAssistantError(f"Не удалось отправить команду обучения ИК-коду: {e}") from e

@service_handler
async def async_send_ir_code(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки ИК-кодов."""
    code = call.data.get(ATTR_CODE)
    
    _LOGGER.debug("📡 Отправка ИК-кода: %s", code[:20] + "..." if len(code) > 20 else code)
    
    # Получаем конфигурацию
    config = hass.data[DOMAIN].get("config", {})
    ieee = config.get(CONF_IEEE)
    endpoint_id = config.get(CONF_ENDPOINT)
    cluster_id = config.get(CONF_CLUSTER)
    
    if not ieee or not endpoint_id or not cluster_id:
        _LOGGER.error("❌ Отсутствует конфигурация для ИК-пульта")
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
        _LOGGER.info("📡 ИК-код успешно отправлен (длина: %d символов)", len(code))
    except Exception as e:
        _LOGGER.error("❌ Ошибка отправки ИК-кода: %s", e, exc_info=True)
        raise HomeAssistantError(f"Не удалось отправить ИК-код: {e}") from e

@service_handler
async def async_send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для отправки команд по имени устройства и команды."""
    device = call.data.get(ATTR_DEVICE)
    command = call.data.get("command")
    
    _LOGGER.debug("🎮 Отправка команды: устройство=%s, команда=%s", device, command)
    
    if not device or not command or device == "none" or command == "none":
        _LOGGER.error("❌ Не указано устройство или команда: device=%s, command=%s", device, command)
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return
    
    # Получаем ИК-код
    code = ir_data.get_code(device, command)
    
    if not code:
        _LOGGER.error("❌ ИК-код не найден для %s - %s", device, command)
        return
    
    _LOGGER.debug("📡 Найден ИК-код для %s - %s, длина: %d", device, command, len(code))
    
    # Отправляем ИК-код
    await async_send_ir_code(hass, ServiceCall(DOMAIN, SERVICE_SEND_CODE, {ATTR_CODE: code}))

@service_handler
async def async_get_data(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Сервис для получения данных об устройствах и командах."""
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        _LOGGER.error("❌ Координатор данных IR не инициализирован")
        return {}
    
    # Обновляем данные
    await coordinator.async_refresh()
    
    # Формируем упрощенную структуру данных для возврата
    data = {
        "devices": coordinator.data.get("devices", [])[1:] if coordinator.data.get("devices") else [],
        "commands": {}
    }
    
    # Формируем списки команд для каждого устройства
    for device in data["devices"]:
        commands = coordinator.data.get("commands", {}).get(device, [])[1:] if coordinator.data.get("commands", {}).get(device) else []
        data["commands"][device] = commands
    
    return data

@service_handler
async def service_add_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для добавления нового устройства."""
    device_name = call.data.get("name")
    
    _LOGGER.info("➕ Добавление нового устройства: '%s'", device_name)
    
    if not device_name:
        _LOGGER.error("❌ Имя устройства не может быть пустым")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return
    
    # Добавляем устройство
    success = await ir_data.async_add_device(device_name)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            _LOGGER.debug("🔄 Обновление координатора после добавления устройства")
            await coordinator.async_refresh()
        _LOGGER.info("✅ Устройство %s успешно добавлено", device_name)
    else:
        _LOGGER.error("❌ Не удалось добавить устройство %s", device_name)

@service_handler
async def async_remove_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для удаления устройства."""
    device_name = call.data.get(ATTR_DEVICE)
    
    _LOGGER.info("🗑️ Удаление устройства: '%s'", device_name)
    
    if not device_name:
        _LOGGER.error("❌ Имя устройства не может быть пустым")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return
    
    # Удаляем устройство
    success = await ir_data.async_remove_device(device_name)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            _LOGGER.debug("🔄 Обновление координатора после удаления устройства")
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        config_entry_id = hass.data[DOMAIN].get("config_entry_id")
        if config_entry_id:
            _LOGGER.debug("🔄 Перезагрузка интеграции для обновления кнопок")
            await hass.config_entries.async_reload(config_entry_id)
    else:
        _LOGGER.error("❌ Не удалось удалить устройство %s", device_name)

@service_handler
async def async_remove_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для удаления команды."""
    device_name = call.data.get(ATTR_DEVICE)
    command = call.data.get("command")
    
    _LOGGER.info("🗑️ Удаление команды: устройство='%s', команда='%s'", device_name, command)
    
    if not device_name or not command:
        _LOGGER.error("❌ Имя устройства и команда не могут быть пустыми")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return
    
    # Удаляем команду
    success = await ir_data.async_remove_command(device_name, command)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            _LOGGER.debug("🔄 Обновление координатора после удаления команды")
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        config_entry_id = hass.data[DOMAIN].get("config_entry_id")
        if config_entry_id:
            _LOGGER.debug("🔄 Перезагрузка интеграции для обновления кнопок")
            await hass.config_entries.async_reload(config_entry_id)
    else:
        _LOGGER.error("❌ Не удалось удалить команду %s для устройства %s", command, device_name)

@service_handler
async def async_export_config(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Сервис для экспорта конфигурации."""
    _LOGGER.info("📤 Экспорт конфигурации")
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return {"error": "Data storage not initialized"}
    
    # Экспортируем конфигурацию
    config = await ir_data.async_export_config()
    
    _LOGGER.info("✅ Экспортирована конфигурация с %d устройствами", len(config.get("devices", {})))
    
    return config

@service_handler
async def async_import_config(hass: HomeAssistant, call: ServiceCall) -> None:
    """Сервис для импорта конфигурации."""
    config = call.data.get("config")
    
    _LOGGER.info("📥 Импорт конфигурации")
    
    if not config:
        _LOGGER.error("❌ Конфигурация не предоставлена")
        return
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("❌ Хранилище данных IR не инициализировано")
        return
    
    # Импортируем конфигурацию
    success = await ir_data.async_import_config(config)
    
    if success:
        # Обновляем данные координатора
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            _LOGGER.debug("🔄 Обновление координатора после импорта")
            await coordinator.async_refresh()
        
        # Перезагружаем интеграцию для обновления кнопок
        config_entry_id = hass.data[DOMAIN].get("config_entry_id")
        if config_entry_id:
            _LOGGER.debug("🔄 Перезагрузка интеграции для обновления кнопок")
            await hass.config_entries.async_reload(config_entry_id)
    else:
        _LOGGER.error("❌ Не удалось импортировать конфигурацию")


async def _update_device_buttons(hass: HomeAssistant, entry: ConfigEntry, device_name: str, command_name: str) -> None:
    """Динамически обновляет кнопки устройства при добавлении новой команды."""
    try:
        _LOGGER.debug("🔘 Попытка динамического создания кнопки: %s - %s", device_name, command_name)
        
        from .entities import IRRemoteDeviceButton
        
        # Получаем данные о новой команде
        ir_data = hass.data[DOMAIN].get("data")
        if not ir_data:
            _LOGGER.warning("❌ IR data не доступны для динамического обновления кнопки")
            return
        
        # Загружаем данные
        await ir_data.async_load()
        codes = ir_data._data
        
        if not codes or device_name not in codes or command_name not in codes[device_name]:
            _LOGGER.warning("❌ Данные команды не найдены для %s - %s", device_name, command_name)
            return
        
        command_data = codes[device_name][command_name]
        _LOGGER.debug("📋 Данные команды: %s", command_data)
        
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
            _LOGGER.info("✅ Динамически добавлена кнопка: %s - %s", device_name, command_name)
        else:
            _LOGGER.warning("❌ Button entity platform недоступна для динамического создания кнопки")
            
    except Exception as e:
        _LOGGER.error("❌ Ошибка динамического обновления кнопок: %s", e, exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IR Remote component."""
    _LOGGER.info("🚀 Настройка IR Remote интеграции (домен: %s)", DOMAIN)
    
    # Инициализируем структуру данных
    hass.data.setdefault(DOMAIN, {})
    
    _LOGGER.info("✅ IR Remote интеграция инициализирована")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Remote from a config entry."""
    _LOGGER.info("=== 🚀 НАСТРОЙКА IR REMOTE ENTRY ===")
    _LOGGER.info("📋 Entry ID: %s", entry.entry_id)
    _LOGGER.info("📋 Entry data: %s", entry.data)
    
    # Проверяем доступность ZHA
    if "zha" not in hass.data:
        _LOGGER.error("❌ ZHA интеграция не найдена")
        raise ConfigEntryNotReady("ZHA integration not available")
    
    # Инициализация структуры данных
    hass.data[DOMAIN] = {
        "config": entry.data,
        "config_entry_id": entry.entry_id,
    }
    _LOGGER.info("✅ Инициализирована структура данных домена")
    
    try:
        # Настройка хранилища данных и координатора (СНАЧАЛА)
        _LOGGER.info("🔧 Настройка координатора данных...")
        coordinator = await setup_ir_data_coordinator(hass)
        hass.data[DOMAIN]["coordinator"] = coordinator
        _LOGGER.info("✅ Координатор настроен успешно")
        
        # Регистрируем устройство ПОСЛЕ того, как координатор готов
        device = await async_register_ir_remote_device(hass, entry)  
        _LOGGER.info("✅ Устройство зарегистрировано: %s", device.id)
        
        # Настраиваем обработчик событий для сохранения IR-кодов
        async def handle_ir_code_learned(event):
            """Обработчик события обучения IR-коду."""
            device_name = event.data.get("device")
            button = event.data.get("button")
            code = event.data.get("code")
            
            _LOGGER.info("🎯 ПОЛУЧЕНО СОБЫТИЕ ОБУЧЕНИЯ: device=%s, button=%s, code_len=%d", 
                        device_name, button, len(code) if code else 0)
            
            if not device_name or not button or not code:
                _LOGGER.error("❌ Получены неполные данные для сохранения IR-кода: device=%s, button=%s, code=%s", 
                            device_name, button, "есть" if code else "нет")
                return
            
            # Получаем хранилище данных
            ir_data = hass.data[DOMAIN].get("data")
            if not ir_data:
                _LOGGER.error("❌ Хранилище данных IR не инициализировано")
                return
            
            _LOGGER.debug("💾 Попытка сохранения IR-кода...")
            
            # Сохраняем код
            success = await ir_data.async_add_command(device_name, button, code)
            
            if success:
                _LOGGER.info("✅ IR-код для %s - %s успешно сохранен", device_name, button)
                
                # Обновляем координатор
                _LOGGER.debug("🔄 Обновление координатора...")
                await coordinator.async_refresh()
                _LOGGER.debug("✅ Координатор обновлен")
                
                # Обновляем кнопки устройств динамически
                _LOGGER.debug("🔘 Попытка динамического обновления кнопок...")
                await _update_device_buttons(hass, entry, device_name, button)
                
            else:
                _LOGGER.error("❌ Не удалось сохранить IR-код для %s - %s", device_name, button)

        
        # Регистрируем обработчик события
        hass.bus.async_listen(f"{DOMAIN}_ir_code_learned", handle_ir_code_learned)
        _LOGGER.info("✅ Обработчик событий зарегистрирован")
        
        # Настраиваем обработчик событий ZHA
        async def handle_zha_event(event):
            """Обработчик событий от ZHA устройства."""
            _LOGGER.debug("🔥 ZHA EVENT RECEIVED: %s", event.data)
            expected_ieee = entry.data.get(CONF_IEEE)
            expected_endpoint = entry.data.get(CONF_ENDPOINT)
            expected_cluster = entry.data.get(CONF_CLUSTER)
            
            _LOGGER.debug("🎯 ОЖИДАЕМ: ieee=%s, endpoint=%s, cluster=%s", 
                         expected_ieee, expected_endpoint, expected_cluster)
            
            device_ieee = event.data.get("device_ieee")
            endpoint_id = event.data.get("endpoint_id")
            cluster_id = event.data.get("cluster_id")
            command = event.data.get("command")
            args = event.data.get("args", {})
            
            _LOGGER.debug("🔍 EVENT DETAILS: ieee=%s, endpoint=%s, cluster=%s, command=%s, args=%s", 
                 device_ieee, endpoint_id, cluster_id, command, args)
            
            # Проверяем, что это событие от нашего ИК-устройства
            if (device_ieee == entry.data.get(CONF_IEEE) and
                endpoint_id == entry.data.get(CONF_ENDPOINT) and
                cluster_id == entry.data.get(CONF_CLUSTER)):
                
                _LOGGER.info("🎯 Получено событие ZHA от ИК-устройства: command=%s, args=%s", command, args)
                
                # Обрабатываем полученный ИК-код
                if "code" in args:
                    ir_code = args["code"]
                    device_name = args.get("device", "unknown")
                    button_name = args.get("button", "unknown")
                    
                    _LOGGER.info("📥 Получен ИК-код от устройства: device=%s, button=%s, code_len=%d", 
                               device_name, button_name, len(ir_code))
                    
                    # Генерируем событие для сохранения кода
                    _LOGGER.debug("🚀 Генерация события для сохранения кода...")
                    hass.bus.async_fire(f"{DOMAIN}_ir_code_learned", {
                        "device": device_name,
                        "button": button_name,
                        "code": ir_code
                    })
                    _LOGGER.debug("✅ Событие сгенерировано")
                else:
                    _LOGGER.warning("❌ НЕТ КОДА В ARGS: %s", args)
            else:
                _LOGGER.debug("⏭️ СОБЫТИЕ НЕ ОТ НАШЕГО УСТРОЙСТВА (ieee=%s vs %s, endpoint=%s vs %s, cluster=%s vs %s)", 
                            device_ieee, expected_ieee, endpoint_id, expected_endpoint, cluster_id, expected_cluster)
        
        # Регистрируем обработчик событий ZHA
        zha_listener = hass.bus.async_listen("zha_event", handle_zha_event)
        hass.data[DOMAIN]["zha_listener"] = zha_listener
        _LOGGER.info("✅ ZHA обработчик событий зарегистрирован")
        
        # Регистрация сервисов
        await _register_services(hass)
        _LOGGER.info("✅ Сервисы зарегистрированы")
        
        # Настраиваем платформы ПОСЛЕ всех других компонентов
        _LOGGER.info("🔧 Настройка платформ: %s", PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("✅ Платформы настроены")
        
        # Даём время сущностям инициализироваться и принудительно обновляем координатор
        async def final_update():
            await asyncio.sleep(3)  # Увеличиваем время ожидания
            _LOGGER.info("🔄 Выполнение финального обновления координатора...")
            
            try:
                await coordinator.async_refresh()
                _LOGGER.info("✅ Финальное обновление координатора завершено успешно")
            except Exception as e:
                _LOGGER.error("❌ Ошибка в финальном обновлении координатора: %s", e)
        
        hass.async_create_task(final_update())
        
        _LOGGER.info("🎉 IR Remote настроен успешно!")
        
        return True
        
    except Exception as e:
        _LOGGER.error("❌ Ошибка настройки IR Remote: %s", e, exc_info=True)
        
        # Очищаем данные при ошибке
        if DOMAIN in hass.data:
            hass.data.pop(DOMAIN, None)
        
        raise


async def async_register_ir_remote_device(hass: HomeAssistant, entry: ConfigEntry):
    """Регистрация устройства ИК-пульта в реестре устройств."""
    _LOGGER.info("=== 📱 РЕГИСТРАЦИЯ IR REMOTE УСТРОЙСТВА ===")
    
    device_registry = dr.async_get(hass)
    entry_id = entry.entry_id
    
    _LOGGER.info("📋 Регистрация устройства с entry_id: %s", entry_id)
    
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
    
    _LOGGER.info("✅ Устройство зарегистрировано успешно")
    _LOGGER.info("📋 Device ID: %s", device.id)
    _LOGGER.info("📋 Device identifiers: %s", device.identifiers)
    
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
                    _LOGGER.debug("📋 Найдена информация о ZHA устройстве для %s: %s", ieee, device)
                    return {
                        "manufacturer": device.get("manufacturer"),
                        "model": device.get("model"),
                        "sw_version": device.get("sw_version"),
                        "hw_version": device.get("hw_version"),
                    }
    except Exception as e:
        _LOGGER.debug("⚠️ Не удалось получить информацию о ZHA устройстве: %s", e)
    
    return {}


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
        service_add_device,
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
    
    _LOGGER.info("✅ Зарегистрированы сервисы: %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s, %s.%s",
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
    _LOGGER.info("🗑️ Выгрузка IR Remote entry: %s", entry.entry_id)
    
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
            _LOGGER.debug("✅ Удален ZHA обработчик событий")
        
        # Remove data
        hass.data.pop(DOMAIN, None)
    
    _LOGGER.info("✅ IR Remote entry выгружен: %s", unload_ok)
    return unload_ok
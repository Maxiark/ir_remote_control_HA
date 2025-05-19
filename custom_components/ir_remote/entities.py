"""IR Remote entities for Home Assistant."""
import logging
import json
import asyncio
import aiofiles
from pathlib import Path
from typing import Any, List, Optional, Dict, Callable

from homeassistant.components.select import SelectEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    DEFAULT_CLUSTER_TYPE,
    DEFAULT_COMMAND_TYPE,
    ATTR_DEVICE,
    ATTR_BUTTON,
    ATTR_CODE,
    ZHA_COMMAND_LEARN,
    ZHA_COMMAND_SEND,
)

_LOGGER = logging.getLogger(__name__)

# Глобальные переменные для хранения ссылок на сущности
_DEVICE_SELECTORS = {}
_COMMAND_SELECTORS = {}
_TEXT_INPUTS = {}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote entities."""
    _LOGGER.debug("Setting up IR Remote entities")

    # Create data coordinator for device and command lists
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="ir_remote_data",
        update_method=lambda: _update_ir_data(hass),
        update_interval=None,  # Manual updates only
    )
    
    # Initial data fetch
    await coordinator.async_refresh()
    
    # Создаем все сущности и сохраняем ссылки
    send_device_selector = IRRemoteDeviceSelector(hass, config_entry, coordinator, "send", sort_order=10)
    command_selector = IRRemoteCommandSelector(hass, config_entry, coordinator, sort_order=11)
    send_button = IRRemoteSendButton(hass, config_entry, coordinator, sort_order=12)
    
    learn_device_selector = IRRemoteDeviceSelector(hass, config_entry, coordinator, "learn", sort_order=20)
    button_input = IRRemoteButtonInput(hass, config_entry, coordinator, sort_order=21)
    learn_button = IRRemoteLearnButton(hass, config_entry, coordinator, sort_order=22)
    
    new_device_input = IRRemoteNewDeviceInput(hass, config_entry, coordinator, sort_order=30)
    add_device_button = IRRemoteAddDeviceButton(hass, config_entry, coordinator, sort_order=31)
    
    # Сохраняем ссылки в глобальных переменных
    _DEVICE_SELECTORS["send"] = send_device_selector
    _DEVICE_SELECTORS["learn"] = learn_device_selector
    _COMMAND_SELECTORS["command"] = command_selector
    _TEXT_INPUTS["button"] = button_input
    _TEXT_INPUTS["new_device"] = new_device_input
    
    entities = [
        # UI Controls
        send_device_selector,
        command_selector,
        send_button,
        
        learn_device_selector,
        button_input,
        learn_button,
        
        new_device_input,
        add_device_button,
    ]
    
    # Debug для проверки созданных сущностей
    for entity in entities:
        _LOGGER.debug("Добавление сущности: %s (unique_id: %s)", 
                    entity.name if hasattr(entity, "name") else "Unknown", 
                    entity.unique_id if hasattr(entity, "unique_id") else "Unknown")
    
    async_add_entities(entities)


async def _update_ir_data(hass: HomeAssistant) -> dict:
    """Обновление данных ИК-пульта напрямую из json-файла."""
    data = {
        "devices": ["none"],
        "commands": {},
        "codes": {}
    }
    
    # Путь к файлу с кодами
    ir_codes_path = Path(__file__).parent / "scripts" / "ir_codes.json"
    _LOGGER.debug("Путь к файлу IR-кодов: %s", ir_codes_path)
    
    try:
        # Проверяем существование файла
        if await hass.async_add_executor_job(lambda: ir_codes_path.exists()):
            # Читаем файл
            async with aiofiles.open(ir_codes_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                _LOGGER.debug("Прочитан файл IR-кодов размером %d байт", len(content))
                
                codes = json.loads(content)
                data["codes"] = codes
                
                # Формируем список устройств
                device_list = sorted(list(codes.keys()))
                if device_list:
                    data["devices"] = ["none"] + device_list
                    _LOGGER.debug("Устройства из ir_codes.json: %s", device_list)
                
                # Формируем списки команд для каждого устройства
                for device in device_list:
                    commands = ["none"] + list(codes[device].keys())
                    data["commands"][device] = commands
                    _LOGGER.debug("Команды для %s: %s", device, commands)
        else:
            _LOGGER.warning("Файл IR-кодов не найден: %s", ir_codes_path)
            # Создаем пустой файл
            await hass.async_add_executor_job(lambda: ir_codes_path.parent.mkdir(exist_ok=True))
            async with aiofiles.open(ir_codes_path, 'w', encoding='utf-8') as f:
                await f.write("{}")
                
    except json.JSONDecodeError as e:
        _LOGGER.error("Ошибка декодирования JSON: %s", e)
    except Exception as e:
        _LOGGER.error("Ошибка обновления данных IR: %s", e, exc_info=True)
    
    return data


async def add_device(hass: HomeAssistant, device_name: str) -> bool:
    """Добавление нового устройства напрямую в ir_codes.json."""
    if not device_name:
        _LOGGER.warning("Имя устройства не может быть пустым")
        return False
        
    # Предварительная обработка имени устройства
    device_name = device_name.strip()
    _LOGGER.debug(f"Добавление устройства, имя после обработки: '{device_name}'")
    
    config_path = Path(__file__).parent / "scripts" / "ir_codes.json"
    
    try:
        codes = {}
        
        if await hass.async_add_executor_job(lambda: config_path.exists()):
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
        
        if device_name in codes:
            _LOGGER.warning(f"Устройство {device_name} уже существует")
            return False
            
        codes[device_name] = {}
        
        # Убедимся, что используется правильная кодировка
        json_content = json.dumps(codes, indent=2, ensure_ascii=False)
        
        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json_content)
        
        _LOGGER.info(f"Устройство {device_name} успешно добавлено")
        return True
        
    except Exception as e:
        _LOGGER.error(f"Ошибка добавления устройства: {e}", exc_info=True)
        return False


async def save_ir_code(hass: HomeAssistant, device: str, button: str, code: str) -> bool:
    """Сохранение ИК-кода напрямую в ir_codes.json."""
    config_path = Path(__file__).parent / "scripts" / "ir_codes.json"
    
    try:
        codes = {}
        
        if await hass.async_add_executor_job(lambda: config_path.exists()):
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
        
        # Создаем устройство, если его нет
        if device not in codes:
            codes[device] = {}
        
        codes[device][button] = {
            "code": code,
            "name": f"{device.upper()} {button.replace('_', ' ').title()}",
            "description": f"IR code for {device} {button}"
        }
        
        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(codes, indent=2, ensure_ascii=False))
        
        _LOGGER.info(f"Сохранен код для {device} - {button}")    
        return True
        
    except Exception as e:
        _LOGGER.error(f"Ошибка сохранения IR-кода: {e}", exc_info=True)
        return False
    

class IRRemoteDeviceSelector(CoordinatorEntity, SelectEntity):
    """Entity for selecting IR Remote device."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        mode: str,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self.mode = mode  # "learn" or "send"
        
        # Используем названия групп для интуитивного порядка
        group_prefix = "01" if mode == "send" else ("02" if mode == "learn" else "03")
        
        # Генерируем наиболее интуитивное имя и ID для правильной сортировки
        display_name = "Выбор устройства" if mode == "send" else "Устройство для обучения"
        self._attr_unique_id = f"ir_remote_{group_prefix}_{sort_order:02d}_{mode}_device"
        self._attr_name = f"{display_name}"
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        self._attr_has_entity_name = True
        self._attr_translation_key = f"{mode}_device"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        if self.coordinator.data:
            # Подробная отладка доступных устройств
            devices = self.coordinator.data.get("devices", ["none"])
            _LOGGER.debug("Получены устройства из координатора: %s", devices)
            
            # Обновляем список опций в селекторе
            self._attr_options = devices
            
            # Если текущая опция отсутствует в новом списке, сбрасываем на none
            if self._attr_current_option not in devices:
                _LOGGER.debug("Текущее устройство '%s' отсутствует в новом списке, сбрасываем", 
                           self._attr_current_option)
                self._attr_current_option = "none"
                
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
        # If in send mode, update command selector when device changes
        if self.mode == "send":
            # Find and update the command selector
            command_selector = _COMMAND_SELECTORS.get("command")
            if command_selector:
                await command_selector.async_update_commands(option)


class IRRemoteCommandSelector(CoordinatorEntity, SelectEntity):
    """Entity for selecting IR Remote command."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_01_{sort_order:02d}_command_selector"
        self._attr_name = "Выбор команды"
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        self._attr_has_entity_name = True
        self._attr_translation_key = "send_command"
        self._device = "none"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        # Commands will be updated via the device selector
        pass

    async def async_update_commands(self, device: str) -> None:
        """Update command list for selected device."""
        self._device = device
        
        if device == "none" or not self.coordinator.data:
            self._attr_options = ["none"]
        else:
            self._attr_options = self.coordinator.data.get("commands", {}).get(device, ["none"])
        
        self._attr_current_option = "none"
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        self._attr_current_option = option
        self.async_write_ha_state()


class IRRemoteButtonInput(CoordinatorEntity, TextEntity):
    """Entity for entering button name."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_02_{sort_order:02d}_button_input"
        self._attr_name = "Название кнопки"
        self._attr_native_value = ""
        self._attr_has_entity_name = True
        self._attr_translation_key = "button_name"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе
        self._attr_mode = "text"  # Добавлено для соответствия требованиям TextEntity

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_set_value(self, value: str) -> None:
        """Set new value."""
        self._attr_native_value = value
        self.async_write_ha_state()


class IRRemoteNewDeviceInput(CoordinatorEntity, TextEntity):
    """Entity for entering new device name."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_03_{sort_order:02d}_new_device_input"
        self._attr_name = "Новое устройство"
        self._attr_native_value = ""
        self._attr_has_entity_name = True
        self._attr_translation_key = "new_device_name"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе
        self._attr_mode = "text"  # Добавлено для соответствия требованиям TextEntity

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_set_value(self, value: str) -> None:
        """Set new value."""
        self._attr_native_value = value
        self.async_write_ha_state()


class IRRemoteLearnButton(CoordinatorEntity, ButtonEntity):
    """Button entity to start IR learning."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_02_{sort_order:02d}_learn_button"
        self._attr_name = "Начать обучение"
        self._attr_has_entity_name = True
        self._attr_translation_key = "learn_button"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.debug("Кнопка обучения нажата")
        # Используем глобальные ссылки
        device_selector = _DEVICE_SELECTORS.get("learn")
        button_input = _TEXT_INPUTS.get("button")
        
        if not device_selector or not button_input:
            _LOGGER.warning("Селектор устройства или поле ввода кнопки не найдены")
            return
        
        device = device_selector.current_option
        button = button_input.native_value
        
        _LOGGER.debug("Обучение: устройство=%s, кнопка=%s", device, button)
        
        if device == "none" or not button:
            _LOGGER.warning("Невозможно начать обучение: device=%s, button=%s", device, button)
            return
        
        # Call learn service
        _LOGGER.debug("Вызов сервиса обучения для %s - %s", device, button)
        await self.hass.services.async_call(
            DOMAIN,
            "learn_code",
            {
                ATTR_DEVICE: device,
                ATTR_BUTTON: button,
            },
        )


class IRRemoteSendButton(CoordinatorEntity, ButtonEntity):
    """Button entity to send IR command."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_01_{sort_order:02d}_send_button"
        self._attr_name = "Отправить команду"
        self._attr_has_entity_name = True
        self._attr_translation_key = "send_button"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.debug("Кнопка отправки команды нажата")
        # Используем глобальные ссылки
        device_selector = _DEVICE_SELECTORS.get("send")
        command_selector = _COMMAND_SELECTORS.get("command")
        
        if not device_selector or not command_selector:
            _LOGGER.warning("Селекторы устройства или команды не найдены")
            return
        
        device = device_selector.current_option
        command = command_selector.current_option
        
        _LOGGER.debug("Отправка команды: устройство=%s, команда=%s", device, command)
        
        if device == "none" or command == "none" or not self.coordinator.data:
            _LOGGER.warning("Невозможно отправить команду: device=%s, command=%s", device, command)
            return
        
        # Get IR code from data
        codes = self.coordinator.data.get("codes", {})
        if device in codes and command in codes[device]:
            code = codes[device][command].get("code")
            
            if code:
                # Call send service
                _LOGGER.debug("Отправка ИК-кода для %s - %s", device, command)
                await self.hass.services.async_call(
                    DOMAIN,
                    "send_code",
                    {
                        ATTR_CODE: code,
                    },
                )
            else:
                _LOGGER.warning("ИК-код не найден для %s - %s", device, command)
        else:
            _LOGGER.warning("Команда %s не найдена для устройства %s", command, device)


class IRRemoteAddDeviceButton(CoordinatorEntity, ButtonEntity):
    """Кнопка для добавления нового ИК-устройства."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        sort_order: int = 0
    ) -> None:
        """Инициализация сущности."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"ir_remote_03_{sort_order:02d}_add_device_button"
        self._attr_name = "Добавить устройство"
        self._attr_has_entity_name = True
        self._attr_translation_key = "add_device_button"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка добавления устройства нажата")
        # Используем глобальные ссылки
        new_device_input = _TEXT_INPUTS.get("new_device")
        
        if not new_device_input:
            _LOGGER.warning("Поле ввода нового устройства не найдено")
            return
        
        device_name = new_device_input.native_value
        device_name = device_name.strip() if device_name else ""
        
        _LOGGER.debug("Добавление устройства: '%s', длина: %d", device_name, len(device_name))
        
        if not device_name:
            _LOGGER.warning("Невозможно добавить устройство: пустое имя")
            return
        
        # Добавляем устройство напрямую
        _LOGGER.debug("Вызов функции add_device для '%s'", device_name)
        success = await add_device(self.hass, device_name)
        
        if success:
            _LOGGER.debug("Устройство '%s' успешно добавлено", device_name)
            # Очищаем поле ввода
            await new_device_input.async_set_value("")
            
            # Обновляем данные координатора
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error("Не удалось добавить устройство '%s'", device_name)
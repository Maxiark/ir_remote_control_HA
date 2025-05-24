"""IR Remote entities for Home Assistant - правильное исправление без костылей."""
import logging
from typing import Any, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers import entity_registry as er

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


class IRRemoteCoordinatorEntity(CoordinatorEntity):
    """Базовый класс для сущностей IR Remote с координатором."""
    
    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация сущности."""
        super().__init__(coordinator)
        
        self.config_entry = config_entry  # Сохраняем для доступа в других методах
        entry_id = config_entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_has_entity_name = True
        self._attr_entity_category = None
        self._attr_should_poll = False
        
        # Устанавливаем device_info как атрибут
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="ИК-пульт",
            manufacturer="IR Remote Integration",
            model="IR Controller", 
            sw_version="1.2.0",
        )
        
        _LOGGER.info("Created entity: unique_id=%s, name=%s", self._attr_unique_id, name)
    
    @property
    def _context(self):
        """Возвращает контекст для вызова сервисов."""
        return self.hass.context()


class IRRemoteDeviceSelector(IRRemoteCoordinatorEntity, SelectEntity):
    """Селектор устройств IR Remote."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
        device_type: str = "send",
    ) -> None:
        """Инициализация селектора устройств."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self.device_type = device_type
        self._attr_translation_key = f"{device_type}_device"
        
        # Инициализируем опции из координатора
        if coordinator.data and "devices" in coordinator.data:
            self._attr_options = coordinator.data["devices"]
            _LOGGER.info("Device selector initialized with %d devices: %s", 
                        len(self._attr_options), self._attr_options)
        else:
            self._attr_options = ["none"]
            _LOGGER.info("Device selector initialized with default options")
            
        self._attr_current_option = "none"
        
        _LOGGER.info("Created device selector: type=%s, unique_id=%s, options=%s", 
                    device_type, self._attr_unique_id, self._attr_options)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            self._attr_options = devices
            
            if self._attr_current_option not in devices:
                self._attr_current_option = "none"
            
            _LOGGER.info("Device selector updated with devices: %s", devices)
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
        _LOGGER.info("Device selector option changed to: %s", option)
        
        if self.device_type == "send":
            # Находим селектор команд напрямую
            entity_registry = er.async_get(self.hass)
            command_selector_id = None
            
            for entity_id, entity_entry in entity_registry.entities.items():
                if (entity_entry.config_entry_id == self.config_entry.entry_id and
                    "command_selector" in entity_entry.unique_id):
                    command_selector_id = entity_id
                    break
            
            if command_selector_id:
                # Получаем объект сущности
                entity = self.hass.data["entity_components"]["select"].get_entity(command_selector_id)
                if entity:
                    from . import IRRemoteCommandSelector
                    if isinstance(entity, IRRemoteCommandSelector):
                        await entity.async_update_commands(option)
                        _LOGGER.info("Updated commands for device: %s", option)


class IRRemoteCommandSelector(IRRemoteCoordinatorEntity, SelectEntity):
    """Селектор команд IR Remote."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация селектора команд."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_translation_key = "send_command"
        self._device = "none"
        
        # Инициализируем с пустыми опциями
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        
        _LOGGER.info("Created command selector: unique_id=%s", self._attr_unique_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        if self._device != "none" and self.coordinator.data and "commands" in self.coordinator.data:
            commands = self.coordinator.data["commands"].get(self._device, ["none"])
            self._attr_options = commands
            
            if self._attr_current_option not in commands:
                self._attr_current_option = "none"
            
            _LOGGER.info("Command selector updated for device %s with commands: %s", 
                        self._device, commands)
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
        _LOGGER.info("Command selector option changed to: %s", option)
        
    async def async_update_commands(self, device: str) -> None:
        """Обновление списка команд для выбранного устройства."""
        self._device = device
        
        if device == "none" or not self.coordinator.data or "commands" not in self.coordinator.data:
            self._attr_options = ["none"]
            _LOGGER.info("Command selector cleared for device: %s", device)
        else:
            commands = self.coordinator.data["commands"].get(device, ["none"])
            self._attr_options = commands
            _LOGGER.info("Command selector updated for device %s: %s", device, commands)
        
        self._attr_current_option = "none"
        self.async_write_ha_state()


class IRRemoteButtonInput(IRRemoteCoordinatorEntity, TextEntity):
    """Текстовое поле для ввода имени кнопки."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация текстового поля."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_native_value = ""
        self._attr_translation_key = "button_name"
        self._attr_mode = "text"
        
        _LOGGER.info("Created button input: unique_id=%s", self._attr_unique_id)

    async def async_set_value(self, value: str) -> None:
        """Установка значения текстового поля."""
        self._attr_native_value = value
        self.async_write_ha_state()


class IRRemoteNewDeviceInput(IRRemoteCoordinatorEntity, TextEntity):
    """Текстовое поле для ввода имени нового устройства."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация текстового поля."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_native_value = ""
        self._attr_translation_key = "new_device_name"
        self._attr_mode = "text"
        
        _LOGGER.info("Created new device input: unique_id=%s", self._attr_unique_id)

    async def async_set_value(self, value: str) -> None:
        """Установка значения текстового поля."""
        self._attr_native_value = value
        self.async_write_ha_state()


class IRRemoteLearnButton(IRRemoteCoordinatorEntity, ButtonEntity):
    """Кнопка для начала обучения ИК-коду."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация кнопки."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_translation_key = "learn_button"
        
        _LOGGER.info("Created learn button: unique_id=%s", self._attr_unique_id)

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка обучения нажата")
        
        device_selector = None
        button_input = None
        entity_registry = er.async_get(self.hass)
        
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_entry.config_entry_id == self.config_entry.entry_id:
                if "learn_device" in entity_entry.unique_id:
                    entity = self.hass.states.get(entity_id)
                    if entity:
                        device_selector = entity
                elif "button_input" in entity_entry.unique_id:
                    entity = self.hass.states.get(entity_id)
                    if entity:
                        button_input = entity
        
        if not device_selector or not button_input:
            _LOGGER.warning("Селектор устройства или поле ввода кнопки не найдены")
            return
        
        device = device_selector.state if device_selector else "none"
        button = button_input.state if button_input else ""
        
        _LOGGER.debug("Обучение: устройство=%s, кнопка=%s", device, button)
        
        if device == "none" or not button:
            _LOGGER.warning("Невозможно начать обучение: device=%s, button=%s", device, button)
            return
        
        await self.hass.services.async_call(
            DOMAIN,
            "learn_code",
            {
                ATTR_DEVICE: device,
                ATTR_BUTTON: button,
            },
            blocking=True
        )


class IRRemoteSendButton(IRRemoteCoordinatorEntity, ButtonEntity):
    """Кнопка для отправки ИК-команды."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация кнопки."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_translation_key = "send_button"
        
        _LOGGER.info("Created send button: unique_id=%s", self._attr_unique_id)

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка отправки команды нажата")
        
        device_selector = None
        command_selector = None
        entity_registry = er.async_get(self.hass)
        
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_entry.config_entry_id == self.config_entry.entry_id:
                if "send_device" in entity_entry.unique_id:
                    entity = self.hass.states.get(entity_id)
                    if entity:
                        device_selector = entity
                elif "command_selector" in entity_entry.unique_id:
                    entity = self.hass.states.get(entity_id)
                    if entity:
                        command_selector = entity
        
        if not device_selector or not command_selector:
            _LOGGER.warning("Селектор устройства или селектор команды не найдены")
            return
        
        device = device_selector.state if device_selector else "none"
        command = command_selector.state if command_selector else "none"
        
        _LOGGER.debug("Отправка команды: устройство=%s, команда=%s", device, command)
        
        if device == "none" or command == "none":
            _LOGGER.warning("Невозможно отправить команду: device=%s, command=%s", device, command)
            return
        
        await self.hass.services.async_call(
            DOMAIN,
            "send_command",
            {
                ATTR_DEVICE: device,
                "command": command,
            },
            blocking=True
        )


class IRRemoteAddDeviceButton(IRRemoteCoordinatorEntity, ButtonEntity):
    """Кнопка для добавления нового ИК-устройства."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация кнопки."""
        super().__init__(coordinator, config_entry, unique_id_suffix, name)
        self._attr_translation_key = "add_device_button"
        
        _LOGGER.info("Created add device button: unique_id=%s", self._attr_unique_id)

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка добавления устройства нажата")
        
        new_device_input = None
        entity_registry = er.async_get(self.hass)
        
        for entity_id, entity_entry in entity_registry.entities.items():
            if (entity_entry.config_entry_id == self.config_entry.entry_id and
                "new_device_input" in entity_entry.unique_id):
                entity = self.hass.states.get(entity_id)
                if entity:
                    new_device_input = entity
                break
        
        if not new_device_input:
            _LOGGER.warning("Поле ввода нового устройства не найдено")
            return
        
        device_name = new_device_input.state.strip() if new_device_input.state else ""
        
        _LOGGER.debug("Добавление устройства: '%s'", device_name)
        
        if not device_name:
            _LOGGER.warning("Невозможно добавить устройство: пустое имя")
            return
        
        await self.hass.services.async_call(
            DOMAIN,
            "add_device",
            {
                "name": device_name
            },
            blocking=True
        )
        
        await self.coordinator.async_refresh()


class IRRemoteDeviceButton(ButtonEntity):
    """Кнопка для управления ИК-устройством."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_name: str,
        command_name: str,
        command_data: dict,
    ) -> None:
        """Инициализация кнопки устройства."""
        self.hass = hass
        self.config_entry = config_entry
        self.device_name = device_name
        self.command_name = command_name
        self.command_data = command_data
        self._attr_unique_id = f"ir_remote_{device_name}_{command_name}"
        self._attr_name = command_data.get("name", f"{device_name} {command_name}")
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        
        # Устанавливаем device_info для управляемых устройств
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"controlled_{self.device_name}")},
            name=self.device_name.title(),
            manufacturer="IR Controlled Device",
            model="Virtual Device",
            via_device=(DOMAIN, self.config_entry.entry_id),
        )
        
        _LOGGER.info("Created device button: device=%s, command=%s", device_name, command_name)

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Device button pressed: %s - %s", self.device_name, self.command_name)
        
        await self.hass.services.async_call(
            DOMAIN,
            "send_code",
            {
                ATTR_CODE: self.command_data["code"]
            },
            blocking=True
        )
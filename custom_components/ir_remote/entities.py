"""IR Remote entities for Home Assistant - исправленная версия."""
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
        
        _LOGGER.debug("Created entity: unique_id=%s, name=%s", self._attr_unique_id, name)
    
    @property
    def available(self) -> bool:
        """Проверка доступности сущности."""
        # Сущность доступна, если координатор последний раз успешно обновился
        # или если это первый запуск и данные загружаются
        if not self.coordinator.last_update_success:
            _LOGGER.debug("Entity %s unavailable: coordinator last update failed", self._attr_unique_id)
            return False
        
        # Проверяем, что данные координатора инициализированы
        if self.coordinator.data is None:
            _LOGGER.debug("Entity %s unavailable: coordinator data is None", self._attr_unique_id)
            return False
            
        return True


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
        
        # Инициализируем с базовыми опциями
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        
        # Обновляем опции из координатора, если данные доступны
        self._update_options_from_coordinator()
        
        _LOGGER.debug("Created device selector: type=%s, unique_id=%s, initial_options=%s", 
                    device_type, self._attr_unique_id, self._attr_options)

    def _update_options_from_coordinator(self) -> None:
        """Обновление опций из данных координатора."""
        if (self.coordinator.data and 
            isinstance(self.coordinator.data, dict) and 
            "devices" in self.coordinator.data):
            
            devices = self.coordinator.data["devices"]
            if isinstance(devices, list) and devices:
                self._attr_options = devices
                # Проверяем, что текущая опция все еще доступна
                if self._attr_current_option not in devices:
                    self._attr_current_option = "none"
                _LOGGER.debug("Updated device selector options: %s", devices)
            else:
                _LOGGER.debug("No valid devices in coordinator data")
        else:
            _LOGGER.debug("No coordinator data available for device selector")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        _LOGGER.debug("Device selector %s handling coordinator update", self._attr_unique_id)
        self._update_options_from_coordinator()
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        if option not in self._attr_options:
            _LOGGER.warning("Invalid option %s not in %s", option, self._attr_options)
            return
            
        self._attr_current_option = option
        self.async_write_ha_state()
        
        _LOGGER.debug("Device selector option changed to: %s", option)
        
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
                if entity and hasattr(entity, 'async_update_commands'):
                    await entity.async_update_commands(option)
                    _LOGGER.debug("Updated commands for device: %s", option)


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
        
        _LOGGER.debug("Created command selector: unique_id=%s", self._attr_unique_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        if (self._device != "none" and 
            self.coordinator.data and 
            isinstance(self.coordinator.data, dict) and
            "commands" in self.coordinator.data):
            
            commands_data = self.coordinator.data["commands"]
            if isinstance(commands_data, dict):
                commands = commands_data.get(self._device, ["none"])
                if isinstance(commands, list):
                    self._attr_options = commands
                    
                    if self._attr_current_option not in commands:
                        self._attr_current_option = "none"
                    
                    _LOGGER.debug("Command selector updated for device %s with commands: %s", 
                                self._device, commands)
                    self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        if option not in self._attr_options:
            _LOGGER.warning("Invalid command option %s not in %s", option, self._attr_options)
            return
            
        self._attr_current_option = option
        self.async_write_ha_state()
        
        _LOGGER.debug("Command selector option changed to: %s", option)
        
    async def async_update_commands(self, device: str) -> None:
        """Обновление списка команд для выбранного устройства."""
        self._device = device
        
        if (device == "none" or 
            not self.coordinator.data or 
            not isinstance(self.coordinator.data, dict) or
            "commands" not in self.coordinator.data):
            self._attr_options = ["none"]
            _LOGGER.debug("Command selector cleared for device: %s", device)
        else:
            commands_data = self.coordinator.data["commands"]
            if isinstance(commands_data, dict):
                commands = commands_data.get(device, ["none"])
                if isinstance(commands, list):
                    self._attr_options = commands
                    _LOGGER.debug("Command selector updated for device %s: %s", device, commands)
                else:
                    self._attr_options = ["none"]
            else:
                self._attr_options = ["none"]
        
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
        
        _LOGGER.debug("Created button input: unique_id=%s", self._attr_unique_id)

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
        
        _LOGGER.debug("Created new device input: unique_id=%s", self._attr_unique_id)

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
        
        _LOGGER.debug("Created learn button: unique_id=%s", self._attr_unique_id)

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
            self.hass.components.persistent_notification.create(
                "Ошибка: не найдены необходимые элементы интерфейса",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        device = device_selector.state if device_selector else "none"
        button = button_input.state if button_input else ""
        
        _LOGGER.debug("Обучение: устройство=%s, кнопка=%s", device, button)
        
        if device == "none" or not button:
            _LOGGER.warning("Невозможно начать обучение: device=%s, button=%s", device, button)
            self.hass.components.persistent_notification.create(
                "Ошибка: выберите устройство и введите название кнопки",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "learn_code",
                {
                    ATTR_DEVICE: device,
                    ATTR_BUTTON: button,
                },
                blocking=True
            )
        except Exception as e:
            _LOGGER.error("Ошибка при вызове сервиса обучения: %s", e)
            self.hass.components.persistent_notification.create(
                f"Ошибка при обучении: {e}",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
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
        
        _LOGGER.debug("Created send button: unique_id=%s", self._attr_unique_id)

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
            self.hass.components.persistent_notification.create(
                "Ошибка: не найдены необходимые элементы интерфейса",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        device = device_selector.state if device_selector else "none"
        command = command_selector.state if command_selector else "none"
        
        _LOGGER.debug("Отправка команды: устройство=%s, команда=%s", device, command)
        
        if device == "none" or command == "none":
            _LOGGER.warning("Невозможно отправить команду: device=%s, command=%s", device, command)
            self.hass.components.persistent_notification.create(
                "Ошибка: выберите устройство и команду",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "send_command",
                {
                    ATTR_DEVICE: device,
                    "command": command,
                },
                blocking=True
            )
        except Exception as e:
            _LOGGER.error("Ошибка при отправке команды: %s", e)
            self.hass.components.persistent_notification.create(
                f"Ошибка при отправке команды: {e}",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
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
        
        _LOGGER.debug("Created add device button: unique_id=%s", self._attr_unique_id)

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
            self.hass.components.persistent_notification.create(
                "Ошибка: не найдено поле ввода нового устройства",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        device_name = new_device_input.state.strip() if new_device_input.state else ""
        
        _LOGGER.debug("Добавление устройства: '%s'", device_name)
        
        if not device_name:
            _LOGGER.warning("Невозможно добавить устройство: пустое имя")
            self.hass.components.persistent_notification.create(
                "Ошибка: введите название устройства",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )
            return
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "add_device",
                {
                    "name": device_name
                },
                blocking=True
            )
            
            await self.coordinator.async_refresh()
        except Exception as e:
            _LOGGER.error("Ошибка при добавлении устройства: %s", e)
            self.hass.components.persistent_notification.create(
                f"Ошибка при добавлении устройства: {e}",
                "IR Remote: Ошибка",
                f"{DOMAIN}_error"
            )


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
        
        _LOGGER.debug("Created device button: device=%s, command=%s", device_name, command_name)

    @property
    def available(self) -> bool:
        """Кнопки устройств всегда доступны."""
        return True

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Device button pressed: %s - %s", self.device_name, self.command_name)
        
        code = self.command_data.get("code")
        if not code:
            _LOGGER.error("No IR code found for %s - %s", self.device_name, self.command_name)
            return
        
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "send_code",
                {
                    ATTR_CODE: code
                },
                blocking=True
            )
        except Exception as e:
            _LOGGER.error("Ошибка при отправке ИК-кода: %s", e)
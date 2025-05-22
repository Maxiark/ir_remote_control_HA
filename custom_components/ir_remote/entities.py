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


class IRRemoteEntityBase:
    """Базовый класс для всех сущностей IR Remote."""
    
    def __init__(self, config_entry: ConfigEntry):
        """Инициализация базового класса."""
        self.config_entry = config_entry
    
    @property
    def device_info(self) -> DeviceInfo:
        """Информация об устройстве пульта на основе ZHA данных."""
        ieee = self.config_entry.data.get(CONF_IEEE)
        
        return DeviceInfo(
            identifiers={(DOMAIN, ieee)},  # Используем IEEE адрес как идентификатор
            name="ИК-пульт",
            manufacturer="Zigbee",
            model="IR Remote Controller", 
            via_device=("zha", ieee),  # Связываем с ZHA устройством
            configuration_url=None,
        )


class IRRemoteCoordinatorEntity(CoordinatorEntity, IRRemoteEntityBase):
    """Базовый класс для сущностей IR Remote с координатором."""
    
    def __init__(
        self, 
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Инициализация сущности."""
        CoordinatorEntity.__init__(self, coordinator)
        IRRemoteEntityBase.__init__(self, config_entry)
        
        ieee = config_entry.data.get(CONF_IEEE)
        self._attr_unique_id = f"ir_remote_{ieee}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_has_entity_name = True
        self._attr_entity_category = None  # Видимо в основном интерфейсе
        self._attr_should_poll = False


# Остальные классы остаются без изменений, но теперь наследуют правильный device_info

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
        self.device_type = device_type  # "send" или "learn"
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        self._attr_translation_key = f"{device_type}_device"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        if self.coordinator.data:
            devices = self.coordinator.data.get("devices", ["none"])
            self._attr_options = devices
            
            # Сбрасываем текущую опцию, если она не в списке
            if self._attr_current_option not in devices:
                self._attr_current_option = "none"
                
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
        # Если это селектор отправки, обновляем список команд
        if self.device_type == "send":
            # Вызываем сервис обновления команд
            await self.hass.services.async_call(
                DOMAIN,
                "update_commands",
                {ATTR_DEVICE: option},
                blocking=True
            )


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
        self._attr_options = ["none"]
        self._attr_current_option = "none"
        self._attr_translation_key = "send_command"
        self._device = "none"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления данных координатора."""
        if self._device != "none" and self.coordinator.data:
            commands = self.coordinator.data.get("commands", {}).get(self._device, ["none"])
            self._attr_options = commands
            
            # Сбрасываем текущую опцию, если она не в списке
            if self._attr_current_option not in commands:
                self._attr_current_option = "none"
                
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Выбор опции в селекторе."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
    async def async_update_commands(self, device: str) -> None:
        """Обновление списка команд для выбранного устройства."""
        self._device = device
        
        if device == "none" or not self.coordinator.data:
            self._attr_options = ["none"]
        else:
            self._attr_options = self.coordinator.data.get("commands", {}).get(device, ["none"])
        
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
        self._attr_mode = "text"  # Обязательный атрибут для TextEntity

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
        self._attr_mode = "text"  # Обязательный атрибут для TextEntity

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

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка обучения нажата")
        
        # Находим сущности селектора устройства и поля ввода кнопки
        device_selector = None
        button_input = None
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("select", {}).entities.items():
            if (isinstance(entity, IRRemoteDeviceSelector) and 
                entity.device_type == "learn" and 
                entity.unique_id.endswith("learn_device")):
                device_selector = entity
                break
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("text", {}).entities.items():
            if isinstance(entity, IRRemoteButtonInput):
                button_input = entity
                break
        
        if not device_selector or not button_input:
            _LOGGER.warning("Селектор устройства или поле ввода кнопки не найдены")
            return
        
        device = device_selector.current_option
        button = button_input.native_value
        
        _LOGGER.debug("Обучение: устройство=%s, кнопка=%s", device, button)
        
        if device == "none" or not button:
            _LOGGER.warning("Невозможно начать обучение: device=%s, button=%s", device, button)
            return
        
        # Вызываем сервис обучения
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

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка отправки команды нажата")
        
        # Находим сущности селектора устройства и селектора команды
        device_selector = None
        command_selector = None
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("select", {}).entities.items():
            if isinstance(entity, IRRemoteDeviceSelector) and entity.device_type == "send":
                device_selector = entity
            elif isinstance(entity, IRRemoteCommandSelector):
                command_selector = entity
            
            if device_selector and command_selector:
                break
        
        if not device_selector or not command_selector:
            _LOGGER.warning("Селектор устройства или селектор команды не найдены")
            return
        
        device = device_selector.current_option
        command = command_selector.current_option
        
        _LOGGER.debug("Отправка команды: устройство=%s, команда=%s", device, command)
        
        if device == "none" or command == "none":
            _LOGGER.warning("Невозможно отправить команду: device=%s, command=%s", device, command)
            return
        
        # Вызываем сервис отправки команды
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

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        _LOGGER.debug("Кнопка добавления устройства нажата")
        
        # Находим сущность поля ввода нового устройства
        new_device_input = None
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("text", {}).entities.items():
            if isinstance(entity, IRRemoteNewDeviceInput):
                new_device_input = entity
                break
        
        if not new_device_input:
            _LOGGER.warning("Поле ввода нового устройства не найдено")
            return
        
        device_name = new_device_input.native_value.strip()
        
        _LOGGER.debug("Добавление устройства: '%s'", device_name)
        
        if not device_name:
            _LOGGER.warning("Невозможно добавить устройство: пустое имя")
            return
        
        # Вызываем сервис добавления устройства
        await self.hass.services.async_call(
            DOMAIN,
            "add_device",
            {
                "name": device_name
            },
            blocking=True
        )
        
        # Очищаем поле ввода
        await new_device_input.async_set_value("")
        
        # Обновляем данные координатора
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

    @property
    def device_info(self) -> DeviceInfo:
        """Информация об управляемом устройстве (не пульте)."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"controlled_{self.device_name}")},
            name=self.device_name.title(),
            manufacturer="IR Controlled Device",
            model="Virtual Device",
            # Связываем с основным пультом
            via_device=(DOMAIN, self.config_entry.data.get(CONF_IEEE)),
        )

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        await self.hass.services.async_call(
            DOMAIN,
            "send_code",
            {
                ATTR_CODE: self.command_data["code"]
            },
            blocking=True
        )
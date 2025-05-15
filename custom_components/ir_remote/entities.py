"""IR Remote entities for Home Assistant."""
import logging
import subprocess
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
from homeassistant.helpers.entity_component import EntityComponent
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
    
    entities = [
        # UI Controls
        # Группа отправки команд (1)
        IRRemoteDeviceSelector(hass, config_entry, coordinator, "send", sort_order=10),
        IRRemoteCommandSelector(hass, config_entry, coordinator, sort_order=11),
        IRRemoteSendButton(hass, config_entry, coordinator, sort_order=12),
        
        # Группа обучения новым командам (2)
        IRRemoteDeviceSelector(hass, config_entry, coordinator, "learn", sort_order=20),
        IRRemoteButtonInput(hass, config_entry, coordinator, sort_order=21),
        IRRemoteLearnButton(hass, config_entry, coordinator, sort_order=22),
        
        # Группа добавления устройств (3)
        IRRemoteNewDeviceInput(hass, config_entry, coordinator, sort_order=30),
        IRRemoteAddDeviceButton(hass, config_entry, coordinator, sort_order=31),
    ]
    
    async_add_entities(entities)


async def _update_ir_data(hass: HomeAssistant) -> dict:
    """Update IR device and command data."""
    data = {
        "devices": ["none"],
        "commands": {},
        "codes": {}
    }
    
    scripts_dir = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts"
    manage_devices_path = scripts_dir / "manage_devices.py"
    device_commands_path = scripts_dir / "device_commands.py"
    
    # Get device list
    try:
        result = await hass.async_add_executor_job(
            lambda: subprocess.run(
                ["python3", str(manage_devices_path), "list"],
                capture_output=True,
                text=True,
                check=True,
            )
        )
        device_list = result.stdout.strip().split(',')
        if device_list and device_list[0] != "none" and device_list[0]:
            data["devices"] = ["none"] + device_list
        
        # For each device, get commands
        for device in data["devices"]:
            if device == "none":
                continue
                
            cmd_result = await hass.async_add_executor_job(
                lambda: subprocess.run(
                    ["python3", str(device_commands_path), device],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            )
            cmd_list = cmd_result.stdout.strip().split(',')
            data["commands"][device] = cmd_list
    
        # Get IR codes from JSON file
        ir_codes_path = scripts_dir / "ir_codes.json"
        if await hass.async_add_executor_job(lambda: ir_codes_path.exists()):
            async with aiofiles.open(ir_codes_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                codes = json.loads(content)
                data["codes"] = codes
    except Exception as e:
        _LOGGER.error("Error updating IR data: %s", e)
    
    return data


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
            identifiers={(DOMAIN, "ir_remote_controller")},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        if self.coordinator.data:
            self._attr_options = self.coordinator.data.get("devices", ["none"])
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        self._attr_current_option = option
        self.async_write_ha_state()
        
        # If in send mode, update command selector when device changes
        if self.mode == "send":
            # Find and update the command selector
            for entity_id, entity in self.hass.data.get("entity_components", {}).get("select", {}).entities.items():
                if isinstance(entity, IRRemoteCommandSelector):
                    await entity.async_update_commands(option)


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
            identifiers={(DOMAIN, "ir_remote_controller")},
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "ir_remote_controller")},
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "ir_remote_controller")},
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
            identifiers={(DOMAIN, "ir_remote_controller")},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        # Find device selector and button input
        device = "none"
        button = ""
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("select", {}).entities.items():
            if isinstance(entity, IRRemoteDeviceSelector) and entity.mode == "learn":
                device = entity.current_option
                break
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("text", {}).entities.items():
            if isinstance(entity, IRRemoteButtonInput):
                button = entity.native_value
                break
        
        if device == "none" or not button:
            _LOGGER.warning("Cannot learn: device=%s, button=%s", device, button)
            return
        
        # Call learn service
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
            identifiers={(DOMAIN, "ir_remote_controller")},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        # Find device and command selectors
        device = "none"
        command = "none"
        code = None
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("select", {}).entities.items():
            if isinstance(entity, IRRemoteDeviceSelector) and entity.mode == "send":
                device = entity.current_option
            elif isinstance(entity, IRRemoteCommandSelector):
                command = entity.current_option
        
        if device == "none" or command == "none" or not self.coordinator.data:
            _LOGGER.warning("Cannot send: device=%s, command=%s", device, command)
            return
        
        # Get IR code from data
        codes = self.coordinator.data.get("codes", {})
        if device in codes and command in codes[device]:
            code = codes[device][command].get("code")
        
        if not code:
            _LOGGER.warning("IR code not found for %s - %s", device, command)
            return
        
        # Call send service
        await self.hass.services.async_call(
            DOMAIN,
            "send_code",
            {
                ATTR_CODE: code,
            },
        )


class IRRemoteAddDeviceButton(CoordinatorEntity, ButtonEntity):
    """Button entity to add new IR device."""

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
        self._attr_unique_id = f"ir_remote_03_{sort_order:02d}_add_device_button"
        self._attr_name = "Добавить устройство"
        self._attr_has_entity_name = True
        self._attr_translation_key = "add_device_button"
        self._attr_entity_category = None  # Делаем видимым в основном интерфейсе

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "ir_remote_controller")},
            name="ИК-пульт",
            manufacturer="Home Assistant",
            model="IR Remote Controller",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        # Find new device input
        device_name = ""
        
        for entity_id, entity in self.hass.data.get("entity_components", {}).get("text", {}).entities.items():
            if isinstance(entity, IRRemoteNewDeviceInput):
                device_name = entity.native_value
                break
        
        if not device_name:
            _LOGGER.warning("Cannot add device: empty name")
            return
        
        # Run script to add device
        scripts_dir = Path(self.hass.config.path()) / "custom_components" / DOMAIN / "scripts"
        manage_devices_path = scripts_dir / "manage_devices.py"
        
        try:
            await self.hass.async_add_executor_job(
                lambda: subprocess.run(
                    ["python3", str(manage_devices_path), "add", device_name],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            )
            
            # Clear input field
            for entity_id, entity in self.hass.data.get("entity_components", {}).get("text", {}).entities.items():
                if isinstance(entity, IRRemoteNewDeviceInput):
                    await entity.async_set_value("")
            
            # Update coordinator data
            await self.coordinator.async_refresh()
            
        except subprocess.CalledProcessError as e:
            _LOGGER.error("Failed to add device: %s", e.stderr)
        except Exception as e:
            _LOGGER.error("Error adding device: %s", e)
"""Button platform for IR Remote integration."""
import logging
import json
from pathlib import Path

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_IEEE,
    CONF_ENDPOINT,
    CONF_CLUSTER,
    DEFAULT_CLUSTER_TYPE,
    DEFAULT_COMMAND_TYPE,
    ZHA_COMMAND_SEND,
)
from .entities import (
    IRRemoteLearnButton,
    IRRemoteSendButton,
    IRRemoteAddDeviceButton,
    _update_ir_data,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote buttons."""
    _LOGGER.debug("Setting up IR Remote buttons")

    # Create data coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="ir_remote_data",
        update_method=lambda: _update_ir_data(hass),
        update_interval=None,  # Manual updates only
    )
    
    # Initial data fetch
    await coordinator.async_refresh()
    
    # Create UI control buttons
    ui_buttons = [
        IRRemoteSendButton(hass, config_entry, coordinator, sort_order=12),
        IRRemoteLearnButton(hass, config_entry, coordinator, sort_order=22),
        IRRemoteAddDeviceButton(hass, config_entry, coordinator, sort_order=31),
    ]
    
    # Create device command buttons from saved codes
    device_buttons = []
    try:
        config_path = Path(__file__).parent / "scripts" / "ir_codes.json"
        if await hass.async_add_executor_job(lambda: config_path.exists()):
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                devices = json.loads(content)
                
                for device_name, commands in devices.items():
                    for command_name, command_data in commands.items():
                        device_buttons.append(
                            IRRemoteDeviceButton(
                                hass,
                                config_entry,
                                device_name,
                                command_name,
                                command_data,
                            )
                        )
    except Exception as e:
        _LOGGER.error("Error creating device buttons: %s", e)
    
    # Add all buttons
    async_add_entities(ui_buttons + device_buttons)


class IRRemoteDeviceButton(ButtonEntity):
    """Representation of an IR Remote device command button."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_name: str,
        command_name: str,
        command_data: dict,
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self.config_entry = config_entry
        self.device_name = device_name
        self.command_name = command_name
        self.command_data = command_data
        self._attr_unique_id = f"ir_remote_{device_name}_{command_name}"
        self._attr_name = command_data.get("name", f"{device_name} {command_name}")
        self._attr_has_entity_name = True

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
        """Handle the button press."""
        await self.hass.services.async_call(
            "zha",
            "issue_zigbee_cluster_command",
            {
                "ieee": self.config_entry.data[CONF_IEEE],
                "endpoint_id": self.config_entry.data[CONF_ENDPOINT],
                "cluster_id": self.config_entry.data[CONF_CLUSTER],
                "cluster_type": DEFAULT_CLUSTER_TYPE,
                "command": ZHA_COMMAND_SEND,
                "command_type": DEFAULT_COMMAND_TYPE,
                "params": {"code": self.command_data["code"]}
            },
        )
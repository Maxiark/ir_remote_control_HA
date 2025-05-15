"""Select platform for IR Remote integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .entities import IRRemoteDeviceSelector, IRRemoteCommandSelector, _update_ir_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote select entities."""
    _LOGGER.debug("Setting up IR Remote select entities")

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
        IRRemoteDeviceSelector(hass, config_entry, coordinator, "send", sort_order=10),
        IRRemoteCommandSelector(hass, config_entry, coordinator, sort_order=11),
        IRRemoteDeviceSelector(hass, config_entry, coordinator, "learn", sort_order=20),
    ]
    
    async_add_entities(entities)
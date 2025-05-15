"""Text platform for IR Remote integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .entities import IRRemoteButtonInput, IRRemoteNewDeviceInput, _update_ir_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote text entities."""
    _LOGGER.debug("Setting up IR Remote text entities")

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
        IRRemoteButtonInput(hass, config_entry, coordinator, sort_order=21),
        IRRemoteNewDeviceInput(hass, config_entry, coordinator, sort_order=30),
    ]
    
    async_add_entities(entities)
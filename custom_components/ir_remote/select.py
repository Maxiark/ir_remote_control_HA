"""Select platform for IR Remote integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entities import async_setup_entry as async_setup_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Remote select entities."""
    _LOGGER.debug("Select platform forwarding to entities.py setup")
    # Перенаправление на основную функцию создания сущностей
    return
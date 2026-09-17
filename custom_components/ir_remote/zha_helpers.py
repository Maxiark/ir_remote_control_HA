"""Helpers for talking to the ZHA / zigpy device directly."""
import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

LEARNED_CODE_ATTR_ID = 0


def _get_gateway(hass: HomeAssistant) -> Optional[Any]:
    """Return ZHA gateway object or None."""
    try:
        from homeassistant.components.zha.helpers import get_zha_gateway

        return get_zha_gateway(hass)
    except Exception as e:
        _LOGGER.debug("get_zha_gateway path failed: %s", e)

    try:
        zha_data = hass.data.get("zha")
        return getattr(zha_data, "gateway", None) or (
            zha_data.get("zha_gateway") if isinstance(zha_data, dict) else None
        )
    except Exception as e:
        _LOGGER.debug("Legacy zha gateway path failed: %s", e)

    return None


def _get_zigpy_device(hass: HomeAssistant, ieee: str) -> Optional[Any]:
    """Return zigpy device for given IEEE address or None."""
    from zigpy.types import EUI64

    gateway = _get_gateway(hass)
    if gateway is None:
        return None

    ieee_obj = EUI64.convert(ieee)
    zha_device = None
    try:
        zha_device = gateway.get_device(ieee_obj)
    except Exception:
        zha_device = getattr(gateway, "devices", {}).get(ieee_obj)

    return getattr(zha_device, "device", None) if zha_device is not None else None


def get_zha_devices(hass: HomeAssistant) -> dict[str, str]:
    """Return mapping ieee -> display name for all ZHA devices (except coordinator)."""
    gateway = _get_gateway(hass)
    if gateway is None:
        _LOGGER.error("ZHA gateway not available")
        return {}

    devices: dict[str, str] = {}
    for zha_device in getattr(gateway, "devices", {}).values():
        if getattr(zha_device, "is_coordinator", False):
            continue
        ieee = str(zha_device.ieee)
        device_name = (
            getattr(zha_device, "name", None)
            or getattr(zha_device, "model", None)
            or "Unknown Device"
        )
        manufacturer = getattr(zha_device, "manufacturer", "") or ""
        devices[ieee] = (
            f"{device_name} ({manufacturer}) - {ieee}" if manufacturer else f"{device_name} - {ieee}"
        )
    return devices


async def async_read_learned_ir_code(
    hass: HomeAssistant, ieee: str, endpoint_id: int, cluster_id: int
) -> Optional[str]:
    """Read last learned IR code from the TS1201 quirk.

    The quirk keeps the learned code in ``device.last_learned_ir_code`` and
    exposes it through an overridden ``read_attributes``. It is NOT stored in
    the attribute cache and a raw over-the-air read returns garbage, so we read
    it in-process from the zigpy device.
    """
    zigpy_dev = _get_zigpy_device(hass, ieee)
    if zigpy_dev is None:
        _LOGGER.error("ZHA device %s not found", ieee)
        return None

    code = getattr(zigpy_dev, "last_learned_ir_code", None)
    if code:
        _LOGGER.debug("Read learned IR code from device attribute (len=%d)", len(str(code)))
        return str(code)

    try:
        endpoint = zigpy_dev.endpoints[endpoint_id]
        cluster = endpoint.in_clusters[cluster_id]
        result = await cluster.read_attributes([LEARNED_CODE_ATTR_ID])
        if isinstance(result, (list, tuple)) and result and isinstance(result[0], dict):
            code = result[0].get(LEARNED_CODE_ATTR_ID)
            if code:
                _LOGGER.debug("Read learned IR code via cluster.read_attributes (len=%d)", len(str(code)))
                return str(code)
    except Exception as e:
        _LOGGER.debug("cluster.read_attributes fallback failed: %s", e)

    return None

"""IR Remote data management using Storage API."""
import logging
import re
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    STORAGE_VERSION,
    STORAGE_KEY,
    MAX_NAME_LENGTH,
    ALLOWED_NAME_PATTERN,
)

_LOGGER = logging.getLogger(__name__)

# Storage lock to prevent concurrent access
_storage_lock = asyncio.Lock()


class IRRemoteStorage:
    """Class for managing IR Remote data through Storage API."""
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the storage manager."""
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: Dict[str, Any] = {}
        self._loaded = False
        
        # Old data file path for migration
        self._old_data_file = (
            Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts" / "ir_codes.json"
        )
        
        _LOGGER.debug("IR Remote Storage initialized with key: %s", STORAGE_KEY)
    
    async def async_load(self) -> Dict[str, Any]:
        """Load data from Storage API."""
        if self._loaded:
            return self._data
        
        async with _storage_lock:
            try:
                # First attempt migration from old format
                await self._migrate_old_data()
                
                # Load from Storage API
                stored_data = await self.store.async_load()
                
                if stored_data is None:
                    _LOGGER.info("No existing IR data, initializing empty storage")
                    self._data = {"controllers": {}}
                    await self.async_save()
                else:
                    self._data = stored_data
                    _LOGGER.info("IR data loaded: %d controllers", len(self._data.get("controllers", {})))
                
                self._loaded = True
                
            except Exception as e:
                _LOGGER.error("Error loading IR data: %s", e, exc_info=True)
                self._data = {"controllers": {}}
                self._loaded = True
        
        return self._data
    
    async def async_save(self) -> bool:
        """Save data to Storage API."""
        async with _storage_lock:
            try:
                await self.store.async_save(self._data)
                _LOGGER.debug("IR data saved successfully")
                return True
            except Exception as e:
                _LOGGER.error("Error saving IR data: %s", e, exc_info=True)
                return False
    
    async def _migrate_old_data(self) -> None:
        """Migrate data from old ir_codes.json format."""
        try:
            old_exists = await self.hass.async_add_executor_job(
                lambda: self._old_data_file.exists()
            )
            
            if not old_exists:
                return
            
            # Check if we already have data in Storage
            existing_data = await self.store.async_load()
            if existing_data:
                return  # Migration already done
            
            _LOGGER.info("Migrating old IR codes data")
            
            import json
            import aiofiles
            
            # Read old file
            async with aiofiles.open(self._old_data_file, 'r', encoding='utf-8') as f:
                old_content = await f.read()
            
            old_data = json.loads(old_content)
            
            # Convert to new format
            migrated_data = {
                "controllers": {
                    "migrated_controller": {
                        "ieee": "migrated",
                        "name": "Мигрированный ИК-пульт",
                        "endpoint_id": 1,
                        "cluster_id": 57348,
                        "devices": {}
                    }
                }
            }
            
            # Convert old devices to new format
            for device_name, commands in old_data.items():
                migrated_data["controllers"]["migrated_controller"]["devices"][device_name] = {
                    "name": device_name.title(),
                    "commands": commands
                }
            
            # Save migrated data
            self._data = migrated_data
            await self.store.async_save(self._data)
            
            # Create backup of old file
            backup_path = self._old_data_file.with_suffix('.backup')
            await self.hass.async_add_executor_job(
                lambda: self._old_data_file.rename(backup_path)
            )
            
            _LOGGER.info("Migration completed, backup saved: %s", backup_path)
            
        except Exception as e:
            _LOGGER.warning("Migration failed, continuing with empty data: %s", e)
    
    def _validate_name(self, name: str) -> bool:
        """Validate name according to rules."""
        if not name or len(name) > MAX_NAME_LENGTH:
            return False
        
        return bool(re.match(ALLOWED_NAME_PATTERN, name))
    
    async def async_add_controller(
        self, 
        controller_id: str, 
        ieee: str, 
        room_name: str,
        endpoint_id: int = 1,
        cluster_id: int = 57348
    ) -> bool:
        """Add new IR controller."""
        if not self._validate_name(room_name):
            _LOGGER.warning("Invalid room name: %s", room_name)
            return False
        
        await self.async_load()
        
        if "controllers" not in self._data:
            self._data["controllers"] = {}
        
        if controller_id in self._data["controllers"]:
            _LOGGER.warning("Controller %s already exists", controller_id)
            return False
        
        self._data["controllers"][controller_id] = {
            "ieee": ieee,
            "name": f"ИК-пульт в {room_name}",
            "room_name": room_name,
            "endpoint_id": endpoint_id,
            "cluster_id": cluster_id,
            "devices": {}
        }
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Added new controller: %s (%s)", room_name, ieee)
        
        return success
    
    async def async_remove_controller(self, controller_id: str) -> bool:
        """Remove IR controller and all its devices."""
        await self.async_load()
        
        if controller_id not in self._data.get("controllers", {}):
            _LOGGER.warning("Controller %s not found", controller_id)
            return False
        
        controller_name = self._data["controllers"][controller_id].get("name", controller_id)
        del self._data["controllers"][controller_id]
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Removed controller: %s", controller_name)
        
        return success
    
    async def async_add_device(self, controller_id: str, device_id: str, device_name: str) -> bool:
        """Add virtual device to controller."""
        if not self._validate_name(device_name):
            _LOGGER.warning("Invalid device name: %s", device_name)
            return False
        
        await self.async_load()
        
        if controller_id not in self._data.get("controllers", {}):
            _LOGGER.warning("Controller %s not found", controller_id)
            return False
        
        if device_id in self._data["controllers"][controller_id]["devices"]:
            _LOGGER.warning("Device %s already exists in controller %s", device_id, controller_id)
            return False
        
        self._data["controllers"][controller_id]["devices"][device_id] = {
            "name": device_name,
            "commands": {}
        }
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Added device %s to controller %s", device_name, controller_id)
        
        return success
    
    async def async_remove_device(self, controller_id: str, device_id: str) -> bool:
        """Remove virtual device from controller."""
        await self.async_load()
        
        if (controller_id not in self._data.get("controllers", {}) or
            device_id not in self._data["controllers"][controller_id]["devices"]):
            _LOGGER.warning("Device %s not found in controller %s", device_id, controller_id)
            return False
        
        device_name = self._data["controllers"][controller_id]["devices"][device_id].get("name", device_id)
        del self._data["controllers"][controller_id]["devices"][device_id]
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Removed device %s from controller %s", device_name, controller_id)
        
        return success
    
    async def async_add_command(
        self, 
        controller_id: str, 
        device_id: str, 
        command_id: str, 
        command_name: str,
        ir_code: str
    ) -> bool:
        """Add command to device."""
        if not self._validate_name(command_name) or not ir_code:
            _LOGGER.warning("Invalid command data: name=%s, code_len=%d", 
                          command_name, len(ir_code) if ir_code else 0)
            return False
        
        await self.async_load()
        
        if (controller_id not in self._data.get("controllers", {}) or
            device_id not in self._data["controllers"][controller_id]["devices"]):
            _LOGGER.warning("Device %s not found in controller %s", device_id, controller_id)
            return False
        
        device = self._data["controllers"][controller_id]["devices"][device_id]
        
        # Overwrite if command already exists
        if command_id in device["commands"]:
            _LOGGER.info("Overwriting existing command %s for device %s", command_id, device_id)
        
        device["commands"][command_id] = {
            "name": command_name,
            "code": ir_code,
            "description": f"IR command {command_name} for {device.get('name', device_id)}"
        }
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Added command %s to device %s", command_name, device_id)
        
        return success
    
    async def async_remove_command(self, controller_id: str, device_id: str, command_id: str) -> bool:
        """Remove command from device."""
        await self.async_load()
        
        if (controller_id not in self._data.get("controllers", {}) or
            device_id not in self._data["controllers"][controller_id]["devices"] or
            command_id not in self._data["controllers"][controller_id]["devices"][device_id]["commands"]):
            _LOGGER.warning("Command %s not found", command_id)
            return False
        
        command_name = self._data["controllers"][controller_id]["devices"][device_id]["commands"][command_id].get("name", command_id)
        del self._data["controllers"][controller_id]["devices"][device_id]["commands"][command_id]
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Removed command %s from device %s", command_name, device_id)
        
        return success
    
    def get_controllers(self) -> List[Dict[str, Any]]:
        """Get list of all controllers."""
        if not self._loaded:
            return []
        
        controllers = []
        for controller_id, controller_data in self._data.get("controllers", {}).items():
            controllers.append({
                "id": controller_id,
                "name": controller_data.get("name", "Unknown Controller"),
                "ieee": controller_data.get("ieee"),
                "room_name": controller_data.get("room_name"),
                "device_count": len(controller_data.get("devices", {}))
            })
        
        return controllers
    
    def get_controller(self, controller_id: str) -> Optional[Dict[str, Any]]:
        """Get controller data."""
        if not self._loaded:
            return None
        
        return self._data.get("controllers", {}).get(controller_id)
    
    def get_devices(self, controller_id: str) -> List[Dict[str, Any]]:
        """Get list of devices for controller."""
        controller = self.get_controller(controller_id)
        if not controller:
            return []
        
        devices = []
        for device_id, device_data in controller.get("devices", {}).items():
            devices.append({
                "id": device_id,
                "name": device_data.get("name", "Unknown Device"),
                "command_count": len(device_data.get("commands", {}))
            })
        
        return devices
    
    def get_device(self, controller_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        """Get device data."""
        controller = self.get_controller(controller_id)
        if not controller:
            return None
        
        return controller.get("devices", {}).get(device_id)
    
    def get_commands(self, controller_id: str, device_id: str) -> List[Dict[str, Any]]:
        """Get list of commands for device."""
        device = self.get_device(controller_id, device_id)
        if not device:
            return []
        
        commands = []
        for command_id, command_data in device.get("commands", {}).items():
            commands.append({
                "id": command_id,
                "name": command_data.get("name", "Unknown Command"),
                "code": command_data.get("code", "")
            })
        
        return commands
    
    def get_command_code(self, controller_id: str, device_id: str, command_id: str) -> Optional[str]:
        """Get IR code for specific command."""
        device = self.get_device(controller_id, device_id)
        if not device:
            return None
        
        command = device.get("commands", {}).get(command_id)
        return command.get("code") if command else None
    
    async def async_export_data(self) -> Dict[str, Any]:
        """Export all data."""
        await self.async_load()
        return self._data.copy()
    
    async def async_import_data(self, data: Dict[str, Any]) -> bool:
        """Import data (replaces existing)."""
        if not isinstance(data, dict) or "controllers" not in data:
            _LOGGER.error("Invalid import data format")
            return False
        
        # Backup current data
        backup = self._data.copy()
        
        try:
            self._data = data
            success = await self.async_save()
            
            if success:
                _LOGGER.info("Data imported successfully")
            else:
                # Restore backup on failure
                self._data = backup
                _LOGGER.error("Import failed, restored backup")
            
            return success
            
        except Exception as e:
            # Restore backup on error
            self._data = backup
            _LOGGER.error("Import error: %s", e)
            return False
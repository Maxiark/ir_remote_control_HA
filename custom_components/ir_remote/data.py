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
        
        try:
            _LOGGER.info("Storage: Starting data load...")
            
            # First attempt migration from old format
            _LOGGER.info("Storage: Checking for migration...")
            await self._migrate_old_data()
            _LOGGER.info("Storage: Migration check completed")
            
            # Load from Storage API
            _LOGGER.info("Storage: Loading from Store API...")
            stored_data = await self.store.async_load()
            _LOGGER.info("Storage: Store API load completed, data exists: %s", stored_data is not None)
            
            if stored_data is None:
                _LOGGER.info("Storage: No existing IR data, initializing empty storage")
                self._data = {"controllers": {}}
                _LOGGER.info("Storage: About to save initial empty data...")
                
                # Try to save, but don't fail if it doesn't work
                save_success = await self.async_save()
                if save_success:
                    _LOGGER.info("Storage: Initial save completed")
                else:
                    _LOGGER.warning("Storage: Initial save failed, continuing with memory-only storage")
            else:
                self._data = stored_data
                _LOGGER.info("Storage: IR data loaded: %d controllers", len(self._data.get("controllers", {})))
            
            self._loaded = True
            _LOGGER.info("Storage: Load process completed successfully")
            
        except Exception as e:
            _LOGGER.error("Storage: Error loading IR data: %s", e, exc_info=True)
            self._data = {"controllers": {}}
            self._loaded = True
        
        return self._data
    
    async def async_save(self) -> bool:
        """Save data to Storage API."""
        try:
            _LOGGER.info("Storage: Starting save operation...")
            
            # Add timeout to prevent infinite hanging
            import asyncio
            await asyncio.wait_for(
                self.store.async_save(self._data), 
                timeout=30.0  # 30 seconds timeout
            )
            
            _LOGGER.info("Storage: Save operation completed successfully")
            return True
        except asyncio.TimeoutError:
            _LOGGER.error("Storage: Save operation timed out after 30 seconds")
            return False
        except Exception as e:
            _LOGGER.error("Storage: Error saving IR data: %s", e, exc_info=True)
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
    
    async def async_add_device(self, controller_id: str, device_id: str, device_name: str, device_type: str = "universal") -> bool:
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
            "type": device_type,
            "commands": {}
        }
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Added device %s (%s) to controller %s", device_name, device_type, controller_id)
        
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
        if not self._validate_name(command_name):
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
                "type": device_data.get("type", "universal"),  # ДОБАВЛЕНО: возвращаем тип
                "command_count": len(device_data.get("commands", {}))
            })
        
        return devices
    
    def get_device(self, controller_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        """Get device data."""
        controller = self.get_controller(controller_id)
        if not controller:
            return None
        
        device_data = controller.get("devices", {}).get(device_id)
        if not device_data:
            return None
        
        # Возвращаем полные данные устройства включая тип
        return {
            "id": device_id,
            "name": device_data.get("name", "Unknown Device"),
            "type": device_data.get("type", "universal"),  # ДОБАВЛЕНО: возвращаем тип
            "commands": device_data.get("commands", {})
        }
    
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

    async def async_cleanup_orphaned_data(self, valid_controller_ids: set) -> bool:
        """Clean up orphaned controllers that don't have config entries."""
        await self.async_load()
        
        if "controllers" not in self._data:
            return True
        
        cleaned_count = 0
        controllers_to_remove = []
        
        for controller_id in self._data["controllers"]:
            if controller_id not in valid_controller_ids:
                controllers_to_remove.append(controller_id)
        
        for controller_id in controllers_to_remove:
            controller_name = self._data["controllers"][controller_id].get("name", controller_id)
            del self._data["controllers"][controller_id]
            cleaned_count += 1
            _LOGGER.info("Cleaned up orphaned controller: %s (%s)", controller_name, controller_id)
        
        if cleaned_count > 0:
            success = await self.async_save()
            if success:
                _LOGGER.info("Cleaned up %d orphaned controllers", cleaned_count)
            return success
        
        return True
    
    async def async_reset_all_data(self) -> bool:
        """Reset all data - use with caution!"""
        _LOGGER.warning("Resetting all IR Remote data!")
        
        self._data = {"controllers": {}}
        success = await self.async_save()
        
        if success:
            _LOGGER.info("All IR Remote data has been reset")
        
        return success

    async def async_copy_device(
        self,
        source_controller_id: str,
        source_device_id: str,
        target_controller_id: str,
        new_device_name: str,
        new_device_id: Optional[str] = None
    ) -> bool:
        """Copy entire device from one controller to another (or same controller)."""
        await self.async_load()
        
        # Validate source
        if (source_controller_id not in self._data.get("controllers", {}) or
            source_device_id not in self._data["controllers"][source_controller_id]["devices"]):
            _LOGGER.warning("Source device %s not found in controller %s", source_device_id, source_controller_id)
            return False
        
        # Validate target controller
        if target_controller_id not in self._data.get("controllers", {}):
            _LOGGER.warning("Target controller %s not found", target_controller_id)
            return False
        
        # Validate new device name
        if not self._validate_name(new_device_name):
            _LOGGER.warning("Invalid new device name: %s", new_device_name)
            return False
        
        # Generate new device ID if not provided
        if not new_device_id:
            base_device_id = new_device_name.lower().replace(" ", "_").replace("-", "_")
            new_device_id = base_device_id
            
            # Check for conflicts and add suffix if needed
            existing_devices = self._data["controllers"][target_controller_id]["devices"]
            counter = 1
            
            while new_device_id in existing_devices:
                counter += 1
                new_device_id = f"{base_device_id}_{counter}"
                _LOGGER.debug("Device ID conflict, trying: %s", new_device_id)
        
        # Final check if target device already exists (shouldn't happen with the logic above)
        if new_device_id in self._data["controllers"][target_controller_id]["devices"]:
            _LOGGER.error("Target device %s still exists in controller %s after ID generation", 
                         new_device_id, target_controller_id)
            return False
        
        # Get source device data
        source_device = self._data["controllers"][source_controller_id]["devices"][source_device_id].copy()
        
        # Update device name
        source_device["name"] = new_device_name
        
        # Copy device to target
        self._data["controllers"][target_controller_id]["devices"][new_device_id] = source_device
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Copied device from %s:%s to %s:%s (%s)", 
                        source_controller_id, source_device_id,
                        target_controller_id, new_device_id, new_device_name)
        
        return success
    
    async def async_copy_commands(
        self,
        source_controller_id: str,
        source_device_id: str,
        target_controller_id: str,
        target_device_id: str,
        command_ids: Optional[List[str]] = None
    ) -> bool:
        """Copy commands from one device to another."""
        await self.async_load()
        
        # Validate source
        if (source_controller_id not in self._data.get("controllers", {}) or
            source_device_id not in self._data["controllers"][source_controller_id]["devices"]):
            _LOGGER.warning("Source device %s not found in controller %s", source_device_id, source_controller_id)
            return False
        
        # Validate target
        if (target_controller_id not in self._data.get("controllers", {}) or
            target_device_id not in self._data["controllers"][target_controller_id]["devices"]):
            _LOGGER.warning("Target device %s not found in controller %s", target_device_id, target_controller_id)
            return False
        
        # Get source commands
        source_commands = self._data["controllers"][source_controller_id]["devices"][source_device_id]["commands"]
        
        # If no specific commands specified, copy all
        if command_ids is None:
            command_ids = list(source_commands.keys())
        
        # Validate that all specified commands exist
        for cmd_id in command_ids:
            if cmd_id not in source_commands:
                _LOGGER.warning("Source command %s not found", cmd_id)
                return False
        
        # Copy commands to target
        target_commands = self._data["controllers"][target_controller_id]["devices"][target_device_id]["commands"]
        copied_count = 0
        
        for cmd_id in command_ids:
            # Check if command already exists in target
            if cmd_id in target_commands:
                _LOGGER.info("Command %s already exists in target, overwriting", cmd_id)
            
            # Copy command
            target_commands[cmd_id] = source_commands[cmd_id].copy()
            copied_count += 1
        
        success = await self.async_save()
        if success:
            _LOGGER.info("Copied %d commands from %s:%s to %s:%s", 
                        copied_count,
                        source_controller_id, source_device_id,
                        target_controller_id, target_device_id)
        
        return success
    
    def get_all_controllers_with_devices(self) -> Dict[str, Dict[str, Any]]:
        """Get all controllers with their devices info for copy operations."""
        if not self._loaded:
            return {}
        
        result = {}
        for controller_id, controller_data in self._data.get("controllers", {}).items():
            devices = []
            for device_id, device_data in controller_data.get("devices", {}).items():
                devices.append({
                    "id": device_id,
                    "name": device_data.get("name", "Unknown Device"),
                    "type": device_data.get("type", "universal"),
                    "command_count": len(device_data.get("commands", {})),
                    "commands": list(device_data.get("commands", {}).keys())
                })
            
            result[controller_id] = {
                "name": controller_data.get("name", "Unknown Controller"),
                "devices": devices
            }
        
        return result
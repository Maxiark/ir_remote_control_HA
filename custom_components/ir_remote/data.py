"""IR Remote data handler."""
import logging
import json
import os
import asyncio
from pathlib import Path
import aiofiles

from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Блокировка для предотвращения одновременного доступа к файлу
file_lock = asyncio.Lock()

class IRRemoteData:
    """Класс для работы с данными ИК-пульта."""
    
    def __init__(self, hass: HomeAssistant):
        """Инициализация хранилища данных."""
        self.hass = hass
        self.data_file = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts" / "ir_codes.json"
        self._data = None
    
    async def async_load(self) -> dict:
        """Загрузка данных из файла."""
        if self._data is not None:
            return self._data
        
        async with file_lock:
            try:
                # Проверяем существование директории и создаем, если необходимо
                await self.hass.async_add_executor_job(
                    lambda: self.data_file.parent.mkdir(exist_ok=True)
                )
                
                if await self.hass.async_add_executor_job(lambda: self.data_file.exists()):
                    # Проверяем права доступа
                    if not await self.hass.async_add_executor_job(lambda: os.access(self.data_file, os.R_OK | os.W_OK)):
                        _LOGGER.error("Недостаточно прав для чтения/записи файла: %s", self.data_file)
                        self._data = {}
                        return self._data
                    
                    async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        self._data = json.loads(content)
                        _LOGGER.debug("Данные IR успешно загружены из %s", self.data_file)
                else:
                    _LOGGER.debug("Файл данных IR не найден, создаем новый: %s", self.data_file)
                    self._data = {}
                    # Создаем пустой файл
                    await self.async_save()
            except json.JSONDecodeError as e:
                _LOGGER.error("Ошибка чтения данных IR: %s", e)
                # Создаем резервную копию поврежденного файла
                if await self.hass.async_add_executor_job(lambda: self.data_file.exists()):
                    backup_path = self.data_file.with_suffix(f".json.backup.{int(asyncio.get_event_loop().time())}")
                    await self.hass.async_add_executor_job(
                        lambda: self.data_file.rename(backup_path)
                    )
                    _LOGGER.info("Создана резервная копия поврежденного файла: %s", backup_path)
                
                self._data = {}
                await self.async_save()
            except PermissionError as e:
                _LOGGER.error("Ошибка доступа к файлу: %s", e)
                self._data = {}
            except Exception as e:
                _LOGGER.error("Непредвиденная ошибка при загрузке данных: %s", e, exc_info=True)
                self._data = {}
        
        return self._data
    
    async def async_save(self) -> bool:
        """Сохранение данных в файл."""
        async with file_lock:
            try:
                # Убедимся, что директория существует
                await self.hass.async_add_executor_job(
                    lambda: self.data_file.parent.mkdir(exist_ok=True)
                )
                
                # Проверим права доступа к директории
                if not await self.hass.async_add_executor_job(lambda: os.access(self.data_file.parent, os.W_OK)):
                    _LOGGER.error("Недостаточно прав для записи в директорию: %s", self.data_file.parent)
                    return False
                
                # Сохраняем с форматированием
                async with aiofiles.open(self.data_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(self._data, indent=2, ensure_ascii=False, cls=JSONEncoder))
                
                _LOGGER.debug("Данные IR успешно сохранены в %s", self.data_file)
                return True
            except PermissionError as e:
                _LOGGER.error("Ошибка прав доступа при сохранении данных IR: %s", e)
                return False
            except Exception as e:
                _LOGGER.error("Ошибка сохранения данных IR: %s", e, exc_info=True)
                return False
    
    def get_devices(self) -> list:
        """Получить список устройств."""
        if not self._data:
            return []
        return sorted(list(self._data.keys()))
    
    def get_commands(self, device: str) -> list:
        """Получить список команд для устройства."""
        if not self._data or device not in self._data or device == "none":
            return []
        return sorted(list(self._data[device].keys()))
    
    def get_code(self, device: str, command: str) -> str:
        """Получить ИК-код для устройства и команды."""
        if not self._data or device not in self._data or command not in self._data[device]:
            return None
        return self._data[device][command].get("code")
    
    async def async_add_device(self, device: str) -> bool:
        """Добавить новое устройство."""
        if not device or device == "none":
            _LOGGER.warning("Невозможно добавить устройство с пустым именем")
            return False
        
        # Загружаем данные, если это первое обращение
        if self._data is None:
            await self.async_load()
        
        if device in self._data:
            _LOGGER.warning("Устройство %s уже существует", device)
            return False
        
        self._data[device] = {}
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Добавлено новое устройство: %s", device)
        
        return success
    
    async def async_add_command(self, device: str, command: str, code: str) -> bool:
        """Добавить новую команду для устройства."""
        if not device or not command or device == "none" or command == "none" or not code:
            _LOGGER.warning("Невозможно добавить команду: недостаточно данных")
            return False
        
        # Загружаем данные, если это первое обращение
        if self._data is None:
            await self.async_load()
        
        # Создаем устройство, если его нет
        if device not in self._data:
            self._data[device] = {}
        
        self._data[device][command] = {
            "code": code,
            "name": f"{device.upper()} {command.replace('_', ' ').title()}",
            "description": f"IR code for {device} {command}"
        }
        
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Добавлена новая команда %s для устройства %s", command, device)
        
        return success


async def update_ir_data(hass: HomeAssistant) -> dict:
    """Обновление данных ИК-пульта."""
    data = {
        "devices": ["none"],
        "commands": {},
        "codes": {}
    }
    
    # Получаем хранилище данных
    ir_data = hass.data[DOMAIN].get("data")
    if not ir_data:
        _LOGGER.error("Хранилище данных IR не инициализировано")
        return data
    
    # Загружаем данные
    await ir_data.async_load()
    
    # Получаем список устройств
    devices = ir_data.get_devices()
    if devices:
        data["devices"] = ["none"] + devices
        _LOGGER.debug("Устройства из ir_codes.json: %s", devices)
    
    # Получаем списки команд для каждого устройства
    for device in devices:
        commands = ir_data.get_commands(device)
        if commands:
            data["commands"][device] = ["none"] + commands
            _LOGGER.debug("Команды для %s: %s", device, commands)
    
    # Сохраняем все коды для удобства доступа
    data["codes"] = ir_data._data or {}
    
    return data


async def setup_ir_data_coordinator(hass: HomeAssistant) -> DataUpdateCoordinator:
    """Настройка координатора данных IR."""
    # Инициализация хранилища данных
    ir_data = IRRemoteData(hass)
    hass.data[DOMAIN]["data"] = ir_data
    
    # Инициализация координатора данных
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="ir_remote_data",
        update_method=lambda: update_ir_data(hass),
        update_interval=None,  # Только ручные обновления
    )
    
    # Первоначальная загрузка данных
    await coordinator.async_refresh()
    
    return coordinator
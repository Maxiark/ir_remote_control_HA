"""IR Remote data handler - исправленная версия."""
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


async def async_create_notification(hass: HomeAssistant, message: str, title: str, notification_id: str) -> None:
    """Создать уведомление пользователю."""
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": message,
                "title": title,
                "notification_id": notification_id
            }
        )
    except Exception as e:
        _LOGGER.debug("Could not create notification: %s", e)
        # Если не получается создать уведомление, просто логируем
        _LOGGER.info("Notification: %s - %s", title, message)


class IRRemoteData:
    """Класс для работы с данными ИК-пульта."""
    
    def __init__(self, hass: HomeAssistant):
        """Инициализация хранилища данных."""
        self.hass = hass
        self.data_file = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts" / "ir_codes.json"
        self._data = None
        self._loaded = False
    
    async def async_load(self) -> dict:
        """Загрузка данных из файла."""
        if self._loaded and self._data is not None:
            return self._data
        
        async with file_lock:
            try:
                # Проверяем существование директории и создаем, если необходимо
                await self.hass.async_add_executor_job(
                    lambda: self.data_file.parent.mkdir(parents=True, exist_ok=True)
                )
                
                if await self.hass.async_add_executor_job(lambda: self.data_file.exists()):
                    # Проверяем права доступа
                    if not await self.hass.async_add_executor_job(lambda: os.access(self.data_file, os.R_OK | os.W_OK)):
                        _LOGGER.error("Недостаточно прав для чтения/записи файла: %s", self.data_file)
                        self._data = {}
                        self._loaded = True
                        return self._data
                    
                    async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        if content.strip():  # Проверяем, что файл не пустой
                            self._data = json.loads(content)
                        else:
                            self._data = {}
                        _LOGGER.info("Данные IR успешно загружены из %s: %d устройств", 
                                   self.data_file, len(self._data))
                else:
                    _LOGGER.info("Файл данных IR не найден, создаем новый: %s", self.data_file)
                    self._data = {}
                    # Создаем пустой файл
                    await self.async_save()
                
                self._loaded = True
                
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
                self._loaded = True
                await self.async_save()
            except PermissionError as e:
                _LOGGER.error("Ошибка доступа к файлу: %s", e)
                self._data = {}
                self._loaded = True
            except Exception as e:
                _LOGGER.error("Непредвиденная ошибка при загрузке данных: %s", e, exc_info=True)
                self._data = {}
                self._loaded = True
        
        return self._data
    
    async def async_save(self) -> bool:
        """Сохранение данных в файл."""
        async with file_lock:
            try:
                # Убедимся, что директория существует
                await self.hass.async_add_executor_job(
                    lambda: self.data_file.parent.mkdir(parents=True, exist_ok=True)
                )
                
                # Проверим права доступа к директории
                if not await self.hass.async_add_executor_job(lambda: os.access(self.data_file.parent, os.W_OK)):
                    _LOGGER.error("Недостаточно прав для записи в директорию: %s", self.data_file.parent)
                    return False
                
                # Сохраняем с форматированием
                async with aiofiles.open(self.data_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(self._data or {}, indent=2, ensure_ascii=False, cls=JSONEncoder))
                
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
    
    def is_loaded(self) -> bool:
        """Проверить, загружены ли данные."""
        return self._loaded
    
    async def async_add_device(self, device: str) -> bool:
        """Добавить новое устройство."""
        # Валидация имени устройства
        if not device or device == "none":
            _LOGGER.warning("Невозможно добавить устройство с пустым именем")
            return False
        
        # Проверка на допустимые символы
        if not device.replace('_', '').replace('-', '').replace(' ', '').isalnum():
            _LOGGER.warning("Имя устройства содержит недопустимые символы: %s", device)
            return False
        
        # Ограничение длины имени
        if len(device) > 50:
            _LOGGER.warning("Имя устройства слишком длинное: %s", device)
            return False
        
        # Загружаем данные, если это первое обращение
        if not self._loaded:
            await self.async_load()
        
        if device in (self._data or {}):
            _LOGGER.warning("Устройство %s уже существует", device)
            return False
        
        if self._data is None:
            self._data = {}
        
        self._data[device] = {}
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Добавлено новое устройство: %s", device)
            # Создаем уведомление через сервис
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": f"Устройство '{device}' успешно добавлено",
                        "title": "IR Remote: Устройство добавлено",
                        "notification_id": f"{DOMAIN}_device_added"
                    }
                )
            except Exception as e:
                _LOGGER.debug("Could not create notification: %s", e)
        
        return success
    
    async def async_add_command(self, device: str, command: str, code: str) -> bool:
        """Добавить новую команду для устройства."""
        # Валидация параметров
        if not device or not command or device == "none" or command == "none" or not code:
            _LOGGER.warning("Невозможно добавить команду: недостаточно данных")
            return False
        
        # Проверка на допустимые символы в имени команды
        if not command.replace('_', '').replace('-', '').replace(' ', '').replace('+', '').isalnum():
            _LOGGER.warning("Имя команды содержит недопустимые символы: %s", command)
            return False
        
        # Ограничение длины
        if len(command) > 50:
            _LOGGER.warning("Имя команды слишком длинное: %s", command)
            return False
        
        # Загружаем данные, если это первое обращение
        if not self._loaded:
            await self.async_load()
        
        if self._data is None:
            self._data = {}
        
        # Создаем устройство, если его нет
        if device not in self._data:
            self._data[device] = {}
        
        # Проверяем, не существует ли уже такая команда
        if command in self._data[device]:
            _LOGGER.warning("Команда %s для устройства %s уже существует", command, device)
        
        self._data[device][command] = {
            "code": code,
            "name": f"{device.upper()} {command.replace('_', ' ').title()}",
            "description": f"IR code for {device} {command}"
        }
        
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Добавлена новая команда %s для устройства %s", command, device)
        
        return success
    
    async def async_remove_device(self, device: str) -> bool:
        """Удалить устройство и все его команды."""
        if not device or device == "none":
            _LOGGER.warning("Невозможно удалить устройство: пустое имя")
            return False
        
        # Загружаем данные, если это первое обращение
        if not self._loaded:
            await self.async_load()
        
        if device not in (self._data or {}):
            _LOGGER.warning("Устройство %s не найдено", device)
            return False
        
        # Удаляем устройство
        del self._data[device]
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Удалено устройство: %s", device)
            # Создаем уведомление через сервис
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": f"Устройство '{device}' удалено",
                        "title": "IR Remote: Устройство удалено",
                        "notification_id": f"{DOMAIN}_device_removed"
                    }
                )
            except Exception as e:
                _LOGGER.debug("Could not create notification: %s", e)
        
        return success

    async def async_remove_command(self, device: str, command: str) -> bool:
        """Удалить команду для устройства."""
        if not device or not command or device == "none" or command == "none":
            _LOGGER.warning("Невозможно удалить команду: недостаточно данных")
            return False
        
        # Загружаем данные, если это первое обращение
        if not self._loaded:
            await self.async_load()
        
        if device not in (self._data or {}) or command not in self._data[device]:
            _LOGGER.warning("Команда %s для устройства %s не найдена", command, device)
            return False
        
        # Удаляем команду
        del self._data[device][command]
        
        # Если у устройства не осталось команд, удаляем само устройство
        if not self._data[device]:
            del self._data[device]
            _LOGGER.info("Устройство %s удалено так как не осталось команд", device)
        
        success = await self.async_save()
        
        if success:
            _LOGGER.info("Удалена команда %s для устройства %s", command, device)
        
        return success

    async def async_export_config(self) -> dict:
        """Экспортировать конфигурацию устройств и команд."""
        # Загружаем данные, если это первое обращение
        if not self._loaded:
            await self.async_load()
        
        return {
            "version": "1.0",
            "devices": self._data or {}
        }

    async def async_import_config(self, config: dict) -> bool:
        """Импортировать конфигурацию устройств и команд."""
        if not isinstance(config, dict) or "devices" not in config:
            _LOGGER.error("Неверный формат конфигурации для импорта")
            return False
        
        # Создаем резервную копию текущих данных
        backup = self._data.copy() if self._data else {}
        
        try:
            # Загружаем данные, если это первое обращение
            if not self._loaded:
                await self.async_load()
            
            if self._data is None:
                self._data = {}
            
            # Импортируем устройства
            imported_count = 0
            for device, commands in config["devices"].items():
                if device not in self._data:
                    self._data[device] = {}
                
                for command, command_data in commands.items():
                    if isinstance(command_data, dict) and "code" in command_data:
                        self._data[device][command] = command_data
                        imported_count += 1
                    else:
                        _LOGGER.warning("Пропущена некорректная команда %s для устройства %s", command, device)
            
            # Сохраняем импортированные данные
            success = await self.async_save()
            
            if success:
                _LOGGER.info("Импортировано %d команд", imported_count)
                # Создаем уведомление через сервис
                try:
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "message": f"Импортировано {imported_count} команд",
                            "title": "IR Remote: Импорт завершен",
                            "notification_id": f"{DOMAIN}_import_complete"
                        }
                    )
                except Exception as e:
                    _LOGGER.debug("Could not create notification: %s", e)
            else:
                # Восстанавливаем резервную копию
                self._data = backup
                _LOGGER.error("Ошибка сохранения импортированных данных")
            
            return success
            
        except Exception as e:
            # Восстанавливаем резервную копию
            self._data = backup
            _LOGGER.error("Ошибка импорта конфигурации: %s", e)
            return False


async def update_ir_data(hass: HomeAssistant) -> dict:
    """Обновление данных ИК-пульта."""
    _LOGGER.debug("Обновление данных IR")
    
    # Базовая структура данных
    data = {
        "devices": ["none"],
        "commands": {"none": ["none"]},  # Добавляем базовую структуру
        "codes": {}
    }
    
    try:
        # Получаем хранилище данных
        ir_data = hass.data[DOMAIN].get("data")
        if not ir_data:
            _LOGGER.warning("Хранилище данных IR не инициализировано, возвращаем базовые данные")
            return data
        
        # Загружаем данные
        await ir_data.async_load()
        
        # Проверяем, что данные загружены
        if not ir_data.is_loaded():
            _LOGGER.warning("Данные IR не загружены, возвращаем базовые данные")
            return data
        
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
        
        _LOGGER.info("Данные IR успешно обновлены: %d устройств", len(devices))
        
    except Exception as e:
        _LOGGER.error("Ошибка при обновлении данных IR: %s", e, exc_info=True)
    
    return data


async def setup_ir_data_coordinator(hass: HomeAssistant) -> DataUpdateCoordinator:
    """Настройка координатора данных IR."""
    _LOGGER.info("Настройка координатора данных IR")
    
    # Инициализация хранилища данных
    ir_data = IRRemoteData(hass)
    hass.data[DOMAIN]["data"] = ir_data
    
    # Предварительно загружаем данные
    await ir_data.async_load()
    _LOGGER.info("Данные IR предварительно загружены")
    
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
    _LOGGER.info("Координатор данных IR настроен и обновлен")
    
    return coordinator
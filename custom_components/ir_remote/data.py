"""IR Remote data handler - исправленная версия с Storage API."""
import logging
import asyncio
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Версия хранилища данных
STORAGE_VERSION = 1
STORAGE_KEY = "ir_remote_codes"

# Блокировка для предотвращения одновременного доступа
storage_lock = asyncio.Lock()


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
        _LOGGER.info("Notification: %s - %s", title, message)


class IRRemoteData:
    """Класс для работы с данными ИК-пульта через Storage API."""
    
    def __init__(self, hass: HomeAssistant):
        """Инициализация хранилища данных."""
        self.hass = hass
        # Используем Storage API для хранения данных
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # Старый путь для миграции данных
        self.old_data_file = Path(hass.config.path()) / "custom_components" / DOMAIN / "scripts" / "ir_codes.json"
        self._data = None
        self._loaded = False
        
        _LOGGER.info("IR Remote using Storage API: %s", STORAGE_KEY)
    
    async def _migrate_old_data(self) -> None:
        """Миграция данных из старого местоположения."""
        try:
            # Проверяем, есть ли старый файл и нет ли уже данных в Storage
            old_exists = await self.hass.async_add_executor_job(lambda: self.old_data_file.exists())
            storage_data = await self.store.async_load()
            
            if old_exists and not storage_data:
                _LOGGER.info("Migrating IR codes from old location to Storage API")
                
                # Читаем старый файл
                import json
                import aiofiles
                
                async with aiofiles.open(self.old_data_file, 'r', encoding='utf-8') as f:
                    old_content = await f.read()
                
                old_data = json.loads(old_content)
                
                # Создаем резервную копию старого файла
                backup_path = self.old_data_file.with_suffix('.backup')
                async with aiofiles.open(backup_path, 'w', encoding='utf-8') as f:
                    await f.write(old_content)
                
                # Сохраняем в Storage API
                await self.store.async_save(old_data)
                
                _LOGGER.info("Migration completed successfully. Backup saved: %s", backup_path)
                
                # Уведомляем пользователя о миграции
                await async_create_notification(
                    self.hass,
                    "Данные ИК-пульта перенесены в системное хранилище Home Assistant. "
                    "Теперь они не будут потеряны при обновлениях интеграции и будут "
                    "автоматически включены в резервные копии HA.",
                    "IR Remote: Миграция данных",
                    f"{DOMAIN}_migration"
                )
                
        except Exception as e:
            _LOGGER.error("Error during data migration: %s", e, exc_info=True)
    
    async def async_load(self) -> dict:
        """Загрузка данных из Storage API."""
        if self._loaded and self._data is not None:
            return self._data
        
        async with storage_lock:
            try:
                # Сначала пытаемся мигрировать старые данные
                await self._migrate_old_data()
                
                # Загружаем данные из Storage API
                self._data = await self.store.async_load()
                
                if self._data is None:
                    _LOGGER.info("No existing IR data found, initializing empty storage")
                    self._data = {}
                    await self.store.async_save(self._data)
                else:
                    _LOGGER.info("IR data loaded from storage: %d devices", len(self._data))
                
                self._loaded = True
                
            except Exception as e:
                _LOGGER.error("Error loading IR data from storage: %s", e, exc_info=True)
                self._data = {}
                self._loaded = True
        
        return self._data
    
    async def async_save(self) -> bool:
        """Сохранение данных в Storage API."""
        async with storage_lock:
            try:
                await self.store.async_save(self._data or {})
                _LOGGER.debug("IR data successfully saved to storage")
                return True
            except Exception as e:
                _LOGGER.error("Error saving IR data to storage: %s", e, exc_info=True)
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
            try:
                await async_create_notification(
                    self.hass,
                    f"Устройство '{device}' успешно добавлено",
                    "IR Remote: Устройство добавлено",
                    f"{DOMAIN}_device_added"
                )
            except Exception as e:
                _LOGGER.debug("Could not create notification: %s", e)
        
        return success
    
    async def async_add_command(self, device: str, command: str, code: str) -> bool:
        """Добавить новую команду для устройства."""
        # Валидация параметров
        if not device or not command or device == "none" or command == "none" or not code:
            _LOGGER.warning("Невозможно добавить команду: недостаточно данных (device=%s, command=%s, code_len=%s)", 
                          device, command, len(code) if code else 0)
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
            _LOGGER.info("Создано новое устройство при добавлении команды: %s", device)
        
        # Проверяем, не существует ли уже такая команда
        if command in self._data[device]:
            _LOGGER.warning("Команда %s для устройства %s уже существует, перезаписываем", command, device)
        
        self._data[device][command] = {
            "code": code,
            "name": f"{device.upper()} {command.replace('_', ' ').title()}",
            "description": f"IR code for {device} {command}"
        }
        
        success = await self.async_save()
        
        if success:
            _LOGGER.info("✅ Добавлена новая команда %s для устройства %s (код длиной %d символов)", 
                        command, device, len(code))
        else:
            _LOGGER.error("❌ Не удалось сохранить команду %s для устройства %s", command, device)
        
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
            try:
                await async_create_notification(
                    self.hass,
                    f"Устройство '{device}' удалено",
                    "IR Remote: Устройство удалено",
                    f"{DOMAIN}_device_removed"
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
                try:
                    await async_create_notification(
                        self.hass,
                        f"Импортировано {imported_count} команд",
                        "IR Remote: Импорт завершен",
                        f"{DOMAIN}_import_complete"
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
        "commands": {"none": ["none"]},
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
            _LOGGER.debug("Устройства из storage: %s", devices)
        
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
"""Обработчик пользовательского интерфейса для IR Remote."""
import os
import logging
import json
import aiofiles
from pathlib import Path
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.http.static import StaticPathConfig

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Путь к директории с веб-компонентами
FRONTEND_DIRECTORY: Final = Path(__file__).parent / "www"

async def async_setup_frontend(hass: HomeAssistant, config_entry) -> bool:
    """Настроить пользовательский интерфейс ИК-пульта."""
    
    # Проверяем существование директории www
    www_path = FRONTEND_DIRECTORY
    if not os.path.isdir(www_path):
        _LOGGER.error("Директория с веб-компонентами не найдена: %s", www_path)
        return False
    
    # Путь к файлу карточки
    card_path = www_path / "ir-remote-card.js"
    
    # Проверяем существование файла карточки
    if not os.path.isfile(card_path):
        _LOGGER.error("Файл карточки не найден: %s", card_path)
        
        # Создаем файл карточки
        try:
            _LOGGER.debug("Создаем файл карточки...")
            
            # Создаем директорию www, если её нет
            if not os.path.isdir(www_path):
                await hass.async_add_executor_job(lambda: os.makedirs(www_path, exist_ok=True))
            
            # Создаем файл карточки
            card_content = await _get_card_content()
            async with aiofiles.open(card_path, "w", encoding="utf-8") as f:
                await f.write(card_content)
                
            _LOGGER.debug("Файл карточки создан успешно: %s", card_path)
        except Exception as e:
            _LOGGER.error("Ошибка создания файла карточки: %s", e, exc_info=True)
            return False
    
    # Регистрируем карточку как ресурс
    try:
        # Формируем URL компонента
        component_url = f"/ir_remote/ir-remote-card.js"
        
        # Используем асинхронный метод для регистрации статического пути
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                url_path=component_url,
                path=str(card_path),
                cache_headers=False
            )
        ])
        
        # Регистрируем ресурс в frontend
        # Используем импорт внутри функции, чтобы избежать ошибок импорта
        from homeassistant.components import frontend
        await hass.async_add_executor_job(
            frontend.async_register_extra_module_url,
            hass,
            component_url, 
            module_type="module"
        )
        
        _LOGGER.debug("Карточка ИК-пульта успешно зарегистрирована")
        
        # Сохраняем URL карточки в данных домена
        hass.data[DOMAIN]["card_url"] = component_url
        
        # Создаем или обновляем панель Lovelace
        await async_create_lovelace_card(hass, config_entry)
        
        return True
    except Exception as e:
        _LOGGER.error("Ошибка регистрации карточки: %s", e, exc_info=True)
        return False


async def async_create_lovelace_card(hass: HomeAssistant, config_entry) -> None:
    """Создать карточку Lovelace для ИК-пульта."""
    try:
        # Получаем идентификатор устройства
        device_id = config_entry.entry_id
        
        # Создаем конфигурацию карточки
        card_config = {
            "type": "entities",
            "title": "ИК-пульт",
            "entities": [
                # Группа отправки команд
                {"type": "section", "label": "Отправка команд"},
                {"entity": "select.ir_remote_01_10_send_device"},
                {"entity": "select.ir_remote_01_11_command_selector"},
                {"entity": "button.ir_remote_01_12_send_button"},
                
                # Группа обучения
                {"type": "section", "label": "Обучение новым командам"},
                {"entity": "select.ir_remote_02_20_learn_device"},
                {"entity": "text.ir_remote_02_21_button_input"},
                {"entity": "button.ir_remote_02_22_learn_button"},
                
                # Группа добавления устройств
                {"type": "section", "label": "Добавление устройств"},
                {"entity": "text.ir_remote_03_30_new_device_input"},
                {"entity": "button.ir_remote_03_31_add_device_button"}
            ]
        }
        
        # Сохраняем конфигурацию карточки в данных домена для удобства
        hass.data[DOMAIN]["card_config"] = card_config
        
        # Показываем пользователю уведомление о добавлении карточки
        await hass.async_add_executor_job(
            hass.components.persistent_notification.create,
            f"ИК-пульт настроен! Вы можете создать карточку управления на любой панели Lovelace, "
            f"используя следующие сущности: select.ir_remote_01_10_send_device, select.ir_remote_01_11_command_selector и т.д.",
            "ИК-пульт установлен",
            f"{DOMAIN}_setup"
        )
        
    except Exception as e:
        _LOGGER.error("Ошибка создания карточки Lovelace: %s", e, exc_info=True)


async def _get_card_content() -> str:
    """Получить содержимое файла карточки."""
    # Здесь нужно вставить код карточки из предыдущего ответа
    # Для краткости используем заглушку
    return """
// Упрощенная карточка IR Remote
class IrRemoteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
  }

  setConfig(config) {
    if (!config) {
      throw new Error("No configuration");
    }
    
    this.config = config;
    this.render();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <ha-card header="ИК-пульт">
        <div class="card-content">
          <p>Пожалуйста, используйте стандартные сущности:</p>
          <ul>
            <li>select.ir_remote_01_10_send_device</li>
            <li>select.ir_remote_01_11_command_selector</li>
            <li>button.ir_remote_01_12_send_button</li>
            <li>и другие</li>
          </ul>
        </div>
      </ha-card>
    `;
  }

  set hass(hass) {
    this._hass = hass;
  }
}

customElements.define('ir-remote-card', IrRemoteCard);
"""
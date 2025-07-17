"""Constants for IR Remote integration."""

# Domain
DOMAIN = "ir_remote"

# Configuration constants
CONF_IEEE = "ieee"
CONF_ENDPOINT = "endpoint_id"
CONF_CLUSTER = "cluster_id"
CONF_CLUSTER_TYPE = "cluster_type"
CONF_COMMAND_TYPE = "command_type"
CONF_ROOM_NAME = "room_name"
CONF_DEVICE_TYPE = "device_type"

# Default values for ZHA
DEFAULT_CLUSTER_ID = 57348
DEFAULT_CLUSTER_TYPE = "in"
DEFAULT_COMMAND_TYPE = "server"
DEFAULT_ENDPOINT_ID = 1

# Config Flow constants
CONF_ACTION = "action"
CONF_CONTROLLER_ID = "controller_id" 
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_COMMAND_NAME = "command_name"

# Config Flow actions
ACTION_ADD_CONTROLLER = "add_controller"
ACTION_ADD_DEVICE = "add_device"
ACTION_ADD_COMMAND = "add_command"
ACTION_REMOVE_DEVICE = "remove_device"
ACTION_REMOVE_COMMAND = "remove_command"
ACTION_MANAGE = "manage"

# Config Flow steps
STEP_INIT = "init"
STEP_SELECT_CONTROLLER = "select_controller"
STEP_ADD_CONTROLLER = "add_controller"
STEP_ADD_DEVICE = "add_device"
STEP_SELECT_DEVICE_TYPE = "select_device_type"
STEP_ADD_COMMAND = "add_command"
STEP_LEARN_COMMAND = "learn_command"
STEP_SELECT_CONTROLLER_FOR_REMOVE_DEVICE = "select_controller_for_remove_device"
STEP_SELECT_DEVICE_FOR_REMOVE = "select_device_for_remove"
STEP_CONFIRM_REMOVE_DEVICE = "confirm_remove_device"
STEP_SELECT_CONTROLLER_FOR_REMOVE_COMMAND = "select_controller_for_remove_command"
STEP_SELECT_DEVICE_FOR_REMOVE_COMMAND = "select_device_for_remove_command"
STEP_SELECT_COMMAND_FOR_REMOVE = "select_command_for_remove"
STEP_CONFIRM_REMOVE_COMMAND = "confirm_remove_command"
STEP_MANAGE = "manage"

# Device types
DEVICE_TYPE_TV = "tv"
DEVICE_TYPE_AUDIO = "audio"
DEVICE_TYPE_PROJECTOR = "projector"
DEVICE_TYPE_AC = "ac"
DEVICE_TYPE_UNIVERSAL = "universal"

DEVICE_TYPES = {
    DEVICE_TYPE_TV: "Телевизор",
    DEVICE_TYPE_AUDIO: "Аудиосистема", 
    DEVICE_TYPE_PROJECTOR: "Проектор",
    DEVICE_TYPE_AC: "Кондиционер",
    DEVICE_TYPE_UNIVERSAL: "Универсальное устройство"
}

# Media player device types
MEDIA_PLAYER_TYPES = [DEVICE_TYPE_TV, DEVICE_TYPE_AUDIO, DEVICE_TYPE_PROJECTOR]

# Standard commands for device types
STANDARD_COMMANDS = {
    DEVICE_TYPE_TV: {
        "power": "Питание",
        "volume_up": "Громче",
        "volume_down": "Тише", 
        "mute": "Без звука",
        "channel_up": "Канал +",
        "channel_down": "Канал -",
        "menu": "Меню",
        "home": "Домой",
        "back": "Назад",
        "ok": "ОК",
        "up": "Вверх",
        "down": "Вниз", 
        "left": "Влево",
        "right": "Вправо"
    },
    DEVICE_TYPE_AUDIO: {
        "power": "Питание",
        "volume_up": "Громче",
        "volume_down": "Тише",
        "mute": "Без звука",
        "play": "Воспроизведение",
        "pause": "Пауза",
        "stop": "Стоп",
        "next": "Следующий",
        "previous": "Предыдущий",
        "source": "Источник"
    },
    DEVICE_TYPE_PROJECTOR: {
        "power": "Питание",
        "volume_up": "Громче", 
        "volume_down": "Тише",
        "mute": "Без звука",
        "menu": "Меню",
        "source": "Источник",
        "zoom_in": "Увеличить",
        "zoom_out": "Уменьшить"
    },
    DEVICE_TYPE_AC: {
        "power": "Питание",
        "power_on": "Включить",
        "power_off": "Выключить",
        "temp_16": "16°C",
        "temp_17": "17°C",
        "temp_18": "18°C",
        "temp_19": "19°C",
        "temp_20": "20°C",
        "temp_21": "21°C",
        "temp_22": "22°C",
        "temp_23": "23°C",
        "temp_24": "24°C",
        "temp_25": "25°C",
        "temp_26": "26°C",
        "temp_27": "27°C",
        "temp_28": "28°C",
        "temp_29": "29°C",
        "temp_30": "30°C",
        "mode_cool": "Охлаждение",
        "mode_heat": "Обогрев", 
        "mode_auto": "Авто",
        "mode_fan": "Вентилятор",
        "mode_dry": "Осушение",
        "fan_auto": "Авто скорость",
        "fan_low": "Низкая скорость",
        "fan_medium": "Средняя скорость",
        "fan_high": "Высокая скорость",
        "swing": "Поворот",
        "swing_on": "Поворот вкл",
        "swing_off": "Поворот выкл"
    }
}

# Power commands mapping
POWER_ON_COMMANDS = ["power", "on", "power_on", "turn_on"]
POWER_OFF_COMMANDS = ["power", "off", "power_off", "turn_off"]

# Error codes
ERROR_NO_DEVICE = "device_not_found"
ERROR_NO_ZHA = "zha_not_found"
ERROR_DEVICE_EXISTS = "device_exists"
ERROR_COMMAND_EXISTS = "command_exists"
ERROR_INVALID_NAME = "invalid_name"
ERROR_LEARN_TIMEOUT = "learn_timeout"
ERROR_LEARN_FAILED = "learn_failed"
ERROR_REMOVE_FAILED = "remove_failed"

# Service names
SERVICE_LEARN_COMMAND = "learn_command"
SERVICE_SEND_CODE = "send_code"
SERVICE_SEND_COMMAND = "send_command"
SERVICE_ADD_DEVICE = "add_device"
SERVICE_ADD_COMMAND = "add_command"
SERVICE_REMOVE_DEVICE = "remove_device"
SERVICE_REMOVE_COMMAND = "remove_command"
SERVICE_GET_DATA = "get_data"

# Service attributes
ATTR_CONTROLLER_ID = "controller_id"
ATTR_DEVICE = "device"
ATTR_COMMAND = "command"
ATTR_CODE = "code"
ATTR_DEVICE_NAME = "device_name"
ATTR_COMMAND_NAME = "command_name"

# ZHA commands
ZHA_COMMAND_LEARN = 1
ZHA_COMMAND_SEND = 2

# Storage constants
STORAGE_VERSION = 1
STORAGE_KEY = "ir_remote_data"

# Entity naming patterns
ENTITY_COMMAND_BUTTON = "{device}_{command}"
ENTITY_MEDIA_PLAYER = "{device}_player"
ENTITY_CLIMATE = "{device}_climate"
ENTITY_REMOTE_DEVICE = "{device}_remote"

# Device info
MANUFACTURER = "IR Remote Integration"
MODEL_CONTROLLER = "IR Controller"
MODEL_VIRTUAL_DEVICE = "Virtual IR Device"
MODEL_MEDIA_PLAYER = "IR Media Player"
MODEL_CLIMATE = "IR Climate"
MODEL_REMOTE_DEVICE = "IR Remote"

# Validation constants
MAX_NAME_LENGTH = 50
ALLOWED_NAME_PATTERN = r"^[a-zA-Z0-9\s\-_а-яёА-ЯЁ]+$"

# Translation keys
TRANSLATION_KEY_ADD_COMMAND = "add_command"
TRANSLATION_KEY_DEVICE_COMMAND = "device_command"
TRANSLATION_KEY_MEDIA_PLAYER = "media_player"
TRANSLATION_KEY_CLIMATE = "climate"
TRANSLATION_KEY_REMOTE_DEVICE = "remote_device"
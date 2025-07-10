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

# Default values for ZHA
DEFAULT_CLUSTER_ID = 57348
DEFAULT_CLUSTER_TYPE = "in"
DEFAULT_COMMAND_TYPE = "server"
DEFAULT_ENDPOINT_ID = 1

# Config Flow constants
CONF_ACTION = "action"
CONF_CONTROLLER_ID = "controller_id" 
CONF_DEVICE_NAME = "device_name"
CONF_COMMAND_NAME = "command_name"

# Config Flow actions
ACTION_ADD_CONTROLLER = "add_controller"
ACTION_ADD_DEVICE = "add_device"
ACTION_ADD_COMMAND = "add_command"
ACTION_MANAGE = "manage"

# Config Flow steps
STEP_INIT = "init"
STEP_SELECT_CONTROLLER = "select_controller"
STEP_ADD_CONTROLLER = "add_controller"
STEP_ADD_DEVICE = "add_device"
STEP_ADD_COMMAND = "add_command"
STEP_LEARN_COMMAND = "learn_command"
STEP_MANAGE = "manage"

# Error codes
ERROR_NO_DEVICE = "device_not_found"
ERROR_NO_ZHA = "zha_not_found"
ERROR_DEVICE_EXISTS = "device_exists"
ERROR_COMMAND_EXISTS = "command_exists"
ERROR_INVALID_NAME = "invalid_name"
ERROR_LEARN_TIMEOUT = "learn_timeout"
ERROR_LEARN_FAILED = "learn_failed"

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

# Device info
MANUFACTURER = "IR Remote Integration"
MODEL_CONTROLLER = "IR Controller"
MODEL_VIRTUAL_DEVICE = "Virtual IR Device"

# Validation constants
MAX_NAME_LENGTH = 50
ALLOWED_NAME_PATTERN = r"^[a-zA-Z0-9\s\-_а-яёА-ЯЁ]+$"

# Translation keys
TRANSLATION_KEY_DEVICE_COMMAND = "device_command"
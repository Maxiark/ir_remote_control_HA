"""Constants for IR Remote integration."""
DOMAIN = "ir_remote"

# Configuration constants
CONF_IEEE = "ieee"
CONF_ENDPOINT = "endpoint_id"
CONF_CLUSTER = "cluster_id"
CONF_CLUSTER_TYPE = "cluster_type"
CONF_COMMAND_TYPE = "command_type"

# Default values
DEFAULT_CLUSTER_ID = 57348
DEFAULT_CLUSTER_TYPE = "in"
DEFAULT_COMMAND_TYPE = "server"
DEFAULT_ENDPOINT_ID = 1

# Error codes
ERROR_NO_DEVICE = "device_not_found"
ERROR_NO_ZHA = "zha_not_found"

# Service names
SERVICE_LEARN_CODE = "learn_code"
SERVICE_SEND_CODE = "send_code"
SERVICE_SEND_COMMAND = "send_command"
SERVICE_GET_DATA = "get_data"
SERVICE_ADD_DEVICE = "add_device"
SERVICE_REMOVE_DEVICE = "remove_device"
SERVICE_REMOVE_COMMAND = "remove_command"
SERVICE_EXPORT_CONFIG = "export_config"
SERVICE_IMPORT_CONFIG = "import_config"

# Entity attributes
ATTR_DEVICE = "device"
ATTR_BUTTON = "button"
ATTR_CODE = "code"

# ZHA commands
ZHA_COMMAND_LEARN = 1
ZHA_COMMAND_SEND = 2

# Translation keys
TRANSLATION_KEY_DEVICE = "device"
TRANSLATION_KEY_BUTTON = "button"
TRANSLATION_KEY_COMMAND = "command"
TRANSLATION_KEY_LEARN = "learn_button"
TRANSLATION_KEY_SEND = "send_button"
TRANSLATION_KEY_NEW_DEVICE = "new_device"
TRANSLATION_KEY_ADD_DEVICE = "add_device_button"
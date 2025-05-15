"""Manage IR Remote devices."""
import json
import sys
from pathlib import Path

def get_config_path() -> Path:
    """Get path to configuration file."""
    return Path(__file__).parent / "ir_codes.json"

def load_devices() -> list:
    """Load list of devices from JSON file."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return sorted(list(data.keys()))
            except json.JSONDecodeError:
                return []
    return []

def add_device(device_name: str) -> bool:
    """Add new device."""
    if not device_name:
        print("Device name cannot be empty", file=sys.stderr)
        return False
        
    config_path = get_config_path()
    codes = {}
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                codes = json.load(f)
            except json.JSONDecodeError:
                codes = {}
    
    if device_name in codes:
        print(f"Device {device_name} already exists", file=sys.stderr)
        return False
        
    codes[device_name] = {}
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(codes, f, indent=2, ensure_ascii=False)
    
    return True

def get_devices() -> str:
    """Get list of devices for selector."""
    devices = load_devices()
    if not devices:
        return "none"
    return ','.join(['none'] + devices)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: manage_devices.py [list|add] [device_name]", file=sys.stderr)
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "list":
        print(get_devices(), end='')
    elif command == "add" and len(sys.argv) == 3:
        success = add_device(sys.argv[2])
        print("success" if success else "error", end='')
    else:
        print("Invalid command", file=sys.stderr)
        sys.exit(1)
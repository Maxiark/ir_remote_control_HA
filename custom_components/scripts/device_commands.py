"""Get available commands for a device."""
import json
import sys
from pathlib import Path

def get_device_commands(device: str) -> str:
    """Get list of commands for specified device."""
    config_path = Path(__file__).parent / "ir_codes.json"
    
    try:
        if not config_path.exists():
            print(f"File does not exist: {config_path}", file=sys.stderr)
            return "none"

        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if device in data:
                commands = ['none'] + list(data[device].keys())
                return ','.join(commands)
            
            print(f"Device {device} not found in data", file=sys.stderr)
            return "none"
            
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}", file=sys.stderr)
        return "none"
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        return "none"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(get_device_commands(sys.argv[1]), end='')
    else:
        print("No device specified", file=sys.stderr)
        print('none', end='')
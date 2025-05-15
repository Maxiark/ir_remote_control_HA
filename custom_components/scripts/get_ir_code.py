"""Get IR code for specific device and button."""
import json
import sys
from pathlib import Path

def get_ir_code(device: str, button: str) -> str:
    """Get IR code from configuration."""
    config_path = Path(__file__).parent / "ir_codes.json"
    
    try:
        if not config_path.exists():
            return "No directory"
            
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if device in data and button in data[device]:
                return data[device][button]['code']
            return "Not found code"
                
    except Exception as e:
        return f"Err: {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(get_ir_code(sys.argv[1], sys.argv[2]), end='')
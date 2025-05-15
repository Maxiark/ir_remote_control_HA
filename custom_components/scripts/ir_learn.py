"""IR Remote learning script."""
import json
import sys
import os
from pathlib import Path

def get_config_path() -> Path:
    """Get path to ir_codes.json."""
    return Path(__file__).parent / "ir_codes.json"

def load_codes():
    """Load existing IR codes."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_code(device: str, button: str, code: str) -> None:
    """Save new IR code."""
    codes = load_codes()
    
    # Create device if it doesn't exist
    if device not in codes:
        codes[device] = {}
    
    codes[device][button] = {
        "code": code,
        "name": f"{device.upper()} {button.replace('_', ' ').title()}",
        "description": f"IR code for {device} {button}"
    }
    
    with open(get_config_path(), 'w', encoding='utf-8') as f:
        json.dump(codes, f, indent=2, ensure_ascii=False)
        
    print(f"Saved code for {device} - {button}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: ir_learn.py <device> <button> <code>")
        sys.exit(1)
        
    device = sys.argv[1]
    button = sys.argv[2]
    code = sys.argv[3]
    save_code(device, button, code)
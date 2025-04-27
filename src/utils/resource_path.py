import os
import sys

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        print(f"PyInstaller mode - base path: {base_path}")
    except Exception:
        # If not running as a PyInstaller bundle, use the script's directory
        base_path = os.path.abspath(".")
        print(f"Development mode - base path: {base_path}")
    
    full_path = os.path.join(base_path, relative_path)
    print(f"Resource: {relative_path} -> {full_path} (exists: {os.path.exists(full_path)})")
    return full_path 
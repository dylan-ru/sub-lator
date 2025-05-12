import os
import sys

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    
    Args:
        relative_path (str): Path relative to the script or executable
        
    Returns:
        str: The absolute path to the resource
    """
    # Check if the application is running in a bundle (PyInstaller executable)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # If running from PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # If running in normal Python environment
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path) 
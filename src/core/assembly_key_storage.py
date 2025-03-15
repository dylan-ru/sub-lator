import os
import json
from typing import List
from pathlib import Path

class AssemblyKeyStorage:
    """Storage for AssemblyAI API keys."""
    
    def __init__(self):
        """Initialize the AssemblyAI key storage."""
        # Use pathlib for path handling
        app_data_dir = Path.home() / ".srt_translator"
        # Create the directory if it doesn't exist
        app_data_dir.mkdir(exist_ok=True, parents=True)
        # Set the path to the key file
        self.key_file = app_data_dir / "assembly_keys.json"
        
    def get_keys(self) -> List[str]:
        """Get all stored AssemblyAI API keys."""
        if not self.key_file.exists():
            return []
            
        try:
            with open(self.key_file, "r") as f:
                keys = json.load(f)
            return keys
        except (json.JSONDecodeError, FileNotFoundError):
            return []
            
    def add_key(self, key: str) -> None:
        """Add an AssemblyAI API key to storage."""
        keys = self.get_keys()
        if key not in keys:
            keys.append(key)
            self.save_keys(keys)
            
    def save_keys(self, keys: List[str]) -> None:
        """Save a list of AssemblyAI API keys to storage."""
        with open(self.key_file, "w") as f:
            json.dump(keys, f)
            
    def remove_all_keys(self) -> None:
        """Remove all AssemblyAI API keys from storage."""
        self.save_keys([])
        
    def remove_key(self, key: str) -> None:
        """Remove a specific AssemblyAI API key from storage."""
        keys = self.get_keys()
        if key in keys:
            keys.remove(key)
            self.save_keys(keys)
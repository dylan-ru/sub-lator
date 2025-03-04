import json
import os
from typing import List
from pathlib import Path

class GroqKeyStorage:
    """Class to handle storage and retrieval of Groq API keys"""

    def __init__(self):
        self.keys_file = self._get_storage_path()
        self._ensure_storage_exists()

    def _get_storage_path(self) -> Path:
        """Get the path to the API keys storage file."""
        # Get user's home directory
        home_dir = Path.home()
        # Create directory path
        storage_dir = home_dir / ".srt_translator"
        # Create file path
        return storage_dir / "groq_api_keys.json"

    def _ensure_storage_exists(self) -> None:
        """Ensure that the storage directory and file exist."""
        # Create directory if it doesn't exist
        self.keys_file.parent.mkdir(exist_ok=True)
        
        # Create file if it doesn't exist
        if not self.keys_file.exists():
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump({"keys": []}, f)

    def get_keys(self) -> List[str]:
        """Get all stored API keys."""
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("keys", [])
        except (FileNotFoundError, json.JSONDecodeError):
            # Return empty list if file doesn't exist or is invalid
            return []

    def add_key(self, key: str) -> None:
        """Add a new API key to storage."""
        keys = self.get_keys()
        
        # Don't add if already exists
        if key in keys:
            return
            
        keys.append(key)
        
        with open(self.keys_file, 'w', encoding='utf-8') as f:
            json.dump({"keys": keys}, f)

    def remove_key(self, key: str) -> None:
        """Remove an API key from storage."""
        keys = self.get_keys()
        
        if key in keys:
            keys.remove(key)
            
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump({"keys": keys}, f)

    def remove_all_keys(self) -> None:
        """Remove all API keys from storage."""
        with open(self.keys_file, 'w', encoding='utf-8') as f:
            json.dump({"keys": []}, f) 
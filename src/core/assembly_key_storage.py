import json
import os
from pathlib import Path

class AssemblyKeyStorage:
    def __init__(self):
        self.config_dir = Path.home() / '.srt_translator'
        self.storage_file = str(self.config_dir / 'assembly_api_keys.json')
        self._ensure_storage_file()
        self.api_keys = self._load_keys()

    def _ensure_storage_file(self):
        """Ensure the storage directory and file exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(self.storage_file):
            with open(self.storage_file, 'w') as f:
                json.dump({'api_keys': []}, f)

    def _load_keys(self):
        """Load API keys from the storage file."""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                return data.get('api_keys', [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_keys(self):
        """Save API keys to the storage file."""
        with open(self.storage_file, 'w') as f:
            json.dump({'api_keys': self.api_keys}, f)

    def add_key(self, api_key: str):
        """Add a new API key if it doesn't exist."""
        if api_key not in self.api_keys:
            self.api_keys = [api_key]  # Only store one key at a time
            self._save_keys()

    def remove_key(self, api_key: str):
        """Remove an API key if it exists."""
        if api_key in self.api_keys:
            self.api_keys.remove(api_key)
            self._save_keys()

    def remove_all_keys(self):
        """Remove all API keys."""
        self.api_keys = []
        self._save_keys()

    def get_keys(self):
        """Get all stored API keys."""
        return self.api_keys

    def has_key(self, api_key: str):
        """Check if a specific API key exists."""
        return api_key in self.api_keys
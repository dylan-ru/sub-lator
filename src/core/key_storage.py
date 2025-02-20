import json
import os
from pathlib import Path
from typing import List

class KeyStorage:
    def __init__(self):
        self.config_dir = Path.home() / '.srt_translator'
        self.config_file = self.config_dir / 'api_keys.json'
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensure the configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_keys(self, keys: List[str]) -> None:
        """Save API keys to the configuration file."""
        with open(self.config_file, 'w') as f:
            json.dump({'api_keys': keys}, f)

    def load_keys(self) -> List[str]:
        """Load API keys from the configuration file."""
        if not self.config_file.exists():
            return []
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                return data.get('api_keys', [])
        except (json.JSONDecodeError, IOError):
            return []
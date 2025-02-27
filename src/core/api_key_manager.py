from time import time
from typing import Dict, Optional
from dataclasses import dataclass
from threading import Lock
from .key_storage import KeyStorage

@dataclass
class ApiKeyInfo:
    key: str
    last_used: float = 0
    cooldown_period: float = 5.0  # 5 seconds cooldown

class ApiKeyManager:
    def __init__(self):
        self._keys: Dict[str, ApiKeyInfo] = {}
        self._current_key_index: int = 0
        self._lock = Lock()
        self._storage = KeyStorage()
        # Load saved keys on initialization
        for key in self._storage.load_keys():
            self.add_key(key)

    def add_key(self, key: str) -> None:
        """Add a new API key to the manager."""
        with self._lock:
            if key not in self._keys:
                self._keys[key] = ApiKeyInfo(key=key)
                # Save keys after adding
                self._storage.save_keys(list(self._keys.keys()))

    def remove_key(self, key: str) -> None:
        """Remove an API key from the manager."""
        with self._lock:
            if key in self._keys:
                del self._keys[key]
                # Reset current key index if necessary
                self._current_key_index = min(self._current_key_index, max(0, len(self._keys) - 1))
                # Save keys after removing
                self._storage.save_keys(list(self._keys.keys()))

    def get_available_key(self) -> Optional[str]:
        """Get the next available API key that's not in cooldown."""
        if not self._keys:
            return None

        with self._lock:
            current_time = time()
            keys = list(self._keys.values())
            
            # Try to find an available key starting from the current index
            for _ in range(len(keys)):
                key_info = keys[self._current_key_index]
                if current_time - key_info.last_used >= key_info.cooldown_period:
                    # Update last used time and return the key
                    key_info.last_used = current_time
                    key = key_info.key
                    # Move to next key for next request
                    self._current_key_index = (self._current_key_index + 1) % len(keys)
                    return key
                self._current_key_index = (self._current_key_index + 1) % len(keys)

            # If no key is available, return None
            return None

    def get_all_keys(self) -> list[str]:
        """Get all registered API keys."""
        return list(self._keys.keys())

    def get_key_status(self, key: str) -> Optional[dict]:
        """Get the status of a specific API key."""
        if key not in self._keys:
            return None
            
        key_info = self._keys[key]
        current_time = time()
        time_since_last_use = current_time - key_info.last_used
        is_available = time_since_last_use >= key_info.cooldown_period
        
        return {
            "last_used": key_info.last_used,
            "cooldown_remaining": max(0, key_info.cooldown_period - time_since_last_use),
            "is_available": is_available
        }
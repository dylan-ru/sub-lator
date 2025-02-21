from abc import ABC, abstractmethod
import requests
from typing import List, Dict, Optional
from .api_key_manager import ApiKeyManager

class TranslationService(ABC):
    @abstractmethod
    def translate(self, text: str, model: str) -> str:
        pass

    @abstractmethod
    def get_available_models(self) -> List[str]:
        pass

    @abstractmethod
    def add_api_key(self, key: str) -> None:
        pass

    @abstractmethod
    def remove_api_key(self, key: str) -> None:
        pass

    @abstractmethod
    def get_api_keys(self) -> List[str]:
        pass

    @abstractmethod
    def get_key_status(self, key: str) -> Optional[Dict]:
        pass

class OpenRouterTranslationService(TranslationService):
    def __init__(self):
        self.base_url = "https://openrouter.ai/api/v1"
        self.api_key_manager = ApiKeyManager()
        self.available_models = [
            "google/gemini-2.0-flash-thinking-exp:free",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet",
            "google/gemini-pro",
            "qwen/qwen2.5-vl-72b-instruct:free",
            "deepseek/deepseek-r1-distill-llama-70b:free"
        ]

    def add_api_key(self, key: str) -> None:
        self.api_key_manager.add_key(key)

    def remove_api_key(self, key: str) -> None:
        self.api_key_manager.remove_key(key)

    def get_api_keys(self) -> List[str]:
        return self.api_key_manager.get_all_keys()

    def get_key_status(self, key: str) -> Optional[Dict]:
        return self.api_key_manager.get_key_status(key)

    def translate(self, text: str, model: str) -> str:
        api_key = self.api_key_manager.get_available_key()
        if not api_key:
            raise ValueError("No API key available. Please add an API key or wait for the cooldown period.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a translation assistant. Translate the following text to English, maintaining the original meaning and style. Do not add any additional information or commentary. Translatethe text to the specified language."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise Exception(f"Translation failed: {str(e)}")

    def get_available_models(self) -> List[str]:
        return self.available_models.copy() 
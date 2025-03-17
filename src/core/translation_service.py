from abc import ABC, abstractmethod
import requests
import asyncio
import re
import time
from typing import List, Dict, Optional, Callable, Any
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
        self.max_retries = 5  # Maximum number of retry attempts for rate limits

    def add_api_key(self, key: str) -> None:
        self.api_key_manager.add_key(key)

    def remove_api_key(self, key: str) -> None:
        self.api_key_manager.remove_key(key)

    def get_api_keys(self) -> List[str]:
        return self.api_key_manager.get_all_keys()

    def get_key_status(self, key: str) -> Optional[Dict]:
        return self.api_key_manager.get_key_status(key)

    def _is_rate_limit_error(self, error_message: str) -> bool:
        """Check if an error message indicates a rate limit issue."""
        return any(term in error_message.lower() for term in ["rate limit", "too many requests", "429"])

    def _extract_wait_time(self, error_message: str) -> float:
        """Extract the wait time from a rate limit error message."""
        # Try to find the wait time using regex
        match = re.search(r"try again in (\d+\.\d+)s", error_message)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                pass
        
        # Check for retry-after header value
        match = re.search(r"retry after (\d+) second", error_message, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                pass
        
        # If regex fails, use a default wait time
        return 10.0  # Default to 10 seconds

    async def _handle_rate_limit(self, error_message: str, attempt: int, status_callback: Optional[Callable] = None) -> None:
        """Handle rate limit errors by waiting the specified time."""
        wait_time = self._extract_wait_time(error_message)
        print(f"Rate limit reached. Waiting {wait_time:.1f} seconds before retry (attempt {attempt+1}/{self.max_retries})...")
        
        # Report status if callback provided
        if status_callback:
            status_callback(f"Rate limit reached. Waiting {wait_time:.1f} seconds before retry...")
        
        # Wait for the specified time with updates every second
        for i in range(int(wait_time)):
            # Report progress if callback provided
            if status_callback:
                remaining = wait_time - i
                status_callback(f"Rate limit: waiting {remaining:.1f}s before retry... (attempt {attempt+1}/{self.max_retries})")
            await asyncio.sleep(1)
        
        # Wait any remaining fractional seconds
        fraction = wait_time - int(wait_time)
        if fraction > 0:
            await asyncio.sleep(fraction)
            
        if status_callback:
            status_callback(f"Retrying translation after rate limit wait (attempt {attempt+1}/{self.max_retries})...")

    def translate(self, text: str, model: str) -> str:
        """
        Synchronous method to translate text with the OpenRouter API.
        Kept for backward compatibility.
        """
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
                    "content": "You are a translation assistant. Translate the following text to English, maintaining the original meaning and style. Do not add any additional information or commentary. Translate the text to the specified language."
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

    async def translate_async(self, text: str, model: str, status_callback: Optional[Callable] = None) -> str:
        """
        Asynchronous method to translate text with the OpenRouter API with retry logic.
        
        Args:
            text: The text to translate
            model: The model to use for translation
            status_callback: Optional callback to report status updates during waiting
            
        Returns:
            The translated text
        
        Raises:
            ValueError: If no API keys are available or if the translation fails after max retries
        """
        api_key = self.api_key_manager.get_available_key()
        if not api_key:
            raise ValueError("No API key available. Please add an API key or wait for the cooldown period.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Extract target language from the prompt
        target_language = "English"  # Default
        match = re.search(r"Translate the following .* to ([^.]+)\.", text)
        if match:
            target_language = match.group(1).strip()

        data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a subtitle translator assistant. Translate the given subtitles to {target_language}, preserving all numbers, timecodes, and formatting exactly as they appear. Only translate the text content."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        }

        # Mark this key as used
        self.api_key_manager.mark_key_used(api_key)
        
        # Implement retry logic for rate limit errors
        attempt = 0
        while attempt < self.max_retries:
            try:
                if status_callback:
                    status_callback(f"Sending translation request (attempt {attempt+1}/{self.max_retries})...")

                # Make the synchronous request (with awaitable sleep between retries)
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=60  # Add a reasonable timeout
                )
                
                # Check for errors
                if response.status_code != 200:
                    error_message = "Unknown error"
                    try:
                        error_data = response.json()
                        error_message = error_data.get("error", {}).get("message", "Unknown error")
                    except:
                        error_message = f"HTTP error {response.status_code}: {response.text}"
                    
                    # Check if it's a rate limit error
                    if self._is_rate_limit_error(error_message) or response.status_code == 429:
                        # Handle rate limit error
                        await self._handle_rate_limit(error_message, attempt, status_callback)
                        # Increment attempt counter and try again
                        attempt += 1
                        continue
                    else:
                        # Not a rate limit error, just raise it
                        raise ValueError(f"OpenRouter API error: {error_message}")
                
                # Parse the response
                response_json = response.json()
                
                # Extract the translated text
                translated_text = response_json["choices"][0]["message"]["content"]
                
                return translated_text
                
            except requests.exceptions.Timeout:
                if status_callback:
                    status_callback(f"Request timed out. Retrying (attempt {attempt+1}/{self.max_retries})...")
                await asyncio.sleep(5)  # Wait 5 seconds before retrying on timeout
                attempt += 1
                continue
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limit error
                if self._is_rate_limit_error(error_str):
                    # Handle rate limit error
                    await self._handle_rate_limit(error_str, attempt, status_callback)
                    # Increment attempt counter and try again
                    attempt += 1
                    continue
                else:
                    # Not a rate limit error, just raise it
                    raise ValueError(f"Error during translation: {error_str}")
        
        # If we get here, we've exceeded max retries
        raise ValueError(f"Max retries exceeded ({self.max_retries}). Please try again later.")

    def get_available_models(self) -> List[str]:
        return self.available_models.copy() 

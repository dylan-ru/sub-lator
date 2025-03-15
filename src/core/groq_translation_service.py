import requests
import json
import time
import asyncio
import re
from typing import List, Dict, Optional, Any, Callable
import os
from .groq_key_storage import GroqKeyStorage

class GroqTranslationService:
    """Service for handling Groq API translations"""
    
    def __init__(self):
        self.key_storage = GroqKeyStorage()
        self._key_statuses = {}  # Track key statuses and cooldowns
        self._current_key_index = 0  # Track which key to use next for rotation
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "whisper-large-v3-turbo"
        self.max_retries = 5  # Maximum number of retry attempts for rate limits
        
    def get_api_keys(self) -> List[str]:
        """Get all available API keys."""
        return self.key_storage.get_keys()
        
    def add_api_key(self, key: str) -> None:
        """Add a new API key."""
        self.key_storage.add_key(key)
        
    def remove_api_key(self, key: str) -> None:
        """Remove an API key."""
        self.key_storage.remove_key(key)
        # Also remove from status tracking
        if key in self._key_statuses:
            del self._key_statuses[key]
    
    def get_available_models(self) -> List[str]:
        """Get all available Groq models."""
        return [
            "llama-3.3-70b-versatile",
            "llama-guard-3-8b",
            "llama-3.1-8b-instant"
        ]
    
    def get_transcription_model(self) -> str:
        """Get the default transcription model."""
        return "whisper-large-v3-turbo"
    
    def _is_rate_limit_error(self, error_message: str) -> bool:
        """Check if an error message indicates a rate limit issue."""
        return "rate limit" in error_message.lower() and "please try again in" in error_message.lower()
    
    def _extract_wait_time(self, error_message: str) -> float:
        """Extract the wait time from a rate limit error message."""
        # Try to find the wait time using regex
        match = re.search(r"try again in (\d+\.\d+)s", error_message)
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
    
    async def translate(self, text: str, model: str, status_callback: Optional[Callable] = None) -> str:
        """
        Translate text using Groq API with key rotation and rate limit handling.
        
        Args:
            text: The text to translate
            model: The model to use for translation
            status_callback: Optional callback to report status updates during waiting
            
        Returns:
            The translated text
        
        Raises:
            ValueError: If no API keys are available or if the translation fails after max retries
        """
        api_keys = self.get_api_keys()
        if not api_keys:
            raise ValueError("No API keys available")
        
        # If we have keys, use the one at the current index
        if len(api_keys) > 0:
            # Get the key at the current index
            api_key = api_keys[self._current_key_index]
            
            # Update the index for the next request (cycle back to 0 if needed)
            self._current_key_index = (self._current_key_index + 1) % len(api_keys)
            
            print(f"Using Groq API key {self._current_key_index + 1} of {len(api_keys)}")
        else:
            # This shouldn't happen since we check if api_keys is empty above
            api_key = api_keys[0]
        
        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Extract target language from the prompt
        target_language = "English"  # Default
        match = re.search(r"Translate the following .* to ([^.]+)\.", text)
        if match:
            target_language = match.group(1).strip()
        
        # Set up the payload for the API request
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a subtitle translator assistant. Translate the given SRT subtitles to {target_language}, preserving all numbers, timecodes, and formatting exactly as they appear. Only translate the text content."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        # Track this key as in use
        self._update_key_status(api_key, False)
        
        # Implement retry logic for rate limit errors
        attempt = 0
        while attempt < self.max_retries:
            try:
                # Make the request to the Groq API
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )
                
                # Parse the response
                response_json = response.json()
                
                # Check for errors
                if response.status_code != 200:
                    error_message = response_json.get("error", {}).get("message", "Unknown error")
                    
                    # Check if it's a rate limit error
                    if self._is_rate_limit_error(error_message):
                        # Handle rate limit error
                        await self._handle_rate_limit(error_message, attempt, status_callback)
                        # Increment attempt counter and try again
                        attempt += 1
                        continue
                    else:
                        # Not a rate limit error, just raise it
                        raise ValueError(f"Groq API error: {error_message}")
                
                # Success! Extract the translated text
                translated_text = response_json["choices"][0]["message"]["content"]
                
                # Mark the key as available again with no cooldown
                self._update_key_status(api_key, True, 0.0)
                
                return translated_text
                
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
                    # Not a rate limit error, mark the key as available and raise
                    self._update_key_status(api_key, True, 0.0)
                    raise ValueError(f"Error during translation: {error_str}")
        
        # If we get here, we've exceeded max retries
        self._update_key_status(api_key, True, 0.0)
        raise ValueError(f"Max retries exceeded ({self.max_retries}) for rate limit. Please try again later.")
    
    def _update_key_status(self, key: str, is_available: bool, cooldown: float = 0.0) -> None:
        """Update the status of an API key."""
        current_time = time.time()
        self._key_statuses[key] = {
            "is_available": is_available,
            "last_used": current_time,
            "cooldown": 0.0,  # Always set cooldown to 0
            "available_at": current_time  # Key is always immediately available
        }
    
    def get_key_status(self, key: str) -> Optional[Dict[str, Any]]:
        """Get the current status of an API key."""
        if key not in self._key_statuses:
            return None
            
        # Return key as always available with no cooldown
        return {
            "is_available": True,
            "cooldown_remaining": 0.0
        } 
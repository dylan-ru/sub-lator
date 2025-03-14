import requests
import json
import time
from typing import List, Dict, Optional, Any
import os
from .groq_key_storage import GroqKeyStorage
import re

class GroqTranslationService:
    """Service for handling Groq API translations"""
    
    def __init__(self):
        self.key_storage = GroqKeyStorage()
        self._key_statuses = {}  # Track key statuses and cooldowns
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "whisper-large-v3-turbo"
        
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
    
    def translate(self, text: str, model: str) -> str:
        """Translate text using Groq API."""
        api_keys = self.get_api_keys()
        if not api_keys:
            raise ValueError("No API keys available")
            
        # Use the first available key
        api_key = api_keys[0]
        
        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Extract target language from the prompt
        target_language = "English"  # Default
        match = re.search(r"Translate the following SRT subtitles to ([^.]+)\.", text)
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
        
        try:
            # Make the request to the Groq API
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload
            )
            
            # Mark the key as available again with no cooldown
            self._update_key_status(api_key, True, 0.0)  # Changed from 1.0 to 0.0
            
            # Parse the response
            response_json = response.json()
            
            # Check for errors
            if response.status_code != 200:
                error_message = response_json.get("error", {}).get("message", "Unknown error")
                raise ValueError(f"Groq API error: {error_message}")
                
            # Extract the translated text
            translated_text = response_json["choices"][0]["message"]["content"]
            return translated_text
                
        except Exception as e:
            # Mark the key as available again with no cooldown
            self._update_key_status(api_key, True, 0.0)  # Changed from 5.0 to 0.0
            raise ValueError(f"Error during translation: {str(e)}")
    
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
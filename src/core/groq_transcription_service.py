import requests
import json
import os
import time
import re
from typing import List, Dict, Optional, Any
import tempfile
from .groq_key_storage import GroqKeyStorage

class GroqTranscriptionService:
    """Service for handling Groq API transcriptions"""
    
    def __init__(self):
        self.key_storage = GroqKeyStorage()
        self._key_statuses = {}  # Track key statuses and cooldowns
        self.base_url = "https://api.groq.com/openai/v1/audio/transcriptions"
        self.model = "whisper-large-v3-turbo"  # Default transcription model
        
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
    
    def get_transcription_model(self) -> str:
        """Get the transcription model being used."""
        return self.model
        
    def transcribe(self, audio_file_path: str) -> str:
        """Transcribe audio file to text using Groq API."""
        api_keys = self.get_api_keys()
        if not api_keys:
            raise ValueError("No API keys available")
            
        # Use the first available key
        api_key = api_keys[0]
        
        # Check if file exists
        if not os.path.exists(audio_file_path):
            raise ValueError(f"File not found: {audio_file_path}")
        
        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        # Track this key as in use
        self._update_key_status(api_key, False)
        
        try:
            with open(audio_file_path, 'rb') as audio_file:
                # Create the form data
                files = {
                    'file': (os.path.basename(audio_file_path), audio_file, 'audio/mpeg')
                }
                data = {
                    'model': self.model,
                    'response_format': 'text'  # Request text format instead of SRT
                }
                
                # Make the request to the Groq API
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    files=files,
                    data=data
                )
            
            # Mark the key as available again with cooldown
            self._update_key_status(api_key, True, 1.0)  # 1 second cooldown
            
            # Check for errors
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", {}).get("message", "Unknown error")
                except:
                    error_message = f"HTTP error {response.status_code}"
                raise ValueError(f"Groq API error: {error_message}")
                
            # Get the plain text response
            plain_text = response.text
            
            # Convert the plain text to SRT format
            srt_content = self._convert_text_to_srt(plain_text)
            
            # Return the transcription in SRT format
            return srt_content
                
        except Exception as e:
            # Mark the key as available again but with a longer cooldown due to error
            self._update_key_status(api_key, True, 5.0)  # 5 second cooldown after error
            raise ValueError(f"Error during transcription: {str(e)}")
    
    def _convert_text_to_srt(self, text: str) -> str:
        """Convert plain text transcript to SRT format with estimated timestamps."""
        lines = text.strip().split('\n')
        srt_content = []
        
        # Estimate an average of 4 seconds per line
        seconds_per_line = 4
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            # Calculate start and end time
            start_seconds = i * seconds_per_line
            end_seconds = (i + 1) * seconds_per_line
            
            # Format timestamps - SRT format: HH:MM:SS,mmm
            start_time = self._format_timestamp(start_seconds)
            end_time = self._format_timestamp(end_seconds)
            
            # Add entry to SRT content
            srt_content.append(f"{i+1}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(line)
            srt_content.append("")  # Empty line between entries
        
        return "\n".join(srt_content)
    
    def _format_timestamp(self, seconds: int) -> str:
        """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        millisecs = 0  # We don't have millisecond precision in our estimate
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _update_key_status(self, key: str, is_available: bool, cooldown: float = 0.0) -> None:
        """Update the status of an API key."""
        current_time = time.time()
        self._key_statuses[key] = {
            "is_available": is_available,
            "last_used": current_time,
            "cooldown": cooldown,
            "available_at": current_time + cooldown
        }
    
    def get_key_status(self, key: str) -> Optional[Dict[str, Any]]:
        """Get the current status of an API key."""
        if key not in self._key_statuses:
            return None
            
        status = self._key_statuses[key]
        current_time = time.time()
        
        # Calculate remaining cooldown
        if status["available_at"] > current_time:
            cooldown_remaining = status["available_at"] - current_time
            is_available = False
        else:
            cooldown_remaining = 0.0
            is_available = True
            
        return {
            "is_available": is_available,
            "cooldown_remaining": cooldown_remaining
        } 
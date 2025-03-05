from abc import ABC, abstractmethod
from typing import List, Optional, Dict

class ApiProvider(ABC):
    """Interface for API key providers following Interface Segregation Principle"""
    
    @abstractmethod
    def get_name(self) -> str:
        """Get the name of the provider"""
        pass
    
    @abstractmethod
    def get_keys(self) -> List[str]:
        """Get all API keys for this provider"""
        pass
    
    @abstractmethod
    def add_key(self, key: str) -> None:
        """Add an API key for this provider"""
        pass
    
    @abstractmethod
    def remove_key(self, key: str) -> None:
        """Remove an API key from this provider"""
        pass
    
    @abstractmethod
    def remove_all_keys(self) -> None:
        """Remove all API keys from this provider"""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get all available models for this provider"""
        pass
        
    @abstractmethod
    def get_api_key(self) -> Optional[str]:
        """Get the current API key (first one if multiple exist)"""
        pass
        
    @abstractmethod
    def set_api_key(self, key: str) -> None:
        """Set a single API key (replacing any existing ones)"""
        pass
        
    @abstractmethod
    def clear_api_key(self) -> None:
        """Clear the current API key"""
        pass


class OpenRouterProvider(ApiProvider):
    """OpenRouter API provider implementation"""
    
    def __init__(self):
        from .key_storage import KeyStorage
        self.key_storage = KeyStorage()
        
    def get_name(self) -> str:
        return "OpenRouter"
    
    def get_keys(self) -> List[str]:
        return self.key_storage.get_keys()
    
    def add_key(self, key: str) -> None:
        self.key_storage.add_key(key)
    
    def remove_key(self, key: str) -> None:
        self.key_storage.remove_key(key)
    
    def remove_all_keys(self) -> None:
        self.key_storage.remove_all_keys()
    
    def get_available_models(self) -> List[str]:
        return [
            "openai/gpt-3.5-turbo",
            "openai/gpt-4",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet",
            "meta-llama/llama-3-70b-instruct",
            "google/gemini-pro"
        ]
    
    def get_api_key(self) -> Optional[str]:
        """Get the current API key (first one if multiple exist)"""
        keys = self.get_keys()
        return keys[0] if keys else None
        
    def set_api_key(self, key: str) -> None:
        """Set a single API key (replacing any existing ones)"""
        self.remove_all_keys()
        self.add_key(key)
        
    def clear_api_key(self) -> None:
        """Clear the current API key"""
        self.remove_all_keys()


class GroqProvider(ApiProvider):
    """Groq API provider implementation"""
    
    def __init__(self):
        from .groq_key_storage import GroqKeyStorage
        self.key_storage = GroqKeyStorage()
    
    def get_name(self) -> str:
        return "Groq"
    
    def get_keys(self) -> List[str]:
        return self.key_storage.get_keys()
    
    def add_key(self, key: str) -> None:
        self.key_storage.add_key(key)
    
    def remove_key(self, key: str) -> None:
        self.key_storage.remove_key(key)
    
    def remove_all_keys(self) -> None:
        self.key_storage.remove_all_keys()
    
    def get_available_models(self) -> List[str]:
        return [
            "llama-3.3-70b-versatile",
            "llama-guard-3-8b",
            "llama-3.1-8b-instant"
        ]
    
    def get_api_key(self) -> Optional[str]:
        """Get the current API key (first one if multiple exist)"""
        keys = self.get_keys()
        return keys[0] if keys else None
        
    def set_api_key(self, key: str) -> None:
        """Set a single API key (replacing any existing ones)"""
        self.remove_all_keys()
        self.add_key(key)
        
    def clear_api_key(self) -> None:
        """Clear the current API key"""
        self.remove_all_keys()


class AssemblyAIProvider(ApiProvider):
    """AssemblyAI API provider implementation"""
    
    def __init__(self):
        from .assembly_key_storage import AssemblyKeyStorage
        self.key_storage = AssemblyKeyStorage()
    
    def get_name(self) -> str:
        return "AssemblyAI"
    
    def get_keys(self) -> List[str]:
        return self.key_storage.get_keys()
    
    def add_key(self, key: str) -> None:
        self.key_storage.add_key(key)
    
    def remove_key(self, key: str) -> None:
        self.key_storage.remove_key(key)
    
    def remove_all_keys(self) -> None:
        self.key_storage.remove_all_keys()
    
    def get_available_models(self) -> List[str]:
        # AssemblyAI doesn't have model selection in the current implementation
        return ["default"]
    
    def get_api_key(self) -> Optional[str]:
        """Get the current API key (first one if multiple exist)"""
        keys = self.get_keys()
        return keys[0] if keys else None
        
    def set_api_key(self, key: str) -> None:
        """Set a single API key (replacing any existing ones)"""
        self.remove_all_keys()
        self.add_key(key)
        
    def clear_api_key(self) -> None:
        """Clear the current API key"""
        self.remove_all_keys()


class ApiProviderFactory:
    """Factory for creating API providers (Factory Method Pattern)"""
    
    @staticmethod
    def get_provider(provider_name: str) -> ApiProvider:
        """Get an API provider by name"""
        if provider_name == "OpenRouter":
            return OpenRouterProvider()
        elif provider_name == "Groq":
            return GroqProvider()
        elif provider_name == "AssemblyAI":
            return AssemblyAIProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """Get a list of available provider names"""
        return ["OpenRouter", "Groq", "AssemblyAI"] 
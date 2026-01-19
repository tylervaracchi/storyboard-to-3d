# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
AI Settings Manager
Handles configuration for AI providers (API keys, preferences, etc.)
"""

import json
import unreal
from pathlib import Path
from typing import Dict, Optional


class AISettings:
    """Manages AI provider settings and configuration"""

    def __init__(self):
        # Settings file location
        content_dir = Path(unreal.Paths.project_content_dir())
        self.settings_dir = content_dir / "StoryboardTo3D" / "Config"
        self.settings_file = self.settings_dir / "ai_settings.json"

        # Default settings
        self.default_settings = {
            'provider': 'auto',  # 'auto', 'llava', 'gpt4v', or 'claude'
            'llava': {
                'enabled': True,
                'url': 'http://localhost:11434',
                'model': 'llava:latest'
            },
            'gpt4v': {
                'enabled': True,
                'api_key': '',
                'model': 'gpt-4o'
            },
            'claude': {
                'enabled': True,
                'api_key': '',
                'model': 'claude-3-5-sonnet-20241022'
            },
            'cost_limits': {
                'max_per_panel': 0.50,
                'max_per_project': 50.00,
                'warn_at': 10.00
            },
            'auto_selection': {
                'prefer_accuracy': True,
                'budget_per_analysis': 0.05
            }
        }

        # Load settings
        self.settings = self.load_settings()

    def load_settings(self) -> Dict:
        """Load settings from file, or create defaults"""

        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)

                    # Merge with defaults (in case new settings added)
                    settings = self.default_settings.copy()
                    self._deep_update(settings, loaded)

                    unreal.log(f"[AI Settings] Loaded from: {self.settings_file}")
                    return settings

            except Exception as e:
                unreal.log_error(f"[AI Settings] Failed to load: {e}")
                return self.default_settings.copy()

        else:
            # Create default settings file
            unreal.log("[AI Settings] Creating default settings")
            self.save_settings(self.default_settings)
            return self.default_settings.copy()

    def _deep_update(self, base_dict, update_dict):
        """Deep update dictionary"""
        for key, value in update_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value

    def save_settings(self, settings: Dict = None):
        """Save settings to file"""

        if settings is None:
            settings = self.settings

        # Ensure directory exists
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)

            unreal.log(f"[AI Settings] Saved to: {self.settings_file}")

        except Exception as e:
            unreal.log_error(f"[AI Settings] Failed to save: {e}")

    def get(self, key: str, default=None):
        """Get a setting value"""
        keys = key.split('.')
        value = self.settings

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value):
        """Set a setting value"""
        keys = key.split('.')
        current = self.settings

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        self.save_settings()

    def get_provider(self) -> str:
        """Get selected provider ('auto', 'llava', 'gpt4v', or 'claude')"""
        return self.get('provider', 'auto')

    def set_provider(self, provider: str):
        """Set selected provider"""
        if provider not in ['auto', 'llava', 'gpt4v', 'claude']:
            raise ValueError(f"Invalid provider: {provider}")

        self.set('provider', provider)
        unreal.log(f"[AI Settings] Provider set to: {provider}")

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for provider"""
        if provider == 'gpt4v':
            return self.get('gpt4v.api_key', '')
        elif provider == 'claude':
            return self.get('claude.api_key', '')
        return None

    def set_api_key(self, provider: str, api_key: str):
        """Set API key for provider"""
        if provider == 'gpt4v':
            self.set('gpt4v.api_key', api_key)
        elif provider == 'claude':
            self.set('claude.api_key', api_key)

        unreal.log(f"[AI Settings] API key updated for {provider}")

    def get_provider_config(self, provider: str) -> Dict:
        """Get full config for a provider"""
        if provider == 'llava':
            return {
                'url': self.get('llava.url', 'http://localhost:11434'),
                'model': self.get('llava.model', 'llava:latest')
            }
        elif provider == 'gpt4v':
            return {
                'api_key': self.get('gpt4v.api_key', ''),
                'model': self.get('gpt4v.model', 'gpt-4o')
            }
        elif provider == 'claude':
            return {
                'api_key': self.get('claude.api_key', ''),
                'model': self.get('claude.model', 'claude-3-5-sonnet-20241022')
            }
        return {}

    def get_all_provider_configs(self) -> Dict:
        """Get config for all providers (for factory)"""
        return {
            'openai_api_key': self.get('gpt4v.api_key', ''),
            'anthropic_api_key': self.get('claude.api_key', ''),
            'ollama_url': self.get('llava.url', 'http://localhost:11434')
        }

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if provider is enabled"""
        return self.get(f'{provider}.enabled', True)

    def set_provider_enabled(self, provider: str, enabled: bool):
        """Enable/disable a provider"""
        self.set(f'{provider}.enabled', enabled)

    def get_cost_limit(self, limit_type: str) -> float:
        """Get cost limit (max_per_panel, max_per_project, warn_at)"""
        return self.get(f'cost_limits.{limit_type}', 0.50)

    def set_cost_limit(self, limit_type: str, value: float):
        """Set cost limit"""
        self.set(f'cost_limits.{limit_type}', value)

    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        self.settings = self.default_settings.copy()
        self.save_settings()
        unreal.log("[AI Settings] Reset to defaults")

    def export_settings(self, filepath: str):
        """Export settings to a file (for backup/sharing)"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.settings, f, indent=2)
            unreal.log(f"[AI Settings] Exported to: {filepath}")
            return True
        except Exception as e:
            unreal.log_error(f"[AI Settings] Export failed: {e}")
            return False

    def import_settings(self, filepath: str):
        """Import settings from a file"""
        try:
            with open(filepath, 'r') as f:
                self.settings = json.load(f)
            self.save_settings()
            unreal.log(f"[AI Settings] Imported from: {filepath}")
            return True
        except Exception as e:
            unreal.log_error(f"[AI Settings] Import failed: {e}")
            return False


# Global instance
_ai_settings_instance = None

def get_ai_settings() -> AISettings:
    """Get global AI settings instance"""
    global _ai_settings_instance
    if _ai_settings_instance is None:
        _ai_settings_instance = AISettings()
    return _ai_settings_instance

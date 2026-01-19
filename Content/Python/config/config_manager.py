# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Configuration Management System
Centralized settings and environment management
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

class Config:
    """Configuration manager with environment variable support"""

    # Default configuration
    DEFAULTS = {
        # API Settings
        "api": {
            "provider": "OpenAI GPT-4 Vision",  # OpenAI GPT-4 Vision, Claude 3.5 Sonnet, etc.
            "timeout": 30,
            "max_retries": 3,
            "max_tokens": 500
        },

        # UI Settings
        "ui": {
            "theme": "dark",
            "window_width": 1800,
            "window_height": 900,
            "auto_save": True,
            "auto_save_interval": 300,  # seconds
            "show_tooltips": True,
            "confirm_delete": True
        },

        # Generation Settings
        "generation": {
            "default_panel_duration": 3.0,
            "default_shot_scale": 1.0,
            "auto_analyze_panels": False,
            "create_cameras": True,
            "create_lights": True,
            "use_hdri": True,
            "hdri_path": "/Game/HDRI/Default_HDRI"
        },

        # Project Settings
        "project": {
            "content_root": "/Game/StoryboardTo3D",
            "shows_folder": "Shows",
            "auto_sync_content_browser": True,
            "sync_interval": 5,  # seconds
            "backup_on_save": True,
            "max_backups": 5
        },

        # Asset Library Settings
        "asset_library": {
            "auto_scan_on_startup": False,
            "scan_paths": [
                "/Game/Characters",
                "/Game/Props",
                "/Game/Environments"
            ],
            "default_character_type": "SkeletalMesh",
            "default_prop_type": "StaticMesh",
            "default_location_type": "World"
        },

        # Developer Settings
        "developer": {
            "debug_mode": False,
            "verbose_logging": False,
            "show_performance_stats": False,
            "enable_experimental_features": False
        }
    }

    def __init__(self):
        """Initialize configuration manager"""
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "settings.json"
        self.env_file = self.config_dir / ".env"
        self.config = self.load_config()
        self._load_environment()

    def _get_config_dir(self) -> Path:
        """Get configuration directory"""
        # Try multiple locations in order of preference
        locations = [
            Path.home() / ".storyboard_to_3d",  # User home
            Path(__file__).parent.parent / "config",  # Project config folder
            Path.cwd() / "config"  # Current directory
        ]

        for location in locations:
            if location.exists() or not location.exists():
                location.mkdir(parents=True, exist_ok=True)
                return location

        return locations[0]

    def _load_environment(self):
        """Load environment variables from .env file"""
        if self.env_file.exists():
            try:
                with open(self.env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip().strip('"').strip("'")
            except Exception as e:
                print(f"Warning: Could not load .env file: {e}")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    return self._deep_merge(self.DEFAULTS.copy(), loaded)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")

        # Create default config
        self.save_config(self.DEFAULTS)
        return self.DEFAULTS.copy()

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file"""
        if config is None:
            config = self.config

        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support"""
        # Support dot notation like "api.provider"
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any, save: bool = True) -> bool:
        """Set configuration value with dot notation support"""
        keys = key.split('.')
        config = self.config

        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the value
        config[keys[-1]] = value

        # Save if requested
        if save:
            return self.save_config()

        return True

    def get_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        """Get API key from environment variables"""
        if provider is None:
            provider = self.get("api.provider", "OpenAI GPT-4 Vision")

        # Map provider to environment variable name
        env_vars = {
            "OpenAI GPT-4 Vision": "OPENAI_API_KEY",
            "OpenAI GPT-4o": "OPENAI_API_KEY",
            "Claude 3.5 Sonnet": "ANTHROPIC_API_KEY",
            "Claude 3 Opus": "ANTHROPIC_API_KEY"
        }

        env_var = env_vars.get(provider, "API_KEY")

        # Try to get from environment
        api_key = os.environ.get(env_var)

        # Fallback to generic API_KEY
        if not api_key:
            api_key = os.environ.get("API_KEY")

        # Try config file (less secure, but convenient for development)
        if not api_key:
            api_key = self.get(f"api.keys.{provider.lower().replace(' ', '_')}")

        return api_key

    def set_api_key(self, provider: str, key: str) -> bool:
        """Set API key in environment (temporary) or .env file (permanent)"""
        # Map provider to environment variable name
        env_vars = {
            "OpenAI GPT-4 Vision": "OPENAI_API_KEY",
            "OpenAI GPT-4o": "OPENAI_API_KEY",
            "Claude 3.5 Sonnet": "ANTHROPIC_API_KEY",
            "Claude 3 Opus": "ANTHROPIC_API_KEY"
        }

        env_var = env_vars.get(provider, "API_KEY")

        # Set in current environment
        os.environ[env_var] = key

        # Save to .env file for persistence
        try:
            env_lines = []
            found = False

            if self.env_file.exists():
                with open(self.env_file, 'r') as f:
                    for line in f:
                        if line.strip().startswith(f"{env_var}="):
                            env_lines.append(f"{env_var}={key}\n")
                            found = True
                        else:
                            env_lines.append(line)

            if not found:
                env_lines.append(f"{env_var}={key}\n")

            with open(self.env_file, 'w') as f:
                f.writelines(env_lines)

            return True
        except Exception as e:
            print(f"Error saving API key: {e}")
            return False

    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def reset_to_defaults(self, section: Optional[str] = None):
        """Reset configuration to defaults"""
        if section:
            if section in self.DEFAULTS:
                self.config[section] = self.DEFAULTS[section].copy()
        else:
            self.config = self.DEFAULTS.copy()

        self.save_config()

    def export_config(self, file_path: str) -> bool:
        """Export configuration to file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error exporting config: {e}")
            return False

    def import_config(self, file_path: str) -> bool:
        """Import configuration from file"""
        try:
            with open(file_path, 'r') as f:
                imported = json.load(f)
                self.config = self._deep_merge(self.DEFAULTS.copy(), imported)
                self.save_config()
            return True
        except Exception as e:
            print(f"Error importing config: {e}")
            return False


# Global config instance
_config_instance = None

def get_config() -> Config:
    """Get global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

# Convenience functions
def get(key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return get_config().get(key, default)

def set(key: str, value: Any, save: bool = True) -> bool:
    """Set configuration value"""
    return get_config().set(key, value, save)

def get_api_key(provider: Optional[str] = None) -> Optional[str]:
    """Get API key for provider"""
    return get_config().get_api_key(provider)

def set_api_key(provider: str, key: str) -> bool:
    """Set API key for provider"""
    return get_config().set_api_key(provider, key)

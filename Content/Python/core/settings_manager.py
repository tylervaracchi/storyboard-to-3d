# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Enhanced Settings Manager - Comprehensive persistence system
Handles all settings: global, show, episode, and panel-level
"""

import unreal
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class SettingsManager:
    """Comprehensive settings management with auto-save"""

    # Settings version for migration support
    SETTINGS_VERSION = "2.0"

    def __init__(self):
        # Get paths
        self.content_dir = Path(unreal.Paths.project_content_dir())
        self.plugin_dir = self.content_dir / "StoryboardTo3D"
        self.settings_dir = self.plugin_dir / "Settings"

        # Ensure directories exist
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        # Settings files
        self.global_settings_file = self.settings_dir / "global_settings.json"
        self.recent_projects_file = self.settings_dir / "recent_projects.json"
        self.ui_state_file = self.settings_dir / "ui_state.json"

        # Load settings
        self.global_settings = self.load_global_settings()
        self.recent_projects = self.load_recent_projects()
        self.ui_state = self.load_ui_state()

        # Cache for panel settings
        self.panel_settings_cache = {}

        # Auto-save flag
        self.auto_save_enabled = self.global_settings.get('auto_save', True)

    # ========================================
    # GLOBAL SETTINGS
    # ========================================

    def load_global_settings(self) -> Dict[str, Any]:
        """Load global application settings"""
        if self.global_settings_file.exists():
            try:
                with open(self.global_settings_file, 'r') as f:
                    settings = json.load(f)
                    # Migrate if needed
                    if settings.get('version') != self.SETTINGS_VERSION:
                        settings = self.migrate_settings(settings)
                    return settings
            except Exception as e:
                unreal.log_warning(f"Failed to load global settings: {e}")

        # Return defaults
        return self.get_default_global_settings()

    def get_default_global_settings(self) -> Dict[str, Any]:
        """Get default global settings"""
        return {
            'version': self.SETTINGS_VERSION,
            'auto_save': True,
            'auto_save_interval': 60,  # seconds
            'backup_enabled': True,
            'max_backups': 10,

            # AI Settings
            'ai': {
                'provider': 'none',  # 'openai', 'claude', 'none'
                'openai_api_key': '',
                'claude_api_key': '',
                'model': 'gpt-4-vision-preview',
                'max_tokens': 500,
                'temperature': 0.7,
                'enable_caching': True,
                'cache_duration': 86400  # 24 hours
            },

            # Ollama Settings (for local AI)
            'ollama': {
                'server_url': 'http://localhost:11434',
                'auto_start': True,
                'default_text_model': 'llama3.2',
                'default_vision_model': 'llava',
                'context_length': 4096,
                'gpu_layers': 0,
                'keep_loaded': False,
                'parallel_requests': 1,
                'request_timeout': 60,
                'use_streaming': True
            },

            # AI Settings (general)
            'ai_settings': {
                'provider': 'Ollama (Local)',
                'api_key': '',
                'endpoint': '',
                'text_model': 'llama3.2',
                'vision_model': 'llava',
                'temperature': 0.7,
                'max_tokens': 2000,
                'auto_analyze': True,
                'batch_analysis': True,
                'batch_size': 5,
                'timeout': 30,
                'retry_on_failure': True,
                'max_retries': 3,
                'use_optimized_prompts': True  # Enable 50-66% token reduction (Optimization #4)
            },

            # Default Panel Settings
            'panel_defaults': {
                'duration': 3.0,
                'transition_duration': 0.5,
                'shot_type': 'auto',
                'camera_height': 160.0,
                'camera_fov': 90.0,
                'enable_auto_framing': True,
                'enable_depth_of_field': False,
                'enable_motion_blur': False
            },

            # Scene Generation Settings
            'scene': {
                'clear_before_build': True,
                'build_location': [0, 0, 0],
                'spacing_between_scenes': 2000,
                'default_lighting': 'three_point',
                'default_time_of_day': 'day',
                'default_mood': 'neutral',
                'use_hdri': False,
                'hdri_path': '',
                'enable_shadows': True,
                'shadow_quality': 'medium'
            },

            # Sequence Settings
            'sequence': {
                'fps': 30,
                'resolution': [1920, 1080],
                'output_format': 'mp4',
                'codec': 'h264',
                'quality': 'high',
                'enable_audio': False,
                'master_sequence_name': 'Master_Sequence',
                'auto_create_camera_cuts': True
            },

            # Asset Library Settings
            'assets': {
                'auto_scan_on_startup': False,
                'scan_paths': ['/Game'],
                'exclude_paths': ['/Engine'],
                'cache_results': True,
                'use_smart_matching': True,
                'matching_threshold': 0.7
            },

            # UI Preferences
            'ui': {
                'theme': 'dark',
                'window_opacity': 1.0,
                'show_tooltips': True,
                'confirm_deletions': True,
                'remember_layout': True,
                'panel_thumbnail_size': 120,
                'auto_collapse_sections': False,
                'show_advanced_options': False
            },

            # Performance Settings
            'performance': {
                'max_concurrent_operations': 4,
                'enable_gpu_acceleration': True,
                'texture_streaming_pool_size': 1000,
                'max_undo_history': 50,
                'enable_async_loading': True
            },

            # File Management
            'files': {
                'auto_organize': True,
                'naming_convention': 'sequential',  # 'sequential', 'timestamp', 'custom'
                'custom_naming_pattern': 'Panel_{index:03d}',
                'keep_original_names': False,
                'compress_images': False,
                'compression_quality': 85
            },

            # Paths
            'paths': {
                'default_import_path': '',
                'default_export_path': '',
                'custom_asset_paths': []
            },

            # last modified
            'last_modified': datetime.now().isoformat()
        }

    def save_global_settings(self):
        """Save global settings to disk"""
        try:
            self.global_settings['last_modified'] = datetime.now().isoformat()

            # Create backup if enabled
            if self.global_settings.get('backup_enabled', True):
                self.backup_settings()

            # Save settings
            with open(self.global_settings_file, 'w') as f:
                json.dump(self.global_settings, f, indent=2)

            unreal.log(f"Global settings saved")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save global settings: {e}")
            return False

    # Compatibility methods for test scripts
    def save(self, settings: Dict[str, Any] = None):
        """Save settings (compatibility wrapper)"""
        if settings:
            self.global_settings.update(settings)
        return self.save_global_settings()

    def load(self) -> Dict[str, Any]:
        """Load settings (compatibility wrapper)"""
        return self.global_settings

    @property
    def settings_file(self):
        """Settings file path (compatibility property)"""
        return self.global_settings_file

    def get_default_settings(self) -> Dict[str, Any]:
        """Get default settings (compatibility wrapper)"""
        return self.get_default_global_settings()

    def get_setting(self, path: str, default=None):
        """Get a setting by dot-notation path (e.g., 'ai.provider')"""
        keys = path.split('.')
        value = self.global_settings

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default

        return value

    def set_setting(self, path: str, value: Any):
        """Set a setting by dot-notation path"""
        keys = path.split('.')
        settings = self.global_settings

        # Navigate to the parent
        for key in keys[:-1]:
            if key not in settings:
                settings[key] = {}
            settings = settings[key]

        # Set the value
        settings[keys[-1]] = value

        # Auto-save if enabled
        if self.auto_save_enabled:
            self.save_global_settings()

    # ========================================
    # SHOW SETTINGS
    # ========================================

    def get_show_settings_path(self, show_name: str) -> Path:
        """Get path to show settings file"""
        show_dir = self.plugin_dir / "Shows" / show_name
        return show_dir / "show_settings.json"

    def load_show_settings(self, show_name: str) -> Dict[str, Any]:
        """Load settings for a specific show"""
        settings_file = self.get_show_settings_path(show_name)

        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                unreal.log_warning(f"Failed to load show settings: {e}")

        # Return defaults
        return self.get_default_show_settings(show_name)

    def get_default_show_settings(self, show_name: str) -> Dict[str, Any]:
        """Get default settings for a show"""
        return {
            'name': show_name,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),

            # Show-specific overrides
            'panel_defaults': {
                'duration': 3.0,
                'transition_duration': 0.5
            },

            # Asset library for this show
            'asset_library': {
                'characters': {},
                'props': {},
                'locations': {},
                'custom_mappings': {}
            },

            # Show metadata
            'metadata': {
                'description': '',
                'genre': '',
                'target_audience': '',
                'notes': ''
            },

            # Export settings for this show
            'export': {
                'include_sources': True,
                'include_sequences': True,
                'compress': False
            }
        }

    def save_show_settings(self, show_name: str, settings: Dict[str, Any]):
        """Save show settings"""
        settings_file = self.get_show_settings_path(show_name)
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            settings['modified'] = datetime.now().isoformat()
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            unreal.log(f"Show settings saved: {show_name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save show settings: {e}")
            return False

    # ========================================
    # EPISODE SETTINGS
    # ========================================

    def get_episode_settings_path(self, show_name: str, episode_name: str) -> Path:
        """Get path to episode settings file"""
        episode_dir = self.plugin_dir / "Shows" / show_name / "Episodes" / episode_name
        return episode_dir / "episode_settings.json"

    def load_episode_settings(self, show_name: str, episode_name: str) -> Dict[str, Any]:
        """Load settings for a specific episode"""
        settings_file = self.get_episode_settings_path(show_name, episode_name)

        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                unreal.log_warning(f"Failed to load episode settings: {e}")

        return self.get_default_episode_settings(episode_name)

    def get_default_episode_settings(self, episode_name: str) -> Dict[str, Any]:
        """Get default settings for an episode"""
        return {
            'name': episode_name,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),

            # Episode-specific settings
            'duration_override': None,  # Override global panel duration
            'scene_settings': {},
            'sequence_settings': {},

            # Episode metadata
            'metadata': {
                'episode_number': 0,
                'title': '',
                'description': '',
                'script_file': '',
                'notes': ''
            }
        }

    def save_episode_settings(self, show_name: str, episode_name: str, settings: Dict[str, Any]):
        """Save episode settings"""
        settings_file = self.get_episode_settings_path(show_name, episode_name)
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            settings['modified'] = datetime.now().isoformat()
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            unreal.log(f"Episode settings saved: {episode_name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save episode settings: {e}")
            return False

    # ========================================
    # PANEL SETTINGS
    # ========================================

    def get_panel_settings_path(self, show_name: str, episode_name: str) -> Path:
        """Get path to panel settings file"""
        episode_dir = self.plugin_dir / "Shows" / show_name / "Episodes" / episode_name
        return episode_dir / "panel_settings.json"

    def load_panel_settings(self, show_name: str, episode_name: str, panel_name: str) -> Dict[str, Any]:
        """Load settings for a specific panel"""
        # Check cache first
        cache_key = f"{show_name}:{episode_name}:{panel_name}"
        if cache_key in self.panel_settings_cache:
            return self.panel_settings_cache[cache_key]

        # Load from file
        settings_file = self.get_panel_settings_path(show_name, episode_name)

        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    all_panels = json.load(f)
                    if panel_name in all_panels:
                        settings = all_panels[panel_name]
                        self.panel_settings_cache[cache_key] = settings
                        return settings
            except Exception as e:
                unreal.log_warning(f"Failed to load panel settings: {e}")

        # Return defaults
        default = self.get_default_panel_settings(panel_name)
        self.panel_settings_cache[cache_key] = default
        return default

    def get_default_panel_settings(self, panel_name: str) -> Dict[str, Any]:
        """Get default settings for a panel"""
        return {
            'name': panel_name,
            'duration': 3.0,
            'transition_duration': 0.5,

            # Shot composition
            'shot': {
                'type': 'auto',  # auto, wide, medium, close, ecu, ots, pov
                'angle': 'eye_level',  # low, eye_level, high, birds_eye, worms_eye
                'movement': 'static',  # static, pan, tilt, dolly, crane, handheld
                'focus': 'auto'  # auto, foreground, midground, background
            },

            # Camera settings
            'camera': {
                'fov': 90.0,
                'focal_length': 50.0,
                'aperture': 2.8,
                'focus_distance': 500.0,
                'sensor_width': 36.0,
                'sensor_height': 24.0,
                'enable_dof': False,
                'enable_motion_blur': False
            },

            # Scene elements
            'elements': {
                'characters': [],
                'props': [],
                'location': 'auto',
                'environment': 'default'
            },

            # Lighting
            'lighting': {
                'setup': 'three_point',  # three_point, natural, studio, dramatic
                'key_intensity': 1.0,
                'fill_intensity': 0.5,
                'rim_intensity': 0.3,
                'ambient_intensity': 0.2,
                'time_of_day': 'day',
                'mood': 'neutral',
                'color_temperature': 6500
            },

            # Analysis results
            'analysis': {
                'analyzed': False,
                'analysis_date': None,
                'ai_provider': None,
                'detected_elements': {},
                'suggested_mood': None,
                'suggested_shot': None
            },

            # Generation status
            'generation': {
                'generated': False,
                'generation_date': None,
                'scene_path': None,
                'sequence_path': None,
                'errors': []
            },

            # Custom metadata
            'metadata': {
                'notes': '',
                'tags': [],
                'dialogue': '',
                'action': ''
            }
        }

    def save_panel_settings(self, show_name: str, episode_name: str, panel_name: str, settings: Dict[str, Any]):
        """Save settings for a specific panel"""
        settings_file = self.get_panel_settings_path(show_name, episode_name)
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing panel settings
        all_panels = {}
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    all_panels = json.load(f)
            except:
                pass

        # Update panel settings
        all_panels[panel_name] = settings

        # Update cache
        cache_key = f"{show_name}:{episode_name}:{panel_name}"
        self.panel_settings_cache[cache_key] = settings

        # Save to file
        try:
            with open(settings_file, 'w') as f:
                json.dump(all_panels, f, indent=2)

            if not self.auto_save_enabled:
                unreal.log(f"Panel settings saved: {panel_name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save panel settings: {e}")
            return False

    def save_all_panel_settings(self, show_name: str, episode_name: str, panels_settings: Dict[str, Dict[str, Any]]):
        """Save all panel settings at once (batch save)"""
        settings_file = self.get_panel_settings_path(show_name, episode_name)
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(settings_file, 'w') as f:
                json.dump(panels_settings, f, indent=2)

            # Update cache
            for panel_name, settings in panels_settings.items():
                cache_key = f"{show_name}:{episode_name}:{panel_name}"
                self.panel_settings_cache[cache_key] = settings

            unreal.log(f"All panel settings saved for episode: {episode_name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save panel settings: {e}")
            return False

    # ========================================
    # UI STATE PERSISTENCE
    # ========================================

    def load_ui_state(self) -> Dict[str, Any]:
        """Load UI state (window positions, sizes, etc.)"""
        if self.ui_state_file.exists():
            try:
                with open(self.ui_state_file, 'r') as f:
                    return json.load(f)
            except:
                pass

        return {
            'window_geometry': None,
            'window_state': None,
            'splitter_states': {},
            'expanded_sections': [],
            'last_show': None,
            'last_episode': None,
            'last_panel': None,
            'recent_imports': [],
            'column_widths': {}
        }

    def save_ui_state(self):
        """Save UI state"""
        try:
            with open(self.ui_state_file, 'w') as f:
                json.dump(self.ui_state, f, indent=2)
            return True
        except Exception as e:
            unreal.log_error(f"Failed to save UI state: {e}")
            return False

    # ========================================
    # RECENT PROJECTS
    # ========================================

    def load_recent_projects(self) -> list:
        """Load recent projects list"""
        if self.recent_projects_file.exists():
            try:
                with open(self.recent_projects_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def add_recent_project(self, show_name: str):
        """Add project to recent list"""
        # Remove if already exists
        self.recent_projects = [p for p in self.recent_projects if p['name'] != show_name]

        # Add to front
        self.recent_projects.insert(0, {
            'name': show_name,
            'last_opened': datetime.now().isoformat()
        })

        # Keep only last 10
        self.recent_projects = self.recent_projects[:10]

        # Save
        try:
            with open(self.recent_projects_file, 'w') as f:
                json.dump(self.recent_projects, f, indent=2)
        except:
            pass

    # ========================================
    # BACKUP & RESTORE
    # ========================================

    def backup_settings(self):
        """Create backup of all settings"""
        backup_dir = self.settings_dir / "backups"
        backup_dir.mkdir(exist_ok=True)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"settings_backup_{timestamp}.json"

        try:
            backup_data = {
                'version': self.SETTINGS_VERSION,
                'timestamp': datetime.now().isoformat(),
                'global_settings': self.global_settings,
                'recent_projects': self.recent_projects,
                'ui_state': self.ui_state
            }

            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)

            # Clean old backups
            self.clean_old_backups(backup_dir)

            unreal.log(f"Settings backed up: {backup_file.name}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to backup settings: {e}")
            return False

    def clean_old_backups(self, backup_dir: Path):
        """Keep only the most recent backups"""
        max_backups = self.global_settings.get('max_backups', 10)

        backups = sorted(backup_dir.glob("settings_backup_*.json"))
        if len(backups) > max_backups:
            for old_backup in backups[:-max_backups]:
                old_backup.unlink()

    def restore_settings(self, backup_file: str):
        """Restore settings from backup"""
        backup_path = self.settings_dir / "backups" / backup_file

        if not backup_path.exists():
            unreal.log_error(f"Backup file not found: {backup_file}")
            return False

        try:
            with open(backup_path, 'r') as f:
                backup_data = json.load(f)

            # Restore settings
            self.global_settings = backup_data.get('global_settings', {})
            self.recent_projects = backup_data.get('recent_projects', [])
            self.ui_state = backup_data.get('ui_state', {})

            # Save restored settings
            self.save_global_settings()
            self.save_ui_state()

            unreal.log(f"Settings restored from: {backup_file}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to restore settings: {e}")
            return False

    def list_backups(self) -> list:
        """List available backups"""
        backup_dir = self.settings_dir / "backups"
        if not backup_dir.exists():
            return []

        backups = []
        for backup_file in sorted(backup_dir.glob("settings_backup_*.json"), reverse=True):
            try:
                with open(backup_file, 'r') as f:
                    data = json.load(f)
                    backups.append({
                        'filename': backup_file.name,
                        'timestamp': data.get('timestamp', 'Unknown'),
                        'size': backup_file.stat().st_size
                    })
            except:
                pass

        return backups

    # ========================================
    # MIGRATION
    # ========================================

    def migrate_settings(self, old_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from old version to current"""
        unreal.log(f"Migrating settings from version {old_settings.get('version', '1.0')} to {self.SETTINGS_VERSION}")

        # Start with defaults
        new_settings = self.get_default_global_settings()

        # Migrate old values
        # This is where you'd add migration logic for each version
        if 'version' not in old_settings or old_settings['version'] == '1.0':
            # Migrate from 1.0 to 2.0
            if 'ai_api_key' in old_settings:
                new_settings['ai']['openai_api_key'] = old_settings['ai_api_key']
            if 'default_panel_duration' in old_settings:
                new_settings['panel_defaults']['duration'] = old_settings['default_panel_duration']

        # Preserve any custom settings that still exist
        for key in old_settings:
            if key in new_settings and key != 'version':
                if isinstance(new_settings[key], dict) and isinstance(old_settings[key], dict):
                    new_settings[key].update(old_settings[key])
                else:
                    new_settings[key] = old_settings[key]

        return new_settings

    # ========================================
    # EXPORT/IMPORT
    # ========================================

    def export_all_settings(self, export_path: str):
        """Export all settings to a file"""
        try:
            export_data = {
                'version': self.SETTINGS_VERSION,
                'exported': datetime.now().isoformat(),
                'global_settings': self.global_settings,
                'recent_projects': self.recent_projects,
                'ui_state': self.ui_state
            }

            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2)

            unreal.log(f"Settings exported to: {export_path}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to export settings: {e}")
            return False

    def import_settings(self, import_path: str):
        """Import settings from a file"""
        try:
            with open(import_path, 'r') as f:
                import_data = json.load(f)

            # Validate version
            if import_data.get('version') != self.SETTINGS_VERSION:
                import_data['global_settings'] = self.migrate_settings(import_data.get('global_settings', {}))

            # Import settings
            self.global_settings = import_data.get('global_settings', self.get_default_global_settings())
            self.recent_projects = import_data.get('recent_projects', [])
            self.ui_state = import_data.get('ui_state', {})

            # Save imported settings
            self.save_global_settings()
            self.save_ui_state()

            unreal.log(f"Settings imported from: {import_path}")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to import settings: {e}")
            return False


# Global instance
_settings_manager = None

def get_settings_manager() -> SettingsManager:
    """Get global settings manager instance"""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager

def get_settings() -> Dict[str, Any]:
    """Get global settings"""
    return get_settings_manager().global_settings

def get_setting(path: str, default=None):
    """Get a specific setting by path"""
    return get_settings_manager().get_setting(path, default)

def set_setting(path: str, value: Any):
    """Set a specific setting by path"""
    get_settings_manager().set_setting(path, value)

def save_settings():
    """Save all settings"""
    manager = get_settings_manager()
    manager.save_global_settings()
    manager.save_ui_state()

def update_settings(new_settings: Dict[str, Any]):
    """Update global settings with new values"""
    manager = get_settings_manager()
    manager.global_settings.update(new_settings)
    return manager.save_global_settings()

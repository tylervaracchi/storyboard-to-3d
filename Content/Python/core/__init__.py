# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Core functionality package - Scene building and sequence generation
Includes comprehensive settings management
"""

from .panel_analyzer import PanelAnalyzer
from .asset_matcher import AssetMatcher
from .scene_builder import SceneBuilder
from .sequence_generator import SequenceGenerator
from .shows_manager import ShowsManager
from .episodes_manager import EpisodesManager
from .settings_manager import (
    SettingsManager,
    get_settings_manager,
    get_settings,
    get_setting,
    set_setting,
    save_settings
)

__all__ = [
    'PanelAnalyzer',
    'AssetMatcher',
    'SceneBuilder',
    'SequenceGenerator',
    'ShowsManager',
    'EpisodesManager',
    'SettingsManager',
    'get_settings_manager',
    'get_settings',
    'get_setting',
    'set_setting',
    'save_settings'
]

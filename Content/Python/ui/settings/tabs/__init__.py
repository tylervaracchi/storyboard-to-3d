# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Settings tabs for StoryboardTo3D
"""

from .general_tab import GeneralTab
from .ai_tab import AISettingsTab
from .ollama_tab import OllamaSettingsTab
from .paths_tab import PathsTab
from .advanced_tab import AdvancedTab

__all__ = [
    'GeneralTab',
    'AISettingsTab',
    'OllamaSettingsTab',
    'PathsTab',
    'AdvancedTab'
]

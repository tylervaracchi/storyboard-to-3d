# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Core functionality package - Scene building and sequence generation
Includes comprehensive settings management

Submodule imports are lazy (PEP 562 module __getattr__) so that packages
with no editor dependency (e.g. core.gen3d) stay importable outside
Unreal: eager imports here would pull in modules that do a top-level
'import unreal' and break 'from core.gen3d import ...' in plain Python.
In-editor behavior is unchanged — 'from core import SceneBuilder' etc.
still work, and genuine import errors in a submodule still surface
loudly at first access.
"""

import importlib

# Public name -> submodule that provides it
_NAME_TO_MODULE = {
    'PanelAnalyzer': '.panel_analyzer',
    'AssetMatcher': '.asset_matcher',
    'SceneBuilder': '.scene_builder',
    'SequenceGenerator': '.sequence_generator',
    'ShowsManager': '.shows_manager',
    'EpisodesManager': '.episodes_manager',
    'SettingsManager': '.settings_manager',
    'get_settings_manager': '.settings_manager',
    'get_settings': '.settings_manager',
    'get_setting': '.settings_manager',
    'set_setting': '.settings_manager',
    'save_settings': '.settings_manager',
}

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


def __getattr__(name):
    """Lazily import the submodule that provides a public name (PEP 562)."""
    module_name = _NAME_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(
            "module {!r} has no attribute {!r}".format(__name__, name))
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache for subsequent lookups
    return value


def __dir__():
    return sorted(list(globals()) + __all__)

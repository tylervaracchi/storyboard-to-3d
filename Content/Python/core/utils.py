# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
CENTRAL UTILITIES FOR STORYBOARD TO 3D
Shared utilities to prevent code duplication
"""

import unreal
from pathlib import Path

# Singleton instances
_managers = {}

def get_shows_manager():
    """Get singleton ShowsManager instance"""
    if 'shows' not in _managers:
        from core.shows_manager import ShowsManager
        _managers['shows'] = ShowsManager()
    return _managers['shows']

def get_episodes_manager():
    """Get singleton EpisodesManager instance"""
    if 'episodes' not in _managers:
        from core.episodes_manager import EpisodesManager
        _managers['episodes'] = EpisodesManager()
    return _managers['episodes']

def sanitize_asset_data(data):
    """Convert any format to proper asset dict - SINGLE SOURCE OF TRUTH"""
    if data is None:
        return {
            "asset_path": "",
            "description": "",
            "aliases": [],
            "thumbnail": {"type": "none", "path": None}
        }

    if isinstance(data, str):
        # Legacy string format - convert to dict
        return {
            "asset_path": data,
            "description": "Converted from legacy format",
            "aliases": [],
            "thumbnail": {"type": "none", "path": None}
        }

    if isinstance(data, dict):
        # Ensure all required fields exist
        if "asset_path" not in data:
            data["asset_path"] = ""
        if "description" not in data:
            data["description"] = ""
        if "aliases" not in data:
            data["aliases"] = []
        if "thumbnail" not in data:
            data["thumbnail"] = {"type": "none", "path": None}
        elif not isinstance(data["thumbnail"], dict):
            data["thumbnail"] = {"type": "none", "path": None}

        return data

    # Unknown format
    unreal.log_warning(f"Unknown asset data format: {type(data)}")
    return {
        "asset_path": "",
        "description": f"Unknown data type: {type(data)}",
        "aliases": [],
        "thumbnail": {"type": "none", "path": None}
    }

def get_show_asset_library_path(show_name):
    """Get the asset library path for a show"""
    manager = get_shows_manager()
    return manager.shows_root / show_name / "asset_library.json"

def ensure_library_structure(library):
    """Ensure library has proper structure"""
    if not isinstance(library, dict):
        library = {}

    for category in ['characters', 'props', 'locations']:
        if category not in library:
            library[category] = {}

    return library

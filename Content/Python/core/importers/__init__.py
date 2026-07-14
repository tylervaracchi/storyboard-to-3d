# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Importers package - bulk panel import from external storyboard tools.

Currently supports:
    - Wonder Unit Storyboarder projects (.storyboarder file + images/ folder)
    - Flat image folders in natural-sort order (e.g. a ComfyUI output folder)

Both importers copy images into the target show/episode using the existing
ShowsManager/EpisodesManager patterns (see core/shows_manager.py and
core/episodes_manager.py) and therefore only run inside the Unreal Editor
Python environment.
"""

from .storyboarder_importer import import_storyboarder
from .image_folder_importer import import_image_folder, natural_key

__all__ = [
    'import_storyboarder',
    'import_image_folder',
    'natural_key',
]

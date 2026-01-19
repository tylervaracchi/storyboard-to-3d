# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.

"""
Asset Matcher Module

Matches object names from storyboard analysis to Unreal Engine assets.
Prioritizes show-specific asset libraries, then falls back to general project
assets and basic shapes.
"""

import unreal
import json
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, List


class AssetMatcher:
    """
    Matches object names to Unreal Engine assets with show-specific priority.
    
    The matching priority order is:
        1. Show-specific asset library (exact match, aliases, description)
        2. General project asset cache (exact match)
        3. Fuzzy matching in general cache
        4. Fallback to basic shapes
    
    Attributes:
        show_name: Name of the current show for library lookup.
        show_library: Loaded show-specific asset definitions.
        asset_cache: Cache of general project assets.
    
    Example:
        >>> matcher = AssetMatcher(show_name="MyShow")
        >>> asset = matcher.find_best_match("hero_character", category="characters")
    """

    def __init__(self, show_name: Optional[str] = None):
        """
        Initialize the asset matcher.
        
        Args:
            show_name: Optional show name to load show-specific asset library.
        """
        self.show_name = show_name
        self.show_library: Dict[str, Dict] = {}
        self.asset_cache: Dict[str, str] = {}

        if show_name:
            self.load_show_library(show_name)

        self.build_asset_cache()

    def load_show_library(self, show_name: str) -> None:
        """
        Load the show-specific asset library from disk.
        
        Args:
            show_name: Name of the show whose library to load.
        """
        from core.shows_manager import ShowsManager

        manager = ShowsManager()
        show_path = manager.shows_root / show_name
        library_path = show_path / "asset_library.json"

        if library_path.exists():
            try:
                with open(library_path, 'r') as f:
                    self.show_library = json.load(f)
                unreal.log(f"Loaded asset library for show: {show_name}")
            except (json.JSONDecodeError, IOError) as e:
                unreal.log_warning(f"Failed to load show library: {e}")
                self.show_library = {}
        else:
            unreal.log(f"No asset library found for show: {show_name}")
            self.show_library = {}

    def build_asset_cache(self) -> None:
        """
        Build cache of available assets from the project.
        
        Scans common asset paths and builds a lookup dictionary mapping
        lowercase asset names to their full paths.
        """
        unreal.log("Building asset cache...")

        asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

        search_paths = [
            '/Game',
            '/Engine/BasicShapes',
            '/Engine/VREditor/BasicMeshes',
            '/Engine/EditorMeshes'
        ]

        for path in search_paths:
            meshes = asset_registry.get_assets_by_path(path, recursive=True)

            for asset_data in meshes:
                if asset_data.asset_class_path.asset_name == 'StaticMesh':
                    asset_name = str(asset_data.asset_name)
                    asset_path = str(asset_data.get_full_name())
                    self.asset_cache[asset_name.lower()] = asset_path

        unreal.log(f"Asset cache built with {len(self.asset_cache)} general assets")

    def find_best_match(self, object_name: str, category: Optional[str] = None) -> Optional[Any]:
        """
        Find the best matching asset for an object name.
        
        Searches in priority order: show library, general cache, fuzzy match,
        then fallback shapes.
        
        Args:
            object_name: Name of the object to find an asset for.
            category: Optional category hint ('characters', 'props', 'locations').
                     If None, category is inferred from object_name keywords.
        
        Returns:
            Loaded Unreal asset object, or None if no match found.
        
        Example:
            >>> asset = matcher.find_best_match("wooden_chair", category="props")
        """
        object_name_lower = object_name.lower().strip()

        # PRIORITY 1: Show-specific library
        if self.show_library:
            if not category:
                category = self._infer_category(object_name_lower)

            asset = self._search_show_library(object_name_lower, category)
            if asset:
                return asset

        # PRIORITY 2: Exact match in general cache
        if object_name_lower in self.asset_cache:
            unreal.log(f"Matched '{object_name}' in general cache")
            return self.load_asset(self.asset_cache[object_name_lower])

        # PRIORITY 3: Fuzzy matching
        asset = self._fuzzy_match(object_name_lower)
        if asset:
            return asset

        # PRIORITY 4: Fallback shapes
        return self.get_fallback_asset(object_name)

    def _infer_category(self, object_name: str) -> str:
        """
        Infer asset category from object name keywords.
        
        Args:
            object_name: Lowercase object name to analyze.
        
        Returns:
            Category string: 'characters', 'locations', or 'props'.
        """
        if any(word in object_name for word in ['character', 'person', 'hero', 'villain']):
            return 'characters'
        elif any(word in object_name for word in ['location', 'scene', 'level', 'place']):
            return 'locations'
        return 'props'

    def _search_show_library(self, object_name: str, category: str) -> Optional[Any]:
        """
        Search show library for matching asset.
        
        Args:
            object_name: Lowercase object name to find.
            category: Category to search in.
        
        Returns:
            Loaded asset or None.
        """
        if category not in self.show_library:
            return None

        for asset_name, asset_data in self.show_library[category].items():
            # Exact match
            if asset_name.lower() == object_name:
                asset_path = asset_data.get('asset_path')
                if asset_path:
                    unreal.log(f"Matched '{object_name}' to show asset: {asset_name}")
                    return self.load_asset(asset_path)

            # Alias match
            aliases = asset_data.get('aliases', [])
            for alias in aliases:
                if alias.lower() == object_name or object_name in alias.lower():
                    asset_path = asset_data.get('asset_path')
                    if asset_path:
                        unreal.log(f"Matched '{object_name}' via alias to show asset: {asset_name}")
                        return self.load_asset(asset_path)

            # Description match
            description = asset_data.get('description', '').lower()
            if object_name in description:
                asset_path = asset_data.get('asset_path')
                if asset_path:
                    unreal.log(f"Matched '{object_name}' via description to show asset: {asset_name}")
                    return self.load_asset(asset_path)

        return None

    def _fuzzy_match(self, object_name: str) -> Optional[Any]:
        """
        Find asset using fuzzy string matching.
        
        Args:
            object_name: Lowercase object name to match.
        
        Returns:
            Best matching asset if score > 0.5, otherwise None.
        """
        best_match = None
        best_score = 0.0

        for asset_name, asset_path in self.asset_cache.items():
            score = SequenceMatcher(None, object_name, asset_name).ratio()

            # Bonus for substring match
            if object_name in asset_name:
                score += 0.3

            if score > best_score and score > 0.5:
                best_score = score
                best_match = asset_path

        if best_match:
            unreal.log(f"Fuzzy matched '{object_name}' with score {best_score:.2f}")
            return self.load_asset(best_match)

        return None

    def load_asset(self, asset_path: str) -> Optional[Any]:
        """
        Load an Unreal asset from its path.
        
        Args:
            asset_path: Full asset path, optionally with class prefix.
        
        Returns:
            Loaded asset object, or None if load fails.
        """
        try:
            # Extract path from class prefix format if present
            if "'" in asset_path:
                asset_path = asset_path.split("'")[1]

            asset = unreal.EditorAssetLibrary.load_asset(asset_path)

            if asset:
                return asset
            else:
                unreal.log_warning(f"Asset not found: {asset_path}")
        except Exception as e:
            unreal.log_warning(f"Failed to load asset {asset_path}: {e}")

        return None

    def get_fallback_asset(self, object_name: str) -> Optional[Any]:
        """
        Get a fallback basic shape based on object type.
        
        Args:
            object_name: Object name to determine appropriate shape.
        
        Returns:
            Basic shape asset (Cube, Cylinder, etc.) or default Cube.
        """
        shape_map = {
            'chair': '/Engine/BasicShapes/Cube',
            'table': '/Engine/BasicShapes/Cube',
            'desk': '/Engine/BasicShapes/Cube',
            'person': '/Engine/BasicShapes/Cylinder',
            'character': '/Engine/BasicShapes/Cylinder',
            'tree': '/Engine/BasicShapes/Cone',
            'lamp': '/Engine/BasicShapes/Cylinder',
            'ball': '/Engine/BasicShapes/Sphere',
            'box': '/Engine/BasicShapes/Cube',
            'wall': '/Engine/BasicShapes/Plane',
            'floor': '/Engine/BasicShapes/Plane',
            'door': '/Engine/BasicShapes/Cube',
            'window': '/Engine/BasicShapes/Plane'
        }

        for keyword, shape_path in shape_map.items():
            if keyword in object_name.lower():
                asset = unreal.EditorAssetLibrary.load_asset(shape_path)
                if asset:
                    unreal.log(f"Using fallback shape for '{object_name}'")
                    return asset

        default = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube')
        if default:
            unreal.log(f"Using default cube for '{object_name}'")

        return default

    def find_character_asset(self) -> Optional[Any]:
        """
        Find a character mesh or blueprint.
        
        Checks show library first, then common character paths.
        
        Returns:
            Character asset or fallback cylinder shape.
        """
        # Check show library
        if self.show_library and 'characters' in self.show_library:
            for char_name, char_data in self.show_library['characters'].items():
                asset_path = char_data.get('asset_path')
                if asset_path:
                    asset = self.load_asset(asset_path)
                    if asset:
                        unreal.log(f"Using show character: {char_name}")
                        return asset

        # Fallback paths
        character_paths = [
            '/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter',
            '/Game/ThirdPersonBP/Blueprints/ThirdPersonCharacter',
            '/Game/Mannequin/Character/Mesh/SK_Mannequin',
            '/Game/Characters/Mannequin/Mesh/SK_Mannequin',
            '/Engine/EngineMeshes/SkeletalCylinder'
        ]

        for path in character_paths:
            asset = unreal.EditorAssetLibrary.load_asset(path)
            if asset:
                return asset

        return unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cylinder')

    def find_prop_assets(self, prop_names: List[str]) -> List[Dict[str, Any]]:
        """
        Find assets for multiple props.
        
        Args:
            prop_names: List of prop names to find assets for.
        
        Returns:
            List of dicts with 'name' and 'asset' keys for each matched prop.
        """
        assets = []

        for prop_name in prop_names:
            asset = self.find_best_match(prop_name, category='props')
            if asset:
                assets.append({
                    'name': prop_name,
                    'asset': asset
                })

        return assets

    def get_show_asset_summary(self) -> str:
        """
        Get a summary of available show assets.
        
        Returns:
            Formatted string summarizing asset counts by category.
        """
        if not self.show_library:
            return "No show library loaded"

        summary = f"Show: {self.show_name}\n"
        for category in ['characters', 'props', 'locations']:
            count = len(self.show_library.get(category, {}))
            summary += f"  {category}: {count} assets\n"

            for name in list(self.show_library.get(category, {}).keys())[:3]:
                summary += f"    - {name}\n"

        return summary

    def search_project_assets(self, search_term: str) -> List[Dict[str, str]]:
        """
        Search project for assets matching a term.
        
        Args:
            search_term: Search string to match against asset names.
        
        Returns:
            List of dicts with 'name', 'path', and 'type' for each match.
        """
        asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

        filter = unreal.ARFilter()
        filter.package_paths = ['/Game']
        filter.recursive_paths = True
        filter.class_paths = ['StaticMesh', 'SkeletalMesh', 'Blueprint']

        assets = asset_registry.get_assets(filter)

        matches = []
        search_lower = search_term.lower()

        for asset_data in assets:
            asset_name = str(asset_data.asset_name).lower()

            if search_lower in asset_name:
                matches.append({
                    'name': str(asset_data.asset_name),
                    'path': str(asset_data.get_full_name()),
                    'type': str(asset_data.asset_class_path.asset_name)
                })

        return matches

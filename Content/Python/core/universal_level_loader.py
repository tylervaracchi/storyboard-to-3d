# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
UNIVERSAL LEVEL LOADER
Works with any location from asset library, not just Park
"""

import unreal
import json
from pathlib import Path
import time

def load_any_level_from_library(location_name, show_name):
    """
    Universal level loader that works with any location
    Handles various path formats and extensions
    """

    unreal.log("\n" + "="*60)
    unreal.log("UNIVERSAL LEVEL LOADER")
    unreal.log("="*60)
    unreal.log(f"Location: {location_name}")
    unreal.log(f"Show: {show_name}")

    if not show_name:
        unreal.log("No show specified")
        return False

    # Step 1: Read asset library
    content_dir = Path(unreal.Paths.project_content_dir())
    asset_library_path = content_dir / "StoryboardTo3D" / "Shows" / show_name / "asset_library.json"

    unreal.log(f"\n Reading asset library...")

    if not asset_library_path.exists():
        unreal.log(f"Asset library not found at: {asset_library_path}")
        return False

    try:
        with open(asset_library_path, 'r') as f:
            library = json.load(f)
        unreal.log(f"Asset library loaded")
    except Exception as e:
        unreal.log(f"Failed to read asset library: {e}")
        return False

    # Step 2: Get location data
    locations = library.get('locations', {})

    if location_name not in locations:
        # Try case-insensitive match
        location_name_lower = location_name.lower()
        for loc_name in locations:
            if loc_name.lower() == location_name_lower:
                location_name = loc_name
                unreal.log(f"Found case-insensitive match: {loc_name}")
                break
        else:
            unreal.log(f"Location '{location_name}' not found in asset library")
            unreal.log(f"Available locations: {list(locations.keys())}")
            return False

    # Step 3: Get the path from library
    location_data = locations[location_name]
    level_path = location_data.get('asset_path', location_data.get('path', None))

    if not level_path:
        unreal.log(f"No path specified for location '{location_name}'")
        return False

    unreal.log(f"\n Asset library path: {level_path}")

    # Step 4: Clean and normalize the path
    original_path = level_path

    # Handle various extensions that might be in the asset library
    known_extensions = ['.park', '.umap', '.uasset', '.level']
    for ext in known_extensions:
        if level_path.endswith(ext):
            level_path = level_path[:-len(ext)]
            unreal.log(f"Removed extension '{ext}': {level_path}")
            break

    # Step 5: Check if asset exists
    unreal.log(f"\n Checking if level exists...")

    exists = False
    actual_path = None

    # Try without extension first
    if unreal.EditorAssetLibrary.does_asset_exist(level_path):
        exists = True
        actual_path = level_path
        unreal.log(f"Found at: {level_path}")
    else:
        # Try with .umap extension
        if unreal.EditorAssetLibrary.does_asset_exist(f"{level_path}.umap"):
            exists = True
            actual_path = f"{level_path}.umap"
            unreal.log(f"Found at: {actual_path}")
        else:
            unreal.log(f"Not found at: {level_path} or {level_path}.umap")

    if not exists:
        unreal.log(f"\n Level asset not found")
        unreal.log(f"Please ensure the level exists at one of these paths:")
        unreal.log(f"- {level_path}")
        unreal.log(f"- {level_path}.umap")
        return False

    # Step 6: Get current level for comparison
    current_world = unreal.EditorLevelLibrary.get_editor_world()
    current_level_name = current_world.get_name() if current_world else "Unknown"
    unreal.log(f"\n Current level: {current_level_name}")

    # Check if we're already in the target level (case-insensitive)
    target_level_name = level_path.split('/')[-1]  # Extract just the level name from path
    if current_level_name.lower() == target_level_name.lower():
        unreal.log(f"\n Already in target level: {current_level_name}")
        unreal.log(f"No need to reload")
        unreal.log("="*60)
        return True

    # Step 7: Load the level
    unreal.log(f"\n Loading level: {location_name}...")
    unreal.log(f"Path: {actual_path or level_path}")

    load_success = False

    # Method 1: Try LevelEditorSubsystem (UE5 preferred)
    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_editor:
            load_success = level_editor.load_level(level_path)
            if load_success:
                unreal.log(f"Load command sent via LevelEditorSubsystem")
    except Exception as e:
        unreal.log(f"LevelEditorSubsystem not available: {e}")

    # Method 2: Fallback to EditorLevelLibrary
    if not load_success:
        try:
            load_success = unreal.EditorLevelLibrary.load_level(level_path)
            if load_success:
                unreal.log(f"Load command sent via EditorLevelLibrary")
        except Exception as e:
            unreal.log(f"EditorLevelLibrary failed: {e}")

    if not load_success:
        unreal.log(f"Failed to send load command")
        return False

    # Step 8: Wait and verify
    time.sleep(1.0)  # Give it time to load

    new_world = unreal.EditorLevelLibrary.get_editor_world()
    new_level_name = new_world.get_name() if new_world else "Unknown"

    unreal.log(f"\n New level: {new_level_name}")

    # Step 9: Verify success
    if new_level_name != current_level_name:
        unreal.log(f"\n SUCCESSFULLY LOADED: {location_name}")
        unreal.log(f"From: {original_path}")
        unreal.log(f"Level name: {new_level_name}")
        unreal.log("="*60)
        return True
    else:
        unreal.log(f"\n Level name unchanged")
        unreal.log(f"Expected change from '{current_level_name}'")
        unreal.log(f"But still showing '{new_level_name}'")

        # Sometimes the level loads but keeps the same name
        # Check if any actors changed
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        unreal.log(f"Current actor count: {len(actors)}")

        unreal.log("="*60)
        return False

def get_all_locations_from_library(show_name):
    """Get all available locations for a show"""

    content_dir = Path(unreal.Paths.project_content_dir())
    asset_library_path = content_dir / "StoryboardTo3D" / "Shows" / show_name / "asset_library.json"

    if not asset_library_path.exists():
        return []

    try:
        with open(asset_library_path, 'r') as f:
            library = json.load(f)

        locations = library.get('locations', {})
        return list(locations.keys())
    except:
        return []

def test_all_locations(show_name='oat'):
    """Test loading all locations for a show"""

    unreal.log("\n" + "="*70)
    unreal.log("TESTING ALL LOCATIONS")
    unreal.log("="*70)

    locations = get_all_locations_from_library(show_name)

    if not locations:
        unreal.log(f"No locations found for show '{show_name}'")
        return

    unreal.log(f"\nFound {len(locations)} location(s) to test:")
    for loc in locations:
        unreal.log(f"- {loc}")

    results = []

    for location in locations:
        unreal.log(f"Testing: {location}")
        success = load_any_level_from_library(location, show_name)
        results.append((location, success))

        # Give user time to see the level
        if success:
            time.sleep(2)

    # Summary
    unreal.log("\n" + "="*70)
    unreal.log("TEST SUMMARY")
    unreal.log("="*70)

    for location, success in results:
        status = " PASS" if success else " FAIL"
        unreal.log(f"{location}: {status}")

    passed = sum(1 for _, s in results if s)
    total = len(results)
    unreal.log(f"\nResults: {passed}/{total} passed")

# Convenient wrapper for scene builder integration
def ensure_location_loaded(analysis, show_name):
    """
    Main function called by scene builder
    Extracts location from analysis and loads it
    """

    # Get location from analysis
    location = analysis.get('location', None)

    # Fallback to location_type if location not set
    if not location or location in ['Unknown', 'Auto-detect', 'Default']:
        location = analysis.get('location_type', None)

    # Skip generic location types
    if location in ['Unknown', 'Auto-detect', 'Default', 'Interior', 'Exterior', None]:
        unreal.log("ℹ No specific location to load, using current level")
        return True

    # Load the location
    return load_any_level_from_library(location, show_name)

# Test functions
if __name__ == "__main__":
    # Test Park
    unreal.log("\n Testing Park level...")
    load_any_level_from_library('Park', 'oat')

    # Test all locations
    # test_all_locations('oat')

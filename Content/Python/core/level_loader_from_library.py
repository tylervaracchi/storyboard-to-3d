# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
SMART LEVEL LOADER
Reads location paths directly from asset_library.json
"""

import unreal
import json
from pathlib import Path
import time

def load_level_from_asset_library(location_name, show_name):
    """
    Load level using the exact path from asset_library.json
    """

    unreal.log("\n" + "="*60)
    unreal.log("LOADING LEVEL FROM ASSET LIBRARY")
    unreal.log("="*60)
    unreal.log(f"Location: {location_name}")
    unreal.log(f"Show: {show_name}")

    # Step 1: Read the asset library JSON
    if not show_name:
        unreal.log("No show specified")
        return False

    # Build path to asset library
    content_dir = Path(unreal.Paths.project_content_dir())
    asset_library_path = content_dir / "StoryboardTo3D" / "Shows" / show_name / "asset_library.json"

    unreal.log(f"\n Reading asset library from:")
    unreal.log(f"{asset_library_path}")

    if not asset_library_path.exists():
        unreal.log(f"Asset library not found")
        return False

    # Read the JSON
    try:
        with open(asset_library_path, 'r') as f:
            library = json.load(f)
        unreal.log(f"Asset library loaded")
    except Exception as e:
        unreal.log(f"Failed to read asset library: {e}")
        return False

    # Step 2: Find the location in the library
    locations = library.get('locations', {})
    unreal.log(f"\n Available locations in library:")
    for loc_name, loc_data in locations.items():
        path = loc_data.get('asset_path', loc_data.get('path', 'No path'))
        unreal.log(f"- {loc_name}: {path}")

    if location_name not in locations:
        unreal.log(f"\n Location '{location_name}' not in asset library")
        # Try case-insensitive match
        for loc_name in locations:
            if loc_name.lower() == location_name.lower():
                location_name = loc_name
                unreal.log(f"Found case-insensitive match: {loc_name}")
                break
        else:
            return False

    # Step 3: Get the exact path from library
    location_data = locations[location_name]
    level_path = location_data.get('asset_path', location_data.get('path', None))

    if not level_path:
        unreal.log(f"No path specified for location '{location_name}'")
        return False

    unreal.log(f"\n Found location path in asset library: {level_path}")

    # Clean up the path - remove extensions
    if level_path.endswith('.park'):
        # The asset library has .park but it's actually a .umap file
        level_path = level_path[:-5]  # Remove .park
        unreal.log(f"Cleaned path (removed .park): {level_path}")
    elif level_path.endswith('.umap'):
        level_path = level_path[:-5]  # Remove .umap
        unreal.log(f"Cleaned path (removed .umap): {level_path}")

    # Step 4: Verify the level exists
    if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
        unreal.log(f"Level asset not found at: {level_path}")

        # Try with .umap extension
        if unreal.EditorAssetLibrary.does_asset_exist(f"{level_path}.umap"):
            level_path = f"{level_path}.umap"
            unreal.log(f"Found with .umap extension")
        else:
            return False

    unreal.log(f"Level asset exists")

    # Step 5: Get current level info for comparison
    current_world = unreal.EditorLevelLibrary.get_editor_world()
    current_level_name = current_world.get_name() if current_world else "Unknown"
    unreal.log(f"\n Current level: {current_level_name}")

    # Step 6: Load the level
    unreal.log(f"\n Loading level...")

    # Try new UE5 way first
    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_editor:
            success = level_editor.load_level(level_path)
            if success:
                unreal.log(f"Level load command sent (LevelEditorSubsystem)")
            else:
                # Fallback to old method
                success = unreal.EditorLevelLibrary.load_level(level_path)
                if success:
                    unreal.log(f"Level load command sent (EditorLevelLibrary)")
                else:
                    unreal.log(f"Failed to load level")
                    return False
    except Exception as e:
        unreal.log(f"Error loading level: {e}")
        return False

    # Step 7: Wait and verify
    time.sleep(1.0)  # Give it more time to load

    new_world = unreal.EditorLevelLibrary.get_editor_world()
    new_level_name = new_world.get_name() if new_world else "Unknown"

    unreal.log(f"\n New level: {new_level_name}")

    if new_level_name != current_level_name:
        unreal.log(f"\n SUCCESSFULLY LOADED: {location_name}")
        unreal.log(f"Path: {level_path}")
        unreal.log(f"Level: {new_level_name}")
        unreal.log("="*60)
        return True
    else:
        unreal.log(f"\n Level name unchanged - load may have failed")
        unreal.log("="*60)
        return False

def get_location_from_analysis(analysis):
    """Extract location name from analysis"""
    # Prefer 'location' field over 'location_type'
    location = analysis.get('location', None)
    if not location or location in ['Unknown', 'Auto-detect', 'Default', 'Interior', 'Exterior']:
        location = analysis.get('location_type', None)

    if location in ['Unknown', 'Auto-detect', 'Default', 'Interior', 'Exterior']:
        return None

    return location

def ensure_location_loaded(analysis, show_name):
    """
    Main function to ensure correct location is loaded
    """
    location = get_location_from_analysis(analysis)

    if not location:
        unreal.log("ℹ No specific location to load, using current level")
        return True

    return load_level_from_asset_library(location, show_name)

# Test function
def test_with_park():
    """Test loading Park level from asset library"""

    # Simulate what would come from analysis
    test_analysis = {
        'location': 'Park',
        'location_type': 'Exterior'
    }

    result = ensure_location_loaded(test_analysis, 'oat')

    if result:
        unreal.log("\n Test PASSED - Park level loaded from asset library")
    else:
        unreal.log("\n Test FAILED - Check your asset_library.json")
        unreal.log("Make sure 'Park' has a valid 'asset_path' or 'path' field")

    return result

if __name__ == "__main__":
    test_with_park()

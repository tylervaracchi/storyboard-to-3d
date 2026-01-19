# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 01: Basic Sequence Creation
Tests the fundamental sequence creation API in UE 5.6
"""

import unreal

def test_basic_sequence_creation():
    """Test basic sequence creation and verify API methods"""

    unreal.log("Testing basic sequence creation...")

    try:
        # Clean up any existing test sequence
        test_path = "/Game/Tests/Test01_BasicSequence"
        if unreal.EditorAssetLibrary.does_asset_exist(test_path):
            unreal.EditorAssetLibrary.delete_asset(test_path)

        # Ensure directory exists
        if not unreal.EditorAssetLibrary.does_directory_exist("/Game/Tests"):
            unreal.EditorAssetLibrary.make_directory("/Game/Tests")

        # Create sequence
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test01_BasicSequence",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if not level_sequence:
            unreal.log_error("Failed to create sequence")
            return False

        unreal.log(f"Created sequence: {level_sequence}")

        # Test available methods
        unreal.log("Testing sequence methods...")

        # Check for add_track (UE 5.6) vs add_master_track (older)
        has_add_track = hasattr(level_sequence, 'add_track')
        has_add_master_track = hasattr(level_sequence, 'add_master_track')

        unreal.log(f"- add_track: {'' if has_add_track else ''}")
        unreal.log(f"- add_master_track: {'' if has_add_master_track else ''}")

        # Check for get_tracks vs get_master_tracks
        has_get_tracks = hasattr(level_sequence, 'get_tracks')
        has_get_master_tracks = hasattr(level_sequence, 'get_master_tracks')

        unreal.log(f"- get_tracks: {'' if has_get_tracks else ''}")
        unreal.log(f"- get_master_tracks: {'' if has_get_master_tracks else ''}")

        # Test movie scene access
        movie_scene = None
        if hasattr(level_sequence, 'get_movie_scene'):
            movie_scene = level_sequence.get_movie_scene()
            unreal.log(f"get_movie_scene() works: {movie_scene}")
        elif hasattr(level_sequence, 'movie_scene'):
            movie_scene = level_sequence.movie_scene
            unreal.log(f"movie_scene property works: {movie_scene}")
        else:
            unreal.log("No movie_scene access method found")

        # Clean up
        unreal.EditorAssetLibrary.delete_asset(test_path)

        return has_add_track  # Return True if using new API

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False

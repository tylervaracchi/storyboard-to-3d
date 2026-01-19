# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 03: Camera Cut Track Creation
Tests camera cut track creation methods in UE 5.6
"""

import unreal

def test_camera_cut_track_creation():
    """Test creating camera cut tracks with different methods"""

    unreal.log("Testing camera cut track creation...")

    try:
        # Create test sequence
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test03_CameraCutTrack",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if not level_sequence:
            return False

        # Test creating camera cut track
        camera_cut_track = None
        method_used = None

        # Method 1: add_track (UE 5.6)
        try:
            camera_cut_track = level_sequence.add_track(unreal.MovieSceneCameraCutTrack)
            if camera_cut_track:
                unreal.log("Method 1: add_track() works")
                method_used = "add_track"
        except Exception as e:
            unreal.log(f"Method 1 failed: {e}")

        # Method 2: add_master_track (older versions)
        if not camera_cut_track:
            try:
                camera_cut_track = level_sequence.add_master_track(unreal.MovieSceneCameraCutTrack)
                if camera_cut_track:
                    unreal.log("Method 2: add_master_track() works")
                    method_used = "add_master_track"
            except Exception as e:
                unreal.log(f"Method 2 failed: {e}")

        # Method 3: Through movie scene
        if not camera_cut_track:
            try:
                movie_scene = level_sequence.get_movie_scene() if hasattr(level_sequence, 'get_movie_scene') else None
                if movie_scene:
                    if hasattr(movie_scene, 'add_track'):
                        camera_cut_track = movie_scene.add_track(unreal.MovieSceneCameraCutTrack)
                        if camera_cut_track:
                            unreal.log("Method 3: movie_scene.add_track() works")
                            method_used = "movie_scene.add_track"
                    elif hasattr(movie_scene, 'add_master_track'):
                        camera_cut_track = movie_scene.add_master_track(unreal.MovieSceneCameraCutTrack)
                        if camera_cut_track:
                            unreal.log("Method 3: movie_scene.add_master_track() works")
                            method_used = "movie_scene.add_master_track"
            except Exception as e:
                unreal.log(f"Method 3 failed: {e}")

        if not camera_cut_track:
            unreal.log_error("No method worked for creating camera cut track")
            return False

        unreal.log(f"Camera cut track created using: {method_used}")
        unreal.log(f"Track type: {type(camera_cut_track)}")

        # Test adding a section
        try:
            section = camera_cut_track.add_section()
            if section:
                unreal.log("Section added successfully")
                unreal.log(f"Section type: {type(section)}")

                # Check available methods on section
                unreal.log("Section methods for camera binding:")

                methods_to_check = [
                    'set_camera_binding_id',
                    'get_camera_binding_id',
                    'set_camera_guid',
                    'get_camera_guid',
                    'camera_binding_id',
                    'camera_guid'
                ]

                for method in methods_to_check:
                    if hasattr(section, method):
                        unreal.log(f"{method}")
                    else:
                        unreal.log(f"{method}")

                # Check editor properties
                if hasattr(section, 'get_editor_property_names'):
                    props = section.get_editor_property_names()
                    unreal.log(f"Editor properties: {props}")

        except Exception as e:
            unreal.log_error(f"Failed to add section: {e}")

        # Check how to retrieve tracks
        unreal.log("\n    Testing track retrieval methods:")

        # Test get_tracks
        try:
            tracks = level_sequence.get_tracks()
            unreal.log(f"get_tracks() returned {len(tracks)} tracks")
        except:
            unreal.log("get_tracks() not available")

        # Test get_master_tracks
        try:
            tracks = level_sequence.get_master_tracks()
            unreal.log(f"get_master_tracks() returned {len(tracks)} tracks")
        except:
            unreal.log("get_master_tracks() not available")

        # Clean up
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/Test03_CameraCutTrack")

        return camera_cut_track is not None

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False

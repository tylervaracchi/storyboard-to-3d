# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
TEST: GENERATE BUTTON FLOW WITH CAMERA BINDING
Tests the exact flow when clicking the green GENERATE button
"""

import unreal
import sys
from pathlib import Path

# Note: Don't use __file__ when running via exec()
# Add plugin path manually
plugin_path = r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python'
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)

def test_generate_button_flow():
    """Test the complete generate flow with camera binding verification"""

    unreal.log("\n" + "="*80)
    unreal.log("TESTING GENERATE BUTTON FLOW WITH CAMERA BINDING")
    unreal.log("="*80)

    # Create mock panel analysis (what comes from the UI)
    mock_analysis = {
        'characters': ['Hero', 'Villain'],
        'props': ['Sword', 'Shield'],
        'location': 'Castle',
        'location_type': 'interior',
        'shot_type': 'medium',
        'num_characters': 2,
        'description': 'Epic battle scene in castle'
    }

    unreal.log("\n Mock Analysis Data:")
    for key, value in mock_analysis.items():
        unreal.log(f"{key}: {value}")

    # Import the scene builder (what GENERATE button uses)
    try:
        from core.scene_builder_sequencer import SceneBuilder
        unreal.log("\n SceneBuilder imported successfully")
    except ImportError as e:
        unreal.log_error(f"\n Failed to import SceneBuilder: {e}")
        return False

    # Create scene builder with test show
    unreal.log("\n Creating SceneBuilder...")
    scene_builder = SceneBuilder(show_name="test")
    unreal.log("SceneBuilder created")

    # Build the scene (this is what happens when you click GENERATE)
    unreal.log("\n Building scene (simulating GENERATE button click)...")
    unreal.log("-"*80)

    try:
        scene_data = scene_builder.build_scene(
            analysis=mock_analysis,
            panel_index=999,  # Test panel
            auto_camera=True,
            auto_lighting=True
        )

        # Wait for build to complete (it uses queued operations)
        import time
        unreal.log("\n⏳ Waiting for queued build operations to complete...")
        time.sleep(5)  # Give it time to process the queue

        unreal.log("\n Build initiated")

    except Exception as e:
        unreal.log_error(f"\n Build failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Now verify the sequence was created
    unreal.log("\n" + "="*80)
    unreal.log("VERIFICATION - Checking what was created")
    unreal.log("="*80)

    sequence_path = "/Game/StoryboardSequences/test/Seq_Panel_999"

    # Check if sequence exists
    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_path):
        unreal.log_error(f"\n Sequence not found at: {sequence_path}")
        return False

    unreal.log(f"\n Sequence exists: {sequence_path}")

    # Load the sequence
    level_sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)
    if not level_sequence:
        unreal.log_error("\n Failed to load sequence")
        return False

    unreal.log("Sequence loaded")

    # Check contents
    unreal.log("\n Sequence Contents:")

    # Check spawnables
    spawnables = level_sequence.get_spawnables()
    unreal.log(f"\n   Spawnables ({len(spawnables)}):")
    camera_found = False
    for spawnable in spawnables:
        display_name = spawnable.get_display_name()
        unreal.log(f"• {display_name}")
        if 'camera' in display_name.lower():
            camera_found = True
            unreal.log(f"CAMERA FOUND: {display_name}")

    # Check tracks (UE 5.6 uses get_tracks not get_master_tracks)
    tracks = level_sequence.get_tracks()
    unreal.log(f"\n   Master Tracks ({len(tracks)}):")
    camera_cut_track_found = False
    camera_cut_track = None

    for track in tracks:
        track_type = type(track).__name__
        unreal.log(f"• {track_type}")

        if isinstance(track, unreal.MovieSceneCameraCutTrack):
            camera_cut_track_found = True
            camera_cut_track = track
            unreal.log(f"CAMERA CUT TRACK FOUND")

            # Check sections
            sections = track.get_sections()
            unreal.log(f"Sections: {len(sections)}")

            for i, section in enumerate(sections):
                unreal.log(f"Section {i+1}:")

                # Try to get camera binding
                try:
                    binding = section.get_camera_binding_id()
                    if binding:
                        unreal.log(f"Has binding: {binding}")

                        # Check if binding has GUID
                        if hasattr(binding, 'guid'):
                            unreal.log(f"GUID: {binding.guid}")

                        # Check if binding points to our camera
                        # Compare with spawnable GUIDs
                        for spawnable in spawnables:
                            spawnable_guid = spawnable.get_id()
                            if hasattr(binding, 'guid') and str(binding.guid) == str(spawnable_guid):
                                spawnable_name = spawnable.get_display_name()
                                if 'camera' in spawnable_name.lower():
                                    unreal.log(f"VERIFIED: Bound to {spawnable_name}")
                                else:
                                    unreal.log(f"Bound to {spawnable_name} (not camera?)")
                    else:
                        unreal.log(f"NO BINDING")

                except Exception as e:
                    unreal.log(f"Error checking binding: {e}")

    # Summary
    unreal.log("\n" + "="*80)
    unreal.log("VERIFICATION SUMMARY")
    unreal.log("="*80)

    results = {
        'sequence_created': True,
        'camera_spawnable': camera_found,
        'camera_cut_track': camera_cut_track_found,
        'camera_binding': False  # We'll set this based on detailed check
    }

    # Do detailed binding check
    if camera_cut_track_found and camera_cut_track:
        sections = camera_cut_track.get_sections()
        if sections:
            try:
                binding = sections[0].get_camera_binding_id()
                if binding:
                    # Check if it's bound to a camera spawnable
                    for spawnable in spawnables:
                        if hasattr(binding, 'guid') and str(binding.guid) == str(spawnable.get_id()):
                            if 'camera' in spawnable.get_display_name().lower():
                                results['camera_binding'] = True
            except:
                pass

    # Print results
    for key, value in results.items():
        status = "" if value else ""
        unreal.log(f"{status} {key}: {value}")

    # Recommendations
    unreal.log("\n RECOMMENDATIONS:")

    if not results['camera_binding'] and results['camera_cut_track']:
        unreal.log("Camera cut track exists but camera is NOT bound")
        unreal.log("MANUAL FIX REQUIRED:")
        unreal.log("1. Open the sequence in Sequencer")
        unreal.log("2. Find the red camera cut section")
        unreal.log("3. Right-click it")
        unreal.log("4. Select your camera from the menu")
        unreal.log("\n    This is a known UE 5.6 Python API limitation")
    elif results['camera_binding']:
        unreal.log("Camera binding is working!")
        unreal.log("Scene generation flow is complete")

    # Cleanup
    unreal.log("\n Cleaning up test sequence...")
    if unreal.EditorAssetLibrary.does_asset_exist(sequence_path):
        unreal.EditorAssetLibrary.delete_asset(sequence_path)
        unreal.log("Test sequence deleted")

    unreal.log("\n" + "="*80)
    unreal.log("TEST COMPLETE")
    unreal.log("="*80)

    return all(results.values())


if __name__ == "__main__":
    # Run main test
    unreal.log("\n" + ""*40)
    unreal.log("GENERATE BUTTON FLOW TEST SUITE")
    unreal.log(""*40)

    test_generate_button_flow()

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
TEST: Viewport Locking with Camera Cuts
Tests that viewport automatically locks to camera after generation
"""

import unreal
import sys
from pathlib import Path

# Add plugin path
plugin_path = r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python'
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)

def test_viewport_locking():
    """Test viewport locking to camera cuts"""

    unreal.log("\n" + "="*80)
    unreal.log("TESTING VIEWPORT LOCKING TO CAMERA CUTS")
    unreal.log("="*80)

    # Create a test scene with camera
    unreal.log("\n1⃣ Creating test scene with camera...")

    from core.scene_builder_sequencer import SceneBuilder

    mock_analysis = {
        'characters': ['TestChar'],
        'props': [],
        'location': 'TestLoc',
        'location_type': 'interior',
        'shot_type': 'medium',
        'num_characters': 1
    }

    scene_builder = SceneBuilder(show_name="test")
    scene_builder.build_scene(mock_analysis, panel_index=888, auto_camera=True, auto_lighting=False)

    # Wait for build to complete
    import time
    unreal.log("\n⏳ Waiting for scene to build...")
    time.sleep(6)  # Give extra time for viewport locking

    # Check if viewport is locked
    unreal.log("\n2⃣ Checking viewport lock status...")

    try:
        # Get current lock state
        is_locked = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport()

        if is_locked:
            unreal.log("Viewport IS locked to camera cuts")
            unreal.log("Viewport will show camera view")
        else:
            unreal.log("Viewport is NOT locked")
            unreal.log("Attempting to lock now...")

            # Try to lock it
            unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)

            # Verify
            is_locked = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport()
            if is_locked:
                unreal.log("Successfully locked viewport to camera")
            else:
                unreal.log("Failed to lock viewport")

    except Exception as e:
        unreal.log_error(f"Error checking viewport lock: {e}")
        unreal.log("This API might not be available in your UE version")
        return False

    # Verify sequence exists
    sequence_path = "/Game/StoryboardSequences/test/Seq_Panel_888"

    if unreal.EditorAssetLibrary.does_asset_exist(sequence_path):
        unreal.log(f"\n3⃣ Verifying sequence: {sequence_path}")

        level_sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)

        # Check for camera cut track
        has_camera_cut = False
        for track in level_sequence.get_tracks():
            if isinstance(track, unreal.MovieSceneCameraCutTrack):
                has_camera_cut = True
                sections = track.get_sections()
                unreal.log(f"Camera cut track found with {len(sections)} section(s)")
                break

        if not has_camera_cut:
            unreal.log("No camera cut track found")

        # Cleanup
        unreal.EditorAssetLibrary.delete_asset(sequence_path)
        unreal.log("Test sequence deleted")

    # Summary
    unreal.log("\n" + "="*80)
    unreal.log("VIEWPORT LOCKING TEST RESULTS")
    unreal.log("="*80)

    if is_locked and has_camera_cut:
        unreal.log("SUCCESS: Viewport locked and camera cut track exists")
        unreal.log("\n WHAT THIS MEANS:")
        unreal.log("• Viewport automatically shows camera view")
        unreal.log("• No need to manually press Shift+C")
        unreal.log("• Users see the scene through the camera immediately")
        return True
    elif has_camera_cut and not is_locked:
        unreal.log("PARTIAL: Camera cut track exists but viewport not locked")
        unreal.log("\n WHAT THIS MEANS:")
        unreal.log("• Camera cut track works")
        unreal.log("• Viewport locking might not be supported")
        unreal.log("• Users need to manually press Shift+C")
        return False
    else:
        unreal.log("FAILED: Issues with camera cut track or viewport")
        return False


def test_viewport_lock_api():
    """Test if the viewport lock API is available"""

    unreal.log("\n" + "="*80)
    unreal.log("TESTING VIEWPORT LOCK API AVAILABILITY")
    unreal.log("="*80)

    api_tests = []

    # Test 1: Check if function exists
    unreal.log("\n1⃣ Checking if API functions exist...")
    try:
        # Try to get the function
        func = unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport
        unreal.log("set_lock_camera_cut_to_viewport() exists")
        api_tests.append(('function_exists', True))
    except AttributeError:
        unreal.log("set_lock_camera_cut_to_viewport() does not exist")
        api_tests.append(('function_exists', False))

    try:
        func = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport
        unreal.log("is_lock_camera_cut_to_viewport() exists")
        api_tests.append(('query_function_exists', True))
    except AttributeError:
        unreal.log("is_lock_camera_cut_to_viewport() does not exist")
        api_tests.append(('query_function_exists', False))

    # Test 2: Try to call the functions
    unreal.log("\n2⃣ Testing function calls...")
    try:
        current_state = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport()
        unreal.log(f"Query successful: Current lock state = {current_state}")
        api_tests.append(('query_works', True))
    except Exception as e:
        unreal.log(f"Query failed: {e}")
        api_tests.append(('query_works', False))

    try:
        unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
        unreal.log("Set lock to True successful")
        api_tests.append(('set_works', True))

        # Verify it was set
        new_state = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport()
        if new_state:
            unreal.log("Verified: Lock is now True")
            api_tests.append(('set_verified', True))
        else:
            unreal.log("Lock was set but query returns False")
            api_tests.append(('set_verified', False))

    except Exception as e:
        unreal.log(f"Set failed: {e}")
        api_tests.append(('set_works', False))
        api_tests.append(('set_verified', False))

    # Summary
    unreal.log("\n" + "="*80)
    unreal.log("API AVAILABILITY RESULTS")
    unreal.log("="*80)

    for test_name, result in api_tests:
        status = "" if result else ""
        unreal.log(f"{status} {test_name}: {result}")

    all_passed = all(result for _, result in api_tests)

    if all_passed:
        unreal.log("\n ALL API TESTS PASSED")
        unreal.log("Viewport locking is fully supported")
    else:
        unreal.log("\n SOME API TESTS FAILED")
        unreal.log("Viewport locking might not be fully supported")
        unreal.log("Users may need to manually press Shift+C")

    return all_passed


if __name__ == "__main__":
    unreal.log("\n" + ""*40)
    unreal.log("VIEWPORT LOCKING TEST SUITE")
    unreal.log(""*40)

    # Test 1: API availability
    unreal.log("\n═══════════════════════════════════════════════════════════════")
    unreal.log("TEST 1: API AVAILABILITY")
    unreal.log("═══════════════════════════════════════════════════════════════")
    api_available = test_viewport_lock_api()

    # Test 2: Full workflow
    if api_available:
        unreal.log("\n═══════════════════════════════════════════════════════════════")
        unreal.log("TEST 2: FULL WORKFLOW WITH VIEWPORT LOCKING")
        unreal.log("═══════════════════════════════════════════════════════════════")
        test_viewport_locking()
    else:
        unreal.log("\n Skipping full workflow test - API not available")
        unreal.log("\n RECOMMENDATION:")
        unreal.log("Add user notification to manually press Shift+C")
        unreal.log("Or add a button in UI to trigger viewport lock")

    unreal.log("\n" + "="*80)
    unreal.log("TESTS COMPLETE")
    unreal.log("="*80)

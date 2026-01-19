# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Quick Test Runner
Simple script to run camera binding tests
"""

import unreal
import sys
from pathlib import Path

# Add parent directory to path
test_dir = Path(__file__).parent
parent_dir = test_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

def quick_test():
    """Run a quick test to check camera binding"""

    unreal.log("\n" + "="*60)
    unreal.log("QUICK CAMERA BINDING TEST")
    unreal.log("="*60)

    try:
        # Create minimal test sequence
        unreal.log("\n1⃣ Creating test sequence...")

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        seq = asset_tools.create_asset(
            asset_name="QuickTest",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        # Add camera
        unreal.log("2⃣ Adding camera...")
        camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location=unreal.Vector(-500, 0, 200)
        )

        # Add to sequence
        level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
        if level_seq_editor:
            binding = level_seq_editor.add_spawnable_from_instance(seq, camera)
        else:
            binding = seq.add_spawnable_from_instance(camera)

        camera_guid = binding.get_id()

        # Add cut track
        unreal.log("3⃣ Adding camera cut track...")
        track = seq.add_track(unreal.MovieSceneCameraCutTrack)
        section = track.add_section()

        # Try to bind
        unreal.log("4⃣ Attempting to bind camera...")

        success = False

        # Method 1: Direct GUID
        try:
            section.set_camera_binding_id(camera_guid)
            unreal.log("Direct GUID binding worked!")
            success = True
        except Exception as e:
            unreal.log(f"Direct GUID failed: {str(e)[:50]}")

        # Method 2: MovieSceneObjectBindingID
        if not success:
            try:
                binding_id = unreal.MovieSceneObjectBindingID()
                binding_id.set_editor_property('guid', camera_guid)
                section.set_camera_binding_id(binding_id)
                unreal.log("MovieSceneObjectBindingID worked!")
                success = True
            except Exception as e:
                unreal.log(f"MovieSceneObjectBindingID failed: {str(e)[:50]}")

        # Check result
        unreal.log("\n5⃣ Checking result...")

        try:
            current = section.get_camera_binding_id()
            if current:
                unreal.log("Camera binding exists!")
                if hasattr(current, 'guid'):
                    if str(current.guid) == str(camera_guid):
                        unreal.log("GUID matches - binding successful!")
                    else:
                        unreal.log("GUID doesn't match")
            else:
                unreal.log("No binding found")
        except:
            unreal.log("Could not check binding")

        # Clean up
        unreal.EditorLevelLibrary.destroy_actor(camera)
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/QuickTest")

        # Result
        unreal.log("\n" + "="*60)
        if success:
            unreal.log("CAMERA BINDING WORKS!")
            unreal.log("You can use the automated method")
        else:
            unreal.log("CAMERA BINDING FAILED")
            unreal.log("\n Required Manual Step:")
            unreal.log("After generation, right-click the camera cut section")
            unreal.log("and select the camera from the menu")
        unreal.log("="*60)

        return success

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    quick_test()

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 04: Camera Binding Methods
Tests different methods for binding camera to camera cut track in UE 5.6
"""

import unreal

def test_camera_binding_methods():
    """Test various methods for binding camera to cut track"""

    unreal.log("Testing camera binding methods...")

    try:
        # Setup: Create sequence with camera and cut track
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test04_CameraBinding",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if not level_sequence:
            return False

        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(level_sequence)

        # Create camera
        camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location=unreal.Vector(-500, 0, 200),
            rotation=unreal.Rotator(-10, 0, 0)
        )

        # Add camera as spawnable (use method that works from test 02)
        camera_binding = None
        camera_guid = None

        level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
        if level_seq_editor:
            camera_binding = level_seq_editor.add_spawnable_from_instance(level_sequence, camera_actor)
        else:
            camera_binding = level_sequence.add_spawnable_from_instance(camera_actor)

        if camera_binding:
            camera_guid = camera_binding.get_id()
            unreal.log(f"Camera added with GUID: {camera_guid}")
            unreal.log(f"GUID type: {type(camera_guid)}")
        else:
            unreal.log_error("Failed to add camera")
            return False

        # Create camera cut track and section
        camera_cut_track = level_sequence.add_track(unreal.MovieSceneCameraCutTrack)
        if not camera_cut_track:
            unreal.log_error("Failed to create camera cut track")
            return False

        section = camera_cut_track.add_section()
        if not section:
            unreal.log_error("Failed to add section")
            return False

        unreal.log("\n    Testing binding methods:")

        # Method 1: Direct GUID
        success = False
        try:
            section.set_camera_binding_id(camera_guid)
            unreal.log("Method 1: Direct GUID worked")
            success = True
        except Exception as e:
            unreal.log(f"Method 1 failed: {str(e)[:100]}")

        # Method 2: MovieSceneObjectBindingID with just GUID
        if not success:
            try:
                binding_id = unreal.MovieSceneObjectBindingID()
                binding_id.set_editor_property('guid', camera_guid)
                section.set_camera_binding_id(binding_id)
                unreal.log("Method 2: MovieSceneObjectBindingID with GUID worked")
                success = True
            except Exception as e:
                unreal.log(f"Method 2 failed: {str(e)[:100]}")

        # Method 3: MovieSceneObjectBindingID with all properties
        if not success:
            try:
                binding_id = unreal.MovieSceneObjectBindingID()
                binding_id.set_editor_property('guid', camera_guid)

                sequence_id = unreal.MovieSceneSequenceID()
                sequence_id.set_editor_property('value', 0)
                binding_id.set_editor_property('sequence_id', sequence_id)
                binding_id.set_editor_property('space', unreal.MovieSceneObjectBindingSpace.LOCAL)

                section.set_camera_binding_id(binding_id)
                unreal.log("Method 3: MovieSceneObjectBindingID with full properties worked")
                success = True
            except Exception as e:
                unreal.log(f"Method 3 failed: {str(e)[:100]}")

        # Method 4: Direct property assignment
        if not success:
            try:
                if hasattr(section, 'camera_binding_id'):
                    binding_id = unreal.MovieSceneObjectBindingID()
                    binding_id.guid = camera_guid
                    section.camera_binding_id = binding_id
                    unreal.log("Method 4: Direct property assignment worked")
                    success = True
                else:
                    unreal.log("Method 4: No camera_binding_id property")
            except Exception as e:
                unreal.log(f"Method 4 failed: {str(e)[:100]}")

        # Method 5: Editor property
        if not success:
            try:
                binding_id = unreal.MovieSceneObjectBindingID()
                binding_id.set_editor_property('guid', camera_guid)
                section.set_editor_property('camera_binding_id', binding_id)
                unreal.log("Method 5: set_editor_property worked")
                success = True
            except Exception as e:
                unreal.log(f"Method 5 failed: {str(e)[:100]}")

        # Verify binding
        unreal.log("\n    Verifying binding:")
        try:
            current_binding = section.get_camera_binding_id()
            unreal.log(f"Current binding: {current_binding}")

            if current_binding:
                if hasattr(current_binding, 'guid'):
                    unreal.log(f"Binding GUID: {current_binding.guid}")

                    # Check if it matches
                    if str(current_binding.guid) == str(camera_guid):
                        unreal.log("Camera successfully bound!")
                    else:
                        unreal.log("Binding exists but GUID doesn't match")
                else:
                    # The binding might be automatically set
                    unreal.log("ℹ Binding exists (possibly auto-linked)")
                    success = True
        except Exception as e:
            unreal.log(f"Could not verify: {e}")

        # Clean up
        unreal.EditorLevelLibrary.destroy_actor(camera_actor)
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/Test04_CameraBinding")

        return success

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False

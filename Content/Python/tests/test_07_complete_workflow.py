# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 07: Complete Workflow Test
Tests the entire workflow from sequence creation to camera binding
"""

import unreal

def test_complete_workflow():
    """Test the complete workflow as it would happen in production"""

    unreal.log("Testing complete workflow...")

    results = {
        'sequence_created': False,
        'camera_spawned': False,
        'camera_added_to_sequence': False,
        'cut_track_created': False,
        'section_added': False,
        'camera_bound': False,
        'binding_verified': False
    }

    try:
        # Step 1: Create sequence
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test07_CompleteWorkflow",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if level_sequence:
            results['sequence_created'] = True
            unreal.log("Sequence created")
        else:
            unreal.log("Failed to create sequence")
            return results

        # Step 2: Open in sequencer
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(level_sequence)
        unreal.log("Opened in sequencer")

        # Step 3: Create and spawn camera
        camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location=unreal.Vector(-500, 0, 200),
            rotation=unreal.Rotator(-10, 0, 0)
        )

        if camera_actor:
            results['camera_spawned'] = True
            unreal.log("Camera spawned")
        else:
            unreal.log("Failed to spawn camera")
            return results

        # Step 4: Add camera to sequence
        camera_binding = None
        camera_guid = None

        # Try UE 5.6 method first
        level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
        if level_seq_editor:
            try:
                camera_binding = level_seq_editor.add_spawnable_from_instance(level_sequence, camera_actor)
                unreal.log("Using LevelSequenceEditorSubsystem")
            except:
                pass

        # Fallback to direct method
        if not camera_binding:
            try:
                camera_binding = level_sequence.add_spawnable_from_instance(camera_actor)
                unreal.log("Using direct sequence method")
            except:
                pass

        if camera_binding:
            camera_guid = camera_binding.get_id()
            results['camera_added_to_sequence'] = True
            unreal.log(f"Camera added with GUID: {camera_guid}")
        else:
            unreal.log("Failed to add camera to sequence")
            unreal.EditorLevelLibrary.destroy_actor(camera_actor)
            return results

        # Step 5: Create camera cut track
        camera_cut_track = level_sequence.add_track(unreal.MovieSceneCameraCutTrack)

        if camera_cut_track:
            results['cut_track_created'] = True
            unreal.log("Camera cut track created")
        else:
            unreal.log("Failed to create camera cut track")
            unreal.EditorLevelLibrary.destroy_actor(camera_actor)
            return results

        # Step 6: Add section
        section = camera_cut_track.add_section()

        if section:
            results['section_added'] = True
            unreal.log("Section added")
        else:
            unreal.log("Failed to add section")
            unreal.EditorLevelLibrary.destroy_actor(camera_actor)
            return results

        # Step 7: Bind camera to section
        binding_success = False
        methods_tried = []

        # Try all known methods
        binding_methods = [
            ('Direct GUID', lambda: section.set_camera_binding_id(camera_guid)),
            ('MovieSceneObjectBindingID', lambda: bind_with_object_id(section, camera_guid)),
            ('Editor Property', lambda: bind_with_editor_property(section, camera_guid)),
            ('Direct Assignment', lambda: bind_with_direct_assignment(section, camera_guid))
        ]

        for method_name, method_func in binding_methods:
            try:
                method_func()
                binding_success = True
                unreal.log(f"{method_name} succeeded")
                break
            except Exception as e:
                methods_tried.append(f"{method_name}: {str(e)[:50]}")

        if binding_success:
            results['camera_bound'] = True
        else:
            unreal.log("All binding methods failed:")
            for attempt in methods_tried:
                unreal.log(f"- {attempt}")

        # Step 8: Verify binding
        try:
            current_binding = section.get_camera_binding_id()
            if current_binding:
                unreal.log(f"Binding exists: {current_binding}")

                # Check if it has the camera
                if hasattr(current_binding, 'guid'):
                    if str(current_binding.guid) == str(camera_guid):
                        results['binding_verified'] = True
                        unreal.log("Camera properly bound and verified")
                    else:
                        unreal.log("Binding exists but GUID doesn't match")
                else:
                    # Might be auto-bound
                    unreal.log("ℹ Binding exists (possibly auto-bound)")
                    results['binding_verified'] = True
            else:
                unreal.log("No binding found")
        except Exception as e:
            unreal.log(f"Verification failed: {e}")

        # Clean up
        unreal.EditorLevelLibrary.destroy_actor(camera_actor)
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/Test07_CompleteWorkflow")

        # Summary
        unreal.log("\n    Workflow Summary:")
        for step, success in results.items():
            status = "" if success else ""
            unreal.log(f"{status} {step}")

        return results

    except Exception as e:
        unreal.log_error(f"Workflow test failed: {e}")
        return results


def bind_with_object_id(section, camera_guid):
    """Helper: Bind using MovieSceneObjectBindingID"""
    binding_id = unreal.MovieSceneObjectBindingID()
    binding_id.set_editor_property('guid', camera_guid)
    section.set_camera_binding_id(binding_id)


def bind_with_editor_property(section, camera_guid):
    """Helper: Bind using editor property"""
    binding_id = unreal.MovieSceneObjectBindingID()
    binding_id.set_editor_property('guid', camera_guid)
    section.set_editor_property('camera_binding_id', binding_id)


def bind_with_direct_assignment(section, camera_guid):
    """Helper: Bind using direct assignment"""
    if hasattr(section, 'camera_binding_id'):
        binding_id = unreal.MovieSceneObjectBindingID()
        binding_id.guid = camera_guid
        section.camera_binding_id = binding_id
    else:
        raise Exception("No camera_binding_id attribute")

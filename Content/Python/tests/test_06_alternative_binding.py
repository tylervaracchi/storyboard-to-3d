# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 06: Alternative Binding Approaches
Tests workarounds and alternative methods for camera binding
"""

import unreal

def test_alternative_binding_methods():
    """Test alternative approaches to bind camera to cut track"""

    unreal.log("Testing alternative binding approaches...")

    try:
        # Setup
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test06_Alternative",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if not level_sequence:
            return False

        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(level_sequence)

        # Test 1: Single camera auto-binding
        unreal.log("\n    Test 1: Auto-binding with single camera")

        # Create camera
        camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location=unreal.Vector(-500, 0, 200),
            rotation=unreal.Rotator(-10, 0, 0)
        )

        # Add as spawnable
        level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
        if level_seq_editor:
            camera_binding = level_seq_editor.add_spawnable_from_instance(level_sequence, camera_actor)
        else:
            camera_binding = level_sequence.add_spawnable_from_instance(camera_actor)

        # Add camera cut track
        camera_cut_track = level_sequence.add_track(unreal.MovieSceneCameraCutTrack)
        section = camera_cut_track.add_section()

        # Save and refresh
        unreal.EditorAssetLibrary.save_asset("/Game/Tests/Test06_Alternative")
        unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()

        # Check if auto-bound
        try:
            current_binding = section.get_camera_binding_id()
            if current_binding:
                unreal.log("Camera auto-bound when only one camera exists")
            else:
                unreal.log("No auto-binding occurred")
        except:
            unreal.log("Could not check binding")

        # Test 2: Using MovieSceneBindingProxy
        unreal.log("\n    Test 2: Using MovieSceneBindingProxy")
        try:
            binding_proxy = unreal.MovieSceneBindingProxy()
            binding_proxy.set_sequence(level_sequence)
            binding_proxy.set_id(camera_binding.get_id())

            # Try to use proxy's ID
            proxy_id = binding_proxy.get_id()
            section.set_camera_binding_id(proxy_id)
            unreal.log("MovieSceneBindingProxy method worked")
        except Exception as e:
            unreal.log(f"MovieSceneBindingProxy failed: {str(e)[:50]}")

        # Test 3: Python command execution
        unreal.log("\n    Test 3: Using Python console command")
        try:
            # Build a command that might work in the console
            cmd = f"import unreal; seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence(); "
            cmd += f"tracks = seq.get_tracks(); cut_track = [t for t in tracks if isinstance(t, unreal.MovieSceneCameraCutTrack)][0]; "
            cmd += f"section = cut_track.get_sections()[0]; "
            cmd += f"bindings = seq.get_spawnables(); camera = [b for b in bindings if 'camera' in str(b.get_display_name()).lower()][0]; "
            cmd += f"section.set_camera_binding_id(camera.get_id())"

            # This would be executed in console
            unreal.log("Command built for console execution")
            unreal.log(f"Command: {cmd[:100]}...")
        except:
            unreal.log("Command building failed")

        # Test 4: Check for extension modules
        unreal.log("\n    Test 4: Checking for extension modules")

        extensions = [
            'MovieSceneToolsHelpers',
            'MovieSceneBindingExtensions',
            'SequencerScriptingHelpers',
            'LevelSequenceEditorHelpers'
        ]

        for ext in extensions:
            if hasattr(unreal, ext):
                unreal.log(f"Found {ext}")

                # Check its methods
                ext_class = getattr(unreal, ext)
                for method in dir(ext_class):
                    if 'camera' in method.lower() or 'binding' in method.lower():
                        unreal.log(f"- {method}")
            else:
                unreal.log(f"{ext} not found")

        # Test 5: Direct manipulation of sequence data
        unreal.log("\n    Test 5: Direct sequence data manipulation")
        try:
            # Get all data about the sequence
            all_spawnables = level_sequence.get_spawnables()
            all_tracks = level_sequence.get_tracks()

            unreal.log(f"Spawnables: {len(all_spawnables)}")
            unreal.log(f"Tracks: {len(all_tracks)}")

            # Find camera cut track sections
            for track in all_tracks:
                if isinstance(track, unreal.MovieSceneCameraCutTrack):
                    sections = track.get_sections()
                    unreal.log(f"Camera cut sections: {len(sections)}")

                    for i, sect in enumerate(sections):
                        # Try to get any property that might help
                        if hasattr(sect, '__dict__'):
                            unreal.log(f"Section {i} dict: {sect.__dict__}")

        except Exception as e:
            unreal.log(f"Direct manipulation failed: {e}")

        # Clean up
        unreal.EditorLevelLibrary.destroy_actor(camera_actor)
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/Test06_Alternative")

        return True  # Return True if we got through all tests

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False

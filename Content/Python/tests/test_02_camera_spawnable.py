# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 02: Camera Spawnable Methods
Tests different methods for adding cameras as spawnables in UE 5.6
"""

import unreal

def test_camera_spawnable_methods():
    """Test various methods for adding camera as spawnable"""

    unreal.log("Testing camera spawnable methods...")

    try:
        # Create test sequence
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        level_sequence = asset_tools.create_asset(
            asset_name="Test02_CameraSpawnable",
            package_path="/Game/Tests",
            asset_class=unreal.LevelSequence,
            factory=unreal.LevelSequenceFactoryNew()
        )

        if not level_sequence:
            return False

        # Open sequence
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(level_sequence)

        # Create camera actor
        camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location=unreal.Vector(-500, 0, 200),
            rotation=unreal.Rotator(-10, 0, 0)
        )

        if not camera_actor:
            unreal.log_error("Failed to spawn camera")
            return False

        unreal.log("Camera spawned")

        # Test Method 1: Direct sequence method (deprecated but might work)
        method1_success = False
        try:
            binding1 = level_sequence.add_spawnable_from_instance(camera_actor)
            if binding1:
                unreal.log("Method 1: level_sequence.add_spawnable_from_instance() works")
                unreal.log(f"Binding type: {type(binding1)}")
                unreal.log(f"Binding ID: {binding1.get_id()}")
                method1_success = True
        except Exception as e:
            unreal.log(f"Method 1 failed: {e}")

        # Test Method 2: LevelSequenceEditorSubsystem (UE 5.6 preferred)
        method2_success = False
        try:
            level_seq_editor = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
            if level_seq_editor:
                binding2 = level_seq_editor.add_spawnable_from_instance(level_sequence, camera_actor)
                if binding2:
                    unreal.log("Method 2: LevelSequenceEditorSubsystem.add_spawnable_from_instance() works")
                    unreal.log(f"Binding type: {type(binding2)}")
                    unreal.log(f"Binding ID: {binding2.get_id()}")
                    method2_success = True
        except Exception as e:
            unreal.log(f"Method 2 failed: {e}")

        # Test Method 3: MovieSceneSequenceExtensions
        method3_success = False
        try:
            if hasattr(unreal, 'MovieSceneSequenceExtensions'):
                binding3 = unreal.MovieSceneSequenceExtensions.add_spawnable_from_instance(
                    level_sequence, camera_actor
                )
                if binding3:
                    unreal.log("Method 3: MovieSceneSequenceExtensions.add_spawnable_from_instance() works")
                    method3_success = True
        except Exception as e:
            unreal.log(f"Method 3 failed: {e}")

        # Check what type of objects we get back
        all_bindings = level_sequence.get_spawnables()
        unreal.log(f"\n    Total spawnables in sequence: {len(all_bindings)}")

        for binding in all_bindings:
            display_name = binding.get_display_name()

            # Handle Text object
            if hasattr(display_name, 'to_string'):
                name_str = display_name.to_string()
            else:
                name_str = str(display_name)

            binding_id = binding.get_id()
            unreal.log(f"- {name_str}: {binding_id} (type: {type(binding_id)})")

        # Clean up
        unreal.EditorLevelLibrary.destroy_actor(camera_actor)
        unreal.EditorAssetLibrary.delete_asset("/Game/Tests/Test02_CameraSpawnable")

        return method1_success or method2_success or method3_success

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        return False

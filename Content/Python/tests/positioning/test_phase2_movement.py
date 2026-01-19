# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PHASE 2: Test Actor Movement/Transform API in Sequences
Tests that we can programmatically move actors in Unreal

Test Goals:
1. Spawn a test actor in the level
2. Move it via Python API (transform)
3. Verify the movement worked
4. Test movement within a sequence (keyframing)
5. Clean up after tests
"""

import unreal
from pathlib import Path
import sys
import time

# Add plugin path
plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))


class ActorMovementTest:
    """Test actor movement and transform APIs"""

    def __init__(self):
        self.test_actors = []
        self.test_sequence = None
        self.world = None
        self.subsystem = None

    def setup(self):
        """Setup test environment"""
        unreal.log("Setting up test environment...")

        # Get world
        self.world = unreal.EditorLevelLibrary.get_editor_world()
        if not self.world:
            unreal.log_error("Failed to get editor world")
            return False

        # Get EditorActorSubsystem (UE 5.6)
        self.subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if not self.subsystem:
            unreal.log_error("Failed to get EditorActorSubsystem")
            return False

        unreal.log("Test environment ready")
        return True

    def cleanup(self):
        """Clean up test actors and sequences"""
        unreal.log("\nCleaning up test data...")

        # Delete test actors
        if self.subsystem:
            for actor in self.test_actors:
                try:
                    if actor:  # Simple check if actor exists
                        self.subsystem.destroy_actor(actor)
                        unreal.log(f"Deleted actor: {actor.get_name()}")
                except:
                    pass  # Actor may already be deleted

        # Delete test sequence
        if self.test_sequence:
            seq_path = self.test_sequence.get_path_name()
            if unreal.EditorAssetLibrary.does_asset_exist(seq_path):
                unreal.EditorAssetLibrary.delete_asset(seq_path)
                unreal.log(f"Deleted sequence: {seq_path}")

        self.test_actors.clear()
        unreal.log("Cleanup complete")

    def test_1_spawn_actor(self):
        """Test 1: Spawn a simple actor"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 1: Spawn Actor")
        unreal.log("="*70)

        try:
            # Use a simple cube from engine content
            cube_path = "/Engine/BasicShapes/Cube"
            cube_asset = unreal.EditorAssetLibrary.load_asset(cube_path)

            if not cube_asset:
                unreal.log_error(f"Failed to load cube asset: {cube_path}")
                return False

            # Spawn actor
            spawn_location = unreal.Vector(0, 0, 100)
            spawn_rotation = unreal.Rotator(0, 0, 0)

            actor = self.subsystem.spawn_actor_from_object(
                cube_asset,
                spawn_location,
                spawn_rotation
            )

            if not actor:
                unreal.log_error("Failed to spawn actor")
                return False

            self.test_actors.append(actor)

            unreal.log(f"Spawned actor: {actor.get_name()}")
            unreal.log(f"Location: {actor.get_actor_location()}")
            unreal.log(f"Rotation: {actor.get_actor_rotation()}")

            return True

        except Exception as e:
            unreal.log_error(f"Test 1 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_2_move_actor(self):
        """Test 2: Move an existing actor"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 2: Move Actor")
        unreal.log("="*70)

        if not self.test_actors:
            unreal.log_error("No test actor available")
            return False

        actor = self.test_actors[0]

        try:
            # Get initial position
            initial_loc = actor.get_actor_location()
            unreal.log(f"Initial location: {initial_loc}")

            # Move actor
            new_location = unreal.Vector(200, 300, 150)
            actor.set_actor_location(new_location, False, False)

            # Verify movement
            actual_loc = actor.get_actor_location()
            unreal.log(f"New location: {actual_loc}")

            # Check if it moved (allow small tolerance)
            moved = (abs(actual_loc.x - new_location.x) < 1 and
                    abs(actual_loc.y - new_location.y) < 1 and
                    abs(actual_loc.z - new_location.z) < 1)

            if moved:
                unreal.log("Actor moved successfully")
                return True
            else:
                unreal.log_error("Actor did not move to expected position")
                return False

        except Exception as e:
            unreal.log_error(f"Test 2 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_3_rotate_actor(self):
        """Test 3: Rotate an actor"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 3: Rotate Actor")
        unreal.log("="*70)

        if not self.test_actors:
            unreal.log_error("No test actor available")
            return False

        actor = self.test_actors[0]

        try:
            # Get initial rotation
            initial_rot = actor.get_actor_rotation()
            unreal.log(f"Initial rotation: {initial_rot}")

            # Rotate actor
            new_rotation = unreal.Rotator(15, 45, 0)
            actor.set_actor_rotation(new_rotation, False)

            # Verify rotation
            actual_rot = actor.get_actor_rotation()
            unreal.log(f"New rotation: {actual_rot}")

            # Check if it rotated
            rotated = (abs(actual_rot.pitch - new_rotation.pitch) < 1 and
                      abs(actual_rot.yaw - new_rotation.yaw) < 1)

            if rotated:
                unreal.log("Actor rotated successfully")
                return True
            else:
                unreal.log_error("Actor did not rotate to expected orientation")
                return False

        except Exception as e:
            unreal.log_error(f"Test 3 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_4_create_sequence(self):
        """Test 4: Create a test sequence"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 4: Create Sequence")
        unreal.log("="*70)

        try:
            # Create test sequence
            sequence_name = "Test_Positioning_Sequence"
            sequence_path = "/Game/Tests/Positioning/"

            # Ensure directory exists
            if not unreal.EditorAssetLibrary.does_directory_exist(sequence_path):
                unreal.EditorAssetLibrary.make_directory(sequence_path)

            # Create sequence
            self.test_sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name=sequence_name,
                package_path=sequence_path,
                asset_class=unreal.LevelSequence,
                factory=unreal.LevelSequenceFactoryNew()
            )

            if not self.test_sequence:
                unreal.log_error("Failed to create sequence")
                return False

            # Set playback range ()
            fps = 30
            start_frame = 0
            end_frame = int(10 * fps)

            # Use MovieSceneSequenceExtensions for playback range
            playback_range = unreal.MovieSceneSequenceExtensions.get_playback_range(self.test_sequence)
            playback_range.set_start_frame(start_frame)
            playback_range.set_end_frame(end_frame)  # 10 seconds at 30fps
            unreal.log("Sequence created with 10-second duration")

            unreal.log(f"Created sequence: {sequence_name}")
            return True

        except Exception as e:
            unreal.log_error(f"Test 4 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_5_add_actor_to_sequence(self):
        """Test 5: Add actor to sequence as spawnable"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 5: Add Actor to Sequence")
        unreal.log("="*70)

        if not self.test_sequence:
            unreal.log_error("No test sequence available")
            return False

        if not self.test_actors:
            unreal.log_error("No test actor available")
            return False

        actor = self.test_actors[0]

        try:
            # Add actor as spawnable
            spawnable = self.test_sequence.add_spawnable_from_instance(actor)

            if not spawnable:
                unreal.log_error("Failed to add actor as spawnable")
                return False

            unreal.log(f"Added actor to sequence as spawnable")

            return True

        except Exception as e:
            unreal.log_error(f"Test 5 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_6_keyframe_transform(self):
        """Test 6: Add transform keyframes to sequence"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 6: Keyframe Transform in Sequence")
        unreal.log("="*70)

        if not self.test_sequence:
            unreal.log_error("No test sequence available")
            return False

        try:
            # Get spawnables
            spawnables = self.test_sequence.get_spawnables()

            if not spawnables:
                unreal.log_error("No spawnables in sequence")
                return False

            spawnable_binding = spawnables[0]

            # Add transform track
            transform_track = spawnable_binding.add_track(unreal.MovieScene3DTransformTrack)

            if not transform_track:
                unreal.log_error("Failed to add transform track")
                return False

            # Add transform section
            transform_section = transform_track.add_section()
            transform_section.set_start_frame_bounded(True)
            transform_section.set_start_frame(0)
            transform_section.set_end_frame_bounded(True)
            transform_section.set_end_frame(300)

            unreal.log("Added transform track to sequence")

            # Get channels
            channels = transform_section.get_channels_by_type(unreal.MovieSceneScriptingDoubleChannel)

            if len(channels) >= 3:
                # Keyframe start position (frame 0)
                channels[0].add_key(unreal.FrameNumber(0), 0.0)    # X
                channels[1].add_key(unreal.FrameNumber(0), 0.0)    # Y
                channels[2].add_key(unreal.FrameNumber(0), 100.0)  # Z

                # Keyframe end position (frame 300)
                channels[0].add_key(unreal.FrameNumber(300), 500.0)   # X
                channels[1].add_key(unreal.FrameNumber(300), 500.0)   # Y
                channels[2].add_key(unreal.FrameNumber(300), 100.0)   # Z

                unreal.log("Added transform keyframes")
                unreal.log("Frame 0: (0, 0, 100)")
                unreal.log("Frame 300: (500, 500, 100)")

                return True
            else:
                unreal.log_error(f"Expected 3+ channels, got {len(channels)}")
                return False

        except Exception as e:
            unreal.log_error(f"Test 6 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_7_programmatic_transform_update(self):
        """Test 7: Update spawnable transform programmatically"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 7: Programmatic Transform Update")
        unreal.log("="*70)

        if not self.test_sequence:
            unreal.log_error("No test sequence available")
            return False

        try:
            # Get spawnable
            spawnables = self.test_sequence.get_spawnables()
            if not spawnables:
                unreal.log_error("No spawnables found")
                return False

            spawnable = spawnables[0]

            # Get object template
            obj_template = spawnable.get_object_template()
            if not obj_template:
                unreal.log_error("Failed to get object template")
                return False

            # Get current transform from the actor directly
            initial_location = obj_template.get_actor_location()
            unreal.log(f"Initial template location: {initial_location}")

            # Update transform directly
            new_location = unreal.Vector(100, 200, 50)
            obj_template.set_actor_location(new_location, False, False)

            # Verify
            updated_location = obj_template.get_actor_location()
            unreal.log(f"Updated template location: {updated_location}")

            success = (abs(updated_location.x - new_location.x) < 1 and
                      abs(updated_location.y - new_location.y) < 1 and
                      abs(updated_location.z - new_location.z) < 1)

            if success:
                unreal.log("Spawnable transform updated programmatically")
                return True
            else:
                unreal.log_error("Transform did not update as expected")
                return False

        except Exception as e:
            unreal.log_error(f"Test 7 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def run_all_tests(self):
        """Run all Phase 2 tests"""
        unreal.log("\n" + "="*70)
        unreal.log("PHASE 2: ACTOR MOVEMENT TESTING")
        unreal.log("="*70)

        if not self.setup():
            unreal.log_error("Setup failed - cannot run tests")
            return

        # Run tests
        tests = [
            ("Spawn Actor", self.test_1_spawn_actor),
            ("Move Actor", self.test_2_move_actor),
            ("Rotate Actor", self.test_3_rotate_actor),
            ("Create Sequence", self.test_4_create_sequence),
            ("Add to Sequence", self.test_5_add_actor_to_sequence),
            ("Keyframe Transform", self.test_6_keyframe_transform),
            ("Programmatic Update", self.test_7_programmatic_transform_update)
        ]

        results = []

        for test_name, test_func in tests:
            try:
                success = test_func()
                results.append((test_name, success))
            except Exception as e:
                unreal.log_error(f"Test '{test_name}' crashed: {e}")
                results.append((test_name, False))

        # Cleanup
        self.cleanup()

        # Print summary
        passed = sum(1 for _, success in results if success)
        failed = len(results) - passed

        unreal.log("\n" + "="*70)
        unreal.log("PHASE 2 TEST SUMMARY")
        unreal.log("="*70)
        unreal.log(f"Passed: {passed}/{len(results)}")
        unreal.log(f"Failed: {failed}/{len(results)}")
        unreal.log("\nDetailed Results:")
        for test_name, success in results:
            status = "" if success else ""
            unreal.log(f"{status} {test_name}")

        if passed == len(results):
            unreal.log("\n ALL PHASE 2 TESTS PASSED - Ready for Phase 3!")
        elif passed > 0:
            unreal.log(f"\n {passed}/{len(results)} tests passed - Fix failures before Phase 3")
        else:
            unreal.log("\n ALL TESTS FAILED - Check Unreal Python API")

        unreal.log("="*70)


# Main execution
if __name__ == "__main__":
    test = ActorMovementTest()
    test.run_all_tests()

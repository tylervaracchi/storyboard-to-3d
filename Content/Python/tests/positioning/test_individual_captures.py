# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Individual capture tests - one button per angle
FIXED: Uses delay between captures to avoid command collision
"""

import unreal
import time
from pathlib import Path


class IndividualCaptureTests:
    """Individual test for each camera angle"""

    def __init__(self):
        self.scout_camera = None
        self.subsystem = None
        self.level_editor_subsystem = None

    def setup_scout_camera(self):
        """Create scout camera if it doesn't exist"""
        # Check if scout camera already exists
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()
        for actor in all_actors:
            if actor.get_actor_label() == "AI_Scout_Camera":
                self.scout_camera = actor
                unreal.log("Reusing existing AI_Scout_Camera")
                return True

        # Create new scout camera
        self.subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

        scout_loc = unreal.Vector(0, 0, 200)
        scout_rot = unreal.Rotator(0, 0, 0)

        self.scout_camera = self.subsystem.spawn_actor_from_class(
            unreal.CineCameraActor,
            scout_loc,
            scout_rot
        )

        if not self.scout_camera:
            unreal.log_error("Failed to spawn scout camera")
            return False

        self.scout_camera.set_actor_label("AI_Scout_Camera")

        # Disable auto-focus
        camera_component = self.scout_camera.get_cine_camera_component()
        if camera_component:
            focus_settings = camera_component.focus_settings
            focus_settings.focus_method = unreal.CameraFocusMethod.DISABLE
            camera_component.set_editor_property('focus_settings', focus_settings)

        unreal.log("Created AI_Scout_Camera")
        return True

    def capture_angle(self, angle_name, position, rotation):
        """Capture a single angle - returns immediately, file saves asynchronously"""
        start_time = time.time()
        unreal.log(f"\n Capturing {angle_name}...")
        unreal.log(f"⏱ Start: {time.strftime('%H:%M:%S')}")
        unreal.log(f"DEBUG: Requested position: {position}")
        unreal.log(f"DEBUG: Requested rotation: {rotation}")
        unreal.log(f"DEBUG: Pitch={rotation.pitch}, Yaw={rotation.yaw}, Roll={rotation.roll}")

        try:
            # Find existing scout camera
            step_start = time.time()
            if not self.scout_camera:
                # Look for existing camera
                subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                all_actors = subsystem.get_all_level_actors()
                for actor in all_actors:
                    if actor.get_actor_label() == "AI_Scout_Camera":
                        self.scout_camera = actor
                        break

                if not self.scout_camera:
                    unreal.log_error("AI_Scout_Camera not found!")
                    unreal.log("Click [ Pilot Viewport to Scout] first to create camera")
                    return False

            setup_time = time.time() - step_start

            # Move camera
            step_start = time.time()
            unreal.log(f"Moving camera to {position}")

            # DEBUG: Check camera BEFORE move
            before_loc = self.scout_camera.get_actor_location()
            before_rot = self.scout_camera.get_actor_rotation()
            unreal.log(f"DEBUG: BEFORE move - Location: {before_loc}")
            unreal.log(f"DEBUG: BEFORE move - Rotation: {before_rot}")

            self.scout_camera.set_actor_location(position, False, False)
            self.scout_camera.set_actor_rotation(rotation, False)

            # DEBUG: Check camera AFTER move (before viewport update)
            after_loc = self.scout_camera.get_actor_location()
            after_rot = self.scout_camera.get_actor_rotation()
            unreal.log(f"DEBUG: AFTER move (before pilot) - Location: {after_loc}")
            unreal.log(f"DEBUG: AFTER move (before pilot) - Rotation: {after_rot}")

            # CRITICAL: Force viewport to update by re-piloting
            unreal.log("Re-piloting viewport...")
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            # DEBUG: Check pilot status before
            try:
                current_pilot = level_editor_subsystem.get_piloting_actor()
                if current_pilot:
                    unreal.log(f"DEBUG: Already piloting: {current_pilot.get_actor_label()}")
                else:
                    unreal.log(f"DEBUG: Not currently piloting any actor")
            except:
                unreal.log(f"DEBUG: Could not get piloting status")

            level_editor_subsystem.pilot_level_actor(self.scout_camera)

            # DEBUG: Verify piloting is active
            try:
                new_pilot = level_editor_subsystem.get_piloting_actor()
                if new_pilot:
                    unreal.log(f"DEBUG: Now piloting: {new_pilot.get_actor_label()}")
                    unreal.log(f"DEBUG: Piloted camera location: {new_pilot.get_actor_location()}")
                    unreal.log(f"DEBUG: Piloted camera rotation: {new_pilot.get_actor_rotation()}")
                else:
                    unreal.log_warning(f"DEBUG: Piloting failed - no actor returned")
            except Exception as e:
                unreal.log_warning(f"DEBUG: Could not verify piloting: {e}")

            move_time = time.time() - step_start
            unreal.log("Forcing sequence evaluation for spawnable actors...")
            try:
                # Lock to sequence camera cuts temporarily to force evaluation
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
                unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)
                unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
                time.sleep(0.3)  # Allow sequence to fully evaluate
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                # Re-pilot to scout camera after sequence evaluation
                level_editor_subsystem.pilot_level_actor(self.scout_camera)
                unreal.log("Sequence evaluated, scout camera re-piloted")
            except Exception as e:
                unreal.log_warning(f"Could not force sequence evaluation: {e}")

            # Verify camera moved
            actual_loc = self.scout_camera.get_actor_location()
            actual_rot = self.scout_camera.get_actor_rotation()
            unreal.log(f"Camera at: {actual_loc}")
            unreal.log(f"Rotation: {actual_rot}")

            # DEBUG: Compare requested vs actual
            loc_diff_x = abs(actual_loc.x - position.x)
            loc_diff_y = abs(actual_loc.y - position.y)
            loc_diff_z = abs(actual_loc.z - position.z)
            rot_diff_pitch = abs(actual_rot.pitch - rotation.pitch)
            rot_diff_yaw = abs(actual_rot.yaw - rotation.yaw)
            rot_diff_roll = abs(actual_rot.roll - rotation.roll)

            unreal.log(f"DEBUG: Location difference:")
            unreal.log(f"X: {loc_diff_x:.2f}cm (req={position.x:.2f}, actual={actual_loc.x:.2f})")
            unreal.log(f"Y: {loc_diff_y:.2f}cm (req={position.y:.2f}, actual={actual_loc.y:.2f})")
            unreal.log(f"Z: {loc_diff_z:.2f}cm (req={position.z:.2f}, actual={actual_loc.z:.2f})")
            unreal.log(f"DEBUG: Rotation difference:")
            unreal.log(f"Pitch: {rot_diff_pitch:.2f}° (req={rotation.pitch:.2f}, actual={actual_rot.pitch:.2f})")
            unreal.log(f"Yaw: {rot_diff_yaw:.2f}° (req={rotation.yaw:.2f}, actual={actual_rot.yaw:.2f})")
            unreal.log(f"Roll: {rot_diff_roll:.2f}° (req={rotation.roll:.2f}, actual={actual_rot.roll:.2f})")

            # Warn if position/rotation differs significantly
            if loc_diff_x > 1.0 or loc_diff_y > 1.0 or loc_diff_z > 1.0:
                unreal.log_warning(f"DEBUG: Camera position differs from requested!")
            if rot_diff_pitch > 0.1 or rot_diff_yaw > 0.1 or rot_diff_roll > 0.1:
                unreal.log_warning(f"DEBUG: Camera rotation differs from requested!")

            # Queue screenshot
            step_start = time.time()
            filename = f"test_{angle_name}"

            # Calculate expected path
            screenshot_path = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor" / f"{filename}.png"

            unreal.log(f"HighResShot 1 filename={filename}")
            unreal.SystemLibrary.execute_console_command(None, f"HighResShot 1 filename={filename}")
            unreal.log(f"Screenshot queued!")
            unreal.log(f"Will save to: {screenshot_path.name}")

            screenshot_time = time.time() - step_start

            # Total time
            total_time = time.time() - start_time

            # Print timing summary
            unreal.log("⏱ TIMING:")
            unreal.log(f"Setup:  {setup_time:.2f}s")
            unreal.log(f"Move:   {move_time:.2f}s")
            unreal.log(f"Queue:  {screenshot_time:.2f}s")
            unreal.log(f"──────────────")
            unreal.log(f"Total:  {total_time:.2f}s")
            unreal.log(f"{angle_name.upper()} queued - will save in ~10s")
            return True

        except Exception as e:
            unreal.log_error(f"Error: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

    def cleanup_scout(self):
        """Delete scout camera from level"""
        unreal.log("\n Deleting AI_Scout_Camera...")

        # Find the camera in the level
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()

        scout_camera = None
        for actor in all_actors:
            if actor.get_actor_label() == "AI_Scout_Camera":
                scout_camera = actor
                break

        if not scout_camera:
            unreal.log_warning("AI_Scout_Camera not found (already deleted?)")
            return False

        # Eject viewport if piloted
        try:
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            level_editor_subsystem.eject_pilot_level_actor()
            unreal.log("Ejected viewport")
        except:
            pass

        # Delete the camera
        try:
            subsystem.destroy_actor(scout_camera)
            unreal.log("Deleted AI_Scout_Camera")
            self.scout_camera = None
            return True
        except Exception as e:
            unreal.log_error(f"Failed to delete: {e}")
            return False


# Individual test functions
def test_front():
    """Test front angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_front() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    return test.capture_angle(
        "front",
        unreal.Vector(-1364.0, -17.0, 182.0),
        unreal.Rotator(pitch=0.0, yaw=0.0, roll=0.0)
    )

def test_right():
    """Test right angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_right() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    # RIGHT view should look from the right side (Yaw=-90, NOT Pitch=-90)
    return test.capture_angle(
        "right",
        unreal.Vector(-26.999945, 1415.438812, 163.519337),
        unreal.Rotator(pitch=0.0, yaw=-90.0, roll=0.0)  # Explicit parameter names!
    )

def test_back():
    """Test back angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_back() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    return test.capture_angle(
        "back",
        unreal.Vector(1055.615701, 3.996872, 108.0),
        unreal.Rotator(pitch=0.0, yaw=-180.0, roll=0.0)
    )

def test_left():
    """Test left angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_left() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    return test.capture_angle(
        "left",
        unreal.Vector(-13.999949, -1319.43881, 130.519337),
        unreal.Rotator(pitch=0.0, yaw=90.0, roll=0.0)
    )

def test_top():
    """Test top angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_top() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    # TOP view should look straight down (Pitch=-90)
    return test.capture_angle(
        "top",
        unreal.Vector(-11.072672, -1.466941, 2141.045177),  # High Z for top-down
        unreal.Rotator(pitch=-90.0, yaw=0.0, roll=0.0)  # Explicit parameter names!
    )

def test_front_3_4():
    """Test front 3/4 angle"""
    unreal.log("\n" + "="*70)
    unreal.log("DEBUG: test_front_3_4() called")
    unreal.log("="*70)
    test = IndividualCaptureTests()
    return test.capture_angle(
        "front_3_4",
        unreal.Vector(-1036.86257, 910.687801, 167.451207),
        unreal.Rotator(pitch=0.0, yaw=-42.200001, roll=0.0)
    )

def test_hero():
    """Test hero camera"""
    start_time = time.time()
    unreal.log("\n Capturing HERO shot...")
    unreal.log(f"⏱ Start: {time.strftime('%H:%M:%S')}")
    unreal.log("Make sure sequence is open!")

    try:
        # Bind camera cuts
        step_start = time.time()
        unreal.log("Binding camera cuts...")
        try:
            unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
            time.sleep(0.5)
            bind_time = time.time() - step_start
            unreal.log(f"Bound ({bind_time:.2f}s)")
        except Exception as e:
            bind_time = time.time() - step_start
            unreal.log_error(f"Failed: {e}")
            return False

        # Queue screenshot
        step_start = time.time()
        filename = "test_hero"

        screenshot_path = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor" / f"{filename}.png"

        unreal.log(f"HighResShot 1 filename={filename}")
        unreal.SystemLibrary.execute_console_command(None, f"HighResShot 1 filename={filename}")
        unreal.log(f"Screenshot queued!")
        unreal.log(f"Will save to: {screenshot_path.name}")

        screenshot_time = time.time() - step_start

        unreal.log("Camera cuts still locked - click [ Eject] to unlock")

        # Total time
        total_time = time.time() - start_time
        unreal.log("⏱ TIMING:")
        unreal.log(f"Bind:   {bind_time:.2f}s")
        unreal.log(f"Queue:  {screenshot_time:.2f}s")
        unreal.log(f"──────────────")
        unreal.log(f"Total:  {total_time:.2f}s")
        unreal.log("HERO queued - will save in ~10s")
        return True

    except Exception as e:
        unreal.log_error(f"Error: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())
        return False

def cleanup():
    """Cleanup scout camera"""
    test = IndividualCaptureTests()
    test.cleanup_scout()

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PHASE 3 SIMPLE: Just spawn scout camera and verify it works
Step by step approach - no test scene, use your actual level
"""

import unreal
import time
from pathlib import Path


class SceneCaptureSimple:
    """Simple scout camera test with multi-angle capture"""

    def __init__(self):
        self.scout_camera = None
        self.hero_camera = None
        self.subsystem = None
        self.screenshots = []

    def step_1_spawn_scout_camera(self):
        """Step 1: Just spawn a scout camera in outliner and stop"""
        unreal.log("\n" + "="*70)
        unreal.log("="*70)

        try:
            # Get subsystem
            self.subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            if not self.subsystem:
                unreal.log_error("Could not get EditorActorSubsystem")
                return False

            # Spawn scout camera in OUTLINER with NO rotation
            scout_loc = unreal.Vector(-500, 0, 200)
            scout_rot = unreal.Rotator(0, 0, 0)  # Zero rotation

            unreal.log(f"Spawning scout camera at {scout_loc} with NO rotation...")

            self.scout_camera = self.subsystem.spawn_actor_from_class(
                unreal.CineCameraActor,
                scout_loc,
                scout_rot
            )

            if not self.scout_camera:
                unreal.log_error("Failed to spawn scout camera")
                return False

            # Label it
            self.scout_camera.set_actor_label("AI_Scout_Camera")

            # Turn OFF auto-focus (IMPORTANT!)
            camera_component = self.scout_camera.get_cine_camera_component()
            if camera_component:
                focus_settings = camera_component.focus_settings
                focus_settings.focus_method = unreal.CameraFocusMethod.DISABLE
                camera_component.set_editor_property('focus_settings', focus_settings)
                unreal.log("Auto-focus DISABLED")

            unreal.log("Scout camera spawned in OUTLINER")
            unreal.log(f"Label: AI_Scout_Camera")
            unreal.log(f"Location: {scout_loc}")
            unreal.log(f"Rotation: (0, 0, 0) - NO rotation applied")
            # PILOT VIEWPORT TO CAMERA
            unreal.log("Piloting viewport to scout camera...")
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if not level_editor_subsystem:
                unreal.log_warning("Could not get LevelEditorSubsystem for piloting")
                return False

            # UNBIND camera cuts from viewport before scout captures
            unreal.log("\n Unbinding camera cuts from viewport (Shift+C)...")
            try:
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                time.sleep(0.3)
                unreal.log("Camera cuts unbound - scout camera can now control viewport")
            except Exception as e:
                unreal.log_warning(f"Could not unbind camera cuts: {e}")
                unreal.log("Continuing anyway...")

            # CAPTURE 6 SCOUT ANGLES
            unreal.log("\n" + "="*70)
            unreal.log("CAPTURING 6 SCOUT ANGLES")
            unreal.log("="*70)

            # Define 6 optimal angles for AI
            scout_angles = [
                ("front", unreal.Vector(-500, 0, 150), unreal.Rotator(-10, 0, 0)),
                ("right", unreal.Vector(0, -500, 150), unreal.Rotator(-10, 90, 0)),
                ("back", unreal.Vector(500, 0, 150), unreal.Rotator(-10, 180, 0)),
                ("left", unreal.Vector(0, 500, 150), unreal.Rotator(-10, -90, 0)),
                ("top", unreal.Vector(0, 0, 800), unreal.Rotator(-90, 0, 0)),
                ("front_3_4", unreal.Vector(-350, -350, 200), unreal.Rotator(-15, 45, 0))
            ]

            for angle_name, position, rotation in scout_angles:
                unreal.log(f"\n Capturing {angle_name} angle...")

                # Move scout camera
                self.scout_camera.set_actor_location(position, False, False)
                self.scout_camera.set_actor_rotation(rotation, False)
                time.sleep(0.3)  # Wait for camera to settle

                # Pilot viewport
                level_editor_subsystem.pilot_level_actor(self.scout_camera)
                time.sleep(0.5)  # Wait for viewport to update

                # Capture
                filename = f"scout_{angle_name}"
                unreal.SystemLibrary.execute_console_command(None, f"HighResShot 1 filename={filename}")

                # WAIT LONGER for screenshot to complete
                time.sleep(7.0)

                # EJECT viewport to ensure screenshot completes
                level_editor_subsystem.eject_pilot_level_actor()
                time.sleep(0.3)

                self.screenshots.append(filename)
                unreal.log(f"{filename}.png")

            # Eject from scout
            level_editor_subsystem.eject_pilot_level_actor()

            unreal.log("\n All 6 scout angles captured!")
            return True

        except Exception as e:
            unreal.log_error(f"Error: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

    def step_2_hero_camera_shot(self):
        """Step 2: Capture hero camera shot using Shift+C"""
        unreal.log("\n" + "="*70)
        unreal.log("="*70)

        try:
            unreal.log("Capturing from camera cuts track (hero camera)...")
            unreal.log("Make sure your sequence is open with camera on camera cuts track!")
            # BIND camera cuts to viewport (Shift+C)
            unreal.log("Binding camera cuts to viewport (Shift+C)...")
            try:
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
                time.sleep(0.5)  # Wait for viewport to update to hero camera
                unreal.log("Camera cuts bound - viewport showing hero camera")
            except Exception as e:
                unreal.log_error(f"Failed to bind camera cuts: {e}")
                return False

            # CAPTURE HERO SHOT
            unreal.log("Capturing HERO shot...")
            unreal.SystemLibrary.execute_console_command(None, "HighResShot 1 filename=hero_shot")

            # WAIT for screenshot
            time.sleep(7.0)

            # UNBIND camera cuts from viewport (Shift+C again)
            unreal.log("Unbinding camera cuts from viewport (Shift+C)...")
            try:
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                time.sleep(0.2)
                unreal.log("Camera cuts unbound")
            except Exception as e:
                unreal.log_warning(f"Could not unbind: {e}")

            self.screenshots.append("hero_shot")
            unreal.log("hero_shot.png")
            return True

        except Exception as e:
            unreal.log_error(f"Error: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

    def cleanup(self):
        """Delete temporary cameras"""
        unreal.log("\n" + "="*70)
        unreal.log("CLEANUP")
        unreal.log("="*70)

        if self.subsystem:
            # Delete scout camera (temporary)
            if self.scout_camera:
                try:
                    self.subsystem.destroy_actor(self.scout_camera)
                    unreal.log("Deleted: AI_Scout_Camera (temporary tool)")
                except Exception as e:
                    unreal.log_error(f"Failed to delete scout: {e}")

            # DON'T delete hero camera - it's from the sequence!
            if self.hero_camera:
                camera_label = self.hero_camera.get_actor_label()
                unreal.log(f"Kept: {camera_label} (from sequence, stays in level)")

        self.scout_camera = None
        self.hero_camera = None


def run_simple_test():
    """Run the complete multi-angle capture test"""
    test = SceneCaptureSimple()

    unreal.log("\n" + "="*70)
    unreal.log("PHASE 3: MULTI-ANGLE CAPTURE TEST")
    unreal.log("="*70)
    unreal.log("This test will:")
    unreal.log("1. Spawn temporary scout camera")
    unreal.log("2. Capture 6 scout angles (front, right, back, left, top, 3/4)")
    unreal.log("3. Find hero camera from sequence camera cuts track")
    unreal.log("4. Capture hero shot from sequence camera")
    unreal.log("5. Total: 7 screenshots for AI")
    unreal.log("REQUIREMENT: Open your level sequence before running!")
    # Step 1: Scout angles
    success1 = test.step_1_spawn_scout_camera()

    if not success1:
        unreal.log_error("Failed at step 1")
        return None

    # Step 2: Hero shot
    success2 = test.step_2_hero_camera_shot()

    if not success2:
        unreal.log_error("Failed at step 2")
        return None

    # Summary
    unreal.log("="*70)
    unreal.log("TEST COMPLETE - All screenshots captured!")
    unreal.log("="*70)
    unreal.log(f"\n Total screenshots: {len(test.screenshots)}")
    unreal.log("\n Screenshots created:")
    for i, name in enumerate(test.screenshots, 1):
        unreal.log(f"{i}. {name}.png")

    screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
    unreal.log(f"\n Location: {screenshots_dir}")

    unreal.log("\n Ready to send to AI:")
    unreal.log("• 6 scout angles (scene understanding)")
    unreal.log("• 1 hero shot (from sequence camera)")
    unreal.log("• + 1 storyboard image (target)")
    unreal.log("= 8 images total to AI ")
    unreal.log("Camera Management:")
    unreal.log("• Scout camera: Deleted (temporary tool)")
    unreal.log("• Hero camera: Kept in sequence (permanent)")
    return test  # Return test object so user can cleanup later

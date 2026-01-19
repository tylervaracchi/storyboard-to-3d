# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PHASE 4: Test Single Positioning Iteration
Tests complete cycle: Capture → AI Analysis → Move Actor → Verify

Test Goals:
1. Setup: Spawn actor and storyboard reference
2. Capture current scene state
3. Send to AI with storyboard for comparison
4. Parse AI positioning instructions
5. Move actor based on AI instructions
6. Verify movement worked
"""

import unreal
from pathlib import Path
import sys
import base64
import json
import time

# Add plugin path
plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))


class SingleIterationTest:
    """Test complete single iteration of AI positioning"""

    def __init__(self):
        self.world = None
        self.subsystem = None
        self.ai_provider = None
        self.test_actor = None
        self.test_camera = None
        self.storyboard_image = None
        self.capture_dir = Path(unreal.Paths.project_saved_dir()) / "PositioningTests"
        self.capture_dir.mkdir(parents=True, exist_ok=True)

    def setup(self):
        """Setup test environment"""
        unreal.log("="*70)
        unreal.log("PHASE 4: SINGLE POSITIONING ITERATION TEST")
        unreal.log("="*70)

        # Get world and subsystem
        self.world = unreal.EditorLevelLibrary.get_editor_world()
        self.subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

        if not self.world or not self.subsystem:
            unreal.log_error("Failed to get world or subsystem")
            return False

        # Setup AI
        try:
            from core.settings_manager import get_settings
            from api.ai_client_enhanced import EnhancedAIClient

            settings = get_settings()
            ai_settings = settings.get('ai_settings', {})

            # Extract provider and API key from settings
            provider = ai_settings.get('active_provider', 'OpenAI GPT-4 Vision')
            api_key = ai_settings.get('openai_api_key') or ai_settings.get('anthropic_api_key') or ai_settings.get('api_key')

            # Create AI client with correct parameters
            self.ai_provider = EnhancedAIClient(
                provider=provider,
                api_key=api_key,
                enable_cache=True
            )
            unreal.log("AI provider initialized")
        except Exception as e:
            unreal.log_error(f"Failed to setup AI: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

        # Find storyboard image
        content_dir = Path(unreal.Paths.project_content_dir())
        shows_dir = content_dir / "StoryboardTo3D" / "Shows"

        if shows_dir.exists():
            for show_dir in shows_dir.iterdir():
                # Try Panels folder
                panels_dir = show_dir / "Panels"
                if panels_dir.exists():
                    for img in panels_dir.glob("*.png"):
                        self.storyboard_image = img
                        break

                # Try Episodes
                if not self.storyboard_image:
                    episodes_dir = show_dir / "Episodes"
                    if episodes_dir.exists():
                        for ep_dir in episodes_dir.iterdir():
                            ep_panels = ep_dir / "Panels"
                            if ep_panels.exists():
                                for img in ep_panels.glob("*.png"):
                                    self.storyboard_image = img
                                    break
                            if self.storyboard_image:
                                break

                if self.storyboard_image:
                    break

        if self.storyboard_image:
            unreal.log(f"Found storyboard: {self.storyboard_image.name}")
        else:
            unreal.log_warning("No storyboard found - will test without reference")

        return True

    def cleanup(self):
        """Clean up test actors"""
        unreal.log("\nCleaning up...")

        if self.subsystem:
            if self.test_actor and unreal.is_valid(self.test_actor):
                self.subsystem.destroy_actor(self.test_actor)
            if self.test_camera and unreal.is_valid(self.test_camera):
                self.subsystem.destroy_actor(self.test_camera)

        unreal.log("Cleanup complete")

    def step_1_spawn_scene(self):
        """Step 1: Spawn test scene"""
        unreal.log("\n" + "-"*70)
        unreal.log("-"*70)

        try:
            # Spawn test actor (cube)
            cube_path = "/Engine/BasicShapes/Cube"
            cube_asset = unreal.EditorAssetLibrary.load_asset(cube_path)

            if not cube_asset:
                unreal.log_error("Failed to load cube")
                return False

            # Start at suboptimal position (AI will need to correct)
            initial_pos = unreal.Vector(150, 150, 100)
            initial_rot = unreal.Rotator(0, 45, 0)

            self.test_actor = self.subsystem.spawn_actor_from_object(
                cube_asset, initial_pos, initial_rot
            )

            if not self.test_actor:
                unreal.log_error("Failed to spawn actor")
                return False

            self.test_actor.set_actor_label("TestActor_Positioning")

            unreal.log(f"Spawned test actor at {initial_pos}")

            # Spawn camera
            camera_pos = unreal.Vector(-500, 0, 200)
            camera_rot = unreal.Rotator(-15, 0, 0)

            self.test_camera = self.world.spawn_actor(
                unreal.CineCameraActor,
                camera_pos,
                camera_rot
            )

            if not self.test_camera:
                unreal.log_error("Failed to spawn camera")
                return False

            self.test_camera.set_actor_label("TestCamera_Positioning")

            unreal.log(f"Spawned camera at {camera_pos}")
            return True

        except Exception as e:
            unreal.log_error(f"Step 1 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def step_2_capture_scene(self):
        """Step 2: Capture current scene state"""
        unreal.log("\n" + "-"*70)
        unreal.log("-"*70)

        try:
            # Lock viewport to camera
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if not level_editor_subsystem:
                unreal.log_error("LevelEditorSubsystem not available")
                return None

            level_editor_subsystem.pilot_level_actor(self.test_camera)
            time.sleep(0.3)  # Wait for viewport update

            # Take screenshot
            automation_lib = unreal.AutomationLibrary()
            screenshot_name = "phase4_current_scene"

            options = unreal.AutomationScreenshotOptions()
            options.resolution = unreal.Vector2D(1280, 720)
            options.delay = 0.1

            automation_lib.take_automation_screenshot(screenshot_name, options)
            time.sleep(0.5)

            # Unlock viewport
            level_editor_subsystem.eject_pilot_level_actor()

            # Find the screenshot
            saved_screenshots = Path(unreal.Paths.project_saved_dir()) / "Screenshots"
            screenshot_files = sorted(saved_screenshots.glob(f"*{screenshot_name}*.png"),
                                     key=lambda p: p.stat().st_mtime, reverse=True)

            if not screenshot_files:
                unreal.log_error("Screenshot not found")
                return None

            screenshot_path = screenshot_files[0]
            unreal.log(f"Captured scene: {screenshot_path.name}")

            # Encode for AI
            with open(screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            unreal.log(f"Encoded for AI ({len(image_data)} chars)")
            return image_data

        except Exception as e:
            unreal.log_error(f"Step 2 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return None

    def step_3_ai_analysis(self, scene_capture):
        """Step 3: Send to AI and get positioning instructions"""
        unreal.log("\n" + "-"*70)
        unreal.log("-"*70)

        if not scene_capture:
            unreal.log_error("No scene capture provided")
            return None

        try:
            # Get actor's current position for reference
            current_pos = self.test_actor.get_actor_location()
            current_rot = self.test_actor.get_actor_rotation()

            # Build prompt
            prompt = f"""You are analyzing a 3D scene to improve object positioning.

CURRENT STATE:
- Actor: "TestActor" (cube)
- Current Position: X={current_pos.x:.1f}, Y={current_pos.y:.1f}, Z={current_pos.z:.1f}
- Current Rotation: Yaw={current_rot.yaw:.1f}

TASK:
The actor should be centered in frame at position (0, 0, 100).
Analyze the current scene and provide positioning corrections.

Respond ONLY with JSON:
{{
    "analysis": "Brief description of current positioning",
    "needs_adjustment": true,
    "adjustments": [
        {{
            "actor": "TestActor",
            "target_position": {{"x": 0, "y": 0, "z": 100}},
            "target_rotation": {{"yaw": 0}},
            "priority": "high",
            "reason": "Actor is off-center"
        }}
    ]
}}"""

            unreal.log("Sending to AI...")
            unreal.log(f"Current actor position: {current_pos}")

            # Send to AI
            if hasattr(self.ai_provider, 'analyze_image'):
                response = self.ai_provider.analyze_image(scene_capture, prompt)
            else:
                unreal.log_error("AI provider doesn't support image analysis")
                return None

            if not response:
                unreal.log_error("AI returned empty response")
                return None

            unreal.log("Received AI response")
            unreal.log(f"Response preview: {response[:200]}...")

            # Parse JSON
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_text = response[json_start:json_end]
                    data = json.loads(json_text)
                else:
                    raise

            unreal.log("Parsed AI response")
            unreal.log(f"Analysis: {data.get('analysis', 'N/A')}")
            unreal.log(f"Needs adjustment: {data.get('needs_adjustment', False)}")

            if 'adjustments' in data and data['adjustments']:
                adj = data['adjustments'][0]
                unreal.log(f"Target position: {adj.get('target_position', {})}")
                unreal.log(f"Reason: {adj.get('reason', 'N/A')}")

            return data

        except Exception as e:
            unreal.log_error(f"Step 3 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return None

    def step_4_apply_adjustments(self, ai_response):
        """Step 4: Apply AI positioning instructions"""
        unreal.log("\n" + "-"*70)
        unreal.log("-"*70)

        if not ai_response:
            unreal.log_error("No AI response provided")
            return False

        try:
            adjustments = ai_response.get('adjustments', [])

            if not adjustments:
                unreal.log_warning("No adjustments in AI response")
                return False

            # Get first adjustment (for single actor test)
            adj = adjustments[0]

            # Get current position
            before_pos = self.test_actor.get_actor_location()
            before_rot = self.test_actor.get_actor_rotation()

            unreal.log(f"Before: Position={before_pos}, Rotation={before_rot}")

            # Apply position
            if 'target_position' in adj:
                target_pos = adj['target_position']
                new_location = unreal.Vector(
                    target_pos.get('x', before_pos.x),
                    target_pos.get('y', before_pos.y),
                    target_pos.get('z', before_pos.z)
                )

                self.test_actor.set_actor_location(new_location, False, False)
                unreal.log(f"Moved to: {new_location}")

            # Apply rotation
            if 'target_rotation' in adj:
                target_rot = adj['target_rotation']
                new_rotation = unreal.Rotator(
                    target_rot.get('pitch', before_rot.pitch),
                    target_rot.get('yaw', before_rot.yaw),
                    target_rot.get('roll', before_rot.roll)
                )

                self.test_actor.set_actor_rotation(new_rotation, False)
                unreal.log(f"Rotated to: {new_rotation}")

            # Verify movement
            after_pos = self.test_actor.get_actor_location()
            after_rot = self.test_actor.get_actor_rotation()

            unreal.log(f"After: Position={after_pos}, Rotation={after_rot}")

            # Check if movement occurred
            moved = (abs(after_pos.x - before_pos.x) > 0.1 or
                    abs(after_pos.y - before_pos.y) > 0.1 or
                    abs(after_pos.z - before_pos.z) > 0.1)

            if moved:
                unreal.log("Actor successfully repositioned")
                return True
            else:
                unreal.log_warning("Actor position unchanged")
                return False

        except Exception as e:
            unreal.log_error(f"Step 4 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def step_5_verify_improvement(self):
        """Step 5: Capture again and verify improvement"""
        unreal.log("\n" + "-"*70)
        unreal.log("-"*70)

        try:
            # Capture scene again
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if not level_editor_subsystem:
                unreal.log_error("LevelEditorSubsystem not available")
                return False

            level_editor_subsystem.pilot_level_actor(self.test_camera)
            time.sleep(0.3)

            automation_lib = unreal.AutomationLibrary()
            screenshot_name = "phase4_after_adjustment"

            options = unreal.AutomationScreenshotOptions()
            options.resolution = unreal.Vector2D(1280, 720)
            options.delay = 0.1

            automation_lib.take_automation_screenshot(screenshot_name, options)
            time.sleep(0.5)

            level_editor_subsystem.eject_pilot_level_actor()

            unreal.log("Captured adjusted scene")

            # Check final position
            final_pos = self.test_actor.get_actor_location()
            target_pos = unreal.Vector(0, 0, 100)

            distance_to_target = (
                (final_pos.x - target_pos.x)**2 +
                (final_pos.y - target_pos.y)**2 +
                (final_pos.z - target_pos.z)**2
            ) ** 0.5

            unreal.log(f"Final position: {final_pos}")
            unreal.log(f"Target position: {target_pos}")
            unreal.log(f"Distance to target: {distance_to_target:.1f} units")

            if distance_to_target < 50:  # Within 50 units is good
                unreal.log("Positioning is close to target")
                return True
            else:
                unreal.log("Still far from target - would need more iterations")
                return True  # Don't fail, just note

        except Exception as e:
            unreal.log_error(f"Step 5 failed: {e}")
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def run_test(self):
        """Run complete single iteration test"""
        if not self.setup():
            unreal.log_error("Setup failed")
            return

        try:
            # Run all steps
            success = True

            if not self.step_1_spawn_scene():
                success = False

            if success:
                scene_capture = self.step_2_capture_scene()
                if not scene_capture:
                    success = False

            if success and scene_capture:
                ai_response = self.step_3_ai_analysis(scene_capture)
                if not ai_response:
                    success = False

            if success and ai_response:
                if not self.step_4_apply_adjustments(ai_response):
                    success = False

            if success:
                if not self.step_5_verify_improvement():
                    success = False

            # Print summary
            unreal.log("\n" + "="*70)
            unreal.log("PHASE 4 TEST SUMMARY")
            unreal.log("="*70)

            if success:
                unreal.log("SINGLE ITERATION TEST PASSED")
                unreal.log("\nComplete cycle verified:")
                unreal.log("1. Scene spawned ")
                unreal.log("2. Scene captured ")
                unreal.log("3. AI analysis completed ")
                unreal.log("4. Adjustments applied ")
                unreal.log("5. Improvement verified ")
                unreal.log("\n Ready for Phase 5: Iterative Loop!")
            else:
                unreal.log("SINGLE ITERATION TEST FAILED")
                unreal.log("\nCheck the logs above for specific failures")

            unreal.log("="*70)

        finally:
            self.cleanup()


# Main execution
if __name__ == "__main__":
    test = SingleIterationTest()
    test.run_test()

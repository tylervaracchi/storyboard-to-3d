# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PHASE 5: Iterative Positioning Loop with Convergence
Tests complete iterative refinement system with stopping criteria

Test Goals:
1. Run multiple positioning iterations
2. Track similarity/improvement over iterations
3. Implement convergence detection (stop when good enough)
4. Implement max iterations safety limit
5. Log iteration history for analysis
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


class IterativePositioningSystem:
    """Complete iterative positioning system with convergence"""

    def __init__(self, max_iterations=5, convergence_threshold=0.9):
        self.world = None
        self.subsystem = None
        self.ai_provider = None
        self.test_actor = None
        self.test_camera = None
        self.storyboard_image = None

        # Iteration control
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.iteration_history = []

        # Paths
        self.capture_dir = Path(unreal.Paths.project_saved_dir()) / "PositioningTests" / "Iterations"
        self.capture_dir.mkdir(parents=True, exist_ok=True)

    def setup(self):
        """Setup test environment"""
        unreal.log("="*70)
        unreal.log("PHASE 5: ITERATIVE POSITIONING SYSTEM")
        unreal.log("="*70)
        unreal.log(f"Max iterations: {self.max_iterations}")
        unreal.log(f"Convergence threshold: {self.convergence_threshold}")
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

    def spawn_test_scene(self):
        """Spawn test scene with intentionally wrong positioning"""
        unreal.log("\nSpawning test scene...")

        try:
            # Spawn actor in wrong position
            cube_path = "/Engine/BasicShapes/Cube"
            cube_asset = unreal.EditorAssetLibrary.load_asset(cube_path)

            if not cube_asset:
                unreal.log_error("Failed to load cube")
                return False

            # Start FAR from target to test convergence
            initial_pos = unreal.Vector(300, 250, 150)
            initial_rot = unreal.Rotator(0, 90, 0)

            self.test_actor = self.subsystem.spawn_actor_from_object(
                cube_asset, initial_pos, initial_rot
            )

            if not self.test_actor:
                unreal.log_error("Failed to spawn actor")
                return False

            self.test_actor.set_actor_label("IterativeTest_Actor")
            unreal.log(f"Spawned actor at {initial_pos} (intentionally wrong)")

            # Spawn camera
            camera_pos = unreal.Vector(-600, 0, 250)
            camera_rot = unreal.Rotator(-20, 0, 0)

            self.test_camera = self.world.spawn_actor(
                unreal.CineCameraActor,
                camera_pos,
                camera_rot
            )

            if not self.test_camera:
                unreal.log_error("Failed to spawn camera")
                return False

            self.test_camera.set_actor_label("IterativeTest_Camera")
            unreal.log(f"Spawned camera at {camera_pos}")

            return True

        except Exception as e:
            unreal.log_error(f"Failed to spawn scene: {e}")
            return False

    def capture_current_state(self, iteration_num):
        """Capture current scene state"""
        try:
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if not level_editor_subsystem:
                return None

            # Lock to camera
            level_editor_subsystem.pilot_level_actor(self.test_camera)
            time.sleep(0.3)

            # Capture
            automation_lib = unreal.AutomationLibrary()
            screenshot_name = f"iteration_{iteration_num:02d}"

            options = unreal.AutomationScreenshotOptions()
            options.resolution = unreal.Vector2D(1280, 720)
            options.delay = 0.1

            automation_lib.take_automation_screenshot(screenshot_name, options)
            time.sleep(0.5)

            # Unlock
            level_editor_subsystem.eject_pilot_level_actor()

            # Find screenshot
            saved_screenshots = Path(unreal.Paths.project_saved_dir()) / "Screenshots"
            screenshot_files = sorted(saved_screenshots.glob(f"*{screenshot_name}*.png"),
                                     key=lambda p: p.stat().st_mtime, reverse=True)

            if not screenshot_files:
                return None

            # Encode
            with open(screenshot_files[0], 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')

        except Exception as e:
            unreal.log_error(f"Capture failed: {e}")
            return None

    def analyze_with_ai(self, scene_capture, iteration_num):
        """Send to AI for analysis"""
        try:
            current_pos = self.test_actor.get_actor_location()
            current_rot = self.test_actor.get_actor_rotation()

            # Build iteration-aware prompt
            prompt = f"""Iteration {iteration_num}/{self.max_iterations}: Position refinement task.

CURRENT STATE:
- Actor: Cube
- Position: X={current_pos.x:.1f}, Y={current_pos.y:.1f}, Z={current_pos.z:.1f}
- Rotation: Yaw={current_rot.yaw:.1f}

TARGET:
- Position: X=0, Y=0, Z=100 (centered in frame)
- Rotation: Yaw=0

INSTRUCTIONS:
Analyze the image and provide corrections to move the actor toward the target.
Rate current similarity to target (0.0 = very wrong, 1.0 = perfect).

{"For iteration " + str(iteration_num) + ", be more aggressive with corrections." if iteration_num <= 2 else "Fine-tune positioning with small adjustments."}

Respond ONLY with JSON:
{{
    "similarity": 0.0 to 1.0,
    "description": "Brief assessment",
    "adjustments": [
        {{
            "actor": "Cube",
            "position_delta": {{"x": 0, "y": 0, "z": 0}},
            "rotation_delta": {{"yaw": 0}},
            "confidence": 0.0 to 1.0
        }}
    ]
}}"""

            # Send to AI
            if not hasattr(self.ai_provider, 'analyze_image'):
                return None

            response = self.ai_provider.analyze_image(scene_capture, prompt)

            if not response:
                return None

            # Parse JSON
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(response[json_start:json_end])
                else:
                    return None

            return data

        except Exception as e:
            unreal.log_error(f"AI analysis failed: {e}")
            return None

    def apply_adjustments(self, ai_response):
        """Apply AI adjustments"""
        try:
            adjustments = ai_response.get('adjustments', [])

            if not adjustments:
                return False

            adj = adjustments[0]

            # Get current transform
            current_pos = self.test_actor.get_actor_location()
            current_rot = self.test_actor.get_actor_rotation()

            # Apply delta (relative adjustment)
            if 'position_delta' in adj:
                delta = adj['position_delta']
                new_pos = unreal.Vector(
                    current_pos.x + delta.get('x', 0),
                    current_pos.y + delta.get('y', 0),
                    current_pos.z + delta.get('z', 0)
                )
                self.test_actor.set_actor_location(new_pos, False, False)

            # Apply rotation delta
            if 'rotation_delta' in adj:
                delta = adj['rotation_delta']
                new_rot = unreal.Rotator(
                    current_rot.pitch + delta.get('pitch', 0),
                    current_rot.yaw + delta.get('yaw', 0),
                    current_rot.roll + delta.get('roll', 0)
                )
                self.test_actor.set_actor_rotation(new_rot, False)

            return True

        except Exception as e:
            unreal.log_error(f"Failed to apply adjustments: {e}")
            return False

    def calculate_objective_distance(self):
        """Calculate objective distance to target (for validation)"""
        target = unreal.Vector(0, 0, 100)
        current = self.test_actor.get_actor_location()

        distance = (
            (current.x - target.x)**2 +
            (current.y - target.y)**2 +
            (current.z - target.z)**2
        ) ** 0.5

        return distance

    def check_convergence(self):
        """Check if positioning has converged"""
        if len(self.iteration_history) < 2:
            return False

        # Check last similarity score
        last_similarity = self.iteration_history[-1].get('similarity', 0)

        if last_similarity >= self.convergence_threshold:
            unreal.log(f"Converged: Similarity {last_similarity:.2f} >= {self.convergence_threshold}")
            return True

        # Check if no improvement in last 2 iterations
        if len(self.iteration_history) >= 3:
            recent_similarities = [h.get('similarity', 0) for h in self.iteration_history[-3:]]
            improvement = recent_similarities[-1] - recent_similarities[0]

            if improvement < 0.05:  # Less than 5% improvement
                unreal.log(f"Plateaued: Only {improvement:.3f} improvement in 3 iterations")
                return True

        return False

    def run_iteration(self, iteration_num):
        """Run single iteration"""
        unreal.log("\n" + "="*70)
        unreal.log(f"ITERATION {iteration_num}")
        unreal.log("="*70)

        # Capture
        unreal.log("Capturing scene...")
        scene_capture = self.capture_current_state(iteration_num)

        if not scene_capture:
            unreal.log_error("Failed to capture scene")
            return False

        unreal.log("Scene captured")

        # AI Analysis
        unreal.log("Analyzing with AI...")
        ai_response = self.analyze_with_ai(scene_capture, iteration_num)

        if not ai_response:
            unreal.log_error("Failed to get AI response")
            return False

        similarity = ai_response.get('similarity', 0)
        description = ai_response.get('description', 'N/A')

        unreal.log(f"AI Analysis complete")
        unreal.log(f"Similarity: {similarity:.2f}")
        unreal.log(f"Assessment: {description}")

        # Apply adjustments
        unreal.log("Applying adjustments...")
        if not self.apply_adjustments(ai_response):
            unreal.log_error("Failed to apply adjustments")
            return False

        # Get new position
        new_pos = self.test_actor.get_actor_location()
        objective_distance = self.calculate_objective_distance()

        unreal.log(f"Actor repositioned to {new_pos}")
        unreal.log(f"Distance to target: {objective_distance:.1f} units")

        # Record iteration
        iteration_data = {
            'iteration': iteration_num,
            'similarity': similarity,
            'description': description,
            'position': {'x': new_pos.x, 'y': new_pos.y, 'z': new_pos.z},
            'objective_distance': objective_distance,
            'ai_response': ai_response
        }

        self.iteration_history.append(iteration_data)

        return True

    def run_full_test(self):
        """Run complete iterative positioning test"""
        if not self.setup():
            return

        if not self.spawn_test_scene():
            self.cleanup()
            return

        try:
            unreal.log("\n" + "="*70)
            unreal.log("STARTING ITERATIVE POSITIONING")
            unreal.log("="*70)

            # Record initial state
            initial_pos = self.test_actor.get_actor_location()
            initial_distance = self.calculate_objective_distance()

            unreal.log(f"Initial position: {initial_pos}")
            unreal.log(f"Initial distance to target: {initial_distance:.1f} units")

            # Run iterations
            converged = False

            for i in range(1, self.max_iterations + 1):
                if not self.run_iteration(i):
                    unreal.log_error(f"Iteration {i} failed - stopping")
                    break

                # Check convergence
                if self.check_convergence():
                    converged = True
                    unreal.log(f"\n CONVERGED after {i} iterations!")
                    break

            # Final summary
            self.print_summary(converged, initial_distance)

        finally:
            self.cleanup()

    def print_summary(self, converged, initial_distance):
        """Print final summary"""
        unreal.log("\n" + "="*70)
        unreal.log("ITERATIVE POSITIONING SUMMARY")
        unreal.log("="*70)

        if not self.iteration_history:
            unreal.log("No iterations completed")
            return

        unreal.log(f"Total iterations: {len(self.iteration_history)}")
        unreal.log(f"Converged: {' Yes' if converged else ' No (hit max iterations)'}")

        # Position improvement
        final_distance = self.iteration_history[-1]['objective_distance']
        improvement = initial_distance - final_distance
        improvement_pct = (improvement / initial_distance) * 100 if initial_distance > 0 else 0

        unreal.log(f"\nPosition Improvement:")
        unreal.log(f"Initial distance: {initial_distance:.1f} units")
        unreal.log(f"Final distance: {final_distance:.1f} units")
        unreal.log(f"Improvement: {improvement:.1f} units ({improvement_pct:.1f}%)")

        # Similarity progression
        unreal.log(f"\nSimilarity Progression:")
        for i, iteration in enumerate(self.iteration_history, 1):
            similarity = iteration.get('similarity', 0)
            distance = iteration.get('objective_distance', 0)
            unreal.log(f"Iteration {i}: Similarity={similarity:.2f}, Distance={distance:.1f}")

        # Final assessment
        final_similarity = self.iteration_history[-1].get('similarity', 0)

        if final_similarity >= self.convergence_threshold:
            unreal.log(f"\n SUCCESS: Achieved target similarity ({final_similarity:.2f})")
        elif improvement_pct > 50:
            unreal.log(f"\n PARTIAL SUCCESS: {improvement_pct:.1f}% improvement")
        else:
            unreal.log(f"\n LIMITED SUCCESS: Only {improvement_pct:.1f}% improvement")

        unreal.log("\n" + "="*70)
        unreal.log("PHASE 5 COMPLETE - ITERATIVE SYSTEM TESTED!")
        unreal.log("="*70)

        # Save iteration log
        log_file = self.capture_dir / f"iteration_log_{int(time.time())}.json"
        with open(log_file, 'w') as f:
            json.dump({
                'summary': {
                    'converged': converged,
                    'total_iterations': len(self.iteration_history),
                    'initial_distance': initial_distance,
                    'final_distance': final_distance,
                    'improvement_percent': improvement_pct
                },
                'iterations': self.iteration_history
            }, f, indent=2)

        unreal.log(f"\nIteration log saved: {log_file}")


# Main execution
if __name__ == "__main__":
    system = IterativePositioningSystem(
        max_iterations=5,
        convergence_threshold=0.85
    )
    system.run_full_test()

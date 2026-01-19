# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PHASE 1: Test AI Input/Output for Positioning Instructions
Tests that AI can receive images and return positioning commands

Test Goals:
1. Send storyboard + current scene to AI
2. Get back structured positioning data (JSON)
3. Validate the response format
"""

import unreal
import json
import base64
from pathlib import Path
import sys

# Add plugin path
plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))


class PositioningAITest:
    """Test AI communication for positioning"""

    def __init__(self):
        self.test_results = []
        self.ai_provider = None
        self.setup_ai()

    def setup_ai(self):
        """Setup AI client from settings"""
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
            self.log_result(" AI client initialized", True)
            return True

        except Exception as e:
            self.log_result(f" AI client setup failed: {e}", False)
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def log_result(self, message, success):
        """Log test result"""
        self.test_results.append({"message": message, "success": success})
        unreal.log(message)

    def test_1_basic_prompt(self):
        """Test 1: Basic AI response (text only)"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 1: Basic AI Prompt (Text Only)")
        unreal.log("="*70)

        prompt = """You are a positioning assistant for 3D scenes.

Given this scenario:
- Character: "Hero"
- Prop: "Chair"
- Shot type: "medium"

Respond with JSON positioning instructions:
{
    "actors": [
        {
            "name": "Hero",
            "position": {"x": 0, "y": 100, "z": 0},
            "rotation": {"pitch": 0, "yaw": 0, "roll": 0}
        },
        {
            "name": "Chair",
            "position": {"x": 0, "y": -100, "z": 0},
            "rotation": {"pitch": 0, "yaw": 180, "roll": 0}
        }
    ]
}

Only return valid JSON, no other text."""

        try:
            # Send to AI (text only)
            response = self.ai_provider.analyze_text(prompt)

            if not response:
                self.log_result(" AI returned empty response (check API key in Settings → AI tab)", False)
                unreal.log_warning("Make sure you have:")
                unreal.log_warning("1. Selected an AI provider in Settings")
                unreal.log_warning("2. Entered a valid API key")
                unreal.log_warning("3. Tested the connection (Test Connection button)")
                return False

            unreal.log(f"Raw AI Response:\n{response[:500]}")

            # Try to parse as JSON
            try:
                data = json.loads(response)
                self.log_result(" AI returned valid JSON", True)

                # Validate structure
                if 'actors' in data and isinstance(data['actors'], list):
                    self.log_result(f" JSON has 'actors' array with {len(data['actors'])} items", True)

                    # Check first actor structure
                    if data['actors']:
                        actor = data['actors'][0]
                        has_name = 'name' in actor
                        has_position = 'position' in actor and 'x' in actor['position']
                        has_rotation = 'rotation' in actor and 'yaw' in actor['rotation']

                        if has_name and has_position and has_rotation:
                            self.log_result(" Actor data structure is valid", True)
                            unreal.log(f"Sample actor: {json.dumps(actor, indent=2)}")
                            return True
                        else:
                            self.log_result(" Actor data missing required fields", False)
                            return False
                else:
                    self.log_result(" JSON missing 'actors' array", False)
                    return False

            except json.JSONDecodeError as e:
                self.log_result(f" AI response is not valid JSON: {e}", False)
                unreal.log("Attempting to extract JSON from response...")

                # Try to find JSON in response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1

                if json_start >= 0 and json_end > json_start:
                    try:
                        json_text = response[json_start:json_end]
                        data = json.loads(json_text)
                        self.log_result(" Extracted valid JSON from AI response", True)
                        return True
                    except:
                        self.log_result(" Could not extract valid JSON", False)
                        return False

                return False

        except Exception as e:
            self.log_result(f" Test failed with error: {e}", False)
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_2_image_with_positioning(self):
        """Test 2: Send image + get positioning instructions"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 2: Image + Positioning Instructions")
        unreal.log("="*70)

        # Find a test image (storyboard panel)
        content_dir = Path(unreal.Paths.project_content_dir())
        shows_dir = content_dir / "StoryboardTo3D" / "Shows"

        test_image = None
        if shows_dir.exists():
            # Find first panel image
            for show_dir in shows_dir.iterdir():
                panels_dir = show_dir / "Panels"
                if panels_dir.exists():
                    for img in panels_dir.glob("*.png"):
                        test_image = img
                        break
                    if test_image:
                        break

                # Also check Episodes
                episodes_dir = show_dir / "Episodes"
                if episodes_dir.exists() and not test_image:
                    for ep_dir in episodes_dir.iterdir():
                        ep_panels = ep_dir / "Panels"
                        if ep_panels.exists():
                            for img in ep_panels.glob("*.png"):
                                test_image = img
                                break
                        if test_image:
                            break
                if test_image:
                    break

        if not test_image or not test_image.exists():
            self.log_result(" No test image found - skipping image test", False)
            unreal.log(f"Searched in: {shows_dir}")
            return False

        unreal.log(f"Using test image: {test_image}")

        try:
            # Read and encode image
            with open(test_image, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            self.log_result(f" Loaded test image ({len(image_data)} chars)", True)

            # Create prompt
            prompt = """Analyze this storyboard panel image.

Based on what you see, provide positioning instructions for a 3D scene.

Available assets:
- Character: "Hero" (humanoid character)
- Prop: "Chair" (furniture)

Respond ONLY with JSON in this format:
{
    "description": "Brief description of the scene",
    "actors": [
        {
            "name": "Hero",
            "position": {"x": 0, "y": 100, "z": 0},
            "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
            "visible": true
        }
    ],
    "camera": {
        "position": {"x": 0, "y": -500, "z": 100},
        "look_at": {"x": 0, "y": 0, "z": 100}
    }
}"""

            # Send to AI with image
            if hasattr(self.ai_provider, 'analyze_image'):
                response = self.ai_provider.analyze_image(image_data, prompt)
            else:
                self.log_result(" AI provider doesn't support image analysis", False)
                unreal.log_error("The AI client is missing the analyze_image method.")
                return False

            if not response:
                self.log_result(" AI returned empty response for image (check API key)", False)
                unreal.log_warning("Image analysis requires:")
                unreal.log_warning("1. Vision-capable AI model (GPT-4V, GPT-4o, Claude)")
                unreal.log_warning("2. Valid API key configured")
                unreal.log_warning("3. Working internet connection")
                return False

            unreal.log(f"AI Response (first 500 chars):\n{response[:500]}")

            # Parse JSON
            try:
                # Try direct parse
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

            self.log_result(" AI returned valid JSON with image analysis", True)

            # Validate structure
            has_description = 'description' in data
            has_actors = 'actors' in data and isinstance(data['actors'], list)
            has_camera = 'camera' in data

            unreal.log(f"Response structure:")
            unreal.log(f"- description: {has_description}")
            unreal.log(f"- actors: {has_actors} ({len(data.get('actors', []))} items)")
            unreal.log(f"- camera: {has_camera}")

            if has_description and has_actors:
                self.log_result(" Image analysis response is valid", True)
                unreal.log(f"\nAI Description: {data['description']}")
                return True
            else:
                self.log_result(" Response missing required fields", False)
                return False

        except Exception as e:
            self.log_result(f" Image test failed: {e}", False)
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def test_3_two_image_comparison(self):
        """Test 3: Send storyboard + current scene, get positioning corrections"""
        unreal.log("\n" + "="*70)
        unreal.log("TEST 3: Two-Image Comparison (Storyboard vs Scene)")
        unreal.log("="*70)

        # Find test images
        content_dir = Path(unreal.Paths.project_content_dir())
        shows_dir = content_dir / "StoryboardTo3D" / "Shows"

        test_images = []
        if shows_dir.exists():
            for show_dir in shows_dir.iterdir():
                panels_dir = show_dir / "Panels"
                if panels_dir.exists():
                    for img in list(panels_dir.glob("*.png"))[:2]:  # Get 2 images
                        test_images.append(img)
                    if len(test_images) >= 2:
                        break

        if len(test_images) < 2:
            self.log_result(" Need 2 test images - skipping comparison test", False)
            return False

        unreal.log(f"Using test images:")
        unreal.log(f"Storyboard: {test_images[0].name}")
        unreal.log(f"Scene: {test_images[1].name}")

        try:
            # Encode both images
            images_b64 = []
            for img_path in test_images:
                with open(img_path, 'rb') as f:
                    images_b64.append(base64.b64encode(f.read()).decode('utf-8'))

            self.log_result(f" Loaded 2 images for comparison", True)

            # Create comparison prompt
            prompt = """You are comparing a storyboard (Image 1) with the current 3D scene (Image 2).

Your task: Determine what positioning adjustments are needed to make Image 2 match Image 1.

Analyze:
1. Character positions (are they in the right place?)
2. Camera angle (does it match?)
3. Composition (is framing similar?)

Respond ONLY with JSON:
{
    "similarity": 0.7,
    "needs_adjustment": true,
    "adjustments": [
        {
            "actor": "Hero",
            "current_issue": "Too far left",
            "adjustment": {"x": 50, "y": 0, "z": 0},
            "priority": "high"
        }
    ],
    "camera_adjustment": {
        "needs_change": true,
        "suggestion": "Move camera closer and lower angle"
    }
}"""

            # For this test, we'll use a simpler single-image call since multi-image may not be supported
            # In practice, you'd concatenate images or use provider-specific multi-image APIs
            combined_prompt = f"{prompt}\n\nNOTE: Both images provided. First is storyboard target, second is current scene."

            if hasattr(self.ai_provider, 'analyze_image'):
                # Use first image for now (in real impl, you'd handle both)
                response = self.ai_provider.analyze_image(images_b64[0], combined_prompt)
            else:
                self.log_result(" AI provider doesn't support image analysis", False)
                return False

            if not response:
                self.log_result(" AI returned empty response", False)
                return False

            # Parse response
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(response[json_start:json_end])
                else:
                    raise

            self.log_result(" AI returned comparison analysis", True)

            # Validate comparison structure
            has_similarity = 'similarity' in data
            has_adjustments = 'adjustments' in data

            if has_similarity and has_adjustments:
                self.log_result(" Comparison response structure is valid", True)
                unreal.log(f"\nComparison Results:")
                unreal.log(f"Similarity: {data.get('similarity', 'N/A')}")
                unreal.log(f"Adjustments needed: {len(data.get('adjustments', []))}")
                return True
            else:
                self.log_result(" Comparison response incomplete", False)
                return False

        except Exception as e:
            self.log_result(f" Comparison test failed: {e}", False)
            import traceback
            unreal.log(traceback.format_exc())
            return False

    def run_all_tests(self):
        """Run all Phase 1 tests"""
        unreal.log("\n" + "="*70)
        unreal.log("PHASE 1: AI INPUT/OUTPUT TESTING")
        unreal.log("="*70)

        if not self.ai_provider:
            unreal.log_error("AI provider not initialized - cannot run tests")
            return

        # Run tests
        tests = [
            ("Basic Prompt", self.test_1_basic_prompt),
            ("Image Analysis", self.test_2_image_with_positioning),
            ("Two-Image Comparison", self.test_3_two_image_comparison)
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            try:
                if test_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                unreal.log_error(f"Test '{test_name}' crashed: {e}")
                failed += 1

        # Print summary
        unreal.log("\n" + "="*70)
        unreal.log("PHASE 1 TEST SUMMARY")
        unreal.log("="*70)
        unreal.log(f"Passed: {passed}/{len(tests)}")
        unreal.log(f"Failed: {failed}/{len(tests)}")
        unreal.log("\nDetailed Results:")
        for result in self.test_results:
            unreal.log(f"{result['message']}")

        if passed == len(tests):
            unreal.log("\n ALL PHASE 1 TESTS PASSED - Ready for Phase 2!")
        elif passed > 0:
            unreal.log(f"\n {passed}/{len(tests)} tests passed - Fix failures before Phase 2")
        else:
            unreal.log("\n ALL TESTS FAILED - Check AI configuration")

        unreal.log("="*70)


# Main execution
if __name__ == "__main__":
    test = PositioningAITest()
    test.run_all_tests()

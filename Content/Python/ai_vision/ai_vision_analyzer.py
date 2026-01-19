# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
AI Vision Analyzer for StoryboardTo3D
Integrates with Ollama/LLaVA for intelligent scene comparison
"""

import unreal
import json
import base64
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Try importing requests for API calls
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    unreal.log_warning("[AIVisionAnalyzer] requests not available. Install with: pip install requests")

# Import existing AI infrastructure
try:
    from api.local_ai_manager import OllamaProvider, InternVL2SceneBuilder
    LOCAL_AI_AVAILABLE = True
except ImportError:
    LOCAL_AI_AVAILABLE = False
    unreal.log_warning("[AIVisionAnalyzer] local_ai_manager not available")

class AIVisionAnalyzer:
    """
    AI-powered vision analysis using LLaVA/InternVL2 for scene comparison
    """

    # Recommended vision models for scene comparison
    VISION_MODELS = {
        'llava:13b': {
            'description': 'LLaVA 13B - General vision model',
            'size': '26GB',
            'quality': 'Good',
            'speed': 'Medium'
        },
        'llava:34b': {
            'description': 'LLaVA 34B - Larger, more accurate',
            'size': '68GB',
            'quality': 'Excellent',
            'speed': 'Slow'
        },
        'bakllava:latest': {
            'description': 'BakLLaVA - Optimized LLaVA',
            'size': '15GB',
            'quality': 'Good',
            'speed': 'Fast'
        },
        'internvl2:8b': {
            'description': 'InternVL2 - Best for viewport matching',
            'size': '16GB',
            'quality': 'Excellent',
            'speed': 'Fast'
        }
    }

    def __init__(self, model: str = 'internvl2:8b', endpoint: str = 'http://localhost:11434'):
        """
        Initialize AI Vision Analyzer

        Args:
            model: Vision model to use
            endpoint: Ollama endpoint URL
        """
        self.model = model
        self.endpoint = endpoint
        self.api_base = f"{endpoint}/api"

        # Try to use existing InternVL2 builder if available
        self.scene_builder = None
        if LOCAL_AI_AVAILABLE:
            from api.local_ai_manager import get_scene_builder
            self.scene_builder = get_scene_builder()
            unreal.log("[AIVisionAnalyzer] Using existing InternVL2 scene builder")

        # Ollama provider for model management
        self.ollama = None
        if LOCAL_AI_AVAILABLE:
            self.ollama = OllamaProvider(endpoint)

        # Check if Ollama is running
        self.is_connected = False
        self.check_connection()

        unreal.log(f"[AIVisionAnalyzer] Initialized with model: {model}")

    def check_connection(self) -> bool:
        """Check if Ollama is running and model is available"""
        if not REQUESTS_AVAILABLE:
            unreal.log_error("[AIVisionAnalyzer] requests module not available")
            return False

        try:
            # Check Ollama status
            response = requests.get(f"{self.api_base}/tags", timeout=2)
            if response.status_code != 200:
                unreal.log_error("[AIVisionAnalyzer] Ollama not responding")
                self.is_connected = False
                return False

            # Check if model is available
            data = response.json()
            models = data.get("models", [])
            model_names = [m.get("name", "") for m in models]

            if not any(self.model in name for name in model_names):
                unreal.log_warning(f"[AIVisionAnalyzer] Model {self.model} not installed")
                unreal.log(f"[AIVisionAnalyzer] Available models: {model_names}")
                self.is_connected = False
                return False

            self.is_connected = True
            unreal.log(f"[AIVisionAnalyzer]  Connected to Ollama with {self.model}")
            return True

        except Exception as e:
            unreal.log_error(f"[AIVisionAnalyzer] Connection check failed: {e}")
            self.is_connected = False
            return False

    def install_model(self, model_name: Optional[str] = None) -> bool:
        """
        Install a vision model via Ollama

        Args:
            model_name: Model to install (uses default if None)

        Returns:
            Success status
        """
        model_name = model_name or self.model

        if not self.ollama:
            unreal.log_error("[AIVisionAnalyzer] Ollama provider not available")
            return False

        unreal.log(f"[AIVisionAnalyzer] Installing model: {model_name}")
        unreal.log(f"[AIVisionAnalyzer] This may take several minutes...")

        success = self.ollama.install_model(model_name)

        if success:
            unreal.log(f"[AIVisionAnalyzer]  Model {model_name} installed successfully")
            self.check_connection()
        else:
            unreal.log_error(f"[AIVisionAnalyzer] Failed to install {model_name}")

        return success

    def compare_scene_with_ai(self,
                             storyboard_path: str,
                             viewport_path: str,
                             focus_areas: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Use AI to compare storyboard to viewport

        Args:
            storyboard_path: Path to storyboard image
            viewport_path: Path to viewport capture
            focus_areas: Specific areas to focus on (composition, lighting, etc.)

        Returns:
            AI analysis results
        """
        unreal.log("[AIVisionAnalyzer] Starting AI scene comparison")

        # Check connection
        if not self.is_connected:
            if not self.check_connection():
                return self._fallback_comparison(storyboard_path, viewport_path)

        # Use InternVL2 scene builder if available
        if self.scene_builder and hasattr(self.scene_builder, 'compare_viewport_to_storyboard'):
            unreal.log("[AIVisionAnalyzer] Using InternVL2 scene builder")
            return self.scene_builder.compare_viewport_to_storyboard(viewport_path, storyboard_path)

        # Otherwise use direct Ollama API
        try:
            # Read images
            with open(storyboard_path, "rb") as f:
                storyboard_b64 = base64.b64encode(f.read()).decode('utf-8')
            with open(viewport_path, "rb") as f:
                viewport_b64 = base64.b64encode(f.read()).decode('utf-8')

            # Build comparison prompt
            prompt = self._build_comparison_prompt(focus_areas)

            # Make API call
            response = self._call_vision_api(prompt, [storyboard_b64, viewport_b64])

            if response:
                return self._parse_ai_response(response)
            else:
                return self._fallback_comparison(storyboard_path, viewport_path)

        except Exception as e:
            unreal.log_error(f"[AIVisionAnalyzer] AI comparison failed: {e}")
            return self._fallback_comparison(storyboard_path, viewport_path)

    def _build_comparison_prompt(self, focus_areas: Optional[List[str]] = None) -> str:
        """Build prompt for scene comparison"""

        prompt = """You are comparing two images:
1. FIRST IMAGE: Target storyboard panel
2. SECOND IMAGE: Current 3D viewport render

Analyze how well the viewport matches the storyboard and provide:

OVERALL MATCH (0-100%):
- Overall similarity percentage

COMPOSITION ANALYSIS:
- Camera angle match (perfect/good/needs adjustment)
- Framing match (correct/too wide/too tight)
- Subject positioning (accurate/needs repositioning)

LIGHTING ANALYSIS:
- Light direction match (accurate/needs adjustment)
- Mood/atmosphere match (perfect/good/different)
- Brightness match (correct/too dark/too bright)

CONTENT ANALYSIS:
- Are all important objects present? (yes/missing items)
- Character positions correct? (yes/needs adjustment)
- Background elements match? (yes/different)

SPECIFIC ADJUSTMENTS NEEDED:
- Camera: [specific movements needed]
- Lighting: [specific changes needed]
- Objects: [what to add/remove/reposition]

CONFIDENCE: How confident are you in this analysis (0-100%)

Return as JSON with keys: overall_match, composition, lighting, content, adjustments, confidence"""

        if focus_areas:
            prompt += f"\n\nFocus especially on: {', '.join(focus_areas)}"

        return prompt

    def _call_vision_api(self, prompt: str, images: List[str]) -> Optional[Dict[str, Any]]:
        """Call Ollama vision API"""
        if not REQUESTS_AVAILABLE:
            return None

        request_data = {
            "model": self.model,
            "prompt": prompt,
            "images": images,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent analysis
                "num_predict": 2000
            }
        }

        try:
            unreal.log(f"[AIVisionAnalyzer] Calling {self.model} for comparison...")

            response = requests.post(
                f"{self.api_base}/generate",
                json=request_data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "{}")

                # Try to parse JSON
                try:
                    # Clean response
                    if "```json" in response_text:
                        start = response_text.find("```json") + 7
                        end = response_text.find("```", start)
                        if end > start:
                            response_text = response_text[start:end].strip()

                    parsed = json.loads(response_text)
                    unreal.log("[AIVisionAnalyzer] Successfully parsed AI response")
                    return parsed

                except json.JSONDecodeError:
                    # Try to extract JSON from response
                    if "{" in response_text:
                        start = response_text.find("{")
                        end = response_text.rfind("}") + 1
                        try:
                            parsed = json.loads(response_text[start:end])
                            return parsed
                        except:
                            pass

                    unreal.log_warning("[AIVisionAnalyzer] Could not parse JSON response")
                    return {"raw_response": response_text}
            else:
                unreal.log_error(f"[AIVisionAnalyzer] API error: {response.status_code}")
                return None

        except Exception as e:
            unreal.log_error(f"[AIVisionAnalyzer] API call failed: {e}")
            return None

    def _parse_ai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and structure AI response"""

        # Ensure required fields
        result = {
            'overall_match': response.get('overall_match', 50),
            'composition': response.get('composition', {}),
            'lighting': response.get('lighting', {}),
            'content': response.get('content', {}),
            'adjustments': response.get('adjustments', {}),
            'confidence': response.get('confidence', 70),
            'ai_model': self.model,
            'analysis_type': 'ai_vision'
        }

        # Add recommendations based on match
        match = result['overall_match']
        recommendations = []

        if match < 30:
            recommendations.append(" Major adjustments needed")
        elif match < 60:
            recommendations.append(" Moderate adjustments recommended")
        elif match < 80:
            recommendations.append(" Minor tweaks would help")
        else:
            recommendations.append(" Excellent match!")

        # Add specific recommendations from adjustments
        if result['adjustments']:
            if 'camera' in result['adjustments']:
                recommendations.append(f" Camera: {result['adjustments']['camera']}")
            if 'lighting' in result['adjustments']:
                recommendations.append(f" Lighting: {result['adjustments']['lighting']}")
            if 'objects' in result['adjustments']:
                recommendations.append(f" Objects: {result['adjustments']['objects']}")

        result['recommendations'] = recommendations

        return result

    def _fallback_comparison(self, storyboard_path: str, viewport_path: str) -> Dict[str, Any]:
        """Fallback comparison when AI is not available"""
        unreal.log("[AIVisionAnalyzer] Using fallback comparison (AI not available)")

        # Use basic scene matcher if available
        from ai_vision.scene_matcher import SceneMatcher
        matcher = SceneMatcher()
        basic_result = matcher.compare_images(storyboard_path, viewport_path, detailed=False)

        # Add AI-specific fields
        basic_result['ai_model'] = 'fallback'
        basic_result['analysis_type'] = 'basic'
        basic_result['confidence'] = 50

        return basic_result

    def analyze_panel_for_3d(self, storyboard_path: str) -> Dict[str, Any]:
        """
        Analyze storyboard panel to extract 3D scene requirements

        Args:
            storyboard_path: Path to storyboard image

        Returns:
            Scene requirements for 3D construction
        """
        unreal.log("[AIVisionAnalyzer] Analyzing panel for 3D requirements")

        # Use InternVL2 if available
        if self.scene_builder and hasattr(self.scene_builder, 'analyze_storyboard_for_scene'):
            return self.scene_builder.analyze_storyboard_for_scene(storyboard_path)

        # Otherwise use direct API
        try:
            with open(storyboard_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode('utf-8')

            prompt = """Analyze this storyboard panel and identify everything needed to recreate it in 3D:

CAMERA:
- Shot type (wide/medium/close-up)
- Camera angle (high/eye-level/low)
- Camera position in scene

CHARACTERS:
- Number of characters
- Positions (foreground/midground/background)
- Actions/poses

OBJECTS/PROPS:
- List all visible objects
- Their positions relative to characters

ENVIRONMENT:
- Interior or exterior
- Time of day
- Weather conditions

LIGHTING:
- Main light direction
- Mood (bright/dark/dramatic)
- Key light position

Return as detailed JSON."""

            response = self._call_vision_api(prompt, [image_b64])

            if response:
                return response
            else:
                return self._basic_panel_analysis(storyboard_path)

        except Exception as e:
            unreal.log_error(f"[AIVisionAnalyzer] Panel analysis failed: {e}")
            return self._basic_panel_analysis(storyboard_path)

    def _basic_panel_analysis(self, storyboard_path: str) -> Dict[str, Any]:
        """Basic panel analysis without AI"""
        return {
            'camera': {'shot_type': 'medium', 'angle': 'eye-level'},
            'characters': [],
            'objects': [],
            'environment': 'interior',
            'lighting': {'mood': 'neutral', 'direction': 'front'},
            'analysis_type': 'basic'
        }

    def suggest_improvements(self, comparison_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate specific improvement suggestions based on comparison

        Args:
            comparison_result: Result from scene comparison

        Returns:
            List of actionable improvements
        """
        improvements = []

        match = comparison_result.get('overall_match', 0)

        # Camera improvements
        if comparison_result.get('composition', {}).get('camera_angle') != 'perfect':
            improvements.append({
                'type': 'camera',
                'priority': 'high',
                'action': 'Adjust camera angle',
                'details': comparison_result.get('adjustments', {}).get('camera', 'Reposition camera')
            })

        # Lighting improvements
        lighting = comparison_result.get('lighting', {})
        if lighting.get('mood_match') != 'perfect':
            improvements.append({
                'type': 'lighting',
                'priority': 'medium',
                'action': 'Adjust lighting',
                'details': comparison_result.get('adjustments', {}).get('lighting', 'Modify light intensity')
            })

        # Content improvements
        content = comparison_result.get('content', {})
        if content.get('missing_items'):
            improvements.append({
                'type': 'objects',
                'priority': 'high',
                'action': 'Add missing objects',
                'details': f"Add: {', '.join(content.get('missing_items', []))}"
            })

        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        improvements.sort(key=lambda x: priority_order.get(x['priority'], 3))

        return improvements

    def iterative_refinement(self,
                           storyboard_path: str,
                           max_iterations: int = 5,
                           target_match: float = 85.0) -> Dict[str, Any]:
        """
        Iteratively refine scene to match storyboard

        Args:
            storyboard_path: Path to target storyboard
            max_iterations: Maximum refinement iterations
            target_match: Target match percentage

        Returns:
            Refinement results
        """
        from ai_vision.viewport_capture import ViewportCapture
        from ai_vision.scene_matcher import SceneMatcher

        capture = ViewportCapture()
        matcher = SceneMatcher()

        unreal.log(f"[AIVisionAnalyzer] Starting iterative refinement (target: {target_match}%)")

        results = {
            'iterations': [],
            'final_match': 0,
            'success': False
        }

        for i in range(max_iterations):
            unreal.log(f"[AIVisionAnalyzer] Iteration {i+1}/{max_iterations}")

            # Capture current viewport
            viewport_path = capture.capture_viewport(f"iteration_{i+1}.png")
            if not viewport_path:
                unreal.log_error("[AIVisionAnalyzer] Failed to capture viewport")
                break

            # Compare with AI
            comparison = self.compare_scene_with_ai(storyboard_path, viewport_path)

            # Get match percentage
            match = comparison.get('overall_match', 0)
            results['iterations'].append({
                'iteration': i+1,
                'match': match,
                'comparison': comparison
            })

            unreal.log(f"[AIVisionAnalyzer] Match: {match}%")

            # Check if target reached
            if match >= target_match:
                results['success'] = True
                results['final_match'] = match
                unreal.log(f"[AIVisionAnalyzer]  Target match reached: {match}%")
                break

            # Apply adjustments
            adjustments = comparison.get('adjustments', {})
            if adjustments:
                self._apply_adjustments(adjustments)

                # Wait for scene to update
                time.sleep(0.5)
            else:
                unreal.log("[AIVisionAnalyzer] No adjustments suggested")
                break

        results['final_match'] = results['iterations'][-1]['match'] if results['iterations'] else 0

        unreal.log(f"[AIVisionAnalyzer] Refinement complete. Final match: {results['final_match']}%")

        return results

    def _apply_adjustments(self, adjustments: Dict[str, Any]):
        """Apply suggested adjustments to the scene"""

        # This would integrate with scene_builder to make actual adjustments
        # For now, just log what would be done

        if 'camera' in adjustments:
            unreal.log(f"[AIVisionAnalyzer] Would adjust camera: {adjustments['camera']}")
            # TODO: Call camera system to make adjustment

        if 'lighting' in adjustments:
            unreal.log(f"[AIVisionAnalyzer] Would adjust lighting: {adjustments['lighting']}")
            # TODO: Call lighting system to make adjustment

        if 'objects' in adjustments:
            unreal.log(f"[AIVisionAnalyzer] Would adjust objects: {adjustments['objects']}")
            # TODO: Call scene builder to make adjustment

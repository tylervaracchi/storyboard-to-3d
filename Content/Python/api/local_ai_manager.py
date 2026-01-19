# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Local AI Integration Manager for StoryboardTo3D
Supports InternVL2 and other local models for viewport matching
"""

import json
import base64
import subprocess
import platform
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from dataclasses import dataclass
import unreal

# Import requests if available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    unreal.log_warning("Requests not available - install with: pip install requests")


class LocalAIProvider(Enum):
    """Available local AI providers"""
    OLLAMA = "Ollama"
    LM_STUDIO = "LM Studio"
    CUSTOM = "Custom"


@dataclass
class ModelInfo:
    """Information about a local model"""
    name: str
    provider: LocalAIProvider
    size: str
    quality: str
    speed: str
    capabilities: List[str]
    requirements: Dict[str, Any]


class InternVL2SceneBuilder:
    """
    Single-model solution using InternVL2 for complete scene building
    Optimized for viewport matching and iterative refinement
    """

    def __init__(self):
        self.model = "internvl2:8b"  # Default to InternVL2
        self.endpoint = "http://localhost:11434/api"

        # Scene state tracking
        self.current_scene_state = {}
        self.iteration_history = []
        self.confidence_threshold = 0.85

        unreal.log("[DEBUG InternVL2] Scene builder initialized")

    def setup(self) -> bool:
        """One-time setup of InternVL2"""
        unreal.log("[DEBUG InternVL2] Starting setup...")

        if not REQUESTS_AVAILABLE:
            unreal.log_error("[DEBUG InternVL2] Requests module not available!")
            return False

        # Check if Ollama is running
        try:
            response = requests.get(f"{self.endpoint}/tags", timeout=2)
            if response.status_code != 200:
                unreal.log("[DEBUG InternVL2] Ollama not running, attempting to start...")
                self.start_ollama_service()
                time.sleep(5)
        except:
            unreal.log("[DEBUG InternVL2] Ollama not reachable, attempting to start...")
            self.start_ollama_service()
            time.sleep(5)

        # Check again after potential start
        try:
            response = requests.get(f"{self.endpoint}/tags", timeout=5)
            if response.status_code != 200:
                unreal.log_error("[DEBUG InternVL2] Failed to connect to Ollama")
                return False

            # Check if model is installed
            data = response.json()
            models = data.get("models", [])
            model_names = [m.get("name", "") for m in models]

            if not any(self.model in name for name in model_names):
                unreal.log(f"[DEBUG InternVL2] Model {self.model} not found, please install it first")
                return False

            unreal.log(f"[DEBUG InternVL2]  {self.model} ready for scene building")
            return True

        except Exception as e:
            unreal.log_error(f"[DEBUG InternVL2] Setup failed: {e}")
            return False

    def start_ollama_service(self):
        """Start Ollama service based on platform"""
        system = platform.system()
        unreal.log(f"[DEBUG InternVL2] Starting Ollama on {system}")

        try:
            if system == "Windows":
                subprocess.Popen(["ollama", "serve"],
                               shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["ollama", "serve"])
            else:  # Linux
                subprocess.Popen(["systemctl", "start", "ollama"])

            unreal.log("[DEBUG InternVL2] Ollama service start command executed")
        except Exception as e:
            unreal.log_error(f"[DEBUG InternVL2] Failed to start Ollama: {e}")

    def analyze_storyboard_for_scene(self, storyboard_path: str) -> Dict[str, Any]:
        """
        Analyze storyboard and identify all assets needed
        """
        unreal.log(f"[DEBUG InternVL2] Analyzing storyboard: {storyboard_path}")

        try:
            with open(storyboard_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            unreal.log_error(f"[DEBUG InternVL2] Failed to read image: {e}")
            return {}

        prompt = """<image>
Analyze this storyboard panel for 3D scene construction.

Identify ALL elements needed to build this scene:

1. CHARACTERS: List each character with position
2. PROPS: List every object with position
3. CAMERA: Shot type and position
4. LIGHTING: Main light direction and mood

Return as JSON with this structure:
{
    "characters": [{"name": "character1", "position": {"x": 0, "y": 0, "z": 0}}],
    "props": [{"name": "desk", "position": {"x": 100, "y": 0, "z": 0}}],
    "camera": {"shot_type": "medium", "position": {"x": -200, "y": 0, "z": 160}},
    "lighting": {"key_light_direction": {"x": 1, "y": 1, "z": -1}, "mood": "neutral"}
}"""

        response = self._call_internvl2(prompt, [image_b64])
        unreal.log(f"[DEBUG InternVL2] Analysis complete: {json.dumps(response)[:200]}...")
        return response

    def compare_viewport_to_storyboard(self, viewport_path: str, storyboard_path: str) -> Dict[str, Any]:
        """
        Compare viewport to storyboard and get precise adjustments
        """
        unreal.log("[DEBUG InternVL2] Comparing viewport to storyboard")

        try:
            with open(viewport_path, "rb") as f:
                viewport_b64 = base64.b64encode(f.read()).decode('utf-8')
            with open(storyboard_path, "rb") as f:
                storyboard_b64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            unreal.log_error(f"[DEBUG InternVL2] Failed to read images: {e}")
            return {"error": str(e)}

        prompt = """<image>
Compare these two images:
1. First: Current 3D viewport
2. Second: Target storyboard

Provide SPECIFIC adjustments to match viewport to storyboard.

Return JSON:
{
    "similarity": 0.75,
    "camera_adjustments": {
        "move": {"x": 0, "y": -50, "z": 10},
        "rotate": {"pitch": 5, "yaw": 0, "roll": 0}
    },
    "confidence": 0.9
}

Be precise with measurements in Unreal units."""

        response = self._call_internvl2(prompt, [viewport_b64, storyboard_b64])
        unreal.log(f"[DEBUG InternVL2] Comparison result - Similarity: {response.get('similarity', 0)}")
        return response

    def _call_internvl2(self, prompt: str, images: List[str]) -> Dict[str, Any]:
        """Call InternVL2 model via Ollama"""
        if not REQUESTS_AVAILABLE:
            unreal.log_error("[DEBUG InternVL2] Requests module not available")
            return {"error": "Requests module not installed"}

        request_data = {
            "model": self.model,
            "prompt": prompt,
            "images": images,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low for precision
                "num_predict": 2000
            }
        }

        try:
            unreal.log(f"[DEBUG InternVL2] Calling model {self.model}...")
            response = requests.post(
                f"{self.endpoint}/generate",
                json=request_data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "{}")
                from core.json_extractor import parse_llm_json
                try:
                    parsed = parse_llm_json(response_text)
                    unreal.log("[DEBUG InternVL2] Successfully parsed JSON response")
                    return parsed
                except Exception as e:
                    unreal.log_error(f"[DEBUG InternVL2] Failed to parse JSON: {e}")

                    unreal.log_warning("[DEBUG InternVL2] Could not parse JSON, returning raw")
                    return {"raw_response": response_text}
            else:
                unreal.log_error(f"[DEBUG InternVL2] API error: {response.status_code}")
                return {"error": f"API error: {response.status_code}"}

        except Exception as e:
            unreal.log_error(f"[DEBUG InternVL2] Call failed: {e}")
            return {"error": str(e)}

    def capture_viewport(self) -> str:
        """Capture current viewport"""
        viewport_path = Path(unreal.Paths.project_saved_dir()) / "viewport_capture.png"

        unreal.log(f"[DEBUG InternVL2] Capturing viewport to {viewport_path}")

        # Use Unreal's screenshot functionality
        unreal.AutomationLibrary.take_high_res_screenshot(
            1920, 1080,
            str(viewport_path),
            camera=None,
            capture_hdr=False
        )

        # Wait for file to be written
        time.sleep(0.5)

        if viewport_path.exists():
            unreal.log("[DEBUG InternVL2] Viewport captured successfully")
        else:
            unreal.log_error("[DEBUG InternVL2] Failed to capture viewport")

        return str(viewport_path)


class OllamaProvider:
    """Ollama local AI provider for model management"""

    # Vision models for storyboarding
    VISION_MODELS = {
        "internvl2:8b": {
            "size": "16GB",
            "quality": "Excellent",
            "speed": "Fast",
            "description": "BEST for viewport matching and spatial reasoning (MIT License)",
            "capabilities": ["viewport_matching", "spatial_reasoning", "asset_detection"],
            "license": "MIT (100% Free)",
            "viewport_score": 95
        },
        "qwen2-vl:7b": {
            "size": "15GB",
            "quality": "Excellent",
            "speed": "Fast",
            "description": "Excellent for technical screenshots (Apache 2.0)",
            "capabilities": ["screenshot_analysis", "technical_understanding"],
            "license": "Apache 2.0 (100% Free)",
            "viewport_score": 92
        },
        "llama3.2-vision:11b": {
            "size": "22GB",
            "quality": "Very Good",
            "speed": "Medium",
            "description": "Meta's vision model with good reasoning",
            "capabilities": ["general_vision", "reasoning"],
            "license": "Meta Community License",
            "viewport_score": 88
        },
        "minicpm-v:latest": {
            "size": "16GB",
            "quality": "Good",
            "speed": "Fast",
            "description": "Efficient model for image comparison",
            "capabilities": ["image_comparison", "efficiency"],
            "license": "Apache 2.0 (100% Free)",
            "viewport_score": 85
        }
    }

    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint
        self.api_base = f"{endpoint}/api"

    def is_available(self) -> bool:
        """Check if Ollama is running"""
        if not REQUESTS_AVAILABLE:
            return False

        try:
            response = requests.get(f"{self.api_base}/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> List[str]:
        """List installed Ollama models"""
        if not REQUESTS_AVAILABLE:
            return []

        try:
            response = requests.get(f"{self.api_base}/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return [m.get("name", "") for m in models]
        except:
            pass
        return []

    def install_model(self, model_name: str) -> bool:
        """Pull an Ollama model"""
        if not REQUESTS_AVAILABLE:
            return False

        try:
            unreal.log(f"[DEBUG Ollama] Pulling model: {model_name}")

            response = requests.post(
                f"{self.api_base}/pull",
                json={"name": model_name},
                stream=True
            )

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        unreal.log(f"[DEBUG Ollama] {data['status']}")

            return True

        except Exception as e:
            unreal.log_error(f"[DEBUG Ollama] Failed to pull model: {e}")
            return False


# Global instance
_scene_builder = None

def get_scene_builder() -> InternVL2SceneBuilder:
    """Get or create the scene builder instance"""
    global _scene_builder
    if _scene_builder is None:
        _scene_builder = InternVL2SceneBuilder()
    return _scene_builder

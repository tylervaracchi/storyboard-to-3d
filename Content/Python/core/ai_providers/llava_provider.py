# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
LLaVA Provider - Local AI vision via Ollama
Free, private, no API key needed
"""

import requests
import base64
import time
from pathlib import Path
from typing import List, Dict
import unreal

try:
    from .base_provider import BaseAIProvider
except ImportError:
    from base_provider import BaseAIProvider


class LLaVAProvider(BaseAIProvider):
    """LLaVA vision model via Ollama (local, free)"""

    def __init__(self, model: str = "llava:latest", url: str = "http://localhost:11434"):
        super().__init__("LLaVA")
        self.model = model
        self.url = url
        self.ollama_url = url  # Alias for compatibility
        self.max_images = 5  # LLaVA works best with fewer images

    def analyze_images(self, images: List[str], prompt: str, **kwargs) -> Dict:
        """Analyze images using LLaVA"""

        start_time = time.time()

        # Validate images
        valid, error = self.validate_images(images)
        if not valid:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': 0.0,
                'success': False,
                'error': error
            }

        # Limit images
        if len(images) > self.max_images:
            unreal.log_warning(f"[LLaVA] Too many images ({len(images)}), using first {self.max_images}")
            images = images[:self.max_images]

        try:
            # Convert images to base64
            image_data = []
            for img_path in images:
                with open(img_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                    image_data.append(b64)

            unreal.log(f"[LLaVA] Sending {len(images)} images to Ollama...")

            # Call Ollama API
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": image_data,
                    "stream": False
                },
                timeout=120  # 2 minute timeout
            )

            response.raise_for_status()
            result = response.json()

            elapsed = time.time() - start_time

            # Update statistics
            self.call_count += 1
            self.last_cost = 0.0  # Free!
            self.total_cost = 0.0

            unreal.log(f"[LLaVA] Analysis complete in {elapsed:.1f}s")

            return {
                'response': result.get('response', ''),
                'confidence': 0.75,  # LLaVA typically 75-80% confidence
                'cost': 0.0,
                'time': elapsed,
                'success': True,
                'error': ''
            }

        except requests.exceptions.Timeout:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': 'LLaVA request timed out after 120s'
            }
        except requests.exceptions.ConnectionError:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': 'Could not connect to Ollama. Is it running? (ollama serve)'
            }
        except Exception as e:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': f'LLaVA error: {str(e)}'
            }

    def is_available(self) -> bool:
        """Check if Ollama is running and has LLaVA model"""
        try:
            # Check if Ollama is running
            response = requests.get(f"{self.url}/api/tags", timeout=2)
            if response.status_code != 200:
                return False

            # Check if LLaVA model is available
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]

            # Check for any llava model
            has_llava = any('llava' in name.lower() for name in model_names)

            return has_llava

        except:
            return False

    def get_cost_estimate(self, num_images: int, prompt_length: int = 500) -> float:
        """LLaVA is always free"""
        return 0.0

    def get_provider_info(self) -> Dict:
        """Get LLaVA provider information"""
        return {
            'name': 'LLaVA (Local)',
            'type': 'llava',
            'cost_per_image': 0.0,
            'speed': 'Slow (10-20s per analysis)',
            'accuracy': 'Good (75-80%)',
            'max_images': self.max_images,
            'requires_api_key': False,
            'is_local': True,
            'url': self.url,
            'model': self.model
        }

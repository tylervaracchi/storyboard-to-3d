# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Base AI Provider Abstract Class
Defines interface for all AI vision providers (LLaVA, GPT-4V, Claude, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pathlib import Path


class BaseAIProvider(ABC):
    """Abstract base class for AI vision providers"""

    def __init__(self, name: str):
        self.name = name
        self.last_cost = 0.0
        self.total_cost = 0.0
        self.call_count = 0

    @abstractmethod
    def analyze_images(self, images: List[str], prompt: str, **kwargs) -> Dict:
        """
        Analyze multiple images with a prompt

        Args:
            images: List of image file paths
            prompt: Analysis prompt
            **kwargs: Provider-specific options

        Returns:
            {
                'response': str,           # AI's text response
                'confidence': float,       # 0.0-1.0 confidence score
                'cost': float,            # USD cost (0 for local)
                'time': float,            # Seconds taken
                'success': bool,          # Whether analysis succeeded
                'error': str              # Error message if failed
            }
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if provider is available and properly configured

        Returns:
            True if provider can be used
        """
        pass

    @abstractmethod
    def get_cost_estimate(self, num_images: int, prompt_length: int = 500) -> float:
        """
        Estimate cost for an analysis

        Args:
            num_images: Number of images to analyze
            prompt_length: Approximate prompt length in characters

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    def get_provider_info(self) -> Dict:
        """
        Get information about this provider

        Returns:
            {
                'name': str,
                'type': str,
                'cost_per_image': float,
                'speed': str,
                'accuracy': str,
                'max_images': int,
                'requires_api_key': bool,
                'is_local': bool
            }
        """
        pass

    def validate_images(self, images: List[str]) -> tuple:
        """
        Validate image files exist and are readable

        Returns:
            (success: bool, error_message: str)
        """
        for img_path in images:
            path = Path(img_path)
            if not path.exists():
                return False, f"Image not found: {img_path}"
            if not path.is_file():
                return False, f"Not a file: {img_path}"
            if path.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.webp']:
                return False, f"Unsupported image format: {path.suffix}"

        return True, ""

    def get_statistics(self) -> Dict:
        """Get usage statistics for this provider"""
        return {
            'provider': self.name,
            'total_calls': self.call_count,
            'total_cost': self.total_cost,
            'average_cost': self.total_cost / self.call_count if self.call_count > 0 else 0.0
        }

    def reset_statistics(self):
        """Reset usage statistics"""
        self.last_cost = 0.0
        self.total_cost = 0.0
        self.call_count = 0

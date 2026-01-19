# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Scene Matcher Module for StoryboardTo3D
Compares storyboard panels to viewport captures
"""

import unreal
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

# Try importing image processing libraries
try:
    from PIL import Image
    import numpy as np
    IMAGE_LIBS_AVAILABLE = True
except ImportError:
    IMAGE_LIBS_AVAILABLE = False
    unreal.log_warning("[SceneMatcher] PIL/numpy not available. Install with: pip install pillow numpy")

class SceneMatcher:
    """
    Matches and compares storyboard panels to viewport captures
    """

    def __init__(self):
        """Initialize scene matcher"""
        self.comparison_history = []
        self.last_comparison = None

        # Weights for different comparison aspects
        self.weights = {
            'composition': 0.3,
            'color': 0.2,
            'lighting': 0.2,
            'content': 0.3
        }

        unreal.log("[SceneMatcher] Initialized")

    def compare_images(self,
                      storyboard_path: str,
                      viewport_path: str,
                      detailed: bool = True) -> Dict[str, Any]:
        """
        Compare storyboard panel to viewport capture

        Args:
            storyboard_path: Path to storyboard image
            viewport_path: Path to viewport capture
            detailed: Include detailed analysis

        Returns:
            Comparison results with match percentage and recommendations
        """
        unreal.log(f"[SceneMatcher] Comparing images...")
        unreal.log(f"Storyboard: {Path(storyboard_path).name}")
        unreal.log(f"Viewport: {Path(viewport_path).name}")

        result = {
            'storyboard': storyboard_path,
            'viewport': viewport_path,
            'timestamp': datetime.now().isoformat(),
            'match_percentage': 0.0,
            'aspects': {},
            'recommendations': [],
            'adjustments': {}
        }

        # Check if files exist
        if not Path(storyboard_path).exists():
            unreal.log_error(f"[SceneMatcher] Storyboard not found: {storyboard_path}")
            result['error'] = 'Storyboard file not found'
            return result

        if not Path(viewport_path).exists():
            unreal.log_error(f"[SceneMatcher] Viewport capture not found: {viewport_path}")
            result['error'] = 'Viewport capture not found'
            return result

        # Perform different types of comparison
        if IMAGE_LIBS_AVAILABLE:
            # Use image processing libraries for detailed comparison
            result['aspects'] = self._compare_with_processing(storyboard_path, viewport_path)
        else:
            # Basic comparison using file properties
            result['aspects'] = self._compare_basic(storyboard_path, viewport_path)

        # Calculate overall match percentage
        if result['aspects']:
            total_score = 0
            total_weight = 0

            for aspect, data in result['aspects'].items():
                if aspect in self.weights:
                    weight = self.weights[aspect]
                    score = data.get('score', 0)
                    total_score += score * weight
                    total_weight += weight

            if total_weight > 0:
                result['match_percentage'] = round((total_score / total_weight) * 100, 2)

        # Generate recommendations based on match
        result['recommendations'] = self._generate_recommendations(result)

        # Calculate adjustments needed
        result['adjustments'] = self._calculate_adjustments(result)

        # Store in history
        self.last_comparison = result
        self.comparison_history.append(result)

        # Limit history size
        if len(self.comparison_history) > 100:
            self.comparison_history.pop(0)

        unreal.log(f"[SceneMatcher] Match: {result['match_percentage']}%")

        return result

    def _compare_with_processing(self, storyboard_path: str, viewport_path: str) -> Dict[str, Any]:
        """
        Compare images using PIL and numpy
        """
        aspects = {}

        try:
            # Load images
            storyboard = Image.open(storyboard_path).convert('RGB')
            viewport = Image.open(viewport_path).convert('RGB')

            # Resize for comparison if needed
            if storyboard.size != viewport.size:
                # Resize viewport to match storyboard
                viewport = viewport.resize(storyboard.size, Image.LANCZOS)

            # Convert to numpy arrays
            story_array = np.array(storyboard)
            view_array = np.array(viewport)

            # Composition comparison (structural similarity)
            aspects['composition'] = self._compare_composition(story_array, view_array)

            # Color comparison
            aspects['color'] = self._compare_colors(story_array, view_array)

            # Lighting comparison
            aspects['lighting'] = self._compare_lighting(story_array, view_array)

            # Content comparison (edge detection)
            aspects['content'] = self._compare_content(story_array, view_array)

        except Exception as e:
            unreal.log_error(f"[SceneMatcher] Error in image processing: {e}")

        return aspects

    def _compare_composition(self, img1: np.ndarray, img2: np.ndarray) -> Dict[str, Any]:
        """Compare image composition using structural analysis"""
        try:
            # Convert to grayscale
            gray1 = np.mean(img1, axis=2)
            gray2 = np.mean(img2, axis=2)

            # Calculate normalized cross-correlation
            correlation = np.corrcoef(gray1.flat, gray2.flat)[0, 1]

            # Score from 0 to 1
            score = max(0, correlation)

            return {
                'score': score,
                'correlation': correlation,
                'match': 'good' if score > 0.7 else 'moderate' if score > 0.4 else 'poor'
            }

        except Exception as e:
            unreal.log_warning(f"[SceneMatcher] Composition comparison error: {e}")
            return {'score': 0.5, 'error': str(e)}

    def _compare_colors(self, img1: np.ndarray, img2: np.ndarray) -> Dict[str, Any]:
        """Compare color distributions"""
        try:
            # Calculate mean colors
            mean1 = np.mean(img1, axis=(0, 1))
            mean2 = np.mean(img2, axis=(0, 1))

            # Calculate color difference
            color_diff = np.linalg.norm(mean1 - mean2)

            # Normalize to 0-1 (inverse, so smaller diff = higher score)
            max_diff = 441.67  # sqrt(255^2 * 3)
            score = 1 - (color_diff / max_diff)

            return {
                'score': score,
                'mean_storyboard': mean1.tolist(),
                'mean_viewport': mean2.tolist(),
                'difference': color_diff
            }

        except Exception as e:
            unreal.log_warning(f"[SceneMatcher] Color comparison error: {e}")
            return {'score': 0.5, 'error': str(e)}

    def _compare_lighting(self, img1: np.ndarray, img2: np.ndarray) -> Dict[str, Any]:
        """Compare lighting/brightness"""
        try:
            # Calculate luminance
            lum1 = 0.299 * img1[:,:,0] + 0.587 * img1[:,:,1] + 0.114 * img1[:,:,2]
            lum2 = 0.299 * img2[:,:,0] + 0.587 * img2[:,:,1] + 0.114 * img2[:,:,2]

            # Compare histograms
            hist1, _ = np.histogram(lum1, bins=50, range=(0, 255))
            hist2, _ = np.histogram(lum2, bins=50, range=(0, 255))

            # Normalize histograms
            hist1 = hist1 / np.sum(hist1)
            hist2 = hist2 / np.sum(hist2)

            # Calculate histogram similarity
            similarity = np.minimum(hist1, hist2).sum()

            return {
                'score': similarity,
                'mean_brightness_story': np.mean(lum1),
                'mean_brightness_view': np.mean(lum2),
                'histogram_match': similarity
            }

        except Exception as e:
            unreal.log_warning(f"[SceneMatcher] Lighting comparison error: {e}")
            return {'score': 0.5, 'error': str(e)}

    def _compare_content(self, img1: np.ndarray, img2: np.ndarray) -> Dict[str, Any]:
        """Compare content using edge detection"""
        try:
            # Simple edge detection using gradients
            gray1 = np.mean(img1, axis=2)
            gray2 = np.mean(img2, axis=2)

            # Calculate gradients
            dx1 = np.diff(gray1, axis=1)
            dy1 = np.diff(gray1, axis=0)
            edges1 = np.sqrt(dx1[:-1,:]**2 + dy1[:,:-1]**2)

            dx2 = np.diff(gray2, axis=1)
            dy2 = np.diff(gray2, axis=0)
            edges2 = np.sqrt(dx2[:-1,:]**2 + dy2[:,:-1]**2)

            # Compare edge maps
            edge_diff = np.mean(np.abs(edges1 - edges2))
            score = 1 - min(edge_diff / 100, 1)  # Normalize

            return {
                'score': score,
                'edge_similarity': score,
                'edge_difference': edge_diff
            }

        except Exception as e:
            unreal.log_warning(f"[SceneMatcher] Content comparison error: {e}")
            return {'score': 0.5, 'error': str(e)}

    def _compare_basic(self, storyboard_path: str, viewport_path: str) -> Dict[str, Any]:
        """
        Basic comparison without image processing libraries
        """
        aspects = {}

        # File size comparison
        story_size = Path(storyboard_path).stat().st_size
        view_size = Path(viewport_path).stat().st_size

        size_ratio = min(story_size, view_size) / max(story_size, view_size)

        # Basic scoring based on file properties
        aspects['composition'] = {'score': 0.5, 'method': 'basic'}
        aspects['color'] = {'score': 0.5, 'method': 'basic'}
        aspects['lighting'] = {'score': 0.5, 'method': 'basic'}
        aspects['content'] = {'score': size_ratio, 'method': 'file_size'}

        return aspects

    def _generate_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """
        Generate recommendations based on comparison
        """
        recommendations = []
        match = result.get('match_percentage', 0)
        aspects = result.get('aspects', {})

        # Overall match recommendations
        if match < 30:
            recommendations.append("Major adjustments needed - scene doesn't match storyboard")
        elif match < 60:
            recommendations.append("Moderate adjustments needed to better match storyboard")
        elif match < 80:
            recommendations.append("Minor adjustments would improve the match")
        else:
            recommendations.append("Excellent match! Only fine-tuning needed")

        # Specific aspect recommendations
        if 'composition' in aspects:
            comp_score = aspects['composition'].get('score', 0)
            if comp_score < 0.5:
                recommendations.append(" Adjust camera position or framing")

        if 'color' in aspects:
            color_score = aspects['color'].get('score', 0)
            if color_score < 0.5:
                recommendations.append(" Adjust color grading or materials")

        if 'lighting' in aspects:
            light_score = aspects['lighting'].get('score', 0)
            if light_score < 0.5:
                recommendations.append(" Adjust lighting intensity or direction")

        if 'content' in aspects:
            content_score = aspects['content'].get('score', 0)
            if content_score < 0.5:
                recommendations.append(" Check object placement and visibility")

        return recommendations

    def _calculate_adjustments(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate specific adjustments needed
        """
        adjustments = {
            'camera': {},
            'lighting': {},
            'objects': {}
        }

        aspects = result.get('aspects', {})

        # Camera adjustments based on composition
        if 'composition' in aspects:
            comp = aspects['composition']
            if comp.get('score', 0) < 0.7:
                adjustments['camera'] = {
                    'suggestion': 'Reframe shot',
                    'confidence': 1 - comp.get('score', 0)
                }

        # Lighting adjustments
        if 'lighting' in aspects:
            light = aspects['lighting']
            story_bright = light.get('mean_brightness_story', 128)
            view_bright = light.get('mean_brightness_view', 128)

            if story_bright and view_bright:
                brightness_diff = story_bright - view_bright
                if abs(brightness_diff) > 20:
                    adjustments['lighting'] = {
                        'brightness_change': brightness_diff,
                        'direction': 'increase' if brightness_diff > 0 else 'decrease'
                    }

        return adjustments

    def batch_compare(self,
                     storyboard_paths: List[str],
                     viewport_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Compare multiple image pairs

        Args:
            storyboard_paths: List of storyboard paths
            viewport_paths: List of viewport paths

        Returns:
            List of comparison results
        """
        results = []

        pairs = min(len(storyboard_paths), len(viewport_paths))

        for i in range(pairs):
            unreal.log(f"[SceneMatcher] Comparing pair {i+1}/{pairs}")
            result = self.compare_images(storyboard_paths[i], viewport_paths[i])
            results.append(result)

        return results

    def get_comparison_summary(self) -> Dict[str, Any]:
        """
        Get summary of all comparisons
        """
        if not self.comparison_history:
            return {'total': 0, 'average_match': 0}

        matches = [c.get('match_percentage', 0) for c in self.comparison_history]

        return {
            'total': len(self.comparison_history),
            'average_match': sum(matches) / len(matches),
            'best_match': max(matches),
            'worst_match': min(matches),
            'recent': self.comparison_history[-5:]  # Last 5 comparisons
        }

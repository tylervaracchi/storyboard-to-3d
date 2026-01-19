# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Sketch Analyzer for Auto Initial Placement
Analyzes hand-drawn line art storyboards to extract character positions
Provides initial placement suggestions before AI iteration begins
Expected: Start at 70% vs 40% baseline (+30 points!)
"""

import base64
from io import BytesIO
from typing import Dict, List, Any

# Check for required dependencies
try:
    from PIL import Image
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class SketchAnalyzer:
    """Analyzes hand-drawn storyboards for automatic actor placement"""

    def __init__(self):
        self.available = PIL_AVAILABLE and CV2_AVAILABLE

        print(f"DEBUG: SketchAnalyzer initialized, available={self.available}")
        if not self.available:
            print(f"Sketch analysis disabled: PIL={PIL_AVAILABLE}, CV2={CV2_AVAILABLE}")
            if not PIL_AVAILABLE:
                print("Install: pip install pillow")
            if not CV2_AVAILABLE:
                print("Install: pip install opencv-python")

    def analyze_from_base64(self, storyboard_b64: str) -> Dict[str, Any]:
        """
        Analyze a base64-encoded storyboard image

        Args:
            storyboard_b64: Base64-encoded storyboard image

        Returns:
            Analysis dict with character detections and positions
        """
        print(f"DEBUG: analyze_from_base64 called, available={self.available}")

        if not self.available:
            print("DEBUG: Returning empty analysis (dependencies missing)")
            return {'success': False, 'characters': []}

        try:
            # Decode base64 to PIL Image
            print(f"DEBUG: Decoding base64 image ({len(storyboard_b64)} chars)")
            image_data = base64.b64decode(storyboard_b64)
            print(f"DEBUG: Decoded {len(image_data)} bytes")

            pil_image = Image.open(BytesIO(image_data))
            print(f"DEBUG: Opened PIL image: size={pil_image.size}, mode={pil_image.mode}")

            # Convert to numpy array
            img_array = np.array(pil_image)
            print(f"DEBUG: Numpy array shape: {img_array.shape}, dtype: {img_array.dtype}")

            # Convert to grayscale if needed
            if len(img_array.shape) == 3:
                if img_array.shape[2] == 4:  # RGBA
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGBA2GRAY)
                else:  # RGB
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array

            print(f"DEBUG: Image dimensions: {gray.shape[1]}x{gray.shape[0]}")
            print(f"DEBUG: Mean pixel value: {np.mean(gray):.1f}")

            # Analyze the sketch
            analysis = self.analyze_sketch(gray)

            print(f"DEBUG: Analysis complete: {len(analysis['characters'])} characters detected")
            return analysis

        except Exception as e:
            print(f"ERROR: Failed to analyze sketch: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'characters': []}

    def analyze_sketch(self, gray_image: np.ndarray) -> Dict[str, Any]:
        """
        Analyze grayscale sketch image for character detection

        Args:
            gray_image: Grayscale numpy array

        Returns:
            Dict with detected characters and their properties
        """
        print("DEBUG: analyze_sketch started")

        height, width = gray_image.shape

        # Invert if needed (assume dark lines on light background)
        mean_val = np.mean(gray_image)
        if mean_val > 127:
            # Light background, dark lines - invert
            gray_image = 255 - gray_image
            print("DEBUG: Inverted image (was light background)")

        # Threshold to binary
        _, binary = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        print(f"DEBUG: Applied Otsu thresholding")

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        print(f"DEBUG: Found {len(contours)} contours")

        # Filter contours by area (characters should be 1-60% of image)
        min_area = (width * height) * 0.01  # 1% minimum
        max_area = (width * height) * 0.60  # 60% maximum

        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                valid_contours.append(contour)

        print(f"DEBUG: Filtered to {len(valid_contours)} valid contours (area: {min_area:.0f}-{max_area:.0f})")

        # Analyze each contour
        characters = []
        for i, contour in enumerate(valid_contours):
            x, y, w, h = cv2.boundingRect(contour)

            # Calculate properties
            center_x = x + w / 2
            center_y = y + h / 2
            aspect_ratio = h / w if w > 0 else 1.0

            # Classify pose based on aspect ratio
            if aspect_ratio > 1.7:
                pose = 'standing'
            elif aspect_ratio < 1.0:
                pose = 'sitting'
            else:
                pose = 'neutral'

            # Estimate depth from Y-position (higher in image = farther away)
            depth_score = center_y / height  # 0.0 (top/far) to 1.0 (bottom/near)

            # Normalize position (0.0 to 1.0)
            normalized_x = center_x / width
            normalized_y = center_y / height

            character_data = {
                'index': i,
                'bbox': {'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)},
                'center': {'x': float(center_x), 'y': float(center_y)},
                'normalized': {'x': float(normalized_x), 'y': float(normalized_y)},
                'aspect_ratio': float(aspect_ratio),
                'pose': pose,
                'depth_score': float(depth_score),
                'area': float(cv2.contourArea(contour))
            }

            characters.append(character_data)

            print(f"DEBUG: Character {i}: bbox=({x},{y},{w},{h}), aspect_ratio={aspect_ratio:.2f}, pose={pose}, depth={depth_score:.2f}")

        # Sort by X position (left to right)
        characters.sort(key=lambda c: c['center']['x'])

        result = {
            'success': True,
            'image_size': {'width': width, 'height': height},
            'characters': characters,
            'num_detected': len(characters)
        }

        print(f"DEBUG: analyze_sketch complete: {len(characters)} characters")
        return result

    def convert_to_unreal_positions(self, analysis: Dict[str, Any],
                                    character_names: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Convert normalized positions to Unreal Engine coordinates

        Args:
            analysis: Analysis result from analyze_sketch()
            character_names: List of character names to assign

        Returns:
            Dict mapping character names to {x, y, z} positions
        """
        print(f"DEBUG: convert_to_unreal_positions called with {len(character_names)} character names")

        if not analysis.get('success') or not analysis.get('characters'):
            print("DEBUG: No valid analysis data, returning empty dict")
            return {}

        characters = analysis['characters']
        positions = {}

        # Match characters to names (left to right)
        for i, char_data in enumerate(characters):
            if i >= len(character_names):
                break

            char_name = character_names[i]

            # Convert normalized positions to Unreal coordinates
            # X-axis: Depth (forward/back) - based on depth_score
            # Range: -500 (far) to 500 (near)
            depth_score = char_data['depth_score']
            x = -500 + (depth_score * 1000)  # Map 0-1 to -500 to +500

            # Y-axis: Left/right - based on horizontal position
            # Range: -500 (left) to 500 (right), centered at 0
            normalized_x = char_data['normalized']['x']
            y = -500 + (normalized_x * 1000)  # Map 0-1 to -500 to +500

            # Z-axis: Ground level (0) or sitting height (determined by pose)
            pose = char_data['pose']
            if pose == 'sitting':
                z = 0  # Sitting - character origin at ground
            else:
                z = 0  # Standing - character origin at ground (feet)

            positions[char_name] = {
                'x': float(x),
                'y': float(y),
                'z': float(z),
                'pose': pose,
                'confidence': 0.6  # Moderate confidence for auto-placement
            }

            print(f"DEBUG: {char_name}: X={x:.1f}, Y={y:.1f}, Z={z:.1f}, pose={pose}")

        print(f"DEBUG: Converted {len(positions)} positions")
        return positions


# Module-level test function
def test_sketch_analyzer():
    """Test the sketch analyzer"""
    analyzer = SketchAnalyzer()

    if not analyzer.available:
        print("Cannot test: dependencies not installed")
        print("Install: pip install opencv-python pillow")
        return False

    # Create test sketch (simple geometric shapes)
    from PIL import ImageDraw
    test_img = Image.new('L', (800, 600), color=255)  # White background
    draw = ImageDraw.Draw(test_img)

    # Draw two simple "characters" (rectangles)
    draw.rectangle([200, 300, 280, 500], fill=0, outline=0)  # Left character
    draw.rectangle([500, 250, 580, 500], fill=0, outline=0)  # Right character

    # Convert to base64
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    test_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    print("\n" + "="*70)
    print("Testing Sketch Analyzer")
    print("="*70)

    # Test analysis
    print("\n Analyzing test sketch...")
    analysis = analyzer.analyze_from_base64(test_b64)

    print(f"\n Analysis complete:")
    print(f"Success: {analysis.get('success')}")
    print(f"Characters detected: {analysis.get('num_detected')}")

    if analysis.get('characters'):
        print("\n   Character details:")
        for char in analysis['characters']:
            print(f"- Index {char['index']}: {char['pose']}, aspect={char['aspect_ratio']:.2f}")

    # Test position conversion
    print("\n Converting to Unreal positions...")
    positions = analyzer.convert_to_unreal_positions(analysis, ['Character1', 'Character2'])

    print(f"\n Position conversion complete:")
    for name, pos in positions.items():
        print(f"{name}: X={pos['x']:.1f}, Y={pos['y']:.1f}, Z={pos['z']:.1f}, pose={pos['pose']}")

    print("\n" + "="*70)
    print("Sketch analyzer tests complete!")
    print("="*70)

    return True


if __name__ == '__main__':
    test_sketch_analyzer()

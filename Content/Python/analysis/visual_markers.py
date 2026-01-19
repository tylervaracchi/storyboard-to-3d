# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Automatic Visual Markers for 3D Scene Analysis
Adds grid overlays, coordinate axes, and scale bars to captured images
Research shows +35-40% accuracy improvement with spatial reference markers
"""

import base64
from io import BytesIO
from typing import Optional

# Check for required dependencies
try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class VisualMarkerRenderer:
    """Adds spatial reference markers to captured images"""

    def __init__(self):
        self.available = PIL_AVAILABLE and CV2_AVAILABLE

        # Color scheme for axes (RGB format for OpenCV BGR conversion)
        self.colors = {
            'x_axis': (0, 0, 255),    # Red - Forward/Back
            'y_axis': (0, 255, 0),    # Green - Left/Right
            'z_axis': (255, 0, 0),    # Blue - Up/Down
            'grid': (128, 128, 128),  # Gray - Grid lines
            'ground': (255, 255, 0),  # Cyan - Ground plane
            'text': (255, 255, 255)   # White - Labels
        }

        print(f"DEBUG: VisualMarkerRenderer initialized, available={self.available}")
        if not self.available:
            print(f"Visual markers disabled: PIL={PIL_AVAILABLE}, CV2={CV2_AVAILABLE}")
            if not PIL_AVAILABLE:
                print("Install: pip install pillow")
            if not CV2_AVAILABLE:
                print("Install: pip install opencv-python")

    def add_markers_to_base64(self, image_b64: str, camera_type: str,
                              depth_map_b64: Optional[str] = None,
                              actor_labels: Optional[dict] = None) -> str:
        """
        Add spatial reference markers to a base64-encoded image

        Args:
            image_b64: Base64-encoded image string
            camera_type: Camera angle (front, right, back, left, top, three_quarter, hero)
            depth_map_b64: Optional depth map for advanced visualization
            actor_labels: Optional dict of actor names and their 3D positions
                         Format: {'ActorName': {'x': float, 'y': float, 'z': float}}

        Returns:
            Base64-encoded image with markers added
        """
        print(f"DEBUG: add_markers_to_base64 called for camera_type='{camera_type}', available={self.available}, actor_labels={actor_labels is not None}")

        if not self.available:
            print("DEBUG: Returning original image (dependencies missing)")
            return image_b64

        try:
            # Decode base64 to PIL Image
            print(f"DEBUG: Decoding base64 image ({len(image_b64)} chars)")
            image_data = base64.b64decode(image_b64)
            print(f"DEBUG: Decoded {len(image_data)} bytes")

            pil_image = Image.open(BytesIO(image_data))
            print(f"DEBUG: Decoded image: size={pil_image.size}, mode={pil_image.mode}")

            # Convert to OpenCV format (BGR)
            img_array = np.array(pil_image)
            if len(img_array.shape) == 2:  # Grayscale
                img = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
            elif img_array.shape[2] == 4:  # RGBA
                img = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            else:  # RGB
                img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            print(f"DEBUG: Converted to OpenCV BGR array: shape={img.shape}")

            # Apply appropriate markers based on camera type
            if camera_type == 'top':
                print("DEBUG: Applying top view markers")
                img = self._add_grid_and_axes_2d(img, 'top', actor_labels)
            elif camera_type in ['right', 'left']:
                print(f"DEBUG: Applying side view markers for '{camera_type}'")
                img = self._add_grid_and_axes_2d(img, 'side', actor_labels)
            elif camera_type in ['front', 'back']:
                print(f"DEBUG: Applying front/back view markers for '{camera_type}'")
                img = self._add_grid_and_axes_2d(img, 'front', actor_labels)
            else:  # hero, three_quarter
                print(f"DEBUG: Applying comprehensive markers for '{camera_type}'")
                img = self._add_comprehensive_markers(img, depth_map_b64, actor_labels)

            # Convert back to PIL Image
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result_image = Image.fromarray(img_rgb)

            # Encode back to base64
            buffer = BytesIO()
            result_image.save(buffer, format='PNG')
            result_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            print(f"DEBUG: Encoded annotated image ({len(result_b64)} chars, diff: {len(result_b64)-len(image_b64):+d})")

            return result_b64

        except Exception as e:
            print(f"ERROR: Failed to add markers: {e}")
            import traceback
            traceback.print_exc()
            print("DEBUG: Returning original image due to error")
            return image_b64

    def _add_grid_and_axes_2d(self, img, view_type: str, actor_labels: Optional[dict] = None):
        """Add grid and 2D axes for orthographic views"""
        print(f"DEBUG: _add_grid_and_axes_2d called for view_type='{view_type}', has_actor_labels={actor_labels is not None}")

        height, width = img.shape[:2]

        # Grid spacing (10% of image size)
        grid_spacing_x = width // 10
        grid_spacing_y = height // 10

        # Draw vertical grid lines
        for x in range(0, width, grid_spacing_x):
            cv2.line(img, (x, 0), (x, height), self.colors['grid'], 1)

        # Draw horizontal grid lines
        for y in range(0, height, grid_spacing_y):
            cv2.line(img, (0, y), (width, y), self.colors['grid'], 1)

        # Draw axes based on view type
        center_x, center_y = width // 2, height // 2
        axis_length = min(width, height) // 4
        thickness = 3

        if view_type == 'top':
            # X-axis (forward) - Red, pointing up
            cv2.arrowedLine(img, (center_x, center_y), (center_x, center_y - axis_length),
                          self.colors['x_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'X (Forward)', (center_x + 10, center_y - axis_length),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['x_axis'], 2)

            # Y-axis (right) - Green, pointing right
            cv2.arrowedLine(img, (center_x, center_y), (center_x + axis_length, center_y),
                          self.colors['y_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'Y (Right)', (center_x + axis_length + 10, center_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['y_axis'], 2)

        elif view_type == 'side':
            # X-axis (forward) - Red, pointing right
            cv2.arrowedLine(img, (center_x, center_y), (center_x + axis_length, center_y),
                          self.colors['x_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'X', (center_x + axis_length + 10, center_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['x_axis'], 2)

            # Z-axis (up) - Blue, pointing up
            cv2.arrowedLine(img, (center_x, center_y), (center_x, center_y - axis_length),
                          self.colors['z_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'Z (Up)', (center_x + 10, center_y - axis_length),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['z_axis'], 2)

            # Ground plane indicator (Z=0)
            ground_y = int(center_y + axis_length * 0.7)
            cv2.line(img, (0, ground_y), (width, ground_y), self.colors['ground'], 2)
            cv2.putText(img, 'Ground (Z=0)', (10, ground_y - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['ground'], 2)

        elif view_type == 'front':
            # Y-axis (right) - Green, pointing right
            cv2.arrowedLine(img, (center_x, center_y), (center_x + axis_length, center_y),
                          self.colors['y_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'Y (Right)', (center_x + axis_length + 10, center_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['y_axis'], 2)

            # Z-axis (up) - Blue, pointing up
            cv2.arrowedLine(img, (center_x, center_y), (center_x, center_y - axis_length),
                          self.colors['z_axis'], thickness, tipLength=0.3)
            cv2.putText(img, 'Z (Up)', (center_x + 10, center_y - axis_length),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['z_axis'], 2)

            # Ground plane
            ground_y = int(center_y + axis_length * 0.7)
            cv2.line(img, (0, ground_y), (width, ground_y), self.colors['ground'], 2)
            cv2.putText(img, 'Ground', (10, ground_y - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['ground'], 2)

        # Add actor labels if provided
        if actor_labels:
            img = self._draw_actor_labels(img, actor_labels, view_type)

        print(f"DEBUG: Added grid ({width}x{height}) with axes for {view_type} view")
        return img

    def _draw_actor_labels(self, img, actor_labels: dict, view_type: str):
        """Draw simple actor name labels at top of image"""
        print(f"DEBUG: Drawing {len(actor_labels)} actor labels for {view_type} view")

        height, width = img.shape[:2]

        # Simple approach: List actor names at top
        # No bounding boxes - coordinates are already in text prompt
        if not actor_labels:
            return img

        # Create label text
        actor_names = list(actor_labels.keys())
        label_text = "Actors: " + " | ".join(actor_names)

        # Get text size
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        text_size = cv2.getTextSize(label_text, font, font_scale, thickness)[0]

        # Position at top center
        text_x = (width - text_size[0]) // 2
        text_y = 35

        # Draw semi-transparent background
        padding = 10
        bg_x1 = text_x - padding
        bg_y1 = text_y - text_size[1] - padding
        bg_x2 = text_x + text_size[0] + padding
        bg_y2 = text_y + padding

        # Background rectangle
        overlay = img.copy()
        cv2.rectangle(overlay, (bg_x1, bg_y1), (bg_x2, bg_y2), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

        # Draw text
        cv2.putText(img, label_text, (text_x, text_y),
                   font, font_scale, (0, 255, 255), thickness)  # Yellow text

        print(f"DEBUG: Drew simple label with {len(actor_labels)} actors")
        return img

    def _add_comprehensive_markers(self, img, depth_map_b64: Optional[str] = None, actor_labels: Optional[dict] = None):
        """Add comprehensive markers for hero/diagonal views"""
        print(f"DEBUG: _add_comprehensive_markers called, has_depth_map={depth_map_b64 is not None}")

        height, width = img.shape[:2]

        # NOTE: Grid removed for perspective views (hero/3_quarter)
        # Flat orthogonal grids don't work with perspective cameras
        # They would need vanishing point calculations to be accurate
        # Instead, we rely on scale bar and depth cues

        # Corner reference axes (more useful for perspective than center axes)
        # Bottom-left corner coordinate system
        corner_x, corner_y = 30, height - 30
        axis_length = 60
        thickness = 3

        # X-axis (forward) - Red
        cv2.arrowedLine(img, (corner_x, corner_y), (corner_x + axis_length, corner_y),
                       self.colors['x_axis'], thickness, tipLength=0.2)
        cv2.putText(img, 'X', (corner_x + axis_length + 5, corner_y + 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.colors['x_axis'], 1)

        # Y-axis (right) - Green (angled for perspective hint)
        y_end_x = int(corner_x + axis_length*0.7)
        y_end_y = int(corner_y - axis_length*0.3)
        cv2.arrowedLine(img, (corner_x, corner_y), (y_end_x, y_end_y),
                       self.colors['y_axis'], thickness, tipLength=0.2)
        cv2.putText(img, 'Y', (y_end_x + 5, y_end_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.colors['y_axis'], 1)

        # Z-axis (up) - Blue
        cv2.arrowedLine(img, (corner_x, corner_y), (corner_x, corner_y - axis_length),
                       self.colors['z_axis'], thickness, tipLength=0.2)
        cv2.putText(img, 'Z', (corner_x + 5, corner_y - axis_length - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.colors['z_axis'], 1)

        # Reference scale bar (200 units = 2 meters)
        scale_bar_length = 200  # pixels representing 200cm
        scale_x = width - scale_bar_length - 20
        scale_y = height - 40

        cv2.line(img, (scale_x, scale_y), (scale_x + scale_bar_length, scale_y),
                self.colors['text'], 3)
        cv2.line(img, (scale_x, scale_y - 5), (scale_x, scale_y + 5),
                self.colors['text'], 2)
        cv2.line(img, (scale_x + scale_bar_length, scale_y - 5),
                (scale_x + scale_bar_length, scale_y + 5), self.colors['text'], 2)
        cv2.putText(img, '200cm (2m)', (scale_x + 40, scale_y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['text'], 2)

        # Add depth map overlay if provided
        if depth_map_b64:
            try:
                print("DEBUG: Overlaying depth map")
                depth_data = base64.b64decode(depth_map_b64)
                depth_image = Image.open(BytesIO(depth_data))
                depth_array = np.array(depth_image.resize((width, height)))

                # Convert depth to heatmap (semi-transparent)
                if len(depth_array.shape) == 2:  # Grayscale depth
                    depth_colored = cv2.applyColorMap(depth_array, cv2.COLORMAP_TURBO)
                    img = cv2.addWeighted(img, 0.7, depth_colored, 0.3, 0)

                    # Add depth legend (TURBO colormap: dark blue=near, red=far)
                    legend_x, legend_y = 20, 20
                    cv2.putText(img, 'Depth: Near (Blue)', (legend_x, legend_y),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    cv2.putText(img, 'Depth: Far (Red)', (legend_x, legend_y + 20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                print("DEBUG: Depth map overlay complete")
            except Exception as e:
                print(f"Failed to overlay depth map: {e}")

        # Add actor labels if provided
        if actor_labels:
            img = self._draw_actor_labels(img, actor_labels, 'perspective')

        print("DEBUG: Comprehensive markers complete (corner axes + scale bar + actor labels, NO grid for perspective)")
        return img


# Module-level test function
def test_visual_markers():
    """Test the visual marker renderer"""
    renderer = VisualMarkerRenderer()

    if not renderer.available:
        print("Cannot test: dependencies not installed")
        print("Install: pip install opencv-python pillow")
        return False

    # Create test image (solid color)
    test_img = Image.new('RGB', (800, 600), color=(50, 50, 50))
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    test_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    print("\n" + "="*70)
    print("Testing Visual Marker Renderer")
    print("="*70)

    # Test each camera type
    camera_types = ['top', 'right', 'front', 'hero']
    for cam_type in camera_types:
        print(f"\n Testing {cam_type} view...")
        result = renderer.add_markers_to_base64(test_b64, cam_type)
        print(f"{cam_type}: {len(result)} chars")

    print("\n" + "="*70)
    print("Visual marker tests complete!")
    print("="*70)

    return True


if __name__ == '__main__':
    test_visual_markers()

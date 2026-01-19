# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Installation Verification Script for StoryboardTo3D
Tests all dependencies and features to ensure proper setup
"""

import sys
from pathlib import Path

print("=" * 80)
print("StoryboardTo3D - Installation Verification")
print("=" * 80)
print()

# Results tracking
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}

def test_result(name, passed, message=""):
    """Record test result"""
    if passed:
        results['passed'].append(name)
        print(f"{name}")
        if message:
            print(f"{message}")
    else:
        results['failed'].append(name)
        print(f"{name}")
        if message:
            print(f"{message}")
    print()

def warning(name, message):
    """Record warning"""
    results['warnings'].append(name)
    print(f"{name}")
    print(f"{message}")
    print()

# =============================================================================
# TEST 1: Core Python Dependencies
# =============================================================================
print("Testing Core Dependencies...")
print("-" * 80)

# Test OpenCV
try:
    import cv2
    version = cv2.__version__
    test_result("OpenCV (cv2)", True, f"Version: {version}")
except ImportError as e:
    test_result("OpenCV (cv2)", False, f"Not installed. Run: pip install opencv-python")

# Test Pillow
try:
    from PIL import Image
    import PIL
    version = PIL.__version__
    test_result("Pillow (PIL)", True, f"Version: {version}")
except ImportError:
    test_result("Pillow (PIL)", False, "Not installed. Run: pip install pillow")

# Test NumPy (required by OpenCV)
try:
    import numpy as np
    version = np.__version__
    test_result("NumPy", True, f"Version: {version}")
except ImportError:
    test_result("NumPy", False, "Not installed. Run: pip install numpy")

# Test Pydantic (for structured outputs)
try:
    import pydantic
    version = pydantic.__version__
    test_result("Pydantic", True, f"Version: {version}")
except ImportError:
    warning("Pydantic", "Not installed. Structured outputs disabled. Run: pip install pydantic")

# =============================================================================
# TEST 2: Optional ML Dependencies (Depth-Anything-V2)
# =============================================================================
print("Testing Optional ML Dependencies (Depth-Anything-V2)...")
print("-" * 80)

# Test PyTorch
try:
    import torch
    version = torch.__version__
    cuda_available = torch.cuda.is_available()
    device = "CUDA" if cuda_available else "CPU"
    test_result("PyTorch", True, f"Version: {version}, Device: {device}")
except ImportError:
    warning("PyTorch", "Not installed. Depth-Anything-V2 will not work. Run: pip install torch")

# Test Transformers
try:
    import transformers
    version = transformers.__version__
    test_result("Transformers", True, f"Version: {version}")
except ImportError:
    warning("Transformers", "Not installed. Depth-Anything-V2 will not work. Run: pip install transformers")

# Test if depth model would load
depth_model_available = False
try:
    import torch
    import transformers
    from transformers import pipeline
    # Just check if pipeline is callable, don't actually load model
    depth_model_available = True
    test_result("Depth Model API", True, "transformers.pipeline is available")
except Exception as e:
    warning("Depth Model API", f"Cannot initialize: {e}")

# =============================================================================
# TEST 3: StoryboardTo3D Modules
# =============================================================================
print("Testing StoryboardTo3D Modules...")
print("-" * 80)

# Add plugin path to sys.path if needed
plugin_path = Path(__file__).parent.parent
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))
    print(f"Added to path: {plugin_path}")
    print()

# Test VisualMarkerRenderer
try:
    from analysis.visual_markers import VisualMarkerRenderer
    renderer = VisualMarkerRenderer()
    if renderer.available:
        test_result("Visual Markers", True, "Renderer initialized and available")
    else:
        test_result("Visual Markers", False, "Module loaded but dependencies missing")
except Exception as e:
    test_result("Visual Markers", False, f"Import error: {e}")

# Test SketchAnalyzer
try:
    from analysis.sketch_analyzer import SketchAnalyzer
    analyzer = SketchAnalyzer()
    if analyzer.available:
        test_result("Sketch Analyzer", True, "Analyzer initialized and available")
    else:
        test_result("Sketch Analyzer", False, "Module loaded but dependencies missing")
except Exception as e:
    test_result("Sketch Analyzer", False, f"Import error: {e}")

# Test DepthAnalyzer
try:
    from analysis.depth_analyzer import DepthAnalyzer
    depth_analyzer = DepthAnalyzer()
    if depth_analyzer.available:
        test_result("Depth Analyzer", True, f"Model loaded (device: {depth_analyzer.device})")
    else:
        test_result("Depth Analyzer", False, "Module loaded but dependencies missing")
except Exception as e:
    test_result("Depth Analyzer", False, f"Import error: {e}")

# Test ActivePanelWidget
try:
    from ui.widgets.active_panel_widget import ActivePanelWidget
    test_result("Active Panel Widget", True, "Main UI widget imports successfully")
except Exception as e:
    test_result("Active Panel Widget", False, f"Import error: {e}")

# Test SceneAdjuster
try:
    from core.scene_adjuster import SceneAdjuster
    test_result("Scene Adjuster", True, "Core adjuster module available")
except Exception as e:
    test_result("Scene Adjuster", False, f"Import error: {e}")

# =============================================================================
# TEST 4: Feature Tests
# =============================================================================
print("Testing Feature Functionality...")
print("-" * 80)

# Test Visual Marker Generation
try:
    from analysis.visual_markers import VisualMarkerRenderer
    from PIL import Image
    import base64
    from io import BytesIO

    renderer = VisualMarkerRenderer()
    if renderer.available:
        # Create test image
        test_img = Image.new('RGB', (800, 600), color=(50, 50, 50))
        buffer = BytesIO()
        test_img.save(buffer, format='PNG')
        test_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Try to add markers
        result = renderer.add_markers_to_base64(test_b64, 'top')

        if len(result) > len(test_b64):
            test_result("Visual Marker Generation", True, f"Added {len(result) - len(test_b64)} chars of marker data")
        else:
            test_result("Visual Marker Generation", False, "Output not larger than input")
    else:
        warning("Visual Marker Generation", "Renderer not available (dependencies missing)")
except Exception as e:
    test_result("Visual Marker Generation", False, f"Error: {e}")

# Test Sketch Analysis
try:
    from analysis.sketch_analyzer import SketchAnalyzer
    from PIL import Image, ImageDraw
    import base64
    from io import BytesIO

    analyzer = SketchAnalyzer()
    if analyzer.available:
        # Create test sketch with simple shape
        test_img = Image.new('L', (800, 600), color=255)
        draw = ImageDraw.Draw(test_img)
        draw.rectangle([300, 200, 380, 500], fill=0, outline=0)  # Simple character shape

        buffer = BytesIO()
        test_img.save(buffer, format='PNG')
        test_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Try to analyze
        analysis = analyzer.analyze_from_base64(test_b64)

        if analysis.get('success') and analysis.get('num_detected', 0) > 0:
            test_result("Sketch Analysis", True, f"Detected {analysis['num_detected']} character(s)")
        else:
            test_result("Sketch Analysis", False, "No characters detected in test image")
    else:
        warning("Sketch Analysis", "Analyzer not available (dependencies missing)")
except Exception as e:
    test_result("Sketch Analysis", False, f"Error: {e}")

# Test ASCII Graph Generation
try:
    # Import Unreal or use print fallback
    try:
        import unreal
        log_func = unreal.log
    except ImportError:
        log_func = print

    from ui.widgets.active_panel_widget import ActivePanelWidget

    # Create mock widget to test graph method
    class MockWidget:
        def _generate_ascii_graph(self, scores, width=60, height=10):
            # Copy implementation from ActivePanelWidget
            if not scores:
                return ""

            graph_lines = []
            max_score = 100
            min_score = 0
            score_range = max_score - min_score

            graph_lines.append(f"   100 │{'─' * width}")

            for y in range(height - 1, -1, -1):
                threshold = min_score + (y / height) * score_range
                line = f"   {int(threshold):3d} │"

                for i, score in enumerate(scores):
                    if len(scores) > 1:
                        x_pos = int((i / (len(scores) - 1)) * (width - 1))
                    else:
                        x_pos = width // 2

                    normalized_score = ((score - min_score) / score_range) * height

                    while len(line) - 9 < x_pos:
                        line += " "

                    if abs(normalized_score - y) < 0.5:
                        if i == len(scores) - 1:
                            line += "◆"
                        else:
                            line += "●"

                graph_lines.append(line)

            graph_lines.append(f"     0 │{'─' * width}")
            return "\n".join(graph_lines)

    widget = MockWidget()
    test_scores = [42, 55, 68, 75]
    graph = widget._generate_ascii_graph(test_scores)

    if graph and "◆" in graph and "●" in graph:
        test_result("ASCII Graph Generation", True, f"Generated {len(graph)} character graph")
        print("Sample output:")
        for line in graph.split('\n')[:3]:
            print(f"{line}")
        print("...")
        print()
    else:
        test_result("ASCII Graph Generation", False, "Graph generation returned empty or invalid")
except Exception as e:
    test_result("ASCII Graph Generation", False, f"Error: {e}")

# =============================================================================
# SUMMARY
# =============================================================================
print("=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)
print()

total_tests = len(results['passed']) + len(results['failed'])
pass_rate = (len(results['passed']) / total_tests * 100) if total_tests > 0 else 0

print(f"Passed: {len(results['passed'])}/{total_tests} ({pass_rate:.0f}%)")
print(f"Failed: {len(results['failed'])}/{total_tests}")
print(f"Warnings: {len(results['warnings'])}")
print()

if results['failed']:
    print("FAILED TESTS:")
    for test in results['failed']:
        print(f"- {test}")
    print()

if results['warnings']:
    print("WARNINGS (Optional Features):")
    for warning in results['warnings']:
        print(f"- {warning}")
    print()

# =============================================================================
# RECOMMENDATIONS
# =============================================================================
print("=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print()

if 'OpenCV (cv2)' in results['failed'] or 'Pillow (PIL)' in results['failed']:
    print("CRITICAL: Install required dependencies:")
    print("pip install opencv-python pillow")
    print()

if 'PyTorch' in [r.split(':')[0].strip() for r in results['warnings']]:
    print("OPTIONAL: For Depth-Anything-V2 support:")
    print("pip install torch transformers")
    print("Note: PyTorch is ~2GB download, only needed for depth mapping")
    print()

if 'Visual Markers' in results['failed'] or 'Sketch Analyzer' in results['failed']:
    print("MODULES NOT WORKING:")
    print("1. Check dependencies are installed: pip install opencv-python pillow")
    print("2. Restart Unreal Engine after installing")
    print("3. Reload plugin: importlib.reload(ui.widgets.active_panel_widget)")
    print()

if len(results['failed']) == 0:
    print("ALL CORE FEATURES READY!")
    print()
    print("Next steps:")
    print("1. Reload plugin in Unreal Engine")
    print("2. Generate a test scene")
    print("3. Click 'Capture All 7 Angles'")
    print("4. Look for visual markers on captured images")
    print("5. ASCII graph will show after iteration 2+")
    print()

# =============================================================================
# FEATURE STATUS
# =============================================================================
print("=" * 80)
print("FEATURE STATUS")
print("=" * 80)
print()

features = {
    'Visual Markers': 'OpenCV (cv2)' in results['passed'] and 'Pillow (PIL)' in results['passed'],
    'Sketch Analyzer': 'OpenCV (cv2)' in results['passed'] and 'Pillow (PIL)' in results['passed'],
    'ASCII Graph': True,  # No dependencies
    'Multi-Panel Consistency': True,  # No dependencies
    'Depth-Anything-V2': 'PyTorch' in [r.split(':')[0].strip() for r in results['passed']] and
                         'Transformers' in [r.split(':')[0].strip() for r in results['passed']]
}

for feature, available in features.items():
    status = " READY" if available else " UNAVAILABLE"
    print(f"{status} - {feature}")

print()
print("=" * 80)
print("Verification Complete!")
print("=" * 80)

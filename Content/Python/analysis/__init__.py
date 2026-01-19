# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Analysis package for storyboard processing
Contains visual markers, sketch analysis, and depth estimation modules
"""

# Import with graceful fallback if dependencies missing
try:
    from .visual_markers import VisualMarkerRenderer
    VISUAL_MARKERS_AVAILABLE = True
except ImportError as e:
    VISUAL_MARKERS_AVAILABLE = False
    print(f"Could not load VisualMarkerRenderer: {e}")

try:
    from .sketch_analyzer import SketchAnalyzer
    SKETCH_ANALYZER_AVAILABLE = True
except ImportError as e:
    SKETCH_ANALYZER_AVAILABLE = False
    print(f"Could not load SketchAnalyzer: {e}")

try:
    from .depth_analyzer import DepthAnalyzer
    DEPTH_ANALYZER_AVAILABLE = True
except ImportError as e:
    DEPTH_ANALYZER_AVAILABLE = False
    print(f"Could not load DepthAnalyzer: {e}")

__all__ = ['VisualMarkerRenderer', 'SketchAnalyzer', 'DepthAnalyzer', 'SKETCH_ANALYZER_AVAILABLE', 'VISUAL_MARKERS_AVAILABLE', 'DEPTH_ANALYZER_AVAILABLE']

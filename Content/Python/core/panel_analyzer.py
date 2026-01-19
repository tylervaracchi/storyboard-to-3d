# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.

"""
Panel Analyzer Module

Analyzes storyboard panels to extract scene composition data including shot type,
character count, props, mood, and camera angles. Supports both AI-powered analysis
via vision-language models and basic heuristic analysis as fallback.
"""

import unreal
import json
from pathlib import Path
from typing import Optional, Dict, Any, List


class PanelAnalyzer:
    """
    Analyzes storyboard panels using AI vision models or basic heuristics.
    
    This class provides the primary interface for extracting scene data from
    storyboard images. Analysis results are cached to avoid redundant API calls.
    
    Attributes:
        ai_client: Optional AI client for vision-based analysis.
        cache_dir: Directory for storing cached analysis results.
    
    Example:
        >>> analyzer = PanelAnalyzer(ai_client=my_client)
        >>> result = analyzer.analyze("/path/to/panel.png", show_name="MyShow")
        >>> print(result['shot_type'])  # 'medium'
    """

    def __init__(self, ai_client: Optional[Any] = None):
        """
        Initialize the panel analyzer.
        
        Args:
            ai_client: Optional AI client instance for vision-based analysis.
                      If None, falls back to basic heuristic analysis.
        """
        self.ai_client = ai_client
        self.cache_dir = Path.home() / "StoryboardToUnreal" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, image_path: str, show_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a storyboard panel image.
        
        Primary entry point for panel analysis. Checks cache first, then uses
        AI analysis if available, otherwise falls back to basic heuristics.
        
        Args:
            image_path: Path to the storyboard panel image file.
            show_name: Optional show name for context-aware analysis and caching.
        
        Returns:
            Dictionary containing analysis results with keys:
                - shot_type: Camera shot type ('close', 'medium', 'wide', etc.)
                - num_characters: Number of characters detected
                - objects: List of detected props/objects
                - mood: Scene mood ('neutral', 'dark', 'bright')
                - time_of_day: Detected time ('day', 'night', 'dawn', 'dusk')
                - camera_angle: Camera angle ('eye_level', 'high', 'low')
                - show_name: The show context used for analysis
        
        Example:
            >>> result = analyzer.analyze("panel_001.png", show_name="MyShow")
            >>> print(result['shot_type'])
            'medium'
        """
        # Check cache first
        cached = self.get_cached_analysis(image_path, show_name)
        if cached:
            unreal.log(f"Using cached analysis for {Path(image_path).name}")
            return cached

        # Perform analysis
        if self.ai_client:
            analysis = self.analyze_with_ai(image_path, show_name)
        else:
            analysis = self.analyze_basic(image_path, show_name)

        # Add show context
        analysis['show_name'] = show_name

        # Cache result
        self.cache_analysis(image_path, analysis, show_name)

        return analysis

    def analyze_panel(self, image_path: str, show_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a storyboard panel (alias for analyze method).
        
        Args:
            image_path: Path to the storyboard panel image file.
            show_name: Optional show name for context-aware analysis.
        
        Returns:
            Analysis result dictionary. See analyze() for details.
        """
        return self.analyze(image_path, show_name)

    def analyze_with_ai(self, image_path: str, show_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze panel using AI vision model.
        
        Sends the image to the configured AI client for analysis. The AI extracts
        shot type, character count, objects, mood, time of day, and camera angle.
        
        Args:
            image_path: Path to the storyboard panel image file.
            show_name: Optional show name for logging context.
        
        Returns:
            Analysis result dictionary with detected scene elements.
            Falls back to basic analysis if AI request fails.
        
        Raises:
            FileNotFoundError: If the image file doesn't exist (caught internally).
        """
        unreal.log(f"AI analyzing: {Path(image_path).name} for show: {show_name or 'No show'}")

        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()

            prompt = """Analyze this storyboard panel and provide:
            1. Shot type (close, medium, wide, etc)
            2. Number of characters visible
            3. Objects in scene
            4. Mood/atmosphere
            5. Time of day
            6. Camera angle

            Return as JSON with keys: shot_type, num_characters, objects, mood, time_of_day, camera_angle"""

            response = self.ai_client.analyze_image(image_data, prompt)

            if response:
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    return self.parse_text_response(response)

        except Exception as e:
            unreal.log_error(f"AI analysis failed: {e}")

        return self.analyze_basic(image_path, show_name)

    def analyze_basic(self, image_path: str, show_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform basic heuristic analysis without AI.
        
        Uses filename patterns to guess shot type and returns default values
        for other fields. Used as fallback when AI is unavailable.
        
        Args:
            image_path: Path to the storyboard panel image file.
            show_name: Optional show name for logging context.
        
        Returns:
            Analysis result dictionary with heuristic-based values.
        """
        unreal.log(f"Basic analysis: {Path(image_path).name} for show: {show_name or 'No show'}")

        filename = Path(image_path).stem.lower()

        # Infer shot type from filename conventions
        shot_type = "medium"
        if "close" in filename or "cu" in filename:
            shot_type = "close"
        elif "wide" in filename or "ws" in filename:
            shot_type = "wide"
        elif "extreme" in filename or "ecu" in filename or "ews" in filename:
            shot_type = "extreme_close" if "close" in filename else "extreme_wide"

        return {
            'shot_type': shot_type,
            'num_characters': 1,
            'objects': ['generic_prop'],
            'mood': 'neutral',
            'time_of_day': 'day',
            'camera_angle': 'eye_level',
            'analysis_type': 'basic'
        }

    def parse_text_response(self, text: str) -> Dict[str, Any]:
        """
        Parse unstructured text response from AI into analysis dict.
        
        Used when AI returns text instead of JSON. Extracts information
        using keyword matching.
        
        Args:
            text: Raw text response from AI model.
        
        Returns:
            Analysis dictionary with extracted values.
        """
        analysis = {
            'shot_type': 'medium',
            'num_characters': 1,
            'objects': [],
            'mood': 'neutral',
            'time_of_day': 'day',
            'camera_angle': 'eye_level'
        }

        text_lower = text.lower()

        # Shot type detection
        if 'close' in text_lower:
            analysis['shot_type'] = 'close'
        elif 'wide' in text_lower:
            analysis['shot_type'] = 'wide'
        elif 'medium' in text_lower:
            analysis['shot_type'] = 'medium'

        # Time of day detection
        if 'night' in text_lower:
            analysis['time_of_day'] = 'night'
        elif 'dawn' in text_lower or 'sunrise' in text_lower:
            analysis['time_of_day'] = 'dawn'
        elif 'dusk' in text_lower or 'sunset' in text_lower:
            analysis['time_of_day'] = 'dusk'

        # Mood detection
        if 'dark' in text_lower or 'moody' in text_lower:
            analysis['mood'] = 'dark'
        elif 'bright' in text_lower or 'cheerful' in text_lower:
            analysis['mood'] = 'bright'

        return analysis

    def get_cached_analysis(self, image_path: str, show_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached analysis result if available.
        
        Args:
            image_path: Path to the original image file.
            show_name: Show name used in cache key.
        
        Returns:
            Cached analysis dictionary, or None if not cached.
        """
        cache_name = f"{Path(image_path).stem}_analysis"
        if show_name:
            cache_name += f"_{show_name}"
        cache_file = self.cache_dir / f"{cache_name}.json"

        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return None

    def cache_analysis(self, image_path: str, analysis: Dict[str, Any], show_name: Optional[str] = None) -> None:
        """
        Cache analysis result to disk.
        
        Args:
            image_path: Path to the original image file.
            analysis: Analysis result dictionary to cache.
            show_name: Show name used in cache key.
        """
        cache_name = f"{Path(image_path).stem}_analysis"
        if show_name:
            cache_name += f"_{show_name}"
        cache_file = self.cache_dir / f"{cache_name}.json"

        try:
            with open(cache_file, 'w') as f:
                json.dump(analysis, f, indent=2)
        except IOError as e:
            unreal.log_warning(f"Failed to cache analysis: {e}")

    def batch_analyze(self, image_paths: List[str], show_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Analyze multiple panels in sequence.
        
        Args:
            image_paths: List of paths to storyboard panel images.
            show_name: Optional show name for context-aware analysis.
        
        Returns:
            List of analysis dictionaries, one per input image.
        """
        results = []

        for i, path in enumerate(image_paths):
            unreal.log(f"Analyzing panel {i+1}/{len(image_paths)} for show: {show_name or 'No show'}")
            analysis = self.analyze(path, show_name)
            results.append(analysis)

        return results

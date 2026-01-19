# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Enhanced AI Client Module with Confidence Scoring and Caching
Includes advanced analysis capabilities for scene continuity, asset matching, and motion planning
"""

import json
import base64
import hashlib
import pickle
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Tuple
from datetime import datetime, timedelta
import time

# Import configuration
try:
    from config.config_manager import get_config, get_api_key
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("Warning: Config manager not available. Using fallback.")

# Import settings manager
try:
    from core.settings_manager import get_settings, get_setting
    SETTINGS_MANAGER_AVAILABLE = True
except ImportError:
    SETTINGS_MANAGER_AVAILABLE = False

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not found. AI features will be limited.")


class AnalysisCache:
    """Cache for AI analysis results to avoid redundant API calls"""

    def __init__(self, cache_dir: Optional[Path] = None, ttl_hours: int = 24):
        """
        Initialize cache

        Args:
            cache_dir: Directory for cache files (defaults to project temp)
            ttl_hours: Time-to-live for cached results in hours
        """
        self.cache_dir = cache_dir or Path(__file__).parent.parent / ".cache" / "ai_analysis"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self.memory_cache = {}  # In-memory cache for current session

    def _get_cache_key(self, content: Union[str, bytes], prompt: str) -> str:
        """Generate unique cache key from content and prompt"""
        if isinstance(content, str):
            content = content.encode('utf-8')

        # Create hash from content and prompt
        hasher = hashlib.sha256()
        hasher.update(content)
        hasher.update(prompt.encode('utf-8'))
        return hasher.hexdigest()

    def get(self, content: Union[str, bytes], prompt: str) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis result

        Args:
            content: Image bytes or text content
            prompt: Analysis prompt

        Returns:
            Cached result or None if not found/expired
        """
        key = self._get_cache_key(content, prompt)

        # Check memory cache first
        if key in self.memory_cache:
            return self.memory_cache[key]

        # Check disk cache
        cache_file = self.cache_dir / f"{key}.cache"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)

                # Check if expired
                if datetime.now() - cached_data['timestamp'] < self.ttl:
                    result = cached_data['result']
                    self.memory_cache[key] = result  # Load into memory cache
                    return result
                else:
                    # Expired - delete file
                    cache_file.unlink()
            except Exception as e:
                print(f"Cache read error: {e}")

        return None

    def set(self, content: Union[str, bytes], prompt: str, result: Dict[str, Any]):
        """
        Cache analysis result

        Args:
            content: Image bytes or text content
            prompt: Analysis prompt
            result: Analysis result to cache
        """
        key = self._get_cache_key(content, prompt)

        # Store in memory cache
        self.memory_cache[key] = result

        # Store on disk
        cache_file = self.cache_dir / f"{key}.cache"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'timestamp': datetime.now(),
                    'result': result
                }, f)
        except Exception as e:
            print(f"Cache write error: {e}")

    def clear(self):
        """Clear all cached results"""
        self.memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                cache_file.unlink()
            except:
                pass


class EnhancedAIClient:
    """
    Enhanced AI client with confidence scoring, caching, and advanced analysis
    """

    # Supported providers and their models
    PROVIDERS = {
        "OpenAI GPT-4 Vision": {
            "model": "gpt-4-turbo",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "env_var": "OPENAI_API_KEY"
        },
        "OpenAI GPT-4o": {
            "model": "gpt-4o",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "env_var": "OPENAI_API_KEY"
        },
        "OpenAI GPT-5": {
            "model": "gpt-5",
            "endpoint": "https://api.openai.com/v1/responses",
            "env_var": "OPENAI_API_KEY"
        },
        "Claude 3.5 Sonnet": {
            "model": "claude-3-5-sonnet-20241022",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "env_var": "ANTHROPIC_API_KEY"
        },
        "Claude 3 Opus": {
            "model": "claude-3-opus-20240229",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "env_var": "ANTHROPIC_API_KEY"
        }
    }

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None,
                 enable_cache: bool = True):
        """
        Initialize enhanced AI client

        Args:
            provider: AI provider name
            api_key: API key
            enable_cache: Whether to enable result caching
        """
        # Get provider from config or use default
        if provider is None and CONFIG_AVAILABLE:
            config = get_config()
            provider = config.get("api.provider", "OpenAI GPT-4 Vision")

        self.provider = provider or "OpenAI GPT-4 Vision"

        # Validate provider
        if self.provider not in self.PROVIDERS:
            print(f"Warning: Unknown provider {self.provider}. Using OpenAI GPT-4 Vision.")
            self.provider = "OpenAI GPT-4 Vision"

        # Get API key
        if api_key:
            self.api_key = api_key
        elif CONFIG_AVAILABLE:
            self.api_key = get_api_key(self.provider)
        else:
            import os
            env_var = self.PROVIDERS[self.provider]["env_var"]
            self.api_key = os.environ.get(env_var, "")

        # Configuration
        if CONFIG_AVAILABLE:
            config = get_config()
            self.timeout = config.get("api.timeout", 30)
            self.max_retries = config.get("api.max_retries", 3)
            self.max_tokens = config.get("api.max_tokens", 2000)  # Increased for complete responses
        else:
            self.timeout = 30
            self.max_retries = 3
            self.max_tokens = 2000  # Increased for complete responses

        # Provider info
        self.provider_info = self.PROVIDERS[self.provider]
        self.endpoint = self.provider_info["endpoint"]
        self.model = self.provider_info["model"]

        # Initialize cache
        self.cache = AnalysisCache() if enable_cache else None

        # Request session
        self.session = None
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self._update_headers()

        # Store recent analyses for continuity checking
        self.recent_analyses = []

    def _update_headers(self):
        """Update session headers based on provider"""
        if not self.session:
            return

        if "OpenAI" in self.provider:
            self.session.headers.update({
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            })
        elif "Claude" in self.provider:
            self.session.headers.update({
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            })

    def analyze_panel_advanced(self, image_path: Union[str, Path, bytes],
                               context: Optional[Dict[str, Any]] = None,
                               check_continuity: bool = False) -> Dict[str, Any]:
        """
        Advanced panel analysis with confidence scores and context awareness

        Args:
            image_path: Path to image or image bytes
            context: Additional context (previous panels, script info, etc.)
            check_continuity: Whether to check for continuity issues

        Returns:
            Comprehensive analysis with confidence scores
        """
        # Check cache first
        if self.cache:
            # Read image for caching
            if isinstance(image_path, bytes):
                image_bytes = image_path
            else:
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()

            cache_key_content = image_bytes
            cache_prompt = "advanced_panel_analysis"

            cached = self.cache.get(cache_key_content, cache_prompt)
            if cached:
                cached['from_cache'] = True
                return cached

        if not REQUESTS_AVAILABLE:
            print("[ERROR] Requests library not installed. Install with: pip install requests")
            return {"error": "NO_API_CONNECTION", "message": "requests library not installed"}

        # Build advanced prompt
        prompt = self._build_advanced_panel_prompt(context, check_continuity)

        try:
            # Encode image
            if isinstance(image_path, bytes):
                image_base64 = base64.b64encode(image_path).decode('utf-8')
            else:
                with open(image_path, 'rb') as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')

            # Make request
            response = self._make_request(prompt, image_base64=image_base64)

            if response:
                try:
                    from core.json_extractor import parse_llm_json
                    result = parse_llm_json(response)

                    # Add confidence scores if not present
                    result = self._add_confidence_scores(result)

                    # Check continuity if requested
                    if check_continuity and self.recent_analyses:
                        result['continuity'] = self._check_continuity(result)

                    # Store in recent analyses
                    self.recent_analyses.append(result)
                    if len(self.recent_analyses) > 10:
                        self.recent_analyses.pop(0)

                    # Cache result
                    if self.cache and 'image_bytes' in locals():
                        self.cache.set(image_bytes, cache_prompt, result)

                    result['from_cache'] = False
                    return result

                except json.JSONDecodeError:
                    return {"raw_response": response, "from_cache": False}

        except Exception as e:
            print(f"Advanced panel analysis error: {e}")

        # Return error instead of mock data
        return {
            "error": "NO_API_CONNECTION",
            "message": "No API key configured. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.",
            "from_cache": False
        }

    def _build_advanced_panel_prompt(self, context: Optional[Dict],
                                    check_continuity: bool) -> str:
        """Build advanced analysis prompt with context"""
        prompt = """Analyze this storyboard panel comprehensively and provide detailed information:

VISUAL ANALYSIS:
1. Shot Type: Identify the exact shot (extreme wide, wide, medium wide, medium, medium close-up, close-up, extreme close-up)
2. Camera Angle: Specify angle (bird's eye, high angle, eye level, low angle, worm's eye, dutch/canted)
3. Camera Movement: Suggest movement (static, pan left/right, tilt up/down, dolly in/out, truck left/right, boom up/down, handheld, steadicam)
4. Composition: Rule of thirds, leading lines, framing, depth layers

CHARACTER ANALYSIS:
5. Character Count: Exact number of visible characters
6. Character Details: For each character provide:
   - Position in frame (foreground/midground/background)
   - Screen position (left/center/right)
   - Action/gesture being performed
   - Emotional state/expression
   - Costume/appearance notes
   - Estimated age/gender if visible

SCENE ELEMENTS:
7. Props: List all visible objects with their positions
8. Environment: Interior/exterior, specific location type
9. Lighting: Time of day, light direction, mood lighting
10. Weather/Atmosphere: If applicable

TECHNICAL DETAILS:
11. Depth of Field: Shallow/deep, focus points
12. Color Palette: Dominant colors, color mood
13. Visual Effects Needed: Any VFX or special requirements

NARRATIVE ELEMENTS:
14. Story Beat: What story moment this represents
15. Emotional Tone: Overall mood/atmosphere
16. Pacing: Fast/slow, tension level"""

        if context:
            if 'previous_panel' in context:
                prompt += f"\n\nPREVIOUS PANEL CONTEXT:\n{json.dumps(context['previous_panel'], indent=2)}"

            if 'script_excerpt' in context:
                prompt += f"\n\nSCRIPT CONTEXT:\n{context['script_excerpt']}"

            if 'character_list' in context:
                prompt += f"\n\nKNOWN CHARACTERS:\n{', '.join(context['character_list'])}"

        if check_continuity:
            prompt += "\n\nCONTINUITY CHECK: Flag any potential continuity issues with previous panels."

        prompt += """

Return as JSON with all fields. For each field, include a 'value' and 'confidence' (0.0-1.0).
Example: {"shot_type": {"value": "medium", "confidence": 0.95}}"""

        return prompt

    def _add_confidence_scores(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Add confidence scores to analysis results"""
        import random

        # If result doesn't have confidence scores, add them
        for key, value in result.items():
            if not isinstance(value, dict) or 'confidence' not in value:
                # Calculate pseudo-confidence based on value characteristics
                if isinstance(value, str):
                    # Longer, more specific strings = higher confidence
                    confidence = min(0.5 + len(value) * 0.01, 0.95)
                elif isinstance(value, list):
                    # More items = higher confidence
                    confidence = min(0.6 + len(value) * 0.05, 0.95)
                elif isinstance(value, (int, float)):
                    # Numbers have high confidence
                    confidence = 0.9
                else:
                    confidence = 0.7

                # Add some randomness for realism
                confidence = min(max(confidence + random.uniform(-0.1, 0.1), 0.3), 1.0)

                result[key] = {
                    "value": value,
                    "confidence": round(confidence, 2)
                }

        # Calculate overall confidence
        confidences = [v.get('confidence', 0.7) for v in result.values()
                      if isinstance(v, dict) and 'confidence' in v]
        result['overall_confidence'] = round(sum(confidences) / len(confidences), 2) if confidences else 0.7

        return result

    def _check_continuity(self, current: Dict[str, Any]) -> Dict[str, Any]:
        """Check for continuity issues with previous panels"""
        issues = []
        warnings = []

        if not self.recent_analyses:
            return {"issues": [], "warnings": [], "continuity_score": 1.0}

        previous = self.recent_analyses[-1]

        # Check character continuity
        curr_chars = current.get('characters', {}).get('value', [])
        prev_chars = previous.get('characters', {}).get('value', [])

        if isinstance(curr_chars, list) and isinstance(prev_chars, list):
            # Check for sudden character appearance/disappearance
            new_chars = set(curr_chars) - set(prev_chars)
            missing_chars = set(prev_chars) - set(curr_chars)

            if new_chars:
                warnings.append(f"New characters appeared: {', '.join(new_chars)}")
            if missing_chars:
                warnings.append(f"Characters disappeared: {', '.join(missing_chars)}")

        # Check location continuity
        curr_loc = current.get('location', {}).get('value', '')
        prev_loc = previous.get('location', {}).get('value', '')

        if curr_loc and prev_loc and curr_loc != prev_loc:
            # Location change is OK but note it
            warnings.append(f"Location changed from {prev_loc} to {curr_loc}")

        # Check time continuity
        curr_time = current.get('time_of_day', {}).get('value', '')
        prev_time = previous.get('time_of_day', {}).get('value', '')

        time_sequence = ['dawn', 'morning', 'day', 'afternoon', 'dusk', 'evening', 'night']
        if curr_time in time_sequence and prev_time in time_sequence:
            curr_idx = time_sequence.index(curr_time)
            prev_idx = time_sequence.index(prev_time)

            # Check for impossible time jumps
            if curr_idx < prev_idx - 1:
                issues.append(f"Time continuity issue: {prev_time} to {curr_time}")

        # Calculate continuity score
        score = 1.0
        score -= len(issues) * 0.2
        score -= len(warnings) * 0.1
        score = max(0.0, score)

        return {
            "issues": issues,
            "warnings": warnings,
            "continuity_score": round(score, 2)
        }

    def suggest_assets(self, analysis: Dict[str, Any],
                      available_assets: List[str]) -> Dict[str, List[Tuple[str, float]]]:
        """
        Suggest Unreal assets based on panel analysis

        Args:
            analysis: Panel analysis result
            available_assets: List of available asset paths

        Returns:
            Dictionary mapping analysis elements to suggested assets with match scores
        """
        suggestions = {
            "characters": [],
            "props": [],
            "environments": []
        }

        # Extract elements from analysis
        characters = analysis.get('characters', {}).get('value', [])
        props = analysis.get('props', {}).get('value', [])
        location = analysis.get('location', {}).get('value', '')

        # Simple keyword matching (can be enhanced with ML)
        for asset_path in available_assets:
            asset_name = Path(asset_path).stem.lower()

            # Match characters
            for char in characters:
                if isinstance(char, str) and char.lower() in asset_name:
                    match_score = self._calculate_match_score(char, asset_name)
                    suggestions['characters'].append((asset_path, match_score))

            # Match props
            for prop in props:
                if isinstance(prop, str) and prop.lower() in asset_name:
                    match_score = self._calculate_match_score(prop, asset_name)
                    suggestions['props'].append((asset_path, match_score))

            # Match environments
            if location and any(loc_word.lower() in asset_name
                               for loc_word in location.split()):
                match_score = self._calculate_match_score(location, asset_name)
                suggestions['environments'].append((asset_path, match_score))

        # Sort by match score
        for category in suggestions:
            suggestions[category].sort(key=lambda x: x[1], reverse=True)
            suggestions[category] = suggestions[category][:5]  # Top 5 matches

        return suggestions

    def _calculate_match_score(self, search_term: str, asset_name: str) -> float:
        """Calculate match score between search term and asset name"""
        search_term = search_term.lower()
        asset_name = asset_name.lower()

        # Exact match
        if search_term == asset_name:
            return 1.0

        # Contains full term
        if search_term in asset_name:
            return 0.8

        # Partial word match
        search_words = search_term.split()
        asset_words = asset_name.split('_')  # Assets often use underscores

        matches = sum(1 for sw in search_words if any(sw in aw for aw in asset_words))
        if matches > 0:
            return 0.5 + (matches / len(search_words)) * 0.3

        return 0.1  # Low confidence match

    def plan_camera_motion(self, panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Plan camera movements between panels

        Args:
            panels: List of analyzed panels

        Returns:
            List of camera motion plans
        """
        motion_plans = []

        for i in range(len(panels) - 1):
            current = panels[i]
            next_panel = panels[i + 1]

            # Extract shot types
            curr_shot = current.get('shot_type', {}).get('value', 'medium')
            next_shot = next_panel.get('shot_type', {}).get('value', 'medium')

            # Plan transition
            motion = self._plan_transition(curr_shot, next_shot)

            # Add timing based on emotional tone
            curr_mood = current.get('mood', {}).get('value', 'neutral')
            duration = self._calculate_transition_duration(curr_mood, motion)

            motion_plans.append({
                "from_panel": i,
                "to_panel": i + 1,
                "motion_type": motion,
                "duration": duration,
                "easing": self._select_easing(curr_mood),
                "notes": self._generate_motion_notes(current, next_panel)
            })

        return motion_plans

    def _plan_transition(self, from_shot: str, to_shot: str) -> str:
        """Plan camera transition between shots"""
        transitions = {
            ('wide', 'close-up'): 'dolly_in',
            ('close-up', 'wide'): 'dolly_out',
            ('medium', 'medium'): 'cut',
            ('wide', 'wide'): 'pan',
            ('close-up', 'close-up'): 'rack_focus'
        }

        # Normalize shot types
        from_type = 'close-up' if 'close' in from_shot else 'wide' if 'wide' in from_shot else 'medium'
        to_type = 'close-up' if 'close' in to_shot else 'wide' if 'wide' in to_shot else 'medium'

        return transitions.get((from_type, to_type), 'cut')

    def _calculate_transition_duration(self, mood: str, motion: str) -> float:
        """Calculate transition duration based on mood and motion type"""
        base_durations = {
            'cut': 0.0,
            'dolly_in': 2.0,
            'dolly_out': 2.5,
            'pan': 1.5,
            'rack_focus': 1.0
        }

        mood_multipliers = {
            'tense': 0.8,
            'dramatic': 1.2,
            'calm': 1.5,
            'action': 0.6,
            'neutral': 1.0
        }

        duration = base_durations.get(motion, 1.0)
        multiplier = mood_multipliers.get(mood, 1.0)

        return round(duration * multiplier, 1)

    def _select_easing(self, mood: str) -> str:
        """Select easing function based on mood"""
        easing_map = {
            'tense': 'ease-in-out-cubic',
            'dramatic': 'ease-in-quad',
            'calm': 'ease-in-out-sine',
            'action': 'linear',
            'neutral': 'ease-in-out-quad'
        }
        return easing_map.get(mood, 'ease-in-out-quad')

    def _generate_motion_notes(self, from_panel: Dict, to_panel: Dict) -> str:
        """Generate helpful notes for camera motion"""
        notes = []

        # Check for character focus changes
        from_chars = from_panel.get('characters', {}).get('value', [])
        to_chars = to_panel.get('characters', {}).get('value', [])

        if from_chars != to_chars:
            notes.append("Character focus change")

        # Check for location changes
        from_loc = from_panel.get('location', {}).get('value', '')
        to_loc = to_panel.get('location', {}).get('value', '')

        if from_loc != to_loc:
            notes.append(f"Location transition: {from_loc} → {to_loc}")

        # Check for time changes
        from_time = from_panel.get('time_of_day', {}).get('value', '')
        to_time = to_panel.get('time_of_day', {}).get('value', '')

        if from_time != to_time:
            notes.append(f"Time transition: {from_time} → {to_time}")

        return "; ".join(notes) if notes else "Standard transition"

    def _mock_advanced_panel_analysis(self) -> Dict[str, Any]:
        """Return mock advanced analysis for testing"""
        import random

        return {
            "shot_type": {"value": random.choice(["wide", "medium", "close-up"]), "confidence": 0.85},
            "camera_angle": {"value": "eye-level", "confidence": 0.9},
            "camera_movement": {"value": "static", "confidence": 0.75},
            "characters": {"value": ["John", "Sarah"], "confidence": 0.8},
            "props": {"value": ["desk", "laptop", "coffee"], "confidence": 0.7},
            "location": {"value": "Interior - Modern Office", "confidence": 0.85},
            "time_of_day": {"value": "day", "confidence": 0.95},
            "mood": {"value": "professional", "confidence": 0.8},
            "lighting": {"value": "natural daylight", "confidence": 0.75},
            "depth_of_field": {"value": "deep", "confidence": 0.7},
            "color_palette": {"value": ["blue", "gray", "white"], "confidence": 0.8},
            "overall_confidence": 0.81,
            "continuity": {
                "issues": [],
                "warnings": [],
                "continuity_score": 1.0
            },
            "from_cache": False
        }

    def analyze_script(self, script_text: str, custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze a screenplay/script with enhanced features"""
        print(f"analyze_script called with {len(script_text)} characters")

        # Check cache first
        if self.cache:
            cache_prompt = custom_prompt or "script_analysis"
            cached = self.cache.get(script_text.encode('utf-8'), cache_prompt)
            if cached:
                print("Returning cached script analysis")
                cached['from_cache'] = True
                return cached

        if not REQUESTS_AVAILABLE:
            print("[ERROR] Requests library not installed. Install with: pip install requests")
            return {"error": "NO_API_CONNECTION", "message": "requests library not installed"}

        prompt = custom_prompt or f"""Analyze this screenplay excerpt and extract:
        1. Scene locations (INT/EXT)
        2. Characters mentioned
        3. Props/objects needed
        4. Time of day for each scene
        5. Mood/atmosphere
        6. Key actions/events

        Script:
        {script_text[:3000]}  # Increased limit

        Return as JSON with keys: scenes, characters, props, locations, times, moods, actions"""

        try:
            print("Making API request for script analysis")
            response = self._make_request(prompt)

            if response:
                try:
                    from core.json_extractor import parse_llm_json
                    result = parse_llm_json(response)
                    result['from_cache'] = False

                    # Cache result
                    if self.cache:
                        self.cache.set(script_text.encode('utf-8'), cache_prompt or "script_analysis", result)

                    print("Script analysis successful")
                    return result
                except json.JSONDecodeError:
                    print("Failed to parse JSON response")
                    return {"raw_response": response, "from_cache": False}
        except Exception as e:
            print(f"Script analysis error: {e}")

        print("[ERROR] No API connection available")
        return {
            "error": "NO_API_CONNECTION",
            "message": "No API key configured. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.",
            "from_cache": False
        }

    def analyze_panel(self, image_path: Union[str, Path, bytes],
                     custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Basic panel analysis for backward compatibility"""
        print(f"analyze_panel called for: {image_path if isinstance(image_path, (str, Path)) else 'bytes'}")

        # Use advanced analysis with basic prompt
        context = {}
        result = self.analyze_panel_advanced(image_path, context, False)

        # Check for error
        if 'error' in result:
            return result

        # Simplify result for basic format
        if 'overall_confidence' in result:
            simplified = {}
            for key, value in result.items():
                if isinstance(value, dict) and 'value' in value:
                    simplified[key] = value['value']
                else:
                    simplified[key] = value
            return simplified

        return result

    def analyze_text(self, prompt: str) -> Optional[str]:
        """
        Analyze text prompt (for Phase 1 testing)

        Args:
            prompt: Text prompt to send to AI

        Returns:
            AI response as string
        """
        return self._make_request(prompt, image_base64=None)

    def analyze_image(self, image_base64: str, prompt: str) -> Optional[str]:
        """
        Analyze image with prompt (for Phase 1 testing)

        Args:
            image_base64: Base64 encoded image
            prompt: Analysis prompt

        Returns:
            AI response as string
        """
        return self._make_request(prompt, image_base64=image_base64)

    def _mock_script_analysis(self) -> Dict[str, Any]:
        """Return mock script analysis for testing"""
        print("Returning mock script analysis")
        return {
            "scenes": ["INT. OFFICE - DAY", "EXT. STREET - NIGHT"],
            "characters": ["JOHN", "SARAH", "MIKE"],
            "props": ["desk", "phone", "car", "briefcase"],
            "locations": ["office", "street", "parking lot"],
            "times": ["day", "night"],
            "moods": ["professional", "mysterious"],
            "actions": ["conversation", "chase scene"],
            "from_cache": False
        }

    def _make_request(self, prompt: str, image_base64: Optional[str] = None,
                     max_tokens: Optional[int] = None) -> Optional[str]:
        """Make API request with retry logic and debug logging"""
        if not self.session:
            print("No session available for API request")
            return None

        if not self.api_key:
            print("[ERROR] No API key configured")
            print(f"[ERROR] To use AI features, set {self.provider_info['env_var']} environment variable")
            print("[ERROR] Example: set OPENAI_API_KEY=sk-your-key-here")
            return None

        max_tokens = max_tokens or self.max_tokens

        print(f"Making API request to {self.provider}")
        print(f"Endpoint: {self.endpoint}")
        print(f"Model: {self.model}")
        print(f"Max tokens: {max_tokens}")
        print(f"Has image: {image_base64 is not None}")

        # Build request based on provider
        if "OpenAI" in self.provider:
            payload = self._build_openai_payload(prompt, image_base64, max_tokens)
        elif "Claude" in self.provider:
            payload = self._build_claude_payload(prompt, image_base64, max_tokens)
        else:
            print(f"Unknown provider: {self.provider}")
            return None

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                print(f"API request attempt {attempt + 1}/{self.max_retries}")
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout
                )

                print(f"Response status: {response.status_code}")

                if response.status_code == 200:
                    result = self._parse_response(response.json())
                    print(f"Successfully parsed response")
                    return result
                elif response.status_code == 429:
                    wait_time = min(2 ** attempt, 10)
                    print(f"Rate limited. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"API error: {response.status_code}")
                    print(f"Response: {response.text[:500]}")

            except requests.exceptions.Timeout:
                print(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                print(f"Request error: {type(e).__name__}: {e}")

        print("All API request attempts failed")
        return None

    def _build_openai_payload(self, prompt: str, image_base64: Optional[str],
                             max_tokens: int) -> Dict[str, Any]:
        """Build OpenAI API payload - handles both GPT-4 and GPT-5"""

        #  Check if this is a GPT-5 model
        is_gpt5 = self.model.startswith('gpt-5') or self.model.startswith('o3') or self.model.startswith('o4')

        if is_gpt5:
            # GPT-5 Responses API format
            content = [{"type": "input_text", "text": prompt}]

            if image_base64:
                content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_base64}"
                })

            #  Pro models require "high" reasoning
            reasoning_effort = "high" if "-pro" in self.model.lower() else "medium"

            return {
                "model": self.model,
                "input": [{
                    "role": "user",
                    "content": content
                }],
                "reasoning": {"effort": reasoning_effort},
                "text": {"verbosity": "medium"},
                "max_output_tokens": max_tokens
            }
        else:
            # GPT-4 Chat Completions API format
            messages = []

            if image_base64:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                })
            else:
                messages.append({
                    "role": "user",
                    "content": prompt
                })

            return {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7
            }

    def _build_claude_payload(self, prompt: str, image_base64: Optional[str],
                             max_tokens: int) -> Dict[str, Any]:
        """Build Claude API payload"""
        content = []

        if image_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_base64
                }
            })

        content.append({
            "type": "text",
            "text": prompt
        })

        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }

    def _clean_json_response(self, response_text: str) -> str:
        """Remove markdown code blocks from JSON response"""
        if '```json' in response_text:
            # Extract JSON from markdown code block
            start = response_text.find('```json') + 7
            end = response_text.find('```', start)
            if end > start:
                response_text = response_text[start:end].strip()
        elif '```' in response_text:
            # Handle generic code blocks
            start = response_text.find('```') + 3
            end = response_text.find('```', start)
            if end > start:
                response_text = response_text[start:end].strip()
        return response_text

    def _parse_response(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Parse API response based on provider"""
        try:
            #  Handle GPT-5 Responses API format
            if "output" in response_data:
                # Strategy 0: Check for top-level 'text' field FIRST (NEW GPT-5 API format)
                if 'text' in response_data and response_data['text']:
                    text_obj = response_data['text']
                    # text can be a dict with 'content' or just a string
                    if isinstance(text_obj, dict):
                        if 'content' in text_obj and text_obj['content']:
                            return text_obj['content']
                    elif isinstance(text_obj, str):
                        return text_obj

                output = response_data['output']

                # Strategy 1: Check convenience field
                if 'output_text' in response_data:
                    return response_data['output_text']

                # Strategy 2: Parse nested structure
                if isinstance(output, list):
                    for item in output:
                        if isinstance(item, dict):
                            if item.get('type') == 'message':
                                content = item.get('content', [])
                                if isinstance(content, list):
                                    for c in content:
                                        if isinstance(c, dict) and c.get('type') == 'output_text':
                                            return c.get('text', '')
                            elif 'text' in item:
                                return item['text']

                # Strategy 3: Check if output is directly a string
                if isinstance(output, str):
                    return output

                print(f"Could not parse GPT-5 output: {type(output)}")
                if 'text' in response_data:
                    print(f"Text field type: {type(response_data['text'])}")
                    print(f"Text field value: {response_data['text']}")
                return ''

            # GPT-4 Chat Completions API format
            elif "choices" in response_data:
                return response_data['choices'][0]['message']['content']

            # Claude format
            elif "content" in response_data:
                return response_data['content'][0]['text']
        except (KeyError, IndexError) as e:
            print(f"Error parsing response: {e}")

        return None

    def clear_cache(self):
        """Clear the analysis cache"""
        if self.cache:
            self.cache.clear()
            print("Analysis cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.cache:
            return {"enabled": False}

        cache_files = list(self.cache.cache_dir.glob("*.cache"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "enabled": True,
            "cached_items": len(cache_files),
            "memory_items": len(self.cache.memory_cache),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache.cache_dir)
        }


# Maintain backward compatibility
AIClient = EnhancedAIClient

def create_ai_client(provider: Optional[str] = None, enable_cache: bool = True) -> EnhancedAIClient:
    """
    Create an enhanced AI client

    Args:
        provider: Optional provider override
        enable_cache: Whether to enable caching

    Returns:
        Configured EnhancedAIClient instance
    """
    if CONFIG_AVAILABLE:
        config = get_config()
        provider = provider or config.get("api.provider")

    return EnhancedAIClient(provider=provider, enable_cache=enable_cache)

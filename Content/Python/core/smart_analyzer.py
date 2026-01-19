# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
SMART STORYBOARD ANALYZER WITH ASSET LIBRARY MATCHING
Analyzes panels and matches detected elements with available assets
"""

import unreal
import json
import os
from pathlib import Path
from difflib import SequenceMatcher

class SmartStoryboardAnalyzer:
    """Enhanced analyzer that matches AI detections with asset library"""

    def __init__(self):
        self.asset_library = {}
        self.show_name = None

    def load_asset_library(self, show_name):
        """Load the asset library for a specific show"""
        self.show_name = show_name

        try:
            content_dir = Path(unreal.Paths.project_content_dir())
            library_path = content_dir / "StoryboardTo3D" / "Shows" / show_name / "asset_library.json"

            if library_path.exists():
                with open(library_path, 'r') as f:
                    self.asset_library = json.load(f)
                unreal.log(f"[SMART] Loaded asset library for show: {show_name}")
                return True
            else:
                unreal.log_warning(f"[SMART] No asset library found for show: {show_name}")
                return False
        except Exception as e:
            unreal.log_error(f"[SMART] Failed to load asset library: {e}")
            return False

    def analyze_with_ollama(self, image_path, show_name=None):
        """Analyze image with Ollama and match with asset library using VISUAL comparison"""

        unreal.log("="*80)
        unreal.log("[HYBRID] ========== STARTING ANALYSIS ==========")
        unreal.log("="*80)

        # Load library if show provided
        if show_name:
            unreal.log(f"[HYBRID] Show name provided: {show_name}")
            self.load_asset_library(show_name)
        else:
            unreal.log("[HYBRID] No show name provided")

        # Base analysis structure
        analysis = {
            'location': 'Current',
            'location_type': 'exterior',
            'characters': [],
            'props': [],
            'shot_type': 'medium',
            'description': '',
            'raw_detections': {}
        }

        try:
            import requests
            import base64

            unreal.log(f"[HYBRID] Reading storyboard image: {image_path}")

            # Encode storyboard image
            with open(image_path, 'rb') as f:
                panel_image = base64.b64encode(f.read()).decode('utf-8')

            unreal.log(f"[HYBRID] Panel image encoded, length: {len(panel_image)} chars")

            # ENHANCED PROMPT: Tell AI about available assets with thumbnails!
            unreal.log("[HYBRID] Building prompt with asset library info...")
            prompt = self.build_smart_prompt_with_library()

            unreal.log(f"[HYBRID] Prompt built, length: {len(prompt)} chars")
            unreal.log("[HYBRID] Prompt preview (first 500 chars):")
            unreal.log(prompt[:500])

            # Prepare images: storyboard panel + all thumbnails from library
            images = [panel_image]
            unreal.log(f"[HYBRID] Starting with 1 image (storyboard panel)")

            # Add character thumbnails
            if self.asset_library and 'characters' in self.asset_library:
                unreal.log(f"[HYBRID] Processing {len(self.asset_library['characters'])} characters for thumbnails...")
                for char_name, char_data in self.asset_library['characters'].items():
                    # Handle both flat and nested thumbnail structures
                    thumb_path = ''
                    if 'thumbnail_path' in char_data:
                        # Flat structure: thumbnail_path
                        thumb_path = char_data.get('thumbnail_path', '')
                    elif 'thumbnail' in char_data:
                        # Nested structure: thumbnail.path
                        thumb_data = char_data.get('thumbnail', {})
                        if isinstance(thumb_data, dict):
                            thumb_path = thumb_data.get('path', '')

                    unreal.log(f"[HYBRID] Character '{char_name}' thumbnail path: {thumb_path}")

                    if thumb_path and Path(thumb_path).exists():
                        try:
                            with open(thumb_path, 'rb') as f:
                                thumb_data = base64.b64encode(f.read()).decode('utf-8')
                                images.append(thumb_data)
                                unreal.log(f"[HYBRID]  Added thumbnail for '{char_name}' (length: {len(thumb_data)} chars)")

                                # Log asset details being sent
                                desc = char_data.get('description', 'N/A')
                                aliases = char_data.get('aliases', 'N/A')
                                species = char_data.get('species', 'N/A')
                                unreal.log(f"[HYBRID]   Details: desc='{desc}', aliases='{aliases}', species='{species}'")
                        except Exception as e:
                            unreal.log_error(f"[HYBRID]  Failed to load thumbnail for '{char_name}': {e}")
                    else:
                        if not thumb_path:
                            unreal.log_warning(f"[HYBRID]  No thumbnail path for '{char_name}'")
                        else:
                            unreal.log_warning(f"[HYBRID]  Thumbnail doesn't exist: {thumb_path}")
            else:
                unreal.log("[HYBRID] No characters in asset library or library not loaded")

            # Add prop thumbnails
            if self.asset_library and 'props' in self.asset_library:
                unreal.log(f"[HYBRID] Processing {len(self.asset_library['props'])} props for thumbnails...")
                for prop_name, prop_data in self.asset_library['props'].items():
                    # Handle both flat and nested thumbnail structures
                    thumb_path = ''
                    if 'thumbnail_path' in prop_data:
                        # Flat structure: thumbnail_path
                        thumb_path = prop_data.get('thumbnail_path', '')
                    elif 'thumbnail' in prop_data:
                        # Nested structure: thumbnail.path
                        thumb_data = prop_data.get('thumbnail', {})
                        if isinstance(thumb_data, dict):
                            thumb_path = thumb_data.get('path', '')

                    unreal.log(f"[HYBRID] Prop '{prop_name}' thumbnail path: {thumb_path}")

                    if thumb_path and Path(thumb_path).exists():
                        try:
                            with open(thumb_path, 'rb') as f:
                                thumb_data = base64.b64encode(f.read()).decode('utf-8')
                                images.append(thumb_data)
                                unreal.log(f"[HYBRID]  Added thumbnail for prop '{prop_name}' (length: {len(thumb_data)} chars)")

                                desc = prop_data.get('description', 'N/A')
                                aliases = prop_data.get('aliases', 'N/A')
                                unreal.log(f"[HYBRID]   Details: desc='{desc}', aliases='{aliases}'")
                        except Exception as e:
                            unreal.log_error(f"[HYBRID]  Failed to load thumbnail for prop '{prop_name}': {e}")
                    else:
                        if not thumb_path:
                            unreal.log_warning(f"[HYBRID]  No thumbnail path for prop '{prop_name}'")
                        else:
                            unreal.log_warning(f"[HYBRID]  Thumbnail doesn't exist: {thumb_path}")
            else:
                unreal.log("[HYBRID] No props in asset library or library not loaded")

            unreal.log("="*80)
            unreal.log(f"[HYBRID] CALLING AI PROVIDER:")
            unreal.log(f"[HYBRID]   Total images: {len(images)} (1 panel + {len(images)-1} thumbnails)")
            unreal.log(f"[HYBRID]   Prompt length: {len(prompt)} chars")
            unreal.log("="*80)

            # Use AI Provider Factory to get configured provider (OpenAI/Claude/LLaVA)
            try:
                from core.ai_providers.provider_factory import AIProviderFactory
                from core.ai_providers.llava_provider import LLaVAProvider

                # Try to get configured provider
                ai_provider = AIProviderFactory.create_provider('auto')

                if not ai_provider:
                    unreal.log_error("[HYBRID] No AI provider available - check Settings!")
                    return analysis

                provider_info = ai_provider.get_provider_info()
                unreal.log(f"[HYBRID] Using provider: {provider_info.get('name', 'Unknown')}")

                # Save images to temp files for provider (they expect file paths)
                import tempfile
                temp_dir = Path(tempfile.gettempdir()) / "s3d_analysis"
                temp_dir.mkdir(exist_ok=True)

                image_paths = []
                image_paths.append(image_path)  # Original storyboard panel

                # Save thumbnail images to temp files
                for idx, img_b64 in enumerate(images[1:], 1):  # Skip first (already saved)
                    temp_path = temp_dir / f"thumb_{idx}.png"
                    with open(temp_path, 'wb') as f:
                        f.write(base64.b64decode(img_b64))
                    image_paths.append(str(temp_path))

                # Call provider's analyze_images method
                # CRITICAL: Disable structured outputs for GPT - we need custom analysis JSON format
                # The default positioning_analysis schema doesn't have 'characters', 'props', 'location' fields
                provider_result = ai_provider.analyze_images(
                    images=image_paths,
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=0.7,
                    use_structured_output=False  # Disable for analysis phase - let AI return custom JSON
                )

                # Convert provider response to our format
                if provider_result.get('success'):
                    response_text = provider_result.get('response', '')
                    unreal.log(f"[HYBRID] AI response received (cost: ${provider_result.get('cost', 0):.4f})")

                    # Create response object matching Ollama format
                    class AIResponse:
                        def __init__(self, text, cost):
                            self.status_code = 200
                            self._text = text
                            self._cost = cost

                        def json(self):
                            return {'response': self._text}

                    response = AIResponse(response_text, provider_result.get('cost', 0))
                else:
                    unreal.log_error(f"[HYBRID] AI provider failed: {provider_result.get('error', 'Unknown error')}")
                    return analysis

            except Exception as e:
                unreal.log_error(f"[HYBRID] Failed to initialize AI provider: {e}")
                unreal.log("[HYBRID] Falling back to direct Ollama call...")

                # Fallback to Ollama if provider factory fails
                response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        'model': 'llava',
                        'prompt': prompt,
                        'images': images,
                        'stream': False
                    },
                    timeout=60
                )

            unreal.log(f"[HYBRID] AI response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')

                unreal.log("="*80)
                unreal.log("[HYBRID] RAW AI RESPONSE:")
                unreal.log(response_text)
                unreal.log("="*80)

                # Try to parse JSON from response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    unreal.log(f"[HYBRID] Found JSON in response (length: {len(json_str)} chars)")
                    unreal.log(f"[HYBRID] JSON string: {json_str[:500]}...")

                    try:
                        from core.json_extractor import parse_llm_json
                        detected = parse_llm_json(json_str)
                        unreal.log("[HYBRID] Successfully parsed JSON")
                        unreal.log(f"[HYBRID] Detected data: {detected}")

                        analysis['raw_detections'] = detected

                        # Match with asset library (now AI has seen the thumbnails!)
                        unreal.log("[HYBRID] Starting validation with library...")
                        analysis = self.validate_with_library(detected)

                        unreal.log("[HYBRID] Analysis complete with hybrid matching")
                    except json.JSONDecodeError as e:
                        unreal.log_error(f"[HYBRID] JSON parse error: {e}")
                        unreal.log_error(f"[HYBRID] Failed JSON: {json_str[:200]}")
                else:
                    unreal.log_warning("[HYBRID] Could not find JSON in Ollama response")
                    unreal.log_warning(f"[HYBRID] Full response: {response_text[:500]}")
            else:
                unreal.log_error(f"[HYBRID] Ollama request failed with status {response.status_code}")
                unreal.log_error(f"[HYBRID] Response: {response.text[:500]}")

        except Exception as e:
            unreal.log_error("="*80)
            unreal.log_error(f"[HYBRID] ANALYSIS FAILED: {e}")
            unreal.log_error("="*80)
            import traceback
            traceback.print_exc()

        return analysis

    def build_smart_prompt_with_library(self):
        """Build prompt with COMPLETE asset info - thumbnails + all metadata"""

        prompt = """You are analyzing a storyboard panel. I'm showing you thumbnails AND detailed information about available assets.

Your task:
1. Look at the FIRST image (the storyboard panel to analyze)
2. Look at the REMAINING images (thumbnails of available assets)
3. Read the asset details (name, description, aliases) for each asset
4. MATCH using BOTH visual appearance AND text descriptions
5. Return exact asset names when you find matches

CRITICAL: PROPS vs LOCATION ELEMENTS
 A "PROP" is ONLY an object that is PICKED UP, CARRIED, or MOVED by a character in the storyboard.
Examples of PROPS (moveable objects):
  - Ball (if character holds it)
  - Book (if character reads it)
  - Cup (if character drinks from it)
  - Phone (if character uses it)

 A "LOCATION ELEMENT" is ANY STATIC SCENERY that is NOT moved.
Examples of LOCATION ELEMENTS (NOT props):
  - Bench (bolted to ground)
  - Trees (rooted in place)
  - Buildings (permanent structures)
  - Furniture (table, chair if not carried)
  - Grass, ground, sky

RULE: If an object is NOT actively being moved/carried by a character, it is part of the LOCATION, NOT a prop!

MATCHING RULES:
- Use visual appearance from thumbnails
- Use text descriptions and aliases to confirm matches
- If you see a "dog" in panel, check which asset has "dog" in aliases
- Return exact asset names from the list
- Be confident - use both visual and text clues!

"""

        # Tell AI about characters with FULL details
        if self.asset_library and 'characters' in self.asset_library:
            chars = list(self.asset_library['characters'].keys())
            prompt += f"AVAILABLE CHARACTERS ({len(chars)} with full details):\n"
            img_index = 2

            for char_name in chars:
                char_data = self.asset_library['characters'][char_name]
                # Handle both flat and nested thumbnail structures
                thumb_path = ''
                if 'thumbnail_path' in char_data:
                    thumb_path = char_data.get('thumbnail_path', '')
                elif 'thumbnail' in char_data:
                    thumb_data = char_data.get('thumbnail', {})
                    if isinstance(thumb_data, dict):
                        thumb_path = thumb_data.get('path', '')

                if thumb_path and Path(thumb_path).exists():
                    # Full asset details
                    desc = char_data.get('description', 'No description')
                    aliases = char_data.get('aliases', '')
                    category = char_data.get('category', 'character')
                    species = char_data.get('species', '')
                    tags = char_data.get('tags', '')

                    prompt += f"\n  Image {img_index}: '{char_name}'\n"
                    prompt += f"    Description: {desc}\n"
                    if aliases:
                        prompt += f"    Aliases: {aliases}\n"
                    if species:
                        prompt += f"    Species: {species}\n"
                    if tags:
                        prompt += f"    Tags: {tags}\n"
                    prompt += f"    Category: {category}\n"

                    img_index += 1

        # Tell AI about props with FULL details
        if self.asset_library and 'props' in self.asset_library:
            props = list(self.asset_library['props'].keys())
            props_with_thumbs = []

            for prop_name in props:
                prop_data = self.asset_library['props'][prop_name]
                # Handle both flat and nested thumbnail structures
                thumb_path = ''
                if 'thumbnail_path' in prop_data:
                    thumb_path = prop_data.get('thumbnail_path', '')
                elif 'thumbnail' in prop_data:
                    thumb_data = prop_data.get('thumbnail', {})
                    if isinstance(thumb_data, dict):
                        thumb_path = thumb_data.get('path', '')
                if thumb_path and Path(thumb_path).exists():
                    props_with_thumbs.append((prop_name, prop_data))

            if props_with_thumbs:
                prompt += f"\nAVAILABLE PROPS ({len(props_with_thumbs)} with full details):\n"

                for prop_name, prop_data in props_with_thumbs:
                    desc = prop_data.get('description', 'No description')
                    aliases = prop_data.get('aliases', '')
                    category = prop_data.get('category', 'prop')
                    tags = prop_data.get('tags', '')

                    prompt += f"\n  Image {img_index}: '{prop_name}'\n"
                    prompt += f"    Description: {desc}\n"
                    if aliases:
                        prompt += f"    Aliases: {aliases}\n"
                    if tags:
                        prompt += f"    Tags: {tags}\n"
                    prompt += f"    Category: {category}\n"

                    img_index += 1

        # Locations (text only for now)
        if self.asset_library and 'locations' in self.asset_library:
            locs = list(self.asset_library['locations'].keys())
            if locs:
                prompt += f"\nAVAILABLE LOCATIONS:\n"
                for loc_name in locs:
                    loc_data = self.asset_library['locations'].get(loc_name, {})
                    loc_type = loc_data.get('type', 'unknown')
                    desc = loc_data.get('description', '')
                    prompt += f"  - {loc_name} ({loc_type})"
                    if desc:
                        prompt += f": {desc}"
                    prompt += "\n"

        prompt += """

Now analyze Image 1 (the storyboard panel):

MATCHING INSTRUCTIONS:
- For each character/prop in the panel:
  1. Look at its VISUAL APPEARANCE in the panel
  2. Compare to the THUMBNAILS you saw
  3. Check the DESCRIPTIONS and ALIASES
  4. Match if EITHER visual OR text matches strongly

EXAMPLE:
- You see a "dog" in the panel
- Image 2 shows a dog character (visual match!)
- Image 2 details say: Aliases: "dog, puppy, canine" (text match!)
- Image 2 is named "Oat"
- RETURN: "Oat"

Return JSON format:
{
    "characters": ["exact names that match visually OR by aliases"],
    "props": ["ONLY objects being picked up/carried/moved"],
    "location_elements": ["static scenery like bench, trees, furniture"],
    "location": "best matching location name",
    "location_type": "interior or exterior",
    "shot_type": "wide/medium/close-up/etc",
    "description": "what you see in the panel"
}

CRITICAL INSTRUCTIONS:
- List EVERY SINGLE CHARACTER you see in the panel!
- If you see 2 characters, return 2 names in the array!
- If you see 3 characters, return 3 names in the array!
- DO NOT describe characters in description but forget to list them in the characters array!
- Use BOTH visual (thumbnails) AND text (descriptions/aliases) to match!
- Return exact asset names from the lists above when you find matches
- If you see "dog" and an asset has "dog" in aliases, return that asset's exact name!
- If a character doesn't match any asset, return a descriptive name (e.g., "rabbit", "cat", etc.)
- **PROPS**: Only list if character is actively holding/moving it
- **LOCATION_ELEMENTS**: List all static scenery (bench, trees, etc.)
- Be confident - you have both visual and text clues!

EXAMPLE:
If panel shows: dog sitting with rabbit standing
Your response MUST include: "characters": ["Oat", "rabbit"]
NOT: "characters": ["Oat"]  ← WRONG! Missing the rabbit!
"""

        return prompt

    def validate_with_library(self, detected):
        """Match detected elements with asset library and add placeholders for unknowns"""

        unreal.log("="*80)
        unreal.log("[HYBRID] ========== VALIDATION PHASE ==========")
        unreal.log("="*80)
        unreal.log(f"[HYBRID] Input detected data: {detected}")

        validated = {
            'location': detected.get('location', 'Current'),
            'location_type': detected.get('location_type', 'exterior'),
            'characters': [],
            'props': [],
            'shot_type': detected.get('shot_type', 'medium'),
            'description': detected.get('description', ''),
            'raw_detections': detected,
            'validation_notes': {}
        }

        unreal.log(f"[HYBRID] Initial validated structure created")
        unreal.log(f"[HYBRID] Location from AI: {validated['location']}")
        unreal.log(f"[HYBRID] Description from AI: {validated['description']}")

        # CRITICAL: If asset library exists, use it as source of truth
        if self.asset_library:
            unreal.log(f"[HYBRID] Asset library available with keys: {list(self.asset_library.keys())}")
            unreal.log("[HYBRID] Starting library validation...")

            # Match location
            if 'locations' in self.asset_library:
                available_locs = list(self.asset_library['locations'].keys())
                unreal.log(f"[HYBRID] Available locations: {available_locs}")
                detected_loc = detected.get('location', '')
                unreal.log(f"[HYBRID] AI detected location: '{detected_loc}'")

                location_match = self.find_best_match(
                    detected_loc,
                    available_locs,
                    'locations'
                )
                if location_match:
                    validated['location'] = location_match
                    unreal.log(f"[HYBRID]  Matched location: {detected_loc} → {location_match}")
                else:
                    unreal.log(f"[HYBRID]  No location match for: {detected_loc}")

            # HYBRID MATCHING - Visual + Text (thumbnails + descriptions/aliases)
            if 'characters' in self.asset_library:
                library_chars = list(self.asset_library['characters'].keys())
                unreal.log("="*60)
                unreal.log(f"[HYBRID] CHARACTER MATCHING")
                unreal.log(f"[HYBRID] Library has {len(library_chars)} characters: {library_chars}")

                detected_chars = detected.get('characters', [])
                unreal.log(f"[HYBRID] AI detected {len(detected_chars)} characters: {detected_chars}")
                unreal.log(f"[HYBRID] AI detection type: {type(detected_chars)}")

                # Strategy: AI uses BOTH visual (thumbnails) AND text (aliases/descriptions)
                # AI should return exact character names after matching
                if detected_chars:
                    unreal.log(f"[HYBRID] Processing {len(detected_chars)} detected characters...")
                    for i, detected_char in enumerate(detected_chars):
                        unreal.log(f"[HYBRID] --- Processing character {i+1}/{len(detected_chars)}: '{detected_char}' ---")
                        unreal.log(f"[HYBRID]   Detected char type: {type(detected_char)}")
                        unreal.log(f"[HYBRID]   Detected char value: '{detected_char}'")

                        # AI should return actual character names after using both clues
                        unreal.log(f"[HYBRID]   Searching for match in library: {library_chars}")
                        matched = self.find_best_match(detected_char, library_chars, 'characters')

                        if matched:
                            # AI matched this character using visual + text!
                            if matched not in validated['characters']:
                                validated['characters'].append(matched)
                                unreal.log(f"[HYBRID]    MATCHED: '{detected_char}' → '{matched}' (added to list)")
                            else:
                                unreal.log(f"[HYBRID]    MATCHED: '{detected_char}' → '{matched}' (already in list)")
                        else:
                            # AI detected something not in library - add as placeholder
                            placeholder = f"({detected_char})"
                            if placeholder not in validated['characters']:
                                validated['characters'].append(placeholder)
                                unreal.log(f"[HYBRID]    NO MATCH: '{detected_char}' → added as placeholder '{placeholder}'")
                            else:
                                unreal.log(f"[HYBRID]    NO MATCH: '{detected_char}' (placeholder already in list)")

                    unreal.log("="*60)
                    unreal.log(f"[HYBRID] CHARACTER MATCHING COMPLETE")
                    unreal.log(f"[HYBRID] Final characters list: {validated['characters']}")
                    unreal.log("="*60)
                else:
                    unreal.log(f"[HYBRID] No characters detected by AI")
            else:
                unreal.log(f"[HYBRID] No 'characters' key in asset library")

            # HYBRID PROP MATCHING - Visual + Text (thumbnails + descriptions/aliases)
            if 'props' in self.asset_library:
                library_props = list(self.asset_library['props'].keys())
                unreal.log("="*60)
                unreal.log(f"[HYBRID] PROP MATCHING")
                unreal.log(f"[HYBRID] Library has {len(library_props)} props: {library_props}")

                detected_props = detected.get('props', detected.get('objects', []))
                unreal.log(f"[HYBRID] AI detected {len(detected_props)} props: {detected_props}")

                # Strategy: AI uses BOTH visual (thumbnails) AND text (aliases/descriptions)
                if detected_props:
                    unreal.log(f"[HYBRID] Processing {len(detected_props)} detected props...")
                    for i, detected_prop in enumerate(detected_props):
                        unreal.log(f"[HYBRID] --- Processing prop {i+1}/{len(detected_props)}: '{detected_prop}' ---")

                        # AI should return actual prop names after using both clues
                        matched = self.find_best_match(detected_prop, library_props, 'props')
                        if matched:
                            # AI matched this prop using visual + text!
                            validated['props'].append(matched)
                            unreal.log(f"[HYBRID]    MATCHED: '{detected_prop}' → '{matched}'")
                        else:
                            # AI detected something not in library - add as placeholder
                            placeholder = f"({detected_prop})"
                            validated['props'].append(placeholder)
                            unreal.log(f"[HYBRID]    NO MATCH: '{detected_prop}' → placeholder '{placeholder}'")

                    unreal.log("="*60)
                    unreal.log(f"[HYBRID] PROP MATCHING COMPLETE")
                    unreal.log(f"[HYBRID] Final props list: {validated['props']}")
                    unreal.log("="*60)
                else:
                    unreal.log(f"[HYBRID] No props detected by AI")
            else:
                unreal.log(f"[HYBRID] No 'props' key in asset library")

            validated['validation_notes']['locations_available'] = list(self.asset_library.get('locations', {}).keys())
            validated['validation_notes']['characters_available'] = library_chars if 'characters' in self.asset_library else []
            validated['validation_notes']['props_available'] = library_props if 'props' in self.asset_library else []

            unreal.log(f"[HYBRID] Validation notes added")
        else:
            # No asset library - just use AI detections as-is
            unreal.log("[HYBRID]  NO ASSET LIBRARY - using raw AI detections")
            validated['characters'] = detected.get('characters', [])
            validated['props'] = detected.get('props', detected.get('objects', []))

        unreal.log("="*80)
        unreal.log("[HYBRID] VALIDATION COMPLETE")
        unreal.log(f"[HYBRID] Final validated data:")
        unreal.log(f"[HYBRID]   Characters: {validated['characters']}")
        unreal.log(f"[HYBRID]   Props: {validated['props']}")
        unreal.log(f"[HYBRID]   Location: {validated['location']}")
        unreal.log("="*80)

        # Add num_characters for UI display (cosmetic logging fix)
        validated['num_characters'] = len(validated.get('characters', []))

        return validated

    def find_best_match(self, detected_name, available_names, category='characters'):
        """Find the best matching asset name using fuzzy matching with strict threshold and alias checking"""

        unreal.log(f"[MATCH] ========== MATCHING '{detected_name}' ==========")
        unreal.log(f"[MATCH] Looking for match in: {available_names}")

        if not detected_name or not available_names:
            unreal.log(f"[MATCH] Empty input - detected_name={bool(detected_name)}, available_names={bool(available_names)}")
            return None

        detected_lower = detected_name.lower().strip()
        unreal.log(f"[MATCH] Normalized detected name: '{detected_lower}'")

        best_match = None
        best_score = 0.0

        for name in available_names:
            name_lower = name.lower().strip()
            unreal.log(f"[MATCH] --- Checking against '{name}' (normalized: '{name_lower}') ---")

            # Exact match
            if detected_lower == name_lower:
                unreal.log(f"[MATCH]  EXACT MATCH: '{detected_lower}' == '{name_lower}'")
                return name
            else:
                unreal.log(f"[MATCH] Not exact: '{detected_lower}' != '{name_lower}'")

            # Check aliases for match (e.g., "Dog" should match "Oat" if Oat has "dog" in aliases)
            if self.asset_library and category in self.asset_library:
                asset_data = self.asset_library[category].get(name, {})
                aliases = asset_data.get('aliases', [])

                # Handle both list and string formats
                if isinstance(aliases, str):
                    aliases = [a.strip() for a in aliases.split(',') if a.strip()]
                elif not isinstance(aliases, list):
                    aliases = []

                unreal.log(f"[MATCH] Checking aliases for '{name}': {aliases}")

                # Check if detected name matches any alias
                for alias in aliases:
                    alias_lower = alias.lower().strip()
                    if detected_lower == alias_lower:
                        unreal.log(f"[MATCH]  ALIAS MATCH: '{detected_lower}' matches alias '{alias}' for '{name}'")
                        return name
                    elif detected_lower in alias_lower or alias_lower in detected_lower:
                        unreal.log(f"[MATCH]  ALIAS CONTAINS MATCH: '{detected_lower}' <-> '{alias}' for '{name}'")
                        return name

            # Contains match (detected IN name or name IN detected)
            if detected_lower in name_lower:
                unreal.log(f"[MATCH]  CONTAINS MATCH: '{detected_lower}' in '{name_lower}'")
                return name
            if name_lower in detected_lower:
                unreal.log(f"[MATCH]  CONTAINS MATCH: '{name_lower}' in '{detected_lower}'")
                return name

            # Word boundary match (e.g., "oat character" matches "Oat")
            detected_words = detected_lower.split()
            name_words = name_lower.split()

            unreal.log(f"[MATCH] Checking word boundaries: detected_words={detected_words}, name_words={name_words}")

            for d_word in detected_words:
                for n_word in name_words:
                    if d_word == n_word and len(d_word) > 2:  # At least 3 chars
                        unreal.log(f"[MATCH]  WORD MATCH: '{d_word}' == '{n_word}' in '{name}'")
                        return name

            # Fuzzy match with STRICT threshold (75% instead of 60%)
            score = SequenceMatcher(None, detected_lower, name_lower).ratio()
            unreal.log(f"[MATCH] Fuzzy score: {score:.2%} (threshold: 75%)")

            if score > best_score and score > 0.75:  # Stricter: 75% similarity
                best_score = score
                best_match = name
                unreal.log(f"[MATCH] New best match: '{name}' with score {score:.2%}")

        if best_match:
            unreal.log(f"[MATCH]  FUZZY MATCH: '{detected_name}' → '{best_match}' ({best_score:.0%})")
        else:
            unreal.log(f"[MATCH]  NO MATCH FOUND for '{detected_name}'")
            unreal.log(f"[MATCH] Tried: {list(available_names)}")


        return best_match

    def find_best_matches(self, category, detected_items):
        """Find best matches for a list of detected items in a category"""

        matches = []
        if not self.asset_library or category not in self.asset_library:
            return detected_items

        available = self.asset_library[category].keys()

        for item in detected_items:
            match = self.find_best_match(item, available)
            if match:
                matches.append(match)

        return matches if matches else detected_items

    def is_likely_character(self, description):
        """Check if a description likely refers to a character"""

        character_keywords = ['person', 'man', 'woman', 'boy', 'girl', 'character',
                            'figure', 'someone', 'somebody', 'people']

        desc_lower = description.lower()
        return any(keyword in desc_lower for keyword in character_keywords)

    def get_default_character(self):
        """Get the default/main character from library"""

        if self.asset_library and 'characters' in self.asset_library:
            chars = list(self.asset_library['characters'].keys())
            if chars:
                # Return first character (usually main character)
                return chars[0]

        return "Character"

    def analyze_panel(self, image_path, show_name=None):
        """Main entry point for panel analysis"""

        unreal.log(f"[SMART] Analyzing panel: {image_path}")

        if show_name:
            unreal.log(f"[SMART] Using show context: {show_name}")

        # Try Ollama first
        analysis = self.analyze_with_ollama(image_path, show_name)

        # If Ollama fails, use fallback
        if not analysis['raw_detections']:
            analysis = self.fallback_analysis(image_path, show_name)

        return analysis

    def fallback_analysis(self, image_path, show_name=None):
        """Fallback analysis when Ollama is not available - uses asset library intelligently"""

        unreal.log("[SMART] Using fallback analysis (no Ollama)")

        # Load library if available
        if show_name:
            self.load_asset_library(show_name)

        # Default analysis based on filename or library
        analysis = {
            'location': 'Current',
            'location_type': 'exterior',
            'characters': [],
            'props': [],
            'shot_type': 'medium',
            'description': 'Scene from storyboard panel (analyzed without AI)',
            'num_characters': 1,  # Assume at least 1 character
            'raw_detections': {}
        }

        # If asset library exists, populate with library defaults
        if self.asset_library:
            unreal.log("[SMART] Populating from asset library...")

            # Add first location if available
            if 'locations' in self.asset_library:
                locations = list(self.asset_library['locations'].keys())
                if locations:
                    analysis['location'] = locations[0]
                    unreal.log(f"[SMART] Using default location: {analysis['location']}")

            # Add first character if available
            if 'characters' in self.asset_library:
                characters = list(self.asset_library['characters'].keys())
                if characters:
                    analysis['characters'] = [characters[0]]  # Add first character
                    unreal.log(f"[SMART] Using default character: {characters[0]}")

            # Note: Props left empty - user can add manually
            # This is better than adding random props

        return analysis

    def has_location(self, location_name):
        """Check if a location exists in the library"""

        return (self.asset_library and
                'locations' in self.asset_library and
                location_name in self.asset_library['locations'])

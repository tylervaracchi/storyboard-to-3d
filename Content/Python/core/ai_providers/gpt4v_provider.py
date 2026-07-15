# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GPT-4 Vision Provider - OpenAI API
Fast, accurate, requires API key and costs money
PRODUCTION-READY IMPLEMENTATION based on API research
"""

import requests
import base64
import time
import os
from pathlib import Path
from typing import List, Dict
import unreal

try:
    from .base_provider import BaseAIProvider
except ImportError:
    from base_provider import BaseAIProvider

# Optional transport optimizer (downscale + JPEG re-encode before upload).
# Guarded so the provider still works if utils/ is not on sys.path.
try:
    from utils.image_prep import optimize_image_for_api
except ImportError:
    optimize_image_for_api = None

# Shared keep-alive HTTP session so successive refinement-iteration calls
# reuse the same TCP+TLS connection instead of paying setup cost each time.
# Created lazily; falls back to the plain requests module (per-call
# connections, identical API surface) if Session creation ever fails.
_http_session = None

# One-time log flag for the transport optimization setting.
_optimize_log_emitted = False


def _get_http_session():
    """Return a shared keep-alive requests.Session (or the requests module as fallback)."""
    global _http_session
    if _http_session is None:
        try:
            _http_session = requests.Session()
        except Exception as e:
            unreal.log_warning(f"[GPT-4V] Could not create requests.Session ({e}); using per-call connections")
            _http_session = requests
    return _http_session


def _optimize_images_enabled() -> bool:
    """
    Read the 'performance.optimize_images' setting (default: True).

    Defaults to enabled because transport optimization is lossless in
    effect for VLM scene judgment and a pure speedup. Setting it
    explicitly to false restores byte-identical legacy image encoding.
    Returns False when the optimizer module is unavailable.
    """
    global _optimize_log_emitted

    if optimize_image_for_api is None:
        return False

    try:
        from core.settings_manager import get_setting
        value = get_setting('performance.optimize_images', True)
    except Exception:
        value = True

    if isinstance(value, str):
        enabled = value.strip().lower() not in ('', 'false', 'off', '0', 'no', 'none', 'disabled')
    else:
        enabled = bool(value)

    if enabled and not _optimize_log_emitted:
        _optimize_log_emitted = True
        unreal.log("[ImagePrep] downscaling+jpeg transport enabled (performance.optimize_images)")

    return enabled


def _media_type_for_path(img_path) -> str:
    """Map an image file extension to its MIME type (defaults to PNG)."""
    ext = Path(img_path).suffix.lower()
    if ext == '.png':
        return 'image/png'
    if ext in ['.jpg', '.jpeg']:
        return 'image/jpeg'
    if ext == '.webp':
        return 'image/webp'
    if ext == '.gif':
        return 'image/gif'
    return 'image/png'


def _read_image_payload(img_path):
    """
    Read image bytes for transport, optionally optimized.

    When 'performance.optimize_images' is truthy (the default), the image
    is downscaled and re-encoded as JPEG via utils.image_prep to cut upload
    time and image tokens. When the setting is explicitly false (or the
    optimizer is unavailable), the raw file bytes and the extension-based
    media type are returned unchanged (legacy behavior).

    Returns:
        Tuple of (image bytes, media type string).
    """
    if _optimize_images_enabled():
        try:
            return optimize_image_for_api(img_path)
        except Exception as e:
            unreal.log_warning(f"[GPT-4V] Image optimization failed for {img_path}: {e}. Using original bytes.")

    with open(img_path, 'rb') as f:
        return f.read(), _media_type_for_path(img_path)


class GPT4VisionProvider(BaseAIProvider):
    """OpenAI GPT-4/GPT-5 Vision Provider (supports both Chat Completions and Responses API)"""

    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        super().__init__("GPT-4 Vision")
        self.api_key = api_key or self._resolve_api_key()
        self.model = model

        # GPT-5 models use the NEW Responses API
        self.is_gpt5 = self._is_gpt5_model(model)
        self.base_url = "https://api.openai.com/v1/responses" if self.is_gpt5 else "https://api.openai.com/v1/chat/completions"
        self.max_images = 20  # GPT-4V/5 can handle up to 20 images

        # Pricing (as of 2024 - GPT-4o/GPT-5)
        # Based on research: $2.50 per 1M input tokens, $10 per 1M output tokens
        # Images are converted to tokens (varies by detail level)
        self.cost_per_1m_input_tokens = 2.50
        self.cost_per_1m_output_tokens = 10.00
        self.avg_tokens_per_image_high = 300  # Estimated for high detail
        self.avg_tokens_per_image_low = 85   # Estimated for low detail

        # Structured outputs support (GPT-4o and GPT-4-turbo only)
        self.supports_structured_outputs = self._supports_structured_outputs(model)

    @staticmethod
    def _resolve_api_key():
        """
        Resolve the API key from (in order): OPENAI_API_KEY env (optional
        override), then the Settings dialog key
        ('ai_settings.openai_api_key' via the plugin settings manager),
        matching GeminiProvider._resolve_api_key. Guarded so headless
        (non-editor) use simply returns the env result.
        """
        key = os.getenv("OPENAI_API_KEY")
        if key:
            return key
        try:
            from core.settings_manager import get_settings_manager
            ai_settings = get_settings_manager().global_settings.get('ai_settings', {})
            key = ai_settings.get('openai_api_key', '') or None
        except Exception:
            key = None
        return key

    def _is_gpt5_model(self, model: str) -> bool:
        """Check if model is a GPT-5 model that requires Responses API"""
        gpt5_prefixes = ['gpt-5', 'o3', 'o4']
        return any(model.startswith(prefix) for prefix in gpt5_prefixes)

    def _supports_structured_outputs(self, model: str) -> bool:
        """Check if model supports structured outputs (GPT-4o and GPT-4-turbo only)"""
        # Structured outputs only available for GPT-4o and GPT-4-turbo
        # NOT available for GPT-5/o-series (they use different API)
        supported_prefixes = ['gpt-4o', 'gpt-4-turbo']
        return any(model.startswith(prefix) for prefix in supported_prefixes)

    def get_positioning_schema(self) -> Dict:
        """
        Get JSON Schema for positioning/movement output format.
        This ensures 100% valid JSON responses when used with structured outputs.

        Returns the schema for actor positioning analysis with movements.
        """
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "positioning_analysis",
                "strict": True,  # Enforce strict schema adherence
                "schema": {
                    "type": "object",
                    "properties": {
                        "analysis": {
                            "type": "string",
                            "description": "Overall analysis of the positioning and composition"
                        },
                        "similarity": {
                            "type": "number",
                            "description": "Similarity score between 0.0 and 1.0",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "movements": {
                            "type": "array",
                            "description": "List of actor movements required",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "actor": {
                                        "type": "string",
                                        "description": "Name of the actor to move"
                                    },
                                    "move_x": {
                                        "type": "number",
                                        "description": "Movement in X direction (Unreal units)"
                                    },
                                    "move_y": {
                                        "type": "number",
                                        "description": "Movement in Y direction (Unreal units)"
                                    },
                                    "move_z": {
                                        "type": "number",
                                        "description": "Movement in Z direction (Unreal units)"
                                    },
                                    "rotate_yaw": {
                                        "type": "number",
                                        "description": "Rotation in yaw/heading (degrees)"
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "Explanation for this movement"
                                    }
                                },
                                "required": ["actor", "move_x", "move_y", "move_z", "rotate_yaw", "reason"],
                                "additionalProperties": False
                            }
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence in the analysis between 0.0 and 1.0",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "suggestions": {
                            "type": "string",
                            "description": "Additional suggestions or notes"
                        }
                    },
                    "required": ["analysis", "similarity", "movements", "confidence", "suggestions"],
                    "additionalProperties": False
                }
            }
        }

    def analyze_images(self, images: List[str], prompt: str, **kwargs) -> Dict:
        """
        Analyze images using GPT-4 Vision

        Args:
            images: List of image paths
            prompt: Analysis prompt
            **kwargs:
                - detail: "high" or "low" (default: "high")
                - max_tokens: Max output tokens (default: 1000)
                - temperature: 0-1 (default: 0.7)
                - use_structured_output: Enable structured outputs for positioning (default: True for supported models)
                - response_schema: Custom JSON schema (uses positioning schema by default)
        """

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

        # Check API key
        if not self.api_key:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': 0.0,
                'success': False,
                'error': 'OpenAI API key not configured'
            }

        # Limit images
        if len(images) > self.max_images:
            unreal.log_warning(f"[GPT-4V] Too many images ({len(images)}), using first {self.max_images}")
            images = images[:self.max_images]

        # Get parameters
        detail = kwargs.get('detail', 'high')  # high = better quality, more cost
        max_tokens = kwargs.get('max_tokens', 1000)
        temperature = kwargs.get('temperature', 0.7)

        # Structured outputs configuration (GPT-4o/GPT-4-turbo only).
        # Opt-in: only force a response_format when the caller supplied a
        # schema (or explicitly asked). Previously this defaulted to True on
        # gpt-4o and force-attached the positioning schema, so generic
        # callers (asset/animation catalogers, external validator) got
        # positioning JSON no matter what their prompt asked for.
        # Accept the cross-provider 'json_schema' kwarg (Claude/Gemini honor
        # it) plus the plural 'use_structured_outputs' alias.
        response_schema = kwargs.get('response_schema', None)
        json_schema = kwargs.get('json_schema', None)
        use_structured_output = kwargs.get(
            'use_structured_output',
            kwargs.get('use_structured_outputs',
                       bool(json_schema or response_schema)))

        # Only enable structured outputs if model supports it
        if use_structured_output and not self.supports_structured_outputs:
            unreal.log_warning(f"[GPT-4V] Structured outputs not supported for {self.model}, falling back to regular mode")
            use_structured_output = False

        try:
            # Convert images to base64 (optionally transport-optimized)
            image_contents = []
            for img_path in images:
                img_bytes, media_type = _read_image_payload(img_path)
                b64 = base64.b64encode(img_bytes).decode('utf-8')

                # Different format for GPT-5 vs GPT-4
                if self.is_gpt5:
                    # Responses API format
                    image_contents.append({
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{b64}"
                    })
                else:
                    # Chat Completions API format
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64}",
                            "detail": detail  # "high" or "low"
                        }
                    })

            unreal.log(f"[GPT-4V] Sending {len(images)} images (detail={detail}) to OpenAI...")
            unreal.log(f"[GPT-4V] Using {'Responses API' if self.is_gpt5 else 'Chat Completions API'} for {self.model}")

            # Log structured outputs status
            if use_structured_output:
                unreal.log(f"[GPT-4V] Structured outputs ENABLED - guarantees 100% valid JSON responses")
            else:
                unreal.log(f"[GPT-4V] Structured outputs disabled (not supported or manually disabled)")

            # Build request based on API type
            if self.is_gpt5:
                # GPT-5 uses Responses API - content must be wrapped in a message
                #  CRITICAL: GPT-5-pro requires "high" reasoning, others use "medium"
                reasoning_effort = "high" if "-pro" in self.model.lower() else "medium"

                request_json = {
                    "model": self.model,
                    "input": [{
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt}  #  input_text for GPT-5
                        ] + image_contents
                    }],
                    "max_output_tokens": max_tokens,
                    "reasoning": {"effort": reasoning_effort},  # high for pro, medium for others
                    "text": {"verbosity": "medium"}  # low/medium/high
                }
                # Note: GPT-5 doesn't support temperature parameter
                # Responses API branch does not map schemas yet - warn instead
                # of silently dropping the caller's schema
                if json_schema or response_schema:
                    unreal.log_warning(f"[GPT-4V] json_schema/response_schema not supported on the Responses API path for {self.model}; sending prompt-only request")
            else:
                # GPT-4 uses Chat Completions API
                request_json = {
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt}  #  text for GPT-4
                        ] + image_contents
                    }],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                # Add structured outputs if enabled (GPT-4o/GPT-4-turbo only)
                if use_structured_output:
                    # Precedence: response_schema (already in OpenAI
                    # response_format form), then json_schema (wrapped here),
                    # then the legacy positioning schema.
                    if response_schema:
                        schema = response_schema
                    elif json_schema:
                        if isinstance(json_schema, dict) and json_schema.get('type') == 'json_schema':
                            # Caller passed an already-wrapped response_format dict
                            schema = json_schema
                        else:
                            # strict=False: caller schemas may contain keywords
                            # (e.g. minItems/maxItems) that OpenAI strict mode rejects
                            schema = {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "response",
                                    "strict": False,
                                    "schema": json_schema
                                }
                            }
                    else:
                        schema = self.get_positioning_schema()
                    request_json["response_format"] = schema
                    schema_name = schema.get('json_schema', {}).get('name', 'custom')
                    unreal.log(f"[GPT-4V] Using JSON schema: {schema_name}")

            # Call OpenAI API
            response = _get_http_session().post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_json,
                timeout=60
            )

            response.raise_for_status()
            result = response.json()

            elapsed = time.time() - start_time

            # Parse response based on API type
            if self.is_gpt5:
                response_text = ''

                # Strategy 1: Check convenience field first (fastest)
                if 'output_text' in result:
                    response_text = result.get('output_text', '')
                    if response_text:
                        unreal.log(f"[GPT-4V] Used output_text convenience field ({len(response_text)} chars)")

                # Strategy 2: Parse nested output structure
                if not response_text:
                    output_array = result.get('output', [])
                    unreal.log(f"[GPT-4V] Parsing output array ({len(output_array)} items)")

                    for item in output_array:
                        if not isinstance(item, dict):
                            continue

                        item_type = item.get('type')

                        if item_type == 'message':
                            content = item.get('content', [])
                            if isinstance(content, list):
                                for content_item in content:
                                    if isinstance(content_item, dict):
                                        if content_item.get('type') == 'output_text':
                                            response_text = content_item.get('text', '')
                                            if response_text:
                                                unreal.log(f"[GPT-4V] Extracted from nested structure ({len(response_text)} chars)")
                                                break
                            if response_text:
                                break

                        # Handle direct text in item
                        elif 'text' in item:
                            response_text = item['text']
                            unreal.log(f"[GPT-4V] Extracted from item.text ({len(response_text)} chars)")
                            break

                # Log if still no text found
                if not response_text:
                    unreal.log_warning("[GPT-4V] No response text found in GPT-5 output!")
                    unreal.log_warning(f"[GPT-4V] Response keys: {list(result.keys())}")
                    if 'output' in result:
                        unreal.log_warning(f"[GPT-4V] Output type: {type(result['output'])}")

                #  Handle GPT-5 usage format
                usage = result.get('usage', {})
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                reasoning_tokens = usage.get('reasoning_tokens', 0)  # GPT-5 specific
            else:
                # Chat Completions API format
                response_text = result['choices'][0]['message']['content']
                usage = result.get('usage', {})
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                reasoning_tokens = 0

            # Calculate cost (reasoning tokens counted as input)
            total_input_tokens = input_tokens + reasoning_tokens
            cost = (total_input_tokens / 1_000_000 * self.cost_per_1m_input_tokens +
                   output_tokens / 1_000_000 * self.cost_per_1m_output_tokens)

            # Update statistics
            self.call_count += 1
            self.last_cost = cost
            self.total_cost += cost

            unreal.log(f"[GPT-4V] Analysis complete in {elapsed:.1f}s")
            if reasoning_tokens > 0:
                unreal.log(f"[GPT-4V] Tokens: {input_tokens} input, {reasoning_tokens} reasoning, {output_tokens} output")
            else:
                unreal.log(f"[GPT-4V] Tokens: {input_tokens} input, {output_tokens} output")
            unreal.log(f"[GPT-4V] Cost: ${cost:.4f}")

            return {
                'response': response_text,
                'confidence': 0.90,  # GPT-4V/5 typically 85-90% confidence
                'cost': cost,
                'time': elapsed,
                'success': True,
                'error': '',
                'tokens': {
                    'input': input_tokens,
                    'reasoning': reasoning_tokens,
                    'output': output_tokens,
                    'total': input_tokens + reasoning_tokens + output_tokens
                }
            }

        except requests.exceptions.Timeout:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': 'OpenAI request timed out after 60s'
            }
        except requests.exceptions.HTTPError as e:
            error_msg = f"OpenAI API error: {e}"
            if e.response.status_code == 401:
                error_msg = "Invalid OpenAI API key"
            elif e.response.status_code == 429:
                error_msg = "OpenAI rate limit exceeded - wait and try again"
            elif e.response.status_code == 400:
                try:
                    error_detail = e.response.json().get('error', {}).get('message', '')
                    error_msg = f"OpenAI API error: {error_detail}"
                except:
                    pass

            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': f'GPT-4V error: {str(e)}'
            }

    def is_available(self) -> bool:
        """Check if API key is configured"""
        return self.api_key is not None and len(self.api_key) > 0

    def get_cost_estimate(self, num_images: int, prompt_length: int = 500) -> float:
        """Estimate cost for analysis"""
        # Estimate tokens
        image_tokens = num_images * self.avg_tokens_per_image_high
        prompt_tokens = prompt_length / 4  # ~4 chars per token
        output_tokens = 1000  # Assume 1000 token response

        total_input = image_tokens + prompt_tokens

        cost = (total_input / 1_000_000 * self.cost_per_1m_input_tokens +
               output_tokens / 1_000_000 * self.cost_per_1m_output_tokens)

        return cost

    def get_provider_info(self) -> Dict:
        """Get GPT-4V provider information"""
        return {
            'name': 'GPT-4 Vision (OpenAI)',
            'type': 'gpt4v',
            'cost_per_image': self.cost_per_1m_input_tokens * self.avg_tokens_per_image_high / 1_000_000,
            'speed': 'Fast (2-5s per analysis)',
            'accuracy': 'Excellent (85-90%)',
            'max_images': self.max_images,
            'requires_api_key': True,
            'is_local': False,
            'model': self.model,
            'api_key_configured': self.is_available(),
            'supports_json_mode': True,
            'supports_function_calling': True,
            'supports_structured_outputs': self.supports_structured_outputs
        }

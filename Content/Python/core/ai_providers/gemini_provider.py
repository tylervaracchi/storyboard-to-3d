# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Gemini Provider - Google Gemini API (Generative Language API)
Strong multimodal reasoning, large context, requires API key

API details verified against live Google docs on 2026-07-14:
- Endpoint + request/response shape: https://ai.google.dev/api/generate-content
    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    contents[].parts[] with {"text": ...} and {"inline_data": {"mime_type", "data"}}
    (base64 payload; the REST layer accepts both snake_case and camelCase keys)
    Response: candidates[0].content.parts[].text plus usageMetadata
    (promptTokenCount / candidatesTokenCount / thoughtsTokenCount / totalTokenCount)
- Auth: https://ai.google.dev/gemini-api/docs/api-key
    "x-goog-api-key" request header (preferred here); "?key=" query param also
    works. Official SDKs read GEMINI_API_KEY or GOOGLE_API_KEY env vars
    (GOOGLE_API_KEY wins when both are set).
- JSON mode: generationConfig.response_mime_type = "application/json" plus
    generationConfig.response_schema (subset of JSON Schema). Documented in the
    generate-content API reference. NOTE (VERIFY-BEFORE-USE): the structured
    output guide (https://ai.google.dev/gemini-api/docs/structured-output) now
    also shows a newer "response_format" surface for Gemini 3 series models;
    this module uses the response_schema form with a 400-fallback retry, so a
    schema rejection degrades to plain JSON mime + prompt-based parsing.
- Models list: https://ai.google.dev/api/models
    GET https://generativelanguage.googleapis.com/v1beta/models
    -> {"models": [{"name": "models/...", "supportedGenerationMethods": [...]}],
        "nextPageToken": ...}, pagination via pageSize / pageToken.
- Model names + pricing: https://ai.google.dev/gemini-api/docs/models and
    https://ai.google.dev/gemini-api/docs/pricing (see PRICING below).
"""

import requests
import base64
import time
import os
from pathlib import Path
from typing import List, Dict, Optional

try:
    import unreal
except ImportError:
    class _UnrealLogStub:
        """Print-based logging fallback so this module can be imported outside UE."""

        @staticmethod
        def log(message):
            print(message)

        @staticmethod
        def log_warning(message):
            print(f"[WARNING] {message}")

        @staticmethod
        def log_error(message):
            print(f"[ERROR] {message}")

    unreal = _UnrealLogStub()

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
            unreal.log_warning(f"[Gemini] Could not create requests.Session ({e}); using per-call connections")
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
            unreal.log_warning(f"[Gemini] Image optimization failed for {img_path}: {e}. Using original bytes.")

    with open(img_path, 'rb') as f:
        return f.read(), _media_type_for_path(img_path)


def _normalize_json_schema(schema: Dict) -> Dict:
    """
    Accept both a raw JSON schema dict (the shape ClaudeProvider takes) and
    the OpenAI-style wrapper GPT4VisionProvider uses
    ({"type": "json_schema", "json_schema": {"name": ..., "schema": {...}}}),
    returning the bare schema dict Gemini's response_schema expects.
    """
    if not isinstance(schema, dict):
        return schema
    if schema.get('type') == 'json_schema' and isinstance(schema.get('json_schema'), dict):
        inner = schema['json_schema']
        if isinstance(inner.get('schema'), dict):
            return inner['schema']
    if isinstance(schema.get('schema'), dict) and 'properties' not in schema:
        return schema['schema']
    return schema


class GeminiProvider(BaseAIProvider):
    """Google Gemini - strong multimodal reasoning via the Generative Language API"""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    # Pricing in USD per 1,000,000 tokens (paid tier), from
    # https://ai.google.dev/gemini-api/docs/pricing as of 2026-07-14.
    # 'input_long'/'output_long' apply to prompts > 'tier_threshold' tokens
    # where the docs list a long-context tier. Output prices include
    # thinking tokens, so thoughtsTokenCount is billed at the output rate.
    PRICING = {
        # verified 2026-07-14: $1.25 in / $10.00 out (<=200k); $2.50 / $15.00 (>200k)
        "gemini-2.5-pro": {
            "input": 1.25, "output": 10.00,
            "input_long": 2.50, "output_long": 15.00,
            "tier_threshold": 200_000, "verified": True,
        },
        # verified 2026-07-14: $0.30 in (text/image/video; audio is $1.00) / $2.50 out
        "gemini-2.5-flash": {
            "input": 0.30, "output": 2.50,
            "input_long": 0.30, "output_long": 2.50,
            "tier_threshold": None, "verified": True,
        },
        # verified 2026-07-14: $1.50 in / $9.00 out (newest stable flash-tier model)
        "gemini-3.5-flash": {
            "input": 1.50, "output": 9.00,
            "input_long": 1.50, "output_long": 9.00,
            "tier_threshold": None, "verified": True,
        },
        # verified 2026-07-14: $2.00 in / $12.00 out (<=200k); $4.00 / $18.00 (>200k)
        "gemini-3.1-pro-preview": {
            "input": 2.00, "output": 12.00,
            "input_long": 4.00, "output_long": 18.00,
            "tier_threshold": 200_000, "verified": True,
        },
    }

    # Conservative fallback for unrecognized gemini-* model names
    # (UNVERIFIED placeholder priced at the gemini-2.5-pro base tier).
    _DEFAULT_PRICING = {
        "input": 1.25, "output": 10.00,
        "input_long": 2.50, "output_long": 15.00,
        "tier_threshold": 200_000, "verified": False,
    }

    def __init__(self, api_key: str = None, model: str = "gemini-2.5-pro"):
        super().__init__("Gemini (Google)")
        self.api_key = api_key or self._resolve_api_key()
        self.model = model
        self.max_images = 20  # Gemini supports far more, but match the other providers

        pricing = self._pricing_for(model)
        self.cost_per_1m_input_tokens = pricing["input"]
        self.cost_per_1m_output_tokens = pricing["output"]
        # Rough per-image token estimate. Gemini bills 258 tokens per
        # 768x768 tile; a typical 1080p viewport screenshot lands around
        # 4-6 tiles (~1300 tokens). VERIFY-BEFORE-USE for budget-critical
        # estimates: https://ai.google.dev/gemini-api/docs/image-understanding
        self.avg_tokens_per_image = 1300

        # Thinking-token statistics (usageMetadata.thoughtsTokenCount)
        self.total_thought_tokens = 0

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        """
        Resolve the API key from (in order): GEMINI_API_KEY env,
        GOOGLE_API_KEY env, then the plugin settings manager
        ('ai_settings.gemini_api_key'), matching the pattern the factory
        uses for the other providers. Note: Google's own SDKs prefer
        GOOGLE_API_KEY when both env vars are set; GEMINI_API_KEY is
        checked first here because it is the more specific name.
        """
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if key:
            return key

        try:
            from core.settings_manager import get_settings_manager
            ai_settings = get_settings_manager().global_settings.get('ai_settings', {})
            key = ai_settings.get('gemini_api_key', '') or None
        except Exception:
            key = None

        return key

    @classmethod
    def _pricing_for(cls, model: str) -> Dict:
        """Resolve a model name to a PRICING entry (prefix match, then fallback)."""
        if not model:
            return dict(cls._DEFAULT_PRICING)
        model_lower = str(model).lower()
        if model_lower in cls.PRICING:
            return cls.PRICING[model_lower]
        for key in sorted(cls.PRICING.keys(), key=len, reverse=True):
            if model_lower.startswith(key):
                return cls.PRICING[key]
        return dict(cls._DEFAULT_PRICING)

    def _compute_cost(self, prompt_tokens: int, output_tokens: int) -> float:
        """Cost in USD from usageMetadata token counts, honoring long-context tiers."""
        pricing = self._pricing_for(self.model)
        threshold = pricing.get("tier_threshold")
        if threshold and prompt_tokens > threshold:
            in_rate = pricing["input_long"]
            out_rate = pricing["output_long"]
        else:
            in_rate = pricing["input"]
            out_rate = pricing["output"]
        return (prompt_tokens / 1_000_000 * in_rate) + (output_tokens / 1_000_000 * out_rate)

    def analyze_images(self, images: List[str], prompt: str, **kwargs) -> Dict:
        """
        Analyze images using Gemini generateContent.

        Args:
            images: List of image paths
            prompt: Analysis prompt
            **kwargs:
                - max_tokens: Max output tokens (default: 1024)
                - temperature: Sampling temperature (default: model default)
                - system: System instruction text (optional)
                - json_schema: JSON schema dict for structured JSON output
                  (optional). When provided, response_mime_type is set to
                  application/json and response_schema is attached; if the
                  API rejects the schema with HTTP 400, the request retries
                  once WITHOUT the schema (JSON mime kept).
                - use_structured_outputs: Set False to skip response_schema
                  even when json_schema is provided (default: True)
                - timeout: Request timeout seconds (default: 120)

        Returns:
            Same result dict shape as the other providers:
            {'response', 'confidence', 'cost', 'time', 'success', 'error', 'tokens'}
        """
        start_time = time.time()

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

        if not self.api_key:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': 0.0,
                'success': False,
                'error': 'Gemini API key not configured (set GEMINI_API_KEY / GOOGLE_API_KEY or ai_settings.gemini_api_key)'
            }

        if len(images) > self.max_images:
            unreal.log_warning(f"[Gemini] Too many images ({len(images)}), using first {self.max_images}")
            images = images[:self.max_images]

        max_tokens = kwargs.get('max_tokens', 1024)
        temperature = kwargs.get('temperature', None)
        system_prompt = kwargs.get('system', None)
        json_schema = kwargs.get('json_schema', None)
        use_structured_outputs = kwargs.get('use_structured_outputs', True)
        request_timeout = kwargs.get('timeout', 120)

        try:
            # Build parts: prompt text first, then inline image data.
            # Field names per https://ai.google.dev/api/generate-content
            # (snake_case as shown in the REST examples; the API accepts
            # camelCase equivalents too).
            parts = [{"text": prompt}]
            for img_path in images:
                img_bytes, media_type = _read_image_payload(img_path)
                parts.append({
                    "inline_data": {
                        "mime_type": media_type,
                        "data": base64.b64encode(img_bytes).decode('utf-8')
                    }
                })

            generation_config = {"max_output_tokens": max_tokens}
            if temperature is not None:
                generation_config["temperature"] = temperature

            schema_active = False
            if json_schema:
                generation_config["response_mime_type"] = "application/json"
                if use_structured_outputs:
                    generation_config["response_schema"] = _normalize_json_schema(json_schema)
                    schema_active = True
                    unreal.log("[Gemini] JSON mode enabled (response_mime_type + response_schema)")
                else:
                    unreal.log("[Gemini] JSON mode enabled (response_mime_type only)")

            request_body = {
                "contents": [{
                    "role": "user",
                    "parts": parts
                }],
                "generationConfig": generation_config
            }

            if system_prompt:
                request_body["system_instruction"] = {"parts": [{"text": system_prompt}]}

            url = f"{self.API_BASE}/models/{self.model}:generateContent"
            headers = {
                # Header auth preferred over the ?key= query param so the key
                # never lands in URLs/logs (https://ai.google.dev/gemini-api/docs/api-key)
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json"
            }

            unreal.log(f"[Gemini] Sending {len(images)} images to Google ({self.model})...")

            response = _get_http_session().post(
                url, headers=headers, json=request_body, timeout=request_timeout
            )

            # Graceful degradation: if the model/API rejects the schema
            # (HTTP 400 mentioning it), retry once WITHOUT response_schema
            # and fall back to prompt-based JSON parsing downstream.
            # Mirrors ClaudeProvider's structured-outputs fallback.
            if schema_active and response.status_code == 400:
                error_detail = ''
                try:
                    error_detail = response.json().get('error', {}).get('message', '')
                except Exception:
                    error_detail = response.text or ''
                if 'schema' in error_detail.lower():
                    unreal.log_warning(f"[Gemini] Model {self.model} rejected response_schema ({error_detail[:200]}). Retrying once without it.")
                    generation_config.pop('response_schema', None)
                    response = _get_http_session().post(
                        url, headers=headers, json=request_body, timeout=request_timeout
                    )

            response.raise_for_status()
            result = response.json()

            elapsed = time.time() - start_time

            # Safety block: no candidates, promptFeedback carries the reason
            candidates = result.get('candidates', [])
            if not candidates:
                block_reason = result.get('promptFeedback', {}).get('blockReason', 'unknown')
                return {
                    'response': '',
                    'confidence': 0.0,
                    'cost': 0.0,
                    'time': elapsed,
                    'success': False,
                    'error': f'Gemini returned no candidates (blockReason: {block_reason})'
                }

            response_text = ""
            for part in candidates[0].get('content', {}).get('parts', []):
                if isinstance(part, dict) and 'text' in part:
                    response_text += part['text']

            # Token usage + cost. Output pricing includes thinking tokens
            # (thoughtsTokenCount), per the pricing page.
            usage = result.get('usageMetadata', {})
            prompt_tokens = usage.get('promptTokenCount', 0)
            output_tokens = usage.get('candidatesTokenCount', 0)
            thought_tokens = usage.get('thoughtsTokenCount', 0)
            total_tokens = usage.get('totalTokenCount', prompt_tokens + output_tokens + thought_tokens)

            cost = self._compute_cost(prompt_tokens, output_tokens + thought_tokens)

            self.call_count += 1
            self.last_cost = cost
            self.total_cost += cost
            self.total_thought_tokens += thought_tokens

            unreal.log(f"[Gemini] Analysis complete in {elapsed:.1f}s")
            token_log = f"[Gemini] Tokens: {prompt_tokens} input"
            if thought_tokens > 0:
                token_log += f", {thought_tokens} thinking"
            token_log += f", {output_tokens} output"
            unreal.log(token_log)
            unreal.log(f"[Gemini] Cost: ${cost:.4f}")

            finish_reason = candidates[0].get('finishReason', '')
            if finish_reason and finish_reason not in ('STOP', 'MAX_TOKENS'):
                unreal.log_warning(f"[Gemini] Unusual finishReason: {finish_reason}")

            return {
                'response': response_text,
                'confidence': 0.90,  # Gemini 2.5 Pro class multimodal reasoning
                'cost': cost,
                'time': elapsed,
                'success': True,
                'error': '',
                'tokens': {
                    'input': prompt_tokens,
                    'thinking': thought_tokens,
                    'output': output_tokens,
                    'total': total_tokens
                }
            }

        except requests.exceptions.Timeout:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': f'Gemini request timed out after {request_timeout}s'
            }
        except requests.exceptions.HTTPError as e:
            error_msg = f"Gemini API error: {e}"
            try:
                status = e.response.status_code
                if status in (401, 403):
                    error_msg = "Invalid Gemini API key or insufficient permissions"
                elif status == 429:
                    error_msg = "Gemini rate limit exceeded - wait and try again"
                else:
                    try:
                        error_detail = e.response.json().get('error', {}).get('message', '')
                        if error_detail:
                            error_msg = f"Gemini API error: {error_detail}"
                    except Exception:
                        pass
            except AttributeError:
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
                'error': f'Gemini error: {str(e)}'
            }

    def is_available(self) -> bool:
        """Check if API key is configured"""
        return self.api_key is not None and len(self.api_key) > 0

    @classmethod
    def list_available_models(cls, api_key: str) -> List[str]:
        """
        Query the models list endpoint (GET /v1beta/models) for model names
        that support generateContent, with the 'models/' prefix stripped.

        Endpoint + response shape per https://ai.google.dev/api/models
        (verified 2026-07-14): {"models": [{"name": "models/gemini-...",
        "supportedGenerationMethods": [...]}], "nextPageToken": ...}

        Args:
            api_key: Google Gemini API key

        Returns:
            List of model name strings (e.g. ["gemini-2.5-pro", ...]).
            Returns an empty list and logs a warning on any failure.
        """
        if not api_key:
            unreal.log_warning("[Gemini] Cannot list models: no API key provided")
            return []

        model_names = []
        page_token = None
        try:
            for _ in range(10):  # hard cap on pagination loops
                params = {"pageSize": 100}
                if page_token:
                    params["pageToken"] = page_token

                response = _get_http_session().get(
                    f"{cls.API_BASE}/models",
                    headers={"x-goog-api-key": api_key},
                    params=params,
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()

                for entry in data.get("models", []):
                    if not isinstance(entry, dict):
                        continue
                    methods = entry.get("supportedGenerationMethods", [])
                    if "generateContent" not in methods:
                        continue
                    name = entry.get("name", "")
                    if name.startswith("models/"):
                        name = name[len("models/"):]
                    if name:
                        model_names.append(name)

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            unreal.log(f"[Gemini] Models API returned {len(model_names)} generateContent models")
            return model_names

        except Exception as e:
            unreal.log_warning(f"[Gemini] Failed to list models from Google API: {e}")
            return []

    def get_cost_estimate(self, num_images: int, prompt_length: int = 500) -> float:
        """Estimate cost for analysis"""
        image_tokens = num_images * self.avg_tokens_per_image
        prompt_tokens = prompt_length / 4  # ~4 chars per token
        output_tokens = 1000  # Assume 1000 token response

        total_input = image_tokens + prompt_tokens

        cost = (total_input / 1_000_000 * self.cost_per_1m_input_tokens +
               output_tokens / 1_000_000 * self.cost_per_1m_output_tokens)

        return cost

    def get_provider_info(self) -> Dict:
        """Get Gemini provider information"""
        pricing = self._pricing_for(self.model)
        return {
            'name': 'Gemini (Google)',
            'type': 'gemini',
            'cost_per_image': self.cost_per_1m_input_tokens * self.avg_tokens_per_image / 1_000_000,
            'speed': 'Fast (2-6s per analysis)',
            'accuracy': 'Excellent (85-90%)',
            'max_images': self.max_images,
            'requires_api_key': True,
            'is_local': False,
            'model': self.model,
            'api_key_configured': self.is_available(),
            'supports_json_mode': True,
            'supports_structured_outputs': True,
            'pricing_verified': bool(pricing.get('verified')),
            'thought_tokens_total': self.total_thought_tokens,
            'context_window': '1M tokens'
        }

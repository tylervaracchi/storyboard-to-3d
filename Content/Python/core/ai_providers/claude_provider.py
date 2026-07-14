# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Claude Provider - Anthropic API
Best spatial reasoning, excellent accuracy, requires API key
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


class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude - Excellent for spatial reasoning with extended thinking"""

    # Shared Anthropic API constants
    API_VERSION = "2023-06-01"
    MODELS_URL = "https://api.anthropic.com/v1/models"

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-6", use_extended_thinking: bool = True, enable_caching: bool = True, use_structured_outputs: bool = True):
        super().__init__("Claude Sonnet 4.5 (Extended Thinking)")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.use_extended_thinking = use_extended_thinking
        self.enable_caching = enable_caching
        # Structured outputs (output_config json_schema) guarantee schema-valid JSON.
        # Only takes effect when the caller supplies a json_schema kwarg to analyze_images.
        # Older models reject output_config with HTTP 400; we retry once without it.
        self.use_structured_outputs = use_structured_outputs
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.max_images = 20  # Claude can handle up to 20 images (100 via API!)

        # Pricing (as of 2025 - Claude Sonnet 4.5)
        # Extended thinking adds reasoning token costs
        self.cost_per_1m_input_tokens = 3.00
        self.cost_per_1m_output_tokens = 15.00
        self.avg_tokens_per_image = 1600  # Estimated based on research

        # Prompt caching pricing (90% discount on cached content!)
        self.cost_per_1m_cache_write_tokens = 3.75  # Slightly more to write cache
        self.cost_per_1m_cache_read_tokens = 0.30   # 90% discount on reads!

        # Extended thinking settings
        self.thinking_budget_tokens = 10000  # Budget for reasoning (can be adjusted)

        # Cache statistics tracking
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
        self.total_cache_savings = 0.0

    def analyze_images(self, images: List[str], prompt: str, **kwargs) -> Dict:
        """
        Analyze images using Claude

        Args:
            images: List of image paths
            prompt: Analysis prompt
            **kwargs:
                - max_tokens: Max output tokens (default: 1024)
                - temperature: 0-1 (default: 1.0)
                - system: System prompt (optional)
                - enable_caching: Enable prompt caching (default: inherited from instance)
                - json_schema: JSON schema dict for structured outputs (optional).
                  When provided (and use_structured_outputs is on), the API is asked
                  to return schema-valid JSON via output_config json_schema.
                - use_structured_outputs: Override the instance flag (optional)
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
                'error': 'Anthropic API key not configured'
            }

        # Limit images
        if len(images) > self.max_images:
            unreal.log_warning(f"[Claude] Too many images ({len(images)}), using first {self.max_images}")
            images = images[:self.max_images]

        # Get parameters
        max_tokens = kwargs.get('max_tokens', 1024)
        temperature = kwargs.get('temperature', 1.0)
        system_prompt = kwargs.get('system', None)
        enable_caching = kwargs.get('enable_caching', self.enable_caching)
        json_schema = kwargs.get('json_schema', None)
        use_structured_outputs = kwargs.get('use_structured_outputs', self.use_structured_outputs)

        # FIXED: Adaptive timeout based on context (was fixed 60s causing timeouts)
        # Longer timeout for complex analysis with extended thinking + vision
        # Extended thinking with multiple images can take 2-3 minutes
        request_timeout = kwargs.get('timeout', 180 if self.use_extended_thinking else 90)
        unreal.log(f"[Claude] Request timeout: {request_timeout}s (extended thinking: {self.use_extended_thinking})")

        # CRITICAL: When extended thinking is enabled, max_tokens must be GREATER than thinking_budget_tokens
        # Extended thinking uses budget_tokens for reasoning, then max_tokens for the actual response
        # So max_tokens must leave room for output AFTER the thinking budget is consumed
        if self.use_extended_thinking:
            min_required = self.thinking_budget_tokens + 4096  # Budget + reasonable output space
            if max_tokens < min_required:
                max_tokens = min_required
                unreal.log(f"[Claude] Adjusted max_tokens to {max_tokens} (thinking budget {self.thinking_budget_tokens} + 4096 output)")

        try:
            # Convert images to base64
            image_contents = []
            for img_path in images:
                with open(img_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')

                    # Detect image type
                    ext = Path(img_path).suffix.lower()
                    if ext == '.png':
                        media_type = 'image/png'
                    elif ext in ['.jpg', '.jpeg']:
                        media_type = 'image/jpeg'
                    elif ext == '.webp':
                        media_type = 'image/webp'
                    elif ext == '.gif':
                        media_type = 'image/gif'
                    else:
                        media_type = 'image/png'

                    image_contents.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64
                        }
                    })

            unreal.log(f"[Claude] Sending {len(images)} images to Anthropic...")

            # Log caching status
            if enable_caching:
                unreal.log(f"[Claude] Prompt caching ENABLED - 90% cost savings on repeated content")
            else:
                unreal.log(f"[Claude] Prompt caching disabled")

            # Build message content with optional cache control
            # BEST PRACTICE: Cache last 2 images (typically storyboard reference frames)
            # This gives massive savings when iterating on positioning
            message_content = [{"type": "text", "text": prompt}]

            # Add images with cache control on last 2 images if caching enabled
            for i, img_content in enumerate(image_contents):
                # Cache the last 2 images (these are typically reference storyboard frames)
                if enable_caching and i >= len(image_contents) - 2:
                    img_content["cache_control"] = {"type": "ephemeral"}
                message_content.append(img_content)

            # Build request body
            request_body = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{
                    "role": "user",
                    "content": message_content
                }]
            }

            # Add extended thinking for complex spatial reasoning (Sonnet 4+)
            if self.use_extended_thinking:
                request_body["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": self.thinking_budget_tokens
                }
                unreal.log(f"[Claude] Extended thinking enabled (budget: {self.thinking_budget_tokens} tokens)")

            # Add system prompt if provided with optional cache control
            # BEST PRACTICE: Cache system prompt (static shot rules, composition guidelines)
            if system_prompt:
                if enable_caching:
                    # System prompt as array with cache control for caching
                    request_body["system"] = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                else:
                    # Regular string format when caching disabled
                    request_body["system"] = system_prompt

            # Temperature handling: Extended thinking REQUIRES temperature=1.0
            if self.use_extended_thinking:
                # Extended thinking only works with temperature=1.0, so we must NOT set it
                # (Claude API will default to 1.0)
                if temperature != 1.0:
                    unreal.log_warning(f"[Claude] Temperature {temperature} ignored - extended thinking requires 1.0")
            else:
                # Normal mode: use requested temperature
                if temperature != 1.0:
                    request_body["temperature"] = temperature

            # Structured outputs: ask the API to return schema-valid JSON.
            # Supported on Sonnet 4.5+ generation models. Older models reject
            # output_config with HTTP 400; handled with a one-shot retry below.
            structured_output_active = False
            if use_structured_outputs and json_schema:
                request_body["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": json_schema
                    }
                }
                structured_output_active = True
                unreal.log("[Claude] Structured outputs enabled (output_config json_schema)")

            # Call Anthropic API
            # Note: prompt caching is GA - no beta header needed. cache_control
            # blocks below the cacheable minimum are ignored harmlessly.
            headers = {
                "x-api-key": self.api_key,
                "content-type": "application/json",
                "anthropic-version": self.API_VERSION
            }

            response = requests.post(
                self.base_url,
                headers=headers,
                json=request_body,
                timeout=request_timeout
            )

            # Graceful degradation: if the model rejects output_config (older
            # models return HTTP 400 mentioning it), retry once without it and
            # fall back to prompt-based JSON parsing downstream.
            if structured_output_active and response.status_code == 400:
                error_detail = ''
                try:
                    error_detail = response.json().get('error', {}).get('message', '')
                except Exception:
                    error_detail = response.text or ''
                if 'output_config' in error_detail:
                    unreal.log_warning(f"[Claude] Model {self.model} rejected output_config (structured outputs not supported). Retrying once without it.")
                    request_body.pop('output_config', None)
                    response = requests.post(
                        self.base_url,
                        headers=headers,
                        json=request_body,
                        timeout=request_timeout
                    )

            response.raise_for_status()
            result = response.json()

            elapsed = time.time() - start_time

            # Calculate cost (including thinking tokens and cache costs)
            usage = result.get('usage', {})
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)

            # Extended thinking tokens (if present)
            thinking_tokens = 0
            if self.use_extended_thinking and 'thinking' in usage:
                thinking_tokens = usage['thinking'].get('tokens', 0)

            # Prompt caching tokens (if present)
            cache_creation_input_tokens = usage.get('cache_creation_input_tokens', 0)
            cache_read_input_tokens = usage.get('cache_read_input_tokens', 0)

            # Track cache statistics
            if cache_creation_input_tokens > 0:
                self.cache_creation_tokens += cache_creation_input_tokens
                unreal.log(f"[Claude] Cache CREATED: {cache_creation_input_tokens} tokens written to cache")

            if cache_read_input_tokens > 0:
                self.cache_read_tokens += cache_read_input_tokens
                # Calculate savings from cache hit (90% discount)
                cache_savings = cache_read_input_tokens / 1_000_000 * (self.cost_per_1m_input_tokens - self.cost_per_1m_cache_read_tokens)
                self.total_cache_savings += cache_savings
                unreal.log(f"[Claude] Cache HIT: {cache_read_input_tokens} tokens (saved ${cache_savings:.4f})")

            # Calculate actual cost with caching pricing
            # Regular input tokens (not cached)
            regular_input_tokens = input_tokens - cache_read_input_tokens

            # Thinking tokens are charged at input token rate
            total_input_tokens = input_tokens + thinking_tokens

            # Cost calculation with cache pricing
            cost = 0.0
            cost += regular_input_tokens / 1_000_000 * self.cost_per_1m_input_tokens  # Regular input
            cost += cache_creation_input_tokens / 1_000_000 * self.cost_per_1m_cache_write_tokens  # Cache write (slightly more)
            cost += cache_read_input_tokens / 1_000_000 * self.cost_per_1m_cache_read_tokens  # Cache read (90% discount!)
            cost += thinking_tokens / 1_000_000 * self.cost_per_1m_input_tokens  # Thinking at input rate
            cost += output_tokens / 1_000_000 * self.cost_per_1m_output_tokens  # Output tokens

            # Update statistics
            self.call_count += 1
            self.last_cost = cost
            self.total_cost += cost

            unreal.log(f"[Claude] Analysis complete in {elapsed:.1f}s")

            # Enhanced logging with cache information
            token_log = f"[Claude] Tokens: {input_tokens} input"
            if cache_read_input_tokens > 0:
                token_log += f" ({cache_read_input_tokens} cached)"
            if thinking_tokens > 0:
                token_log += f", {thinking_tokens} thinking"
            token_log += f", {output_tokens} output"
            unreal.log(token_log)

            cost_log = f"[Claude] Cost: ${cost:.4f}"
            if cache_read_input_tokens > 0:
                cache_savings = cache_read_input_tokens / 1_000_000 * (self.cost_per_1m_input_tokens - self.cost_per_1m_cache_read_tokens)
                cost_log += f" (saved ${cache_savings:.4f} from cache, total savings: ${self.total_cache_savings:.4f})"
            unreal.log(cost_log)

            # Extract text content (skip thinking blocks if extended thinking is enabled)
            response_text = ""
            content_blocks = result.get('content', [])
            for block in content_blocks:
                # Only extract 'text' type blocks, skip 'thinking' blocks
                if isinstance(block, dict) and block.get('type') == 'text':
                    response_text += block.get('text', '')

            if not response_text:
                # Fallback: try to get first content block text (old behavior)
                if content_blocks and isinstance(content_blocks[0], dict):
                    response_text = content_blocks[0].get('text', '')

            return {
                'response': response_text,
                'confidence': 0.95,  # Claude 4.5 with extended thinking - best spatial reasoning!
                'cost': cost,
                'time': elapsed,
                'success': True,
                'error': '',
                'tokens': {
                    'input': input_tokens,
                    'thinking': thinking_tokens,
                    'output': output_tokens,
                    'total': input_tokens + thinking_tokens + output_tokens,
                    'cache_creation': cache_creation_input_tokens,
                    'cache_read': cache_read_input_tokens
                },
                'cache_savings': self.total_cache_savings
            }

        except requests.exceptions.Timeout:
            return {
                'response': '',
                'confidence': 0.0,
                'cost': 0.0,
                'time': time.time() - start_time,
                'success': False,
                'error': f'Anthropic request timed out after {request_timeout}s'
            }
        except requests.exceptions.HTTPError as e:
            error_msg = f"Anthropic API error: {e}"
            if e.response.status_code == 401:
                error_msg = "Invalid Anthropic API key"
            elif e.response.status_code == 429:
                error_msg = "Anthropic rate limit exceeded - wait and try again"
            elif e.response.status_code == 400:
                try:
                    error_detail = e.response.json().get('error', {}).get('message', '')
                    error_msg = f"Anthropic API error: {error_detail}"
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
                'error': f'Claude error: {str(e)}'
            }

    def is_available(self) -> bool:
        """Check if API key is configured"""
        return self.api_key is not None and len(self.api_key) > 0

    @classmethod
    def list_available_models(cls, api_key: str) -> List[str]:
        """
        Query the Anthropic Models API (GET /v1/models) for available model IDs.

        Args:
            api_key: Anthropic API key to authenticate with

        Returns:
            List of model ID strings (e.g. ["claude-sonnet-4-6", ...]).
            Returns an empty list and logs a warning on any failure.
        """
        if not api_key:
            try:
                unreal.log_warning("[Claude] Cannot list models: no API key provided")
            except AttributeError:
                print("[Claude] Cannot list models: no API key provided")
            return []

        try:
            response = requests.get(
                cls.MODELS_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": cls.API_VERSION
                },
                params={"limit": 100},
                timeout=10
            )
            response.raise_for_status()
            data = response.json().get("data", [])

            model_ids = []
            for entry in data:
                if isinstance(entry, dict) and entry.get("id"):
                    model_ids.append(entry["id"])

            try:
                unreal.log(f"[Claude] Models API returned {len(model_ids)} models")
            except AttributeError:
                print(f"[Claude] Models API returned {len(model_ids)} models")
            return model_ids

        except Exception as e:
            try:
                unreal.log_warning(f"[Claude] Failed to list models from Anthropic API: {e}")
            except AttributeError:
                print(f"[Claude] Failed to list models from Anthropic API: {e}")
            return []

    def get_cost_estimate(self, num_images: int, prompt_length: int = 500) -> float:
        """Estimate cost for analysis"""
        # Estimate tokens
        image_tokens = num_images * self.avg_tokens_per_image
        prompt_tokens = prompt_length / 4  # ~4 chars per token
        output_tokens = 1000  # Assume 1000 token response

        total_input = image_tokens + prompt_tokens

        cost = (total_input / 1_000_000 * self.cost_per_1m_input_tokens +
               output_tokens / 1_000_000 * self.cost_per_1m_output_tokens)

        return cost

    def get_provider_info(self) -> Dict:
        """Get Claude provider information"""
        return {
            'name': 'Claude Sonnet 4.5 (Extended Thinking)' if self.use_extended_thinking else f'Claude {self.model}',
            'type': 'claude',
            'cost_per_image': self.cost_per_1m_input_tokens * self.avg_tokens_per_image / 1_000_000,
            'speed': 'Slower (4-10s with extended thinking)' if self.use_extended_thinking else 'Fast (2-4s per analysis)',
            'accuracy': 'Exceptional (95%+ with extended thinking!)' if self.use_extended_thinking else 'Excellent (90-95%)',
            'max_images': self.max_images,
            'requires_api_key': True,
            'is_local': False,
            'model': self.model,
            'extended_thinking': self.use_extended_thinking,
            'thinking_budget': self.thinking_budget_tokens if self.use_extended_thinking else 0,
            'api_key_configured': self.is_available(),
            'supports_prompt_caching': True,
            'prompt_caching_enabled': self.enable_caching,
            'supports_structured_outputs': True,
            'structured_outputs_enabled': self.use_structured_outputs,
            'cache_savings_total': self.total_cache_savings,
            'cache_read_tokens': self.cache_read_tokens,
            'cache_creation_tokens': self.cache_creation_tokens,
            'supports_batch_api': True,
            'context_window': '200K tokens'
        }

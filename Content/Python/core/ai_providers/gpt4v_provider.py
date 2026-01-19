# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
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


class GPT4VisionProvider(BaseAIProvider):
    """OpenAI GPT-4/GPT-5 Vision Provider (supports both Chat Completions and Responses API)"""

    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        super().__init__("GPT-4 Vision")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
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

        # Structured outputs configuration (GPT-4o/GPT-4-turbo only)
        use_structured_output = kwargs.get('use_structured_output', self.supports_structured_outputs)
        response_schema = kwargs.get('response_schema', None)

        # Only enable structured outputs if model supports it
        if use_structured_output and not self.supports_structured_outputs:
            unreal.log_warning(f"[GPT-4V] Structured outputs not supported for {self.model}, falling back to regular mode")
            use_structured_output = False

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
                    # Use custom schema if provided, otherwise use positioning schema
                    schema = response_schema if response_schema else self.get_positioning_schema()
                    request_json["response_format"] = schema
                    unreal.log(f"[GPT-4V] Using JSON schema: {schema['json_schema']['name']}")

            # Call OpenAI API
            response = requests.post(
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

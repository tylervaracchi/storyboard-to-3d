# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
AI Client Module - Optimized Version
Secure API integration with configuration management
"""

import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Union
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
    print("Warning: Settings manager not available. Using direct file access.")

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not found. AI features will be limited.")
    print("Install with: pip install requests")


class AIClient:
    """
    Optimized AI client with secure API key management
    Supports OpenAI and Anthropic Claude models
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

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize AI client

        Args:
            provider: AI provider name (defaults to config or "OpenAI GPT-4 Vision")
            api_key: API key (defaults to environment variable)
        """
        # Get provider and model from Unreal global settings FIRST
        self.selected_model = None
        if provider is None:
            try:
                #  Use settings_manager if available
                if SETTINGS_MANAGER_AVAILABLE:
                    settings_provider = get_setting('ai_settings.provider', '')
                    active_provider = get_setting('ai_settings.active_provider', settings_provider)

                    # Map settings provider to AIClient provider
                    if 'gpt' in active_provider.lower() or 'openai' in active_provider.lower():
                        self.selected_model = get_setting('ai_settings.openai_model', 'gpt-4o')
                        # Map model to provider name
                        if self.selected_model == 'gpt-5':
                            provider = "OpenAI GPT-5"
                        elif self.selected_model == 'gpt-4o':
                            provider = "OpenAI GPT-4o"
                        else:
                            provider = "OpenAI GPT-4 Vision"
                    elif 'claude' in active_provider.lower():
                        self.selected_model = get_setting('ai_settings.claude_model', 'claude-3-5-sonnet-20241022')
                        provider = "Claude 3.5 Sonnet"

                    if provider:
                        print(f"Loaded provider from settings: {provider} (model: {self.selected_model})")
                else:
                    # Fallback: read JSON directly
                    import unreal
                    from pathlib import Path
                    import json

                    content_dir = Path(unreal.Paths.project_content_dir())
                    global_settings_file = content_dir / "StoryboardTo3D" / "Settings" / "global_settings.json"

                    if global_settings_file.exists():
                        with open(global_settings_file, 'r') as f:
                            global_settings = json.load(f)

                        ai_settings = global_settings.get('ai_settings', {})
                        settings_provider = ai_settings.get('provider', '')

                        # Map settings provider to AIClient provider
                        if 'gpt' in settings_provider.lower() or 'openai' in settings_provider.lower():
                            self.selected_model = ai_settings.get('openai_model', 'gpt-4o')
                            # Map model to provider name
                            if self.selected_model == 'gpt-5':
                                provider = "OpenAI GPT-5"
                            elif self.selected_model == 'gpt-4o':
                                provider = "OpenAI GPT-4o"
                            else:
                                provider = "OpenAI GPT-4 Vision"
                        elif 'claude' in settings_provider.lower():
                            self.selected_model = ai_settings.get('claude_model', 'claude-3-5-sonnet-20241022')
                            provider = "Claude 3.5 Sonnet"

                        if provider:
                            print(f"Loaded provider from settings: {provider} (model: {self.selected_model})")
            except Exception as e:
                print(f"Could not load provider from settings: {e}")

        # Fallback to config or default
        if provider is None and CONFIG_AVAILABLE:
            config = get_config()
            provider = config.get("api.provider", "OpenAI GPT-4 Vision")

        self.provider = provider or "OpenAI GPT-4 Vision"

        # Validate provider
        if self.provider not in self.PROVIDERS:
            print(f"Warning: Unknown provider {self.provider}. Using OpenAI GPT-4 Vision.")
            self.provider = "OpenAI GPT-4 Vision"

        # Get API key securely - PRIORITY ORDER:
        # 1. Explicitly passed api_key parameter
        # 2. Unreal project global settings (ai_settings section) - NEWEST
        # 3. Config manager (.env files)
        # 4. Environment variables

        if api_key:
            self.api_key = api_key
        else:
            #  Try settings_manager FIRST, then fallback to JSON
            self.api_key = None

            if SETTINGS_MANAGER_AVAILABLE:
                # Load from settings manager
                if "gpt" in self.provider.lower() or "openai" in self.provider.lower():
                    # Check multiple possible locations
                    self.api_key = (get_setting('ai_settings.openai_api_key', '') or
                                   get_setting('ai.openai_api_key', '') or
                                   get_setting('ai_settings.api_key', ''))
                elif "claude" in self.provider.lower():
                    self.api_key = (get_setting('ai_settings.claude_api_key', '') or
                                   get_setting('ai.claude_api_key', '') or
                                   get_setting('ai_settings.api_key', ''))

                if self.api_key:
                    print(f"Loaded API key from settings_manager")

            # Fallback: Try Unreal global settings directly
            if not self.api_key:
                try:
                    import unreal
                    from pathlib import Path
                    import json

                    content_dir = Path(unreal.Paths.project_content_dir())
                    global_settings_file = content_dir / "StoryboardTo3D" / "Settings" / "global_settings.json"

                    if global_settings_file.exists():
                        with open(global_settings_file, 'r') as f:
                            global_settings = json.load(f)

                        # Check ai_settings section (NEW settings dialog)
                        if "gpt" in self.provider.lower() or "openai" in self.provider.lower():
                            self.api_key = global_settings.get('ai_settings', {}).get('openai_api_key', '')
                        elif "claude" in self.provider.lower():
                            self.api_key = global_settings.get('ai_settings', {}).get('claude_api_key', '')

                    if self.api_key:
                        print(f"Using API key from Unreal global settings (ai_settings)")
                except Exception as e:
                    print(f"Could not load from global settings: {e}")

            # Fallback to config manager
            if not self.api_key and CONFIG_AVAILABLE:
                self.api_key = get_api_key(self.provider)
                if self.api_key:
                    print(f"Using API key from config manager")

            # Final fallback to environment variable
            if not self.api_key:
                import os
                env_var = self.PROVIDERS[self.provider]["env_var"]
                self.api_key = os.environ.get(env_var, "")
                if self.api_key:
                    print(f"Using API key from environment variable")

        # Get configuration from config manager
        if CONFIG_AVAILABLE:
            config = get_config()
            self.timeout = config.get("api.timeout", 30)
            self.max_retries = config.get("api.max_retries", 3)
            self.max_tokens = config.get("api.max_tokens", 500)
        else:
            self.timeout = 30
            self.max_retries = 3
            self.max_tokens = 500

        # Provider info
        self.provider_info = self.PROVIDERS[self.provider]
        self.endpoint = self.provider_info["endpoint"]
        # Use selected model if available, otherwise use default from provider
        self.model = self.selected_model if self.selected_model else self.provider_info["model"]

        # Request session for connection pooling
        self.session = None
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self._update_headers()

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

    def set_api_key(self, api_key: str):
        """Update API key and refresh headers"""
        self.api_key = api_key

        # Save to config if available
        if CONFIG_AVAILABLE:
            config = get_config()
            config.set_api_key(self.provider, api_key)

        # Update headers
        if self.session:
            self._update_headers()

    def test_connection(self) -> tuple[bool, str]:
        """Test API connection"""
        if not REQUESTS_AVAILABLE:
            return False, "requests module not installed"

        if not self.api_key:
            return False, f"No API key provided. Set {self.provider_info['env_var']} environment variable."

        try:
            # Simple test request
            print(f"[test_connection] Testing with endpoint: {self.endpoint}")
            print(f"[test_connection] Model: {self.model}")
            response = self._make_request("Say 'OK' if you can read this.", max_tokens=50)
            print(f"[test_connection] Response: {response}")
            print(f"[test_connection] Response is None: {response is None}")

            if response is not None:  # Check for None, not truthiness (empty string is valid)
                return True, f" {self.provider} connection successful (response: '{response[:50]}')"
            else:
                return False, f" {self.provider} connection failed (no response)"

        except Exception as e:
            import traceback
            print(f"[test_connection] Exception: {e}")
            print(traceback.format_exc())
            return False, f" Connection error: {str(e)}"

    def analyze_panel(self, image_path: Union[str, Path, bytes],
                     custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a storyboard panel

        Args:
            image_path: Path to image file or image bytes
            custom_prompt: Custom analysis prompt (optional)

        Returns:
            Dictionary with analysis results
        """
        if not REQUESTS_AVAILABLE:
            return self._mock_panel_analysis()

        # Default panel analysis prompt
        if custom_prompt is None:
            custom_prompt = """Analyze this storyboard panel and provide:
            1. Shot type (wide, medium, close-up, extreme close-up)
            2. Number of characters visible
            3. Character positions and actions
            4. Props/objects in the scene
            5. Location/setting description
            6. Time of day
            7. Mood/atmosphere
            8. Camera angle (high, low, eye-level, dutch)
            9. Suggested camera movement (static, pan, dolly, zoom)

            Return as JSON with keys: shot_type, num_characters, characters, props,
            location, time_of_day, mood, camera_angle, camera_movement"""

        try:
            # Encode image
            if isinstance(image_path, bytes):
                image_base64 = base64.b64encode(image_path).decode('utf-8')
            else:
                with open(image_path, 'rb') as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')

            # Make request with retries
            response = self._make_request(custom_prompt, image_base64=image_base64)

            if response:
                # Try to parse as JSON
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    # Return raw text if not JSON
                    return {"raw_response": response}

        except Exception as e:
            print(f"Panel analysis error: {e}")

        return self._mock_panel_analysis()

    def analyze_script(self, script_text: str) -> Dict[str, Any]:
        """
        Analyze a screenplay/script

        Args:
            script_text: Script text to analyze

        Returns:
            Dictionary with script analysis
        """
        if not REQUESTS_AVAILABLE:
            return self._mock_script_analysis()

        prompt = f"""Analyze this screenplay excerpt and extract:
        1. Scene locations (INT/EXT)
        2. Characters mentioned
        3. Props/objects needed
        4. Time of day for each scene
        5. Mood/atmosphere
        6. Key actions/events

        Script:
        {script_text[:2000]}  # Limit to prevent token overflow

        Return as JSON with keys: scenes, characters, props, times, moods, actions"""

        response = self._make_request(prompt)

        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                return {"raw_response": response}

        return self._mock_script_analysis()

    def _make_request(self, prompt: str, image_base64: Optional[str] = None,
                     max_tokens: Optional[int] = None) -> Optional[str]:
        """
        Make API request with retry logic

        Args:
            prompt: Text prompt
            image_base64: Base64 encoded image (optional)
            max_tokens: Max tokens for response

        Returns:
            Response text or None
        """
        if not self.session:
            print("[_make_request] No session")
            return None

        max_tokens = max_tokens or self.max_tokens

        # Build request based on provider
        if "OpenAI" in self.provider:
            payload = self._build_openai_payload(prompt, image_base64, max_tokens)
            print(f"[_make_request] Payload keys: {list(payload.keys())}")
        elif "Claude" in self.provider:
            payload = self._build_claude_payload(prompt, image_base64, max_tokens)
        else:
            print(f"[_make_request] Unknown provider: {self.provider}")
            return None

        #  CRITICAL: Add exponential backoff for retries
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s, 8s (capped at 10s)
                    wait_time = min(2 ** (attempt - 1), 10)
                    print(f"[_make_request] Retry {attempt}/{self.max_retries} after {wait_time}s")
                    time.sleep(wait_time)

                print(f"[_make_request] POST to {self.endpoint}")
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout
                )

                print(f"[_make_request] Status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    print(f"[_make_request] Initial status: {data.get('status')}")

                    # GPT-5: Poll if incomplete
                    if data.get('status') == 'incomplete' and 'id' in data:
                        response_id = data['id']
                        print(f"[_make_request] Response incomplete, polling for result...")

                        # Poll for up to 120 seconds (GPT-5 reasoning models can take time)
                        for poll_attempt in range(60):  # 60 attempts, 2s each = 120s max
                            time.sleep(2)
                            poll_response = self.session.get(
                                f"{self.endpoint}/{response_id}",
                                timeout=self.timeout
                            )

                            if poll_response.status_code == 200:
                                data = poll_response.json()
                                status = data.get('status')
                                print(f"[_make_request] Poll {poll_attempt + 1}: status={status}")

                                if status == 'completed':
                                    print(f"[_make_request] Response completed!")
                                    break
                                elif status == 'failed':
                                    print(f"[_make_request] Response failed: {data.get('error')}")
                                    return None
                            else:
                                print(f"[_make_request] Poll failed: {poll_response.status_code}")

                    result = self._parse_response(data)
                    print(f"[_make_request] Parsed result: {result[:100] if result else None}")
                    return result
                elif response.status_code == 429:
                    #  Rate limited - exponential backoff with jitter
                    import random
                    base_wait = min(2 ** attempt, 30)  # Cap at 30s
                    jitter = random.uniform(0, 1)  # Add jitter to prevent thundering herd
                    wait_time = base_wait + jitter
                    print(f"[_make_request] Rate limited (429). Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue  # Retry
                else:
                    #  Better error logging with request ID for support
                    request_id = response.headers.get('x-request-id', 'unknown')
                    print(f"[_make_request] API error: {response.status_code}")
                    print(f"[_make_request] Request ID: {request_id}")
                    print(f"[_make_request] Error: {response.text[:500]}")

                    # Don't retry 4xx errors (except 429)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        print(f"[_make_request] Client error - not retrying")
                        break

            except requests.exceptions.Timeout:
                print(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                print(f"Request error: {e}")
                import traceback
                print(traceback.format_exc())

        print("[_make_request] All retries failed")
        return None

    def _build_openai_payload(self, prompt: str, image_base64: Optional[str],
                             max_tokens: int) -> Dict[str, Any]:
        """Build OpenAI API payload - GPT-5 uses different format than GPT-4"""
        is_gpt5 = self.model.startswith('gpt-5') or self.model.startswith('o3') or self.model.startswith('o4')

        if is_gpt5:
            # GPT-5 Responses API format
            content = [{"type": "input_text", "text": prompt}]

            if image_base64:
                content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_base64}"  # Simple string, not nested
                })

            #  CRITICAL: Pro models require "high" reasoning effort
            reasoning_effort = "high" if "-pro" in self.model.lower() else "medium"

            payload = {
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
            content = [{"type": "text", "text": prompt}]

            if image_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}",
                        "detail": "high"
                    }
                })

            payload = {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": content
                }],
                "max_tokens": max_tokens,
                "temperature": 0.7
            }

        return payload

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

    def _parse_response(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Parse API response based on provider"""
        try:
            if "output" in response_data:  # GPT-5 Responses API

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

                # Strategy 1: Check for output_text convenience field
                if 'output_text' in response_data:
                    text = response_data['output_text']
                    if text:
                        return text

                # Strategy 2: Parse nested structure
                if isinstance(output, list):
                    for item in output:
                        if isinstance(item, dict):
                            item_type = item.get('type')

                            # Handle message type
                            if item_type == 'message':
                                content = item.get('content', [])
                                if isinstance(content, list):
                                    for content_item in content:
                                        if isinstance(content_item, dict):
                                            # Try both output_text and text types
                                            if content_item.get('type') in ['output_text', 'text']:
                                                text = content_item.get('text', '')
                                                if text:
                                                    return text

                            # Handle direct text in output item
                            elif 'text' in item:
                                text_value = item['text']
                                if isinstance(text_value, str) and text_value:
                                    return text_value
                                elif isinstance(text_value, dict) and 'content' in text_value:
                                    return text_value['content']

                # Strategy 3: Check if output is directly a string
                if isinstance(output, str):
                    return output

                print(f"[_parse_response] WARNING: Could not extract text from GPT-5 response")
                print(f"[_parse_response] Response keys: {list(response_data.keys())}")
                print(f"[_parse_response] Output type: {type(output)}")
                if isinstance(output, list):
                    print(f"[_parse_response] Output length: {len(output)}")
                    for i, item in enumerate(output[:3]):  # Show first 3 items
                        print(f"[_parse_response] Output[{i}]: {item}")
                if 'text' in response_data:
                    print(f"[_parse_response] Text field type: {type(response_data['text'])}")
                    print(f"[_parse_response] Text field value: {response_data['text']}")
                if 'error' in response_data and response_data['error']:
                    print(f"[_parse_response] ERROR in response: {response_data['error']}")
                if 'status' in response_data:
                    print(f"[_parse_response] Status: {response_data['status']}")
                return ''
            elif "choices" in response_data:  # GPT-4 Chat Completions API
                return response_data['choices'][0]['message']['content']
            elif "content" in response_data:  # Claude
                return response_data['content'][0]['text']
            elif "response" in response_data:  # Ollama (LLaVA, InternVL2, etc.)
                return response_data['response']
        except (KeyError, IndexError) as e:
            print(f"Error parsing response: {e}")

        return None

    def _mock_panel_analysis(self) -> Dict[str, Any]:
        """Return mock panel analysis for testing"""
        import random

        return {
            "shot_type": random.choice(["wide", "medium", "close-up"]),
            "num_characters": random.randint(0, 3),
            "characters": [f"Character {i+1}" for i in range(random.randint(0, 3))],
            "props": ["desk", "chair", "window"],
            "location": "Interior - Office",
            "time_of_day": random.choice(["day", "night", "dawn", "dusk"]),
            "mood": random.choice(["neutral", "tense", "calm", "dramatic"]),
            "camera_angle": "eye-level",
            "camera_movement": "static"
        }

    def _mock_script_analysis(self) -> Dict[str, Any]:
        """Return mock script analysis for testing"""
        return {
            "scenes": ["INT. OFFICE - DAY", "EXT. STREET - NIGHT"],
            "characters": ["JOHN", "SARAH", "MIKE"],
            "props": ["desk", "phone", "car", "briefcase"],
            "times": ["day", "night"],
            "moods": ["professional", "mysterious"],
            "actions": ["conversation", "chase scene"]
        }

    def __del__(self):
        """Cleanup session on deletion"""
        if self.session:
            self.session.close()


# Factory function for easy client creation
def create_ai_client(provider: Optional[str] = None) -> AIClient:
    """
    Create an AI client with configuration

    Args:
        provider: Optional provider override

    Returns:
        Configured AIClient instance
    """
    if CONFIG_AVAILABLE:
        config = get_config()
        provider = provider or config.get("api.provider")

    return AIClient(provider=provider)


# Export for backward compatibility
MockAIClient = AIClient  # The main client now includes mock functionality

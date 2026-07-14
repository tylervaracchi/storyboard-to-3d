# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
# AI Provider Factory
from .llava_provider import LLaVAProvider
from .gpt4v_provider import GPT4VisionProvider
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
import unreal

class AIProviderFactory:
    @staticmethod
    def create_provider(provider_type='auto', **kwargs):
        """Create an AI provider instance

        Args:
            provider_type: 'auto', 'llava', 'gpt4v', 'claude', or 'gemini'
            **kwargs: Additional provider configuration

        Returns:
            Provider instance or None
        """
        # Auto-detect best provider
        if provider_type == 'auto':
            unreal.log("[AI] Auto-detecting best available provider...")
            return AIProviderFactory.get_best_available_provider(**kwargs)

        # Create specific provider
        providers = {
            'llava': LLaVAProvider,
            'gpt4v': GPT4VisionProvider,
            'claude': ClaudeProvider,
            'gemini': GeminiProvider
        }

        if provider_type not in providers:
            unreal.log_warning(f"Unknown provider: {provider_type}, falling back to auto-detect")
            return AIProviderFactory.get_best_available_provider(**kwargs)

        return providers[provider_type](**kwargs)

    @staticmethod
    def get_best_available_provider(**config):
        """
        Auto-detect best available provider based on settings
        Priority: 1) User's configured provider, 2) OpenAI, 3) Claude, 4) Gemini, 5) LLaVA
        """
        unreal.log("[AI] Checking configured providers...")

        # Try to load settings
        try:
            from core.settings_manager import get_settings_manager
            settings_mgr = get_settings_manager()
            ai_settings = settings_mgr.global_settings.get('ai_settings', {})

            # Get configured provider name
            provider_name = ai_settings.get('provider', 'Auto')
            unreal.log(f"[AI] User configured provider: {provider_name}")

            # Try user's choice first
            if 'OpenAI' in provider_name or 'GPT' in provider_name:
                api_key = ai_settings.get('openai_api_key', '')
                model = ai_settings.get('openai_model', 'gpt-4o')
                if api_key:
                    unreal.log(f"[AI] Trying OpenAI with model: {model}")
                    gpt4v = GPT4VisionProvider(api_key=api_key, model=model)
                    if gpt4v.is_available():
                        unreal.log(f"[AI]  Selected: OpenAI GPT-4 Vision ({model})")
                        return gpt4v
                    else:
                        unreal.log_warning("[AI] OpenAI configured but API key invalid")

            elif 'Claude' in provider_name or 'Anthropic' in provider_name:
                api_key = ai_settings.get('claude_api_key', '')
                model = ai_settings.get('claude_model', 'claude-sonnet-4-6')
                if api_key:
                    unreal.log(f"[AI] Trying Claude with model: {model}")
                    # Cost toggles (Features tab). scoring_model=None keeps
                    # the provider's built-in default when the toggle is off.
                    use_files_api = bool(settings_mgr.get_setting('cost.use_files_api', False))
                    scoring_model = None
                    if settings_mgr.get_setting('cost.use_scoring_model', False):
                        scoring_model = settings_mgr.get_setting('cost.scoring_model', 'claude-haiku-4-5')
                    claude = ClaudeProvider(api_key=api_key, model=model,
                                            use_files_api=use_files_api,
                                            scoring_model=scoring_model)
                    if claude.is_available():
                        unreal.log(f"[AI]  Selected: Claude ({model})")
                        return claude
                    else:
                        unreal.log_warning("[AI] Claude configured but API key invalid")

            elif 'Gemini' in provider_name or 'Google' in provider_name:
                api_key = ai_settings.get('gemini_api_key', '')
                model = ai_settings.get('gemini_model', 'gemini-2.5-pro')
                if api_key:
                    unreal.log(f"[AI] Trying Gemini with model: {model}")
                    gemini = GeminiProvider(api_key=api_key, model=model)
                    if gemini.is_available():
                        unreal.log(f"[AI]  Selected: Gemini ({model})")
                        return gemini
                    else:
                        unreal.log_warning("[AI] Gemini configured but API key invalid")

            # If user chose "Auto" or their choice failed, try all providers
            unreal.log("[AI] Checking all available providers...")

            # 1. Try OpenAI (best quality)
            openai_key = ai_settings.get('openai_api_key', '')
            if openai_key:
                model = ai_settings.get('openai_model', 'gpt-4o')
                unreal.log(f"[AI] Found OpenAI API key, testing with {model}...")
                gpt4v = GPT4VisionProvider(api_key=openai_key, model=model)
                if gpt4v.is_available():
                    unreal.log(f"[AI]  Auto-selected: OpenAI GPT-4 Vision ({model})")
                    return gpt4v

            # 2. Try Claude (excellent spatial reasoning)
            claude_key = ai_settings.get('claude_api_key', '')
            if claude_key:
                model = ai_settings.get('claude_model', 'claude-sonnet-4-6')
                unreal.log(f"[AI] Found Claude API key, testing with {model}...")
                # Cost toggles (Features tab). scoring_model=None keeps
                # the provider's built-in default when the toggle is off.
                use_files_api = bool(settings_mgr.get_setting('cost.use_files_api', False))
                scoring_model = None
                if settings_mgr.get_setting('cost.use_scoring_model', False):
                    scoring_model = settings_mgr.get_setting('cost.scoring_model', 'claude-haiku-4-5')
                claude = ClaudeProvider(api_key=claude_key, model=model,
                                        use_files_api=use_files_api,
                                        scoring_model=scoring_model)
                if claude.is_available():
                    unreal.log(f"[AI]  Auto-selected: Claude ({model})")
                    return claude

            # 3. Try Gemini (strong multimodal reasoning)
            gemini_key = ai_settings.get('gemini_api_key', '')
            if gemini_key:
                model = ai_settings.get('gemini_model', 'gemini-2.5-pro')
                unreal.log(f"[AI] Found Gemini API key, testing with {model}...")
                gemini = GeminiProvider(api_key=gemini_key, model=model)
                if gemini.is_available():
                    unreal.log(f"[AI]  Auto-selected: Gemini ({model})")
                    return gemini

            # 4. Fall back to LLaVA (local, free)
            llava_url = ai_settings.get('llava_url', 'http://localhost:11434')
            unreal.log(f"[AI] Trying LLaVA at {llava_url}...")
            llava = LLaVAProvider(url=llava_url)
            if llava.is_available():
                unreal.log("[AI]  Auto-selected: LLaVA (local)")
                return llava
            else:
                unreal.log_warning("[AI] LLaVA not available (Ollama not running?)")

        except Exception as e:
            unreal.log_warning(f"[AI] Error loading settings: {e}")
            # Fall back to basic LLaVA check
            llava = LLaVAProvider(url=config.get('ollama_url', 'http://localhost:11434'))
            if llava.is_available():
                unreal.log("[AI] Auto-selected: LLaVA (local)")
                return llava

        unreal.log_error("[AI]  No AI providers available!")
        unreal.log_error("[AI] Configure OpenAI or Claude API key in Settings, or start Ollama for LLaVA")
        return None

    @staticmethod
    def get_available_providers(**config):
        """Get list of all providers with availability status"""
        available = []

        # Try to load settings for API keys
        try:
            from core.settings_manager import get_settings_manager
            settings_mgr = get_settings_manager()
            ai_settings = settings_mgr.global_settings.get('ai_settings', {})
        except:
            ai_settings = {}

        # Check OpenAI GPT-4V
        openai_key = config.get('openai_api_key') or ai_settings.get('openai_api_key', '')
        openai_model = config.get('openai_model') or ai_settings.get('openai_model', 'gpt-4o')
        if openai_key:
            gpt4v = GPT4VisionProvider(api_key=openai_key, model=openai_model)
            if gpt4v.is_available():
                info = gpt4v.get_provider_info()
                info['available'] = True
                available.append(info)
            else:
                available.append({
                    'name': 'GPT-4 Vision (OpenAI)', 'type': 'gpt4v',
                    'available': False,
                    'error': 'API key configured but invalid'
                })
        else:
            available.append({
                'name': 'GPT-4 Vision (OpenAI)', 'type': 'gpt4v',
                'available': False,
                'error': 'No API key configured'
            })

        # Check Claude
        claude_key = config.get('claude_api_key') or ai_settings.get('claude_api_key', '')
        claude_model = config.get('claude_model') or ai_settings.get('claude_model', 'claude-sonnet-4-6')
        if claude_key:
            claude = ClaudeProvider(api_key=claude_key, model=claude_model)
            if claude.is_available():
                info = claude.get_provider_info()
                info['available'] = True
                available.append(info)
            else:
                available.append({
                    'name': 'Claude 3.5 Sonnet (Anthropic)', 'type': 'claude',
                    'available': False,
                    'error': 'API key configured but invalid'
                })
        else:
            available.append({
                'name': 'Claude 3.5 Sonnet (Anthropic)', 'type': 'claude',
                'available': False,
                'error': 'No API key configured'
            })

        # Check Gemini
        gemini_key = config.get('gemini_api_key') or ai_settings.get('gemini_api_key', '')
        gemini_model = config.get('gemini_model') or ai_settings.get('gemini_model', 'gemini-2.5-pro')
        if gemini_key:
            gemini = GeminiProvider(api_key=gemini_key, model=gemini_model)
            if gemini.is_available():
                info = gemini.get_provider_info()
                info['available'] = True
                available.append(info)
            else:
                available.append({
                    'name': 'Gemini (Google)', 'type': 'gemini',
                    'available': False,
                    'error': 'API key configured but invalid'
                })
        else:
            available.append({
                'name': 'Gemini (Google)', 'type': 'gemini',
                'available': False,
                'error': 'No API key configured'
            })

        # Check LLaVA
        llava_url = config.get('ollama_url') or ai_settings.get('llava_url', 'http://localhost:11434')
        llava = LLaVAProvider(url=llava_url)
        if llava.is_available():
            info = llava.get_provider_info()
            info['available'] = True
            available.append(info)
        else:
            available.append({
                'name': 'LLaVA (Local)', 'type': 'llava',
                'available': False,
                'error': 'Ollama not running or llava model not installed'
            })

        return available

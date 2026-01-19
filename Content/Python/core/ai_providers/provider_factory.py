# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
# AI Provider Factory
from .llava_provider import LLaVAProvider
from .gpt4v_provider import GPT4VisionProvider
from .claude_provider import ClaudeProvider
import unreal

class AIProviderFactory:
    @staticmethod
    def create_provider(provider_type='auto', **kwargs):
        """Create an AI provider instance

        Args:
            provider_type: 'auto', 'llava', 'gpt4v', or 'claude'
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
            'claude': ClaudeProvider
        }

        if provider_type not in providers:
            unreal.log_warning(f"Unknown provider: {provider_type}, falling back to auto-detect")
            return AIProviderFactory.get_best_available_provider(**kwargs)

        return providers[provider_type](**kwargs)

    @staticmethod
    def get_best_available_provider(**config):
        """
        Auto-detect best available provider based on settings
        Priority: 1) User's configured provider, 2) OpenAI, 3) Claude, 4) LLaVA
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
                model = ai_settings.get('claude_model', 'claude-3-5-sonnet-20241022')
                if api_key:
                    unreal.log(f"[AI] Trying Claude with model: {model}")
                    claude = ClaudeProvider(api_key=api_key, model=model)
                    if claude.is_available():
                        unreal.log(f"[AI]  Selected: Claude ({model})")
                        return claude
                    else:
                        unreal.log_warning("[AI] Claude configured but API key invalid")

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
                model = ai_settings.get('claude_model', 'claude-3-5-sonnet-20241022')
                unreal.log(f"[AI] Found Claude API key, testing with {model}...")
                claude = ClaudeProvider(api_key=claude_key, model=model)
                if claude.is_available():
                    unreal.log(f"[AI]  Auto-selected: Claude ({model})")
                    return claude

            # 3. Fall back to LLaVA (local, free)
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
        claude_model = config.get('claude_model') or ai_settings.get('claude_model', 'claude-3-5-sonnet-20241022')
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

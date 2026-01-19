# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
AI Providers Package
Multi-provider AI vision system for Unreal Engine

Supported Providers:
- LLaVA (Local via Ollama) - Free, private
- GPT-4 Vision (OpenAI) - Fast, accurate, paid
- Claude 3.5 Sonnet (Anthropic) - Best spatial reasoning, paid
"""

from .base_provider import BaseAIProvider
from .llava_provider import LLaVAProvider
from .gpt4v_provider import GPT4VisionProvider
from .claude_provider import ClaudeProvider
from .provider_factory import AIProviderFactory

__all__ = [
    'BaseAIProvider',
    'LLaVAProvider',
    'GPT4VisionProvider',
    'ClaudeProvider',
    'AIProviderFactory'
]

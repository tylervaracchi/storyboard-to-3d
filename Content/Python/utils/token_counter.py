# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Token Counter Utility for OpenAI Models
Accurate token counting before API calls to prevent context window errors

Based on production best practices from October 2025
"""

from typing import List, Dict, Any, Optional

# Try to import tiktoken (official OpenAI tokenizer)
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("tiktoken not available. Install with: pip install tiktoken")
    print("Token counting will use rough estimation instead.")


class TokenCounter:
    """
    Accurate token counting for OpenAI models
    Prevents context window overflow and helps estimate costs
    """

    # Model context windows (as of October 2025)
    CONTEXT_WINDOWS = {
        # GPT-5 family (400K input)
        "gpt-5": {"input": 400_000, "output": 128_000},
        "gpt-5-mini": {"input": 400_000, "output": 128_000},
        "gpt-5-nano": {"input": 400_000, "output": 128_000},
        "gpt-5-pro": {"input": 400_000, "output": 128_000},

        # GPT-4.1 family (1M tokens)
        "gpt-4.1": {"input": 1_000_000, "output": 1_000_000},
        "gpt-4.1-mini": {"input": 1_000_000, "output": 1_000_000},
        "gpt-4.1-nano": {"input": 1_000_000, "output": 1_000_000},

        # GPT-4o family (128K)
        "gpt-4o": {"input": 128_000, "output": 16_384},
        "gpt-4o-mini": {"input": 128_000, "output": 16_384},

        # GPT-4 family (8K-32K)
        "gpt-4": {"input": 8_192, "output": 8_192},
        "gpt-4-turbo": {"input": 128_000, "output": 4_096},
        "gpt-4-32k": {"input": 32_768, "output": 32_768},

        # O-series (reasoning models)
        "o3": {"input": 200_000, "output": 100_000},
        "o3-mini": {"input": 200_000, "output": 100_000},
        "o4-mini": {"input": 200_000, "output": 100_000},
    }

    def __init__(self, model: str = "gpt-4o"):
        """
        Initialize token counter

        Args:
            model: Model name to count tokens for
        """
        self.model = model
        self.encoding = None

        if TIKTOKEN_AVAILABLE:
            try:
                # Get encoding for model
                self.encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base for unknown models
                print(f"Model {model} not recognized by tiktoken, using cl100k_base encoding")
                self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        if TIKTOKEN_AVAILABLE and self.encoding:
            # Accurate token counting
            return len(self.encoding.encode(text))
        else:
            # Rough estimation: ~4 characters per token
            return len(text) // 4

    def count_message_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in message array (for Chat Completions API)

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Total token count including formatting overhead
        """
        if not TIKTOKEN_AVAILABLE or not self.encoding:
            # Rough estimation
            total_chars = sum(len(str(m.get('content', ''))) for m in messages)
            return (total_chars // 4) + (len(messages) * 4)  # +4 tokens per message overhead

        # Accurate counting with formatting overhead
        # Based on OpenAI's token counting guide
        tokens = 0

        for message in messages:
            tokens += 4  # Every message has formatting tokens

            role = message.get('role', '')
            content = message.get('content', '')

            tokens += len(self.encoding.encode(role))

            if isinstance(content, str):
                tokens += len(self.encoding.encode(content))
            elif isinstance(content, list):
                # Handle multimodal content
                for item in content:
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            tokens += len(self.encoding.encode(item.get('text', '')))
                        elif item.get('type') == 'image_url':
                            # Images are counted differently (see estimate_image_tokens)
                            tokens += 85  # Low detail estimate

        tokens += 2  # Every reply is primed with assistant role

        return tokens

    def estimate_image_tokens(self, image_detail: str = "high") -> int:
        """
        Estimate tokens for an image

        Args:
            image_detail: "high" or "low"

        Returns:
            Estimated token count
        """
        # Based on OpenAI documentation
        if image_detail == "high":
            return 300  # High detail ~300 tokens
        else:
            return 85   # Low detail ~85 tokens

    def get_context_window(self, model: Optional[str] = None) -> Dict[str, int]:
        """
        Get context window limits for model

        Args:
            model: Model name (uses self.model if not provided)

        Returns:
            Dict with 'input' and 'output' token limits
        """
        model = model or self.model

        # Try exact match
        if model in self.CONTEXT_WINDOWS:
            return self.CONTEXT_WINDOWS[model]

        # Try prefix match
        for key, limits in self.CONTEXT_WINDOWS.items():
            if model.startswith(key):
                return limits

        # Default fallback
        print(f"Unknown model {model}, using conservative 8K limit")
        return {"input": 8_192, "output": 4_096}

    def validate_request(self, text: str, max_output_tokens: int = 1000) -> Dict[str, Any]:
        """
        Validate if request fits within context window

        Args:
            text: Input text
            max_output_tokens: Requested output tokens

        Returns:
            Dict with validation result
        """
        input_tokens = self.count_tokens(text)
        limits = self.get_context_window()

        total_needed = input_tokens + max_output_tokens
        max_total = limits['input']

        is_valid = total_needed <= max_total

        return {
            "valid": is_valid,
            "input_tokens": input_tokens,
            "output_tokens_requested": max_output_tokens,
            "total_tokens": total_needed,
            "context_limit": max_total,
            "tokens_remaining": max_total - total_needed if is_valid else 0,
            "recommendation": self._get_recommendation(input_tokens, max_output_tokens, limits)
        }

    def _get_recommendation(self, input_tokens: int, output_tokens: int,
                           limits: Dict[str, int]) -> str:
        """Generate recommendation for token usage"""
        total = input_tokens + output_tokens
        limit = limits['input']

        usage_pct = (total / limit) * 100

        if usage_pct > 100:
            return f" EXCEEDS LIMIT by {total - limit:,} tokens. Reduce input or output."
        elif usage_pct > 90:
            return f" Using {usage_pct:.1f}% of context. Consider reducing input."
        elif usage_pct > 75:
            return f" Using {usage_pct:.1f}% of context. Room for {limit - total:,} more tokens."
        else:
            return f" Using {usage_pct:.1f}% of context. {limit - total:,} tokens available."

    def truncate_to_limit(self, text: str, max_tokens: int,
                         reserve_output: int = 1000) -> str:
        """
        Truncate text to fit within token limit

        Args:
            text: Text to truncate
            max_tokens: Maximum input tokens allowed
            reserve_output: Tokens to reserve for output

        Returns:
            Truncated text
        """
        available_tokens = max_tokens - reserve_output
        current_tokens = self.count_tokens(text)

        if current_tokens <= available_tokens:
            return text

        if not TIKTOKEN_AVAILABLE or not self.encoding:
            # Rough truncation by characters
            char_limit = available_tokens * 4
            return text[:char_limit]

        # Accurate truncation by tokens
        tokens = self.encoding.encode(text)
        truncated_tokens = tokens[:available_tokens]
        return self.encoding.decode(truncated_tokens)


# Convenience functions
def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Quick token count"""
    counter = TokenCounter(model)
    return counter.count_tokens(text)


def validate_prompt(text: str, model: str = "gpt-4o",
                   max_output: int = 1000) -> bool:
    """Quick validation"""
    counter = TokenCounter(model)
    result = counter.validate_request(text, max_output)
    return result['valid']


# Self-test
if __name__ == "__main__":
    print("Testing TokenCounter...")

    counter = TokenCounter("gpt-4o")

    test_text = "Hello, world! This is a test of token counting."
    tokens = counter.count_tokens(test_text)
    print(f"Text: '{test_text}'")
    print(f"Tokens: {tokens}")

    # Test validation
    long_text = "Test " * 1000
    validation = counter.validate_request(long_text, max_output_tokens=500)
    print(f"\n Validation for {validation['input_tokens']} input tokens:")
    print(f"{validation['recommendation']}")

    # Test context windows
    for model in ["gpt-5", "gpt-4.1", "gpt-4o", "o3"]:
        limits = TokenCounter(model).get_context_window()
        print(f"\n {model}: {limits['input']:,} input / {limits['output']:,} output tokens")

    if not TIKTOKEN_AVAILABLE:
        print("\n Note: tiktoken not installed. Using estimation.")
        print("Install with: pip install tiktoken")

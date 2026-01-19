# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ROBUST JSON EXTRACTOR
Enterprise-grade JSON parsing for LLM outputs (LLaVA, GPT, Claude)
Handles malformed JSON, control characters, markdown wrapping, extra data
"""

import json
import re
from typing import Any, Dict, List, Union

# Try to import json-repair library (install: pip install json-repair)
try:
    from json_repair import repair_json
    JSON_REPAIR_AVAILABLE = True
except ImportError:
    JSON_REPAIR_AVAILABLE = False
    print("json-repair not available. Install: pip install json-repair")
    print("Some JSON parsing edge cases may fail.")


class RobustJSONExtractor:
    """
    Multi-strategy JSON parser for LLM outputs

    Handles:
    - Malformed JSON (trailing commas, unquoted keys)
    - Control characters (0x00-0x1F)
    - Markdown code blocks
    - Extra data after JSON
    - Multiple JSON objects
    """

    @staticmethod
    def extract_and_parse(llm_response: str) -> Union[Dict, List]:
        """
        Extract and parse JSON from LLM response using multiple strategies

        Args:
            llm_response: Raw response from LLM (may contain markdown, extra text, etc.)

        Returns:
            Parsed JSON as dict or list

        Raises:
            ValueError: If no valid JSON found after all strategies
        """

        if not llm_response or not isinstance(llm_response, str):
            raise ValueError("Input must be a non-empty string")

        # Strategy 1: Direct parse (fastest path)
        try:
            return json.loads(llm_response)
        except json.JSONDecodeError:
            # Try repair immediately on direct input
            if JSON_REPAIR_AVAILABLE:
                try:
                    return repair_json(llm_response, return_objects=True)
                except:
                    pass

        # Strategy 2: Extract from markdown code blocks
        result = RobustJSONExtractor._try_markdown_extraction(llm_response)
        if result is not None:
            return result

        # Strategy 3: Find JSON boundaries and extract
        result = RobustJSONExtractor._try_boundary_extraction(llm_response)
        if result is not None:
            return result

        # Strategy 4: Clean control characters and repair
        result = RobustJSONExtractor._try_clean_and_repair(llm_response)
        if result is not None:
            return result

        # All strategies failed
        raise ValueError(
            f"Failed to extract valid JSON from response. "
            f"Response preview: {llm_response[:200]}..."
        )

    @staticmethod
    def _try_markdown_extraction(text: str) -> Union[Dict, List, None]:
        """Extract JSON from markdown code blocks"""

        markdown_patterns = [
            r'```json\s*\n(.*?)\n```',      # ```json ... ```
            r'```\s*\n(\{.*?\})\n```',      # ``` {...} ```
            r'```\s*\n(\[.*?\])\n```',      # ``` [...] ```
        ]

        for pattern in markdown_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1)

                # Try direct parse
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

                # Try repair if available
                if JSON_REPAIR_AVAILABLE:
                    try:
                        return repair_json(json_str, return_objects=True)
                    except:
                        pass

        return None

    @staticmethod
    def _try_boundary_extraction(text: str) -> Union[Dict, List, None]:
        """Find JSON object/array boundaries and extract"""

        # Find start
        start_idx = text.find('{')
        start_char = '{'
        end_char = '}'

        if start_idx == -1:
            start_idx = text.find('[')
            start_char = '['
            end_char = ']'

        if start_idx == -1:
            return None

        # Find matching end bracket
        end_idx = RobustJSONExtractor._find_matching_bracket(
            text, start_idx, start_char, end_char
        )

        if end_idx == -1:
            # Try finding last occurrence
            end_idx = text.rfind(end_char)

        if end_idx > start_idx:
            json_str = text[start_idx:end_idx+1]

            # Try direct parse
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # Try repair if available
            if JSON_REPAIR_AVAILABLE:
                try:
                    return repair_json(json_str, return_objects=True)
                except:
                    pass

        return None

    @staticmethod
    def _try_clean_and_repair(text: str) -> Union[Dict, List, None]:
        """Clean control characters and attempt repair"""

        # Remove control characters (except tab, newline, carriage return)
        cleaned = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)

        # Try direct parse on cleaned text
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try repair if available
        if JSON_REPAIR_AVAILABLE:
            try:
                return repair_json(cleaned, return_objects=True)
            except:
                pass

        # Last resort: Try to extract and repair just the JSON part
        result = RobustJSONExtractor._try_boundary_extraction(cleaned)
        if result is not None:
            return result

        return None

    @staticmethod
    def _find_matching_bracket(text: str, start_idx: int,
                               open_char: str, close_char: str) -> int:
        """Find matching closing bracket"""

        count = 1
        i = start_idx + 1

        while i < len(text) and count > 0:
            if text[i] == open_char:
                count += 1
            elif text[i] == close_char:
                count -= 1
            i += 1

        return i - 1 if count == 0 else -1


def sanitize_control_chars(text: str) -> str:
    """
    Remove control characters that violate JSON spec

    Keeps: tab (0x09), newline (0x0A), carriage return (0x0D)
    Removes: 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F-0x9F
    """
    return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)


# Convenience function for drop-in replacement
def parse_llm_json(llm_response: str) -> Union[Dict, List]:
    """
    Drop-in replacement for json.loads() when parsing LLM outputs

    Usage:
        # OLD: data = json.loads(llava_output)
        # NEW: data = parse_llm_json(llava_output)
    """
    return RobustJSONExtractor.extract_and_parse(llm_response)


# Self-test
if __name__ == "__main__":
    print("Testing RobustJSONExtractor...")

    test_cases = [
        ("Normal JSON", '{"key": "value"}', {"key": "value"}),
        ("Trailing comma", '{"key": "value",}', {"key": "value"}),
        ("Markdown wrapped", '```json\n{"key": "value"}\n```', {"key": "value"}),
        ("Control chars", '{"text": "line1\x0aline2"}', {"text": "line1line2"}),
        ("Extra data", '{"key": "value"}\nExtra text here', {"key": "value"}),
        ("Unquoted keys", '{key: "value"}', {"key": "value"}),
        ("Array", '[1, 2, 3]', [1, 2, 3]),
    ]

    passed = 0
    failed = 0

    for name, input_str, expected in test_cases:
        try:
            result = parse_llm_json(input_str)
            if result == expected:
                print(f"{name}")
                passed += 1
            else:
                print(f"{name}: Got {result}, expected {expected}")
                failed += 1
        except Exception as e:
            print(f"{name}: {e}")
            failed += 1

    print(f"\n Results: {passed} passed, {failed} failed")

    if not JSON_REPAIR_AVAILABLE:
        print("\n Note: json-repair not installed. Some tests may fail.")
        print("Install with: pip install json-repair")

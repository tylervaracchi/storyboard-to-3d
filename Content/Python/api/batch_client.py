# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Claude Batch Client - Anthropic Message Batches API
Submits Messages API requests as an asynchronous batch at a 50 percent
token discount. Intended for non-latency-sensitive work such as bulk
storyboard panel analysis.

Pure requests-based (no Anthropic SDK dependency) and safe to import
outside Unreal Engine (logging falls back to print).

API shape:
    POST https://api.anthropic.com/v1/messages/batches
        {"requests": [{"custom_id": ..., "params": {<messages body>}}]}
    GET  https://api.anthropic.com/v1/messages/batches/{id}
        poll until processing_status == "ended"
    GET  results_url -> JSONL, one line per custom_id (arbitrary order)
"""

import json
import os
import time
from typing import Dict, List

# Alias so the submit() parameter can be named 'requests' (matching the
# public signature) without shadowing the HTTP library inside the methods.
import requests as _http

try:
    import unreal

    def _log(message):
        unreal.log(message)

    def _log_warning(message):
        unreal.log_warning(message)

except ImportError:
    def _log(message):
        print(message)

    def _log_warning(message):
        print(f"[WARNING] {message}")


class ClaudeBatchClient:
    """Minimal client for the Anthropic Message Batches API."""

    API_VERSION = "2023-06-01"
    BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"

    def __init__(self, api_key: str = None, request_timeout: int = 120):
        """
        Args:
            api_key: Anthropic API key. When omitted, falls back to the
                ANTHROPIC_API_KEY env var (optional override), then the
                Settings dialog key ('ai_settings.claude_api_key').
            request_timeout: Per-HTTP-request timeout in seconds
        """
        self.api_key = (api_key or os.getenv("ANTHROPIC_API_KEY")
                        or self._settings_api_key())
        self.request_timeout = request_timeout

    @staticmethod
    def _settings_api_key():
        """Settings dialog key ('ai_settings.claude_api_key'), guarded so
        headless (non-editor) use returns None instead of raising."""
        try:
            from core.settings_manager import get_settings_manager
            ai_settings = get_settings_manager().global_settings.get(
                'ai_settings', {})
            return ai_settings.get('claude_api_key', '') or None
        except Exception:
            return None

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json"
        }

    def is_available(self) -> bool:
        """True when an API key is configured."""
        return bool(self.api_key)

    def submit(self, requests: List[Dict]) -> str:
        """
        Submit a batch of Messages API requests.

        Args:
            requests: List of dicts, each with:
                - custom_id: Unique string to match results back to inputs
                - params: A normal Messages API request body
                  (model, max_tokens, messages, ...)

        Returns:
            The batch id string.

        Raises:
            ValueError if no API key is configured or the list is empty.
            requests.HTTPError if the API rejects the batch.
        """
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")
        if not requests:
            raise ValueError("No batch requests provided")

        response = _http.post(
            self.BATCHES_URL,
            headers=self._headers(),
            json={"requests": requests},
            timeout=self.request_timeout
        )
        response.raise_for_status()
        batch_id = response.json().get("id", "")
        _log(f"[ClaudeBatch] Submitted batch {batch_id} ({len(requests)} requests, 50% token discount)")
        return batch_id

    def status(self, batch_id: str) -> Dict:
        """
        Fetch the current batch object.

        Returns the full batch dict; key fields are processing_status
        ('in_progress' or 'ended'), request_counts, and results_url.
        """
        response = _http.get(
            f"{self.BATCHES_URL}/{batch_id}",
            headers=self._headers(),
            timeout=self.request_timeout
        )
        response.raise_for_status()
        return response.json()

    def wait(self, batch_id: str, poll_seconds: int = 30, timeout_minutes: int = 120) -> Dict:
        """
        Poll until the batch ends or the timeout elapses.

        Args:
            batch_id: Batch id returned by submit()
            poll_seconds: Delay between status polls
            timeout_minutes: Wall-clock budget before giving up

        Returns:
            The final batch dict (processing_status == 'ended').

        Raises:
            TimeoutError when timeout_minutes elapses first.
        """
        deadline = time.time() + timeout_minutes * 60
        while True:
            batch = self.status(batch_id)
            processing_status = batch.get("processing_status", "")
            counts = batch.get("request_counts", {}) or {}
            _log(
                f"[ClaudeBatch] {batch_id}: {processing_status} "
                f"(processing: {counts.get('processing', 0)}, "
                f"succeeded: {counts.get('succeeded', 0)}, "
                f"errored: {counts.get('errored', 0)})"
            )
            if processing_status == "ended":
                return batch
            if time.time() >= deadline:
                raise TimeoutError(f"Batch {batch_id} did not end within {timeout_minutes} minutes")
            time.sleep(poll_seconds)

    def results(self, batch_id: str) -> Dict[str, Dict]:
        """
        Download and index batch results.

        Results arrive as JSONL in arbitrary order, so they are keyed by
        custom_id here; never rely on position.

        Returns:
            Dict mapping custom_id -> result dict. Each result dict carries a
            'type' ('succeeded', 'errored', 'canceled', 'expired'); on success
            the full Messages API response is under 'message'.

        Raises:
            RuntimeError if the batch has no results_url yet (still running).
        """
        batch = self.status(batch_id)
        results_url = batch.get("results_url")
        if not results_url:
            raise RuntimeError(
                f"Batch {batch_id} has no results_url yet "
                f"(processing_status: {batch.get('processing_status')})"
            )

        response = _http.get(
            results_url,
            headers=self._headers(),
            timeout=self.request_timeout,
            stream=True
        )
        response.raise_for_status()

        results = {}
        for line in response.iter_lines():
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError as e:
                _log_warning(f"[ClaudeBatch] Skipping unparseable results line: {e}")
                continue
            custom_id = entry.get("custom_id")
            if custom_id:
                results[custom_id] = entry.get("result", {}) or {}

        _log(f"[ClaudeBatch] Retrieved {len(results)} results for batch {batch_id}")
        return results

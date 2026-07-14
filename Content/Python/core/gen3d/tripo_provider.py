# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tripo3D Text-to-Model Provider

Coded against the Tripo3D platform docs at
https://platform.tripo3d.ai/docs/generation and https://docs.tripo3d.ai/
(checked 2026-07-14). NOTE: the official docs pages are JavaScript
rendered and could not be fully machine-read at implementation time; the
endpoint, auth, request body, response envelope, and 'success' status
below were confirmed via secondary sources, while the full status list
and the draft-tier flags are best-known shapes marked VERIFY-BEFORE-USE.

  Create task:  POST https://api.tripo3d.ai/v2/openapi/task
  Poll task:    GET  https://api.tripo3d.ai/v2/openapi/task/{task_id}
  Auth header:  Authorization: Bearer <TRIPO_API_KEY>   (keys begin 'tsk_')

  Create body:
    {"type": "text_to_model", "prompt": "..."}
    Prompt max length is 1024 characters.
    VERIFY-BEFORE-USE: for the cheapest draft tier this module also sends
    {"texture": false, "pbr": false} to skip texturing. If the live API
    rejects these fields, remove them (the task then produces a textured
    model at slightly higher cost).

  Create response: {"code": 0, "data": {"task_id": "..."}}

  Poll response:
    {"code": 0,
     "data": {"task_id": "...",
              "status": "...",
              "output": {"model": <url>, "pbr_model": <url>,
                         "base_model": <url>}}}
    'success' is the confirmed terminal-success status. The in-progress
    statuses 'queued' and 'running' and the failure statuses 'failed',
    'cancelled', 'banned', 'expired', 'unknown' are best-known values;
    VERIFY-BEFORE-USE. Any unrecognized status keeps polling until the
    timeout, so a doc drift here degrades to a timeout, never a crash.

  Model download URLs live under data.output; Tripo delivers GLB files.
  Preference order here: pbr_model, model, base_model.

Quality tiers via the 'gen3d.quality' setting:
  'draft' (default, also accepts 'preview'/'fast'/'low'):
      untextured model, cheapest and fastest (VERIFY-BEFORE-USE flags).
  anything else ('standard', 'textured', ...):
      omit the flags; Tripo's defaults produce a textured model.

API key: TRIPO_API_KEY environment variable, then the plugin
config_manager pattern (see Gen3DProvider._resolve_api_key).
"""

from typing import Any, Dict, Optional, Tuple

from .base_provider import Gen3DProvider, Gen3DError, _log_warning

try:
    import unreal  # noqa: F401  (parity guard; not directly used here)
except ImportError:
    unreal = None


TRIPO_API_BASE = "https://api.tripo3d.ai/v2/openapi/task"
TRIPO_PROMPT_MAX_CHARS = 1024
TRIPO_DRAFT_QUALITIES = ('draft', 'preview', 'fast', 'low')
TRIPO_OUTPUT_PREFERENCE = ('pbr_model', 'model', 'base_model')


class TripoProvider(Gen3DProvider):
    """Tripo3D text-to-model provider (https://platform.tripo3d.ai/docs)."""

    name = 'tripo'
    pricing_note = ("Tripo3D text_to_model in draft (untextured) mode is the "
                    "cheapest tier; set gen3d.quality to 'standard' for a "
                    "textured model. Pricing: https://platform.tripo3d.ai")

    DEFAULT_QUALITY = 'draft'

    def get_api_key(self):
        # type: () -> Optional[str]
        """TRIPO_API_KEY env var, then plugin config ('api.keys.tripo3d')."""
        return self._resolve_api_key('TRIPO_API_KEY', 'tripo3d')

    # ------------------------------------------------------------------
    # Gen3DProvider hooks
    # ------------------------------------------------------------------

    def _headers(self):
        # type: () -> Dict[str, str]
        return {
            'Authorization': 'Bearer {}'.format(self.get_api_key()),
            'Content-Type': 'application/json'
        }

    def _create_task(self, prompt):
        # type: (str) -> str
        """Create a text_to_model task; returns the task id."""
        body = {
            'type': 'text_to_model',
            'prompt': prompt[:TRIPO_PROMPT_MAX_CHARS]
        }

        if self.get_quality() in TRIPO_DRAFT_QUALITIES:
            # VERIFY-BEFORE-USE: skip texturing for the cheapest/fastest
            # tier. Remove these two fields if the live API rejects them.
            body['texture'] = False
            body['pbr'] = False

        data = self._request_json(
            'POST', TRIPO_API_BASE, headers=self._headers(), json_body=body)
        payload = self._unwrap(data)

        task_id = payload.get('task_id')
        if not task_id:
            raise Gen3DError(
                "Tripo create-task response had no task_id: {}".format(
                    str(data)[:200]))
        return str(task_id)

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        data = self._request_json(
            'GET', '{}/{}'.format(TRIPO_API_BASE, task_id),
            headers=self._headers())
        return self._unwrap(data)

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map Tripo status values to the base provider's states.

        'success' confirmed; other values best-known (VERIFY-BEFORE-USE,
        see module docstring). Unknown statuses keep polling until the
        timeout rather than aborting.
        """
        status = str(task_data.get('status', '')).strip().lower()

        if status == 'success':
            return 'succeeded', None
        if status in ('failed', 'cancelled', 'canceled', 'banned',
                      'expired', 'unknown'):
            return 'failed', 'status {}'.format(status)
        if status in ('queued', 'waiting', 'pending'):
            return 'pending', None
        if status in ('running', 'processing', 'generating'):
            return 'running', None

        _log_warning("[Gen3D] Unknown Tripo task status '{}'; continuing to "
                     "poll".format(status))
        return 'running', None

    def _model_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Model URLs live under data.output (pbr_model / model /
        base_model); Tripo delivers GLB. Extension is sniffed from the
        URL with '.glb' as the default."""
        output = task_data.get('output')
        if not isinstance(output, dict):
            return None

        for key in TRIPO_OUTPUT_PREFERENCE:
            url = output.get(key)
            if url:
                return str(url), self._extension_from_url(url, default='.glb')
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap(data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Unwrap Tripo's {"code": 0, "data": {...}} response envelope.
        A non-zero code is an API-level failure."""
        code = data.get('code', 0)
        if code != 0:
            raise Gen3DError("Tripo API returned code {}: {}".format(
                code, str(data.get('message', data))[:200]))

        payload = data.get('data')
        if not isinstance(payload, dict):
            raise Gen3DError(
                "Tripo response had no 'data' object: {}".format(
                    str(data)[:200]))
        return payload

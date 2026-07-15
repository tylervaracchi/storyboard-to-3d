# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Meshy Text-to-3D Provider

Coded against the official Meshy API docs at
https://docs.meshy.ai/en/api/text-to-3d (checked 2026-07-14):

  Create task:  POST https://api.meshy.ai/openapi/v2/text-to-3d
  Poll task:    GET  https://api.meshy.ai/openapi/v2/text-to-3d/{id}
  Auth header:  Authorization: Bearer <MESHY_API_KEY>

  Create body (preview mode, the cheapest tier: an untextured mesh):
    {"mode": "preview", "prompt": "...", "ai_model": "latest",
     "topology": "triangle", "target_polycount": 30000,
     "target_formats": ["glb", "fbx"]}
  The create response carries the task id in the "result" field.

  Poll response fields:
    status: PENDING | IN_PROGRESS | SUCCEEDED | FAILED | CANCELED
    progress: 0-100
    model_urls: {"glb": ..., "fbx": ..., "obj": ..., "usdz": ..., ...}
    task_error: {"message": ...} on failure

  Meshy uses a two-step workflow: a "preview" task generates the mesh
  without texture; a "refine" task (body: {"mode": "refine",
  "preview_task_id": "<id>"}) adds textures at extra credit cost.

Quality tiers via the 'gen3d.quality' setting (Features tab Quality
dropdown; GEN3D_QUALITY env var overrides):
  'standard' (default, also 'refine'/'refined'/'textured'):
      preview task, then a refine task for textures.
  'draft' (also 'preview'/'fast'/'low' or any other value):
      preview task only, untextured. Cheapest and fastest.

API key: MESHY_API_KEY environment variable, then the plugin
config_manager pattern (see Gen3DProvider._resolve_api_key).
"""

from typing import Any, Dict, Optional, Tuple

from .base_provider import Gen3DProvider, Gen3DError, _log, _log_warning

try:
    import unreal  # noqa: F401  (parity guard; not directly used here)
except ImportError:
    unreal = None


MESHY_API_BASE = "https://api.meshy.ai/openapi/v2/text-to-3d"
MESHY_PROMPT_MAX_CHARS = 600
MESHY_PREFERRED_FORMATS = ('fbx', 'glb', 'obj')


class MeshyProvider(Gen3DProvider):
    """Meshy text-to-3D provider (https://docs.meshy.ai/en/api/text-to-3d)."""

    name = 'meshy'
    pricing_note = ("Meshy 'standard' quality (the default) runs a preview "
                    "task plus a refine task for textures; set gen3d.quality "
                    "to 'draft' for the cheapest untextured preview-only "
                    "tier. Pricing: https://www.meshy.ai/pricing")

    DEFAULT_QUALITY = 'standard'

    def get_api_key(self):
        # type: () -> Optional[str]
        """MESHY_API_KEY env var, then plugin config ('api.keys.meshy')."""
        return self._resolve_api_key('MESHY_API_KEY', 'meshy')

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
        """Create a preview-mode text-to-3d task; returns the task id."""
        body = {
            'mode': 'preview',
            'prompt': prompt[:MESHY_PROMPT_MAX_CHARS],
            'ai_model': 'latest',
            'topology': 'triangle',
            'target_polycount': 30000,
            # Ask for FBX alongside the default GLB so the UE FBX import
            # path can be used when available.
            'target_formats': ['glb', 'fbx']
        }
        return self._submit_task(body)

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        return self._request_json(
            'GET', '{}/{}'.format(MESHY_API_BASE, task_id),
            headers=self._headers())

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map Meshy status values to the base provider's states.

        Per https://docs.meshy.ai/en/api/text-to-3d (checked 2026-07-14):
        PENDING, IN_PROGRESS, SUCCEEDED, FAILED, CANCELED.
        """
        status = str(task_data.get('status', '')).strip().upper()

        if status == 'SUCCEEDED':
            return 'succeeded', None
        if status in ('FAILED', 'CANCELED', 'CANCELLED'):
            error = None
            task_error = task_data.get('task_error')
            if isinstance(task_error, dict):
                error = task_error.get('message')
            return 'failed', error or 'status {}'.format(status)
        if status == 'PENDING':
            return 'pending', None
        if status == 'IN_PROGRESS':
            return 'running', None

        _log_warning("[Gen3D] Unknown Meshy task status '{}'; continuing to "
                     "poll".format(status))
        return 'running', None

    def _model_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Model download URLs live in 'model_urls' keyed by format.
        Prefer FBX, then GLB, then OBJ."""
        model_urls = task_data.get('model_urls')
        if not isinstance(model_urls, dict):
            return None

        for fmt in MESHY_PREFERRED_FORMATS:
            url = model_urls.get(fmt)
            if url:
                return str(url), '.{}'.format(fmt)
        return None

    def _finalize(self, task_data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """When gen3d.quality is 'standard' (the default) or an explicit
        'refine' synonym, chain a refine task off the completed preview to
        get a textured model. Any refine failure logs and falls back to
        the untextured preview result."""
        if self.get_quality() not in ('standard', 'refine', 'refined',
                                      'textured'):
            return task_data

        preview_task_id = task_data.get('id')
        if not preview_task_id:
            _log_warning("[Gen3D] Meshy preview task has no id; skipping "
                         "refine stage")
            return task_data

        try:
            _log("[Gen3D] Meshy quality 'refine': starting refine task for "
                 "preview {}".format(preview_task_id))
            refine_id = self._submit_task({
                'mode': 'refine',
                'preview_task_id': str(preview_task_id)
            })
            return self._poll_until_done(refine_id)
        except Gen3DError as e:
            _log_warning("[Gen3D] Meshy refine stage failed ({}); using the "
                         "untextured preview model instead".format(e))
            return task_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _submit_task(self, body):
        # type: (Dict[str, Any]) -> str
        """POST a task creation body; return the new task id.

        The Meshy create response is {"result": "<task-id>"} per
        https://docs.meshy.ai/en/api/text-to-3d (checked 2026-07-14);
        'id' is also accepted defensively.
        """
        data = self._request_json(
            'POST', MESHY_API_BASE, headers=self._headers(), json_body=body)

        task_id = data.get('result') or data.get('id')
        if not task_id:
            raise Gen3DError(
                "Meshy create-task response had no task id: {}".format(
                    str(data)[:200]))
        return str(task_id)

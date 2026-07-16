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

Image-to-model (generate_from_image):
  Upload image: POST https://api.tripo3d.ai/v2/openapi/upload/sts
                (multipart field 'file') -> data.image_token.
                VERIFY-BEFORE-USE: older accounts/doc revisions use
                POST /v2/openapi/upload instead, so this module tries
                /upload/sts first and falls back to /upload.
  Create body:  {"type": "image_to_model",
                 "file": {"type": "<png|jpg|webp>", "file_token": <token>}}
                plus the same draft-tier texture/pbr flags as text tasks.
  Polling, status mapping, and model download reuse the exact same
  base-provider machinery as text_to_model.

Quality tiers via the 'gen3d.quality' setting (Features tab Quality
dropdown; GEN3D_QUALITY env var overrides):
  'standard' (default, also 'textured' or anything not listed below):
      omit the flags; Tripo's defaults produce a textured model.
  'draft' (also accepts 'preview'/'fast'/'low'):
      untextured model, cheapest and fastest (VERIFY-BEFORE-USE flags).

API key: TRIPO_API_KEY environment variable, then the plugin
config_manager pattern (see Gen3DProvider._resolve_api_key).
"""

import os
from typing import Any, Dict, Optional, Tuple

from .base_provider import Gen3DProvider, Gen3DError, _log, _log_warning

try:
    import unreal  # noqa: F401  (parity guard; not directly used here)
except ImportError:
    unreal = None


TRIPO_API_BASE = "https://api.tripo3d.ai/v2/openapi/task"
TRIPO_UPLOAD_STS_URL = "https://api.tripo3d.ai/v2/openapi/upload/sts"
TRIPO_UPLOAD_URL = "https://api.tripo3d.ai/v2/openapi/upload"
TRIPO_PROMPT_MAX_CHARS = 1024
TRIPO_DRAFT_QUALITIES = ('draft', 'preview', 'fast', 'low')
TRIPO_OUTPUT_PREFERENCE = ('pbr_model', 'model', 'base_model')
TRIPO_IMAGE_TYPE_MAP = {'.png': 'png', '.jpg': 'jpg', '.jpeg': 'jpg',
                        '.webp': 'webp'}


class TripoProvider(Gen3DProvider):
    """Tripo3D text-to-model and image-to-model provider
    (https://platform.tripo3d.ai/docs)."""

    name = 'tripo'
    pricing_note = ("Tripo3D 'standard' quality (the default) produces a "
                    "textured model; set gen3d.quality to 'draft' for the "
                    "cheapest untextured tier. "
                    "Pricing: https://platform.tripo3d.ai")

    DEFAULT_QUALITY = 'standard'

    def get_api_key(self):
        # type: () -> Optional[str]
        """TRIPO_API_KEY env var, then plugin config ('api.keys.tripo3d')."""
        return self._resolve_api_key('TRIPO_API_KEY', 'tripo3d')

    # ------------------------------------------------------------------
    # Image-to-model entrypoint (parallel to Gen3DProvider.generate)
    # ------------------------------------------------------------------

    def generate_from_image(self, image_path, name=None, **kwargs):
        # type: (str, Optional[str], **Any) -> Dict[str, Any]
        """
        Run a full image-to-3D generation: upload the image, create an
        image_to_model task, poll to completion, download the resulting
        model file to a temp file.

        Mirrors the Gen3DProvider.generate() contract exactly (the polling
        and download plumbing is the same base-provider machinery).

        Args:
            image_path: Local path of a PNG/JPG/WEBP image of the object.
            name: Optional entity name, used only for logging.
            **kwargs: Reserved for future options; ignored.

        Returns:
            {'status': 'succeeded', 'file_path': str, 'provider': str} or
            {'status': 'failed', 'error': str, 'provider': str}.
            Never raises.
        """
        try:
            if not image_path or not os.path.isfile(str(image_path)):
                raise Gen3DError(
                    "Image file not found: {}".format(image_path))

            if not self.get_api_key():
                raise Gen3DError(
                    "No API key available for provider '{}'".format(self.name))

            label = name or os.path.basename(str(image_path))
            _log("[Gen3D] Creating {} image-to-3D task for '{}' from {}".format(
                self.name, label, image_path))

            file_token = self._upload_image(str(image_path))
            task_id = self._create_image_task(
                file_token, self._image_file_type(str(image_path)))
            if not task_id:
                raise Gen3DError("Provider returned no task id")

            task_data = self._poll_until_done(task_id)
            task_data = self._finalize(task_data)

            url_info = self._model_url(task_data)
            if not url_info or not url_info[0]:
                raise Gen3DError("No downloadable model URL in task result")

            url, extension = url_info
            file_path = self._download_to_temp(url, extension)
            _log("[Gen3D] {} image-to-3D generation succeeded, model saved "
                 "to {}".format(self.name, file_path))
            return {
                'status': 'succeeded',
                'file_path': file_path,
                'provider': self.name,
                # Vendor task id of the finished generation - post-steps
                # (e.g. animate_rig for characters) run against it.
                'task_id': task_id
            }
        except Gen3DError as e:
            _log_warning("[Gen3D] {} image-to-3D generation failed: {}".format(
                self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}
        except Exception as e:
            # Belt and braces: generate_from_image() must never raise.
            _log_warning("[Gen3D] {} image-to-3D generation failed "
                         "unexpectedly: {}".format(self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}

    # ------------------------------------------------------------------
    # Auto-rigging (characters)
    # ------------------------------------------------------------------

    def rig_model(self, model_task_id, name=None):
        # type: (str, Optional[str]) -> Dict[str, Any]
        """
        Auto-rig a previously generated model so it imports as a
        SkeletalMesh: run the free animate_prerigcheck, then an
        animate_rig task (Mixamo-style spec, ~25 credits), and download
        the rigged GLB.

        Mirrors the generate() contract: returns
        {'status': 'succeeded', 'file_path': str, 'rig_task_id': str,
         'provider': str} or {'status': 'failed', 'error': str,
        'provider': str}. Never raises. The rig_task_id can later drive
        animate_retarget clips onto this exact character (see
        core/genanim/tripo_provider.py).

        Body shapes cross-checked against the official tripo-js-sdk
        (VERIFY-BEFORE-USE, same caveat as the module docstring); any
        rejection surfaces as a failed dict and callers fall back to the
        static import.
        """
        try:
            if not model_task_id:
                raise Gen3DError("No model task id to rig")
            if not self.get_api_key():
                raise Gen3DError(
                    "No API key available for provider '{}'".format(self.name))

            label = name or model_task_id

            # (1) Free riggability check. An explicit "not riggable" is an
            # honest failure; an errored check logs and proceeds to the
            # rig attempt (the rig task itself fails cleanly if unriggable).
            try:
                check_id = self._create_animate_task(
                    'animate_prerigcheck', model_task_id)
                check_data = self._poll_until_done(check_id)
                output = check_data.get('output')
                riggable = output.get('riggable') \
                    if isinstance(output, dict) else None
                if riggable is False:
                    raise Gen3DError(
                        "Tripo prerigcheck: model for '{}' is not "
                        "riggable".format(label))
                _log("[Gen3D] Tripo prerigcheck passed for '{}'".format(label))
            except Gen3DError as e:
                if 'not riggable' in str(e):
                    raise
                _log_warning("[Gen3D] Tripo prerigcheck errored for '{}' "
                             "({}); attempting rig anyway".format(label, e))

            # (2) Rig (paid). GLB keeps the download/import path identical
            # to the base generation; Interchange imports skinned GLBs as
            # SkeletalMesh assets.
            _log("[Gen3D] Creating Tripo animate_rig task for '{}'".format(
                label))
            rig_task_id = self._create_animate_task(
                'animate_rig', model_task_id,
                extra={'out_format': 'glb', 'spec': 'mixamo'})
            # Rigging on textured models routinely runs 2-4 minutes;
            # the generic 180s generation timeout is too tight.
            rig_timeout = max(420, self.get_timeout_seconds())
            task_data = self._poll_until_done(rig_task_id,
                                              timeout_seconds=rig_timeout)

            url_info = self._model_url(task_data)
            if not url_info or not url_info[0]:
                raise Gen3DError("No downloadable rigged model URL in "
                                 "rig task result")

            url, extension = url_info
            file_path = self._download_to_temp(url, extension)
            _log("[Gen3D] Tripo rig succeeded for '{}', rigged model saved "
                 "to {}".format(label, file_path))
            return {
                'status': 'succeeded',
                'file_path': file_path,
                'rig_task_id': str(rig_task_id),
                'provider': self.name
            }
        except Gen3DError as e:
            _log_warning("[Gen3D] Tripo rigging failed: {}".format(e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}
        except Exception as e:
            # rig_model() must never raise; callers fall back to static.
            _log_warning("[Gen3D] Tripo rigging failed unexpectedly: "
                         "{}".format(e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}

    def _create_animate_task(self, task_type, model_task_id, extra=None):
        # type: (str, str, Optional[Dict[str, Any]]) -> str
        """Create an animate_* task against a finished model task; returns
        the new task id. Body shape per the tripo-js-sdk
        (VERIFY-BEFORE-USE)."""
        body = {
            'type': task_type,
            'original_model_task_id': str(model_task_id)
        }
        if extra:
            body.update(extra)

        data = self._request_json(
            'POST', TRIPO_API_BASE, headers=self._headers(), json_body=body)
        payload = self._unwrap(data)

        task_id = payload.get('task_id')
        if not task_id:
            raise Gen3DError(
                "Tripo {} response had no task_id: {}".format(
                    task_type, str(data)[:200]))
        return str(task_id)

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

    def _create_image_task(self, file_token, file_type):
        # type: (str, str) -> str
        """Create an image_to_model task from an uploaded image token;
        returns the task id. Sends the same draft-tier quality flags as
        the text task where applicable."""
        body = {
            'type': 'image_to_model',
            'file': {
                'type': file_type,
                'file_token': file_token
            }
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

    def _upload_image(self, image_path):
        # type: (str) -> str
        """
        Upload an image to Tripo and return its image token.

        Tries POST /v2/openapi/upload/sts first (current docs), then the
        legacy POST /v2/openapi/upload; both take a multipart 'file' field
        and answer {'code': 0, 'data': {'image_token': ...}}.

        Raises:
            Gen3DError when both endpoints fail.
        """
        requests = self._requests()
        last_error = None

        for url in (TRIPO_UPLOAD_STS_URL, TRIPO_UPLOAD_URL):
            try:
                with open(image_path, 'rb') as handle:
                    response = requests.post(
                        url,
                        headers={'Authorization': 'Bearer {}'.format(
                            self.get_api_key())},
                        files={'file': (os.path.basename(image_path), handle)},
                        timeout=self.DOWNLOAD_TIMEOUT_SECONDS)
            except Exception as e:
                last_error = "POST {} failed: {}".format(url, e)
                _log_warning("[Gen3D] Tripo image upload attempt failed "
                             "({}); trying next endpoint".format(last_error))
                continue

            if response.status_code < 200 or response.status_code >= 300:
                last_error = "POST {} returned HTTP {}: {}".format(
                    url, response.status_code, response.text[:300])
                _log_warning("[Gen3D] Tripo image upload attempt failed "
                             "({}); trying next endpoint".format(last_error))
                continue

            try:
                data = response.json()
            except ValueError as e:
                last_error = "Non-JSON response from {}: {}".format(url, e)
                _log_warning("[Gen3D] Tripo image upload attempt failed "
                             "({}); trying next endpoint".format(last_error))
                continue

            if not isinstance(data, dict):
                last_error = "Unexpected response shape from {}".format(url)
                continue

            try:
                payload = self._unwrap(data)
            except Gen3DError as e:
                last_error = str(e)
                _log_warning("[Gen3D] Tripo image upload attempt failed "
                             "({}); trying next endpoint".format(last_error))
                continue

            token = (payload.get('image_token') or payload.get('token')
                     or payload.get('file_token'))
            if token:
                return str(token)
            last_error = "no image_token in upload response: {}".format(
                str(data)[:200])

        raise Gen3DError("Tripo image upload failed: {}".format(
            last_error or 'unknown error'))

    @staticmethod
    def _image_file_type(image_path):
        # type: (str) -> str
        """Map an image file extension onto Tripo's file.type values
        ('png' / 'jpg' / 'webp'); 'png' when unrecognized."""
        ext = os.path.splitext(str(image_path))[1].lower()
        return TRIPO_IMAGE_TYPE_MAP.get(ext, 'png')

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

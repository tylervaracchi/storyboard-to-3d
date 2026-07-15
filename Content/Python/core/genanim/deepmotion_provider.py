# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
DeepMotion SayMotion Text-to-Animation Provider

The only fully documented TRUE prompt-to-clip REST API. Coded against the
official repo https://github.com/DeepMotion/SayMotion-REST-API (checked
2026-07-14):

  Auth:      GET  {base}/account/v1/auth
             Header: Authorization: Basic base64(clientId:clientSecret)
             Success sets a 'dmsess' session cookie that must accompany
             all later calls (a requests.Session carries it here).
  Generate:  POST {base}/job/v1/process/text2motion
             Body: {"params": ["prompt=<text>", "model=<id>",
                               "numVariant=1", "skipFBX=0", ...]}
  Poll:      GET  {base}/job/v1/status/{rid}
             Status values: PROGRESS (with queue position) | SUCCESS |
             FAILURE. VERIFY-BEFORE-USE: the response may wrap the record
             in a 'status' list; both the flat and list shapes are
             handled below.
  Download:  GET  {base}/job/v1/download/{rid}
             Returns URLs for FBX, BVH, and GLB per variant.
             VERIFY-BEFORE-USE: the exact nesting is not pinned down, so
             the extractor below walks the JSON for the first 'fbx' /
             'glb' / 'bvh' URL, in that preference order.

ACCESS GATING (checked 2026-07-14): SayMotion API access is limited to
verified partners; the production base URL is issued with credentials
(the docs use a localhost placeholder). That is why the base URL must be
supplied via the DEEPMOTION_API_BASE environment variable or the
'genanim.deepmotion_base_url' setting; without it this provider reports
itself unavailable. API-tier pricing is unpublished (VERIFY-BEFORE-USE);
web-product pricing as a proxy: credit-based, roughly 1 credit per 10 s
of generated animation.

SKELETON: upload a Mixamo-skeleton proxy avatar once via the
/character/v1/getModelUploadUrl + /character/v1/storeModel endpoints (not
automated here) and store its model id in the
'genanim.deepmotion_model_id' setting or DEEPMOTION_MODEL_ID environment
variable, so every generated FBX lands on one known skeleton. Imported
clips then remap onto project characters through UE5's standard IK
Retargeter workflow.

Credentials: the Settings dialog Features tab fields
('genanim.deepmotion_client_id' / 'genanim.deepmotion_client_secret').
DEEPMOTION_CLIENT_ID and DEEPMOTION_CLIENT_SECRET environment variables
work as optional overrides, and the plugin config_manager pattern
('api.keys.deepmotion_client_id' / 'api.keys.deepmotion_client_secret')
remains a final fallback.
"""

import base64
import os
from typing import Any, Dict, Optional, Tuple

from .base_provider import GenAnimProvider, GenAnimError, _log, _log_warning

try:
    import unreal  # noqa: F401  (parity guard; not directly used here)
except ImportError:
    unreal = None


DEEPMOTION_PROMPT_MAX_CHARS = 1000
DEEPMOTION_FORMAT_PREFERENCE = ('fbx', 'glb', 'bvh')


def _find_format_url(data, fmt):
    # type: (Any, str) -> Optional[str]
    """Recursively walk a JSON structure for the first HTTP(S) URL stored
    under a key matching the given format name ('fbx', 'glb', 'bvh').
    Tolerant of the download response's exact nesting
    (VERIFY-BEFORE-USE, see module docstring)."""
    if isinstance(data, dict):
        for key, value in data.items():
            if (str(key).strip().lower() == fmt
                    and isinstance(value, str)
                    and value.startswith(('http://', 'https://'))):
                return value
            found = _find_format_url(value, fmt)
            if found:
                return found
    elif isinstance(data, (list, tuple)):
        for item in data:
            found = _find_format_url(item, fmt)
            if found:
                return found
    return None


class DeepMotionProvider(GenAnimProvider):
    """DeepMotion SayMotion text2motion provider
    (https://github.com/DeepMotion/SayMotion-REST-API)."""

    name = 'deepmotion'
    pricing_note = ("DeepMotion SayMotion is partner-gated with unpublished "
                    "API pricing (VERIFY-BEFORE-USE); web-product proxy is "
                    "roughly 1 credit per 10 s clip. Request access at "
                    "https://www.deepmotion.com/saymotion-api")

    def __init__(self, api_key=None):
        super(DeepMotionProvider, self).__init__(api_key=api_key)
        self._client_secret = None
        self._client_secret_resolved = False
        self._session = None

    # ------------------------------------------------------------------
    # Credentials and availability
    # ------------------------------------------------------------------

    def get_api_key(self):
        # type: () -> Optional[str]
        """DEEPMOTION_CLIENT_ID env var (optional override), then the
        Settings dialog field ('genanim.deepmotion_client_id', Features
        tab), then plugin config ('api.keys.deepmotion_client_id')."""
        return self._resolve_api_key(
            'DEEPMOTION_CLIENT_ID', 'deepmotion_client_id',
            settings_path='genanim.deepmotion_client_id')

    def get_client_secret(self):
        # type: () -> Optional[str]
        """DEEPMOTION_CLIENT_SECRET env var (optional override), then the
        Settings dialog field ('genanim.deepmotion_client_secret', Features
        tab), then plugin config ('api.keys.deepmotion_client_secret')."""
        if self._client_secret_resolved:
            return self._client_secret
        self._client_secret_resolved = True
        self._client_secret = self._lookup_key(
            'DEEPMOTION_CLIENT_SECRET', 'deepmotion_client_secret',
            settings_path='genanim.deepmotion_client_secret')
        return self._client_secret

    def get_base_url(self):
        # type: () -> Optional[str]
        """Partner-issued API base URL: DEEPMOTION_API_BASE env var, then
        the 'genanim.deepmotion_base_url' setting. None when unset (the
        docs only publish a localhost placeholder)."""
        base = os.environ.get('DEEPMOTION_API_BASE')
        if not base:
            base = self._get_setting('genanim.deepmotion_base_url', None)
        if not base:
            return None
        return str(base).strip().rstrip('/') or None

    def get_model_id(self):
        # type: () -> Optional[str]
        """Optional custom character model id (the uploaded Mixamo-skeleton
        proxy avatar): DEEPMOTION_MODEL_ID env var, then the
        'genanim.deepmotion_model_id' setting."""
        model_id = os.environ.get('DEEPMOTION_MODEL_ID')
        if not model_id:
            model_id = self._get_setting('genanim.deepmotion_model_id', None)
        if not model_id:
            return None
        return str(model_id).strip() or None

    def is_available(self):
        # type: () -> bool
        """Requires client id, client secret, and the partner-issued base
        URL."""
        if not self.get_api_key() or not self.get_client_secret():
            return False
        if not self.get_base_url():
            _log_warning("[GenAnim] DeepMotion credentials found but no API "
                         "base URL (set DEEPMOTION_API_BASE or the "
                         "'genanim.deepmotion_base_url' setting; the URL is "
                         "issued with partner credentials); DeepMotion "
                         "generation disabled")
            return False
        return True

    # ------------------------------------------------------------------
    # Session (cookie) auth
    # ------------------------------------------------------------------

    def _ensure_session(self):
        """Authenticate once per provider instance: GET /account/v1/auth
        with Basic auth; the returned 'dmsess' cookie lives on the
        requests.Session used for all later calls."""
        if self._session is not None:
            return self._session

        requests = self._requests()
        base = self.get_base_url()
        if not base:
            raise GenAnimError("No DeepMotion API base URL configured")

        client_id = self.get_api_key()
        client_secret = self.get_client_secret()
        if not client_id or not client_secret:
            raise GenAnimError("DeepMotion client id/secret unavailable")

        credentials = '{}:{}'.format(client_id, client_secret)
        token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')

        session = requests.Session()
        try:
            response = session.get(
                '{}/account/v1/auth'.format(base),
                headers={'Authorization': 'Basic {}'.format(token)},
                timeout=self.REQUEST_TIMEOUT_SECONDS)
        except Exception as e:
            raise GenAnimError("DeepMotion auth request failed: {}".format(e))

        if response.status_code < 200 or response.status_code >= 300:
            raise GenAnimError("DeepMotion auth returned HTTP {}: {}".format(
                response.status_code, response.text[:200]))

        # The session cookie ('dmsess') now lives on the session object.
        self._session = session
        _log("[GenAnim] DeepMotion session established")
        return session

    # ------------------------------------------------------------------
    # GenAnimProvider hooks
    # ------------------------------------------------------------------

    def _create_task(self, action_text):
        # type: (str) -> str
        """POST /job/v1/process/text2motion; returns the request id (rid)."""
        session = self._ensure_session()
        base = self.get_base_url()

        prompt = str(action_text)[:DEEPMOTION_PROMPT_MAX_CHARS]
        # numVariant=1 and skipFBX=0 keep cost minimal while retaining the
        # FBX output the UE import path prefers.
        params = ['prompt={}'.format(prompt), 'numVariant=1', 'skipFBX=0']
        model_id = self.get_model_id()
        if model_id:
            params.append('model={}'.format(model_id))

        data = self._request_json(
            'POST', '{}/job/v1/process/text2motion'.format(base),
            json_body={'params': params}, session=session)

        # VERIFY-BEFORE-USE: the create response carries the request id as
        # 'rid'; a 'rids' list is also accepted defensively.
        rid = data.get('rid')
        if not rid:
            rids = data.get('rids')
            if isinstance(rids, (list, tuple)) and rids:
                rid = rids[0]
        if not rid:
            raise GenAnimError(
                "DeepMotion text2motion response had no rid: {}".format(
                    str(data)[:200]))
        return str(rid)

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        """GET /job/v1/status/{rid}, normalized to a flat record carrying
        'rid' and 'status'."""
        session = self._ensure_session()
        base = self.get_base_url()
        data = self._request_json(
            'GET', '{}/job/v1/status/{}'.format(base, task_id),
            session=session)

        # VERIFY-BEFORE-USE: the status endpoint may wrap records in a
        # 'status' list ({"count": 1, "status": [{...}]}); normalize both
        # shapes to one flat dict.
        record = data
        wrapped = data.get('status')
        if isinstance(wrapped, (list, tuple)) and wrapped:
            first = wrapped[0]
            if isinstance(first, dict):
                record = first
        record = dict(record)
        record.setdefault('rid', task_id)
        return record

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map SayMotion status values (PROGRESS | SUCCESS | FAILURE) to
        the base provider's states. Unknown statuses keep polling until
        the timeout rather than aborting."""
        status = str(task_data.get('status', '')).strip().upper()

        if status == 'SUCCESS':
            return 'succeeded', None
        if status in ('FAILURE', 'FAILED', 'CANCELED', 'CANCELLED'):
            details = task_data.get('details')
            return 'failed', (str(details)[:200] if details
                              else 'status {}'.format(status))
        if status in ('PROGRESS', 'RETRY', 'PENDING', 'QUEUED'):
            return 'running', None

        _log_warning("[GenAnim] Unknown DeepMotion job status '{}'; "
                     "continuing to poll".format(status))
        return 'running', None

    def _finalize(self, task_data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """SayMotion's download URLs come from a separate endpoint: GET
        /job/v1/download/{rid}. Merge that response into the task record
        so _clip_url can extract from it."""
        rid = task_data.get('rid')
        if not rid:
            raise GenAnimError("DeepMotion task record has no rid; cannot "
                               "fetch download links")

        session = self._ensure_session()
        base = self.get_base_url()
        download = self._request_json(
            'GET', '{}/job/v1/download/{}'.format(base, rid),
            session=session)

        merged = dict(task_data)
        merged['_download'] = download
        return merged

    def _clip_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Walk the download response for the first FBX (preferred), GLB,
        or BVH URL."""
        download = task_data.get('_download')
        if download is None:
            return None

        for fmt in DEEPMOTION_FORMAT_PREFERENCE:
            url = _find_format_url(download, fmt)
            if url:
                return url, '.{}'.format(fmt)
        return None

    def _download_to_temp(self, url, extension, session=None):
        # type: (str, str, Optional[Any]) -> str
        """Download using the authenticated session by default (the file
        URLs may require the 'dmsess' cookie; signed URLs ignore it)."""
        if session is None:
            session = self._session
        return super(DeepMotionProvider, self)._download_to_temp(
            url, extension, session=session)

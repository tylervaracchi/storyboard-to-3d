# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Gen3D Base Provider

Abstract base class for generative text-to-3D providers (Meshy, Tripo3D).
Implements the shared plumbing every provider needs:

  - generate(prompt) -> dict(status, file_path OR error) that never raises
  - poll-until-done loop (interval ~5s, overall timeout from the
    'gen3d.timeout_seconds' setting, default 180)
  - streamed download-to-temp-file helper (requests)
  - API key resolution: environment variable first, then the plugin's
    config_manager pattern (which loads ~/.storyboard_to_3d/.env into the
    environment), mirroring core/asset_matcher.py's OpenAI key resolution

Subclasses implement four small hooks against their vendor's REST API:
_create_task, _fetch_task, _task_state, and _model_url. See
meshy_provider.py and tripo_provider.py for the concrete implementations
and the vendor doc references they were coded against.

This module is importable outside the Unreal Editor (the 'unreal' import
is guarded), so the HTTP plumbing can be unit-tested standalone.
"""

import os
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (e.g. unit tests of the
    # HTTP/polling plumbing). Editor-dependent features are skipped.
    unreal = None


def _log(message):
    """Log an info message via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def _log_warning(message):
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {}".format(message))


class Gen3DError(Exception):
    """Raised internally for any generation failure; callers of
    Gen3DProvider.generate() never see it (generate catches everything
    and returns a status dict)."""
    pass


class Gen3DProvider(object):
    """
    Abstract base for text-to-3D generation providers.

    Attributes:
        name: Short provider identifier ('meshy', 'tripo').
        pricing_note: Human-readable note about the cost tier used.

    Contract:
        generate(prompt) returns a dict and NEVER raises:
            {'status': 'succeeded', 'file_path': <local file>, 'provider': name}
            {'status': 'failed',    'error': <reason>,          'provider': name}
    """

    name = 'base'
    pricing_note = ''

    DEFAULT_QUALITY = 'preview'
    DEFAULT_TIMEOUT_SECONDS = 180
    POLL_INTERVAL_SECONDS = 5.0
    REQUEST_TIMEOUT_SECONDS = 30
    DOWNLOAD_TIMEOUT_SECONDS = 120

    def __init__(self, api_key=None):
        """
        Args:
            api_key: Optional explicit API key. When omitted, the key is
                resolved lazily from the environment / plugin config.
        """
        self._api_key = api_key
        self._api_key_resolved = bool(api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt):
        # type: (str) -> Dict[str, Any]
        """
        Run a full text-to-3D generation: create task, poll to completion,
        download the resulting model file to a temp file.

        Args:
            prompt: Text description of the object to generate.

        Returns:
            {'status': 'succeeded', 'file_path': str, 'provider': str} or
            {'status': 'failed', 'error': str, 'provider': str}.
            Never raises.
        """
        try:
            if not prompt or not str(prompt).strip():
                raise Gen3DError("Empty prompt")

            if not self.get_api_key():
                raise Gen3DError(
                    "No API key available for provider '{}'".format(self.name))

            _log("[Gen3D] Creating {} text-to-3D task for prompt: {}".format(
                self.name, str(prompt)[:120]))
            task_id = self._create_task(str(prompt))
            if not task_id:
                raise Gen3DError("Provider returned no task id")

            task_data = self._poll_until_done(task_id)
            task_data = self._finalize(task_data)

            url_info = self._model_url(task_data)
            if not url_info or not url_info[0]:
                raise Gen3DError("No downloadable model URL in task result")

            url, extension = url_info
            file_path = self._download_to_temp(url, extension)
            _log("[Gen3D] {} generation succeeded, model saved to {}".format(
                self.name, file_path))
            return {
                'status': 'succeeded',
                'file_path': file_path,
                'provider': self.name
            }
        except Gen3DError as e:
            _log_warning("[Gen3D] {} generation failed: {}".format(self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}
        except Exception as e:
            # Belt and braces: generate() must never raise.
            _log_warning("[Gen3D] {} generation failed unexpectedly: {}".format(
                self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}

    def is_available(self):
        # type: () -> bool
        """True when an API key can be resolved for this provider."""
        return bool(self.get_api_key())

    def get_api_key(self):
        # type: () -> Optional[str]
        """Resolve this provider's API key. Subclasses must implement."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def _create_task(self, prompt):
        # type: (str) -> str
        """Create a generation task; return the vendor task id.
        Raise Gen3DError on failure."""
        raise NotImplementedError

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        """Fetch the current task record from the vendor API.
        Raise Gen3DError on failure."""
        raise NotImplementedError

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map a vendor task record to (state, error_message) where state
        is one of 'pending', 'running', 'succeeded', 'failed'."""
        raise NotImplementedError

    def _model_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Extract (download_url, file_extension) from a succeeded task
        record, or None when no model URL is present."""
        raise NotImplementedError

    def _finalize(self, task_data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Optional post-poll hook (e.g. Meshy's refine stage). The default
        implementation returns the task record unchanged."""
        return task_data

    # ------------------------------------------------------------------
    # Shared plumbing
    # ------------------------------------------------------------------

    def _poll_until_done(self, task_id):
        # type: (str) -> Dict[str, Any]
        """
        Poll the vendor task until it reaches a terminal state.

        Poll interval is POLL_INTERVAL_SECONDS (~5s); the overall timeout
        comes from the 'gen3d.timeout_seconds' setting (default 180).

        Returns:
            The final (succeeded) task record.

        Raises:
            Gen3DError on task failure or timeout.
        """
        timeout_seconds = self.get_timeout_seconds()
        deadline = time.time() + timeout_seconds
        last_state = None

        while True:
            task_data = self._fetch_task(task_id)
            state, error_message = self._task_state(task_data)

            if state == 'succeeded':
                return task_data
            if state == 'failed':
                raise Gen3DError("Task {} failed: {}".format(
                    task_id, error_message or 'no reason given'))

            if state != last_state:
                _log("[Gen3D] {} task {} is {}...".format(
                    self.name, task_id, state))
                last_state = state

            remaining = deadline - time.time()
            if remaining <= 0:
                raise Gen3DError(
                    "Task {} timed out after {}s (still {})".format(
                        task_id, timeout_seconds, state))

            time.sleep(min(self.POLL_INTERVAL_SECONDS, max(remaining, 0.1)))

    def _download_to_temp(self, url, extension):
        # type: (str, str) -> str
        """
        Stream a model file download to a named temp file.

        Args:
            url: HTTP(S) download URL.
            extension: File extension including the dot (e.g. '.glb').

        Returns:
            Absolute path of the downloaded temp file.

        Raises:
            Gen3DError on any download failure.
        """
        requests = self._requests()

        if not extension:
            extension = '.glb'
        if not extension.startswith('.'):
            extension = '.' + extension

        try:
            response = requests.get(
                url, stream=True, timeout=self.DOWNLOAD_TIMEOUT_SECONDS)
        except Exception as e:
            raise Gen3DError("Model download failed: {}".format(e))

        if response.status_code != 200:
            raise Gen3DError("Model download failed with HTTP {}".format(
                response.status_code))

        temp_file = tempfile.NamedTemporaryFile(
            delete=False, prefix='gen3d_{}_'.format(self.name),
            suffix=extension)
        try:
            with temp_file:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        temp_file.write(chunk)
        except Exception as e:
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass
            raise Gen3DError("Model download interrupted: {}".format(e))

        return temp_file.name

    def _requests(self):
        """Import and return the requests module, or raise Gen3DError."""
        try:
            import requests
            return requests
        except ImportError:
            raise Gen3DError(
                "The 'requests' package is unavailable; cannot call the "
                "{} API".format(self.name))

    def _request_json(self, method, url, headers=None, json_body=None):
        # type: (str, str, Optional[Dict], Optional[Dict]) -> Dict[str, Any]
        """
        Perform an HTTP request and parse the JSON response.

        Raises:
            Gen3DError on transport errors, non-2xx status, or bad JSON.
        """
        requests = self._requests()
        try:
            response = requests.request(
                method, url, headers=headers, json=json_body,
                timeout=self.REQUEST_TIMEOUT_SECONDS)
        except Exception as e:
            raise Gen3DError("{} request to {} failed: {}".format(
                method, url, e))

        if response.status_code < 200 or response.status_code >= 300:
            raise Gen3DError("{} {} returned HTTP {}: {}".format(
                method, url, response.status_code, response.text[:300]))

        try:
            data = response.json()
        except ValueError as e:
            raise Gen3DError("Non-JSON response from {}: {}".format(url, e))

        if not isinstance(data, dict):
            raise Gen3DError("Unexpected response shape from {}".format(url))
        return data

    # ------------------------------------------------------------------
    # Settings and key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_setting(path, default):
        """Read a plugin setting via core.settings_manager, guarded so
        this works (returning the default) outside the editor too."""
        try:
            from core.settings_manager import get_setting
            value = get_setting(path, default)
            return default if value is None else value
        except Exception:
            return default

    def get_timeout_seconds(self):
        # type: () -> float
        """Overall generation timeout ('gen3d.timeout_seconds', default 180)."""
        value = (os.environ.get('GEN3D_TIMEOUT_SECONDS')
                 or self._get_setting('gen3d.timeout_seconds',
                                      self.DEFAULT_TIMEOUT_SECONDS))
        try:
            timeout = float(value)
            if timeout <= 0:
                raise ValueError("non-positive timeout")
            return timeout
        except (TypeError, ValueError):
            _log_warning("[Gen3D] Invalid gen3d.timeout_seconds value {!r}; "
                         "using default {}".format(
                             value, self.DEFAULT_TIMEOUT_SECONDS))
            return float(self.DEFAULT_TIMEOUT_SECONDS)

    def get_quality(self):
        # type: () -> str
        """Quality tier from the 'gen3d.quality' setting (lowercased).
        Defaults to the provider's cheapest tier."""
        value = (os.environ.get('GEN3D_QUALITY')
                 or self._get_setting('gen3d.quality', self.DEFAULT_QUALITY))
        return str(value).strip().lower() or self.DEFAULT_QUALITY

    def _resolve_api_key(self, env_var, config_key_name):
        # type: (str, str) -> Optional[str]
        """
        Resolve an API key with the same pattern core/asset_matcher.py uses
        for the OpenAI key:

          1. Environment variable (env_var).
          2. The plugin's config_manager: constructing it loads
             ~/.storyboard_to_3d/.env into the environment, so the env var
             is re-checked, then the 'api.keys.<name>' config entry.

        Args:
            env_var: Environment variable name (e.g. 'MESHY_API_KEY').
            config_key_name: Key under 'api.keys.' in the plugin config
                (e.g. 'meshy').

        Returns:
            API key string, or None if unavailable. Never raises.
        """
        if self._api_key_resolved:
            return self._api_key

        self._api_key_resolved = True
        api_key = os.environ.get(env_var)

        if not api_key:
            # Settings UI key (Features tab), e.g. 'gen3d.tripo_api_key'.
            # Keyed by provider name (self.name), NOT config_key_name: the
            # Features tab saves 'gen3d.tripo_api_key' while Tripo's config
            # key is 'tripo3d', so formatting config_key_name silently missed.
            # settings_manager imports unreal, so this is editor-only; guarded
            # so headless use falls through to the config path unchanged.
            try:
                from core.settings_manager import get_setting
                candidate = get_setting(
                    "gen3d.{}_api_key".format(self.name), None)
                if candidate:
                    api_key = str(candidate).strip() or None
            except Exception:
                api_key = None

        if not api_key:
            get_config = None
            try:
                from config.config_manager import get_config
            except ImportError:
                try:
                    from config_manager import get_config
                except ImportError:
                    get_config = None

            if get_config is not None:
                try:
                    cfg = get_config()  # side effect: loads .env into environ
                    api_key = os.environ.get(env_var)
                    if not api_key:
                        api_key = cfg.get("api.keys.{}".format(config_key_name))
                except Exception as e:
                    _log_warning("[Gen3D] Could not resolve {} via "
                                 "config_manager: {}".format(env_var, e))
                    api_key = None

        self._api_key = api_key
        return api_key

    @staticmethod
    def _extension_from_url(url, default='.glb'):
        # type: (str, str) -> str
        """Best-effort file extension sniff from a download URL path."""
        try:
            path = str(url).split('?', 1)[0].split('#', 1)[0]
            _root, ext = os.path.splitext(path)
            ext = ext.lower()
            if ext in ('.fbx', '.glb', '.gltf', '.obj', '.usdz', '.stl'):
                return ext
        except Exception:
            pass
        return default

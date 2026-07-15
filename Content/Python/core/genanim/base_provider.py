# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GenAnim Base Provider

Abstract base class for generative text-to-animation providers (Tripo
rig-and-retarget presets, DeepMotion SayMotion text2motion). Mirrors
core/gen3d/base_provider.py and implements the shared plumbing every
provider needs:

  - generate(action_text) -> dict(status, file_path OR error) that never
    raises
  - poll-until-done loop (interval ~5s, overall timeout from the
    'genanim.timeout_seconds' setting, default 240; animation jobs queue
    longer than text-to-3D jobs, hence the higher default)
  - streamed download-to-temp-file helper (requests), with optional
    requests.Session support for cookie-authenticated providers
  - API key resolution: environment variable first, then the plugin's
    config_manager pattern (which loads ~/.storyboard_to_3d/.env into the
    environment), mirroring core/gen3d/base_provider.py

Subclasses implement four small hooks against their vendor's REST API:
_create_task, _fetch_task, _task_state, and _clip_url. See
tripo_provider.py and deepmotion_provider.py for the concrete
implementations and the vendor doc references they were coded against.

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


class GenAnimError(Exception):
    """Raised internally for any generation failure; callers of
    GenAnimProvider.generate() never see it (generate catches everything
    and returns a status dict)."""
    pass


class GenAnimProvider(object):
    """
    Abstract base for text-to-animation generation providers.

    Attributes:
        name: Short provider identifier ('tripo', 'deepmotion').
        pricing_note: Human-readable note about the cost tier used.

    Contract:
        generate(action_text) returns a dict and NEVER raises:
            {'status': 'succeeded', 'file_path': <local file>, 'provider': name}
            {'status': 'failed',    'error': <reason>,          'provider': name}
    """

    name = 'base'
    pricing_note = ''

    DEFAULT_TIMEOUT_SECONDS = 240
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

    def generate(self, action_text):
        # type: (str) -> Dict[str, Any]
        """
        Run a full text-to-animation generation: create task, poll to
        completion, download the resulting clip file to a temp file.

        Args:
            action_text: Free-form action text ("running", "waves hello").

        Returns:
            {'status': 'succeeded', 'file_path': str, 'provider': str} or
            {'status': 'failed', 'error': str, 'provider': str}.
            Never raises.
        """
        try:
            if not action_text or not str(action_text).strip():
                raise GenAnimError("Empty action text")

            if not self.get_api_key():
                raise GenAnimError(
                    "No API key available for provider '{}'".format(self.name))

            _log("[GenAnim] Creating {} text-to-animation task for action: "
                 "{}".format(self.name, str(action_text)[:120]))
            task_id = self._create_task(str(action_text))
            if not task_id:
                raise GenAnimError("Provider returned no task id")

            task_data = self._poll_until_done(task_id)
            task_data = self._finalize(task_data)

            url_info = self._clip_url(task_data)
            if not url_info or not url_info[0]:
                raise GenAnimError("No downloadable clip URL in task result")

            url, extension = url_info
            file_path = self._download_to_temp(url, extension)
            _log("[GenAnim] {} generation succeeded, clip saved to {}".format(
                self.name, file_path))
            return {
                'status': 'succeeded',
                'file_path': file_path,
                'provider': self.name
            }
        except GenAnimError as e:
            _log_warning("[GenAnim] {} generation failed: {}".format(
                self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}
        except Exception as e:
            # Belt and braces: generate() must never raise.
            _log_warning("[GenAnim] {} generation failed unexpectedly: "
                         "{}".format(self.name, e))
            return {'status': 'failed', 'error': str(e), 'provider': self.name}

    def is_available(self):
        # type: () -> bool
        """True when an API key can be resolved for this provider.
        Subclasses may add further requirements (rig ids, base URLs)."""
        return bool(self.get_api_key())

    def get_api_key(self):
        # type: () -> Optional[str]
        """Resolve this provider's API key. Subclasses must implement."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def _create_task(self, action_text):
        # type: (str) -> str
        """Create a generation task; return the vendor task id.
        Raise GenAnimError on failure."""
        raise NotImplementedError

    def _fetch_task(self, task_id):
        # type: (str) -> Dict[str, Any]
        """Fetch the current task record from the vendor API.
        Raise GenAnimError on failure."""
        raise NotImplementedError

    def _task_state(self, task_data):
        # type: (Dict[str, Any]) -> Tuple[str, Optional[str]]
        """Map a vendor task record to (state, error_message) where state
        is one of 'pending', 'running', 'succeeded', 'failed'."""
        raise NotImplementedError

    def _clip_url(self, task_data):
        # type: (Dict[str, Any]) -> Optional[Tuple[str, str]]
        """Extract (download_url, file_extension) from a succeeded task
        record, or None when no clip URL is present."""
        raise NotImplementedError

    def _finalize(self, task_data):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Optional post-poll hook (e.g. DeepMotion's separate download
        endpoint). The default implementation returns the task record
        unchanged."""
        return task_data

    # ------------------------------------------------------------------
    # Shared plumbing
    # ------------------------------------------------------------------

    def _poll_until_done(self, task_id):
        # type: (str) -> Dict[str, Any]
        """
        Poll the vendor task until it reaches a terminal state.

        Poll interval is POLL_INTERVAL_SECONDS (~5s); the overall timeout
        comes from the 'genanim.timeout_seconds' setting (default 240).

        Returns:
            The final (succeeded) task record.

        Raises:
            GenAnimError on task failure or timeout.
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
                raise GenAnimError("Task {} failed: {}".format(
                    task_id, error_message or 'no reason given'))

            if state != last_state:
                _log("[GenAnim] {} task {} is {}...".format(
                    self.name, task_id, state))
                last_state = state

            remaining = deadline - time.time()
            if remaining <= 0:
                raise GenAnimError(
                    "Task {} timed out after {}s (still {})".format(
                        task_id, timeout_seconds, state))

            time.sleep(min(self.POLL_INTERVAL_SECONDS, max(remaining, 0.1)))

    def _download_to_temp(self, url, extension, session=None):
        # type: (str, str, Optional[Any]) -> str
        """
        Stream a clip file download to a named temp file.

        Args:
            url: HTTP(S) download URL.
            extension: File extension including the dot (e.g. '.fbx').
            session: Optional requests.Session carrying auth cookies.

        Returns:
            Absolute path of the downloaded temp file.

        Raises:
            GenAnimError on any download failure.
        """
        requests = self._requests()
        http = session if session is not None else requests

        if not extension:
            extension = '.fbx'
        if not extension.startswith('.'):
            extension = '.' + extension

        try:
            response = http.get(
                url, stream=True, timeout=self.DOWNLOAD_TIMEOUT_SECONDS)
        except Exception as e:
            raise GenAnimError("Clip download failed: {}".format(e))

        if response.status_code != 200:
            raise GenAnimError("Clip download failed with HTTP {}".format(
                response.status_code))

        temp_file = tempfile.NamedTemporaryFile(
            delete=False, prefix='genanim_{}_'.format(self.name),
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
            raise GenAnimError("Clip download interrupted: {}".format(e))

        return temp_file.name

    def _requests(self):
        """Import and return the requests module, or raise GenAnimError."""
        try:
            import requests
            return requests
        except ImportError:
            raise GenAnimError(
                "The 'requests' package is unavailable; cannot call the "
                "{} API".format(self.name))

    def _request_json(self, method, url, headers=None, json_body=None,
                      session=None):
        # type: (str, str, Optional[Dict], Optional[Dict], Optional[Any]) -> Dict[str, Any]
        """
        Perform an HTTP request and parse the JSON response.

        Args:
            session: Optional requests.Session; used instead of the module
                so cookie-authenticated providers (DeepMotion) keep their
                session cookie across calls.

        Raises:
            GenAnimError on transport errors, non-2xx status, or bad JSON.
        """
        requests = self._requests()
        http = session if session is not None else requests
        try:
            response = http.request(
                method, url, headers=headers, json=json_body,
                timeout=self.REQUEST_TIMEOUT_SECONDS)
        except Exception as e:
            raise GenAnimError("{} request to {} failed: {}".format(
                method, url, e))

        if response.status_code < 200 or response.status_code >= 300:
            raise GenAnimError("{} {} returned HTTP {}: {}".format(
                method, url, response.status_code, response.text[:300]))

        try:
            data = response.json()
        except ValueError as e:
            raise GenAnimError("Non-JSON response from {}: {}".format(url, e))

        if not isinstance(data, dict):
            raise GenAnimError("Unexpected response shape from {}".format(url))
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
        """Overall generation timeout ('genanim.timeout_seconds',
        default 240)."""
        value = self._get_setting('genanim.timeout_seconds',
                                  self.DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout = float(value)
            if timeout <= 0:
                raise ValueError("non-positive timeout")
            return timeout
        except (TypeError, ValueError):
            _log_warning("[GenAnim] Invalid genanim.timeout_seconds value "
                         "{!r}; using default {}".format(
                             value, self.DEFAULT_TIMEOUT_SECONDS))
            return float(self.DEFAULT_TIMEOUT_SECONDS)

    @staticmethod
    def _lookup_key(env_var, config_key_name, settings_key_name=None,
                    settings_path=None):
        # type: (str, str, Optional[str], Optional[str]) -> Optional[str]
        """
        Uncached key lookup shared by _resolve_api_key and providers that
        need more than one credential (DeepMotion id + secret):

          1. Environment variable (env_var) - optional override.
          2. Settings UI key (Features tab) via core.settings_manager.
          3. The plugin's config_manager: constructing it loads
             ~/.storyboard_to_3d/.env into the environment, so the env var
             is re-checked, then the 'api.keys.<name>' config entry.

        Args:
            settings_path: Full settings key to read verbatim (e.g.
                'genanim.deepmotion_client_secret'). When omitted, the key
                is 'genanim.<settings_key_name or config_key_name>_api_key'.

        Returns:
            Key string, or None if unavailable. Never raises.
        """
        api_key = os.environ.get(env_var)
        if api_key:
            return api_key

        # Settings UI key (Features tab), e.g. 'genanim.tripo_api_key'.
        # Keyed by provider name when the caller supplies one (the Features
        # tab saves 'genanim.tripo_api_key' while Tripo's config key is
        # 'tripo3d', so formatting config_key_name silently missed).
        # settings_manager imports unreal; guarded so headless use falls
        # through to the config path unchanged.
        try:
            from core.settings_manager import get_setting
            candidate = get_setting(
                settings_path or "genanim.{}_api_key".format(
                    settings_key_name or config_key_name), None)
            if candidate:
                candidate = str(candidate).strip()
                if candidate:
                    return candidate
        except Exception:
            pass

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
                _log_warning("[GenAnim] Could not resolve {} via "
                             "config_manager: {}".format(env_var, e))
                api_key = None
        return api_key

    def _resolve_api_key(self, env_var, config_key_name, settings_path=None):
        # type: (str, str, Optional[str]) -> Optional[str]
        """
        Resolve and cache this provider's primary API key with the same
        pattern core/gen3d/base_provider.py uses (env var override, then
        the Settings UI key, then the plugin config). Never raises.

        Args:
            settings_path: Optional full settings key read verbatim
                (e.g. 'genanim.deepmotion_client_id'); default is the
                provider-name-keyed 'genanim.<name>_api_key'.
        """
        if self._api_key_resolved:
            return self._api_key

        self._api_key_resolved = True
        # Settings-UI lookup is keyed by provider name (self.name) unless
        # the caller supplies a verbatim settings_path (DeepMotion's
        # 'genanim.deepmotion_client_id').
        self._api_key = self._lookup_key(env_var, config_key_name,
                                         settings_key_name=self.name,
                                         settings_path=settings_path)
        return self._api_key

    @staticmethod
    def _extension_from_url(url, default='.fbx'):
        # type: (str, str) -> str
        """Best-effort file extension sniff from a download URL path."""
        try:
            path = str(url).split('?', 1)[0].split('#', 1)[0]
            _root, ext = os.path.splitext(path)
            ext = ext.lower()
            if ext in ('.fbx', '.glb', '.gltf', '.bvh'):
                return ext
        except Exception:
            pass
        return default

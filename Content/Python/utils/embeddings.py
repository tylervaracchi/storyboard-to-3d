# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Shared Embeddings Backend

One provider-agnostic entry point for every feature that needs text
embeddings (semantic asset matching, semantic animation matching):

    from utils.embeddings import get_embedding_backend
    backend = get_embedding_backend()   # or None
    vectors = backend.embed_texts(["a dog", "a chair"])  # or None

Backends (selected via the 'asset_library.embedding_provider' setting;
'auto' is the default and picks the first available in this order):

    openai  - POST https://api.openai.com/v1/embeddings
              model text-embedding-3-small; key from OPENAI_API_KEY,
              then the Settings dialog ('ai_settings.openai_api_key' /
              'ai_settings.api_key'), then config_manager.
    gemini  - POST {v1beta}/models/gemini-embedding-001:batchEmbedContents
              (same API base + x-goog-api-key auth pattern as
              core/ai_providers/gemini_provider.py); key from
              GEMINI_API_KEY / GOOGLE_API_KEY env, then
              'ai_settings.gemini_api_key'.
    ollama  - POST {server}/api/embed (fallback /api/embeddings) on the
              configured local server ('ai_settings.llava_url' /
              'ollama.server_url', default http://localhost:11434) with
              the 'asset_library.ollama_embedding_model' model (default
              'nomic-embed-text'). Availability is a 2s /api/tags probe
              that also requires the embedding model to be installed.

NOTE: Anthropic/Claude has NO embeddings API (their docs point users to
third-party embedding providers), so there is intentionally no 'claude'
backend here. Claude-only users fall back to fuzzy matching; the
matchers log one clear line explaining why.

Every backend's embed_texts() returns one vector per input text (input
order) or None on any failure, logged once, never raised. All HTTP
requests use a 15 second timeout. Each backend exposes a 'namespace'
string ("provider:model") that callers MUST mix into their embedding
cache keys so vectors from different embedding spaces are never
compared against each other.

Importable outside the Unreal Editor (guarded unreal import; 'requests'
is imported inside functions).
"""

import os
from typing import List, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (unit tests, harnesses).
    unreal = None


EMBEDDING_TIMEOUT_SECONDS = 15

OPENAI_EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Same API base + header-auth pattern as core/ai_providers/gemini_provider.py
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
# batchEmbedContents accepts at most 100 requests per call
GEMINI_MAX_BATCH = 100

OLLAMA_DEFAULT_SERVER_URL = "http://localhost:11434"
OLLAMA_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_PROBE_TIMEOUT_SECONDS = 2

VALID_PROVIDERS = ('auto', 'openai', 'gemini', 'ollama')


def _log(message: str) -> None:
    """Log an info message via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(f"[Embeddings] {message}")


def _log_warning(message: str) -> None:
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print(f"[Embeddings] WARNING: {message}")


def _get_setting(path: str, default=None):
    """Read a plugin setting, falling back to the default headlessly."""
    try:
        from core.settings_manager import get_setting
        return get_setting(path, default)
    except Exception:
        return default


# ----------------------------------------------------------------------
# Credential / availability resolution
# ----------------------------------------------------------------------

def _resolve_openai_api_key() -> Optional[str]:
    """
    Resolve the OpenAI API key.

    Order (moved verbatim from core/asset_matcher.py): OPENAI_API_KEY
    environment variable (optional override), then the Settings dialog
    key ('ai_settings.openai_api_key' / 'ai_settings.api_key', guarded
    so headless use falls through), then the plugin's config_manager
    (which also loads the ~/.storyboard_to_3d/.env file).
    """
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        candidate = (_get_setting('ai_settings.openai_api_key', '') or
                     _get_setting('ai_settings.api_key', ''))
        if candidate:
            api_key = str(candidate).strip() or None

    if not api_key:
        try:
            from config.config_manager import get_api_key
            api_key = get_api_key("OpenAI GPT-4 Vision")
        except ImportError:
            try:
                from config_manager import get_api_key
                api_key = get_api_key("OpenAI GPT-4 Vision")
            except ImportError:
                api_key = None
        except Exception as e:
            _log_warning(f"Could not resolve OpenAI API key via "
                         f"config_manager: {e}")
            api_key = None

    return api_key


def _resolve_gemini_api_key() -> Optional[str]:
    """
    Resolve the Gemini API key: GEMINI_API_KEY then GOOGLE_API_KEY env
    vars, then the Settings dialog key ('ai_settings.gemini_api_key') -
    the same order core/ai_providers/gemini_provider.py uses.
    """
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key

    candidate = _get_setting('ai_settings.gemini_api_key', '')
    if candidate:
        return str(candidate).strip() or None
    return None


def _resolve_ollama_server_url() -> str:
    """Resolve the local Ollama server base URL from settings."""
    url = (_get_setting('ai_settings.llava_url', '') or
           _get_setting('ollama.server_url', '') or
           OLLAMA_DEFAULT_SERVER_URL)
    return str(url).rstrip('/')


def _resolve_ollama_embedding_model() -> str:
    """Resolve the Ollama embedding model name from settings."""
    model = _get_setting('asset_library.ollama_embedding_model',
                         OLLAMA_DEFAULT_EMBEDDING_MODEL)
    model = str(model or '').strip()
    return model or OLLAMA_DEFAULT_EMBEDDING_MODEL


def _ollama_available(server_url: str, model: str) -> bool:
    """
    2 second probe: is the Ollama server up AND is the embedding model
    installed (name match, with or without the ':tag' suffix)?
    Never raises.
    """
    try:
        import requests
    except ImportError:
        return False

    try:
        response = requests.get(f"{server_url}/api/tags",
                                timeout=OLLAMA_PROBE_TIMEOUT_SECONDS)
        if response.status_code != 200:
            return False
        installed = [str(entry.get('name', ''))
                     for entry in response.json().get('models', [])
                     if isinstance(entry, dict)]
        base = model.split(':')[0]
        return any(name == model or name.split(':')[0] == base
                   for name in installed)
    except Exception:
        return False


# ----------------------------------------------------------------------
# Backends
# ----------------------------------------------------------------------

class OpenAIEmbeddingBackend:
    """OpenAI /v1/embeddings backend (text-embedding-3-small)."""

    name = 'openai'

    def __init__(self, api_key: str, model: str = OPENAI_EMBEDDING_MODEL):
        self.api_key = api_key
        self.model = model
        self.namespace = f"{self.name}:{self.model}"

    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """One vector per input text (input order), or None on failure."""
        if not texts:
            return []

        try:
            import requests
        except ImportError:
            _log_warning("The 'requests' package is unavailable; "
                         "embeddings disabled")
            return None

        try:
            response = requests.post(
                OPENAI_EMBEDDING_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"model": self.model, "input": texts},
                timeout=EMBEDDING_TIMEOUT_SECONDS
            )

            if response.status_code != 200:
                _log_warning(f"OpenAI embedding request failed with HTTP "
                             f"{response.status_code}: {response.text[:200]}")
                return None

            data = response.json().get("data", [])
            if len(data) != len(texts):
                _log_warning(f"OpenAI embedding response count mismatch: "
                             f"expected {len(texts)}, got {len(data)}")
                return None

            ordered = sorted(data, key=lambda item: item.get("index", 0))
            return [item["embedding"] for item in ordered]
        except Exception as e:
            _log_warning(f"OpenAI embedding request failed: {e}")
            return None


class GeminiEmbeddingBackend:
    """Gemini batchEmbedContents backend (gemini-embedding-001)."""

    name = 'gemini'

    def __init__(self, api_key: str, model: str = GEMINI_EMBEDDING_MODEL):
        self.api_key = api_key
        self.model = model
        self.namespace = f"{self.name}:{self.model}"

    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """One vector per input text (input order), or None on failure."""
        if not texts:
            return []

        try:
            import requests
        except ImportError:
            _log_warning("The 'requests' package is unavailable; "
                         "embeddings disabled")
            return None

        url = f"{GEMINI_API_BASE}/models/{self.model}:batchEmbedContents"
        headers = {
            # Header auth preferred over ?key= so the key never lands in
            # URLs/logs (same choice as core/ai_providers/gemini_provider.py)
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        vectors: List[List[float]] = []
        try:
            for start in range(0, len(texts), GEMINI_MAX_BATCH):
                chunk = texts[start:start + GEMINI_MAX_BATCH]
                body = {
                    "requests": [
                        {
                            "model": f"models/{self.model}",
                            "content": {"parts": [{"text": text}]}
                        }
                        for text in chunk
                    ]
                }
                response = requests.post(url, headers=headers, json=body,
                                         timeout=EMBEDDING_TIMEOUT_SECONDS)

                if response.status_code != 200:
                    _log_warning(f"Gemini embedding request failed with HTTP "
                                 f"{response.status_code}: "
                                 f"{response.text[:200]}")
                    return None

                embeddings = response.json().get("embeddings", [])
                if len(embeddings) != len(chunk):
                    _log_warning(f"Gemini embedding response count mismatch: "
                                 f"expected {len(chunk)}, got "
                                 f"{len(embeddings)}")
                    return None

                for entry in embeddings:
                    values = entry.get("values") if isinstance(entry, dict) else None
                    if not values:
                        _log_warning("Gemini embedding response entry has "
                                     "no 'values'")
                        return None
                    vectors.append(values)

            return vectors
        except Exception as e:
            _log_warning(f"Gemini embedding request failed: {e}")
            return None


class OllamaEmbeddingBackend:
    """Local Ollama embeddings backend (/api/embed, /api/embeddings)."""

    name = 'ollama'

    def __init__(self, server_url: str, model: str):
        self.server_url = server_url.rstrip('/')
        self.model = model
        self.namespace = f"{self.name}:{self.model}"

    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """One vector per input text (input order), or None on failure."""
        if not texts:
            return []

        try:
            import requests
        except ImportError:
            _log_warning("The 'requests' package is unavailable; "
                         "embeddings disabled")
            return None

        # Preferred modern endpoint: /api/embed with a batched 'input'
        # list -> {'embeddings': [[...], ...]}.
        try:
            response = requests.post(
                f"{self.server_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=EMBEDDING_TIMEOUT_SECONDS
            )
            if response.status_code == 200:
                payload = response.json()
                embeddings = payload.get("embeddings")
                if embeddings is None and payload.get("embedding") is not None:
                    # Some servers answer the singular shape here too
                    embeddings = [payload["embedding"]]
                if (isinstance(embeddings, list)
                        and len(embeddings) == len(texts)
                        and all(embeddings)):
                    return embeddings
                _log_warning(f"Ollama /api/embed returned an unexpected "
                             f"shape (expected {len(texts)} embeddings); "
                             f"trying /api/embeddings")
            # Non-200 (e.g. 404 on older Ollama versions): fall through
            # to the legacy endpoint below.
        except Exception as e:
            _log_warning(f"Ollama /api/embed request failed: {e}; "
                         f"trying /api/embeddings")

        # Legacy endpoint: /api/embeddings, one 'prompt' per call
        # -> {'embedding': [...]}.
        try:
            vectors: List[List[float]] = []
            for text in texts:
                response = requests.post(
                    f"{self.server_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=EMBEDDING_TIMEOUT_SECONDS
                )
                if response.status_code != 200:
                    _log_warning(f"Ollama embedding request failed with HTTP "
                                 f"{response.status_code}: "
                                 f"{response.text[:200]}")
                    return None
                payload = response.json()
                vector = payload.get("embedding")
                if vector is None and payload.get("embeddings"):
                    # Singular endpoint answering the plural shape
                    vector = payload["embeddings"][0]
                if not vector:
                    _log_warning("Ollama embedding response has no "
                                 "'embedding' vector")
                    return None
                vectors.append(vector)
            return vectors
        except Exception as e:
            _log_warning(f"Ollama embedding request failed: {e}")
            return None


# ----------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------

def get_embedding_backend(provider: Optional[str] = None):
    """
    Build the configured embeddings backend, or None when unavailable.

    Args:
        provider: Optional explicit provider name ('openai', 'gemini',
            'ollama', 'auto'). When None, the
            'asset_library.embedding_provider' setting is read
            (default 'auto').

    Returns:
        A backend object with .name, .model, .namespace and
        .embed_texts(list[str]) -> list[vector] | None, or None when no
        provider has credentials/availability. Never raises.

    'auto' picks the first available in order: OpenAI (API key found),
    Gemini (API key found), Ollama (2s /api/tags probe succeeds and the
    embedding model is installed). Anthropic/Claude offers no
    embeddings API, so a Claude-only setup yields None here and callers
    degrade to fuzzy matching.
    """
    if provider is None:
        provider = _get_setting('asset_library.embedding_provider', 'auto')
    provider = str(provider or 'auto').strip().lower()
    if provider not in VALID_PROVIDERS:
        _log_warning(f"Unknown embedding provider '{provider}'; "
                     f"treating as 'auto'")
        provider = 'auto'

    try:
        if provider in ('auto', 'openai'):
            api_key = _resolve_openai_api_key()
            if api_key:
                return OpenAIEmbeddingBackend(api_key)
            if provider == 'openai':
                _log_warning("Embedding provider 'openai' selected but no "
                             "OpenAI API key was found")
                return None

        if provider in ('auto', 'gemini'):
            api_key = _resolve_gemini_api_key()
            if api_key:
                return GeminiEmbeddingBackend(api_key)
            if provider == 'gemini':
                _log_warning("Embedding provider 'gemini' selected but no "
                             "Gemini API key was found (GEMINI_API_KEY / "
                             "GOOGLE_API_KEY / ai_settings.gemini_api_key)")
                return None

        if provider in ('auto', 'ollama'):
            server_url = _resolve_ollama_server_url()
            model = _resolve_ollama_embedding_model()
            if _ollama_available(server_url, model):
                return OllamaEmbeddingBackend(server_url, model)
            if provider == 'ollama':
                _log_warning(f"Embedding provider 'ollama' selected but "
                             f"{server_url} is unreachable or the "
                             f"'{model}' model is not installed "
                             f"(try: ollama pull {model})")
                return None
    except Exception as e:
        # Belt and braces: selection must never break matching.
        _log_warning(f"Embedding backend selection failed: {e}")
        return None

    return None

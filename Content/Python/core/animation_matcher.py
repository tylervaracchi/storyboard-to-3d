# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Animation Matcher Module

Matches action text from storyboard analysis ("running", "sits on the
bench") to animation assets, mirroring AssetMatcher's difflib pattern.

Library file convention mirrors asset libraries: a per-show
'animation_library.json' stored next to the show's 'asset_library.json'
(<shows_root>/<show>/animation_library.json), with a repository fallback
at samples/animation_library.sample.json (placeholder paths).

Schema:
    {
      "animations": {
        "idle": {"asset_path": "/Game/...", "aliases": ["standing", "waiting"]}
      }
    }

Feature is opt-in: SceneBuilder only uses this when the
'scene.auto_animation' setting is truthy (default off). Nothing here
raises to callers; every miss returns None/False with a logged reason.

Optionally (also off by default) performs semantic matching via OpenAI
embeddings, mirroring core/asset_matcher.py: when the
'asset_library.semantic_matching' setting is truthy AND an OpenAI API
key is available, each animation's 'key. description. aliases' text is
embedded (cached to ~/.storyboard_to_3d/anim_embedding_cache.json) and
the query action text is cosine-matched at >= 0.5. The tier runs
between the alias containment stage and the difflib fuzzy stage; every
failure inside falls through to the fuzzy stage unchanged.

Optionally (also off by default) calls a generative text-to-animation
provider (Tripo animate_retarget or DeepMotion SayMotion, see
core/genanim) when no library clip matches the action text: the clip is
generated, imported into /Game/StoryboardTo3D/GeneratedAnims, registered
in the in-memory library and the show's animation_library.json, and
returned. Enabled via the 'genanim.enabled' setting; every failure in
that path logs and returns None exactly as the plain miss does today.
"""

import hashlib
import json
import math
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (e.g. unit tests of the
    # matching logic). Editor-dependent features are skipped.
    unreal = None


FUZZY_THRESHOLD = 0.6
# core/animation_matcher.py -> Content/Python/core; repo root is 3 levels up
SAMPLE_LIBRARY_PATH = (Path(__file__).resolve().parents[3]
                       / 'samples' / 'animation_library.sample.json')

# Generative text-to-animation configuration (see core/genanim)
GENANIM_DEFAULT_MAX_PER_RUN = 2

# Optional semantic (embedding) tier, mirroring core/asset_matcher.py.
# Active only when 'asset_library.semantic_matching' is truthy and an
# OpenAI API key exists; otherwise the tier is a no-op.
ANIM_EMBEDDING_MODEL = "text-embedding-3-small"
ANIM_EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"
ANIM_EMBEDDING_TIMEOUT_SECONDS = 15
ANIM_SEMANTIC_THRESHOLD = 0.5
ANIM_EMBEDDING_BATCH_SIZE = 100
ANIM_QUERY_EMBEDDING_CACHE_MAX = 128
ANIM_EMBEDDING_CACHE_FILE = (Path.home() / ".storyboard_to_3d"
                             / "anim_embedding_cache.json")


def _log(message):
    """Log info via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print("[AnimationMatcher] {0}".format(message))


def _log_warning(message):
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("[AnimationMatcher] WARNING: {0}".format(message))


class AnimationMatcher:
    """
    Matches action text to animation asset paths and applies them to
    SkeletalMeshActors in single-node (looping) playback mode.

    Example:
        >>> matcher = AnimationMatcher(show_name="MyShow")
        >>> path = matcher.find_animation("the hero is running away")
        >>> if path:
        ...     matcher.apply_animation_to_actor(actor, path)
    """

    def __init__(self, show_name: Optional[str] = None):
        self.show_name = show_name
        self.animations: Dict[str, Dict[str, Any]] = {}
        self.library_path: Optional[Path] = None
        # Generative text-to-animation: per-matcher-instance attempt
        # counter, enforced against the 'genanim.max_per_run' setting.
        self._genanim_generation_count: int = 0
        # Semantic (embedding) tier state, built lazily on the first
        # query so library-only usage never touches the network. The
        # index size is remembered so newly registered (generated)
        # entries trigger a rebuild.
        self._anim_semantic_index: List[Tuple[str, str, List[float]]] = []
        self._anim_semantic_index_size: int = -1
        self._anim_embedding_cache: Dict[str, List[float]] = {}
        self._anim_query_embedding_cache: Dict[str, List[float]] = {}
        self._openai_api_key: Optional[str] = None
        self._openai_api_key_resolved: bool = False
        self._load_library()

    def _show_library_path(self) -> Optional[Path]:
        """Resolve the per-show animation library path, or None."""
        if not self.show_name:
            return None
        try:
            from core.shows_manager import ShowsManager
            manager = ShowsManager()
            return Path(manager.shows_root) / self.show_name / 'animation_library.json'
        except Exception as e:
            _log_warning("Could not resolve show directory for animation "
                         "library: {0}".format(e))
            return None

    def _load_library(self) -> None:
        """Load the first usable library: show file, then samples fallback."""
        candidates = []
        show_path = self._show_library_path()
        if show_path is not None:
            candidates.append(show_path)
        candidates.append(SAMPLE_LIBRARY_PATH)

        for path in candidates:
            try:
                if not path.exists():
                    continue
                with open(str(path), 'r') as f:
                    data = json.load(f)
                animations = data.get('animations') if isinstance(data, dict) else None
                if isinstance(animations, dict) and animations:
                    self.animations = animations
                    self.library_path = path
                    _log("Loaded animation library ({0} entries) from {1}".format(
                        len(animations), path))
                    return
                _log_warning("Animation library at {0} has no 'animations' "
                             "entries; skipping".format(path))
            except Exception as e:
                _log_warning("Failed to load animation library {0}: {1}".format(path, e))

        _log("No animation library found (looked for a show "
             "'animation_library.json' and the samples fallback); "
             "find_animation will return None")

    def find_animation(self, action_text: str) -> Optional[str]:
        """
        Find the best animation asset path for free action text.

        Order: exact key match, alias/key containment in the text, the
        optional semantic (embedding) match (off by default; cosine
        >= 0.5 against 'key. description. aliases' texts), then difflib
        fuzzy match (ratio >= 0.6) against keys and aliases, then the
        optional generative fallback (off by default; see core/genanim).

        Args:
            action_text: Free-form action/description text.

        Returns:
            Asset path string, or None when nothing matches.
        """
        if not action_text or not isinstance(action_text, str):
            return None
        text = action_text.strip().lower()
        if not text:
            return None
        if not self.animations:
            # Empty library: skip the lookup tiers (1-4) but still reach the
            # tier-5 generative fallback - it exists precisely for shows with
            # no animation library ('genanim.enabled' gates it internally).
            return self._generative_animation(action_text)

        # 1. Exact key match (also with punctuation normalized to '_')
        compact = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
        for key in (text, compact):
            entry = self.animations.get(key)
            if isinstance(entry, dict) and entry.get('asset_path'):
                _log("Matched action '{0}' to animation '{1}' (exact)".format(
                    action_text, key))
                return entry['asset_path']

        tokens = set(t for t in re.split(r'[^a-z0-9]+', text) if t)

        # 2. Alias / key containment in the action text
        for key, entry in self.animations.items():
            if not isinstance(entry, dict):
                continue
            asset_path = entry.get('asset_path')
            if not asset_path:
                continue
            aliases = entry.get('aliases') or []
            names = [key] + [str(a) for a in aliases]
            for candidate in names:
                cand = candidate.strip().lower()
                if not cand:
                    continue
                if cand == text or cand in tokens or (len(cand) > 3 and cand in text):
                    _log("Matched action '{0}' to animation '{1}' via "
                         "'{2}'".format(action_text, key, candidate))
                    return asset_path

        # 3. Semantic (embedding) match, optional and off by default.
        # Mirrors asset_matcher's embedding tier; every failure inside
        # returns None so the difflib tier below runs unchanged.
        semantic_path = self._semantic_match(text)
        if semantic_path:
            return semantic_path

        # 4. Fuzzy match with difflib (whole text and per-token)
        best_path = None
        best_key = None
        best_score = 0.0
        for key, entry in self.animations.items():
            if not isinstance(entry, dict):
                continue
            asset_path = entry.get('asset_path')
            if not asset_path:
                continue
            names = [key] + [str(a) for a in (entry.get('aliases') or [])]
            for candidate in names:
                cand = candidate.strip().lower()
                if not cand:
                    continue
                score = SequenceMatcher(None, text, cand).ratio()
                for token in tokens:
                    # Short tokens ('all', 'is') create false positives in
                    # the fuzzy pass; short keys/aliases are already caught
                    # by the exact and containment stages above.
                    if len(token) < 4:
                        continue
                    token_score = SequenceMatcher(None, token, cand).ratio()
                    if token_score > score:
                        score = token_score
                if score > best_score:
                    best_score = score
                    best_path = asset_path
                    best_key = key

        if best_path and best_score >= FUZZY_THRESHOLD:
            _log("Fuzzy matched action '{0}' to animation '{1}' "
                 "(score {2:.2f})".format(action_text, best_key, best_score))
            return best_path

        _log("No animation match for action '{0}' (best score "
             "{1:.2f})".format(action_text, best_score))

        # 5. Generative fallback (optional, off by default; see
        # core/genanim). Every failure inside returns None, so callers
        # see exactly the legacy miss behavior.
        return self._generative_animation(action_text)

    # ------------------------------------------------------------------
    # Semantic (embedding) tier (optional; mirrors core/asset_matcher.py)
    # ------------------------------------------------------------------

    def _get_openai_api_key(self) -> Optional[str]:
        """
        Resolve the OpenAI API key from the environment or config_manager.

        Same pattern as core/asset_matcher.py: environment variable
        first, then the plugin's config_manager (which also loads the
        ~/.storyboard_to_3d/.env file into the environment).

        Returns:
            API key string, or None if unavailable.
        """
        if self._openai_api_key_resolved:
            return self._openai_api_key

        self._openai_api_key_resolved = True
        api_key = os.environ.get("OPENAI_API_KEY")

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
                _log_warning("Could not resolve OpenAI API key via "
                             "config_manager: {0}".format(e))
                api_key = None

        self._openai_api_key = api_key
        return api_key

    def _is_semantic_matching_enabled(self) -> bool:
        """
        Check whether the embedding tier should be active.

        Requires the 'asset_library.semantic_matching' setting to be
        truthy AND an OpenAI API key to be available (the same switch
        core/asset_matcher.py uses, so one toggle governs both).

        Returns:
            True only when both the setting and the API key are present.
        """
        enabled = None
        try:
            from core.settings_manager import get_setting
            value = get_setting('asset_library.semantic_matching', None)
            if value is not None:
                enabled = bool(value)
        except Exception as e:
            _log_warning("Could not read 'asset_library.semantic_matching' "
                         "via settings_manager: {0}".format(e))
            enabled = None

        if enabled is None:
            enabled = False
            try:
                from config.config_manager import get_config
                cfg = get_config()
                enabled = bool(cfg.get("asset_library.semantic_matching",
                                       cfg.get("semantic_matching", False)))
            except ImportError:
                try:
                    from config_manager import get_config
                    cfg = get_config()
                    enabled = bool(cfg.get("asset_library.semantic_matching",
                                           cfg.get("semantic_matching", False)))
                except ImportError:
                    enabled = False
            except Exception as e:
                _log_warning("Could not read semantic_matching setting: "
                             "{0}".format(e))
                enabled = False

        if not enabled:
            return False

        if not self._get_openai_api_key():
            _log("Semantic animation matching is enabled but no OpenAI API "
                 "key was found; skipping the embedding tier")
            return False

        return True

    def _get_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Request embedding vectors for a list of texts from the OpenAI API.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input, in input order),
            or None on any failure (logged, never raised).
        """
        if not texts:
            return []

        api_key = self._get_openai_api_key()
        if not api_key:
            _log_warning("No OpenAI API key available for embedding request")
            return None

        try:
            import requests
        except ImportError:
            _log_warning("The 'requests' package is unavailable; semantic "
                         "animation matching disabled")
            return None

        try:
            response = requests.post(
                ANIM_EMBEDDING_ENDPOINT,
                headers={
                    "Authorization": "Bearer {0}".format(api_key),
                    "Content-Type": "application/json"
                },
                json={"model": ANIM_EMBEDDING_MODEL, "input": texts},
                timeout=ANIM_EMBEDDING_TIMEOUT_SECONDS
            )

            if response.status_code != 200:
                _log_warning("Embedding request failed with HTTP {0}: "
                             "{1}".format(response.status_code,
                                          response.text[:200]))
                return None

            data = response.json().get("data", [])
            if len(data) != len(texts):
                _log_warning("Embedding response count mismatch: expected "
                             "{0}, got {1}".format(len(texts), len(data)))
                return None

            ordered = sorted(data, key=lambda item: item.get("index", 0))
            return [item["embedding"] for item in ordered]
        except Exception as e:
            _log_warning("Embedding request failed: {0}".format(e))
            return None

    @staticmethod
    def _hash_text(text: str) -> str:
        """Return a stable hash key for an embedding text."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Compute cosine similarity between two vectors in pure Python.

        Returns:
            Cosine similarity in [-1.0, 1.0], or 0.0 for invalid input.
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for a, b in zip(vec_a, vec_b):
            dot += a * b
            norm_a += a * a
            norm_b += b * b

        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0

        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    def _load_anim_embedding_cache(self) -> Dict[str, List[float]]:
        """Load the persisted embedding cache from disk; empty on failure."""
        try:
            if ANIM_EMBEDDING_CACHE_FILE.exists():
                with open(str(ANIM_EMBEDDING_CACHE_FILE), 'r') as f:
                    cached = json.load(f)
                if isinstance(cached, dict):
                    return cached
        except Exception as e:
            _log_warning("Failed to load animation embedding cache: "
                         "{0}".format(e))
        return {}

    def _save_anim_embedding_cache(self) -> None:
        """Persist the embedding cache to disk so re-runs are free."""
        try:
            ANIM_EMBEDDING_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(str(ANIM_EMBEDDING_CACHE_FILE), 'w') as f:
                json.dump(self._anim_embedding_cache, f)
        except Exception as e:
            _log_warning("Failed to save animation embedding cache: "
                         "{0}".format(e))

    @staticmethod
    def _entry_embed_text(key: str, entry: Dict[str, Any]) -> str:
        """Compose the 'key. description. aliases' text for one entry."""
        description = str(entry.get('description') or '').strip()
        aliases = entry.get('aliases') or []
        alias_text = ', '.join(str(a).strip() for a in aliases
                               if str(a).strip())
        parts = [str(key).strip(), description, alias_text]
        return '. '.join(p for p in parts if p)

    def _build_anim_semantic_index(self) -> None:
        """
        Build the in-memory (key, asset_path, vector) index for the
        current library. Reuses vectors from the persisted cache (keyed
        by text hash) and only requests embeddings for texts not yet
        cached, in batches. Failures leave the index partial or empty;
        matching then falls through to the fuzzy tier.
        """
        self._anim_semantic_index = []
        self._anim_semantic_index_size = len(self.animations)

        entries: List[Tuple[str, str, str]] = []
        for key, entry in self.animations.items():
            if not isinstance(entry, dict):
                continue
            asset_path = entry.get('asset_path')
            if not asset_path:
                continue
            entries.append((key, asset_path, self._entry_embed_text(key, entry)))

        if not entries:
            return

        self._anim_embedding_cache = self._load_anim_embedding_cache()

        missing: List[Tuple[str, str]] = []
        seen_hashes = set()
        for _key, _asset_path, embed_text in entries:
            text_hash = self._hash_text(embed_text)
            if (text_hash not in self._anim_embedding_cache
                    and text_hash not in seen_hashes):
                missing.append((text_hash, embed_text))
                seen_hashes.add(text_hash)

        if missing:
            _log("Requesting embeddings for {0} new animation "
                 "texts".format(len(missing)))
            for start in range(0, len(missing), ANIM_EMBEDDING_BATCH_SIZE):
                batch = missing[start:start + ANIM_EMBEDDING_BATCH_SIZE]
                vectors = self._get_embeddings([text for _h, text in batch])
                if vectors is None:
                    _log_warning("Embedding batch failed; animation semantic "
                                 "index will be partial")
                    break
                for (text_hash, _text), vector in zip(batch, vectors):
                    self._anim_embedding_cache[text_hash] = vector
            self._save_anim_embedding_cache()

        for key, asset_path, embed_text in entries:
            vector = self._anim_embedding_cache.get(self._hash_text(embed_text))
            if vector:
                self._anim_semantic_index.append((key, asset_path, vector))

        _log("Animation semantic index built with {0} entries".format(
            len(self._anim_semantic_index)))

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Get the embedding for a query string, with a small cache."""
        if query in self._anim_query_embedding_cache:
            return self._anim_query_embedding_cache[query]

        vectors = self._get_embeddings([query])
        if not vectors:
            return None

        vector = vectors[0]
        if len(self._anim_query_embedding_cache) >= ANIM_QUERY_EMBEDDING_CACHE_MAX:
            # Drop the oldest entry (insertion order) to bound memory use
            self._anim_query_embedding_cache.pop(
                next(iter(self._anim_query_embedding_cache)))
        self._anim_query_embedding_cache[query] = vector
        return vector

    def _semantic_match(self, action_text: str) -> Optional[str]:
        """
        Find an animation by embedding similarity to the action text.

        Args:
            action_text: Lowercase action text that missed the exact and
                containment tiers.

        Returns:
            Asset path when the best cosine similarity clears
            ANIM_SEMANTIC_THRESHOLD, otherwise None. Never raises; any
            failure is logged and returns None so callers fall through
            to the difflib fuzzy tier unchanged.
        """
        try:
            if not self.animations:
                return None
            if not self._is_semantic_matching_enabled():
                return None

            # Rebuild lazily, and again whenever the library grew (for
            # example after a generated clip was registered).
            if self._anim_semantic_index_size != len(self.animations):
                self._build_anim_semantic_index()
            if not self._anim_semantic_index:
                return None

            query_vector = self._get_query_embedding(action_text)
            if not query_vector:
                return None

            best_key = None
            best_path = None
            best_score = 0.0
            for key, asset_path, vector in self._anim_semantic_index:
                score = self._cosine_similarity(query_vector, vector)
                if score > best_score:
                    best_score = score
                    best_key = key
                    best_path = asset_path

            if best_path and best_score >= ANIM_SEMANTIC_THRESHOLD:
                _log("Semantic matched action '{0}' to animation '{1}' "
                     "(similarity {2:.2f})".format(
                         action_text, best_key, best_score))
                return best_path

            if best_key:
                _log("Semantic best candidate '{0}' for '{1}' below "
                     "threshold ({2:.2f} < {3})".format(
                         best_key, action_text, best_score,
                         ANIM_SEMANTIC_THRESHOLD))
            return None
        except Exception as e:
            _log_warning("Semantic animation matching failed for '{0}': {1}; "
                         "falling back to fuzzy matching".format(
                             action_text, e))
            return None

    # ------------------------------------------------------------------
    # Generative text-to-animation fallback (optional; see core/genanim)
    # ------------------------------------------------------------------

    def _get_genanim_max_per_run(self) -> int:
        """
        Read the per-run generation budget ('genanim.max_per_run',
        default 2).

        Returns:
            Non-negative integer budget; the default on any failure.
        """
        try:
            from core.settings_manager import get_setting
            value = get_setting('genanim.max_per_run',
                                GENANIM_DEFAULT_MAX_PER_RUN)
            return max(0, int(value))
        except Exception as e:
            _log_warning("[GenAnim] Could not read 'genanim.max_per_run': "
                         "{0}; using default {1}".format(
                             e, GENANIM_DEFAULT_MAX_PER_RUN))
            return GENANIM_DEFAULT_MAX_PER_RUN

    def _generative_animation(self, action_text: str) -> Optional[str]:
        """
        Generate an animation clip for unmatched action text via
        core/genanim.

        Runs only when 'genanim.enabled' is truthy and the configured
        provider is fully set up (genanim_factory.get_configured()
        returns None otherwise, making this a no-op by default). Checks
        the reuse manifest first, then enforces the per-run budget, then
        generates, imports, and registers the new clip in the in-memory
        library and the show's animation_library.json so later panels
        match it via the normal tiers.

        Args:
            action_text: The action text that failed all match tiers.

        Returns:
            Imported asset path, or None. Never raises; every failure
            logs and returns None so callers see the plain miss behavior.
        """
        try:
            from core.genanim import genanim_factory
        except ImportError:
            # Package not present; keep the legacy behavior silently.
            return None

        try:
            provider = genanim_factory.get_configured()
        except Exception as e:
            _log_warning("[GenAnim] Provider configuration failed: "
                         "{0}".format(e))
            return None

        if provider is None:
            return None

        provider_name = getattr(provider, 'name', 'unknown')

        # (a) Reuse a previously generated clip when possible.
        cached_path = None
        try:
            from core.genanim import manifest as genanim_manifest
            cached_path = genanim_manifest.lookup(action_text)
        except Exception as e:
            _log_warning("[GenAnim] Manifest lookup failed: {0}".format(e))

        if cached_path:
            _log("[GenAnim] Reusing previously generated animation for "
                 "'{0}': {1}".format(action_text, cached_path))
            self._register_generated_animation(action_text, cached_path,
                                               provider_name)
            return cached_path

        # (b) Per-run generation budget (counts attempts, so repeated
        # failures cannot spiral costs or stall a batch).
        max_per_run = self._get_genanim_max_per_run()
        if self._genanim_generation_count >= max_per_run:
            _log("[GenAnim] Skipping generation for '{0}': per-run budget "
                 "of {1} exhausted (genanim.max_per_run)".format(
                     action_text, max_per_run))
            return None

        # (c) Generate, import, register, record.
        self._genanim_generation_count += 1
        try:
            result = provider.generate(action_text)
        except Exception as e:
            # provider.generate() should never raise; belt and braces.
            _log_warning("[GenAnim] Generation failed for '{0}': "
                         "{1}".format(action_text, e))
            return None

        if (not isinstance(result, dict)
                or result.get('status') != 'succeeded'
                or not result.get('file_path')):
            error = 'unknown error'
            if isinstance(result, dict):
                error = result.get('error', error)
            _log_warning("[GenAnim] Generation failed for '{0}': "
                         "{1}".format(action_text, error))
            return None

        try:
            from core.genanim.importer import (import_generated_animation,
                                               sanitize_asset_name)
            asset_name = sanitize_asset_name(action_text)[:60]
            asset_path = import_generated_animation(result['file_path'],
                                                    asset_name)
        except Exception as e:
            _log_warning("[GenAnim] Import failed for '{0}': {1}".format(
                action_text, e))
            return None

        if not asset_path:
            _log_warning("[GenAnim] Import produced no asset for "
                         "'{0}'".format(action_text))
            return None

        self._register_generated_animation(action_text, asset_path,
                                           provider_name)

        try:
            from core.genanim import manifest as genanim_manifest
            genanim_manifest.record(action_text, asset_path, provider_name)
        except Exception as e:
            _log_warning("[GenAnim] Failed to record manifest entry: "
                         "{0}".format(e))

        _log("[GenAnim] Generated and imported animation for '{0}' via "
             "{1}: {2}".format(action_text, provider_name, asset_path))
        return asset_path

    def _register_generated_animation(self, action_text: str,
                                      asset_path: str,
                                      provider_name: str) -> None:
        """
        Register a generated clip in the in-memory library (so later
        lookups in this run match it via the normal tiers) and persist it
        to the show's animation_library.json (so future runs match it
        without regenerating). Never raises.

        Args:
            action_text: Action text the clip was generated for.
            asset_path: Imported asset path in the project.
            provider_name: Provider that generated the clip.
        """
        try:
            key = re.sub(r'[^a-z0-9]+', '_',
                         action_text.strip().lower()).strip('_')[:60]
            if not key:
                key = 'generated_animation'
            entry = {
                'asset_path': str(asset_path),
                'aliases': [action_text.strip().lower()],
                'source': str(provider_name or 'unknown'),
                'generated': True
            }
            self.animations[key] = entry
        except Exception as e:
            _log_warning("[GenAnim] Could not register generated animation "
                         "in memory: {0}".format(e))
            return

        self._persist_generated_animation(key, entry)

    def _persist_generated_animation(self, key: str,
                                     entry: Dict[str, Any]) -> None:
        """
        Append a generated-clip entry to the show's
        animation_library.json (created if missing), preserving every
        other key in the file. Skipped with a log when no show is set.
        Never raises.
        """
        try:
            show_path = self._show_library_path()
            if show_path is None:
                _log("[GenAnim] No show set; generated animation '{0}' not "
                     "persisted to a library file".format(key))
                return

            data: Dict[str, Any] = {}
            if show_path.exists():
                try:
                    with open(str(show_path), 'r') as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception as e:
                    _log_warning("[GenAnim] Could not read {0} ({1}); not "
                                 "overwriting it".format(show_path, e))
                    return

            animations = data.get('animations')
            if not isinstance(animations, dict):
                animations = {}
                data['animations'] = animations
            animations[key] = entry

            show_path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(show_path), 'w') as f:
                json.dump(data, f, indent=2)
            _log("[GenAnim] Recorded '{0}' in {1}".format(key, show_path))
        except Exception as e:
            _log_warning("[GenAnim] Could not persist generated animation "
                         "'{0}': {1}".format(key, e))

    def _load_asset(self, asset_path: str) -> Optional[Any]:
        """Load an asset via EditorAssetSubsystem, EditorAssetLibrary fallback."""
        if unreal is None:
            _log_warning("unreal unavailable; cannot load '{0}'".format(asset_path))
            return None
        try:
            if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorAssetSubsystem'):
                subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
                if subsystem is not None:
                    return subsystem.load_asset(asset_path)
            if hasattr(unreal, 'EditorAssetLibrary'):
                _log_warning("EditorAssetSubsystem unavailable; falling back "
                             "to EditorAssetLibrary")
                return unreal.EditorAssetLibrary.load_asset(asset_path)
            _log_warning("No editor asset access API available")
        except Exception as e:
            _log_warning("Failed to load animation asset {0}: {1}".format(asset_path, e))
        return None

    def apply_animation_to_actor(self, actor: Any, anim_asset_path: str) -> bool:
        """
        Play an animation asset on a SkeletalMeshActor (single node, looping).

        Args:
            actor: Actor (or spawnable object template) to animate. Anything
                that is not a SkeletalMeshActor is skipped with a log.
            anim_asset_path: Asset path of the animation to play.

        Returns:
            True when the animation was set and playback started;
            False (with a logged reason) on any miss. Never raises.
        """
        try:
            if unreal is None:
                _log_warning("unreal unavailable; cannot apply animation")
                return False
            if actor is None or not anim_asset_path:
                _log_warning("apply_animation_to_actor called with missing "
                             "actor or asset path")
                return False
            if not hasattr(unreal, 'SkeletalMeshActor'):
                _log_warning("SkeletalMeshActor class unavailable in this "
                             "engine version; skipping animation")
                return False
            if not isinstance(actor, unreal.SkeletalMeshActor):
                _log("Actor is not a SkeletalMeshActor; skipping animation "
                     "'{0}'".format(anim_asset_path))
                return False

            asset = self._load_asset(anim_asset_path)
            if asset is None:
                _log_warning("Animation asset not found: {0} (placeholder "
                             "path? see samples/animation_library.sample.json)".format(
                                 anim_asset_path))
                return False

            component = None
            if hasattr(actor, 'skeletal_mesh_component'):
                component = actor.skeletal_mesh_component
            if component is None and hasattr(actor, 'get_component_by_class') \
                    and hasattr(unreal, 'SkeletalMeshComponent'):
                component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            if component is None:
                _log_warning("No SkeletalMeshComponent found on actor; "
                             "cannot apply '{0}'".format(anim_asset_path))
                return False

            if hasattr(unreal, 'AnimationMode') and hasattr(component, 'set_animation_mode'):
                component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            else:
                _log_warning("AnimationMode/set_animation_mode unavailable; "
                             "continuing without explicit mode switch")

            if not hasattr(component, 'set_animation'):
                _log_warning("set_animation unavailable on component; "
                             "cannot apply '{0}'".format(anim_asset_path))
                return False
            # A skeleton mismatch raises here; caught by the outer except
            component.set_animation(asset)

            if hasattr(component, 'play'):
                component.play(True)  # looping
            elif hasattr(component, 'set_playing'):
                component.set_playing(True)
            else:
                _log_warning("No play/set_playing on component; animation "
                             "set but playback not started")

            _log("Applied animation '{0}' (looping)".format(anim_asset_path))
            return True

        except Exception as e:
            _log_warning("Failed to apply animation '{0}': {1} "
                         "(skeleton mismatch?)".format(anim_asset_path, e))
            return False

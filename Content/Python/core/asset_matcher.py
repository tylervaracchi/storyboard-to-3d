# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Asset Matcher Module

Matches object names from storyboard analysis to Unreal Engine assets.
Prioritizes show-specific asset libraries, then falls back to general project
assets and basic shapes.

Optionally performs semantic matching via text embeddings so that related
terms (e.g. 'canine' or 'pup') can find a 'dog' asset. Semantic matching is
disabled by default; it activates only when the 'semantic_matching' setting
is truthy AND an embeddings backend is available (OpenAI, Gemini, or local
Ollama - see utils/embeddings.py; Anthropic/Claude has no embeddings API).
On any failure it falls back to the existing fuzzy matching, so
out-of-the-box behavior is unchanged.

Optionally (also off by default) calls a generative text-to-3D provider
(Meshy or Tripo3D, see core/gen3d) when every matching tier has failed,
so missing entities get a real generated mesh instead of a basic shape.
Enabled via the 'gen3d.enabled' setting; every failure in that path logs
and falls through to the existing basic-shape fallback unchanged.
"""

import json
import math
import os
import hashlib
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, List, Tuple

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (e.g. unit tests of the
    # semantic matching logic). Editor-dependent features are skipped.
    unreal = None

# Shared multi-provider embeddings backend (OpenAI / Gemini / Ollama).
# Guarded so this module still imports if utils/ is not on sys.path.
try:
    from utils.embeddings import get_embedding_backend
except ImportError:
    get_embedding_backend = None


# Semantic matching configuration (model/endpoint/timeout now live in
# utils/embeddings.py, shared across all embedding consumers)
SEMANTIC_MATCH_THRESHOLD = 0.55
EMBEDDING_BATCH_SIZE = 100
QUERY_EMBEDDING_CACHE_MAX = 128
EMBEDDING_CACHE_FILE = Path.home() / ".storyboard_to_3d" / "embedding_cache.json"

# Generative text-to-3D configuration (see core/gen3d)
GEN3D_DEFAULT_MAX_PER_RUN = 3


def _log(message: str) -> None:
    """Log an info message via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(f"[AssetMatcher] {message}")


def _log_warning(message: str) -> None:
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print(f"[AssetMatcher] WARNING: {message}")


def _get_editor_asset_subsystem():
    """Get the EditorAssetSubsystem, replacing the deprecated EditorAssetLibrary."""
    if unreal is None:
        raise RuntimeError("Unreal module is not available outside the editor")

    if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorAssetSubsystem'):
        return unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

    # Fallback for older engine versions where the subsystem is unavailable
    if hasattr(unreal, 'EditorAssetLibrary'):
        _log_warning("EditorAssetSubsystem unavailable; falling back to EditorAssetLibrary")
        return unreal.EditorAssetLibrary

    raise RuntimeError("No editor asset access API available in this engine version")


class AssetMatcher:
    """
    Matches object names to Unreal Engine assets with show-specific priority.

    The matching priority order is:
        1. Show-specific asset library (exact match, aliases, description)
        2. General project asset cache (exact match)
        3. Semantic matching via text embeddings (optional, off by default;
           OpenAI, Gemini, or local Ollama via utils/embeddings.py)
        4. Fuzzy matching in general cache
        5. Generative text-to-3D (optional, off by default; see core/gen3d)
        6. Fallback to basic shapes

    Attributes:
        show_name: Name of the current show for library lookup.
        show_library: Loaded show-specific asset definitions.
        asset_cache: Cache of general project assets.
        embedding_cache: Persisted text-hash to embedding-vector cache.

    Example:
        >>> matcher = AssetMatcher(show_name="MyShow")
        >>> asset = matcher.find_best_match("hero_character", category="characters")
    """

    def __init__(self, show_name: Optional[str] = None):
        """
        Initialize the asset matcher.

        Args:
            show_name: Optional show name to load show-specific asset library.
        """
        self.show_name = show_name
        self.show_library: Dict[str, Dict] = {}
        self.asset_cache: Dict[str, str] = {}

        # Semantic matching state
        self.embedding_cache: Dict[str, List[float]] = {}
        self._semantic_enabled: bool = False
        self._semantic_index: List[Tuple[str, str, List[float]]] = []
        self._query_embedding_cache: Dict[str, List[float]] = {}
        self._embedding_backend: Optional[Any] = None
        self._embedding_backend_resolved: bool = False

        # Generative text-to-3D: per-matcher-instance attempt counter,
        # enforced against the 'gen3d.max_per_run' setting.
        self._gen3d_generation_count: int = 0
        # Entities whose cached STATIC generation was already retried with
        # rigging this run (a rig-refusing model must not loop costs).
        self._rig_retry_attempted: set = set()
        # entity name (lower) -> vendor rig task id from the auto-rig
        # chain; callers persist it so per-character animation retargeting
        # (genanim) can drive this exact character later.
        self.last_rig_task_ids: Dict[str, str] = {}

        if show_name:
            self.load_show_library(show_name)

        self.build_asset_cache()

    def load_show_library(self, show_name: str) -> None:
        """
        Load the show-specific asset library from disk.

        Args:
            show_name: Name of the show whose library to load.
        """
        from core.shows_manager import ShowsManager

        manager = ShowsManager()
        show_path = manager.shows_root / show_name
        library_path = show_path / "asset_library.json"

        if library_path.exists():
            try:
                with open(library_path, 'r') as f:
                    self.show_library = json.load(f)
                _log(f"Loaded asset library for show: {show_name}")
            except (json.JSONDecodeError, IOError) as e:
                _log_warning(f"Failed to load show library: {e}")
                self.show_library = {}
        else:
            _log(f"No asset library found for show: {show_name}")
            self.show_library = {}

    def build_asset_cache(self) -> None:
        """
        Build cache of available assets from the project.

        Scans common asset paths and builds a lookup dictionary mapping
        lowercase asset names to their full paths. When semantic matching
        is enabled, also builds an embedding index for all known assets.
        """
        _log("Building asset cache...")

        if unreal is not None and hasattr(unreal, 'AssetRegistryHelpers'):
            asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

            search_paths = [
                '/Game',
                '/Engine/BasicShapes',
                '/Engine/VREditor/BasicMeshes',
                '/Engine/EditorMeshes'
            ]

            for path in search_paths:
                meshes = asset_registry.get_assets_by_path(path, recursive=True)

                for asset_data in meshes:
                    # asset_class_path is UE 5.1+; fall back for older engines
                    if hasattr(asset_data, 'asset_class_path'):
                        class_name = str(asset_data.asset_class_path.asset_name)
                    elif hasattr(asset_data, 'asset_class'):
                        class_name = str(asset_data.asset_class)
                    else:
                        continue

                    if class_name == 'StaticMesh':
                        asset_name = str(asset_data.asset_name)
                        if hasattr(asset_data, 'get_soft_object_path'):
                            asset_path = str(asset_data.get_soft_object_path())
                        elif hasattr(asset_data, 'object_path'):
                            asset_path = str(asset_data.object_path)
                        else:
                            continue
                        self.asset_cache[asset_name.lower()] = asset_path
        else:
            _log_warning("Unreal asset registry unavailable; skipping general asset scan")

        _log(f"Asset cache built with {len(self.asset_cache)} general assets")

        # Optional semantic (embedding) index; never fatal on failure
        self._semantic_enabled = self._is_semantic_matching_enabled()
        if self._semantic_enabled:
            try:
                self._build_embedding_index()
            except Exception as e:
                _log_warning(f"Failed to build embedding index: {e}")
                self._semantic_index = []

    def find_best_match(self, object_name: str, category: Optional[str] = None,
                        description: Optional[str] = None,
                        panel_image_path: Optional[str] = None) -> Optional[Any]:
        """
        Find the best matching asset for an object name.

        Searches in priority order: show library, general cache, semantic
        (embedding) match, fuzzy match, optional generative text-to-3D,
        then fallback shapes.

        Args:
            object_name: Name of the object to find an asset for.
            category: Optional category hint ('characters', 'props', 'locations').
                     If None, category is inferred from object_name keywords.
            description: Optional entity description. Only used by the
                     optional generative text-to-3D step to build a richer
                     prompt; existing matching tiers ignore it.
            panel_image_path: Optional path of the source storyboard panel
                     image. Only used by the optional generative step when
                     'gen3d.mode' is 'image' (crop the entity and generate
                     from the image); absent means text mode, existing
                     matching tiers ignore it.

        Returns:
            Loaded Unreal asset object, or None if no match found.

        Example:
            >>> asset = matcher.find_best_match("wooden_chair", category="props")
        """
        object_name_lower = object_name.lower().strip()

        # Category drives the character-rigging path in the generative
        # tier too, so infer it up front (not only for the show library).
        if not category:
            category = self._infer_category(object_name_lower)

        # PRIORITY 1: Show-specific library
        if self.show_library:
            asset = self._search_show_library(object_name_lower, category)
            if asset:
                return asset

        # PRIORITY 2: Exact match in general cache. The cache indexes every
        # StaticMesh under /Game (including old generations), so it must
        # honor the same static-generated-character skip as the show
        # library, or the rigged regeneration can never trigger.
        if object_name_lower in self.asset_cache:
            asset = self.load_asset(self.asset_cache[object_name_lower])
            if asset:
                if self._should_regen_static_character(asset, category):
                    _log(f"[Gen3D] Cache hit for character '{object_name}' is an "
                         f"auto-generated StaticMesh (cannot animate); continuing "
                         f"to the generative tier for rigged regeneration")
                else:
                    _log(f"Matched '{object_name}' in general cache")
                    return asset

        # PRIORITY 3: Semantic (embedding) matching, optional.
        # Any failure inside returns None so we fall through to fuzzy.
        asset = self._semantic_match(object_name_lower)
        if asset and not self._should_regen_static_character(asset, category):
            return asset

        # PRIORITY 4: Fuzzy matching
        asset = self._fuzzy_match(object_name_lower)
        if asset and not self._should_regen_static_character(asset, category):
            return asset

        # PRIORITY 5: Generative text-to-3D (optional, off by default).
        # Any failure inside returns None so we fall through to shapes;
        # with 'gen3d.enabled' false this is a no-op.
        asset = self._generative_match(object_name_lower, description,
                                       panel_image_path=panel_image_path,
                                       category=category)
        if asset:
            return asset

        # PRIORITY 6: Fallback shapes
        return self.get_fallback_asset(object_name)

    def _infer_category(self, object_name: str) -> str:
        """
        Infer asset category from object name keywords.

        Args:
            object_name: Lowercase object name to analyze.

        Returns:
            Category string: 'characters', 'locations', or 'props'.
        """
        if any(word in object_name for word in ['character', 'person', 'hero', 'villain']):
            return 'characters'
        elif any(word in object_name for word in ['location', 'scene', 'level', 'place']):
            return 'locations'
        return 'props'

    def _search_show_library(self, object_name: str, category: str) -> Optional[Any]:
        """
        Search show library for matching asset.

        Args:
            object_name: Lowercase object name to find.
            category: Category to search in.

        Returns:
            Loaded asset or None.
        """
        if category not in self.show_library:
            return None

        # Three sequential passes over ALL entries: (1) exact name,
        # (2) exact alias, (3) loose substring (alias/description
        # containment). Matching per-entry in dict order let an earlier
        # entry's loose substring hit shadow a later entry's EXACT name
        # match (scene_builder._find_asset_path was already fixed the same
        # way; this sibling never was).
        entries = self.show_library[category].items()

        # Pass 1: exact name match
        for asset_name, asset_data in entries:
            if asset_name.lower() == object_name:
                asset = self._load_show_entry(object_name, asset_name,
                                              asset_data, category, '')
                if asset:
                    return asset

        # Pass 2: exact alias equality
        for asset_name, asset_data in entries:
            for alias in self._normalize_aliases(asset_data.get('aliases', [])):
                if alias.lower() == object_name:
                    asset = self._load_show_entry(object_name, asset_name,
                                                  asset_data, category,
                                                  ' via alias')
                    if asset:
                        return asset

        # Pass 3: loose containment (alias substring, then description)
        for asset_name, asset_data in entries:
            for alias in self._normalize_aliases(asset_data.get('aliases', [])):
                if object_name in alias.lower():
                    asset = self._load_show_entry(object_name, asset_name,
                                                  asset_data, category,
                                                  ' via alias substring')
                    if asset:
                        return asset

            description = asset_data.get('description', '').lower()
            if object_name in description:
                asset = self._load_show_entry(object_name, asset_name,
                                              asset_data, category,
                                              ' via description')
                if asset:
                    return asset

        return None

    def _load_show_entry(self, object_name: str, asset_name: str,
                         asset_data: Dict[str, Any], category: str,
                         via: str) -> Optional[Any]:
        """
        Load a show-library entry's asset for a match, with one guard:
        a CHARACTER entry whose asset is an auto-GENERATED StaticMesh is
        skipped when character rigging is enabled, so the generative tier
        can replace it with a rigged (skeletal) generation. Static meshes
        can never animate; user-added static characters (non-generated
        paths) are left alone.
        """
        asset_path = asset_data.get('asset_path')
        if not asset_path:
            return None
        asset = self.load_asset(asset_path)
        if asset is None:
            return None
        if self._should_regen_static_character(asset, category):
            _log(f"[Gen3D] Show entry '{asset_name}' for character "
                 f"'{object_name}' is an auto-generated StaticMesh (cannot "
                 f"animate); skipping so it regenerates rigged")
            return None
        _log(f"Matched '{object_name}'{via} to show asset: {asset_name}")
        return asset

    def _should_regen_static_character(self, asset: Any,
                                       category: Optional[str]) -> bool:
        """
        True when a matched asset is an auto-GENERATED StaticMesh for a
        CHARACTER, rigging is enabled, AND a gen3d provider is configured
        to actually regenerate it. Without a provider the static match is
        kept - degrading a working match to a fallback cube helps no one.
        """
        if category != 'characters' or not self._is_static_mesh(asset):
            return False
        try:
            path = str(asset.get_path_name())
        except Exception:
            return False
        if not path.startswith('/Game/StoryboardTo3D/Generated'):
            return False
        if not self._rig_characters_enabled():
            return False
        try:
            from core.gen3d import gen3d_factory
            return gen3d_factory.get_configured() is not None
        except Exception:
            return False

    @staticmethod
    def _is_static_mesh(asset: Any) -> bool:
        """True when the loaded asset is a StaticMesh (guarded)."""
        try:
            return unreal is not None and isinstance(asset, unreal.StaticMesh)
        except Exception:
            return False

    def _rig_characters_enabled(self) -> bool:
        """Read 'gen3d.rig_characters' (default ON): auto-rig generated
        CHARACTER models via the provider so they import as skeletal
        meshes and can be animated. Never raises."""
        try:
            from core.settings_manager import get_setting
            return bool(get_setting('gen3d.rig_characters', True))
        except Exception:
            return True

    @staticmethod
    def _normalize_aliases(aliases) -> List[str]:
        """Normalize library alias data to a list of strings.

        Aliases stored as a comma-separated STRING are valid library data
        (scene_builder supports that form); iterating such a string directly
        walked it character-by-character, so string-form aliases silently
        never matched here.
        """
        if isinstance(aliases, str):
            return [a.strip() for a in aliases.split(',') if a.strip()]
        if isinstance(aliases, (list, tuple)):
            return [str(a) for a in aliases if a]
        return []

    # ========================================
    # SEMANTIC (EMBEDDING) MATCHING
    # ========================================

    def _get_embedding_backend(self) -> Optional[Any]:
        """
        Resolve the shared embeddings backend (utils/embeddings.py) once
        per matcher instance: OpenAI, Gemini, or local Ollama per the
        'asset_library.embedding_provider' setting ('auto' default).

        Returns:
            Backend object with embed_texts()/namespace, or None when no
            embeddings provider is available.
        """
        if self._embedding_backend_resolved:
            return self._embedding_backend

        self._embedding_backend_resolved = True
        if get_embedding_backend is None:
            self._embedding_backend = None
        else:
            try:
                self._embedding_backend = get_embedding_backend()
            except Exception as e:
                _log_warning(f"Embedding backend resolution failed: {e}")
                self._embedding_backend = None
        return self._embedding_backend

    def _is_semantic_matching_enabled(self) -> bool:
        """
        Check whether semantic matching should be active.

        Requires the 'semantic_matching' setting to be truthy AND an
        embeddings backend (OpenAI, Gemini, or local Ollama) to be
        available. The Features tab persists the toggle via
        core.settings_manager under 'asset_library.semantic_matching', so
        that store is read first; when it carries no value, the legacy
        config_manager lookup (checked under 'asset_library.semantic_matching'
        then top-level 'semantic_matching', defaulting to False) applies
        unchanged.

        Returns:
            True only when both the setting and a backend are present.
        """
        enabled = None
        try:
            from core.settings_manager import get_setting
            value = get_setting('asset_library.semantic_matching', None)
            if value is not None:
                enabled = bool(value)
        except Exception as e:
            _log_warning(f"Could not read 'asset_library.semantic_matching' "
                         f"via settings_manager: {e}")
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
                _log_warning(f"Could not read semantic_matching setting: {e}")
                enabled = False

        if not enabled:
            return False

        if self._get_embedding_backend() is None:
            _log("Semantic matching: no embeddings provider available "
                 "(OpenAI/Gemini/Ollama) - using fuzzy matching")
            return False

        return True

    def _get_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Request embedding vectors via the shared backend
        (utils/embeddings.py: OpenAI, Gemini, or local Ollama).

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input, in input order),
            or None on any failure (logged, never raised).
        """
        if not texts:
            return []

        backend = self._get_embedding_backend()
        if backend is None:
            _log_warning("No embeddings backend available for embedding request")
            return None

        return backend.embed_texts(texts)

    @staticmethod
    def _hash_text(text: str) -> str:
        """Return a stable hash key for an embedding text."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _cache_key(self, text: str) -> str:
        """
        Cache key for an embedding text, namespaced per backend+model
        ('provider:model:sha256') so vectors from different embedding
        spaces are never compared after a provider switch.
        """
        backend = self._get_embedding_backend()
        namespace = getattr(backend, 'namespace', 'unknown')
        return f"{namespace}:{self._hash_text(text)}"

    def _load_embedding_cache(self) -> Dict[str, List[float]]:
        """
        Load the persisted embedding cache from disk.

        Returns:
            Dict mapping text hashes to embedding vectors; empty on failure.
        """
        try:
            if EMBEDDING_CACHE_FILE.exists():
                with open(EMBEDDING_CACHE_FILE, 'r') as f:
                    cached = json.load(f)
                if isinstance(cached, dict):
                    return cached
        except Exception as e:
            _log_warning(f"Failed to load embedding cache: {e}")
        return {}

    def _save_embedding_cache(self) -> None:
        """Persist the embedding cache to disk so re-runs are free."""
        try:
            EMBEDDING_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EMBEDDING_CACHE_FILE, 'w') as f:
                json.dump(self.embedding_cache, f)
        except Exception as e:
            _log_warning(f"Failed to save embedding cache: {e}")

    def _collect_semantic_entries(self) -> List[Tuple[str, str, str]]:
        """
        Collect (label, asset_path, embed_text) tuples for all known assets.

        Show library assets embed 'name. description. aliases'; general cache
        assets have only a name, so their embed text is the name alone.

        Returns:
            List of (label, asset_path, embed_text) tuples.
        """
        entries: List[Tuple[str, str, str]] = []

        for category, assets in self.show_library.items():
            if not isinstance(assets, dict):
                continue
            for asset_name, asset_data in assets.items():
                if not isinstance(asset_data, dict):
                    continue
                asset_path = asset_data.get('asset_path')
                if not asset_path:
                    continue
                description = asset_data.get('description', '') or ''
                # _normalize_aliases: a comma-separated STRING alias field
                # would otherwise be embedded per-character via join
                aliases = self._normalize_aliases(asset_data.get('aliases', []) or [])
                alias_text = ', '.join(aliases)
                parts = [asset_name, description, alias_text]
                embed_text = '. '.join(p.strip() for p in parts if p and p.strip())
                entries.append((asset_name, asset_path, embed_text))

        for asset_name, asset_path in self.asset_cache.items():
            entries.append((asset_name, asset_path, asset_name))

        return entries

    def _build_embedding_index(self) -> None:
        """
        Build the in-memory semantic index for all known assets.

        Reuses vectors from the persisted cache (keyed by text hash) and only
        requests embeddings for texts not yet cached, in batches. Failures
        are logged and leave the index partial or empty; matching then falls
        through to fuzzy search.
        """
        self._semantic_index = []

        entries = self._collect_semantic_entries()
        if not entries:
            return

        self.embedding_cache = self._load_embedding_cache()

        missing: List[Tuple[str, str]] = []
        seen_hashes = set()
        for _label, _asset_path, embed_text in entries:
            text_hash = self._cache_key(embed_text)
            if text_hash not in self.embedding_cache and text_hash not in seen_hashes:
                missing.append((text_hash, embed_text))
                seen_hashes.add(text_hash)

        if missing:
            _log(f"Requesting embeddings for {len(missing)} new asset texts")
            for start in range(0, len(missing), EMBEDDING_BATCH_SIZE):
                batch = missing[start:start + EMBEDDING_BATCH_SIZE]
                vectors = self._get_embeddings([text for _h, text in batch])
                if vectors is None:
                    _log_warning("Embedding batch failed; semantic index will be partial")
                    break
                for (text_hash, _text), vector in zip(batch, vectors):
                    self.embedding_cache[text_hash] = vector
            self._save_embedding_cache()

        for label, asset_path, embed_text in entries:
            vector = self.embedding_cache.get(self._cache_key(embed_text))
            if vector:
                self._semantic_index.append((label, asset_path, vector))

        _log(f"Semantic index built with {len(self._semantic_index)} assets")

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Compute cosine similarity between two vectors in pure Python.

        Args:
            vec_a: First vector.
            vec_b: Second vector.

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

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """
        Get the embedding for a query string, with a small in-memory cache.

        Args:
            query: Lowercase query text.

        Returns:
            Embedding vector or None on failure.
        """
        # Namespaced per backend+model so a provider switch cannot serve
        # vectors from a different embedding space
        cache_key = self._cache_key(query)
        if cache_key in self._query_embedding_cache:
            return self._query_embedding_cache[cache_key]

        vectors = self._get_embeddings([query])
        if not vectors:
            return None

        vector = vectors[0]
        if len(self._query_embedding_cache) >= QUERY_EMBEDDING_CACHE_MAX:
            # Drop the oldest entry (insertion order) to bound memory use
            self._query_embedding_cache.pop(next(iter(self._query_embedding_cache)))
        self._query_embedding_cache[cache_key] = vector
        return vector

    def _semantic_match(self, object_name: str) -> Optional[Any]:
        """
        Find an asset by embedding similarity to the object name.

        Args:
            object_name: Lowercase object name to match.

        Returns:
            Loaded asset when the best cosine similarity clears the
            threshold, otherwise None. Never raises; any failure is logged
            and returns None so callers fall through to fuzzy matching.
        """
        if not self._semantic_enabled or not self._semantic_index:
            return None

        try:
            query_vector = self._get_query_embedding(object_name)
            if not query_vector:
                return None

            best_label = None
            best_path = None
            best_score = 0.0

            for label, asset_path, vector in self._semantic_index:
                score = self._cosine_similarity(query_vector, vector)
                if score > best_score:
                    best_score = score
                    best_label = label
                    best_path = asset_path

            if best_path and best_score >= SEMANTIC_MATCH_THRESHOLD:
                _log(f"Semantic matched '{object_name}' to '{best_label}' "
                     f"(similarity {best_score:.2f})")
                return self.load_asset(best_path)

            if best_label:
                _log(f"Semantic best candidate '{best_label}' for '{object_name}' "
                     f"below threshold ({best_score:.2f} < {SEMANTIC_MATCH_THRESHOLD})")
            return None
        except Exception as e:
            _log_warning(f"Semantic matching failed for '{object_name}': {e}; "
                         f"falling back to fuzzy matching")
            return None

    def _fuzzy_match(self, object_name: str) -> Optional[Any]:
        """
        Find asset using fuzzy string matching.

        Args:
            object_name: Lowercase object name to match.

        Returns:
            Best matching asset if score > 0.5, otherwise None.
        """
        import re as _re

        def _norm(text):
            # Compare on letters/digits only: placeholder names like
            # '(scythe)' and '(ghost)' share enough PUNCTUATION to score
            # 0.53 raw, which once matched a scythe to the ghost mesh
            return _re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()

        best_match = None
        best_label = None
        best_score = 0.0
        norm_object = _norm(object_name)
        if not norm_object:
            return None

        for asset_name, asset_path in self.asset_cache.items():
            norm_asset = _norm(asset_name)
            if not norm_asset:
                continue
            score = SequenceMatcher(None, norm_object, norm_asset).ratio()

            # Bonus for substring match
            if norm_object in norm_asset:
                score += 0.3

            if score > best_score and score > 0.5:
                best_score = score
                best_match = asset_path
                best_label = asset_name

        if best_match:
            _log(f"Fuzzy matched '{object_name}' to '{best_label}' with score {best_score:.2f}")
            return self.load_asset(best_match)

        return None

    # ========================================
    # GENERATIVE TEXT-TO-3D (OPTIONAL)
    # ========================================

    def _get_gen3d_max_per_run(self) -> int:
        """
        Read the per-run generation budget ('gen3d.max_per_run', default 3).

        Returns:
            Non-negative integer budget; the default on any failure.
        """
        try:
            from core.settings_manager import get_setting
            value = get_setting('gen3d.max_per_run', GEN3D_DEFAULT_MAX_PER_RUN)
            return max(0, int(value))
        except Exception as e:
            _log_warning(f"[Gen3D] Could not read 'gen3d.max_per_run': {e}; "
                         f"using default {GEN3D_DEFAULT_MAX_PER_RUN}")
            return GEN3D_DEFAULT_MAX_PER_RUN

    def _get_gen3d_mode(self) -> str:
        """
        Read the generation mode ('gen3d.mode': 'text' default, 'image').

        Returns:
            'text' or 'image'; 'text' on any failure. Never raises.
        """
        try:
            from core.gen3d.gen3d_factory import get_mode
            return get_mode()
        except Exception as e:
            _log_warning(f"[Gen3D] Could not read 'gen3d.mode': {e}; "
                         f"using 'text'")
            return 'text'

    def _generative_match(self, object_name: str,
                          description: Optional[str] = None,
                          panel_image_path: Optional[str] = None,
                          category: Optional[str] = None) -> Optional[Any]:
        """
        Generate a 3D asset for an unmatched entity via core/gen3d.

        Runs only when 'gen3d.enabled' is truthy and a provider API key is
        available (gen3d_factory.get_configured() returns None otherwise,
        making this a no-op by default). Checks the reuse manifest first,
        then enforces the per-run budget, then generates, imports, and
        registers the new asset so later panels in this run match it via
        the normal tiers.

        When 'gen3d.mode' is 'image' and a panel image path is available,
        the entity is cropped from the panel (core.gen3d.entity_cropper)
        and generated via the provider's image-to-model entrypoint; any
        failure in that branch falls back to the text prompt below.

        Args:
            object_name: Lowercase object name that failed all match tiers.
            description: Optional entity description for a richer prompt.
            panel_image_path: Optional source panel image for image mode.

        Returns:
            Loaded asset or None. Never raises; every failure logs and
            returns None so callers fall through to the basic-shape
            fallback unchanged.
        """
        try:
            from core.gen3d import gen3d_factory
        except ImportError:
            # Package not present; keep the legacy behavior silently.
            return None

        try:
            provider = gen3d_factory.get_configured()
        except Exception as e:
            _log_warning(f"[Gen3D] Provider configuration failed: {e}")
            return None

        if provider is None:
            return None

        provider_name = getattr(provider, 'name', 'unknown')
        entity_text = (f"{object_name} {description}".strip()
                       if description else object_name)

        # (a) Reuse a previously generated asset when possible.
        cached_path = None
        try:
            from core.gen3d import manifest as gen3d_manifest
            cached_path = gen3d_manifest.lookup(entity_text)
        except Exception as e:
            _log_warning(f"[Gen3D] Manifest lookup failed: {e}")

        rig_wanted = (category == 'characters'
                      and self._rig_characters_enabled())

        # When the rigged regeneration of a cached STATIC character fails
        # at any later step, fall back to that loadable static asset -
        # never degrade a working (if unanimatable) match to a cube.
        cached_static_fallback = None

        if cached_path:
            asset = self.load_asset(cached_path)
            if asset:
                # A cached STATIC generation for a character predates (or
                # failed) rigging - regenerate rigged, but only once per
                # run per entity so a rig-refusing model cannot loop costs.
                if (rig_wanted and self._is_static_mesh(asset)
                        and object_name not in self._rig_retry_attempted):
                    self._rig_retry_attempted.add(object_name)
                    cached_static_fallback = asset
                    _log(f"[Gen3D] Cached generation for character "
                         f"'{object_name}' is a StaticMesh (cannot animate); "
                         f"regenerating with rigging")
                else:
                    _log(f"[Gen3D] reusing previously generated asset for "
                         f"'{object_name}': {cached_path}")
                    self._register_generated_asset(object_name, cached_path)
                    # Cached rigged meshes keep their retarget capability:
                    # surface the recorded rig id so rescuers persist it
                    try:
                        from core.gen3d import manifest as gen3d_manifest
                        cached_rig = gen3d_manifest.lookup_rig_task_id(entity_text)
                        if cached_rig:
                            self.last_rig_task_ids[object_name] = cached_rig
                    except Exception:
                        pass
                    return asset
            else:
                _log_warning(f"[Gen3D] Previously generated asset failed to "
                             f"load: {cached_path}; regenerating")

        def _regen_failed(reason):
            """Failure exit: prefer the cached static asset over None."""
            if cached_static_fallback is not None:
                _log_warning(f"[Gen3D] Rigged regeneration for "
                             f"'{object_name}' failed ({reason}); keeping "
                             f"the cached static asset")
                self._register_generated_asset(object_name, cached_path)
                return cached_static_fallback
            return None

        # (b) Per-run generation budget (counts attempts, so repeated
        # failures cannot spiral costs or stall a batch).
        max_per_run = self._get_gen3d_max_per_run()
        if self._gen3d_generation_count >= max_per_run:
            _log(f"[Gen3D] Skipping generation for '{object_name}': per-run "
                 f"budget of {max_per_run} exhausted (gen3d.max_per_run); "
                 f"using fallback shape")
            return _regen_failed('per-run budget exhausted')

        # (c) Generate, import, register, record.
        if description:
            prompt = (f"a low-poly game-ready {object_name}, {description}, "
                      f"single object, neutral pose")
        else:
            prompt = f"a low-poly game-ready {object_name}, single object, neutral pose"

        self._gen3d_generation_count += 1

        # Image mode (opt-in via 'gen3d.mode'): crop the entity out of the
        # panel image and generate from the crop. Any failure inside
        # returns None and we fall back to the text prompt below, so this
        # branch can never break the existing text path.
        result = None
        if self._get_gen3d_mode() == 'image':
            result = self._generative_match_image(
                provider, object_name, description, panel_image_path)

        if result is None:
            try:
                result = provider.generate(prompt)
            except Exception as e:
                # provider.generate() should never raise; belt and braces.
                _log_warning(f"[Gen3D] Generation failed for '{object_name}': {e}")
                return _regen_failed(str(e))

        if (not isinstance(result, dict)
                or result.get('status') != 'succeeded'
                or not result.get('file_path')):
            error = 'unknown error'
            if isinstance(result, dict):
                error = result.get('error', error)
            _log_warning(f"[Gen3D] Generation failed for '{object_name}': "
                         f"{error}; using fallback shape")
            return _regen_failed(error)

        # Characters: auto-rig the generated model so it imports as a
        # SkeletalMesh and can be animated (a static character can never
        # leave T-pose... it cannot even reach T-pose). Any rig failure
        # logs and falls back to the static import below.
        model_file = result['file_path']
        prefer_skeletal = False
        if rig_wanted and result.get('task_id') \
                and hasattr(provider, 'rig_model'):
            _log(f"[Gen3D] Rigging generated character '{object_name}' "
                 f"via {provider_name} (gen3d.rig_characters)")
            try:
                rig_result = provider.rig_model(result['task_id'],
                                                name=object_name)
            except Exception as e:
                rig_result = {'status': 'failed', 'error': str(e)}
            if (isinstance(rig_result, dict)
                    and rig_result.get('status') == 'succeeded'
                    and rig_result.get('file_path')):
                model_file = rig_result['file_path']
                prefer_skeletal = True
                if rig_result.get('rig_task_id'):
                    # Remember the rig id so callers can persist it: it
                    # lets genanim retarget clips onto THIS character.
                    self.last_rig_task_ids[object_name] = str(
                        rig_result['rig_task_id'])
                _log(f"[Gen3D] Rigged model ready for '{object_name}' "
                     f"(rig task: {rig_result.get('rig_task_id')})")
            else:
                error = rig_result.get('error', 'unknown error') \
                    if isinstance(rig_result, dict) else 'unknown error'
                _log_warning(f"[Gen3D] Rigging failed for '{object_name}' "
                             f"({error}); importing unrigged static model")
        elif rig_wanted:
            _log_warning(f"[Gen3D] Character '{object_name}' generated but "
                         f"provider '{provider_name}' cannot rig "
                         f"(no task id or rig support); importing static")

        try:
            from core.gen3d.importer import import_generated_model
            asset_path = import_generated_model(model_file, object_name,
                                                prefer_skeletal=prefer_skeletal)
        except Exception as e:
            _log_warning(f"[Gen3D] Import failed for '{object_name}': {e}")
            return _regen_failed(f'import failed: {e}')

        if not asset_path:
            _log_warning(f"[Gen3D] Import produced no asset for "
                         f"'{object_name}'; using fallback shape")
            return _regen_failed('import produced no asset')

        asset = self.load_asset(asset_path)
        if not asset:
            _log_warning(f"[Gen3D] Imported asset failed to load: "
                         f"{asset_path}; using fallback shape")
            return _regen_failed('imported asset failed to load')

        self._register_generated_asset(object_name, asset_path)

        try:
            from core.gen3d import manifest as gen3d_manifest
            gen3d_manifest.record(entity_text, asset_path, provider_name,
                                  rig_task_id=self.last_rig_task_ids.get(
                                      object_name))
        except Exception as e:
            _log_warning(f"[Gen3D] Failed to record manifest entry: {e}")

        _log(f"[Gen3D] generated and imported {object_name} via "
             f"{provider_name}: {asset_path}")
        return asset

    def _generative_match_image(self, provider: Any, object_name: str,
                                description: Optional[str],
                                panel_image_path: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Image-mode generation attempt ('gen3d.mode' == 'image'): crop the
        entity from the panel image (core.gen3d.entity_cropper) and run
        the provider's generate_from_image entrypoint.

        Args:
            provider: Configured Gen3D provider instance.
            object_name: Lowercase entity name being generated.
            description: Optional entity description for the cropper.
            panel_image_path: Source storyboard panel image path, or None.

        Returns:
            The provider's result dict on success, or None so the caller
            falls back to the text prompt. Never raises.
        """
        try:
            if not panel_image_path or not os.path.isfile(str(panel_image_path)):
                _log(f"[Gen3D] image mode: no panel image available for "
                     f"'{object_name}'; falling back to text mode")
                return None

            if not hasattr(provider, 'generate_from_image'):
                _log_warning(f"[Gen3D] image mode: provider "
                             f"'{getattr(provider, 'name', 'unknown')}' has no "
                             f"image-to-model support; falling back to text mode")
                return None

            from core.gen3d import entity_cropper
            crop_path = entity_cropper.crop_entity(
                str(panel_image_path), object_name, description)
            if not crop_path:
                _log(f"[Gen3D] image mode: entity crop failed for "
                     f"'{object_name}'; falling back to text mode")
                return None

            result = provider.generate_from_image(crop_path, object_name)
            if (isinstance(result, dict)
                    and result.get('status') == 'succeeded'
                    and result.get('file_path')):
                return result

            error = 'unknown error'
            if isinstance(result, dict):
                error = result.get('error', error)
            _log_warning(f"[Gen3D] image mode: image-to-model failed for "
                         f"'{object_name}': {error}; falling back to text mode")
            return None
        except Exception as e:
            _log_warning(f"[Gen3D] image mode failed for '{object_name}': "
                         f"{e}; falling back to text mode")
            return None

    def _register_generated_asset(self, object_name: str, asset_path: str) -> None:
        """
        Register a generated asset in the in-memory cache the same way
        library assets are registered (lowercase name -> asset path), so
        later panels in this run match it via the normal exact/fuzzy tiers.

        Args:
            object_name: Entity name the asset was generated for.
            asset_path: Imported asset path in the project.
        """
        try:
            self.asset_cache[object_name.lower().strip()] = asset_path
            # Also register under the imported asset's own name.
            asset_name = asset_path.rsplit('/', 1)[-1].split('.')[0]
            if asset_name:
                self.asset_cache.setdefault(asset_name.lower(), asset_path)
        except Exception as e:
            _log_warning(f"[Gen3D] Could not register generated asset in "
                         f"cache: {e}")

    def load_asset(self, asset_path: str) -> Optional[Any]:
        """
        Load an Unreal asset from its path.

        Args:
            asset_path: Full asset path, optionally with class prefix.

        Returns:
            Loaded asset object, or None if load fails.
        """
        try:
            # Extract path from class prefix format if present
            if "'" in asset_path:
                asset_path = asset_path.split("'")[1]

            asset = _get_editor_asset_subsystem().load_asset(asset_path)

            if asset:
                return asset
            else:
                _log_warning(f"Asset not found: {asset_path}")
        except Exception as e:
            _log_warning(f"Failed to load asset {asset_path}: {e}")

        return None

    def get_fallback_asset(self, object_name: str) -> Optional[Any]:
        """
        Get a fallback basic shape based on object type.

        Args:
            object_name: Object name to determine appropriate shape.

        Returns:
            Basic shape asset (Cube, Cylinder, etc.) or default Cube.
        """
        shape_map = {
            'chair': '/Engine/BasicShapes/Cube',
            'table': '/Engine/BasicShapes/Cube',
            'desk': '/Engine/BasicShapes/Cube',
            'person': '/Engine/BasicShapes/Cylinder',
            'character': '/Engine/BasicShapes/Cylinder',
            'tree': '/Engine/BasicShapes/Cone',
            'lamp': '/Engine/BasicShapes/Cylinder',
            'ball': '/Engine/BasicShapes/Sphere',
            'box': '/Engine/BasicShapes/Cube',
            'wall': '/Engine/BasicShapes/Plane',
            'floor': '/Engine/BasicShapes/Plane',
            'door': '/Engine/BasicShapes/Cube',
            'window': '/Engine/BasicShapes/Plane'
        }

        for keyword, shape_path in shape_map.items():
            if keyword in object_name.lower():
                asset = _get_editor_asset_subsystem().load_asset(shape_path)
                if asset:
                    _log(f"Using fallback shape for '{object_name}'")
                    return asset

        default = _get_editor_asset_subsystem().load_asset('/Engine/BasicShapes/Cube')
        if default:
            _log(f"Using default cube for '{object_name}'")

        return default

    def find_character_asset(self) -> Optional[Any]:
        """
        Find a character mesh or blueprint.

        Checks show library first, then common character paths.

        Returns:
            Character asset or fallback cylinder shape.
        """
        # Check show library
        if self.show_library and 'characters' in self.show_library:
            for char_name, char_data in self.show_library['characters'].items():
                asset_path = char_data.get('asset_path')
                if asset_path:
                    asset = self.load_asset(asset_path)
                    if asset:
                        _log(f"Using show character: {char_name}")
                        return asset

        # Fallback paths
        character_paths = [
            '/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter',
            '/Game/ThirdPersonBP/Blueprints/ThirdPersonCharacter',
            '/Game/Mannequin/Character/Mesh/SK_Mannequin',
            '/Game/Characters/Mannequin/Mesh/SK_Mannequin',
            '/Engine/EngineMeshes/SkeletalCylinder'
        ]

        for path in character_paths:
            asset = _get_editor_asset_subsystem().load_asset(path)
            if asset:
                return asset

        return _get_editor_asset_subsystem().load_asset('/Engine/BasicShapes/Cylinder')

    def find_prop_assets(self, prop_names: List[str]) -> List[Dict[str, Any]]:
        """
        Find assets for multiple props.

        Args:
            prop_names: List of prop names to find assets for.

        Returns:
            List of dicts with 'name' and 'asset' keys for each matched prop.
        """
        assets = []

        for prop_name in prop_names:
            asset = self.find_best_match(prop_name, category='props')
            if asset:
                assets.append({
                    'name': prop_name,
                    'asset': asset
                })

        return assets

    def get_show_asset_summary(self) -> str:
        """
        Get a summary of available show assets.

        Returns:
            Formatted string summarizing asset counts by category.
        """
        if not self.show_library:
            return "No show library loaded"

        summary = f"Show: {self.show_name}\n"
        for category in ['characters', 'props', 'locations']:
            count = len(self.show_library.get(category, {}))
            summary += f"  {category}: {count} assets\n"

            for name in list(self.show_library.get(category, {}).keys())[:3]:
                summary += f"    - {name}\n"

        return summary

    def search_project_assets(self, search_term: str) -> List[Dict[str, str]]:
        """
        Search project for assets matching a term.

        Args:
            search_term: Search string to match against asset names.

        Returns:
            List of dicts with 'name', 'path', and 'type' for each match.
        """
        if unreal is None or not hasattr(unreal, 'AssetRegistryHelpers'):
            _log_warning("Unreal asset registry unavailable; cannot search project assets")
            return []

        try:
            asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

            filter = unreal.ARFilter()
            filter.package_paths = ['/Game']
            filter.recursive_paths = True
            filter.class_paths = [
                unreal.TopLevelAssetPath('/Script/Engine', 'StaticMesh'),
                unreal.TopLevelAssetPath('/Script/Engine', 'SkeletalMesh'),
                unreal.TopLevelAssetPath('/Script/Engine', 'Blueprint'),
            ]

            assets = asset_registry.get_assets(filter)
        except Exception as e:
            _log_warning(f"Project asset search failed: {e}")
            return []

        matches = []
        search_lower = search_term.lower()

        for asset_data in assets:
            asset_name = str(asset_data.asset_name).lower()

            if search_lower in asset_name:
                if hasattr(asset_data, 'asset_class_path'):
                    class_name = str(asset_data.asset_class_path.asset_name)
                elif hasattr(asset_data, 'asset_class'):
                    class_name = str(asset_data.asset_class)
                else:
                    class_name = 'Unknown'

                if hasattr(asset_data, 'get_soft_object_path'):
                    asset_path = str(asset_data.get_soft_object_path())
                elif hasattr(asset_data, 'object_path'):
                    asset_path = str(asset_data.object_path)
                else:
                    continue

                matches.append({
                    'name': str(asset_data.asset_name),
                    'path': asset_path,
                    'type': class_name
                })

        return matches

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Asset Matcher Module

Matches object names from storyboard analysis to Unreal Engine assets.
Prioritizes show-specific asset libraries, then falls back to general project
assets and basic shapes.

Optionally performs semantic matching via OpenAI embeddings so that related
terms (e.g. 'canine' or 'pup') can find a 'dog' asset. Semantic matching is
disabled by default; it activates only when the 'semantic_matching' setting
is truthy AND an OpenAI API key is available. On any failure it falls back
to the existing fuzzy matching, so out-of-the-box behavior is unchanged.
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


# Semantic matching configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"
EMBEDDING_TIMEOUT_SECONDS = 15
SEMANTIC_MATCH_THRESHOLD = 0.55
EMBEDDING_BATCH_SIZE = 100
QUERY_EMBEDDING_CACHE_MAX = 128
EMBEDDING_CACHE_FILE = Path.home() / ".storyboard_to_3d" / "embedding_cache.json"


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
        3. Semantic matching via OpenAI embeddings (optional, off by default)
        4. Fuzzy matching in general cache
        5. Fallback to basic shapes

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
        self._openai_api_key: Optional[str] = None
        self._openai_api_key_resolved: bool = False

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

    def find_best_match(self, object_name: str, category: Optional[str] = None) -> Optional[Any]:
        """
        Find the best matching asset for an object name.

        Searches in priority order: show library, general cache, semantic
        (embedding) match, fuzzy match, then fallback shapes.

        Args:
            object_name: Name of the object to find an asset for.
            category: Optional category hint ('characters', 'props', 'locations').
                     If None, category is inferred from object_name keywords.

        Returns:
            Loaded Unreal asset object, or None if no match found.

        Example:
            >>> asset = matcher.find_best_match("wooden_chair", category="props")
        """
        object_name_lower = object_name.lower().strip()

        # PRIORITY 1: Show-specific library
        if self.show_library:
            if not category:
                category = self._infer_category(object_name_lower)

            asset = self._search_show_library(object_name_lower, category)
            if asset:
                return asset

        # PRIORITY 2: Exact match in general cache
        if object_name_lower in self.asset_cache:
            asset = self.load_asset(self.asset_cache[object_name_lower])
            if asset:
                _log(f"Matched '{object_name}' in general cache")
                return asset

        # PRIORITY 3: Semantic (embedding) matching, optional.
        # Any failure inside returns None so we fall through to fuzzy.
        asset = self._semantic_match(object_name_lower)
        if asset:
            return asset

        # PRIORITY 4: Fuzzy matching
        asset = self._fuzzy_match(object_name_lower)
        if asset:
            return asset

        # PRIORITY 5: Fallback shapes
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

        for asset_name, asset_data in self.show_library[category].items():
            # Exact match
            if asset_name.lower() == object_name:
                asset_path = asset_data.get('asset_path')
                if asset_path:
                    _log(f"Matched '{object_name}' to show asset: {asset_name}")
                    return self.load_asset(asset_path)

            # Alias match
            aliases = asset_data.get('aliases', [])
            for alias in aliases:
                if alias.lower() == object_name or object_name in alias.lower():
                    asset_path = asset_data.get('asset_path')
                    if asset_path:
                        _log(f"Matched '{object_name}' via alias to show asset: {asset_name}")
                        return self.load_asset(asset_path)

            # Description match
            description = asset_data.get('description', '').lower()
            if object_name in description:
                asset_path = asset_data.get('asset_path')
                if asset_path:
                    _log(f"Matched '{object_name}' via description to show asset: {asset_name}")
                    return self.load_asset(asset_path)

        return None

    # ========================================
    # SEMANTIC (EMBEDDING) MATCHING
    # ========================================

    def _get_openai_api_key(self) -> Optional[str]:
        """
        Resolve the OpenAI API key from the environment or config_manager.

        Follows the same pattern as api/ai_client.py: environment variable
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
                _log_warning(f"Could not resolve OpenAI API key via config_manager: {e}")
                api_key = None

        self._openai_api_key = api_key
        return api_key

    def _is_semantic_matching_enabled(self) -> bool:
        """
        Check whether semantic matching should be active.

        Requires the 'semantic_matching' setting to be truthy (read via the
        plugin's config_manager, checked under 'asset_library.semantic_matching'
        then top-level 'semantic_matching', defaulting to False) AND an OpenAI
        API key to be available.

        Returns:
            True only when both the setting and the API key are present.
        """
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

        if not self._get_openai_api_key():
            _log("Semantic matching is enabled but no OpenAI API key was found; "
                 "falling back to fuzzy matching only")
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
            _log_warning("The 'requests' package is unavailable; semantic matching disabled")
            return None

        try:
            response = requests.post(
                EMBEDDING_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={"model": EMBEDDING_MODEL, "input": texts},
                timeout=EMBEDDING_TIMEOUT_SECONDS
            )

            if response.status_code != 200:
                _log_warning(f"Embedding request failed with HTTP {response.status_code}: "
                             f"{response.text[:200]}")
                return None

            data = response.json().get("data", [])
            if len(data) != len(texts):
                _log_warning(f"Embedding response count mismatch: expected {len(texts)}, "
                             f"got {len(data)}")
                return None

            ordered = sorted(data, key=lambda item: item.get("index", 0))
            return [item["embedding"] for item in ordered]
        except Exception as e:
            _log_warning(f"Embedding request failed: {e}")
            return None

    @staticmethod
    def _hash_text(text: str) -> str:
        """Return a stable hash key for an embedding text."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

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
                aliases = asset_data.get('aliases', []) or []
                alias_text = ', '.join(str(a) for a in aliases)
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
            text_hash = self._hash_text(embed_text)
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
            vector = self.embedding_cache.get(self._hash_text(embed_text))
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
        if query in self._query_embedding_cache:
            return self._query_embedding_cache[query]

        vectors = self._get_embeddings([query])
        if not vectors:
            return None

        vector = vectors[0]
        if len(self._query_embedding_cache) >= QUERY_EMBEDDING_CACHE_MAX:
            # Drop the oldest entry (insertion order) to bound memory use
            self._query_embedding_cache.pop(next(iter(self._query_embedding_cache)))
        self._query_embedding_cache[query] = vector
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
        best_match = None
        best_score = 0.0

        for asset_name, asset_path in self.asset_cache.items():
            score = SequenceMatcher(None, object_name, asset_name).ratio()

            # Bonus for substring match
            if object_name in asset_name:
                score += 0.3

            if score > best_score and score > 0.5:
                best_score = score
                best_match = asset_path

        if best_match:
            _log(f"Fuzzy matched '{object_name}' with score {best_score:.2f}")
            return self.load_asset(best_match)

        return None

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

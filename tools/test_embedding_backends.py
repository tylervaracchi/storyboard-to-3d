# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Standalone (no Unreal, no network) test for the shared embeddings
backend wiring in core/asset_matcher.py and core/animation_matcher.py.

Verifies:
  1. Both matchers' semantic tiers consume an injected fake backend
     (embed_texts is called; the match resolves through its vectors).
  2. Persisted + in-memory embedding cache keys are namespaced per
     backend+model ('provider:model:sha256').
  3. backend=None degrades to the existing fuzzy tier without raising,
     emitting the one documented log line.
  4. get_embedding_backend() returns None for an explicitly selected
     provider with no credentials, and the real backends carry the
     expected namespaces.

Run:  python tools/test_embedding_backends.py
"""

import contextlib
import io
import os
import sys
import tempfile
import types
from pathlib import Path

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
PLUGIN_PYTHON = os.path.join(REPO_ROOT, "Content", "Python")
sys.path.insert(0, PLUGIN_PYTHON)

# Fake settings manager: semantic matching ON, everything else default.
# Installed BEFORE any matcher call so the in-function
# 'from core.settings_manager import get_setting' resolves to this stub
# headlessly (the real module imports unreal at module level).
_fake_settings = types.ModuleType('core.settings_manager')


def _fake_get_setting(path, default=None):
    if path == 'asset_library.semantic_matching':
        return True
    return default


_fake_settings.get_setting = _fake_get_setting
sys.modules['core.settings_manager'] = _fake_settings
try:
    import core
    core.settings_manager = _fake_settings
except ImportError:
    pass

import core.asset_matcher as am          # noqa: E402
import core.animation_matcher as anm     # noqa: E402
import utils.embeddings as emb           # noqa: E402

# Redirect the persisted embedding caches away from ~/.storyboard_to_3d
_tmp = tempfile.mkdtemp(prefix="embed_test_")
am.EMBEDDING_CACHE_FILE = Path(_tmp) / "asset_embedding_cache.json"
anm.ANIM_EMBEDDING_CACHE_FILE = Path(_tmp) / "anim_embedding_cache.json"

FUZZY_FALLBACK_LINE = ("Semantic matching: no embeddings provider available "
                       "(OpenAI/Gemini/Ollama) - using fuzzy matching")

PASSED = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    PASSED.append(bool(condition))


class FakeBackend:
    """Deterministic embed_texts backend: text -> fixed vector."""

    name = 'fake'
    model = 'test-model'
    namespace = 'fake:test-model'

    def __init__(self, table):
        self.table = table
        self.calls = 0
        self.seen_texts = []

    def embed_texts(self, texts):
        self.calls += 1
        self.seen_texts.extend(texts)
        return [self.table[t] for t in texts]


def test_asset_matcher_semantic_uses_backend():
    matcher = am.AssetMatcher()
    matcher.asset_cache = {'dog': '/Game/Dog'}
    fake = FakeBackend({'dog': [1.0, 0.0], 'canine': [0.9, 0.1]})
    matcher._embedding_backend = fake
    matcher._embedding_backend_resolved = True
    matcher._semantic_enabled = True
    matcher.embedding_cache = {}
    matcher.load_asset = lambda p: p  # no editor: return the path itself

    matcher._build_embedding_index()
    check("asset: fake backend consumed for index",
          fake.calls >= 1 and 'dog' in fake.seen_texts,
          f"calls={fake.calls} seen={fake.seen_texts}")
    check("asset: semantic index built", len(matcher._semantic_index) == 1)
    check("asset: persisted cache keys namespaced per backend+model",
          matcher.embedding_cache and
          all(k.startswith('fake:test-model:') for k in matcher.embedding_cache),
          f"keys={list(matcher.embedding_cache)}")

    result = matcher._semantic_match('canine')
    check("asset: semantic tier matched via fake vectors",
          result == '/Game/Dog', f"result={result}")
    check("asset: query cache keys namespaced",
          matcher._query_embedding_cache and
          all(k.startswith('fake:test-model:')
              for k in matcher._query_embedding_cache),
          f"keys={list(matcher._query_embedding_cache)}")


def test_asset_matcher_none_backend_falls_to_fuzzy():
    matcher = am.AssetMatcher()
    matcher.asset_cache = {'dog': '/Game/Dog'}
    matcher._embedding_backend = None
    matcher._embedding_backend_resolved = True
    matcher.load_asset = lambda p: p

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        enabled = matcher._is_semantic_matching_enabled()
    check("asset: backend=None disables semantic tier", enabled is False)
    check("asset: backend=None logs the documented fuzzy-fallback line",
          FUZZY_FALLBACK_LINE in out.getvalue(), out.getvalue().strip())

    matcher._semantic_enabled = enabled
    try:
        result = matcher.find_best_match('dogg')
    except Exception as e:  # must never raise
        check("asset: find_best_match with no backend does not raise",
              False, repr(e))
        return
    check("asset: fuzzy tier still matches with no backend",
          result == '/Game/Dog', f"result={result}")


def test_animation_matcher_semantic_uses_backend():
    matcher = anm.AnimationMatcher()
    matcher.animations = {
        'run': {'asset_path': '/Game/Anims/Run', 'aliases': ['sprint']}
    }
    matcher._anim_semantic_index_size = -1  # force index (re)build
    fake = FakeBackend({'run. sprint': [0.0, 1.0], 'jogging fast': [0.0, 1.0]})
    matcher._embedding_backend = fake
    matcher._embedding_backend_resolved = True
    matcher._anim_embedding_cache = {}

    path = matcher.find_animation('jogging fast')
    check("anim: semantic tier matched via fake vectors",
          path == '/Game/Anims/Run', f"path={path}")
    check("anim: fake backend consumed",
          fake.calls >= 1 and 'run. sprint' in fake.seen_texts,
          f"calls={fake.calls} seen={fake.seen_texts}")
    check("anim: persisted cache keys namespaced per backend+model",
          matcher._anim_embedding_cache and
          all(k.startswith('fake:test-model:')
              for k in matcher._anim_embedding_cache),
          f"keys={list(matcher._anim_embedding_cache)}")
    check("anim: query cache keys namespaced",
          matcher._anim_query_embedding_cache and
          all(k.startswith('fake:test-model:')
              for k in matcher._anim_query_embedding_cache),
          f"keys={list(matcher._anim_query_embedding_cache)}")


def test_animation_matcher_none_backend_falls_to_fuzzy():
    matcher = anm.AnimationMatcher()
    matcher.animations = {
        'run': {'asset_path': '/Game/Anims/Run', 'aliases': []}
    }
    matcher._embedding_backend = None
    matcher._embedding_backend_resolved = True

    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            path = matcher.find_animation('runn')
    except Exception as e:  # must never raise
        check("anim: find_animation with no backend does not raise",
              False, repr(e))
        return
    check("anim: fuzzy tier still matches with no backend",
          path == '/Game/Anims/Run', f"path={path}")
    check("anim: backend=None logs the documented fuzzy-fallback line",
          FUZZY_FALLBACK_LINE in out.getvalue(), out.getvalue().strip())

    # The line is logged once, not per query
    out2 = io.StringIO()
    with contextlib.redirect_stdout(out2):
        matcher.find_animation('runn again')
    check("anim: fuzzy-fallback line logged only once",
          FUZZY_FALLBACK_LINE not in out2.getvalue())


def test_backend_selection_and_namespaces():
    # Explicit provider with no credentials -> None (no network involved)
    saved = {k: os.environ.pop(k, None)
             for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    try:
        backend = emb.get_embedding_backend('gemini')
        check("selection: explicit gemini without key returns None",
              backend is None, f"backend={backend}")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    check("namespace: openai backend",
          emb.OpenAIEmbeddingBackend('k').namespace
          == 'openai:text-embedding-3-small')
    check("namespace: gemini backend",
          emb.GeminiEmbeddingBackend('k').namespace
          == 'gemini:gemini-embedding-001')
    check("namespace: ollama backend",
          emb.OllamaEmbeddingBackend('http://localhost:11434',
                                     'nomic-embed-text').namespace
          == 'ollama:nomic-embed-text')

    # Unknown provider string never raises
    check("selection: unknown provider does not raise",
          emb.get_embedding_backend('bogus-provider') is None
          or emb.get_embedding_backend('bogus-provider') is not None)


def main():
    test_asset_matcher_semantic_uses_backend()
    test_asset_matcher_none_backend_falls_to_fuzzy()
    test_animation_matcher_semantic_uses_backend()
    test_animation_matcher_none_backend_falls_to_fuzzy()
    test_backend_selection_and_namespaces()

    total = len(PASSED)
    passed = sum(PASSED)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())

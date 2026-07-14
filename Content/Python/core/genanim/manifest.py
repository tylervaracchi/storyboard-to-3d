# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GenAnim Manifest

Tiny JSON manifest at ~/.storyboard_to_3d/generated_anims.json mapping
sha256(normalized action text) -> {asset_path, provider, created} so that
the same described action is never paid for twice across runs. Mirrors
core/gen3d/manifest.py.

lookup() only returns a hit when the recorded asset still exists in the
project (guarded EditorAssetLibrary/Subsystem does_asset_exist check);
outside the editor, or when the asset is gone, it returns None so callers
regenerate or fall back. All functions log-and-continue; none raises.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor; lookup() then cannot verify
    # asset existence and returns None.
    unreal = None


MANIFEST_FILE = Path.home() / ".storyboard_to_3d" / "generated_anims.json"


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


def _normalize_description(description):
    # type: (str) -> str
    """Lowercase, trim, and collapse whitespace so trivially different
    spellings of the same action share one manifest entry."""
    return re.sub(r'\s+', ' ', str(description or '').strip().lower())


def _manifest_key(description):
    # type: (str) -> str
    """sha256 hex digest of the normalized action text."""
    normalized = _normalize_description(description)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _load_manifest():
    # type: () -> Dict[str, dict]
    """Load the manifest dict from disk; {} on any failure (logged)."""
    try:
        if MANIFEST_FILE.exists():
            with open(str(MANIFEST_FILE), 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            _log_warning("[GenAnim] Manifest file is not a JSON object; "
                         "ignoring it")
    except Exception as e:
        _log_warning("[GenAnim] Failed to load generated-anims manifest: "
                     "{}".format(e))
    return {}


def _save_manifest(data):
    # type: (Dict[str, dict]) -> bool
    """Persist the manifest dict; False on failure (logged)."""
    try:
        MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(MANIFEST_FILE), 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        _log_warning("[GenAnim] Failed to save generated-anims manifest: "
                     "{}".format(e))
        return False


def _asset_still_exists(asset_path):
    # type: (str) -> bool
    """Guarded does_asset_exist check via EditorAssetSubsystem, falling
    back to EditorAssetLibrary. False when unverifiable."""
    if unreal is None:
        return False
    try:
        if hasattr(unreal, 'get_editor_subsystem') and \
                hasattr(unreal, 'EditorAssetSubsystem'):
            api = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        elif hasattr(unreal, 'EditorAssetLibrary'):
            api = unreal.EditorAssetLibrary
        else:
            return False
        return bool(api.does_asset_exist(asset_path))
    except Exception as e:
        _log_warning("[GenAnim] Could not verify asset existence for "
                     "{}: {}".format(asset_path, e))
        return False


def lookup(action_text):
    # type: (str) -> Optional[str]
    """
    Look up a previously generated animation for an action text.

    Args:
        action_text: The action text used at generation time.

    Returns:
        The recorded asset path, but only when the manifest has an entry
        AND the asset still exists in the project. None otherwise (also
        outside the editor, where existence cannot be verified). Never
        raises.
    """
    try:
        entry = _load_manifest().get(_manifest_key(action_text))
        if not isinstance(entry, dict):
            return None

        asset_path = entry.get('asset_path')
        if not asset_path:
            return None

        if unreal is None:
            _log("[GenAnim] Manifest hit for '{}' but asset existence "
                 "cannot be verified outside the editor; ignoring it".format(
                     _normalize_description(action_text)))
            return None

        if not _asset_still_exists(asset_path):
            _log_warning("[GenAnim] Manifest entry for '{}' points to a "
                         "missing asset ({}); it will be regenerated".format(
                             _normalize_description(action_text), asset_path))
            return None

        return str(asset_path)
    except Exception as e:
        _log_warning("[GenAnim] Manifest lookup failed: {}".format(e))
        return None


def record(action_text, asset_path, provider):
    # type: (str, str, str) -> bool
    """
    Record a generated animation in the manifest.

    Args:
        action_text: The action text used at generation time.
        asset_path: Imported asset path in the project.
        provider: Provider name that generated the clip.

    Returns:
        True when the manifest was written; False on failure (logged).
        Never raises.
    """
    try:
        if not action_text or not asset_path:
            _log_warning("[GenAnim] Not recording manifest entry: missing "
                         "action text or asset path")
            return False

        manifest = _load_manifest()
        manifest[_manifest_key(action_text)] = {
            'description': _normalize_description(action_text),
            'asset_path': str(asset_path),
            'provider': str(provider or 'unknown'),
            'created': datetime.now().isoformat()
        }
        return _save_manifest(manifest)
    except Exception as e:
        _log_warning("[GenAnim] Manifest record failed: {}".format(e))
        return False

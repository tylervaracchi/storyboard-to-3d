# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Gen3D Importer

Imports a downloaded model file (FBX or GLB/GLTF) into the Unreal project
under /Game/StoryboardTo3D/Generated using unreal.AssetImportTask executed
through AssetToolsHelpers. FBX files get an hasattr-guarded FbxImportUI
configured for static-mesh (no skeleton) import; GLB/GLTF files rely on
the Interchange framework, which is the default glTF import pipeline in
UE 5.x, so no legacy options are attached for them.

import_generated_model() never raises: every failure path logs a warning
and returns None so callers can fall through to their existing fallbacks.
"""

import os
import re
from typing import List, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor; import_generated_model then
    # logs and returns None.
    unreal = None


GENERATED_ASSET_PATH = '/Game/StoryboardTo3D/Generated'


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


def sanitize_asset_name(name):
    # type: (str) -> str
    """
    Sanitize a free-form entity name into a valid UE asset name.

    Keeps letters, digits, and underscores; collapses everything else to
    single underscores; prefixes names that start with a digit.

    Args:
        name: Free-form name (e.g. 'old wooden rocking-chair').

    Returns:
        A safe asset name (e.g. 'old_wooden_rocking_chair').
    """
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(name or '')).strip('_')
    if not cleaned:
        cleaned = 'GeneratedAsset'
    if cleaned[0].isdigit():
        cleaned = 'Gen_' + cleaned
    return cleaned


def import_generated_model(file_path, asset_name):
    # type: (str, str) -> Optional[str]
    """
    Import a generated model file into the project.

    Args:
        file_path: Local path to the downloaded model (.fbx, .glb, .gltf).
        asset_name: Desired asset name (sanitized automatically).

    Returns:
        The imported StaticMesh asset object path (e.g.
        '/Game/StoryboardTo3D/Generated/chair.chair'), or None on any
        failure. Never raises.
    """
    try:
        if unreal is None:
            _log_warning("[Gen3D] Cannot import model: unreal module "
                         "unavailable (running outside the editor?)")
            return None

        if not file_path or not os.path.isfile(str(file_path)):
            _log_warning("[Gen3D] Cannot import model: file not found: "
                         "{}".format(file_path))
            return None

        if not hasattr(unreal, 'AssetImportTask') or \
                not hasattr(unreal, 'AssetToolsHelpers'):
            _log_warning("[Gen3D] Cannot import model: AssetImportTask / "
                         "AssetToolsHelpers unavailable in this engine "
                         "version")
            return None

        name = sanitize_asset_name(asset_name)
        extension = os.path.splitext(str(file_path))[1].lower()

        task = unreal.AssetImportTask()
        task.filename = str(file_path)
        task.destination_path = GENERATED_ASSET_PATH
        task.destination_name = name
        task.automated = True
        task.save = True
        try:
            task.replace_existing = True
        except Exception:
            pass  # older engines may lack the property; re-import prompts

        if extension == '.fbx':
            options = _build_fbx_static_mesh_options()
            if options is not None:
                try:
                    task.options = options
                except Exception as e:
                    _log_warning("[Gen3D] Could not attach FBX import "
                                 "options ({}); importing with engine "
                                 "defaults".format(e))
        elif extension in ('.glb', '.gltf'):
            _log("[Gen3D] Importing {} via the Interchange framework "
                 "(the default glTF pipeline in UE 5.x); no legacy import "
                 "options attached".format(extension))
        else:
            _log_warning("[Gen3D] Unrecognized model extension '{}'; "
                         "attempting import with engine defaults".format(
                             extension))

        _log("[Gen3D] Importing '{}' from {} into {}".format(
            name, file_path, GENERATED_ASSET_PATH))
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset_tools.import_asset_tasks([task])

        imported_paths = _get_imported_paths(task)

        # Prefer a StaticMesh among the imported objects (glTF Interchange
        # imports can also create materials and textures).
        static_mesh_path = _pick_static_mesh_path(imported_paths)
        if static_mesh_path:
            _log("[Gen3D] Imported StaticMesh: {}".format(static_mesh_path))
            return static_mesh_path

        if imported_paths:
            fallback = _normalize_object_path(imported_paths[0])
            _log_warning("[Gen3D] No StaticMesh identified among imported "
                         "objects; returning first imported path: "
                         "{}".format(fallback))
            return fallback

        # Last resort: probe the expected destination paths.
        for candidate in (
                '{}/{}'.format(GENERATED_ASSET_PATH, name),
                '{}/{}/{}'.format(GENERATED_ASSET_PATH, name, name)):
            if _asset_exists(candidate):
                object_path = _normalize_object_path(candidate)
                _log("[Gen3D] Imported asset found by probing: {}".format(
                    object_path))
                return object_path

        _log_warning("[Gen3D] Import of '{}' produced no locatable asset "
                     "under {}".format(name, GENERATED_ASSET_PATH))
        return None

    except Exception as e:
        _log_warning("[Gen3D] Model import failed: {}".format(e))
        return None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _build_fbx_static_mesh_options():
    """
    Build hasattr-guarded FbxImportUI options for a static-mesh (no
    skeleton) import. Returns None when unavailable; the import then
    proceeds with engine defaults.
    """
    if not hasattr(unreal, 'FbxImportUI'):
        _log_warning("[Gen3D] unreal.FbxImportUI unavailable; importing "
                     "FBX with engine defaults")
        return None

    try:
        options = unreal.FbxImportUI()

        for prop, value in (
                ('import_mesh', True),
                ('import_as_skeletal', False),
                ('import_animations', False),
                ('import_materials', True),
                ('import_textures', True),
                ('create_physics_asset', False)):
            try:
                options.set_editor_property(prop, value)
            except Exception:
                pass  # property missing in this engine version

        # Combine sub-meshes into a single StaticMesh where supported.
        try:
            mesh_data = options.get_editor_property(
                'static_mesh_import_data')
            if mesh_data is not None:
                try:
                    mesh_data.set_editor_property('combine_meshes', True)
                except Exception:
                    pass
        except Exception:
            pass

        return options
    except Exception as e:
        _log_warning("[Gen3D] Could not configure FbxImportUI ({}); "
                     "importing FBX with engine defaults".format(e))
        return None


def _get_imported_paths(task):
    # type: (object) -> List[str]
    """Read imported_object_paths off the finished task, hasattr-guarded
    with a get_editor_property fallback. Returns [] when unavailable."""
    paths = None
    try:
        if hasattr(task, 'imported_object_paths'):
            paths = task.imported_object_paths
    except Exception:
        paths = None

    if paths is None:
        try:
            paths = task.get_editor_property('imported_object_paths')
        except Exception:
            paths = None

    if not paths:
        return []
    try:
        return [str(p) for p in paths if p]
    except Exception:
        return []


def _pick_static_mesh_path(imported_paths):
    # type: (List[str]) -> Optional[str]
    """Return the first imported path whose asset loads as a StaticMesh."""
    if not imported_paths or not hasattr(unreal, 'StaticMesh'):
        return None

    for path in imported_paths:
        object_path = _normalize_object_path(path)
        try:
            asset = _load_asset(object_path)
            if asset is not None and isinstance(asset, unreal.StaticMesh):
                return object_path
        except Exception:
            continue
    return None


def _normalize_object_path(path):
    # type: (str) -> str
    """Turn a package path '/Game/X/Name' into an object path
    '/Game/X/Name.Name'. Paths that already contain a '.' pass through."""
    path = str(path)
    tail = path.rsplit('/', 1)[-1]
    if '.' in tail:
        return path
    return '{}.{}'.format(path, tail)


def _get_editor_asset_api():
    """EditorAssetSubsystem when available, else EditorAssetLibrary.
    Returns None when neither exists (logged by callers)."""
    try:
        if hasattr(unreal, 'get_editor_subsystem') and \
                hasattr(unreal, 'EditorAssetSubsystem'):
            return unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        if hasattr(unreal, 'EditorAssetLibrary'):
            return unreal.EditorAssetLibrary
    except Exception:
        pass
    return None


def _asset_exists(asset_path):
    # type: (str) -> bool
    """Guarded EditorAssetLibrary/Subsystem does_asset_exist check."""
    api = _get_editor_asset_api()
    if api is None:
        return False
    try:
        return bool(api.does_asset_exist(asset_path))
    except Exception:
        return False


def _load_asset(asset_path):
    """Guarded EditorAssetLibrary/Subsystem load_asset; None on failure."""
    api = _get_editor_asset_api()
    if api is None:
        return None
    try:
        return api.load_asset(asset_path)
    except Exception:
        return None

# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
GenAnim Importer

Imports a downloaded animation file (FBX or GLB/GLTF) into the Unreal
project under /Game/StoryboardTo3D/GeneratedAnims using
unreal.AssetImportTask executed through AssetToolsHelpers, mirroring
core/gen3d/importer.py.

FBX files get an hasattr-guarded FbxImportUI configured for a skeletal
import with animations (import_as_skeletal + import_animations): the
generated clips arrive as a proxy character performing the motion, so
the import creates a SkeletalMesh, a Skeleton, and the AnimSequence in
one pass. GLB/GLTF files rely on the Interchange framework, which is the
default glTF import pipeline in UE 5.x and creates the same asset set,
so no legacy options are attached for them.

RETARGETING NOTE: the imported AnimSequence lives on the PROVIDER's
skeleton (Mixamo-convention when the one-time provider setup from the
provider docstrings is followed). Playing it on a project character goes
through the existing IK Retargeter workflow: one IKRig asset per skeleton
plus an IK Retargeter asset per show character remaps every generated
clip. This module only lands the raw clip in the project; it does not
retarget.

import_generated_animation() never raises: every failure path logs a
warning and returns None so callers can fall through to their existing
fallbacks.
"""

import os
import re
from typing import List, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor; import_generated_animation
    # then logs and returns None.
    unreal = None


GENERATED_ANIM_PATH = '/Game/StoryboardTo3D/GeneratedAnims'


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
    Sanitize free-form action text into a valid UE asset name.

    Keeps letters, digits, and underscores; collapses everything else to
    single underscores; prefixes names that start with a digit.

    Args:
        name: Free-form name (e.g. 'nervously pacing around').

    Returns:
        A safe asset name (e.g. 'nervously_pacing_around').
    """
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(name or '')).strip('_')
    if not cleaned:
        cleaned = 'GeneratedAnim'
    if cleaned[0].isdigit():
        cleaned = 'Anim_' + cleaned
    return cleaned


def import_generated_animation(file_path, asset_name, skeleton_path=None):
    # type: (str, str, Optional[str]) -> Optional[str]
    """
    Import a generated animation file into the project.

    Args:
        file_path: Local path to the downloaded clip (.fbx, .glb, .gltf).
        asset_name: Desired asset name (sanitized automatically).
        skeleton_path: Optional existing Skeleton asset path. When set,
            FBX clips import ANIMATION-ONLY onto that skeleton, so the
            resulting AnimSequence is directly playable on the character
            (and passes the scene builder's skeleton-compatibility
            guard). Without it the import creates its own mesh+skeleton
            and the clip needs IK retargeting.

    Returns:
        The imported AnimSequence asset object path (e.g.
        '/Game/StoryboardTo3D/GeneratedAnims/walk.walk'), or the first
        imported asset path when no AnimSequence can be identified, or
        None on any failure. Never raises.
    """
    try:
        if unreal is None:
            _log_warning("[GenAnim] Cannot import clip: unreal module "
                         "unavailable (running outside the editor?)")
            return None

        if not file_path or not os.path.isfile(str(file_path)):
            _log_warning("[GenAnim] Cannot import clip: file not found: "
                         "{}".format(file_path))
            return None

        if not hasattr(unreal, 'AssetImportTask') or \
                not hasattr(unreal, 'AssetToolsHelpers'):
            _log_warning("[GenAnim] Cannot import clip: AssetImportTask / "
                         "AssetToolsHelpers unavailable in this engine "
                         "version")
            return None

        name = sanitize_asset_name(asset_name)
        extension = os.path.splitext(str(file_path))[1].lower()

        if extension == '.bvh':
            # BVH needs the Interchange BVH translator (UE 5.6+) or a
            # Blender conversion pass; neither is assumed here.
            _log_warning("[GenAnim] BVH import is not supported by this "
                         "importer; request FBX or GLB from the provider")
            return None

        task = unreal.AssetImportTask()
        task.filename = str(file_path)
        task.destination_path = GENERATED_ANIM_PATH
        task.destination_name = name
        task.automated = True
        task.save = True
        try:
            task.replace_existing = True
        except Exception:
            pass  # older engines may lack the property; re-import prompts

        target_skeleton = None
        if skeleton_path:
            try:
                api = _get_editor_asset_api()
                target_skeleton = api.load_asset(str(skeleton_path)) if api else None
                if target_skeleton is None:
                    _log_warning("[GenAnim] Target skeleton not found: {}; "
                                 "importing standalone".format(skeleton_path))
            except Exception as e:
                _log_warning("[GenAnim] Could not load target skeleton "
                             "({}); importing standalone".format(e))
                target_skeleton = None

        if extension == '.fbx':
            options = (_build_fbx_anim_only_options(target_skeleton)
                       if target_skeleton is not None
                       else _build_fbx_skeletal_anim_options())
            if options is not None:
                try:
                    task.options = options
                except Exception as e:
                    _log_warning("[GenAnim] Could not attach FBX import "
                                 "options ({}); importing with engine "
                                 "defaults".format(e))
        elif extension in ('.glb', '.gltf'):
            _log("[GenAnim] Importing {} via the Interchange framework "
                 "(the default glTF pipeline in UE 5.x); no legacy import "
                 "options attached".format(extension))
        else:
            _log_warning("[GenAnim] Unrecognized clip extension '{}'; "
                         "attempting import with engine defaults".format(
                             extension))

        _log("[GenAnim] Importing '{}' from {} into {}".format(
            name, file_path, GENERATED_ANIM_PATH))
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset_tools.import_asset_tasks([task])

        imported_paths = _get_imported_paths(task)

        # FORCE-SAVE to disk: imports left memory-only vanish on editor
        # close/unattended exit (matches the gen3d importer fix)
        try:
            api = _get_editor_asset_api()
            if api is not None:
                for p in imported_paths or []:
                    try:
                        api.save_asset(_normalize_object_path(p),
                                       only_if_is_dirty=False)
                    except Exception:
                        continue
                try:
                    api.save_directory(GENERATED_ANIM_PATH,
                                       only_if_is_dirty=True, recursive=True)
                except Exception:
                    pass
        except Exception as e:
            _log_warning("[GenAnim] Could not force-save imported clip: "
                         "{}".format(e))

        # Prefer an AnimSequence among the imported objects (skeletal FBX
        # and glTF Interchange imports also create the mesh, skeleton, and
        # materials).
        anim_path = _pick_anim_sequence_path(imported_paths)
        if anim_path:
            _log("[GenAnim] Imported AnimSequence: {}".format(anim_path))
            return anim_path

        if imported_paths:
            fallback = _normalize_object_path(imported_paths[0])
            _log_warning("[GenAnim] No AnimSequence identified among "
                         "imported objects; returning first imported path: "
                         "{}".format(fallback))
            return fallback

        # Last resort: probe the expected destination paths, including the
        # '<name>_Anim' suffix the FBX importer commonly appends.
        for candidate in (
                '{}/{}_Anim'.format(GENERATED_ANIM_PATH, name),
                '{}/{}'.format(GENERATED_ANIM_PATH, name),
                '{}/{}/{}'.format(GENERATED_ANIM_PATH, name, name)):
            if _asset_exists(candidate):
                object_path = _normalize_object_path(candidate)
                _log("[GenAnim] Imported asset found by probing: {}".format(
                    object_path))
                return object_path

        _log_warning("[GenAnim] Import of '{}' produced no locatable asset "
                     "under {}".format(name, GENERATED_ANIM_PATH))
        return None

    except Exception as e:
        _log_warning("[GenAnim] Clip import failed: {}".format(e))
        return None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _build_fbx_anim_only_options(target_skeleton):
    """
    Build hasattr-guarded FbxImportUI options for an ANIMATION-ONLY
    import onto an existing Skeleton asset (the standard 'import
    animation onto skeleton' flow). Returns None when unavailable.
    """
    if not hasattr(unreal, 'FbxImportUI'):
        _log_warning("[GenAnim] unreal.FbxImportUI unavailable; importing "
                     "FBX with engine defaults")
        return None
    try:
        options = unreal.FbxImportUI()
        for prop, value in (
                ('import_mesh', False),
                ('import_as_skeletal', True),
                ('import_animations', True),
                ('import_materials', False),
                ('import_textures', False),
                ('create_physics_asset', False),
                ('skeleton', target_skeleton),
                ('automated_import_should_detect_type', False)):
            try:
                options.set_editor_property(prop, value)
            except Exception:
                pass  # property missing in this engine version
        try:
            options.set_editor_property(
                'mesh_type_to_import',
                unreal.FBXImportType.FBXIT_ANIMATION)
        except Exception:
            pass
        _log("[GenAnim] FBX anim-only import onto existing skeleton: "
             "{}".format(target_skeleton.get_path_name()))
        return options
    except Exception as e:
        _log_warning("[GenAnim] Could not configure anim-only FbxImportUI "
                     "({}); importing with engine defaults".format(e))
        return None


def _build_fbx_skeletal_anim_options():
    """
    Build hasattr-guarded FbxImportUI options for a skeletal-mesh import
    with animations. Returns None when unavailable; the import then
    proceeds with engine defaults.
    """
    if not hasattr(unreal, 'FbxImportUI'):
        _log_warning("[GenAnim] unreal.FbxImportUI unavailable; importing "
                     "FBX with engine defaults")
        return None

    try:
        options = unreal.FbxImportUI()

        for prop, value in (
                ('import_mesh', True),
                ('import_as_skeletal', True),
                ('import_animations', True),
                ('import_materials', False),
                ('import_textures', False),
                ('create_physics_asset', False)):
            try:
                options.set_editor_property(prop, value)
            except Exception:
                pass  # property missing in this engine version

        # Force the skeletal-mesh import type where the enum exists.
        try:
            if hasattr(unreal, 'FBXImportType'):
                options.set_editor_property(
                    'mesh_type_to_import',
                    unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        except Exception:
            pass

        # Import bone tracks at the exported length where supported.
        try:
            anim_data = options.get_editor_property(
                'anim_sequence_import_data')
            if anim_data is not None:
                for prop, value in (
                        ('import_bone_tracks', True),
                        ('import_custom_attribute', True)):
                    try:
                        anim_data.set_editor_property(prop, value)
                    except Exception:
                        pass
        except Exception:
            pass

        return options
    except Exception as e:
        _log_warning("[GenAnim] Could not configure FbxImportUI ({}); "
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


def _pick_anim_sequence_path(imported_paths):
    # type: (List[str]) -> Optional[str]
    """Return the first imported path whose asset loads as an
    AnimSequence."""
    if not imported_paths or not hasattr(unreal, 'AnimSequence'):
        return None

    for path in imported_paths:
        object_path = _normalize_object_path(path)
        try:
            asset = _load_asset(object_path)
            if asset is not None and isinstance(asset, unreal.AnimSequence):
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

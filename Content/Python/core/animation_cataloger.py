# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
AI cataloging for animation libraries.

For each AnimSequence in a show's animation_library.json this module
spawns a compatible skeletal mesh far from the user's scene, puts it in
single-node animation mode, samples three poses (10/50/90 percent of the
clip's play length), captures each pose with the same SceneCapture2D +
RTF_RGBA8 + PNG export chain core/thumbnail_generator.py uses, composes
the three frames into one side-by-side contact sheet with PIL, and asks
the configured vision provider what single action the character is
performing. The answer fills the entry's 'description' field and empty
or placeholder alias lists so core/animation_matcher.py can match free
action text against meaning instead of raw key names.

Library file convention matches core/animation_matcher.py: the per-show
file is <shows_root>/<show>/animation_library.json, with a repository
fallback at samples/animation_library.sample.json. The samples file is
READ-ONLY here; catalog results are always saved to the show's own
animation_library.json.

Nothing in this module raises to callers: describe_animation returns
None on any failure and catalog_animation_library returns a summary
dict whose 'failed' list carries the misses. All temporary actors are
destroyed in a finally block so nothing is ever left in the level.
"""

import json
import math
import shutil
import tempfile
import traceback
from pathlib import Path

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:  # Running outside the Unreal editor (tests, tooling)
    unreal = None
    UNREAL_AVAILABLE = False

try:
    from ai_vision.scene_capture_rig import (
        get_editor_world,
        spawn_capture_actor,
        get_capture_component,
        configure_capture_component,
        resolve_export_function,
    )
    RIG_HELPERS_AVAILABLE = True
except ImportError:
    RIG_HELPERS_AVAILABLE = False

# Reuse the exact spawn/bounds/render-target/light plumbing the asset
# thumbnail generator already verified against a live 5.8 editor
# (including the TextureRenderTargetFormat RTF_RGBA8 lesson: float
# render targets silently export EXR bytes into .png files).
try:
    from core.thumbnail_generator import (
        MIN_BOUNDS_RADIUS,
        _compute_camera_transform,
        _destroy_actor,
        _get_actor_bounds,
        _level_has_light,
        _load_asset,
        _make_ldr_render_target,
        _spawn_asset_actor,
        _spawn_temp_light,
        is_valid_png,
    )
    THUMBNAIL_HELPERS_AVAILABLE = True
except ImportError:
    THUMBNAIL_HELPERS_AVAILABLE = False

# Single source of truth for the samples fallback location.
try:
    from core.animation_matcher import SAMPLE_LIBRARY_PATH
except Exception:
    # core/animation_cataloger.py -> Content/Python/core; repo root is
    # 3 levels up (same computation animation_matcher uses).
    SAMPLE_LIBRARY_PATH = (Path(__file__).resolve().parents[3]
                           / 'samples' / 'animation_library.sample.json')

# Staging area far from the origin and far below the ground plane,
# offset from the thumbnail generator's staging spot so concurrent
# captures never overlap.
STAGING_LOCATION = (1000000.0, 200000.0, -100000.0)
POSE_FRACTIONS = (0.10, 0.50, 0.90)
CAPTURE_SIZE = 512
# Alias values that count as "not filled in yet".
PLACEHOLDER_ALIASES = ('todo', 'tbd', 'placeholder', 'none', 'n/a')
MAX_ALIASES = 8

VISION_PROMPT = (
    "These three frames are pose samples from ONE character animation "
    "clip, in time order: left is the start, middle is the midpoint, "
    "right is the end. What single action is the character performing "
    "across these three frames? Respond with ONLY a JSON object and no "
    "other text, in exactly this form: "
    '{"action": "<one short lowercase verb phrase>", '
    '"aliases": ["<alias1>", "<alias2>", "<alias3>", "<alias4>", '
    '"<alias5>"]} '
    "where the aliases are 5 lowercase single-word or short synonyms "
    "for the action."
)


def _log(msg):
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log('[AnimationCataloger] {0}'.format(msg))
    else:
        print('[AnimationCataloger] {0}'.format(msg))


def _warn(msg):
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning('[AnimationCataloger] {0}'.format(msg))
    else:
        print('[AnimationCataloger] WARNING: {0}'.format(msg))


def _error(msg):
    if unreal is not None and hasattr(unreal, 'log_error'):
        unreal.log_error('[AnimationCataloger] {0}'.format(msg))
    else:
        print('[AnimationCataloger] ERROR: {0}'.format(msg))


# ----------------------------------------------------------------------
# Animation / mesh resolution helpers (every unreal call guarded)
# ----------------------------------------------------------------------

def _get_play_length(anim):
    """Return the clip length in seconds, or None. Never raises."""
    try:
        if hasattr(anim, 'get_play_length'):
            return float(anim.get_play_length())
    except Exception as e:
        _warn('get_play_length failed: {0}'.format(e))
    try:
        value = anim.get_editor_property('sequence_length')
        if value is not None:
            return float(value)
    except Exception as e:
        _warn('sequence_length property read failed: {0}'.format(e))
    return None


def _find_mesh_for_skeleton(skeleton):
    """Find a SkeletalMesh asset path whose 'Skeleton' tag matches.

    Uses the asset registry (SkeletalMesh assets carry their skeleton as
    an asset tag in export-text form, which contains the skeleton's
    object path). Returns an asset path string or None. Never raises.
    """
    try:
        if skeleton is None or not hasattr(unreal, 'AssetRegistryHelpers'):
            return None
        try:
            skeleton_path = str(skeleton.get_path_name())
        except Exception as e:
            _warn('Could not read the skeleton path: {0}'.format(e))
            return None
        if not skeleton_path:
            return None

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        ar_filter = unreal.ARFilter()
        ar_filter.package_paths = ['/Game']
        ar_filter.recursive_paths = True
        ar_filter.class_paths = [
            unreal.TopLevelAssetPath('/Script/Engine', 'SkeletalMesh'),
        ]
        candidates = registry.get_assets(ar_filter) or []

        for asset_data in candidates:
            tag_value = None
            try:
                if hasattr(asset_data, 'get_tag_value'):
                    tag_value = asset_data.get_tag_value('Skeleton')
            except Exception:
                tag_value = None
            if not tag_value or skeleton_path not in str(tag_value):
                continue
            if hasattr(asset_data, 'get_soft_object_path'):
                return str(asset_data.get_soft_object_path())
            if hasattr(asset_data, 'object_path'):
                return str(asset_data.object_path)
        return None
    except Exception as e:
        _warn('Skeletal mesh registry lookup failed: {0}'.format(e))
        return None


def _resolve_compatible_mesh(anim, skeletal_mesh_path=None):
    """Load a skeletal mesh compatible with the animation's skeleton.

    Tries the asset registry (meshes using the anim's skeleton) first,
    then the caller-provided path. Returns a loaded mesh asset or None.
    """
    skeleton = None
    try:
        skeleton = anim.get_editor_property('skeleton')
    except Exception as e:
        _warn('Could not read the animation skeleton: {0}'.format(e))

    mesh_path = _find_mesh_for_skeleton(skeleton)
    if mesh_path:
        mesh = _load_asset(mesh_path)
        if mesh is not None:
            _log('Resolved compatible mesh via skeleton: {0}'.format(mesh_path))
            return mesh
        _warn('Registry-matched mesh failed to load: {0}'.format(mesh_path))

    if skeletal_mesh_path:
        mesh = _load_asset(str(skeletal_mesh_path))
        if mesh is not None:
            _log('Using provided skeletal mesh: {0}'.format(skeletal_mesh_path))
            return mesh
        _warn('Provided skeletal mesh failed to load: {0}'.format(
            skeletal_mesh_path))
    return None


def _get_skeletal_component(actor):
    """Return the actor's SkeletalMeshComponent, or None. Never raises."""
    try:
        component = None
        if hasattr(actor, 'skeletal_mesh_component'):
            component = actor.skeletal_mesh_component
        if component is None and hasattr(actor, 'get_component_by_class') \
                and hasattr(unreal, 'SkeletalMeshComponent'):
            component = actor.get_component_by_class(
                unreal.SkeletalMeshComponent)
        return component
    except Exception as e:
        _warn('Could not get a SkeletalMeshComponent: {0}'.format(e))
        return None


def _enter_single_node_mode(component, anim):
    """Set single-node animation mode with the clip assigned, paused.

    Returns True when set_animation succeeded, False otherwise.
    """
    try:
        if hasattr(unreal, 'AnimationMode') and \
                hasattr(component, 'set_animation_mode'):
            component.set_animation_mode(
                unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        else:
            _warn('AnimationMode/set_animation_mode unavailable; '
                  'continuing without explicit mode switch')
        if not hasattr(component, 'set_animation'):
            _warn('set_animation unavailable on the component')
            return False
        # A skeleton mismatch raises here; caught by the outer except
        component.set_animation(anim)
        try:
            if hasattr(component, 'set_playing'):
                component.set_playing(False)
            elif hasattr(component, 'stop'):
                component.stop()
        except Exception as e:
            _warn('Could not pause playback: {0}'.format(e))
        return True
    except Exception as e:
        _warn('Single-node setup failed: {0} (skeleton mismatch?)'.format(e))
        return False


def _refresh_pose(component):
    """Force the scrubbed pose to be evaluated before capture."""
    try:
        if hasattr(component, 'refresh_bone_transforms'):
            component.refresh_bone_transforms()
    except Exception as e:
        _warn('refresh_bone_transforms failed: {0}'.format(e))


def _set_animation_position(component, seconds):
    """Scrub the single-node animation to a time in seconds.

    Tries set_position (with and without the fire_notifies argument),
    then the 'position' editor property. Returns True on success.
    """
    seconds = float(seconds)
    if hasattr(component, 'set_position'):
        try:
            component.set_position(seconds, False)
            _refresh_pose(component)
            return True
        except TypeError:
            try:
                component.set_position(seconds)
                _refresh_pose(component)
                return True
            except Exception as e:
                _warn('set_position(seconds) failed: {0}'.format(e))
        except Exception as e:
            _warn('set_position failed: {0}'.format(e))
    try:
        component.set_editor_property('position', seconds)
        _refresh_pose(component)
        return True
    except Exception as e:
        _warn("Could not set the 'position' property: {0}".format(e))
    return False


# ----------------------------------------------------------------------
# Contact sheet + vision helpers
# ----------------------------------------------------------------------

def _compose_contact_sheet(frame_paths, output_path):
    """Paste the pose PNGs side by side into one contact sheet.

    Args:
        frame_paths: list of PNG paths in time order.
        output_path: where to save the composed sheet.

    Returns:
        The output path when the sheet was written, None otherwise.
        Never raises.
    """
    try:
        from PIL import Image
    except ImportError:
        _warn('PIL (pillow) not installed; cannot compose the contact sheet')
        return None
    images = []
    try:
        for path in frame_paths:
            img = Image.open(str(path))
            img.load()
            images.append(img.convert('RGB'))
        if not images:
            return None
        height = max(im.size[1] for im in images)
        total_width = sum(im.size[0] for im in images)
        sheet = Image.new('RGB', (total_width, height), (24, 24, 24))
        x_offset = 0
        for im in images:
            sheet.paste(im, (x_offset, 0))
            x_offset += im.size[0]
        sheet.save(str(output_path), format='PNG')
        return output_path if Path(str(output_path)).exists() else None
    except Exception as e:
        _warn('Contact sheet composition failed: {0}'.format(e))
        return None
    finally:
        for im in images:
            try:
                im.close()
            except Exception:
                pass


def _parse_vision_response(response_text):
    """Extract the action/aliases dict from a model reply.

    Returns:
        {'action_description': str, 'aliases': [str, ...]} or None.
    """
    if not response_text or not isinstance(response_text, str):
        _warn('Vision reply was empty')
        return None

    # Fast path: the prompt asks for bare JSON, so try json.loads first
    data = None
    try:
        data = json.loads(response_text)
    except (ValueError, TypeError):
        data = None

    # Robust path: markdown fences, prose wrapping, malformed JSON
    if data is None:
        try:
            from core.json_extractor import RobustJSONExtractor
            data = RobustJSONExtractor.extract_and_parse(response_text)
        except Exception:
            data = None

    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        _warn('Vision reply carried no JSON object')
        return None

    action = (data.get('action') or data.get('action_description')
              or data.get('description'))
    if not action or not isinstance(action, str) or not action.strip():
        _warn('Vision reply carried no action field')
        return None
    action = action.strip().lower()

    aliases = []
    raw_aliases = data.get('aliases') or data.get('synonyms') or []
    if isinstance(raw_aliases, list):
        for alias in raw_aliases:
            text = str(alias).strip().lower()
            if text and text != action and text not in aliases:
                aliases.append(text)

    return {'action_description': action, 'aliases': aliases[:MAX_ALIASES]}


def _describe_sheet_with_vision(sheet_path, anim_asset_path):
    """Send the contact sheet to the configured vision provider.

    Returns:
        {'action_description': str, 'aliases': [...]} or None.
        Never raises.
    """
    try:
        from core.ai_providers.provider_factory import AIProviderFactory
    except Exception as e:
        _warn('Provider factory unavailable: {0}'.format(e))
        return None
    try:
        provider = AIProviderFactory.create_provider('auto')
    except Exception as e:
        _warn('Provider creation failed: {0}'.format(e))
        return None
    if provider is None:
        _warn('No vision provider configured; cannot describe {0}'.format(
            anim_asset_path))
        return None
    try:
        response = provider.analyze_images(
            [str(sheet_path)], VISION_PROMPT, max_tokens=300)
    except Exception as e:
        _warn('Vision call failed for {0}: {1}'.format(anim_asset_path, e))
        return None
    if not isinstance(response, dict) or not response.get('success'):
        err = 'invalid provider response'
        if isinstance(response, dict):
            err = response.get('error', 'unknown provider error')
        _warn('Vision analysis unsuccessful for {0}: {1}'.format(
            anim_asset_path, err))
        return None
    return _parse_vision_response(response.get('response', ''))


def _cleanup_temp_dir(temp_dir):
    """Remove the temporary frame directory; guarded, never raises."""
    if not temp_dir:
        return
    try:
        shutil.rmtree(str(temp_dir), ignore_errors=True)
    except Exception as e:
        _warn('Could not remove temp dir {0}: {1}'.format(temp_dir, e))


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def describe_animation(anim_asset_path, skeletal_mesh_path=None):
    """Describe what an animation clip depicts using the vision provider.

    Loads the AnimSequence, resolves a compatible skeletal mesh (from
    the anim's skeleton via the asset registry, else the provided path),
    spawns the mesh far from the user's scene in single-node animation
    mode, samples poses at 10/50/90 percent of the play length, captures
    each pose to a PNG, composes a side-by-side contact sheet with PIL,
    and asks the configured vision provider for one short action phrase
    plus alias synonyms.

    Args:
        anim_asset_path: Content Browser path of the AnimSequence.
        skeletal_mesh_path: optional SkeletalMesh path used when the
            asset registry finds no mesh for the anim's skeleton.

    Returns:
        {'action_description': str, 'aliases': [str, ...]} or None.
        Never raises; every failure logs a reason. All temporary actors
        are destroyed in a finally block.
    """
    subject = None
    capture = None
    light = None
    temp_dir = None
    try:
        if not UNREAL_AVAILABLE:
            _warn('unreal module unavailable (not running in the editor)')
            return None
        if not RIG_HELPERS_AVAILABLE or not THUMBNAIL_HELPERS_AVAILABLE:
            _error('Capture helpers unavailable (scene_capture_rig or '
                   'thumbnail_generator failed to import)')
            return None
        if not anim_asset_path:
            _warn('Empty animation asset path; nothing to describe')
            return None

        # Spawning into a null world crashes the editor natively, so
        # verify a level is actually loaded before touching actor APIs
        if get_editor_world() is None:
            _error('No editor world is loaded; open a level before '
                   'cataloging animations')
            return None

        anim = _load_asset(str(anim_asset_path))
        if anim is None:
            _warn('Could not load animation asset: {0}'.format(anim_asset_path))
            return None
        anim_cls = (getattr(unreal, 'AnimSequenceBase', None)
                    or getattr(unreal, 'AnimSequence', None))
        if anim_cls is not None and not isinstance(anim, anim_cls):
            _warn('{0} is not an animation sequence (class {1})'.format(
                anim_asset_path, type(anim).__name__))
            return None

        play_length = _get_play_length(anim)
        if play_length is None or play_length <= 0.0:
            _warn('Could not read a positive play length for {0}; '
                  'sampling at time zero only'.format(anim_asset_path))
            play_length = 0.0

        mesh = _resolve_compatible_mesh(anim, skeletal_mesh_path)
        if mesh is None:
            _warn('No compatible skeletal mesh found for {0}'.format(
                anim_asset_path))
            return None

        staging = unreal.Vector(*STAGING_LOCATION)
        subject = _spawn_asset_actor(mesh, staging)
        if subject is None:
            _warn('Could not spawn a skeletal mesh actor for {0}'.format(
                anim_asset_path))
            return None

        component = _get_skeletal_component(subject)
        if component is None:
            _warn('No SkeletalMeshComponent on the spawned actor')
            return None
        if not _enter_single_node_mode(component, anim):
            return None

        origin, extent = _get_actor_bounds(subject)
        if origin is None or extent is None:
            _warn('Could not read bounds for the spawned mesh')
            return None
        radius = math.sqrt(extent.x * extent.x + extent.y * extent.y
                           + extent.z * extent.z)
        radius = max(radius, MIN_BOUNDS_RADIUS)

        cam_location, cam_rotation = _compute_camera_transform(origin, radius)
        capture = spawn_capture_actor(cam_location, cam_rotation)
        if capture is None:
            _warn('Could not spawn a SceneCapture2D')
            return None
        comp = get_capture_component(capture)
        if comp is None:
            _warn('No SceneCaptureComponent2D on the capture actor')
            return None
        rt = _make_ldr_render_target(CAPTURE_SIZE)
        if rt is None:
            _warn('Could not create a {0}x{0} render target'.format(
                CAPTURE_SIZE))
            return None
        configure_capture_component(comp, rt)

        if not _level_has_light():
            _log('Level has no lights; spawning a temporary DirectionalLight')
            light = _spawn_temp_light(cam_rotation)

        export_fn, export_info = resolve_export_function()
        if export_fn is None:
            _error('No render target export function found; tried: '
                   '{0}'.format(', '.join(export_info)))
            return None

        temp_dir = Path(tempfile.mkdtemp(prefix='sb3d_anim_catalog_'))
        frame_paths = []
        for index, fraction in enumerate(POSE_FRACTIONS):
            if not _set_animation_position(component, play_length * fraction):
                _warn('Could not scrub to {0:.0f} percent; capturing the '
                      'current pose'.format(fraction * 100.0))
            if hasattr(comp, 'capture_scene'):
                comp.capture_scene()
            else:
                _warn('capture_scene() missing on the capture component; '
                      'exporting stale contents')
            filename = 'pose_{0}.png'.format(index)
            export_fn(get_editor_world(), rt, str(temp_dir), filename)
            frame = temp_dir / filename
            if frame.exists() and is_valid_png(frame):
                frame_paths.append(frame)
            else:
                _warn('Pose {0} export produced no valid PNG'.format(index))

        if not frame_paths:
            _warn('No pose frames were captured for {0}'.format(
                anim_asset_path))
            return None

        sheet_path = _compose_contact_sheet(
            frame_paths, temp_dir / 'contact_sheet.png')
        if sheet_path is None:
            return None

        described = _describe_sheet_with_vision(sheet_path, anim_asset_path)
        if described:
            _log("Described {0} as '{1}' (aliases: {2})".format(
                anim_asset_path, described['action_description'],
                ', '.join(described['aliases'])))
        return described
    except Exception as e:
        _error('describe_animation failed for {0}: {1}'.format(
            anim_asset_path, e))
        _error(traceback.format_exc())
        return None
    finally:
        if THUMBNAIL_HELPERS_AVAILABLE:
            for temp_actor in (light, capture, subject):
                _destroy_actor(temp_actor)
        _cleanup_temp_dir(temp_dir)


def _aliases_need_fill(aliases):
    """True when an alias list is missing, empty, or all placeholders."""
    if not isinstance(aliases, list) or not aliases:
        return True
    for alias in aliases:
        text = str(alias).strip().lower()
        if text and text not in PLACEHOLDER_ALIASES:
            return False
    return True


def _merge_aliases(existing, new_aliases):
    """Merge alias lists (existing first), dropping placeholders/dupes."""
    merged = []
    sources = []
    if isinstance(existing, list):
        sources.extend(existing)
    sources.extend(new_aliases or [])
    for alias in sources:
        text = str(alias).strip().lower()
        if text and text not in PLACEHOLDER_ALIASES and text not in merged:
            merged.append(text)
    return merged


def build_show_animation_library_for_skeleton(show_name, skeletal_mesh_path,
                                              limit=60):
    """Discover AnimSequences compatible with a character's skeleton and
    merge them into the show's animation_library.json.

    Without this the animation picker only ever sees the read-only
    samples fallback (whose asset paths do not exist in the project), so
    characters stay in T-pose. Called automatically when a SkeletalMesh
    character is added from the Content Browser.

    Keys are lowercased asset names; aliases are the name's word tokens
    (so 'Walk_Fwd' matches action text containing 'walk'). Existing
    entries are never overwritten. Editor-only; never raises.

    Returns:
        dict {'added': int, 'total_compatible': int,
              'library_path': str|None, 'skipped_reason': str|None}
    """
    result = {'added': 0, 'total_compatible': 0,
              'library_path': None, 'skipped_reason': None}
    try:
        if not UNREAL_AVAILABLE:
            result['skipped_reason'] = 'not running in the editor'
            return result

        asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
        mesh = asset_subsystem.load_asset(str(skeletal_mesh_path)) if asset_subsystem else None
        if not isinstance(mesh, unreal.SkeletalMesh):
            result['skipped_reason'] = 'asset is not a SkeletalMesh'
            return result
        skeleton = mesh.get_editor_property('skeleton')
        if skeleton is None:
            result['skipped_reason'] = 'skeletal mesh has no skeleton'
            return result
        skeleton_path = str(skeleton.get_path_name())

        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        try:
            anim_class = unreal.TopLevelAssetPath('/Script/Engine', 'AnimSequence')
            all_anims = list(registry.get_assets_by_class(anim_class, True))
        except Exception as e:
            result['skipped_reason'] = 'asset registry query failed: {0}'.format(e)
            return result

        compatible = []
        for asset_data in all_anims:
            try:
                tag = asset_data.get_tag_value('Skeleton')
                if tag and skeleton_path in str(tag):
                    compatible.append(asset_data)
            except Exception:
                continue
        result['total_compatible'] = len(compatible)
        if not compatible:
            result['skipped_reason'] = ('no AnimSequences found for skeleton '
                                        + skeleton_path)
            _log('No compatible AnimSequences for {0}'.format(skeleton_path))
            return result
        if len(compatible) > limit:
            _log('Found {0} compatible AnimSequences; keeping the first '
                 '{1}'.format(len(compatible), limit))
            compatible = compatible[:limit]

        from core.shows_manager import ShowsManager
        lib_path = (Path(ShowsManager().shows_root) / str(show_name)
                    / 'animation_library.json')
        result['library_path'] = str(lib_path)

        data = {'animations': {}}
        if lib_path.exists():
            try:
                with open(str(lib_path), 'r') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {'animations': {}}
            except (json.JSONDecodeError, OSError) as e:
                # Do not clobber a file we cannot read
                result['skipped_reason'] = 'existing library unreadable: {0}'.format(e)
                _error('Could not read {0}: {1}'.format(lib_path, e))
                return result
        animations = data.setdefault('animations', {})
        if not isinstance(animations, dict):
            animations = {}
            data['animations'] = animations

        import re as _re

        # Name tokens that carry no motion meaning (pack prefixes,
        # direction/variant suffixes). They polluted aliases: 'as' matched
        # the word "as" in any sentence, 'start' matched "startled".
        noise_tokens = {'as', 'anim', 'sequence', 'demo', 'full', 'inplace',
                        'fwd', 'bwd', 'left', 'right', 'loop', 'start',
                        'end', 'skm', 'sk'}

        # Motion vocabulary: clip names say 'idle'/'walk'; storyboard
        # action text says 'stands'/'strolling'. Detected per name token;
        # the matched family's verbs become aliases so the animation
        # picker can bridge the two vocabularies.
        motion_vocab = (
            ('idle', ('stand', 'stands', 'standing', 'wait', 'waits',
                      'waiting', 'still', 'stationary', 'look', 'looks',
                      'looking', 'stare', 'stares', 'staring', 'watch',
                      'watches', 'watching')),
            ('walk', ('walks', 'walking', 'stroll', 'strolling', 'wander',
                      'wandering', 'pace', 'pacing', 'march', 'marching')),
            ('run', ('runs', 'running', 'sprint', 'sprinting', 'jog',
                     'jogging', 'dash', 'chase', 'chasing', 'flee',
                     'fleeing')),
            ('jump', ('jumps', 'jumping', 'leap', 'leaping', 'hop',
                      'hopping')),
            ('fall', ('falls', 'falling', 'collapse', 'collapsing',
                      'stumble', 'stumbling', 'tumble', 'tumbling')),
            ('land', ('lands', 'landing')),
            ('death', ('die', 'dies', 'dying', 'dead', 'killed')),
            ('gethit', ('hit', 'hurt', 'wounded', 'injured', 'flinch',
                        'flinching', 'stagger', 'staggering', 'recoil')),
            ('attack', ('attacks', 'attacking', 'fight', 'fights',
                        'fighting', 'strike', 'strikes', 'striking',
                        'swing', 'swings', 'swinging', 'punch',
                        'punching', 'slash', 'slashing')),
        )

        # Pack-identity tokens ('Maniac', 'Farmer' from ManiacFarmer_*)
        # appear in (nearly) every compatible clip's name and say nothing
        # about motion - as aliases they made 'A farmer stands' match the
        # first clip alphabetically (a death anim). Drop tokens present in
        # >= 80% of the compatible set (only meaningful from 3+ clips).
        token_df = {}
        clip_token_sets = []
        for asset_data in compatible:
            try:
                spaced = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ',
                                 str(asset_data.asset_name))
                tset = {t.lower() for t in
                        _re.split(r'[^a-zA-Z0-9]+', spaced) if len(t) > 2}
            except Exception:
                tset = set()
            clip_token_sets.append(tset)
            for t in tset:
                token_df[t] = token_df.get(t, 0) + 1
        identity_threshold = max(3, int(0.8 * len(compatible)))
        identity_tokens = {t for t, df in token_df.items()
                           if df >= identity_threshold}

        for asset_data in compatible:
            try:
                asset_name = str(asset_data.asset_name)
                package = str(asset_data.package_name)
                key = asset_name.lower()
                if key in animations:
                    existing_path = str(animations[key].get('asset_path') or '')
                    if existing_path == package:
                        continue  # same clip, already in the library
                    # Different clip sharing a base name (e.g. two packs
                    # with 'Idle'): disambiguate instead of dropping it
                    suffix = 2
                    while f"{key}_{suffix}" in animations:
                        suffix += 1
                    key = f"{key}_{suffix}"
                spaced = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', asset_name)
                tokens = [t for t in _re.split(r'[^a-zA-Z0-9]+', spaced) if t]
                token_set = {t.lower() for t in tokens if len(t) > 2}
                aliases = {t for t in token_set
                           if t not in noise_tokens
                           and t not in identity_tokens}
                for family, verbs in motion_vocab:
                    if family in token_set:
                        aliases.update(verbs)
                animations[key] = {
                    'asset_path': package,
                    'aliases': sorted(aliases),
                    'description': '',
                }
                result['added'] += 1
            except Exception:
                continue

        if result['added']:
            lib_path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(lib_path), 'w') as f:
                json.dump(data, f, indent=2)
            _log('Animation library for show {0}: added {1} clips compatible '
                 'with {2} -> {3}'.format(show_name, result['added'],
                                          skeleton_path, lib_path))
        else:
            _log('Animation library already contains all compatible clips')
    except Exception as e:
        _error('build_show_animation_library_for_skeleton failed: {0}'.format(e))
        _error(traceback.format_exc())
    return result


def catalog_animation_library(show_name, overwrite=False, progress_cb=None):
    """Fill descriptions and alias lists across a show's animation library.

    Reads <shows_root>/<show>/animation_library.json (falling back to
    samples/animation_library.sample.json read-only when the show has no
    library file yet), runs describe_animation for every entry that
    needs it, and saves the updated library ONCE to the show's own
    animation_library.json. The samples file is never written.

    Args:
        show_name: the show folder name (safe_name) under
            <project_content>/StoryboardTo3D/Shows.
        overwrite: when True, re-describe entries that already carry a
            description and aliases; existing aliases are merged with
            the new ones, never dropped. Default False only fills
            entries with a missing description or an empty/placeholder
            alias list.
        progress_cb: optional callable (index, total, key) -> bool;
            return False to cancel (remaining entries count as skipped).

    Returns:
        dict with lists 'cataloged', 'skipped', 'failed' (entry keys),
        plus 'library_path' (str or None) and 'saved' (bool).
        Never raises.
    """
    result = {'cataloged': [], 'skipped': [], 'failed': [],
              'library_path': None, 'saved': False}
    try:
        if not UNREAL_AVAILABLE:
            _warn('unreal module unavailable (not running in the editor)')
            return result
        if not show_name or not str(show_name).strip():
            _warn('catalog_animation_library called with no show name')
            return result

        # Lazy import: ShowsManager touches unreal at init, editor only
        from core.shows_manager import ShowsManager
        manager = ShowsManager()
        show_lib_path = (Path(manager.shows_root) / str(show_name)
                         / 'animation_library.json')
        result['library_path'] = str(show_lib_path)

        data = None
        if show_lib_path.exists():
            try:
                with open(str(show_lib_path), 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                _error('Could not read {0}: {1}'.format(show_lib_path, e))
                return result
        elif SAMPLE_LIBRARY_PATH.exists():
            # Samples fallback is read-only: results are saved to the
            # show's animation_library.json, never back into samples.
            _log('No show animation library; starting from the samples '
                 'fallback (read-only) at {0}'.format(SAMPLE_LIBRARY_PATH))
            try:
                with open(str(SAMPLE_LIBRARY_PATH), 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                _error('Could not read {0}: {1}'.format(
                    SAMPLE_LIBRARY_PATH, e))
                return result
        else:
            _warn('No animation library found for show {0} (looked for {1} '
                  'and the samples fallback)'.format(show_name, show_lib_path))
            return result

        animations = data.get('animations') if isinstance(data, dict) else None
        if not isinstance(animations, dict) or not animations:
            _warn('Animation library has no animations to catalog')
            return result

        entries = list(animations.items())
        total = len(entries)
        cancelled = False
        dirty = False

        for index, (key, entry) in enumerate(entries):
            if not cancelled and progress_cb is not None:
                try:
                    if progress_cb(index, total, key) is False:
                        cancelled = True
                        _log('Cataloging cancelled at entry {0}/{1}'.format(
                            index, total))
                except Exception as e:
                    _warn('progress callback failed: {0}'.format(e))
            if cancelled or not isinstance(entry, dict):
                result['skipped'].append(key)
                continue
            asset_path = entry.get('asset_path') or ''
            if not asset_path:
                _log('Skipping {0}: no asset_path'.format(key))
                result['skipped'].append(key)
                continue

            needs_aliases = _aliases_need_fill(entry.get('aliases'))
            needs_description = not str(entry.get('description') or '').strip()
            if not overwrite and not needs_aliases and not needs_description:
                result['skipped'].append(key)
                continue

            described = describe_animation(
                asset_path, entry.get('skeletal_mesh_path'))
            if not described:
                result['failed'].append(key)
                continue

            if needs_description or overwrite:
                entry['description'] = described['action_description']
                dirty = True
            if described['aliases'] and (needs_aliases or overwrite):
                merged = _merge_aliases(entry.get('aliases'),
                                        described['aliases'])
                if merged != entry.get('aliases'):
                    entry['aliases'] = merged
                    dirty = True
            result['cataloged'].append(key)

        if progress_cb is not None and not cancelled:
            try:
                progress_cb(total, total, '')
            except Exception:
                pass

        if dirty:
            try:
                show_lib_path.parent.mkdir(parents=True, exist_ok=True)
                with open(str(show_lib_path), 'w') as f:
                    json.dump(data, f, indent=2)
                result['saved'] = True
                _log('Updated {0} ({1} cataloged, {2} skipped, '
                     '{3} failed)'.format(
                         show_lib_path, len(result['cataloged']),
                         len(result['skipped']), len(result['failed'])))
            except OSError as e:
                _error('Could not save {0}: {1}'.format(show_lib_path, e))
    except Exception as e:
        _error('catalog_animation_library failed for show {0}: {1}'.format(
            show_name, e))
        _error(traceback.format_exc())
    return result

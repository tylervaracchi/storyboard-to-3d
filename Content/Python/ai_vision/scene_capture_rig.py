# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Viewport-independent multi-view capture rig built on SceneCapture2D.

PURPOSE
    The legacy capture path (tests/positioning/test_individual_captures.py,
    driven by ui/widgets/active_panel_widget.py) pilots the single editor
    viewport through 7 camera positions, with settle delays, sequence
    re-evaluation, and async HighResShot writes. That costs roughly 5-10
    seconds per iteration and exposes a whole bug class around scout-camera
    viewport locking (pilot / eject / camera-cut lock state leaking between
    steps). This rig instead renders every view from pre-placed
    SceneCapture2D actors whose capture components have capture-every-frame
    OFF: a full 7-view capture is roughly one explicit capture_scene() render
    per view plus a synchronous PNG export, and it never touches the editor
    viewport, pilot state, or camera-cut locking.

LEGACY VIEW GEOMETRY (replicated in DEFAULT_VIEW_DEFINITIONS)
    The legacy 6 scout views are hard-coded absolute transforms tuned for the
    reference test scene (an orbit of radius ~1050-1415 around the origin at
    eye height ~108-182, plus a top-down view at Z ~2141). They are NOT
    computed from scene bounds at runtime; the exact legacy vectors are kept
    here verbatim. The legacy hero view is the sequence's spawnable
    CineCameraActor: core/scene_builder.py places it at
    Vector(-distance, 0, 180), Rotator(0, 0, 0) looking down +X, where
    distance maps from the AI-analyzed shot type
    (close=150, medium=300, wide=600, extreme_wide=1000). The rig's default
    hero transform mirrors the 'medium' shot; per-panel framing is applied
    with set_hero_transform(). compute_default_views(center, radius)
    generalizes the same ring geometry for arbitrary scene bounds.

OUTPUT CONTRACT
    capture_all() writes the SAME filenames the legacy path writes
    (test_hero.png, test_front.png, test_right.png, test_back.png,
    test_left.png, test_top.png, test_front_3_4.png) into
    Saved/Screenshots/WindowsEditor by default, so downstream scoring,
    external validation, and the MCP capture tool keep working unchanged.

INTEGRATION
    The iteration loop can swap capture paths behind a future setting
    'performance.scene_capture_rig' (default off). Wiring is intentionally
    left to a supervised pass because active_panel_widget.py is demo-critical.
"""

import math
import os
import traceback

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:  # Running outside the Unreal editor (tests, tooling)
    unreal = None
    UNREAL_AVAILABLE = False

RIG_TAG = 'StoryboardCaptureRig'
GENERATED_TAG = 'StoryboardGenerated'
LABEL_PREFIX = 'StoryboardCapture_'
DEFAULT_RESOLUTION = (1280, 720)

# Rotations are (pitch, yaw, roll). Locations are (x, y, z) in cm.
# Non-hero transforms are the exact legacy scout positions from
# tests/positioning/test_individual_captures.py.
DEFAULT_VIEW_DEFINITIONS = [
    {'name': 'hero', 'location': (-300.0, 0.0, 180.0), 'rotation': (0.0, 0.0, 0.0)},
    {'name': 'front', 'location': (-1364.0, -17.0, 182.0), 'rotation': (0.0, 0.0, 0.0)},
    {'name': 'right', 'location': (-26.999945, 1415.438812, 163.519337), 'rotation': (0.0, -90.0, 0.0)},
    {'name': 'back', 'location': (1055.615701, 3.996872, 108.0), 'rotation': (0.0, -180.0, 0.0)},
    {'name': 'left', 'location': (-13.999949, -1319.43881, 130.519337), 'rotation': (0.0, 90.0, 0.0)},
    {'name': 'top', 'location': (-11.072672, -1.466941, 2141.045177), 'rotation': (-90.0, 0.0, 0.0)},
    {'name': 'front_3_4', 'location': (-1036.86257, 910.687801, 167.451207), 'rotation': (0.0, -42.200001, 0.0)},
]


def _log(msg):
    if unreal is not None:
        unreal.log('[SceneCaptureRig] {0}'.format(msg))
    else:
        print('[SceneCaptureRig] {0}'.format(msg))


def _warn(msg):
    if unreal is not None:
        unreal.log_warning('[SceneCaptureRig] {0}'.format(msg))
    else:
        print('[SceneCaptureRig] WARNING: {0}'.format(msg))


def _error(msg):
    if unreal is not None:
        unreal.log_error('[SceneCaptureRig] {0}'.format(msg))
    else:
        print('[SceneCaptureRig] ERROR: {0}'.format(msg))


def _to_vector(value):
    if unreal is not None and isinstance(value, unreal.Vector):
        return value
    return unreal.Vector(float(value[0]), float(value[1]), float(value[2]))


def _to_rotator(value):
    """Coerce a (pitch, yaw, roll) sequence to unreal.Rotator.

    Always uses keyword arguments: unreal.Rotator's positional order is
    (roll, pitch, yaw), which the legacy code was burned by more than once.
    """
    if unreal is not None and isinstance(value, unreal.Rotator):
        return value
    return unreal.Rotator(pitch=float(value[0]), yaw=float(value[1]), roll=float(value[2]))


# ----------------------------------------------------------------------
# Module-level guarded plumbing (every unreal attribute guarded: names
# vary across 5.4-5.8). Shared by SceneCaptureRig below and by
# core/thumbnail_generator.py; behavior is identical to the original
# SceneCaptureRig private methods, which now delegate here.
# ----------------------------------------------------------------------

def get_actor_subsystem():
    try:
        if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorActorSubsystem'):
            return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    except Exception as e:
        _warn('EditorActorSubsystem unavailable: {0}'.format(e))
    return None


def get_editor_world():
    try:
        if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'UnrealEditorSubsystem'):
            sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
            if sub is not None and hasattr(sub, 'get_editor_world'):
                world = sub.get_editor_world()
                if world:
                    return world
    except Exception as e:
        _warn('UnrealEditorSubsystem world lookup failed: {0}'.format(e))
    ell = getattr(unreal, 'EditorLevelLibrary', None)
    if ell is not None and hasattr(ell, 'get_editor_world'):
        try:
            return ell.get_editor_world()
        except Exception as e:
            _warn('EditorLevelLibrary.get_editor_world failed: {0}'.format(e))
    return None


def get_all_level_actors():
    sub = get_actor_subsystem()
    if sub is not None and hasattr(sub, 'get_all_level_actors'):
        try:
            return list(sub.get_all_level_actors())
        except Exception as e:
            _warn('get_all_level_actors failed: {0}'.format(e))
    ell = getattr(unreal, 'EditorLevelLibrary', None)
    if ell is not None and hasattr(ell, 'get_all_level_actors'):
        try:
            return list(ell.get_all_level_actors())
        except Exception as e:
            _warn('EditorLevelLibrary.get_all_level_actors failed: {0}'.format(e))
    return []


def spawn_capture_actor(location, rotation):
    actor_cls = getattr(unreal, 'SceneCapture2D', None)
    if actor_cls is None:
        _error('unreal.SceneCapture2D class not found in this engine version')
        return None
    sub = get_actor_subsystem()
    if sub is not None and hasattr(sub, 'spawn_actor_from_class'):
        try:
            return sub.spawn_actor_from_class(actor_cls, location, rotation)
        except Exception as e:
            _warn('EditorActorSubsystem spawn failed, trying fallback: {0}'.format(e))
    ell = getattr(unreal, 'EditorLevelLibrary', None)
    if ell is not None and hasattr(ell, 'spawn_actor_from_class'):
        try:
            return ell.spawn_actor_from_class(actor_cls, location, rotation)
        except Exception as e:
            _error('EditorLevelLibrary spawn failed: {0}'.format(e))
    return None


def get_capture_component(actor):
    for prop in ('capture_component2d', 'capture_component2_d'):
        try:
            comp = actor.get_editor_property(prop)
            if comp is not None:
                return comp
        except Exception:
            continue
    comp_cls = getattr(unreal, 'SceneCaptureComponent2D', None)
    if comp_cls is not None and hasattr(actor, 'get_component_by_class'):
        try:
            return actor.get_component_by_class(comp_cls)
        except Exception as e:
            _warn('get_component_by_class fallback failed: {0}'.format(e))
    return None


def make_render_target(name, width, height):
    world = get_editor_world()
    lib = getattr(unreal, 'RenderingLibrary', None)
    if lib is not None and hasattr(lib, 'create_render_target_2d'):
        try:
            # the enum is exposed as TextureRenderTargetFormat (RenderTargetFormat
            # does not exist and silently yields the float default, which makes
            # export_render_target write EXR bytes into the .png)
            fmt_enum = getattr(unreal, 'TextureRenderTargetFormat',
                               getattr(unreal, 'RenderTargetFormat', None))
            # RTF_RGBA8 makes export_render_target write PNG (float formats write HDR)
            fmt = getattr(fmt_enum, 'RTF_RGBA8', None) if fmt_enum is not None else None
            if fmt is not None:
                rt = lib.create_render_target_2d(world, width, height, fmt)
            else:
                rt = lib.create_render_target_2d(world, width, height)
            if rt is not None:
                return rt
        except Exception as e:
            _warn('create_render_target_2d failed for {0}: {1}'.format(name, e))
    # Fallback: construct the object directly and set size properties
    rt_cls = getattr(unreal, 'TextureRenderTarget2D', None)
    if rt_cls is None:
        _error('TextureRenderTarget2D class unavailable; cannot create render target')
        return None
    try:
        rt = rt_cls()
        for prop, value in (('size_x', width), ('size_y', height)):
            try:
                rt.set_editor_property(prop, value)
            except Exception as e:
                _warn('Could not set render target {0}: {1}'.format(prop, e))
        return rt
    except Exception as e:
        _error('Render target fallback construction failed for {0}: {1}'.format(name, e))
        return None


def configure_capture_component(comp, render_target):
    try:
        comp.set_editor_property('texture_target', render_target)
    except Exception as e:
        _warn('Could not assign texture_target: {0}'.format(e))
    enum_cls = getattr(unreal, 'SceneCaptureSource', None)
    source = None
    if enum_cls is not None:
        for candidate in ('SCS_FINAL_COLOR_LDR', 'FINAL_COLOR_LDR'):
            source = getattr(enum_cls, candidate, None)
            if source is not None:
                break
    if source is not None:
        try:
            comp.set_editor_property('capture_source', source)
        except Exception as e:
            _warn('Could not set capture_source, keeping engine default: {0}'.format(e))
    else:
        _log('SceneCaptureSource FINAL_COLOR_LDR enum not found; keeping engine default')
    # Property names vary across 5.4-5.8; guard each individually.
    flag_specs = [
        (('capture_every_frame', 'b_capture_every_frame'), False),
        (('always_persist_rendering_state', 'b_always_persist_rendering_state'), True),
        (('capture_on_movement', 'b_capture_on_movement'), False),
    ]
    for prop_names, value in flag_specs:
        applied = False
        for prop in prop_names:
            try:
                comp.set_editor_property(prop, value)
                applied = True
                break
            except Exception:
                continue
        if not applied:
            _warn('Could not set any of {0} to {1}'.format('/'.join(prop_names), value))


def resolve_export_function():
    tried = []
    for lib_name in ('RenderingLibrary', 'KismetRenderingLibrary'):
        lib = getattr(unreal, lib_name, None)
        if lib is None:
            tried.append('unreal.' + lib_name + ' (module attribute missing)')
            continue
        for fn_name in ('export_render_target', 'ExportRenderTarget'):
            fn = getattr(lib, fn_name, None)
            if callable(fn):
                return fn, '{0}.{1}'.format(lib_name, fn_name)
            tried.append('{0}.{1}'.format(lib_name, fn_name))
    return None, tried


def compute_default_views(center=(0.0, 0.0, 150.0), radius=1350.0):
    """Build the 7-view set on a ring around ``center`` at ``radius``.

    Generalizes the legacy geometry (which is static, tuned for
    center ~(0, 0, 150) and radius ~1350): cameras sit on the XY ring at the
    center's height looking at the center; 'top' hovers at 1.55 * radius
    above the center looking straight down; 'front_3_4' sits at the 135
    degree azimuth (legacy hand-tuned yaw was -42.2, the ideal is -45);
    'hero' starts at the scene_builder 'medium' framing distance (300) on
    the -X axis. Returns a list of view definition dicts usable as
    SceneCaptureRig.setup(view_definitions=...).
    """
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    r = float(radius)
    # (name, azimuth degrees measured from +X toward +Y). Camera yaw looks
    # back at the center: yaw = azimuth - 180 (normalized to [-180, 180]).
    ring = [('front', 180.0), ('right', 90.0), ('back', 0.0), ('left', -90.0), ('front_3_4', 135.0)]
    views = [{'name': 'hero', 'location': (cx - 300.0, cy, cz + 30.0), 'rotation': (0.0, 0.0, 0.0)}]
    for name, azimuth in ring:
        rad = math.radians(azimuth)
        x = cx + r * math.cos(rad)
        y = cy + r * math.sin(rad)
        yaw = azimuth - 180.0
        if yaw < -180.0:
            yaw += 360.0
        views.append({'name': name, 'location': (x, y, cz), 'rotation': (0.0, yaw, 0.0)})
    views.append({'name': 'top', 'location': (cx, cy, cz + 1.55 * r), 'rotation': (-90.0, 0.0, 0.0)})
    return views


class SceneCaptureRig:
    """Persistent SceneCapture2D rig rendering all views without the viewport."""

    def __init__(self):
        self._actors = {}
        self._components = {}
        self._targets = {}
        self._view_order = []
        self._resolution = DEFAULT_RESOLUTION

    # ------------------------------------------------------------------
    # Editor plumbing: thin delegations to the module-level helpers above
    # (kept as methods so the public/instance API stays identical).
    # ------------------------------------------------------------------

    def _get_actor_subsystem(self):
        return get_actor_subsystem()

    def _get_world(self):
        return get_editor_world()

    def _all_level_actors(self):
        return get_all_level_actors()

    def _spawn_capture_actor(self, location, rotation):
        return spawn_capture_actor(location, rotation)

    def _find_existing(self, label):
        rig_tag = unreal.Name(RIG_TAG)
        for actor in self._all_level_actors():
            if actor is None:
                continue
            try:
                if actor.get_actor_label() == label and rig_tag in actor.tags:
                    return actor
            except Exception:
                continue
        return None

    def _apply_tags(self, actor):
        try:
            current = list(actor.tags)
            changed = False
            for tag_str in (GENERATED_TAG, RIG_TAG):
                tag = unreal.Name(tag_str)
                if tag not in current:
                    current.append(tag)
                    changed = True
            if changed:
                actor.set_editor_property('tags', current)
        except Exception as e:
            _warn('Could not tag actor: {0}'.format(e))

    def _get_capture_component(self, actor):
        return get_capture_component(actor)

    def _make_render_target(self, name, width, height):
        return make_render_target(name, width, height)

    def _configure_component(self, comp, render_target):
        configure_capture_component(comp, render_target)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setup(self, view_definitions=None, resolution=DEFAULT_RESOLUTION):
        """Find-or-spawn one SceneCapture2D per view. Never raises."""
        result = {'status': 'ok', 'views': [], 'warnings': []}
        try:
            if not UNREAL_AVAILABLE:
                result['status'] = 'error'
                result['warnings'].append('unreal module unavailable (not running in editor)')
                return result
            self._resolution = (int(resolution[0]), int(resolution[1]))
            views = view_definitions if view_definitions else [dict(v) for v in DEFAULT_VIEW_DEFINITIONS]
            self._view_order = []
            for view in views:
                name = view.get('name')
                if not name:
                    result['warnings'].append('Skipped a view definition with no name')
                    continue
                try:
                    location = _to_vector(view['location'])
                    rotation = _to_rotator(view['rotation'])
                    label = LABEL_PREFIX + name
                    actor = self._find_existing(label)
                    if actor is None:
                        actor = self._spawn_capture_actor(location, rotation)
                        if actor is None:
                            result['warnings'].append('Could not spawn capture actor for {0}'.format(name))
                            continue
                        try:
                            actor.set_actor_label(label)
                        except Exception as e:
                            _warn('Could not label {0}: {1}'.format(name, e))
                    else:
                        _log('Reusing existing rig actor {0}'.format(label))
                    self._apply_tags(actor)
                    try:
                        actor.set_actor_location(location, False, False)
                        actor.set_actor_rotation(rotation, False)
                    except Exception as e:
                        result['warnings'].append('Transform set failed for {0}: {1}'.format(name, e))
                    comp = self._get_capture_component(actor)
                    if comp is None:
                        result['warnings'].append('No SceneCaptureComponent2D on {0}'.format(name))
                        continue
                    rt = self._targets.get(name)
                    if rt is None:
                        rt = self._make_render_target(name, self._resolution[0], self._resolution[1])
                    if rt is None:
                        result['warnings'].append('No render target for {0}; view disabled'.format(name))
                        continue
                    self._configure_component(comp, rt)
                    self._actors[name] = actor
                    self._components[name] = comp
                    self._targets[name] = rt
                    self._view_order.append(name)
                    result['views'].append(name)
                except Exception as e:
                    result['warnings'].append('Setup failed for {0}: {1}'.format(name, e))
            if not result['views']:
                result['status'] = 'error'
            _log('Setup complete: {0} views ready, {1} warnings'.format(
                len(result['views']), len(result['warnings'])))
        except Exception as e:
            result['status'] = 'error'
            result['warnings'].append('Unexpected setup failure: {0}'.format(e))
            _error(traceback.format_exc())
        return result

    def set_hero_transform(self, location, rotation):
        """Update only the hero capture's transform (per-panel framing)."""
        try:
            if not UNREAL_AVAILABLE:
                return False
            actor = self._actors.get('hero')
            if actor is None:
                actor = self._find_existing(LABEL_PREFIX + 'hero')
                if actor is not None:
                    self._actors['hero'] = actor
            if actor is None:
                _warn('set_hero_transform: hero capture not found; run setup() first')
                return False
            actor.set_actor_location(_to_vector(location), False, False)
            actor.set_actor_rotation(_to_rotator(rotation), False)
            return True
        except Exception as e:
            _error('set_hero_transform failed: {0}'.format(e))
            return False

    def _resolve_export_function(self):
        return resolve_export_function()

    def capture_all(self, output_dir=None):
        """Capture every view and export PNGs with the legacy filenames. Never raises."""
        result = {'status': 'ok', 'files': [], 'warnings': []}
        try:
            if not UNREAL_AVAILABLE:
                result['status'] = 'error'
                result['warnings'].append('unreal module unavailable (not running in editor)')
                return result
            if not self._view_order:
                result['warnings'].append('Rig not set up; running setup() with defaults')
                setup_result = self.setup()
                result['warnings'].extend(setup_result.get('warnings', []))
                if setup_result.get('status') != 'ok':
                    result['status'] = 'error'
                    return result
            if output_dir is None:
                paths_cls = getattr(unreal, 'Paths', None)
                if paths_cls is not None and hasattr(paths_cls, 'project_saved_dir'):
                    output_dir = os.path.join(
                        paths_cls.project_saved_dir(), 'Screenshots', 'WindowsEditor')
                else:
                    output_dir = os.path.join('Saved', 'Screenshots', 'WindowsEditor')
                    result['warnings'].append(
                        'unreal.Paths unavailable; using relative dir {0}'.format(output_dir))
            output_dir = os.path.abspath(output_dir)
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                result['status'] = 'error'
                result['warnings'].append('Could not create {0}: {1}'.format(output_dir, e))
                return result
            export_fn, export_info = self._resolve_export_function()
            if export_fn is None:
                result['status'] = 'error'
                result['warnings'].append(
                    'No render target export function found; tried: {0}. '
                    'Cannot write PNGs on this engine version.'.format(', '.join(export_info)))
                return result
            world = self._get_world()
            for name in self._view_order:
                try:
                    comp = self._components.get(name)
                    rt = self._targets.get(name)
                    if comp is None or rt is None:
                        result['warnings'].append('View {0} missing component or render target'.format(name))
                        continue
                    if hasattr(comp, 'capture_scene'):
                        comp.capture_scene()
                    else:
                        result['warnings'].append(
                            'capture_scene() missing on {0} component; exporting last contents'.format(name))
                    filename = 'test_{0}.png'.format(name)
                    export_fn(world, rt, output_dir, filename)
                    file_path = os.path.join(output_dir, filename)
                    result['files'].append({'view': name, 'path': file_path})
                except Exception as e:
                    result['warnings'].append('Capture failed for {0}: {1}'.format(name, e))
            if not result['files']:
                result['status'] = 'error'
            _log('capture_all via {0}: {1} files, {2} warnings'.format(
                export_info, len(result['files']), len(result['warnings'])))
        except Exception as e:
            result['status'] = 'error'
            result['warnings'].append('Unexpected capture failure: {0}'.format(e))
            _error(traceback.format_exc())
        return result

    def teardown(self):
        """Destroy all rig actors (matched by tag). Returns count destroyed."""
        destroyed = 0
        try:
            if not UNREAL_AVAILABLE:
                return 0
            sub = self._get_actor_subsystem()
            ell = getattr(unreal, 'EditorLevelLibrary', None)
            rig_tag = unreal.Name(RIG_TAG)
            for actor in self._all_level_actors():
                if actor is None:
                    continue
                try:
                    if rig_tag not in actor.tags:
                        continue
                    if sub is not None and hasattr(sub, 'destroy_actor'):
                        sub.destroy_actor(actor)
                    elif ell is not None and hasattr(ell, 'destroy_actor'):
                        ell.destroy_actor(actor)
                    else:
                        _warn('No destroy_actor API available')
                        break
                    destroyed += 1
                except Exception as e:
                    _warn('Could not destroy a rig actor: {0}'.format(e))
            self._actors.clear()
            self._components.clear()
            self._targets.clear()
            self._view_order = []
            _log('Teardown destroyed {0} rig actors'.format(destroyed))
        except Exception as e:
            _error('teardown failed: {0}'.format(e))
        return destroyed


_RIG_INSTANCE = None


def get_rig():
    """Module-level singleton so UI callbacks and MCP tools share one rig."""
    global _RIG_INSTANCE
    if _RIG_INSTANCE is None:
        _RIG_INSTANCE = SceneCaptureRig()
    return _RIG_INSTANCE

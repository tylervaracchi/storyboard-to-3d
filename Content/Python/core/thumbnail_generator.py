# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Automatic asset thumbnail generation for the show asset library.

For each library entry this module spawns the asset far away from the
user's working scene, frames it with a temporary SceneCapture2D at a
3/4 view (azimuth ~40 degrees, elevation ~25 degrees), renders one
frame into a square render target, and exports a PNG via the same
guarded UE 5.4-5.8 export chain that ai_vision.scene_capture_rig uses
(verified against a live 5.8 editor). All temporary actors are
destroyed in a finally block so nothing is ever left in the level.

JSON convention (matches core.utils.sanitize_asset_data and the asset
library UI): each entry carries a "thumbnail" dict such as
    {"type": "content_browser", "path": "<absolute png path>"}
Generated thumbnails use type "content_browser" so the existing UI
badges them as auto thumbnails (blue border in AssetLibraryWidget,
"Auto-generated" label in AssetEditDialog). Entries whose thumbnail is
type "manual" (user-authored) are never overwritten.

Thumbnails are written to <shows_root>/<show>/Thumbnails/<safe_name>.png
next to the show's asset_library.json.
"""

import json
import math
import re
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
        get_actor_subsystem,
        get_editor_world,
        get_all_level_actors,
        spawn_capture_actor,
        get_capture_component,
        make_render_target,
        configure_capture_component,
        resolve_export_function,
    )
    RIG_HELPERS_AVAILABLE = True
except ImportError:
    RIG_HELPERS_AVAILABLE = False

# Staging area: far from the origin and far above the ground plane so the
# temporary subject/capture/light never intersect the user's scene (and sit
# above any exponential height fog, which thickens below the ground plane).
STAGING_LOCATION = (1000000.0, 0.0, 100000.0)
CAMERA_AZIMUTH_DEG = 40.0
CAMERA_ELEVATION_DEG = 25.0
CAMERA_DISTANCE_FACTOR = 2.2
MIN_BOUNDS_RADIUS = 25.0
DEFAULT_THUMBNAIL_SIZE = 256
LIBRARY_CATEGORIES = ('characters', 'props', 'locations')

# Distinct truthy status returned by generate_asset_thumbnail for location
# (level/World) entries whose level is not the one currently open in the
# editor: a map-glyph placeholder PNG is written instead of a real capture,
# and callers must count the entry as skipped/deferred, never as failed.
LOCATION_THUMBNAIL_DEFERRED = 'location_thumbnail_deferred'


def _log(msg):
    if unreal is not None:
        unreal.log('[ThumbnailGenerator] {0}'.format(msg))
    else:
        print('[ThumbnailGenerator] {0}'.format(msg))


def _warn(msg):
    if unreal is not None:
        unreal.log_warning('[ThumbnailGenerator] {0}'.format(msg))
    else:
        print('[ThumbnailGenerator] WARNING: {0}'.format(msg))


def _error(msg):
    if unreal is not None:
        unreal.log_error('[ThumbnailGenerator] {0}'.format(msg))
    else:
        print('[ThumbnailGenerator] ERROR: {0}'.format(msg))


def safe_thumbnail_filename(name):
    """Turn an arbitrary entry name into a filesystem-safe stem (no ext)."""
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', str(name)).strip('._-')
    return cleaned or 'asset'


PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def is_valid_png(path):
    """True when the file exists and starts with the PNG magic bytes.

    ExportRenderTarget silently writes EXR data (magic 76 2f 31 01) when
    the render target has a float format, so a .png filename alone proves
    nothing. Qt cannot decode EXR, which shows up as missing thumbnails.
    """
    try:
        p = Path(path)
        if not p.exists():
            return False
        with open(str(p), 'rb') as f:
            return f.read(len(PNG_MAGIC)) == PNG_MAGIC
    except OSError:
        return False


def try_export_editor_thumbnail(asset_path, out_png, min_size=256):
    """Export the Content Browser's own thumbnail for an asset, if possible.

    Calls the plugin's C++ helper (UStoryboardThumbnailLibrary), which reuses
    the thumbnail cached in the asset's package or renders one with the same
    thumbnail renderer the Content Browser uses. Guarded with hasattr so
    editors running older plugin binaries (without the C++ class) silently
    fall back to the turntable pipeline.

    Args:
        asset_path: Content Browser path (e.g. /Game/Props/SM_Ball).
        out_png: absolute path of the PNG to write.
        min_size: reject thumbnails smaller than this on either side.

    Returns:
        True when a valid PNG was written to out_png, False otherwise.
        Never raises.
    """
    try:
        if not UNREAL_AVAILABLE or not asset_path:
            return False
        lib = getattr(unreal, 'StoryboardThumbnailLibrary', None)
        if lib is None or not hasattr(lib, 'export_asset_thumbnail'):
            return False
        out = Path(out_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        if not lib.export_asset_thumbnail(str(asset_path), str(out), int(min_size)):
            return False
        if not is_valid_png(out):
            _warn('Editor thumbnail export wrote non-PNG data for {0}; '
                  'removing {1}'.format(asset_path, out))
            try:
                out.unlink()
            except OSError:
                pass
            return False
        _log('Exported Content Browser thumbnail for {0}: {1}'.format(asset_path, out))
        return True
    except Exception as e:
        _warn('try_export_editor_thumbnail failed for {0}: {1}'.format(asset_path, e))
        return False


def _make_ldr_render_target(size):
    """Create a square RTF_RGBA8 render target.

    The rig helper make_render_target looks up unreal.RenderTargetFormat,
    but the enum is actually exposed as unreal.TextureRenderTargetFormat,
    so the format silently fell back to the engine default (RTF_RGBA16f).
    ExportRenderTarget writes EXR for float formats, producing EXR bytes
    inside .png files that no UI image loader can decode. Requesting
    RTF_RGBA8 explicitly makes the export a real PNG.
    """
    fmt = None
    for enum_name in ('TextureRenderTargetFormat', 'RenderTargetFormat'):
        enum_cls = getattr(unreal, enum_name, None)
        if enum_cls is not None:
            fmt = getattr(enum_cls, 'RTF_RGBA8', None)
            if fmt is not None:
                break
    if fmt is None:
        _warn('RTF_RGBA8 enum not found; export may produce EXR instead of PNG')
        return make_render_target('thumb', size, size)
    world = get_editor_world()
    lib = getattr(unreal, 'RenderingLibrary', None) or getattr(unreal, 'KismetRenderingLibrary', None)
    if lib is not None and hasattr(lib, 'create_render_target_2d'):
        try:
            rt = lib.create_render_target_2d(world, size, size, fmt)
            if rt is not None:
                return rt
        except Exception as e:
            _warn('create_render_target_2d(RTF_RGBA8) failed: {0}'.format(e))
    # Fall back to the shared helper, then try to force the LDR format
    rt = make_render_target('thumb', size, size)
    if rt is not None:
        try:
            rt.set_editor_property('render_target_format', fmt)
        except Exception as e:
            _warn('Could not force render_target_format to RGBA8: {0}'.format(e))
    return rt


def _load_asset(asset_path):
    """Load an asset by path. EditorAssetSubsystem first, library fallback."""
    try:
        if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorAssetSubsystem'):
            sub = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
            if sub is not None and hasattr(sub, 'load_asset'):
                if hasattr(sub, 'does_asset_exist') and not sub.does_asset_exist(asset_path):
                    _warn('Asset does not exist: {0}'.format(asset_path))
                    return None
                return sub.load_asset(asset_path)
    except Exception as e:
        _warn('EditorAssetSubsystem load failed for {0}: {1}'.format(asset_path, e))
    eal = getattr(unreal, 'EditorAssetLibrary', None)
    if eal is not None and hasattr(eal, 'load_asset'):
        try:
            if hasattr(eal, 'does_asset_exist') and not eal.does_asset_exist(asset_path):
                _warn('Asset does not exist: {0}'.format(asset_path))
                return None
            return eal.load_asset(asset_path)
        except Exception as e:
            _warn('EditorAssetLibrary load failed for {0}: {1}'.format(asset_path, e))
    return None


def _spawn_asset_actor(asset, location):
    """Spawn a temp actor for the asset. StaticMesh and SkeletalMesh both go
    through spawn_actor_from_object (StaticMeshActor / SkeletalMeshActor);
    Blueprints fall back to spawning their generated class."""
    rotation = unreal.Rotator(pitch=0.0, yaw=0.0, roll=0.0)
    sub = get_actor_subsystem()
    if sub is not None and hasattr(sub, 'spawn_actor_from_object'):
        try:
            actor = sub.spawn_actor_from_object(asset, location, rotation)
            if actor is not None:
                return actor
        except Exception as e:
            _warn('spawn_actor_from_object failed: {0}'.format(e))
    # Blueprint assets sometimes need their generated class instead
    try:
        bp_cls = getattr(unreal, 'Blueprint', None)
        if bp_cls is not None and isinstance(asset, bp_cls) and hasattr(asset, 'generated_class'):
            gen = asset.generated_class()
            if gen is not None and sub is not None and hasattr(sub, 'spawn_actor_from_class'):
                actor = sub.spawn_actor_from_class(gen, location, rotation)
                if actor is not None:
                    return actor
    except Exception as e:
        _warn('Blueprint generated_class spawn failed: {0}'.format(e))
    ell = getattr(unreal, 'EditorLevelLibrary', None)
    if ell is not None and hasattr(ell, 'spawn_actor_from_object'):
        try:
            return ell.spawn_actor_from_object(asset, location, rotation)
        except Exception as e:
            _warn('EditorLevelLibrary.spawn_actor_from_object failed: {0}'.format(e))
    return None


def _destroy_actor(actor):
    """Destroy a temp actor; guarded so cleanup can never raise."""
    if actor is None:
        return
    try:
        sub = get_actor_subsystem()
        if sub is not None and hasattr(sub, 'destroy_actor'):
            sub.destroy_actor(actor)
            return
        ell = getattr(unreal, 'EditorLevelLibrary', None)
        if ell is not None and hasattr(ell, 'destroy_actor'):
            ell.destroy_actor(actor)
            return
        if hasattr(actor, 'destroy_actor'):
            actor.destroy_actor()
    except Exception as e:
        _warn('Could not destroy a temp actor: {0}'.format(e))


def _get_actor_bounds(actor):
    """Return (origin, box_extent) or (None, None). Includes non-colliding
    components so purely visual meshes are framed correctly."""
    try:
        return actor.get_actor_bounds(False)
    except TypeError:
        pass
    except Exception as e:
        _warn('get_actor_bounds(False) failed: {0}'.format(e))
    try:
        return actor.get_actor_bounds(only_colliding_components=False)
    except Exception as e:
        _warn('get_actor_bounds keyword call failed: {0}'.format(e))
    return None, None


def _look_at_rotation(from_location, to_location):
    """Rotation looking from one point at another, with a manual fallback."""
    math_lib = getattr(unreal, 'MathLibrary', None)
    if math_lib is not None and hasattr(math_lib, 'find_look_at_rotation'):
        try:
            return math_lib.find_look_at_rotation(from_location, to_location)
        except Exception as e:
            _warn('find_look_at_rotation failed, computing manually: {0}'.format(e))
    dx = to_location.x - from_location.x
    dy = to_location.y - from_location.y
    dz = to_location.z - from_location.z
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
    return unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0)


def _compute_camera_transform(origin, radius):
    """3/4 view: ~40 degree azimuth, ~25 degree elevation, distance scaled
    by the bounds sphere radius, looking at the bounds origin."""
    azimuth = math.radians(CAMERA_AZIMUTH_DEG)
    elevation = math.radians(CAMERA_ELEVATION_DEG)
    distance = CAMERA_DISTANCE_FACTOR * radius
    location = unreal.Vector(
        origin.x + distance * math.cos(elevation) * math.cos(azimuth),
        origin.y + distance * math.cos(elevation) * math.sin(azimuth),
        origin.z + distance * math.sin(elevation),
    )
    return location, _look_at_rotation(location, origin)


def _level_has_light():
    """True when the current level appears to contain any light actor."""
    try:
        for actor in get_all_level_actors():
            if actor is None:
                continue
            try:
                if 'light' in type(actor).__name__.lower():
                    return True
            except Exception:
                continue
    except Exception as e:
        _warn('Light scan failed: {0}'.format(e))
    return False


def _spawn_temp_light(camera_rotation):
    """Spawn a temporary DirectionalLight aligned with the camera so the
    faces the camera sees are lit. Returns the actor or None."""
    light_cls = getattr(unreal, 'DirectionalLight', None)
    if light_cls is None:
        _warn('unreal.DirectionalLight class unavailable; skipping temp light')
        return None
    sub = get_actor_subsystem()
    if sub is None or not hasattr(sub, 'spawn_actor_from_class'):
        ell = getattr(unreal, 'EditorLevelLibrary', None)
        if ell is None or not hasattr(ell, 'spawn_actor_from_class'):
            _warn('No spawn API for temp light')
            return None
        spawner = ell
    else:
        spawner = sub
    try:
        location = unreal.Vector(*STAGING_LOCATION)
        return spawner.spawn_actor_from_class(light_cls, location, camera_rotation)
    except Exception as e:
        _warn('Could not spawn temp DirectionalLight: {0}'.format(e))
        return None


def _asset_is_world(asset_path):
    """True when the Content Browser entry is a level (UWorld) asset.

    Uses AssetData from the asset registry so the map package is never
    loaded just to find out what class it is. Never raises."""
    try:
        eal = getattr(unreal, 'EditorAssetLibrary', None)
        if eal is None or not hasattr(eal, 'find_asset_data'):
            return False
        data = eal.find_asset_data(str(asset_path))
        if data is None:
            return False
        for prop in ('asset_class_path', 'asset_class'):
            try:
                value = data.get_editor_property(prop)
            except Exception:
                continue
            if value is None:
                continue
            name = str(getattr(value, 'asset_name', value))
            if name and name != 'None':
                return name == 'World'
    except Exception as e:
        _log('World-asset check failed for {0}: {1}'.format(asset_path, e))
    return False


def _current_level_package_path():
    """Package path (e.g. /Game/Maps/Foo) of the level currently open in
    the editor, or ''. Never raises."""
    world = None
    if RIG_HELPERS_AVAILABLE:
        try:
            world = get_editor_world()
        except Exception:
            world = None
    if world is None:
        try:
            if hasattr(unreal, 'get_editor_subsystem') and \
                    hasattr(unreal, 'UnrealEditorSubsystem'):
                sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
                if sub is not None and hasattr(sub, 'get_editor_world'):
                    world = sub.get_editor_world()
        except Exception:
            world = None
    if world is None:
        return ''
    try:
        return str(world.get_path_name()).split('.')[0]
    except Exception:
        return ''


def _get_viewport_camera_info():
    """(location, rotation) of the active level viewport camera, or
    (None, None). Read-only: the user's viewport is never moved."""
    for source in ('subsystem', 'library'):
        try:
            if source == 'subsystem':
                if not (hasattr(unreal, 'get_editor_subsystem') and
                        hasattr(unreal, 'UnrealEditorSubsystem')):
                    continue
                owner = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
            else:
                owner = getattr(unreal, 'EditorLevelLibrary', None)
            if owner is None or not hasattr(owner, 'get_level_viewport_camera_info'):
                continue
            info = owner.get_level_viewport_camera_info()
            if info:
                return info[0], info[1]
        except Exception as e:
            _log('Viewport camera lookup failed ({0}): {1}'.format(source, e))
    return None, None


def capture_level_view(location, rotation, output_png, size):
    """Capture the currently open level from an ARBITRARY camera pose with
    a temporary SceneCapture2D (the editor viewport is never read or
    moved; the capture actor is destroyed in the finally block). Used by
    the location survey and the loaded-level thumbnail. True when a valid
    PNG was written."""
    capture = None
    try:
        if not RIG_HELPERS_AVAILABLE or get_editor_world() is None:
            return False
        if location is None or rotation is None:
            return False
        capture = spawn_capture_actor(location, rotation)
        if capture is None:
            return False
        comp = get_capture_component(capture)
        if comp is None:
            return False
        # Pin the FOV explicitly: the survey's coordinate-grid math assumes
        # 90 deg (ground span = 2x height for a straight-down shot), so
        # enforce it rather than trusting the engine default to never change
        try:
            comp.set_editor_property('fov_angle', 90.0)
        except Exception:
            pass
        rt = _make_ldr_render_target(max(int(size), 16))
        if rt is None:
            return False
        configure_capture_component(comp, rt)
        if hasattr(comp, 'capture_scene'):
            comp.capture_scene()
        export_fn, export_info = resolve_export_function()
        if export_fn is None:
            return False
        out = Path(output_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
        export_fn(get_editor_world(), rt, str(out.parent), out.name)
        if is_valid_png(out):
            return True
        if out.exists():
            # Non-PNG bytes (float render target exports EXR): remove
            try:
                out.unlink()
            except OSError:
                pass
        return False
    except Exception as e:
        _log('Level view capture failed: {0}'.format(e))
        return False
    finally:
        _destroy_actor(capture)


def _capture_loaded_level_thumbnail(output_png, size):
    """Capture the currently open level from the editor viewport camera
    (least invasive: the camera is read, never moved). True when a valid
    PNG was written."""
    try:
        cam_location, cam_rotation = _get_viewport_camera_info()
    except Exception:
        return False
    return capture_level_view(cam_location, cam_rotation, output_png, size)


def overlay_coordinate_grid(input_png, output_png, center_x, center_y,
                            span, grid_step=500):
    """Burn a labeled world-coordinate grid onto a top-down capture.

    VLMs are unreliable at regressing metric coordinates from raw images;
    a Scaffold/Set-of-Mark style grid with world-coordinate tick labels
    turns 'estimate the position' into 'read the position off the grid',
    which is the proven protocol. The image is assumed to be a straight-
    down capture whose center is world point (center_x, center_y), TOP
    edge toward +X, RIGHT edge toward +Y, covering span x span units.

    Returns True when the annotated PNG was written.
    """
    try:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            _log('PIL unavailable; cannot draw the survey coordinate grid')
            return False
        if grid_step <= 0:
            grid_step = 500  # a non-positive step would hang the loops below
        img = Image.open(str(input_png)).convert('RGB')
        width, height = img.size
        draw = ImageDraw.Draw(img)
        px_per_unit = width / float(span)
        half = span / 2.0

        def world_to_px(wx, wy):
            # +X is up in the image, +Y is right
            px = (wy - center_y + half) * px_per_unit
            py = (half - (wx - center_x)) * px_per_unit
            return px, py

        import math
        start_x = math.floor((center_x - half) / grid_step) * grid_step
        start_y = math.floor((center_y - half) / grid_step) * grid_step
        line_color = (255, 255, 0)
        text_color = (255, 255, 0)

        wx = start_x
        while wx <= center_x + half:
            _, py = world_to_px(wx, center_y)
            if 0 <= py <= height:
                draw.line([(0, py), (width, py)], fill=line_color, width=1)
                draw.text((4, max(py - 12, 0)), f"X={wx:.0f}", fill=text_color)
            wx += grid_step
        wy = start_y
        while wy <= center_y + half:
            px, _ = world_to_px(center_x, wy)
            if 0 <= px <= width:
                draw.line([(px, 0), (px, height)], fill=line_color, width=1)
                draw.text((min(px + 3, width - 60), height - 14), f"Y={wy:.0f}",
                          fill=text_color)
            wy += grid_step

        # Stage center marker
        cx_px, cy_px = world_to_px(center_x, center_y)
        r = 6
        draw.ellipse([cx_px - r, cy_px - r, cx_px + r, cy_px + r],
                     outline=(255, 60, 60), width=2)
        draw.text((cx_px + 8, cy_px - 6), "STAGE", fill=(255, 60, 60))

        out = Path(output_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out), 'PNG')
        return is_valid_png(out)
    except Exception as e:
        _warn('Could not draw the survey grid: {0}'.format(e))
        return False


def write_location_placeholder(output_png, location_name, size=DEFAULT_THUMBNAIL_SIZE):
    """Write an intentional map-glyph placeholder PNG for a location whose
    real thumbnail is deferred until its level is opened in the editor.
    Returns True when a valid PNG exists at output_png afterwards."""
    try:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            _log('PIL unavailable; cannot write a location placeholder PNG')
            return False
        size = max(int(size), 64)
        img = Image.new('RGB', (size, size), (30, 34, 42))
        draw = ImageDraw.Draw(img)
        # Stylized folded map: three panels with slanted top/bottom edges
        left, right = size // 8, size - size // 8
        top, bottom = size // 4, size - int(size * 0.3)
        third = (right - left) // 3
        off = size // 16
        xs = (left, left + third, left + 2 * third, right)
        top_ys = (top + off, top, top + off, top)
        bot_ys = (bottom, bottom - off, bottom, bottom - off)
        outline = list(zip(xs, top_ys)) + list(zip(reversed(xs), reversed(bot_ys)))
        draw.polygon(outline, fill=(52, 62, 82), outline=(120, 140, 180))
        for i in (1, 2):
            draw.line([(xs[i], top_ys[i]), (xs[i], bot_ys[i])],
                      fill=(120, 140, 180), width=1)

        def _font(px):
            try:
                from PIL import ImageFont
            except ImportError:
                return None
            for family in ('arialbd.ttf', 'arial.ttf', 'segoeui.ttf'):
                try:
                    return ImageFont.truetype(family, px)
                except Exception:
                    continue
            try:
                return ImageFont.load_default()
            except Exception:
                return None

        def _centered(text, cy, font, fill):
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                draw.text((size / 2.0 - w / 2.0 - bbox[0], cy - h / 2.0 - bbox[1]),
                          text, font=font, fill=fill)
            except Exception:
                draw.text((size // 3, int(cy)), text, fill=fill)

        _centered('MAP', (top + bottom) / 2.0, _font(size // 5), (225, 230, 240))
        label = str(location_name or 'Location')
        if len(label) > 22:
            label = label[:19] + '...'
        _centered(label, bottom + (size - bottom) / 2.0,
                  _font(max(size // 12, 10)), (170, 185, 210))

        out = Path(output_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out), 'PNG')
        return is_valid_png(out)
    except Exception as e:
        _warn('Could not write location placeholder {0}: {1}'.format(output_png, e))
        return False


def _generate_location_thumbnail(asset_path, output_png, size):
    """By-design thumbnail handling for location (level/World) entries.

    Levels cannot be spawned as staged actors, so instead: when the level
    is the one currently open in the editor, capture it from the editor
    viewport camera; otherwise write a map-glyph placeholder and return
    LOCATION_THUMBNAIL_DEFERRED so callers count the entry as skipped
    (deferred), never as failed. Exactly one info log line, no warnings."""
    wanted = str(asset_path).split('.')[0]
    loaded = _current_level_package_path()
    if wanted and loaded and wanted == loaded:
        if _capture_loaded_level_thumbnail(output_png, size):
            _log('Captured viewport thumbnail for loaded level {0}'.format(asset_path))
            return True
        reason = 'level is open but the viewport capture was unavailable'
    else:
        reason = 'level is not currently open in the editor'
    location_name = wanted.rstrip('/').split('/')[-1]
    write_location_placeholder(output_png, location_name, size=size)
    _log('Location {0}: thumbnail deferred ({1}); map placeholder written. '
         'Open the level and regenerate to capture a real thumbnail.'.format(
             asset_path, reason))
    return LOCATION_THUMBNAIL_DEFERRED


def generate_asset_thumbnail(asset_path, output_png, size=DEFAULT_THUMBNAIL_SIZE,
                             spawn_temp_light=True):
    """Render a single asset to a square PNG thumbnail.

    Loads the asset, spawns it temporarily at a staging location far from
    the user's scene, frames it with a temporary SceneCapture2D at a 3/4
    view, captures one frame, and exports the render target as a PNG.
    Both temp actors (and any temp light) are destroyed in a finally block.

    NOTE ON LIGHTING: the capture renders with the CURRENT level's
    lighting, but the staging area is far from any level lights, so when
    spawn_temp_light is True (default) a temporary DirectionalLight aimed
    like the camera is always spawned for the duration of the capture and
    destroyed with everything else.

    Args:
        asset_path: Content Browser path (e.g. /Game/Props/SM_Ball).
        output_png: absolute path of the PNG to write.
        size: square render target dimension in pixels.
        spawn_temp_light: add a temp DirectionalLight for the capture.

    Returns:
        True when a real thumbnail PNG exists on disk afterwards.
        LOCATION_THUMBNAIL_DEFERRED (a truthy string) for location/level
        assets whose level is not open in the editor: a map-glyph
        placeholder PNG is written to output_png instead and callers
        should count the entry as skipped/deferred, not failed.
        False otherwise. Never raises; failures are logged with a reason.
    """
    subject = None
    capture = None
    light = None
    try:
        if not UNREAL_AVAILABLE:
            _warn('unreal module unavailable (not running in the editor)')
            return False
        if not asset_path:
            _warn('Empty asset path; nothing to capture')
            return False

        # First choice: the Content Browser's own thumbnail (cached in the
        # package, or rendered by the editor's thumbnail renderer via the
        # plugin's C++ helper). Needs no staging, no temp actors, no world.
        if try_export_editor_thumbnail(asset_path, output_png,
                                       min_size=max(int(size), 16)):
            return True

        # Levels (World assets) can never be staged as spawned actors, so
        # they get by-design handling: viewport capture when the level is
        # the one currently open, otherwise a deferred map placeholder.
        if _asset_is_world(asset_path):
            return _generate_location_thumbnail(asset_path, output_png, size)

        if not RIG_HELPERS_AVAILABLE:
            _error('ai_vision.scene_capture_rig helpers unavailable; cannot capture')
            return False

        # Spawning into a null world crashes the editor natively, so verify
        # a level is actually loaded before touching any actor APIs
        if get_editor_world() is None:
            _error('No editor world is loaded; open a level before generating thumbnails')
            return False

        asset = _load_asset(asset_path)
        if asset is None:
            _warn('Could not load asset: {0}'.format(asset_path))
            return False
        world_cls = getattr(unreal, 'World', None)
        if world_cls is not None and isinstance(asset, world_cls):
            # Safety net when the asset-registry class check missed it
            return _generate_location_thumbnail(asset_path, output_png, size)

        staging = unreal.Vector(*STAGING_LOCATION)
        subject = _spawn_asset_actor(asset, staging)
        if subject is None:
            _warn('Could not spawn an actor for {0} (asset class {1})'.format(
                asset_path, type(asset).__name__))
            return False

        origin, extent = _get_actor_bounds(subject)
        if origin is None or extent is None:
            _warn('Could not read bounds for {0}'.format(asset_path))
            return False
        radius = math.sqrt(extent.x * extent.x + extent.y * extent.y + extent.z * extent.z)
        radius = max(radius, MIN_BOUNDS_RADIUS)

        cam_location, cam_rotation = _compute_camera_transform(origin, radius)
        capture = spawn_capture_actor(cam_location, cam_rotation)
        if capture is None:
            _warn('Could not spawn SceneCapture2D for {0}'.format(asset_path))
            return False
        comp = get_capture_component(capture)
        if comp is None:
            _warn('No SceneCaptureComponent2D on the capture actor')
            return False
        size = max(int(size), 16)
        rt = _make_ldr_render_target(size)
        if rt is None:
            _warn('Could not create a {0}x{0} render target'.format(size))
            return False
        configure_capture_component(comp, rt)

        if spawn_temp_light:
            _log('Spawning a temporary DirectionalLight for the capture')
            light = _spawn_temp_light(cam_rotation)

        if hasattr(comp, 'capture_scene'):
            comp.capture_scene()
        else:
            _warn('capture_scene() missing on capture component; exporting stale contents')

        export_fn, export_info = resolve_export_function()
        if export_fn is None:
            _error('No render target export function found; tried: {0}'.format(
                ', '.join(export_info)))
            return False

        out = Path(output_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            try:
                out.unlink()
            except OSError as e:
                _warn('Could not remove stale thumbnail {0}: {1}'.format(out, e))
        export_fn(get_editor_world(), rt, str(out.parent), out.name)
        if out.exists():
            if not is_valid_png(out):
                _error('Export wrote non-PNG data (float render target exports EXR); '
                       'removing broken file {0}'.format(out))
                try:
                    out.unlink()
                except OSError:
                    pass
                return False
            _log('Wrote thumbnail for {0} via {1}: {2}'.format(asset_path, export_info, out))
            return True
        _warn('Export reported no file at {0} (running without a usable RHI, '
              'e.g. -nullrhi, leaves render targets with no resource)'.format(out))
        return False
    except Exception as e:
        _error('generate_asset_thumbnail failed for {0}: {1}'.format(asset_path, e))
        _error(traceback.format_exc())
        return False
    finally:
        for temp_actor in (light, capture, subject):
            _destroy_actor(temp_actor)


def generate_library_thumbnails(show_name, overwrite=False, progress_cb=None,
                                size=DEFAULT_THUMBNAIL_SIZE):
    """Generate thumbnails for every entry in a show's asset_library.json.

    Iterates the characters/props/locations categories, writes
    <shows_root>/<show>/Thumbnails/<safe_name>.png per entry, and writes
    the {"type": "content_browser", "path": ...} thumbnail dict back into
    the entry (the convention the asset library UI already reads).
    Manual (user-authored) thumbnails are never replaced.

    Args:
        show_name: the show folder name (safe_name) under
            <project_content>/StoryboardTo3D/Shows.
        overwrite: regenerate even when a valid thumbnail already exists.
        progress_cb: optional callable (index, total, entry_name) -> bool;
            return False to cancel (remaining entries count as skipped).
        size: square thumbnail dimension in pixels.

    Returns:
        dict with lists 'generated', 'skipped', 'failed' (entry names) and
        'thumb_dir' (str or None). Locations whose level is not open in
        the editor count as skipped (deferred, with a map placeholder),
        never as failed. Never raises.
    """
    result = {'generated': [], 'skipped': [], 'failed': [], 'thumb_dir': None}
    try:
        if not UNREAL_AVAILABLE:
            _warn('unreal module unavailable (not running in the editor)')
            return result
        # Lazy import: core.utils imports unreal unguarded, editor only
        from core.utils import get_shows_manager
        show_path = Path(get_shows_manager().shows_root) / show_name
        library_path = show_path / 'asset_library.json'
        if not library_path.exists():
            _warn('No asset library for show {0} at {1}'.format(show_name, library_path))
            return result
        try:
            with open(library_path, 'r') as f:
                library = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _error('Could not read {0}: {1}'.format(library_path, e))
            return result

        thumb_dir = show_path / 'Thumbnails'
        thumb_dir.mkdir(parents=True, exist_ok=True)
        result['thumb_dir'] = str(thumb_dir)

        entries = []
        for category in LIBRARY_CATEGORIES:
            cat = library.get(category)
            if isinstance(cat, dict):
                for name, data in cat.items():
                    entries.append((category, name, data))
        total = len(entries)
        cancelled = False
        dirty = False

        for index, (category, name, data) in enumerate(entries):
            if not cancelled and progress_cb is not None:
                try:
                    if progress_cb(index, total, name) is False:
                        cancelled = True
                        _log('Generation cancelled at entry {0}/{1}'.format(index, total))
                except Exception as e:
                    _warn('progress callback failed: {0}'.format(e))
            if cancelled or not isinstance(data, dict):
                result['skipped'].append(name)
                continue
            asset_path = data.get('asset_path') or ''
            if not asset_path:
                _log('Skipping {0}: no asset_path'.format(name))
                result['skipped'].append(name)
                continue

            thumb_info = data.get('thumbnail')
            if not isinstance(thumb_info, dict):
                thumb_info = {}
            existing_path = thumb_info.get('path')
            # Manual thumbnails are user-authored: never regenerate them as
            # long as the file exists, whatever its format
            if thumb_info.get('type') == 'manual' and existing_path and \
                    Path(str(existing_path)).exists():
                _log('Skipping {0}: manual thumbnail is user-authored'.format(name))
                result['skipped'].append(name)
                continue
            # Generated thumbnails must be real PNGs; files with EXR bytes
            # from the old float-render-target bug count as broken and are
            # regenerated even without overwrite
            existing_ok = bool(existing_path) and is_valid_png(str(existing_path))
            # Deferred location placeholders always retry: the level may be
            # open now, letting a viewport capture replace the map glyph
            is_location = (category == 'locations')
            deferred_retry = is_location and thumb_info.get('type') == 'placeholder'

            out_png = thumb_dir / (safe_thumbnail_filename(name) + '.png')
            if not overwrite and not deferred_retry:
                if existing_ok:
                    result['skipped'].append(name)
                    continue
                if not is_location and is_valid_png(out_png):
                    # PNG already on disk but JSON pointer missing/stale: repair
                    # it (locations skip this: the PNG on disk could be a
                    # deferred map placeholder, not a real capture)
                    data['thumbnail'] = {'type': 'content_browser', 'path': str(out_png)}
                    dirty = True
                    result['skipped'].append(name)
                    continue

            status = generate_asset_thumbnail(asset_path, str(out_png), size=size)
            if status == LOCATION_THUMBNAIL_DEFERRED:
                # Skipped-with-reason (logged once by the generator); point
                # the entry at the map placeholder so the grid shows intent
                if is_valid_png(out_png):
                    new_thumb = {'type': 'placeholder', 'path': str(out_png)}
                    if data.get('thumbnail') != new_thumb:
                        data['thumbnail'] = new_thumb
                        dirty = True
                result['skipped'].append(name)
            elif status:
                data['thumbnail'] = {'type': 'content_browser', 'path': str(out_png)}
                dirty = True
                result['generated'].append(name)
            else:
                result['failed'].append(name)

        if progress_cb is not None and not cancelled:
            try:
                progress_cb(total, total, '')
            except Exception:
                pass

        if dirty:
            try:
                with open(library_path, 'w') as f:
                    json.dump(library, f, indent=2)
                _log('Updated {0} ({1} generated, {2} skipped, {3} failed)'.format(
                    library_path, len(result['generated']),
                    len(result['skipped']), len(result['failed'])))
            except OSError as e:
                _error('Could not save {0}: {1}'.format(library_path, e))
    except Exception as e:
        _error('generate_library_thumbnails failed for show {0}: {1}'.format(show_name, e))
        _error(traceback.format_exc())
    return result

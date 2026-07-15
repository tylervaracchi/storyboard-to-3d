# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Optional MCP (Model Context Protocol) toolset for StoryboardTo3D.

Requires Unreal Engine 5.8+ with Epic's experimental ModelContextProtocol
plugin enabled. That plugin embeds an MCP server in the editor at
http://127.0.0.1:8000/mcp and auto-discovers unreal.ToolsetDefinition
subclasses from any enabled plugin's Content/Python folder. Tools are
registered with the standalone `toolset_registry` module's tool_call
decorator (the module ships on the MCP plugin's Python path, per Epic's
UE 5.8 docs; older previews exposed it as unreal.toolset_registry, which
is kept as a fallback). Tool schemas are generated from type hints and
docstrings, and tool calls are serialized to the game thread by the
engine.

On engines below 5.8 (or with the MCP plugin disabled) importing this
module is a clean no-op apart from one log line.

TESTABILITY: the tool bodies only wrap existing plugin functionality
(asset library, panel analyzer, scene builder, show import, multi-view
capture, external validation, optional animatic rendering). The real
registration surface (ToolsetDefinition subclassing plus the
toolset_registry.tool_call decorator) only exists with the MCP plugin
enabled, but register_toolset(registry=...) accepts a stand-in registry
object exposing a tool_call decorator, so tool enumeration and schema
construction can be verified headlessly without the MCP plugin. All
registration code is wrapped in defensive guards, and every tool returns
a JSON error string instead of raising.

POST-DEMO ITEM (deliberately NOT exposed as a tool yet): the full
iterative refinement loop (the Phase 2 up-to-20-iteration
adjust/capture/score cycle) lives in ui/widgets/active_panel_widget.py
as QTimer-driven, game-thread UI code inside a ~7000-line widget.
Exposing it over MCP needs a headless, timer-free extraction of that
loop plus in-editor testing, so it is deferred until after the live
demo. Until then, MCP agents can compose the equivalent outer loop from
the existing tools: analyze_storyboard_panel ->
generate_scene_from_panel -> capture_scene_views -> validate_scene /
validate_scene_pair.
"""

import base64
import json
import sys
from pathlib import Path

# unreal only exists inside the editor. Guarded so this module can be
# imported (or at least parsed by tooling) outside UE without raising;
# it then degrades to the same no-op as on engines below 5.8.
try:
    import unreal
except ImportError:
    unreal = None

_SKIP_MESSAGE = (
    "MCP toolset requires UE 5.8+ (Epic ModelContextProtocol plugin); "
    "skipping registration."
)

# Make sure the plugin's Python root is importable regardless of whether
# main.py or Epic's MCP auto-discovery imported this module first. The
# tool methods import plugin modules lazily and rely on this path.
_PLUGIN_PYTHON_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_PYTHON_DIR)

# Module-level reference so the auto-discovered class cannot be garbage
# collected out from under the registry. Set by register_toolset().
STORYBOARD_TOOLSET = None


def _log_info(message):
    """Log an info line via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, "log"):
        unreal.log(message)
    else:
        print(message)


def _log_warning_safe(message):
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, "log_warning"):
        unreal.log_warning(message)
    else:
        print("WARNING: {0}".format(message))


def _load_toolset_registry():
    """Import the MCP plugin's toolset registry, or return None.

    Epic's UE 5.8 docs register tools via a standalone importable
    `toolset_registry` module (on the MCP plugin's Python path), not an
    attribute of unreal. Try that first; fall back to
    unreal.toolset_registry for engine revisions that exposed it there.

    Returns:
        The registry module/object with a tool_call decorator, or None.
    """
    try:
        import toolset_registry  # provided by the ModelContextProtocol plugin
        return toolset_registry
    except ImportError:
        pass
    if unreal is not None:
        return getattr(unreal, "toolset_registry", None)
    return None


def _toolset_api_available():
    """Check for the UE 5.8 MCP Python surface without assuming any of it exists.

    Returns:
        bool: True only if unreal imported, unreal.ToolsetDefinition
              exists, and a toolset registry with tool_call was found.
    """
    if unreal is None:
        return False
    if not hasattr(unreal, "ToolsetDefinition"):
        return False
    registry = _load_toolset_registry()
    if registry is None or not hasattr(registry, "tool_call"):
        # Engine exposes the class but not the decorator registry; treat as
        # unavailable rather than half-registering.
        return False
    return True


def _json_error(message):
    """Format a failure as a JSON string (tools never raise to the client)."""
    return json.dumps({"success": False, "error": str(message)}, indent=2)


def _json_ok(payload):
    """Format a success payload as a JSON string.

    default=str guards against any stray unreal objects sneaking into
    the payload; they serialize as their repr instead of raising.
    """
    result = {"success": True}
    result.update(payload)
    return json.dumps(result, indent=2, default=str)


def _vector_to_list(vec):
    """Convert an unreal.Vector-like object to [x, y, z] floats, or None."""
    try:
        return [float(vec.x), float(vec.y), float(vec.z)]
    except Exception:
        return None


def _validate_image_path(image_path):
    """Return an error string describing the problem, or None if usable."""
    if not image_path:
        return "image_path is empty"
    try:
        p = Path(image_path)
    except (TypeError, ValueError) as e:
        return "Invalid image_path: {0}".format(e)
    if not p.exists():
        return "Image not found: {0}".format(image_path)
    if not p.is_file():
        return "Not a file: {0}".format(image_path)
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        return "Unsupported image format: {0}".format(p.suffix)
    return None


def _build_panel_analyzer():
    """Create a PanelAnalyzer wired to the configured AI client.

    Mirrors ui/main_window.py: if the AI client cannot be created, the
    analyzer falls back to its basic filename-heuristic analysis rather
    than failing.
    """
    from core.panel_analyzer import PanelAnalyzer

    ai_client = None
    try:
        from api.ai_client_enhanced import create_ai_client
        ai_client = create_ai_client()
    except Exception as client_error:
        _log_warning_safe(
            "[MCP] AI client unavailable, falling back to basic analysis: "
            "{0}".format(client_error)
        )
    return PanelAnalyzer(ai_client=ai_client)


def _run_panel_analysis(image_path, show_name):
    """Shared analysis step for the analyze and generate tools.

    Returns:
        tuple: (analysis_dict_or_None, error_string_or_None)
    """
    path_error = _validate_image_path(image_path)
    if path_error:
        return None, path_error
    try:
        analyzer = _build_panel_analyzer()
        analysis = analyzer.analyze(image_path, show_name=show_name or None)
        if not isinstance(analysis, dict):
            return None, "Panel analysis returned no data"
        return analysis, None
    except Exception as e:
        return None, "Panel analysis failed: {0}".format(e)


def _summarize_actor_configs(configs):
    """Reduce SceneBuilder actor config dicts to JSON-safe summaries."""
    summaries = []
    for config in configs or []:
        if not isinstance(config, dict):
            continue
        summaries.append({
            "name": config.get("name", "Unknown"),
            "asset_path": config.get("asset_path", ""),
            "placeholder": bool(config.get("is_placeholder", False)),
            "position": _vector_to_list(config.get("position")),
        })
    return summaries


# Per-image size cap for base64 embedding (raw PNG bytes, ~1.5 MB).
# Base64 inflates by ~33%, so the on-wire payload per image is ~2 MB.
_MAX_IMAGE_BYTES = 1500000
_MAX_EMBEDDED_IMAGES = 7


def _resolve_screenshots_dir():
    """Return (Path_or_None, error_or_None) for the editor screenshot dir.

    Windows editor writes to Saved/Screenshots/WindowsEditor; other
    platforms use a different subfolder name.
    """
    try:
        if not hasattr(unreal, "Paths"):
            return None, "unreal.Paths unavailable on this engine version"
        return (Path(unreal.Paths.project_saved_dir())
                / "Screenshots" / "WindowsEditor"), None
    except Exception as e:
        return None, "Could not resolve screenshot dir: {0}".format(e)


def _downscale_png_bytes(image_path, max_bytes):
    """Downscale a PNG with PIL until its encoded size fits max_bytes.

    Returns:
        tuple: (png_bytes_or_None, note_string). PIL (pillow) is in the
        plugin's requirements.txt; if it is missing, returns None with
        a note instead of raising.
    """
    try:
        from PIL import Image
    except ImportError:
        return None, "PIL (pillow) not installed; cannot downscale"
    import io
    try:
        with Image.open(str(image_path)) as img:
            img.load()
            current = img
            for _ in range(8):
                width, height = current.size
                new_w = max(1, int(width * 0.7))
                new_h = max(1, int(height * 0.7))
                if new_w < 64 or new_h < 64:
                    break
                current = current.resize((new_w, new_h))
                buffer = io.BytesIO()
                current.save(buffer, format="PNG")
                data = buffer.getvalue()
                if len(data) <= max_bytes:
                    return data, "downscaled to {0}x{1}".format(new_w, new_h)
        return None, "could not downscale under {0} bytes".format(max_bytes)
    except Exception as e:
        return None, "downscale failed: {0}".format(e)


def _encode_capture_images(capture_files):
    """Base64-encode capture PNGs, downscaling any over the size cap.

    Args:
        capture_files: list of {"view": str, "path": str, ...} dicts,
            newest first. At most _MAX_EMBEDDED_IMAGES are encoded.

    Returns:
        tuple: (images_list, warnings_list). Each image entry carries
        base64 PNG data the MCP client can decode with base64.b64decode.
    """
    images = []
    warnings = []
    for item in capture_files[:_MAX_EMBEDDED_IMAGES]:
        file_path = item.get("path")
        try:
            raw = Path(file_path).read_bytes()
        except (OSError, TypeError, ValueError) as e:
            warnings.append("{0}: could not read ({1})".format(file_path, e))
            continue
        note = None
        if len(raw) > _MAX_IMAGE_BYTES:
            raw, note = _downscale_png_bytes(file_path, _MAX_IMAGE_BYTES)
            if raw is None:
                warnings.append("{0}: skipped ({1})".format(file_path, note))
                continue
        entry = {
            "view": item.get("view", ""),
            "path": str(file_path),
            "mimeType": "image/png",
            "data": base64.b64encode(raw).decode("ascii"),
        }
        if note:
            entry["note"] = note
        images.append(entry)
    return images, warnings


def _find_newest_hero_capture():
    """Locate the most recent hero capture PNG in the screenshot dir.

    Returns:
        tuple: (Path_or_None, error_string_or_None)
    """
    shots_dir, dir_error = _resolve_screenshots_dir()
    if shots_dir is None:
        return None, dir_error
    try:
        if not shots_dir.exists():
            return None, ("Screenshot directory does not exist yet: {0}. "
                          "Run capture_scene_views first.".format(shots_dir))
        candidates = [p for p in shots_dir.glob("*.png")
                      if "hero" in p.name.lower()]
    except OSError as e:
        return None, "Could not scan screenshot dir: {0}".format(e)
    if not candidates:
        return None, ("No hero capture found in {0}. Run "
                      "capture_scene_views first and wait for the async "
                      "screenshot to be written.".format(shots_dir))
    try:
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError as e:
        return None, "Could not stat hero captures: {0}".format(e)
    return newest, None


def _normalize_asset_path(asset_path):
    """Reduce an asset path to its package path for comparisons.

    Strips an optional class prefix (StaticMesh'/Game/X.X') and the
    object-name suffix (/Game/X.X -> /Game/X) so paths stored in
    different forms across the library, cache, and loaded assets compare
    equal.
    """
    text = str(asset_path or "")
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 2 and parts[1]:
            text = parts[1]
    return text.split(".")[0]


def _classify_asset_match(matcher, asset_path):
    """Best-effort provenance of a find_best_match result.

    AssetMatcher.find_best_match returns only the loaded asset object,
    so the tier that produced it is reconstructed here by comparing the
    asset's package path against the show library and the general asset
    cache. Semantic, fuzzy, and exact general-cache hits load from the
    same cache and are indistinguishable after the fact; they are
    reported as one method.

    Args:
        matcher: The AssetMatcher instance that produced the match.
        asset_path: Path of the loaded asset (any UE path form).

    Returns:
        tuple: (library_entry_name, category, match_method) with empty
        strings for whatever could not be determined.
    """
    target = _normalize_asset_path(asset_path)
    try:
        for category, assets in (matcher.show_library or {}).items():
            if not isinstance(assets, dict):
                continue
            for entry_name, entry_data in assets.items():
                if not isinstance(entry_data, dict):
                    continue
                entry_path = _normalize_asset_path(entry_data.get("asset_path"))
                if entry_path and entry_path == target:
                    return entry_name, str(category), "show_library"
    except Exception:
        pass
    try:
        for cache_name, cache_path in (matcher.asset_cache or {}).items():
            if _normalize_asset_path(cache_path) == target:
                return cache_name, "", "general_cache (exact/semantic/fuzzy)"
    except Exception:
        pass
    if target.startswith("/Engine/BasicShapes") or target.startswith(
            "/Engine/EngineMeshes"):
        return "", "", "fallback_shape"
    return "", "", "unknown"


def _sanitize_show_name(show_name):
    """Mirror ShowsManager.create_show's folder-name sanitization.

    Kept in sync with core/shows_manager.py (create_show, line ~33) so
    an existing show can be detected WITHOUT calling create_show, which
    rewrites show_metadata.json with an empty panel list.
    """
    safe = "".join(c for c in str(show_name)
                   if c.isalnum() or c in (' ', '-', '_')).rstrip()
    return safe.replace(' ', '_')


def _import_panels_folder(manager, folder_path, show_name):
    """Import a folder of panel images into a (new or existing) show.

    Mirrors main.quick_import (same image extensions, same ShowsManager
    entry points) with two differences: the show name can be overridden
    instead of always using the folder name, and create_show is only
    called when the show does not exist yet, because create_show rewrites
    show_metadata.json (wiping an existing show's panel list).

    Args:
        manager: A core.shows_manager.ShowsManager instance.
        folder_path: Folder containing panel images (*.jpg/*.jpeg/*.png).
        show_name: Optional show name; empty uses the folder name.

    Returns:
        tuple: (summary_dict_or_None, error_string_or_None)
    """
    try:
        folder = Path(folder_path)
    except (TypeError, ValueError) as e:
        return None, "Invalid folder_path: {0}".format(e)
    if not folder.exists():
        return None, "Folder not found: {0}".format(folder_path)
    if not folder.is_dir():
        return None, "Not a folder: {0}".format(folder_path)

    image_files = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):  # mirrors main.quick_import
        image_files.extend(folder.glob(ext))
    image_files = sorted(set(image_files), key=lambda p: p.name.lower())
    if not image_files:
        return None, ("No panel images (*.jpg, *.jpeg, *.png) found in "
                      "{0}".format(folder_path))

    display_name = show_name or folder.name
    safe_name = _sanitize_show_name(display_name)
    if not safe_name:
        return None, ("Show name '{0}' contains no usable characters"
                      .format(display_name))

    existing = (manager.shows_root / safe_name / "show_metadata.json").exists()
    if not existing:
        try:
            _show_path, metadata = manager.create_show(display_name)
            safe_name = metadata.get("safe_name", safe_name)
        except Exception as e:
            return None, "Could not create show '{0}': {1}".format(
                display_name, e)

    try:
        imported = manager.import_panels_to_show(
            safe_name, [str(f) for f in image_files])
    except Exception as e:
        return None, "Panel import failed: {0}".format(e)

    return {
        "show_name": display_name,
        "safe_name": safe_name,
        "created_new_show": not existing,
        "found_images": len(image_files),
        "imported_count": len(imported or []),
        "imported_panels": [Path(p).name for p in (imported or [])],
    }, None


def _list_shows_summary(manager):
    """List all shows with panel and episode counts (read-only).

    Episode data is read straight from the filesystem instead of
    EpisodesManager.get_show_episodes, which creates the Episodes folder
    and writes missing metadata files as a side effect; a listing tool
    must not mutate shows.

    Args:
        manager: A core.shows_manager.ShowsManager instance.

    Returns:
        tuple: (shows_list, warnings_list)
    """
    warnings = []
    try:
        all_metadata = manager.get_all_shows()
    except Exception as e:
        return [], ["Could not list shows: {0}".format(e)]

    def _count_files(directory):
        try:
            if directory.exists():
                return len([p for p in directory.iterdir() if p.is_file()])
        except OSError as e:
            warnings.append("{0}: {1}".format(directory, e))
        return 0

    shows = []
    for metadata in all_metadata:
        safe_name = metadata.get("safe_name") or _sanitize_show_name(
            metadata.get("name", ""))
        show_dir = manager.shows_root / safe_name
        episodes = []
        episodes_dir = show_dir / "Episodes"
        try:
            if episodes_dir.exists():
                for episode_dir in sorted(episodes_dir.iterdir(),
                                          key=lambda p: p.name.lower()):
                    if episode_dir.is_dir():
                        episodes.append({
                            "name": episode_dir.name,
                            "panel_count": _count_files(
                                episode_dir / "Panels"),
                        })
        except OSError as e:
            warnings.append("{0}: {1}".format(episodes_dir, e))
        shows.append({
            "name": metadata.get("name", safe_name),
            "safe_name": safe_name,
            "panel_count": _count_files(show_dir / "Panels"),
            "episode_count": len(episodes),
            "episodes": episodes,
        })
    return shows, warnings


def _build_toolset_class(tool_call, base_class):
    """Construct the toolset class with every tool bound to a registry.

    Args:
        tool_call: The registry's tool_call decorator (real
            toolset_registry.tool_call inside UE 5.8 with the MCP plugin,
            or a stand-in decorator during headless verification).
        base_class: unreal.ToolsetDefinition for real registration, or a
            plain base (object) for headless verification.

    Returns:
        The constructed class. Raises to the caller on any failure;
        register_toolset wraps this in its defensive guard.
    """

    class StoryboardTo3DToolset(base_class):
        """Storyboard-to-3D scene generation tools.

        Wraps the StoryboardTo3D plugin pipeline (asset library, AI panel
        analysis, scene building, show import, multi-view capture,
        external validation) for MCP clients such as Claude Code. All
        tools return JSON strings and report failures as
        {"success": false, "error": "..."} instead of raising.
        """

        @tool_call
        def list_asset_library(self) -> str:
            """Return the current asset library as JSON.

            Lists the characters, props, and locations the plugin knows
            about, each with its Unreal asset path, human description,
            and aliases used for AI matching.

            Returns:
                JSON string: {"success": true, "library": {"characters":
                {...}, "props": {...}, "locations": {...}}} or an error.
            """
            try:
                # Lazy import to avoid import-order problems at discovery time.
                from asset_library_manager import get_asset_library
                library = get_asset_library()
                return _json_ok({
                    "library_path": str(library.library_path),
                    "library": library.library,
                })
            except Exception as e:
                return _json_error("Failed to load asset library: {0}".format(e))

        @tool_call
        def match_asset(self, text: str, category: str = "", show_name: str = "") -> str:
            """Resolve a free-text description to a library asset.

            Runs the plugin's AssetMatcher (core.asset_matcher) over the
            given text: show asset library first (exact name, aliases,
            description containment), then the general project cache,
            then semantic embedding matching when the
            'asset_library.semantic_matching' setting and an OpenAI key
            are configured, then fuzzy matching, then basic-shape
            fallback. A show with no asset library is not an error; the
            matcher simply falls through to the general tiers.

            Args:
                text: Entity name or description to resolve (e.g.
                    'red armchair' or 'hero_character').
                category: Optional category hint: 'characters', 'props',
                    or 'locations'. Empty infers the category from
                    keywords in the text.
                show_name: Optional show whose asset library is searched
                    first. Empty searches only general project assets.

            Returns:
                JSON string: {"success": true, "matched": true,
                "match_name": ..., "asset_name": ..., "asset_path": ...,
                "category": ..., "match_method": "show_library" |
                "general_cache (exact/semantic/fuzzy)" |
                "fallback_shape" | "unknown"} or an error. match_method
                is reconstructed from the matcher's state after the
                fact, so exact/semantic/fuzzy general-cache hits are
                reported as one method.
            """
            if not text or not str(text).strip():
                return _json_error("text is required")

            category_clean = str(category or "").strip().lower()
            if category_clean and category_clean not in (
                    "characters", "props", "locations"):
                return _json_error(
                    "category must be 'characters', 'props', 'locations', "
                    "or empty; got '{0}'".format(category))

            try:
                from core.asset_matcher import AssetMatcher
            except Exception as e:
                return _json_error("AssetMatcher unavailable: {0}".format(e))

            show_clean = str(show_name or "").strip()
            try:
                matcher = AssetMatcher(show_name=show_clean or None)
                asset = matcher.find_best_match(
                    str(text).strip(), category=category_clean or None)
            except Exception as e:
                return _json_error("Asset matching failed: {0}".format(e))

            if asset is None:
                return _json_ok({
                    "matched": False,
                    "query": str(text),
                    "show_name": show_clean,
                    "note": ("No asset matched and the basic-shape "
                             "fallback failed to load."),
                })

            try:
                asset_path = str(asset.get_path_name())
            except Exception:
                asset_path = ""
            try:
                asset_name = str(asset.get_name())
            except Exception:
                asset_name = ""

            match_name, match_category, match_method = _classify_asset_match(
                matcher, asset_path)
            return _json_ok({
                "matched": True,
                "query": str(text),
                "show_name": show_clean,
                "match_name": match_name or asset_name,
                "asset_name": asset_name,
                "asset_path": asset_path,
                "category": match_category or category_clean,
                "match_method": match_method,
            })

        @tool_call
        def analyze_storyboard_panel(self, image_path: str, show_name: str = "") -> str:
            """Analyze a storyboard panel image with the configured AI model.

            Runs the plugin's panel analysis (AI vision model when
            configured, filename heuristics otherwise) and returns the
            scene description: shot type, character count, objects, mood,
            time of day, and camera angle.

            Args:
                image_path: Absolute path to the storyboard image
                    (.png, .jpg, .jpeg, or .webp).
                show_name: Optional show name for context-aware analysis
                    and caching. Leave empty for no show context.

            Returns:
                JSON string: {"success": true, "analysis": {...}} or an error.
            """
            analysis, error = _run_panel_analysis(image_path, show_name)
            if error:
                return _json_error(error)
            return _json_ok({
                "image_path": str(image_path),
                "analysis": analysis,
            })

        @tool_call
        def generate_scene_from_panel(self, image_path: str, show_name: str = "") -> str:
            """Analyze a storyboard panel and build the 3D scene in the current level.

            Full pipeline: AI panel analysis, then SceneBuilder creates a
            Level Sequence with camera, lighting, characters, and props as
            spawnables. Returns a summary of what was placed.

            Args:
                image_path: Absolute path to the storyboard image
                    (.png, .jpg, .jpeg, or .webp).
                show_name: Optional show name; when set, characters, props,
                    and locations are matched from that show's asset
                    library. Without it, most assets fall back to
                    placeholder cubes.

            Returns:
                JSON string summarizing the sequence, location, and placed
                actors, or an error.
            """
            analysis, error = _run_panel_analysis(image_path, show_name)
            if error:
                return _json_error(error)

            try:
                from core.scene_builder import SceneBuilder
                builder = SceneBuilder(show_name=show_name or None)
                scene = builder.build_scene(analysis, panel_index=0)
            except Exception as e:
                return _json_error("Scene build failed: {0}".format(e))

            if not scene:
                return _json_error(
                    "SceneBuilder returned no scene (see the Unreal Output "
                    "Log for details; a common cause is no editor world or "
                    "a failed Level Sequence creation)."
                )

            sequence_info = scene.get("sequence") or {}
            location_info = scene.get("location") or {}
            camera_info = scene.get("camera") or {}
            summary = {
                "analysis": analysis,
                "sequence": {
                    "name": sequence_info.get("name", ""),
                    "path": sequence_info.get("path", ""),
                },
                "location": {
                    "name": location_info.get("name", "Default"),
                    "loaded": bool(location_info.get("loaded", False)),
                },
                "camera": {
                    "label": camera_info.get("label", ""),
                    "shot_type": camera_info.get("shot_type", ""),
                } if isinstance(camera_info, dict) else {},
                "characters": _summarize_actor_configs(scene.get("characters")),
                "props": _summarize_actor_configs(scene.get("props")),
                "light_count": len(scene.get("lights") or []),
            }
            return _json_ok(summary)

        @tool_call
        def import_storyboard_and_list(self, folder_path: str = "", show_name: str = "") -> str:
            """Import a folder of panel images into a show, then list all shows.

            With folder_path set, wraps the plugin's quick-import flow
            (same ShowsManager entry points as main.quick_import): panel
            images (*.jpg, *.jpeg, *.png) in the folder are copied into
            the show's Panels directory, creating the show when it does
            not exist and extending it when it does (an existing show's
            metadata is never reset). With folder_path empty, this is a
            pure list-shows call with no side effects.

            Args:
                folder_path: Optional absolute path to a folder of panel
                    images to import. Empty skips the import and only
                    lists shows.
                show_name: Optional show to import into. Empty uses the
                    folder's name as the show name. Ignored when
                    folder_path is empty.

            Returns:
                JSON string: {"success": true, "shows": [{"name": ...,
                "safe_name": ..., "panel_count": ..., "episode_count":
                ..., "episodes": [{"name": ..., "panel_count": ...}]}],
                "show_count": ...} plus an "import" summary when
                folder_path was given, or an error.
            """
            try:
                from core.shows_manager import ShowsManager
                manager = ShowsManager()
            except Exception as e:
                return _json_error("ShowsManager unavailable: {0}".format(e))

            import_summary = None
            folder_clean = str(folder_path or "").strip()
            if folder_clean:
                import_summary, import_error = _import_panels_folder(
                    manager, folder_clean, str(show_name or "").strip())
                if import_error:
                    return _json_error(import_error)

            try:
                shows, warnings = _list_shows_summary(manager)
            except Exception as e:
                return _json_error("Show listing failed: {0}".format(e))

            payload = {
                "shows": shows,
                "show_count": len(shows),
            }
            if import_summary is not None:
                payload["import"] = import_summary
            if warnings:
                payload["warnings"] = warnings
            return _json_ok(payload)

        @tool_call
        def capture_scene_views(self, include_images: bool = False) -> str:
            """Trigger the multi-view capture and return the capture file paths.

            Queues the plugin's 7-view capture set (front, right, back,
            left, top, front 3/4, hero) using the scout-camera workflow.
            Screenshots are queued with the engine's HighResShot command
            and are written asynchronously AFTER this call returns, once
            the editor renders new frames. Check the returned paths a few
            seconds later.

            Args:
                include_images: When True, base64-encode up to 7 of the
                    newest capture PNGs that already exist on disk into
                    an 'images_base64' payload key (each capped at about
                    1.5 MB of PNG data, downscaled with PIL when larger).
                    Default False keeps payloads small. Because captures
                    are written asynchronously, images returned by the
                    same call that queued them are usually from the
                    PREVIOUS capture round: call once to queue, wait a
                    few seconds, then call again with include_images=True.

            Returns:
                JSON string listing each view with its queue status,
                expected output path, and whether the file exists yet,
                plus 'newest_capture_files' (existing files, newest
                first) and, when requested, 'images_base64'.

            Note on native MCP images: the MCP spec (2025-11-25)
            supports image content blocks in tool results ({"type":
            "image", "data": "<base64>", "mimeType": "image/png"}), but
            how Epic's toolset registry maps Python return values to
            those blocks is undocumented. Images therefore ride inside
            the JSON payload for now; replace 'images_base64' with
            native MCP image blocks once Epic documents the mapping.
            """
            try:
                from tests.positioning import test_individual_captures as cap
            except Exception as e:
                return _json_error("Capture module unavailable: {0}".format(e))

            try:
                runner = cap.IndividualCaptureTests()
                if not runner.setup_scout_camera():
                    return _json_error(
                        "Could not create or find the AI_Scout_Camera in "
                        "the current level."
                    )
            except Exception as e:
                return _json_error("Scout camera setup failed: {0}".format(e))

            shots_dir, dir_error = _resolve_screenshots_dir()
            if dir_error:
                try:
                    unreal.log_warning("[MCP] {0}".format(dir_error))
                except Exception:
                    pass

            angle_functions = [
                ("front", getattr(cap, "test_front", None)),
                ("right", getattr(cap, "test_right", None)),
                ("back", getattr(cap, "test_back", None)),
                ("left", getattr(cap, "test_left", None)),
                ("top", getattr(cap, "test_top", None)),
                ("front_3_4", getattr(cap, "test_front_3_4", None)),
                ("hero", getattr(cap, "test_hero", None)),
            ]

            captures = []
            for angle_name, func in angle_functions:
                entry = {"view": angle_name, "queued": False}
                if shots_dir is not None:
                    expected = shots_dir / "test_{0}.png".format(angle_name)
                    entry["expected_path"] = str(expected)
                    entry["exists_now"] = expected.exists()
                if func is None:
                    entry["error"] = "Capture function missing"
                else:
                    try:
                        entry["queued"] = bool(func())
                    except Exception as e:
                        entry["error"] = str(e)
                captures.append(entry)

            # Gather the newest capture files that already exist on disk
            # (usually the previous capture round, given async writes).
            existing_files = []
            for entry in captures:
                expected = entry.get("expected_path")
                if not expected:
                    continue
                try:
                    expected_path = Path(expected)
                    if expected_path.exists():
                        existing_files.append({
                            "view": entry.get("view", ""),
                            "path": str(expected_path),
                            "modified_time": expected_path.stat().st_mtime,
                        })
                except OSError:
                    continue
            existing_files.sort(
                key=lambda item: item["modified_time"], reverse=True)

            payload = {
                "captures": captures,
                "newest_capture_files": existing_files,
                "note": (
                    "Screenshots are written asynchronously after this "
                    "call returns; poll expected_path until the files "
                    "appear. Queuing all HighResShot commands in one "
                    "game-thread call can make views come out identical "
                    "(camera only renders at its final position); if that "
                    "happens, capture views one at a time from the plugin "
                    "UI. The hero view additionally requires an open "
                    "Level Sequence."
                ),
            }

            if include_images:
                # images_base64: base64-encoded PNG strings the MCP
                # client can decode with base64.b64decode. This is a
                # stopgap until Epic documents how Python return values
                # map to native MCP image content blocks (see docstring).
                images, image_warnings = _encode_capture_images(
                    existing_files)
                payload["images_base64"] = images
                payload["images_note"] = (
                    "Each entry's 'data' field is a base64-encoded PNG; "
                    "decode with base64.b64decode to recover the image "
                    "bytes. Native MCP image content blocks should "
                    "replace this once Epic documents the mapping."
                )
                if image_warnings:
                    payload["images_warnings"] = image_warnings

            return _json_ok(payload)

        @tool_call
        def validate_scene(self, storyboard_path: str, strategy: str = "opencv") -> str:
            """Externally validate the newest hero capture against a storyboard panel.

            Runs core.external_validator.ExternalValidator on the given
            storyboard image versus the most recent hero capture found in
            the editor screenshot directory. This is the external
            judgment loop the calibration study recommends: VLM
            self-scores were found to be unreliable stop signals (all
            models reported roughly 84/100 regardless of quality), so an
            independent signal should gate accept/stop decisions.

            Args:
                storyboard_path: Absolute path to the storyboard panel
                    image (.png, .jpg, .jpeg, or .webp).
                strategy: 'opencv' (local PIL/numpy comparison, zero API
                    cost, the default), 'second_model' (a different
                    provider scores the match; needs a configured API
                    key), or 'both' (conservative min of the two).
                    Unknown values fall back to 'opencv' with a logged
                    warning.

            Returns:
                JSON string with the storyboard path, the hero capture
                path that was scored, and the validator result dict
                {'score': 0-100 or null, 'strategy': ..., 'details':
                ...}. A null score means validation failed; the reason
                is in details.error.
            """
            path_error = _validate_image_path(storyboard_path)
            if path_error:
                return _json_error(path_error)

            hero_path, hero_error = _find_newest_hero_capture()
            if hero_error:
                return _json_error(hero_error)

            try:
                from core.external_validator import ExternalValidator
            except Exception as e:
                return _json_error(
                    "ExternalValidator unavailable: {0}".format(e))

            strategy_clean = str(strategy or "opencv").strip().lower()

            try:
                validator = ExternalValidator(strategy=strategy_clean)
                result = validator.validate(
                    str(storyboard_path), str(hero_path))
            except Exception as e:
                return _json_error(
                    "External validation failed: {0}".format(e))

            return _json_ok({
                "storyboard_path": str(storyboard_path),
                "capture_path": str(hero_path),
                "validation": result,
            })

        @tool_call
        def validate_scene_pair(self, storyboard_path: str, capture_path: str = "",
                                strategy: str = "opencv") -> str:
            """Externally validate an arbitrary storyboard/capture image pair.

            Same external judgment loop as validate_scene
            (core.external_validator.ExternalValidator, the
            self-vs-external signal the calibration study recommends),
            but the capture image is caller-supplied instead of
            auto-discovered, so an agent can score any render or
            screenshot against any storyboard panel.

            Args:
                storyboard_path: Absolute path to the storyboard panel
                    image (.png, .jpg, .jpeg, or .webp).
                capture_path: Optional absolute path to the capture or
                    render image to score against the storyboard. Empty
                    falls back to the newest hero capture in the editor
                    screenshot directory (validate_scene's behavior).
                strategy: 'opencv' (local PIL/numpy comparison, zero API
                    cost, the default), 'second_model' (a different
                    provider scores the match; needs a configured API
                    key), or 'both' (conservative min of the two).
                    Unknown values fall back to 'opencv' with a logged
                    warning.

            Returns:
                JSON string with both image paths, 'capture_source'
                ('explicit' or 'newest_hero_capture'), and the validator
                result dict {'score': 0-100 or null, 'strategy': ...,
                'details': ...}. A null score means validation failed;
                the reason is in details.error.
            """
            path_error = _validate_image_path(storyboard_path)
            if path_error:
                return _json_error(path_error)

            capture_clean = str(capture_path or "").strip()
            if capture_clean:
                capture_error = _validate_image_path(capture_clean)
                if capture_error:
                    return _json_error(
                        "capture_path: {0}".format(capture_error))
                resolved_capture = Path(capture_clean)
                capture_source = "explicit"
            else:
                resolved_capture, hero_error = _find_newest_hero_capture()
                if hero_error:
                    return _json_error(hero_error)
                capture_source = "newest_hero_capture"

            try:
                from core.external_validator import ExternalValidator
            except Exception as e:
                return _json_error(
                    "ExternalValidator unavailable: {0}".format(e))

            strategy_clean = str(strategy or "opencv").strip().lower()

            try:
                validator = ExternalValidator(strategy=strategy_clean)
                result = validator.validate(
                    str(storyboard_path), str(resolved_capture))
            except Exception as e:
                return _json_error(
                    "External validation failed: {0}".format(e))

            return _json_ok({
                "storyboard_path": str(storyboard_path),
                "capture_path": str(resolved_capture),
                "capture_source": capture_source,
                "validation": result,
            })

        @tool_call
        def render_animatic(self) -> str:
            """Render an animatic from the current scene, if the module exists.

            Lazily imports core.animatic_renderer (an optional module
            that may not be present in this build) and calls its
            render_animatic() entry point. When the module is absent
            this tool reports that cleanly instead of raising, so the
            toolset works with or without the animatic feature.

            Returns:
                JSON string: {"success": true, "result": ...} from the
                renderer, or {"success": false, "error": "animatic
                module not available"} when the module or its entry
                point is missing.
            """
            try:
                from core import animatic_renderer
            except ImportError:
                return _json_error("animatic module not available")
            except Exception as e:
                return _json_error(
                    "animatic module failed to import: {0}".format(e))

            render_func = getattr(animatic_renderer, "render_animatic", None)
            if not callable(render_func):
                return _json_error(
                    "animatic module not available "
                    "(render_animatic entry point missing)")

            try:
                result = render_func()
            except Exception as e:
                return _json_error("Animatic render failed: {0}".format(e))

            return _json_ok({"result": result})

        @tool_call
        def catalog_animations(self, show_name: str, overwrite: bool = False) -> str:
            """AI-catalog a show's animation library with descriptions and aliases.

            For every AnimSequence entry in the show's
            animation_library.json, spawns a compatible skeletal mesh
            far from the user's scene, samples three poses (10/50/90
            percent of the clip), captures them into a contact sheet,
            and asks the configured vision provider what single action
            the character is performing. Each entry's 'description'
            field and empty or placeholder alias lists are filled so
            meaning-based animation matching works; the library file is
            saved once at the end. Requires an open level and a
            configured AI vision provider; may take a while for large
            libraries (one vision call per entry).

            Args:
                show_name: Show folder name under the plugin's Shows
                    root (the same name the asset library uses).
                overwrite: When True, re-describe entries that already
                    carry a description and aliases (existing aliases
                    are merged, never dropped). Default False only
                    fills missing or placeholder data.

            Returns:
                JSON string: {"success": true, "show_name": ...,
                "result": {"cataloged": [...], "skipped": [...],
                "failed": [...], "library_path": ..., "saved": bool}}
                or an error.
            """
            if not show_name or not str(show_name).strip():
                return _json_error("show_name is required")

            try:
                # Lazy import to avoid import-order problems at discovery time.
                from core.animation_cataloger import catalog_animation_library
            except Exception as e:
                return _json_error(
                    "Animation cataloger unavailable: {0}".format(e))

            try:
                result = catalog_animation_library(
                    str(show_name), overwrite=bool(overwrite))
            except Exception as e:
                return _json_error(
                    "Animation cataloging failed: {0}".format(e))

            return _json_ok({
                "show_name": str(show_name),
                "result": result,
            })

        @tool_call
        def get_project_info(self) -> str:
            """Return plugin version, engine version, and the configured AI provider.

            Returns:
                JSON string with plugin_name, plugin_version,
                engine_version, project_dir, and ai_provider details.
            """
            info = {}

            # Plugin version from the .uplugin manifest (two levels above
            # Content/Python).
            try:
                uplugin_path = (Path(__file__).resolve().parents[2]
                                / "StoryboardTo3D.uplugin")
                with open(str(uplugin_path), "r") as f:
                    manifest = json.load(f)
                info["plugin_name"] = manifest.get("FriendlyName", "StoryboardTo3D")
                info["plugin_version"] = manifest.get("VersionName", "unknown")
            except Exception as e:
                info["plugin_name"] = "StoryboardTo3D"
                info["plugin_version"] = "unknown ({0})".format(e)

            # Engine version. Guarded because SystemLibrary methods can
            # differ across engine releases.
            try:
                if hasattr(unreal, "SystemLibrary") and hasattr(
                        unreal.SystemLibrary, "get_engine_version"):
                    info["engine_version"] = str(
                        unreal.SystemLibrary.get_engine_version())
                else:
                    info["engine_version"] = "unknown (API unavailable)"
            except Exception as e:
                info["engine_version"] = "unknown ({0})".format(e)

            try:
                info["project_dir"] = str(unreal.Paths.project_dir())
            except Exception:
                info["project_dir"] = "unknown"

            # Configured AI provider. The plugin has two settings systems;
            # report the first one that answers, and say which it was.
            provider = None
            provider_source = None
            try:
                from config.config_manager import get_config
                provider = get_config().get("api.provider", None)
                if provider:
                    provider_source = "config_manager (~/.storyboard_to_3d/settings.json)"
            except Exception:
                pass
            if not provider:
                try:
                    from core.settings_manager import get_settings_manager
                    ai_settings = get_settings_manager().global_settings.get(
                        "ai_settings", {})
                    provider = ai_settings.get("provider")
                    if provider:
                        provider_source = "settings_manager (global ai_settings)"
                except Exception:
                    pass
            if not provider:
                try:
                    from core.ai_settings import AISettings
                    provider = AISettings().get("provider")
                    if provider:
                        provider_source = "ai_settings (project Config/ai_settings.json)"
                except Exception:
                    pass

            info["ai_provider"] = provider or "not configured"
            info["ai_provider_source"] = provider_source or "none"

            return _json_ok(info)

    return StoryboardTo3DToolset


def register_toolset(registry=None):
    """Build the toolset class and register its tools with a registry.

    Args:
        registry: Object exposing a tool_call decorator. None (the
            default) uses the real UE 5.8 surface: the standalone
            toolset_registry module (with an unreal.toolset_registry
            fallback) plus unreal.ToolsetDefinition as the base class,
            and no-ops with one log line when that surface is missing.
            Passing a stand-in registry (any object with a tool_call
            decorator method) builds the class on a plain-object base
            instead, so tool enumeration and schema construction can be
            verified headlessly without the MCP plugin; a stand-in never
            registers anything with the engine.

    Returns:
        The constructed toolset class (also kept in the module-level
        STORYBOARD_TOOLSET so it cannot be garbage collected out from
        under the registry), or None when registration was skipped or
        failed. Never raises.
    """
    global STORYBOARD_TOOLSET

    if registry is None:
        if not _toolset_api_available():
            # UE < 5.8 (or MCP plugin disabled, or outside UE entirely):
            # single log line, register nothing.
            _log_info(_SKIP_MESSAGE)
            return None
        registry = _load_toolset_registry()
        base_class = unreal.ToolsetDefinition
    else:
        if not hasattr(registry, "tool_call"):
            _log_warning_safe(
                "[MCP] register_toolset: provided registry has no "
                "tool_call decorator; skipping.")
            return None
        # Stand-in registries are for headless verification only; never
        # subclass the engine type for them, even when it exists.
        base_class = object

    try:
        toolset_class = _build_toolset_class(registry.tool_call, base_class)
    except Exception as registration_error:
        # Untestable outside 5.8: if Epic's decorator or base class behaves
        # differently than documented, log and degrade to a no-op rather
        # than breaking whoever imported us.
        _log_warning_safe(
            "[MCP] Toolset registration failed (non-critical): "
            "{0}".format(registration_error)
        )
        return None

    STORYBOARD_TOOLSET = toolset_class
    _log_info(
        "[MCP] StoryboardTo3DToolset registered (11 tools: "
        "list_asset_library, match_asset, analyze_storyboard_panel, "
        "generate_scene_from_panel, import_storyboard_and_list, "
        "capture_scene_views, validate_scene, validate_scene_pair, "
        "render_animatic, catalog_animations, get_project_info)"
    )
    return toolset_class


# Auto-register at import time so Epic's MCP auto-discovery (which imports
# this module from the plugin's Content/Python folder) and main.py's
# register_mcp_toolset() keep working unchanged. Below UE 5.8, or with the
# MCP plugin disabled, this logs the single skip line exactly as before.
register_toolset()

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Optional MCP (Model Context Protocol) toolset for StoryboardTo3D.

Requires Unreal Engine 5.8+ with Epic's experimental ModelContextProtocol
plugin enabled. That plugin embeds an MCP server in the editor at
http://127.0.0.1:8000/mcp and auto-discovers unreal.ToolsetDefinition
subclasses from any enabled plugin's Content/Python folder. Tool schemas
are generated from type hints and docstrings, and tool calls are
serialized to the game thread by the engine.

On engines below 5.8 the unreal.ToolsetDefinition attribute does not
exist, so importing this module is a clean no-op apart from one log line.

HONESTY NOTE ABOUT TESTABILITY: this module was written against Epic's
published 5.8 API surface and cannot be executed on engines below 5.8.
The tool bodies only wrap existing plugin functionality (asset library,
panel analyzer, scene builder, multi-view capture, external validation,
optional animatic rendering), but the registration
surface itself (ToolsetDefinition subclassing and the
toolset_registry.tool_call decorator) is untestable outside 5.8. All
registration code is therefore wrapped in defensive guards, and every
tool returns a JSON error string instead of raising.
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


def _toolset_api_available():
    """Check for the UE 5.8 MCP Python surface without assuming any of it exists.

    Returns:
        bool: True only if unreal imported and both unreal.ToolsetDefinition
              and unreal.toolset_registry.tool_call are present.
    """
    if unreal is None:
        return False
    if not hasattr(unreal, "ToolsetDefinition"):
        return False
    registry = getattr(unreal, "toolset_registry", None)
    if registry is None or not hasattr(registry, "tool_call"):
        # Engine exposes the class but not the decorator registry; treat as
        # unavailable rather than half-registering.
        return False
    return True


if not _toolset_api_available():
    # UE < 5.8 (or MCP plugin disabled, or outside UE entirely): single
    # log line, define nothing else.
    if unreal is not None and hasattr(unreal, "log"):
        unreal.log(_SKIP_MESSAGE)
    else:
        print(_SKIP_MESSAGE)
else:
    # Make sure the plugin's Python root is importable regardless of whether
    # main.py or Epic's MCP auto-discovery imported this module first. The
    # tool methods import plugin modules lazily and rely on this path.
    _PLUGIN_PYTHON_DIR = str(Path(__file__).resolve().parent)
    if _PLUGIN_PYTHON_DIR not in sys.path:
        sys.path.insert(0, _PLUGIN_PYTHON_DIR)

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
            unreal.log_warning(
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

    # Bind the decorator once so a rename in a future engine revision fails
    # here (inside the try below) with a clear log instead of at class body.
    _tool_call = unreal.toolset_registry.tool_call

    try:

        class StoryboardTo3DToolset(unreal.ToolsetDefinition):
            """Storyboard-to-3D scene generation tools.

            Wraps the StoryboardTo3D plugin pipeline (asset library, AI panel
            analysis, scene building, multi-view capture) for MCP clients
            such as Claude Code. All tools return JSON strings and report
            failures as {"success": false, "error": "..."} instead of raising.
            """

            @_tool_call
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

            @_tool_call
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

            @_tool_call
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

            @_tool_call
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

            @_tool_call
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

            @_tool_call
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

            @_tool_call
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

        # Keep a module-level reference so the auto-discovered class cannot
        # be garbage collected out from under the registry.
        STORYBOARD_TOOLSET = StoryboardTo3DToolset

        unreal.log(
            "[MCP] StoryboardTo3DToolset registered (7 tools: "
            "list_asset_library, analyze_storyboard_panel, "
            "generate_scene_from_panel, capture_scene_views, "
            "validate_scene, render_animatic, get_project_info)"
        )

    except Exception as registration_error:
        # Untestable outside 5.8: if Epic's decorator or base class behaves
        # differently than documented, log and degrade to a no-op rather
        # than breaking whoever imported us.
        unreal.log_warning(
            "[MCP] Toolset registration failed (non-critical): "
            "{0}".format(registration_error)
        )

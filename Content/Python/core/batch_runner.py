# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Batch Runner Module

UI-free overnight runner for episode-scale panel processing. Iterates every
panel image in a show episode, runs PanelAnalyzer analysis on each panel
(cache-aware: already-analyzed panels reuse their cached analysis), then
optionally builds the 3D scene per panel via SceneBuilder. Collects per-panel
results and writes a JSON report to Saved/StoryboardTo3D/batch_reports/.

IMPORTANT HONESTY NOTE (scope of this runner):
    The full iterative-refinement loop (multi-view capture, VLM scoring, and
    up-to-N correction iterations) lives inside the UI widget
    (ui/widgets/active_panel_widget.py, driven by Qt timers and viewport
    state) and is NOT reusable from a headless module yet. This runner
    performs SINGLE-PASS analyze + generate per panel: one PanelAnalyzer
    analysis and one SceneBuilder.build_scene call. That is still the right
    overnight primitive: it produces one Level Sequence per panel with
    camera, lights, characters, and props placed from the initial analysis,
    ready for interactive refinement the next morning.

Usage from the UE Python console:
    py "C:/path/to/Content/Python/core/batch_runner.py" MyShow Episode_1
    py "C:/path/to/Content/Python/core/batch_runner.py" MyShow Episode_1 "Claude (Anthropic)" --no-generate --max-panels 5

Or programmatically:
    from core.batch_runner import run_batch
    summary = run_batch("MyShow", "Episode_1", generate=True)
"""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

# Guard the unreal import so this module can be imported (and py_compiled)
# outside the editor. run_batch itself requires the editor environment.
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False


PANEL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')

DEFAULT_PROVIDER = 'Claude (Anthropic)'


def _log(message):
    """Log via unreal when available, print otherwise."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def _log_warning(message):
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {0}".format(message))


def _log_error(message):
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_error'):
        unreal.log_error(message)
    else:
        print("ERROR: {0}".format(message))


def _sanitize_name(name):
    """Mirror ShowsManager/EpisodesManager folder-name sanitization."""
    safe = "".join(c for c in str(name) if c.isalnum() or c in (' ', '-', '_')).rstrip()
    return safe.replace(' ', '_')


def _project_saved_dir():
    """Resolve the project Saved dir, with a logged fallback outside UE.

    unreal.Paths.project_saved_dir is guarded because the Paths surface can
    differ across engine versions and is absent outside the editor.
    """
    if UNREAL_AVAILABLE and hasattr(unreal, 'Paths') and hasattr(unreal.Paths, 'project_saved_dir'):
        try:
            return Path(unreal.Paths.project_saved_dir())
        except Exception as e:
            _log_warning("[Batch] Could not resolve project Saved dir: {0}".format(e))
    fallback = Path.home() / "StoryboardToUnreal" / "Saved"
    _log_warning("[Batch] Falling back to {0} for report output".format(fallback))
    return fallback


def _reports_dir():
    """Directory for batch JSON reports (created on demand)."""
    reports = _project_saved_dir() / "StoryboardTo3D" / "batch_reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


# ---------------------------------------------------------------------------
# AI client plumbing
# ---------------------------------------------------------------------------

def _map_provider(provider):
    """Map a plugin provider display string to plumbing choices.

    The plugin UI (ui/settings/tabs/ai_tab.py) stores display strings like
    'Claude (Anthropic)', 'GPT-4 Vision (OpenAI)', 'LLaVA (Local)', 'Auto'.
    The text/vision REST client (api/ai_client_enhanced.EnhancedAIClient)
    uses different keys ('Claude 3.5 Sonnet', 'OpenAI GPT-4o', ...), so we
    translate here.

    Returns:
        tuple: (enhanced_client_provider_name_or_None, kind) where kind is
               one of 'claude', 'openai', 'local', 'auto'.
    """
    name = (provider or '').lower()
    if not name or 'auto' in name:
        return None, 'auto'
    if 'claude' in name or 'anthropic' in name:
        return 'Claude 3.5 Sonnet', 'claude'
    if 'gpt' in name or 'openai' in name:
        return 'OpenAI GPT-4o', 'openai'
    if 'llava' in name or 'ollama' in name or 'local' in name:
        return None, 'local'
    _log_warning("[Batch] Unknown provider '{0}', using configured default".format(provider))
    return None, 'auto'


def _settings_manager_api_key(kind):
    """Fetch an API key from the plugin's settings_manager ai_settings.

    The Settings UI saves keys as ai_settings.claude_api_key and
    ai_settings.openai_api_key, which EnhancedAIClient does not read on its
    own (it reads config_manager / environment variables), so we bridge.
    """
    try:
        from core.settings_manager import get_settings_manager
        ai_settings = get_settings_manager().global_settings.get('ai_settings', {})
        if kind == 'claude':
            return ai_settings.get('claude_api_key', '') or ''
        if kind == 'openai':
            return ai_settings.get('openai_api_key', '') or ''
    except Exception as e:
        _log_warning("[Batch] Could not read settings_manager ai_settings: {0}".format(e))
    return ''


class _PanelAnalyzerClientAdapter(object):
    """Adapter between PanelAnalyzer and EnhancedAIClient image calls.

    PanelAnalyzer.analyze_with_ai passes RAW IMAGE BYTES to
    ai_client.analyze_image(...), while EnhancedAIClient.analyze_image
    expects a base64 string (it is embedded directly in the JSON payload).
    Without this adapter the request body fails to serialize and the
    analyzer silently degrades to filename heuristics.
    """

    def __init__(self, client):
        self._client = client

    def analyze_image(self, image_data, prompt):
        if isinstance(image_data, (bytes, bytearray)):
            image_b64 = base64.b64encode(bytes(image_data)).decode('utf-8')
        else:
            image_b64 = image_data
        return self._client.analyze_image(image_b64, prompt)


def _build_ai_client(provider):
    """Create the text/vision REST client for the requested provider.

    Returns None when no usable client can be built. PanelAnalyzer then
    falls back to its basic filename-heuristic analysis (logged).
    """
    enhanced_name, kind = _map_provider(provider)

    if kind == 'local':
        _log_warning(
            "[Batch] Provider '{0}' is a local vision provider; the batch "
            "runner's PanelAnalyzer wiring supports the REST client only. "
            "Falling back to basic analysis.".format(provider))
        return None

    try:
        from api.ai_client_enhanced import create_ai_client
        client = create_ai_client(provider=enhanced_name)
    except Exception as e:
        _log_warning("[Batch] AI client unavailable ({0}); basic analysis only".format(e))
        return None

    # Bridge API keys stored by the plugin Settings UI when the client's own
    # config/env sources came up empty.
    if not getattr(client, 'api_key', ''):
        bridged_kind = kind
        if bridged_kind == 'auto':
            client_provider = getattr(client, 'provider', '') or ''
            bridged_kind = 'claude' if 'Claude' in client_provider else 'openai'
        key = _settings_manager_api_key(bridged_kind)
        if key:
            client.api_key = key
            try:
                client._update_headers()
            except Exception as e:
                _log_warning("[Batch] Could not refresh client headers: {0}".format(e))
            _log("[Batch] API key bridged from plugin settings ({0})".format(bridged_kind))

    if not getattr(client, 'api_key', ''):
        _log_warning(
            "[Batch] No API key found for provider '{0}' (checked client "
            "config, environment, and plugin settings). Panels will use "
            "basic filename analysis.".format(provider))
        return None

    return _PanelAnalyzerClientAdapter(client)


def _build_panel_analyzer(provider):
    """Create a PanelAnalyzer wired to the configured AI client."""
    from core.panel_analyzer import PanelAnalyzer
    return PanelAnalyzer(ai_client=_build_ai_client(provider))


# ---------------------------------------------------------------------------
# Episode / panel resolution
# ---------------------------------------------------------------------------

def _resolve_episode_dir(show, episode):
    """Find the episode directory for a show.

    Accepts either the episode display name or its safe (folder) name.

    Returns:
        tuple: (Path or None, resolved_episode_folder_name_or_None)
    """
    try:
        from core.episodes_manager import EpisodesManager
        manager = EpisodesManager()
        shows_root = manager.shows_root
    except Exception as e:
        _log_error("[Batch] Could not initialize EpisodesManager: {0}".format(e))
        return None, None

    show_candidates = [str(show), _sanitize_name(show)]
    episode_lower = str(episode).lower()
    episode_safe_lower = _sanitize_name(episode).lower()

    for show_folder in show_candidates:
        show_path = shows_root / show_folder
        if not show_path.exists():
            continue

        # Prefer metadata matching (handles display name vs folder name).
        try:
            for meta in manager.get_show_episodes(show_folder):
                meta_name = str(meta.get('name', '')).lower()
                meta_safe = str(meta.get('safe_name', '')).lower()
                if episode_lower in (meta_name, meta_safe) or episode_safe_lower == meta_safe:
                    candidate = show_path / "Episodes" / meta.get('safe_name', '')
                    if candidate.exists():
                        return candidate, meta.get('safe_name', '')
        except Exception as e:
            _log_warning("[Batch] Episode metadata scan failed: {0}".format(e))

        # Direct folder fallback.
        for episode_folder in (str(episode), _sanitize_name(episode)):
            candidate = show_path / "Episodes" / episode_folder
            if candidate.exists():
                return candidate, episode_folder

    return None, None


def _list_panel_images(episode_dir):
    """Sorted list of panel image paths in the episode's Panels folder."""
    panels_dir = episode_dir / "Panels"
    if not panels_dir.exists():
        return []
    images = [p for p in panels_dir.iterdir()
              if p.is_file() and p.suffix.lower() in PANEL_EXTENSIONS]
    return sorted(images, key=lambda p: p.name.lower())


# ---------------------------------------------------------------------------
# Result summarization (JSON-safe)
# ---------------------------------------------------------------------------

def _vector_to_list(vec):
    """Convert an unreal.Vector-like object to [x, y, z] floats, or None."""
    try:
        return [float(vec.x), float(vec.y), float(vec.z)]
    except Exception:
        return None


def _summarize_actor_configs(configs):
    """Reduce SceneBuilder actor config dicts to JSON-safe summaries."""
    summaries = []
    for config in configs or []:
        if not isinstance(config, dict):
            continue
        summaries.append({
            'name': config.get('name', 'Unknown'),
            'asset_path': config.get('asset_path', ''),
            'placeholder': bool(config.get('is_placeholder', False)),
            'position': _vector_to_list(config.get('position')),
        })
    return summaries


def _summarize_scene(scene):
    """Reduce a SceneBuilder scene dict to a JSON-safe summary."""
    if not isinstance(scene, dict):
        return None
    sequence_info = scene.get('sequence') or {}
    location_info = scene.get('location') or {}
    camera_info = scene.get('camera') or {}
    return {
        'sequence_name': sequence_info.get('name', ''),
        'sequence_path': sequence_info.get('path', ''),
        'location': {
            'name': location_info.get('name', 'Default'),
            'loaded': bool(location_info.get('loaded', False)),
        },
        'camera_shot_type': camera_info.get('shot_type', '') if isinstance(camera_info, dict) else '',
        'characters': _summarize_actor_configs(scene.get('characters')),
        'props': _summarize_actor_configs(scene.get('props')),
        'light_count': len(scene.get('lights') or []),
    }


def _extract_entities(analysis):
    """Pull the entity lists out of an analysis dict (JSON-safe)."""
    if not isinstance(analysis, dict):
        return {}
    props = analysis.get('props') or analysis.get('objects') or []
    return {
        'characters': list(analysis.get('characters') or []),
        'num_characters': analysis.get('num_characters', 0),
        'props': list(props),
        'location': analysis.get('location', analysis.get('location_type', '')),
        'shot_type': analysis.get('shot_type', ''),
        'mood': analysis.get('mood', ''),
        'time_of_day': analysis.get('time_of_day', ''),
    }


def _notify_progress(progress_cb, done, total, panel_result):
    """Invoke the progress callback without letting it break the batch."""
    if progress_cb is None:
        return
    try:
        progress_cb(done, total, panel_result)
    except Exception as e:
        _log_warning("[Batch] progress_cb raised (ignored): {0}".format(e))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_batch(show, episode, provider=DEFAULT_PROVIDER, generate=True,
              max_panels=None, progress_cb=None):
    """Run a single-pass analyze (+ optionally generate) batch over an episode.

    HONESTY: this is SINGLE-PASS analyze + generate per panel. The iterative
    refinement loop (multi-view capture, scoring, up-to-N corrections) lives
    in ui/widgets/active_panel_widget.py and is not reusable here yet. See
    the module docstring.

    Args:
        show: Show name (display name or folder name).
        episode: Episode name (display name or safe folder name).
        provider: Provider display string as used by the plugin settings UI,
                  e.g. 'Claude (Anthropic)', 'GPT-4 Vision (OpenAI)', 'Auto'.
        generate: When True, build the scene for each panel via SceneBuilder.
        max_panels: Optional cap on how many panels to process (None = all).
        progress_cb: Optional callable(done_count, total_count, panel_result)
                     invoked after each panel. Exceptions in the callback are
                     logged and ignored.

    Returns:
        Summary dict with per-panel results, counters, and the report path.
        On setup failure (no editor, missing episode) the dict contains an
        'error' key and no panels are processed.
    """
    started = datetime.now()
    summary = {
        'show': str(show),
        'episode': str(episode),
        'provider': str(provider),
        'generate': bool(generate),
        'mode': 'single_pass',
        'note': (
            'Single-pass analyze+generate per panel. The iterative '
            'refinement loop lives in the UI widget '
            '(ui/widgets/active_panel_widget.py) and is not reusable '
            'headlessly yet.'
        ),
        'started': started.isoformat(),
        'finished': None,
        'panels_total': 0,
        'panels_processed': 0,
        'analyzed_fresh': 0,
        'analyzed_from_cache': 0,
        'generated': 0,
        'failed': 0,
        'panels': [],
        'report_path': None,
    }

    if not UNREAL_AVAILABLE:
        summary['error'] = (
            'run_batch requires the Unreal Editor Python environment '
            '(PanelAnalyzer and SceneBuilder depend on the unreal module).'
        )
        _log_error("[Batch] {0}".format(summary['error']))
        return summary

    episode_dir, episode_folder = _resolve_episode_dir(show, episode)
    if episode_dir is None:
        summary['error'] = (
            "Episode '{0}' not found in show '{1}' (checked display and "
            "safe folder names under Shows/<show>/Episodes/)".format(episode, show)
        )
        _log_error("[Batch] {0}".format(summary['error']))
        return summary
    summary['episode_folder'] = episode_folder
    summary['episode_dir'] = str(episode_dir)

    panel_paths = _list_panel_images(episode_dir)
    summary['panels_total'] = len(panel_paths)
    if not panel_paths:
        summary['error'] = "No panel images found in {0}".format(episode_dir / "Panels")
        _log_error("[Batch] {0}".format(summary['error']))
        return summary

    if max_panels is not None:
        try:
            cap = int(max_panels)
            if cap > 0:
                panel_paths = panel_paths[:cap]
        except (TypeError, ValueError):
            _log_warning("[Batch] Ignoring invalid max_panels: {0!r}".format(max_panels))

    _log("=" * 70)
    _log("[Batch] Overnight batch: show='{0}' episode='{1}'".format(show, episode_folder))
    _log("[Batch] Provider: {0} | Generate scenes: {1} | Panels: {2}".format(
        provider, generate, len(panel_paths)))
    _log("[Batch] Mode: single-pass (no iterative refinement; see module docstring)")
    _log("=" * 70)

    try:
        analyzer = _build_panel_analyzer(provider)
    except Exception as e:
        summary['error'] = "Failed to create PanelAnalyzer: {0}".format(e)
        _log_error("[Batch] {0}".format(summary['error']))
        return summary

    builder = None
    if generate:
        try:
            from core.scene_builder import SceneBuilder
            builder = SceneBuilder(show_name=str(show))
        except Exception as e:
            summary['error'] = "Failed to create SceneBuilder: {0}".format(e)
            _log_error("[Batch] {0}".format(summary['error']))
            return summary

    total = len(panel_paths)
    for index, panel_path in enumerate(panel_paths):
        panel_result = {
            'index': index,
            'panel': panel_path.name,
            'path': str(panel_path),
            'status': 'ok',
            'analyzed': False,
            'from_cache': False,
            'generated': False,
            'entities': {},
            'scene': None,
            'errors': [],
        }
        _log("[Batch] Panel {0}/{1}: {2}".format(index + 1, total, panel_path.name))

        # --- Analysis (cache-aware) ---
        analysis = None
        try:
            was_cached = False
            if hasattr(analyzer, 'get_cached_analysis'):
                try:
                    was_cached = analyzer.get_cached_analysis(str(panel_path), str(show)) is not None
                except Exception:
                    was_cached = False

            analysis = analyzer.analyze(str(panel_path), show_name=str(show))
            if isinstance(analysis, dict):
                panel_result['analyzed'] = True
                panel_result['from_cache'] = was_cached
                panel_result['entities'] = _extract_entities(analysis)
                panel_result['analysis'] = analysis
                if was_cached:
                    summary['analyzed_from_cache'] += 1
                else:
                    summary['analyzed_fresh'] += 1
            else:
                panel_result['status'] = 'analysis_failed'
                panel_result['errors'].append('Analysis returned no data')
        except Exception as e:
            panel_result['status'] = 'analysis_failed'
            panel_result['errors'].append('Analysis failed: {0}'.format(e))
            _log_error("[Batch] Analysis failed for {0}: {1}".format(panel_path.name, e))

        # --- Generation (optional, single pass) ---
        if generate and builder is not None and isinstance(analysis, dict):
            try:
                scene = builder.build_scene(analysis, panel_index=index)
                if scene:
                    panel_result['generated'] = True
                    panel_result['scene'] = _summarize_scene(scene)
                    summary['generated'] += 1
                else:
                    panel_result['status'] = 'generation_failed'
                    panel_result['errors'].append(
                        'SceneBuilder returned no scene (see Output Log; '
                        'common causes: no editor world, sequence creation failed)')
            except Exception as e:
                panel_result['status'] = 'generation_failed'
                panel_result['errors'].append('Generation failed: {0}'.format(e))
                _log_error("[Batch] Generation failed for {0}: {1}".format(panel_path.name, e))

        if panel_result['status'] != 'ok':
            summary['failed'] += 1

        summary['panels'].append(panel_result)
        summary['panels_processed'] += 1
        _notify_progress(progress_cb, index + 1, total, panel_result)

    summary['finished'] = datetime.now().isoformat()
    summary['duration_seconds'] = (datetime.now() - started).total_seconds()

    # --- Report ---
    try:
        timestamp = started.strftime('%Y%m%d_%H%M%S')
        report_name = "batch_{0}_{1}_{2}.json".format(
            _sanitize_name(show) or 'show',
            _sanitize_name(episode_folder or episode) or 'episode',
            timestamp)
        report_path = _reports_dir() / report_name
        with open(str(report_path), 'w') as f:
            # default=str guards against any stray unreal objects.
            json.dump(summary, f, indent=2, default=str)
        summary['report_path'] = str(report_path)
        _log("[Batch] Report written: {0}".format(report_path))
    except Exception as e:
        _log_error("[Batch] Failed to write report: {0}".format(e))

    _log("[Batch] Done: {0} panels, {1} fresh analyses, {2} cached, "
         "{3} generated, {4} failed".format(
             summary['panels_processed'], summary['analyzed_fresh'],
             summary['analyzed_from_cache'], summary['generated'],
             summary['failed']))
    return summary


# ---------------------------------------------------------------------------
# Console entry point:
#   py ".../core/batch_runner.py" <show> <episode> [provider] [--no-generate] [--max-panels N]
# ---------------------------------------------------------------------------

def _parse_argv(argv):
    """Parse console arguments (manual parsing; argparse would sys.exit the
    editor's Python console on error).

    Returns:
        dict of run_batch kwargs, or None if usage is invalid.
    """
    positional = []
    generate = True
    max_panels = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--no-generate':
            generate = False
        elif arg == '--max-panels':
            if i + 1 >= len(argv):
                _log_error("[Batch] --max-panels requires a number")
                return None
            i += 1
            try:
                max_panels = int(argv[i])
            except ValueError:
                _log_error("[Batch] Invalid --max-panels value: {0}".format(argv[i]))
                return None
        elif arg.startswith('--max-panels='):
            try:
                max_panels = int(arg.split('=', 1)[1])
            except ValueError:
                _log_error("[Batch] Invalid --max-panels value: {0}".format(arg))
                return None
        elif arg.startswith('--'):
            _log_error("[Batch] Unknown flag: {0}".format(arg))
            return None
        else:
            positional.append(arg)
        i += 1

    if len(positional) < 2:
        _log_error(
            "Usage: py batch_runner.py <show> <episode> [provider] "
            "[--no-generate] [--max-panels N]")
        return None

    kwargs = {
        'show': positional[0],
        'episode': positional[1],
        'generate': generate,
        'max_panels': max_panels,
    }
    if len(positional) >= 3:
        kwargs['provider'] = positional[2]
    return kwargs


if __name__ == "__main__":
    # When run as a script (py ".../batch_runner.py"), the plugin Python root
    # may not be on sys.path yet; core/ is one level below it.
    _PLUGIN_PYTHON_DIR = str(Path(__file__).resolve().parents[1])
    if _PLUGIN_PYTHON_DIR not in sys.path:
        sys.path.insert(0, _PLUGIN_PYTHON_DIR)

    _kwargs = _parse_argv(sys.argv[1:])
    if _kwargs is not None:
        _summary = run_batch(**_kwargs)
        if _summary.get('error'):
            _log_error("[Batch] Batch did not complete: {0}".format(_summary['error']))
        elif _summary.get('report_path'):
            _log("[Batch] Summary report: {0}".format(_summary['report_path']))

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Script Breakdown Module

Text-only LLM step that turns a script or treatment into a structured shot
list (a "breakdown"): one dict per planned storyboard panel with description,
characters, props, location, and shot size. No images are involved; this is
the pre-storyboard planning step.

Provider plumbing (verified against the existing code):
    api/ai_client_enhanced.EnhancedAIClient already supports text-only calls
    via analyze_text(prompt), which sends a message WITHOUT an image block
    (see _build_claude_payload / _build_openai_payload with image_base64 set
    to None). That path is used first. If that client cannot be built (no
    session, no key), we fall back to calling the Anthropic REST endpoint
    directly, following the header pattern from
    core/ai_providers/claude_provider.py (x-api-key + anthropic-version).

Persistence honesty (verified against the managers):
    EpisodesManager and ShowsManager do NOT support panels without images:
    import_panels_to_episode copies image FILES into Episodes/<ep>/Panels/
    and panel_count is computed by globbing *.png / *.jpg; the UI enumerates
    panels from those image files. A metadata-only "text placeholder panel"
    would be invisible to the rest of the plugin. save_breakdown_as_episode
    therefore writes the breakdown JSON to Saved/StoryboardTo3D/breakdowns/
    (plus a convenience copy into the episode's existing Scripts/ folder
    when the episode exists) and returns that path.

Usage:
    from core.script_breakdown import breakdown_script, save_breakdown_as_episode
    shots = breakdown_script(open(path).read(), provider='Claude (Anthropic)')
    report = save_breakdown_as_episode(shots, "MyShow", "Episode_1")

Console usage (works in the UE Python console; the LLM call also works in a
plain Python environment with an ANTHROPIC_API_KEY set):
    py ".../core/script_breakdown.py" "C:/scripts/ep1.txt" --max-panels 12 --show MyShow --episode Episode_1
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Guard the unreal import: this module is text-only and can run outside the
# editor (e.g. breaking down a script on a workstation with an API key).
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False


# Anthropic REST constants, mirroring core/ai_providers/claude_provider.py.
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"

VALID_SHOTS = ('wide', 'medium', 'close')

_SHOT_SYNONYMS = {
    'wide': 'wide', 'ws': 'wide', 'extreme_wide': 'wide', 'ews': 'wide',
    'establishing': 'wide', 'long': 'wide', 'full': 'wide',
    'medium': 'medium', 'ms': 'medium', 'mid': 'medium',
    'medium_wide': 'medium', 'medium_close': 'medium', 'two_shot': 'medium',
    'close': 'close', 'cu': 'close', 'close-up': 'close', 'closeup': 'close',
    'close_up': 'close', 'extreme_close': 'close', 'ecu': 'close',
    'insert': 'close',
}


def _log(message):
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


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_breakdown_prompt(script_text, max_panels):
    """Strict JSON-array prompt for the shot-list breakdown."""
    return (
        "You are a storyboard supervisor breaking a script into a shot list.\n"
        "Read the script below and produce AT MOST {0} shots covering the\n"
        "story in order.\n"
        "\n"
        "Return ONLY a JSON array (no prose, no markdown fences). Each array\n"
        "element must be an object with EXACTLY these keys:\n"
        '  "panel": integer, 1-based shot number in story order\n'
        '  "description": one or two sentences describing the shot action\n'
        '  "characters": array of character name strings visible in the shot\n'
        '  "props": array of significant prop name strings in the shot\n'
        '  "location": short location name string (e.g. "Kitchen", "Forest")\n'
        '  "shot": one of exactly "wide", "medium", or "close"\n'
        "\n"
        "Rules:\n"
        "- Use consistent character and location names across shots.\n"
        "- Props are moveable objects only; do not list scenery as props.\n"
        "- Do not exceed {0} shots. Fewer is fine for short scripts.\n"
        "- Output must be a single valid JSON array and nothing else.\n"
        "\n"
        "SCRIPT:\n"
        "{1}\n"
    ).format(int(max_panels), script_text)


# ---------------------------------------------------------------------------
# Provider plumbing (text-only)
# ---------------------------------------------------------------------------

def _map_provider(provider):
    """Map a plugin provider display string to the EnhancedAIClient name.

    Same translation as core/batch_runner.py: the settings UI stores strings
    like 'Claude (Anthropic)' / 'GPT-4 Vision (OpenAI)' / 'Auto', while
    EnhancedAIClient.PROVIDERS uses 'Claude 3.5 Sonnet' / 'OpenAI GPT-4o'.

    Returns:
        tuple: (enhanced_client_provider_name_or_None, kind) with kind in
               ('claude', 'openai', 'local', 'auto').
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
    _log_warning("[Breakdown] Unknown provider '{0}', using configured default".format(provider))
    return None, 'auto'


def _settings_manager_ai_settings():
    """Read the plugin's global ai_settings dict, or {} outside the editor."""
    try:
        from core.settings_manager import get_settings_manager
        return get_settings_manager().global_settings.get('ai_settings', {})
    except Exception:
        return {}


def _try_enhanced_client(prompt, provider):
    """Attempt the text call through the existing EnhancedAIClient plumbing.

    Returns:
        Response text string, or None if the client path is unusable.
    """
    enhanced_name, kind = _map_provider(provider)
    if kind == 'local':
        _log_warning(
            "[Breakdown] Provider '{0}' is a local vision provider with no "
            "text path here; trying the Anthropic fallback next.".format(provider))
        return None

    try:
        from api.ai_client_enhanced import create_ai_client
        client = create_ai_client(provider=enhanced_name)
    except Exception as e:
        _log_warning("[Breakdown] EnhancedAIClient unavailable: {0}".format(e))
        return None

    # Bridge API keys stored by the plugin Settings UI (ai_settings) when the
    # client's own config/env sources came up empty.
    if not getattr(client, 'api_key', ''):
        ai_settings = _settings_manager_ai_settings()
        bridged_kind = kind
        if bridged_kind == 'auto':
            client_provider = getattr(client, 'provider', '') or ''
            bridged_kind = 'claude' if 'Claude' in client_provider else 'openai'
        key = ''
        if bridged_kind == 'claude':
            key = ai_settings.get('claude_api_key', '') or ''
        elif bridged_kind == 'openai':
            key = ai_settings.get('openai_api_key', '') or ''
        if key:
            client.api_key = key
            try:
                client._update_headers()
            except Exception as e:
                _log_warning("[Breakdown] Could not refresh client headers: {0}".format(e))

    if not getattr(client, 'api_key', ''):
        _log_warning("[Breakdown] No API key for EnhancedAIClient; trying Anthropic fallback")
        return None
    if not hasattr(client, 'analyze_text'):
        _log_warning("[Breakdown] Client has no analyze_text method; trying Anthropic fallback")
        return None

    try:
        _log("[Breakdown] Text call via EnhancedAIClient ({0})".format(
            getattr(client, 'provider', 'unknown')))
        return client.analyze_text(prompt)
    except Exception as e:
        _log_warning("[Breakdown] EnhancedAIClient text call failed: {0}".format(e))
        return None


def _find_anthropic_api_key():
    """Locate an Anthropic key: plugin settings first, then environment."""
    ai_settings = _settings_manager_ai_settings()
    key = ai_settings.get('claude_api_key', '') or ''
    if key:
        return key
    return os.environ.get('ANTHROPIC_API_KEY', '') or ''


def _call_anthropic_direct(prompt, api_key, model=None, max_tokens=4000, timeout=120):
    """Text-only call to the Anthropic Messages API.

    Follows the header pattern from core/ai_providers/claude_provider.py
    (x-api-key + anthropic-version), with a text-only content block instead
    of image blocks.

    Returns:
        Response text string, or None on failure (logged).
    """
    if not REQUESTS_AVAILABLE:
        _log_error("[Breakdown] requests library not available for the Anthropic fallback")
        return None
    if not api_key:
        return None

    ai_settings = _settings_manager_ai_settings()
    model = model or ai_settings.get('claude_model', '') or ANTHROPIC_DEFAULT_MODEL

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_API_VERSION,
    }
    request_body = {
        "model": model,
        "max_tokens": int(max_tokens),
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }],
    }

    try:
        _log("[Breakdown] Text call via Anthropic REST ({0})".format(model))
        response = requests.post(
            ANTHROPIC_MESSAGES_URL,
            headers=headers,
            json=request_body,
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()

        # Extract text blocks (same shape claude_provider parses).
        response_text = ""
        for block in result.get('content', []):
            if isinstance(block, dict) and block.get('type') == 'text':
                response_text += block.get('text', '')
        return response_text or None
    except Exception as e:
        _log_error("[Breakdown] Anthropic REST call failed: {0}".format(e))
        return None


def _request_text_completion(prompt, provider):
    """Run the text prompt through the best available plumbing.

    Order: EnhancedAIClient.analyze_text (existing text-only path), then a
    direct Anthropic REST call. Raises RuntimeError when nothing works so
    callers never receive a silently-empty breakdown.
    """
    response = _try_enhanced_client(prompt, provider)
    if response:
        return response

    api_key = _find_anthropic_api_key()
    if api_key:
        response = _call_anthropic_direct(prompt, api_key)
        if response:
            return response

    raise RuntimeError(
        "No text-capable AI provider available. Configure an API key in the "
        "plugin Settings (Claude/OpenAI) or set ANTHROPIC_API_KEY in the "
        "environment.")


# ---------------------------------------------------------------------------
# Response parsing / normalization
# ---------------------------------------------------------------------------

def _parse_llm_json(response_text):
    """Parse the LLM response using the plugin's robust extractor.

    core.json_extractor has no unreal dependency, but importing it through
    the core package pulls in unreal (core/__init__.py imports analyzer
    modules eagerly), so outside the editor we import it as a sibling file.
    """
    parser = None
    try:
        from core.json_extractor import parse_llm_json as parser
    except Exception:
        try:
            from json_extractor import parse_llm_json as parser
        except Exception:
            parser = None

    if parser is not None:
        return parser(response_text)

    # Last-resort minimal fallback: direct parse of the bracketed slice.
    _log_warning("[Breakdown] json_extractor unavailable; using minimal JSON parse")
    start = response_text.find('[')
    end = response_text.rfind(']')
    if start != -1 and end > start:
        return json.loads(response_text[start:end + 1])
    return json.loads(response_text)


def _as_string_list(value):
    """Coerce an LLM field to a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(',')]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        items = []
        for entry in value:
            text = str(entry).strip()
            if text:
                items.append(text)
        return items
    return [str(value)]


def _normalize_shot(value):
    """Clamp an LLM shot label to 'wide' | 'medium' | 'close'."""
    text = str(value or '').strip().lower().replace(' ', '_').replace('-', '_')
    if text in VALID_SHOTS:
        return text
    mapped = _SHOT_SYNONYMS.get(text)
    if mapped:
        return mapped
    for shot in VALID_SHOTS:
        if shot in text:
            return shot
    return 'medium'


def _normalize_entry(entry, panel_number):
    """Normalize one raw LLM shot entry to the breakdown schema."""
    if not isinstance(entry, dict):
        entry = {'description': str(entry)}
    description = str(entry.get('description', '')).strip()
    if not description:
        description = 'Shot {0}'.format(panel_number)
    location = str(entry.get('location', '')).strip() or 'Unknown'
    return {
        'panel': panel_number,
        'description': description,
        'characters': _as_string_list(entry.get('characters')),
        'props': _as_string_list(entry.get('props')),
        'location': location,
        'shot': _normalize_shot(entry.get('shot')),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def breakdown_script(script_text, provider=None, max_panels=24):
    """Turn a script/treatment into a structured shot list via a text LLM call.

    Args:
        script_text: The script or treatment text to break down.
        provider: Optional provider display string as used by the plugin
                  settings UI (e.g. 'Claude (Anthropic)'). None uses the
                  configured default, with a direct-Anthropic fallback.
        max_panels: Maximum number of shots to request/return (default 24).

    Returns:
        List of dicts, each: {'panel': int, 'description': str,
        'characters': list, 'props': list, 'location': str,
        'shot': 'wide'|'medium'|'close'}, renumbered 1..N in order.

    Raises:
        ValueError: If script_text is empty.
        RuntimeError: If no provider is usable or no JSON shot list could be
                      extracted from the response.
    """
    if not script_text or not str(script_text).strip():
        raise ValueError("script_text is empty")

    try:
        max_panels = max(1, int(max_panels))
    except (TypeError, ValueError):
        max_panels = 24

    prompt = _build_breakdown_prompt(str(script_text), max_panels)
    response_text = _request_text_completion(prompt, provider)

    try:
        parsed = _parse_llm_json(response_text)
    except Exception as e:
        raise RuntimeError(
            "Could not extract a JSON shot list from the LLM response: "
            "{0}. Response preview: {1}".format(e, str(response_text)[:200]))

    # Accept either a bare array or a wrapper object with a list inside.
    if isinstance(parsed, dict):
        for key in ('shots', 'panels', 'breakdown', 'shot_list'):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        raise RuntimeError(
            "LLM response parsed to {0}, expected a JSON array of shots".format(
                type(parsed).__name__))

    breakdown = []
    for entry in parsed[:max_panels]:
        breakdown.append(_normalize_entry(entry, len(breakdown) + 1))

    _log("[Breakdown] Produced {0} shots (max {1})".format(len(breakdown), max_panels))
    return breakdown


def _breakdowns_dir():
    """Saved/StoryboardTo3D/breakdowns, with a logged fallback outside UE."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'Paths') and hasattr(unreal.Paths, 'project_saved_dir'):
        try:
            base = Path(unreal.Paths.project_saved_dir())
        except Exception as e:
            _log_warning("[Breakdown] Could not resolve project Saved dir: {0}".format(e))
            base = Path.home() / "StoryboardToUnreal" / "Saved"
    else:
        base = Path.home() / "StoryboardToUnreal" / "Saved"
        _log_warning("[Breakdown] Outside UE; saving under {0}".format(base))
    breakdowns = base / "StoryboardTo3D" / "breakdowns"
    breakdowns.mkdir(parents=True, exist_ok=True)
    return breakdowns


def _find_episode_dir(show, episode):
    """Locate an existing episode directory, or None. Never creates one."""
    if not UNREAL_AVAILABLE:
        return None
    try:
        from core.episodes_manager import EpisodesManager
        shows_root = EpisodesManager().shows_root
    except Exception as e:
        _log_warning("[Breakdown] EpisodesManager unavailable: {0}".format(e))
        return None
    for show_folder in (str(show), _sanitize_name(show)):
        for episode_folder in (str(episode), _sanitize_name(episode)):
            candidate = shows_root / show_folder / "Episodes" / episode_folder
            if candidate.exists():
                return candidate
    return None


def save_breakdown_as_episode(breakdown, show, episode):
    """Persist a breakdown for a show/episode and return the saved path.

    HONESTY (what the managers actually support): panels in this plugin ARE
    image files. EpisodesManager.import_panels_to_episode copies image files
    into Episodes/<ep>/Panels/ and computes panel_count by globbing
    *.png / *.jpg; the UI builds its panel list from those files. There is
    no image-less placeholder panel concept, so writing shot descriptions
    into panel metadata alone would create panels nothing can see. This
    function therefore:
        1. Writes the breakdown JSON to Saved/StoryboardTo3D/breakdowns/.
        2. If the episode directory already exists, also drops a copy at
           Episodes/<ep>/Scripts/script_breakdown.json (the Scripts folder
           is created by EpisodesManager.create_episode) so the breakdown
           travels with the episode.

    Args:
        breakdown: List of shot dicts from breakdown_script().
        show: Show name (display or folder name).
        episode: Episode name (display or safe folder name).

    Returns:
        String path of the primary saved breakdown JSON.

    Raises:
        ValueError: If breakdown is empty or not a list.
    """
    if not isinstance(breakdown, list) or not breakdown:
        raise ValueError("breakdown must be a non-empty list of shot dicts")

    payload = {
        'show': str(show),
        'episode': str(episode),
        'created': datetime.now().isoformat(),
        'panel_count': len(breakdown),
        'note': (
            'Text-only breakdown. Panels in this plugin are image files, so '
            'these shots are a planning artifact, not importable panels. '
            'Draw or generate panel images, import them with '
            'EpisodesManager.import_panels_to_episode, then use this shot '
            'list as the reference.'
        ),
        'shots': breakdown,
    }

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = "breakdown_{0}_{1}_{2}.json".format(
        _sanitize_name(show) or 'show',
        _sanitize_name(episode) or 'episode',
        timestamp)
    primary_path = _breakdowns_dir() / file_name
    with open(str(primary_path), 'w') as f:
        json.dump(payload, f, indent=2)
    _log("[Breakdown] Saved breakdown: {0}".format(primary_path))

    # Convenience copy inside the episode's Scripts folder when it exists.
    episode_dir = _find_episode_dir(show, episode)
    if episode_dir is not None:
        try:
            scripts_dir = episode_dir / "Scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            episode_copy = scripts_dir / "script_breakdown.json"
            with open(str(episode_copy), 'w') as f:
                json.dump(payload, f, indent=2)
            _log("[Breakdown] Copied breakdown into episode: {0}".format(episode_copy))
        except Exception as e:
            _log_warning("[Breakdown] Could not copy into episode Scripts folder: {0}".format(e))
    else:
        _log("[Breakdown] Episode folder not found; breakdown saved centrally only")

    return str(primary_path)


# ---------------------------------------------------------------------------
# Console entry point:
#   py ".../core/script_breakdown.py" <script.txt> [provider]
#       [--max-panels N] [--show NAME --episode NAME]
# ---------------------------------------------------------------------------

def _parse_argv(argv):
    """Manual argv parsing (argparse would sys.exit the editor console)."""
    positional = []
    options = {'max_panels': 24, 'show': None, 'episode': None}

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--max-panels', '--show', '--episode'):
            if i + 1 >= len(argv):
                _log_error("[Breakdown] {0} requires a value".format(arg))
                return None
            i += 1
            key = arg.lstrip('-').replace('-', '_')
            options[key] = argv[i]
        elif arg.startswith('--'):
            _log_error("[Breakdown] Unknown flag: {0}".format(arg))
            return None
        else:
            positional.append(arg)
        i += 1

    if not positional:
        _log_error(
            "Usage: py script_breakdown.py <script.txt> [provider] "
            "[--max-panels N] [--show NAME --episode NAME]")
        return None

    try:
        options['max_panels'] = max(1, int(options['max_panels']))
    except (TypeError, ValueError):
        _log_error("[Breakdown] Invalid --max-panels value")
        return None

    options['script_path'] = positional[0]
    options['provider'] = positional[1] if len(positional) > 1 else None
    return options


if __name__ == "__main__":
    # When run as a script, the plugin Python root may not be on sys.path
    # yet; core/ is one level below it.
    _PLUGIN_PYTHON_DIR = str(Path(__file__).resolve().parents[1])
    if _PLUGIN_PYTHON_DIR not in sys.path:
        sys.path.insert(0, _PLUGIN_PYTHON_DIR)

    _options = _parse_argv(sys.argv[1:])
    if _options is not None:
        _script_file = Path(_options['script_path'])
        if not _script_file.exists():
            _log_error("[Breakdown] Script file not found: {0}".format(_script_file))
        else:
            with open(str(_script_file), 'r') as _f:
                _text = _f.read()
            try:
                _shots = breakdown_script(
                    _text,
                    provider=_options['provider'],
                    max_panels=_options['max_panels'])
                _log(json.dumps(_shots, indent=2))
                if _options['show'] and _options['episode']:
                    _saved = save_breakdown_as_episode(
                        _shots, _options['show'], _options['episode'])
                    _log("[Breakdown] Saved to: {0}".format(_saved))
            except (ValueError, RuntimeError) as _e:
                _log_error("[Breakdown] {0}".format(_e))

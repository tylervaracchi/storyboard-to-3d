# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
AI cataloging for the show asset library.

Sends each asset's thumbnail (generating one first via
core.thumbnail_generator when the entry lacks a valid one) through the
configured vision provider (AIProviderFactory 'auto') and asks for a
strict JSON payload:

    - description: one concise physical description of what the object
      IS (never the render, background or lighting),
    - aliases: 5 lowercase synonyms an artist might type when searching,
    - category_guess: one of characters/props/locations,
    - attached_props (optional, characters only): props visibly held/worn
      as part of the mesh; written to an entry only when the entry has no
      attached_props yet (manual lists are never clobbered).

Responses are parsed with core.json_extractor so markdown-wrapped or
slightly malformed JSON still lands. describe_asset never raises; it
returns None on any failure and logs the reason.

COST: each described asset costs exactly ONE small image call to the
configured provider (a single ~256px thumbnail plus a short prompt),
so cataloging a whole library costs roughly one cheap vision request
per asset that is missing a description.

catalog_library() fills ONLY empty/placeholder descriptions unless
overwrite=True, MERGES AI aliases with existing ones (user aliases are
never dropped), and saves the show's asset_library.json exactly once.
"""

import json
import traceback
from pathlib import Path

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:  # Running outside the Unreal editor (tests, tooling)
    unreal = None
    UNREAL_AVAILABLE = False

from core.thumbnail_generator import (
    generate_asset_thumbnail,
    safe_thumbnail_filename,
    is_valid_png,
    LIBRARY_CATEGORIES,
    LOCATION_THUMBNAIL_DEFERRED,
)
from core.json_extractor import parse_llm_json

# Descriptions considered "not written yet" (compared lowercase/stripped).
# 'converted from legacy format' comes from core.utils.sanitize_asset_data.
PLACEHOLDER_DESCRIPTIONS = frozenset((
    '',
    'no description',
    'converted from legacy format',
    'describe this asset...',
    'tbd',
    'todo',
    'n/a',
    'none',
))

# Image suffixes every provider's validate_images accepts
SUPPORTED_IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')

MAX_ALIASES = 5

# Structured-outputs schema (Claude honors it via the json_schema kwarg;
# other providers simply ignore the extra kwarg)
CATALOG_JSON_SCHEMA = {
    'type': 'object',
    'properties': {
        'description': {'type': 'string'},
        'aliases': {
            'type': 'array',
            'items': {'type': 'string'},
            'minItems': MAX_ALIASES,
            'maxItems': MAX_ALIASES,
        },
        'category_guess': {
            'type': 'string',
            'enum': list(LIBRARY_CATEGORIES),
        },
        # Optional: held/worn items that are part of a character mesh
        # (e.g. a scythe modeled into the Farmer's hand). Models may omit.
        'attached_props': {
            'type': 'array',
            'items': {'type': 'string'},
        },
    },
    'required': ['description', 'aliases', 'category_guess'],
    'additionalProperties': False,
}

_PROMPT_TEMPLATE = (
    'You are cataloging a 3D asset for a film previsualization asset library.\n'
    'The image is an automatically rendered 3/4 view of a single 3D asset '
    'named "{name}"{path_hint}.\n\n'
    'Respond with ONLY a JSON object, no markdown fences, no extra text:\n'
    '{{\n'
    '  "description": "one concise sentence describing what the physical object IS '
    '(its shape, colors, notable parts). Describe the object itself, never the '
    'render, background, lighting or image quality",\n'
    '  "aliases": ["exactly {max_aliases} lowercase synonyms or alternate words '
    'an artist might type to find this asset"],\n'
    '  "category_guess": "one of: characters, props, locations",\n'
    '  "attached_props": ["OPTIONAL - only for a character (skeletal mesh): '
    'lowercase names of props visibly held or worn as part of the mesh '
    '(e.g. a scythe in the hand). Omit this field entirely for non-characters '
    'or when nothing is held or worn"]\n'
    '}}'
)


def _log(msg):
    if unreal is not None:
        unreal.log('[AssetCataloger] {0}'.format(msg))
    else:
        print('[AssetCataloger] {0}'.format(msg))


def _warn(msg):
    if unreal is not None:
        unreal.log_warning('[AssetCataloger] {0}'.format(msg))
    else:
        print('[AssetCataloger] WARNING: {0}'.format(msg))


def _error(msg):
    if unreal is not None:
        unreal.log_error('[AssetCataloger] {0}'.format(msg))
    else:
        print('[AssetCataloger] ERROR: {0}'.format(msg))


def is_placeholder_description(description):
    """True when a library description counts as empty/placeholder."""
    if not isinstance(description, str):
        return True
    text = description.strip().lower()
    if text in PLACEHOLDER_DESCRIPTIONS:
        return True
    # core.utils.sanitize_asset_data writes 'Unknown data type: ...'
    if text.startswith('unknown data type'):
        return True
    return False


def _existing_thumbnail_path(entry):
    """Return a usable thumbnail image path from an entry, or None.

    PNG files must carry real PNG magic bytes (the old float-render-target
    bug wrote EXR data into .png files, which no provider can decode).
    """
    thumb = entry.get('thumbnail')
    if not isinstance(thumb, dict):
        return None
    path = thumb.get('path')
    if not path:
        return None
    try:
        p = Path(str(path))
        if not p.exists() or not p.is_file():
            return None
        suffix = p.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            return None
        if suffix == '.png' and not is_valid_png(p):
            return None
        return str(p)
    except OSError:
        return None


def _default_thumb_dir():
    """Legacy content-wide thumbnail folder, used when no show dir is given."""
    if unreal is None:
        return None
    try:
        return Path(unreal.Paths.project_content_dir()) / 'StoryboardTo3D' / 'AssetThumbnails'
    except Exception as e:
        _warn('Could not resolve project content dir: {0}'.format(e))
        return None


def _create_provider():
    """Create the configured AI provider (factory 'auto'). None on failure."""
    try:
        from core.ai_providers.provider_factory import AIProviderFactory
        return AIProviderFactory.create_provider('auto')
    except Exception as e:
        _error('Could not create an AI provider: {0}'.format(e))
        return None


def _normalize_category_guess(value):
    """Map a model's category string onto the library categories."""
    text = str(value or '').strip().lower()
    if text in LIBRARY_CATEGORIES:
        return text
    mapping = {
        'character': 'characters',
        'prop': 'props',
        'object': 'props',
        'item': 'props',
        'location': 'locations',
        'environment': 'locations',
        'set': 'locations',
        'scene': 'locations',
    }
    return mapping.get(text, 'props')


def _normalize_aliases(raw_aliases):
    """Lowercase, strip, dedupe and cap the model's alias list."""
    aliases = []
    seen = set()
    if not isinstance(raw_aliases, (list, tuple)):
        return aliases
    for alias in raw_aliases:
        text = str(alias).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        aliases.append(text)
        if len(aliases) >= MAX_ALIASES:
            break
    return aliases


def _normalize_attached_props(raw):
    """Lowercase, strip and dedupe the model's attached_props list.
    Returns [] when the field is missing or malformed (models may omit)."""
    attached = []
    seen = set()
    if not isinstance(raw, (list, tuple)):
        return attached
    for item in raw:
        text = str(item).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        attached.append(text)
    return attached


def merge_aliases(existing, new):
    """Merge AI aliases into existing ones without dropping or reordering
    anything the user already wrote (case-insensitive dedupe)."""
    merged = []
    seen = set()
    for alias in (existing or []):
        text = str(alias).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        merged.append(text)
    for alias in (new or []):
        text = str(alias).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        merged.append(text)
    return merged


def _ensure_thumbnail(entry_name, entry, thumb_dir):
    """Return a usable thumbnail path for the entry, generating one when
    missing/broken. Updates entry['thumbnail'] in place on generation.

    Returns LOCATION_THUMBNAIL_DEFERRED (truthy sentinel) for location
    entries whose level is not open in the editor: those are skipped with
    a single info line, never counted as failed."""
    thumb = entry.get('thumbnail')
    deferred_placeholder = isinstance(thumb, dict) and thumb.get('type') == 'placeholder'
    # A deferred location placeholder (map glyph) is not a describable
    # image: retry generation instead of sending the glyph to the provider
    existing = None if deferred_placeholder else _existing_thumbnail_path(entry)
    if existing:
        return existing

    asset_path = str(entry.get('asset_path') or '').strip()
    if not asset_path:
        _warn('{0}: no valid thumbnail and no asset_path to render one'.format(entry_name))
        return None

    directory = Path(thumb_dir) if thumb_dir else _default_thumb_dir()
    if directory is None:
        _warn('{0}: no thumbnail directory available'.format(entry_name))
        return None
    out_png = directory / (safe_thumbnail_filename(entry_name) + '.png')

    # One render via the headless-verified generator; never raises
    status = generate_asset_thumbnail(asset_path, str(out_png))
    if status == LOCATION_THUMBNAIL_DEFERRED:
        _log('{0}: location thumbnail deferred (level not open in the '
             'editor); skipping AI description'.format(entry_name))
        return LOCATION_THUMBNAIL_DEFERRED
    if status:
        entry['thumbnail'] = {'type': 'content_browser', 'path': str(out_png)}
        return str(out_png)
    _warn('{0}: thumbnail generation failed (see log above)'.format(entry_name))
    return None


def describe_asset(entry_name, entry, provider=None, thumb_dir=None):
    """Describe one library entry with the configured vision provider.

    Ensures a thumbnail exists (rendering one with
    core.thumbnail_generator.generate_asset_thumbnail when the entry lacks
    a valid image; entry['thumbnail'] is updated in place in that case),
    sends that single small image to the provider with a strict JSON
    prompt, and parses the reply with core.json_extractor.

    COST: exactly one small image call to the provider per invocation.

    Args:
        entry_name: display name of the library entry (used in the prompt
            and for the generated thumbnail filename).
        entry: the library entry dict (asset_path/description/aliases/
            thumbnail). Only its 'thumbnail' key may be mutated.
        provider: an already-created provider to reuse (batch callers pass
            one so the factory is not re-run per asset). Auto-created via
            AIProviderFactory.create_provider('auto') when None.
        thumb_dir: directory for a newly generated thumbnail; defaults to
            the legacy content-wide AssetThumbnails folder.

    Returns:
        {'description': str, 'aliases': [str, ...], 'category_guess': str,
         'cost': float} on success, LOCATION_THUMBNAIL_DEFERRED (truthy
        sentinel) when the entry is a location whose level is not open in
        the editor (skip, not a failure), or None on any failure.
        Never raises.
    """
    try:
        if not isinstance(entry, dict):
            _warn('{0}: entry is not a dict'.format(entry_name))
            return None

        thumb_path = _ensure_thumbnail(entry_name, entry, thumb_dir)
        if thumb_path == LOCATION_THUMBNAIL_DEFERRED:
            return LOCATION_THUMBNAIL_DEFERRED
        if not thumb_path:
            return None

        if provider is None:
            provider = _create_provider()
        if provider is None:
            return None

        asset_path = str(entry.get('asset_path') or '').strip()
        path_hint = ' (asset path: {0})'.format(asset_path) if asset_path else ''
        prompt = _PROMPT_TEMPLATE.format(
            name=entry_name, path_hint=path_hint, max_aliases=MAX_ALIASES)

        result = provider.analyze_images(
            [thumb_path], prompt,
            json_schema=CATALOG_JSON_SCHEMA,
            max_tokens=1024,
        )
        if not isinstance(result, dict) or not result.get('success'):
            reason = result.get('error') if isinstance(result, dict) else 'no result'
            _warn('{0}: provider call failed: {1}'.format(entry_name, reason))
            return None

        response = result.get('response') or ''
        try:
            parsed = parse_llm_json(response)
        except ValueError as e:
            _warn('{0}: could not parse provider JSON: {1}'.format(entry_name, e))
            return None
        if not isinstance(parsed, dict):
            _warn('{0}: provider returned non-object JSON'.format(entry_name))
            return None

        description = str(parsed.get('description') or '').strip()
        if not description:
            _warn('{0}: provider returned an empty description'.format(entry_name))
            return None

        return {
            'description': description,
            'aliases': _normalize_aliases(parsed.get('aliases')),
            'category_guess': _normalize_category_guess(parsed.get('category_guess')),
            'attached_props': _normalize_attached_props(parsed.get('attached_props')),
            'cost': float(result.get('cost') or 0.0),
        }
    except Exception as e:
        _error('describe_asset failed for {0}: {1}'.format(entry_name, e))
        _error(traceback.format_exc())
        return None


def catalog_library(show_name, overwrite=False, progress_cb=None):
    """AI-describe every entry in a show's asset_library.json.

    Iterates the characters/props/locations categories and, for each entry
    whose description is empty/placeholder (or every entry when overwrite
    is True), renders a thumbnail if needed and asks the configured
    provider for a description plus aliases. AI aliases are MERGED into
    the existing list (user-written aliases are never dropped). The
    category_guess is only logged when it disagrees with the entry's
    actual category; entries are never moved. The library JSON is saved
    exactly once at the end, and only when something changed.

    COST: one small image call to the configured provider per asset that
    actually gets described (skipped assets cost nothing).

    Args:
        show_name: the show folder name (safe_name) under
            <project_content>/StoryboardTo3D/Shows.
        overwrite: re-describe entries that already have descriptions.
        progress_cb: optional callable (index, total, entry_name) -> bool;
            return False to cancel (remaining entries count as skipped).

    Returns:
        dict with lists 'described', 'skipped', 'failed' (entry names),
        plus 'cost' (float, summed provider cost) and, when the run could
        not start, an 'error' message. Never raises.
    """
    result = {'described': [], 'skipped': [], 'failed': [], 'cost': 0.0}
    try:
        # Lazy import: core.utils imports unreal unguarded, editor only
        try:
            from core.utils import get_shows_manager
            show_path = Path(get_shows_manager().shows_root) / show_name
        except Exception as e:
            result['error'] = 'Could not resolve the show folder: {0}'.format(e)
            _error(result['error'])
            return result

        library_path = show_path / 'asset_library.json'
        if not library_path.exists():
            result['error'] = 'No asset library at {0}'.format(library_path)
            _warn(result['error'])
            return result
        try:
            with open(str(library_path), 'r') as f:
                library = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            result['error'] = 'Could not read {0}: {1}'.format(library_path, e)
            _error(result['error'])
            return result

        thumb_dir = show_path / 'Thumbnails'

        entries = []
        for category in LIBRARY_CATEGORIES:
            cat = library.get(category)
            if isinstance(cat, dict):
                for name, data in cat.items():
                    entries.append((category, name, data))
        total = len(entries)

        provider = _create_provider()
        if provider is None:
            result['error'] = ('No AI provider available. Configure an API key '
                               'in Settings or start Ollama for LLaVA.')
            result['skipped'] = [name for _, name, _ in entries]
            return result
        _log('Cataloging {0} entries for show {1} with {2}'.format(
            total, show_name, getattr(provider, 'name', type(provider).__name__)))

        cancelled = False
        dirty = False

        for index, (category, name, data) in enumerate(entries):
            if not cancelled and progress_cb is not None:
                try:
                    if progress_cb(index, total, name) is False:
                        cancelled = True
                        _log('Cataloging cancelled at entry {0}/{1}'.format(index, total))
                except Exception as e:
                    _warn('progress callback failed: {0}'.format(e))
            if cancelled or not isinstance(data, dict):
                result['skipped'].append(name)
                continue

            existing_description = data.get('description', '')
            if not overwrite and not is_placeholder_description(existing_description):
                result['skipped'].append(name)
                continue

            # Nothing to look at and nothing to render: skip, not a failure
            if not str(data.get('asset_path') or '').strip() and \
                    _existing_thumbnail_path(data) is None:
                _log('Skipping {0}: no asset_path and no usable thumbnail'.format(name))
                result['skipped'].append(name)
                continue

            described = describe_asset(name, data, provider=provider,
                                       thumb_dir=thumb_dir)
            if described == LOCATION_THUMBNAIL_DEFERRED:
                # Location whose level is not open: skipped-with-reason
                # (single info line already logged by _ensure_thumbnail)
                result['skipped'].append(name)
                continue
            if described is None:
                result['failed'].append(name)
                continue

            data['description'] = described['description']
            data['aliases'] = merge_aliases(data.get('aliases'), described['aliases'])
            # Attached props: characters only, and only when the entry has
            # no attached_props yet (a manual list is never clobbered)
            if category == 'characters' and 'attached_props' not in data:
                ai_attached = described.get('attached_props') or []
                if ai_attached:
                    data['attached_props'] = ai_attached
            result['cost'] += described.get('cost', 0.0)
            guess = described.get('category_guess')
            if guess and guess != category:
                _log('{0}: AI suggests category "{1}" (stored under "{2}")'.format(
                    name, guess, category))
            dirty = True
            result['described'].append(name)

        if progress_cb is not None and not cancelled:
            try:
                progress_cb(total, total, '')
            except Exception:
                pass

        if dirty:
            try:
                with open(str(library_path), 'w') as f:
                    json.dump(library, f, indent=2)
                _log('Updated {0} ({1} described, {2} skipped, {3} failed, ~${4:.4f})'.format(
                    library_path, len(result['described']), len(result['skipped']),
                    len(result['failed']), result['cost']))
            except OSError as e:
                result['error'] = 'Could not save {0}: {1}'.format(library_path, e)
                _error(result['error'])
    except Exception as e:
        _error('catalog_library failed for show {0}: {1}'.format(show_name, e))
        _error(traceback.format_exc())
    return result

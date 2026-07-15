# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
AI Entity Cropper

Given a storyboard panel image and an entity (name + description), asks
the configured vision provider for the entity's normalized bounding box
as strict JSON ({'x','y','width','height'}, each 0-1 fractions of the
image), then crops that region out with PIL and saves it next to the
panel as <panel>_crop_<safe_entity>.png. The crop gets ~12% padding on
every side, is clamped to the image bounds, and is upscaled so its
smaller edge is at least 256px.

The provider call mirrors core/asset_cataloger.py exactly: one image via
provider.analyze_images() with a json_schema kwarg (Claude honors it via
structured outputs; other providers ignore the extra kwarg), parsed with
core.json_extractor.parse_llm_json.

crop_entity() NEVER raises: on any failure (no provider available, bad
or unparseable JSON, degenerate bounding box under 2% of the image area,
PIL missing, ...) it logs a warning and returns None so callers fall
back to the existing text-prompt generation mode.

This module is importable outside the Unreal Editor (the 'unreal' import
is guarded; PIL and the provider factory are imported lazily inside the
function). Standalone callers pass their own provider object exposing
the analyze_images(images, prompt, json_schema=..., max_tokens=...)
contract.
"""

import os
import re
from typing import Any, Dict, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (e.g. the standalone demo
    # scripts). Editor-dependent features are skipped.
    unreal = None


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


# Crop geometry constants
PADDING_FRACTION = 0.12        # ~12% padding on each side of the bbox
MIN_CROP_PIXELS = 256          # upscale crops whose smaller edge is under this
MIN_BBOX_AREA_FRACTION = 0.02  # bboxes under 2% of the image area are degenerate

# Structured-outputs schema (Claude honors it via the json_schema kwarg;
# other providers simply ignore the extra kwarg). Same pattern as
# core/asset_cataloger.py's CATALOG_JSON_SCHEMA.
BBOX_JSON_SCHEMA = {
    'type': 'object',
    'properties': {
        'x': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'y': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'width': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'height': {'type': 'number', 'minimum': 0, 'maximum': 1},
    },
    'required': ['x', 'y', 'width', 'height'],
    'additionalProperties': False,
}

_PROMPT_TEMPLATE = (
    'You are locating a single entity inside a storyboard panel image so it '
    'can be cropped out for 3D model generation.\n'
    'Find the entity named "{name}"{description_hint} in the image.\n\n'
    'Respond with ONLY a JSON object, no markdown fences, no extra text:\n'
    '{{\n'
    '  "x": <left edge of the tight bounding box around the entity, as a '
    '0-1 fraction of the image width>,\n'
    '  "y": <top edge, as a 0-1 fraction of the image height>,\n'
    '  "width": <box width, as a 0-1 fraction of the image width>,\n'
    '  "height": <box height, as a 0-1 fraction of the image height>\n'
    '}}'
)


def _create_provider():
    """Create the configured AI provider (factory 'auto'), mirroring
    core/asset_cataloger.py. None on failure (e.g. outside the editor)."""
    try:
        from core.ai_providers.provider_factory import AIProviderFactory
        return AIProviderFactory.create_provider('auto')
    except Exception as e:
        _log_warning("[EntityCropper] Could not create an AI provider: "
                     "{}".format(e))
        return None


def safe_entity_filename(entity_name):
    # type: (str) -> str
    """Filesystem-safe token for the entity name used in the crop
    filename ('Ghost Dog!' -> 'Ghost_Dog')."""
    token = re.sub(r'[^A-Za-z0-9]+', '_', str(entity_name)).strip('_')
    return token or 'entity'


def _parse_bbox(response_text):
    # type: (str) -> Optional[Dict[str, float]]
    """Parse and sanity-check the provider's bbox JSON. Returns a dict of
    floats ('x','y','width','height', clamped into the unit square) or
    None on any problem."""
    try:
        from core.json_extractor import parse_llm_json
        parsed = parse_llm_json(response_text)
    except Exception as e:
        _log_warning("[EntityCropper] Could not parse provider JSON: "
                     "{}".format(e))
        return None

    if not isinstance(parsed, dict):
        _log_warning("[EntityCropper] Provider returned non-object JSON")
        return None

    bbox = {}
    for key in ('x', 'y', 'width', 'height'):
        try:
            bbox[key] = float(parsed.get(key))
        except (TypeError, ValueError):
            _log_warning("[EntityCropper] Bounding box field '{}' missing "
                         "or non-numeric: {!r}".format(key, parsed.get(key)))
            return None

    # Clamp origin into the unit square, then clamp extent to what fits.
    bbox['x'] = min(max(bbox['x'], 0.0), 1.0)
    bbox['y'] = min(max(bbox['y'], 0.0), 1.0)
    bbox['width'] = min(max(bbox['width'], 0.0), 1.0 - bbox['x'])
    bbox['height'] = min(max(bbox['height'], 0.0), 1.0 - bbox['y'])

    if bbox['width'] <= 0.0 or bbox['height'] <= 0.0:
        _log_warning("[EntityCropper] Degenerate bounding box (zero "
                     "extent): {}".format(bbox))
        return None

    area = bbox['width'] * bbox['height']
    if area < MIN_BBOX_AREA_FRACTION:
        _log_warning("[EntityCropper] Degenerate bounding box ({:.1%} of "
                     "image area, minimum {:.0%}): {}".format(
                         area, MIN_BBOX_AREA_FRACTION, bbox))
        return None

    return bbox


def crop_entity(panel_image_path, entity_name, entity_description=None,
                provider=None):
    # type: (str, str, Optional[str], Optional[Any]) -> Optional[str]
    """
    Crop a named entity out of a storyboard panel image via the vision
    provider's bounding box, for image-to-3D generation.

    COST: exactly one small image call to the configured provider.

    Args:
        panel_image_path: Path of the storyboard panel image (PNG/JPG).
        entity_name: Name of the entity to locate (e.g. 'Ghost').
        entity_description: Optional description to help the model find
            the right entity.
        provider: An already-created vision provider to reuse (must expose
            the analyze_images(images, prompt, json_schema=..., ...)
            contract). Auto-created via AIProviderFactory
            .create_provider('auto') when None.

    Returns:
        Absolute path of the saved crop PNG
        (<panel>_crop_<safe_entity>.png next to the panel), or None on
        ANY failure. Never raises; callers fall back to text mode on None.
    """
    try:
        if not panel_image_path or not os.path.isfile(str(panel_image_path)):
            _log_warning("[EntityCropper] Panel image not found: "
                         "{}".format(panel_image_path))
            return None
        panel_image_path = str(panel_image_path)

        if not entity_name or not str(entity_name).strip():
            _log_warning("[EntityCropper] No entity name given")
            return None
        entity_name = str(entity_name).strip()

        if provider is None:
            provider = _create_provider()
        if provider is None:
            _log_warning("[EntityCropper] No vision provider available; "
                         "cannot crop '{}'".format(entity_name))
            return None

        description_hint = ''
        if entity_description and str(entity_description).strip():
            description_hint = ' (described as: {})'.format(
                str(entity_description).strip()[:300])
        prompt = _PROMPT_TEMPLATE.format(
            name=entity_name, description_hint=description_hint)

        result = provider.analyze_images(
            [panel_image_path], prompt,
            json_schema=BBOX_JSON_SCHEMA,
            max_tokens=512,
        )
        if not isinstance(result, dict) or not result.get('success'):
            reason = (result.get('error') if isinstance(result, dict)
                      else 'no result')
            _log_warning("[EntityCropper] Provider call failed for '{}': "
                         "{}".format(entity_name, reason))
            return None

        bbox = _parse_bbox(result.get('response') or '')
        if bbox is None:
            return None

        # PIL imported inside the function so the module stays importable
        # where Pillow is absent; failure just falls back to text mode.
        try:
            from PIL import Image
        except ImportError as e:
            _log_warning("[EntityCropper] PIL (Pillow) unavailable: "
                         "{}".format(e))
            return None

        with Image.open(panel_image_path) as image:
            width, height = image.size
            if width < 2 or height < 2:
                _log_warning("[EntityCropper] Panel image too small: "
                             "{}x{}".format(width, height))
                return None

            # ~12% padding on each side of the bbox, clamped to the image.
            pad_x = bbox['width'] * PADDING_FRACTION
            pad_y = bbox['height'] * PADDING_FRACTION
            left = int(round((bbox['x'] - pad_x) * width))
            top = int(round((bbox['y'] - pad_y) * height))
            right = int(round((bbox['x'] + bbox['width'] + pad_x) * width))
            bottom = int(round((bbox['y'] + bbox['height'] + pad_y) * height))

            left = max(0, min(left, width - 1))
            top = max(0, min(top, height - 1))
            right = max(left + 1, min(right, width))
            bottom = max(top + 1, min(bottom, height))

            crop = image.crop((left, top, right, bottom))

            # Upscale small crops so 3D providers get enough pixels.
            crop_w, crop_h = crop.size
            smaller = min(crop_w, crop_h)
            if smaller < MIN_CROP_PIXELS:
                scale = float(MIN_CROP_PIXELS) / float(smaller)
                new_size = (max(MIN_CROP_PIXELS, int(round(crop_w * scale))),
                            max(MIN_CROP_PIXELS, int(round(crop_h * scale))))
                resample = getattr(Image, 'LANCZOS', Image.BICUBIC)
                crop = crop.resize(new_size, resample)

            panel_dir = os.path.dirname(os.path.abspath(panel_image_path))
            panel_stem = os.path.splitext(
                os.path.basename(panel_image_path))[0]
            crop_path = os.path.join(
                panel_dir, '{}_crop_{}.png'.format(
                    panel_stem, safe_entity_filename(entity_name)))
            crop.save(crop_path, 'PNG')

        _log("[EntityCropper] Cropped '{}' from {} -> {} ({}x{} px, bbox "
             "{})".format(entity_name, os.path.basename(panel_image_path),
                          crop_path, crop.size[0], crop.size[1], bbox))
        return crop_path
    except Exception as e:
        _log_warning("[EntityCropper] crop_entity failed for '{}': "
                     "{}".format(entity_name, e))
        return None

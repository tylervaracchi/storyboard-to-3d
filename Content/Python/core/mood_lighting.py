# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Mood Lighting Module

Maps a free-text mood (from storyboard panel analysis) onto level lighting:
a DirectionalLight (sun), a SkyLight, and optionally an
ExponentialHeightFog. Mood text is fuzzy-resolved against preset names and
a synonyms map using difflib, mirroring the AssetMatcher pattern.

Feature is opt-in: SceneBuilder only calls apply_mood() when the
'scene.apply_mood_lighting' setting is truthy (default off).

apply_mood() never raises; every failure path is logged and reported in the
returned dict. Anything this module spawns is tagged 'StoryboardGenerated'
(so clear_build_area() removes it on the next build) plus
'StoryboardMoodLighting'.
"""

import re
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

try:
    import unreal
except ImportError:
    # Allow import outside the Unreal Editor (e.g. unit tests of the
    # mood-resolution logic). Editor-dependent features are skipped.
    unreal = None


FUZZY_CUTOFF = 0.6

# Each preset: sun rotation (pitch/yaw), directional light intensity in lux
# (UE default-sky scale, where the template level sun is ~10 lux), light
# color (RGB 0-1), sky light intensity scale, and optional fog settings.
MOOD_PRESETS = {
    'day': {
        'sun_pitch': -55.0, 'sun_yaw': 30.0, 'intensity': 10.0,
        'color': (1.0, 0.98, 0.92), 'sky_intensity_scale': 1.0, 'fog': None,
    },
    'night': {
        'sun_pitch': -35.0, 'sun_yaw': -60.0, 'intensity': 3.0,
        'color': (0.55, 0.65, 1.0), 'sky_intensity_scale': 0.5,
        'fog': {'color': (0.03, 0.05, 0.10), 'density': 0.015},
    },
    'golden_hour': {
        'sun_pitch': -8.0, 'sun_yaw': 60.0, 'intensity': 5.0,
        'color': (1.0, 0.65, 0.35), 'sky_intensity_scale': 0.6,
        'fog': {'color': (0.90, 0.60, 0.35), 'density': 0.02},
    },
    'overcast': {
        'sun_pitch': -50.0, 'sun_yaw': 0.0, 'intensity': 3.0,
        'color': (0.85, 0.88, 0.95), 'sky_intensity_scale': 1.4,
        'fog': {'color': (0.75, 0.78, 0.82), 'density': 0.04},
    },
    'noir': {
        'sun_pitch': -25.0, 'sun_yaw': 110.0, 'intensity': 4.0,
        'color': (0.90, 0.90, 1.0), 'sky_intensity_scale': 0.08,
        'fog': {'color': (0.02, 0.02, 0.03), 'density': 0.05},
    },
    'tense': {
        'sun_pitch': -20.0, 'sun_yaw': 140.0, 'intensity': 2.5,
        'color': (0.80, 0.75, 0.90), 'sky_intensity_scale': 0.2,
        'fog': {'color': (0.08, 0.06, 0.12), 'density': 0.025},
    },
    'warm': {
        'sun_pitch': -35.0, 'sun_yaw': 45.0, 'intensity': 6.0,
        'color': (1.0, 0.80, 0.55), 'sky_intensity_scale': 0.7, 'fog': None,
    },
    'cold': {
        'sun_pitch': -45.0, 'sun_yaw': -30.0, 'intensity': 6.0,
        'color': (0.65, 0.78, 1.0), 'sky_intensity_scale': 0.9,
        'fog': {'color': (0.60, 0.70, 0.85), 'density': 0.02},
    },
    'mysterious': {
        'sun_pitch': -15.0, 'sun_yaw': -120.0, 'intensity': 1.5,
        'color': (0.50, 0.60, 0.85), 'sky_intensity_scale': 0.25,
        'fog': {'color': (0.15, 0.20, 0.30), 'density': 0.03},
    },
    'cheerful': {
        'sun_pitch': -60.0, 'sun_yaw': 20.0, 'intensity': 12.0,
        'color': (1.0, 0.97, 0.85), 'sky_intensity_scale': 1.2, 'fog': None,
    },
}

# Free-text synonyms observed in analyzer output ('dark', 'bright',
# 'dramatic', time-of-day words) mapped onto preset names.
MOOD_SYNONYMS = {
    'dark': 'night', 'evening': 'night', 'midnight': 'night',
    'nighttime': 'night', 'moonlit': 'night', 'moonlight': 'night',
    'sunset': 'golden_hour', 'dusk': 'golden_hour', 'sunrise': 'golden_hour',
    'dawn': 'golden_hour', 'golden': 'golden_hour',
    'scary': 'tense', 'ominous': 'tense', 'dramatic': 'tense',
    'suspense': 'tense', 'suspenseful': 'tense', 'threatening': 'tense',
    'horror': 'tense', 'danger': 'tense', 'dangerous': 'tense',
    'cloudy': 'overcast', 'gray': 'overcast', 'grey': 'overcast',
    'gloomy': 'overcast', 'rainy': 'overcast', 'sad': 'overcast',
    'melancholy': 'overcast', 'somber': 'overcast',
    'happy': 'cheerful', 'bright': 'cheerful', 'joyful': 'cheerful',
    'upbeat': 'cheerful', 'playful': 'cheerful',
    'sunny': 'day', 'daytime': 'day', 'noon': 'day', 'neutral': 'day',
    'morning': 'day', 'afternoon': 'day', 'calm': 'day', 'clear': 'day',
    'cozy': 'warm', 'romantic': 'warm', 'intimate': 'warm', 'sepia': 'warm',
    'chilly': 'cold', 'icy': 'cold', 'winter': 'cold', 'frozen': 'cold',
    'clinical': 'cold', 'sterile': 'cold',
    'mystery': 'mysterious', 'eerie': 'mysterious', 'foggy': 'mysterious',
    'spooky': 'mysterious', 'haunting': 'mysterious', 'misty': 'mysterious',
    'moody': 'noir', 'shadowy': 'noir', 'crime': 'noir',
    'detective': 'noir', 'monochrome': 'noir',
}


def _log(message):
    """Log info via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print("[MoodLighting] {0}".format(message))


def _log_warning(message):
    """Log a warning via unreal when available, stdout otherwise."""
    if unreal is not None and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("[MoodLighting] WARNING: {0}".format(message))


def resolve_mood(mood_text: str) -> Optional[str]:
    """
    Fuzzy-resolve free mood text to a MOOD_PRESETS key.

    Resolution order: exact preset name, exact synonym, per-token lookup,
    then difflib close match (cutoff 0.6) against presets and synonyms.

    Args:
        mood_text: Free-form mood text from panel analysis.

    Returns:
        A MOOD_PRESETS key, or None when nothing resolves.
    """
    if not mood_text or not isinstance(mood_text, str):
        return None

    text = mood_text.strip().lower()
    if not text:
        return None
    normalized = re.sub(r'[^a-z0-9]+', '_', text).strip('_')

    if normalized in MOOD_PRESETS:
        return normalized
    if normalized in MOOD_SYNONYMS:
        return MOOD_SYNONYMS[normalized]

    tokens = [t for t in re.split(r'[^a-z0-9]+', text) if t]
    for token in tokens:
        if token in MOOD_PRESETS:
            return token
        if token in MOOD_SYNONYMS:
            return MOOD_SYNONYMS[token]

    candidates = list(MOOD_PRESETS.keys()) + list(MOOD_SYNONYMS.keys())
    for query in [normalized] + tokens:
        close = get_close_matches(query, candidates, n=1, cutoff=FUZZY_CUTOFF)
        if close:
            name = close[0]
            return name if name in MOOD_PRESETS else MOOD_SYNONYMS[name]

    return None


def _get_actor_subsystem():
    """Get the EditorActorSubsystem, or None with a logged reason."""
    if unreal is None:
        return None
    if hasattr(unreal, 'get_editor_subsystem') and hasattr(unreal, 'EditorActorSubsystem'):
        try:
            return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        except Exception as e:
            _log_warning("MoodLighting: EditorActorSubsystem unavailable: {0}".format(e))
    return None


def _get_all_level_actors() -> List[Any]:
    """List level actors via the subsystem, falling back to EditorLevelLibrary."""
    subsystem = _get_actor_subsystem()
    if subsystem is not None and hasattr(subsystem, 'get_all_level_actors'):
        try:
            return list(subsystem.get_all_level_actors())
        except Exception as e:
            _log_warning("MoodLighting: get_all_level_actors failed: {0}".format(e))
    if unreal is not None and hasattr(unreal, 'EditorLevelLibrary'):
        try:
            _log_warning("MoodLighting: falling back to EditorLevelLibrary for actor listing")
            return list(unreal.EditorLevelLibrary.get_all_level_actors())
        except Exception as e:
            _log_warning("MoodLighting: EditorLevelLibrary listing failed: {0}".format(e))
    return []


def _find_actor_of_class(actors: List[Any], class_name: str) -> Optional[Any]:
    """Find the first level actor of the named unreal class (hasattr-guarded)."""
    actor_class = getattr(unreal, class_name, None) if unreal is not None else None
    if actor_class is None:
        _log_warning("MoodLighting: unreal.{0} unavailable in this engine version".format(class_name))
        return None
    for actor in actors:
        try:
            if actor is not None and isinstance(actor, actor_class):
                return actor
        except Exception:
            continue
    return None


def _tag_spawned_actor(actor: Any) -> None:
    """Tag a spawned actor so clear_build_area() picks it up next build."""
    try:
        if hasattr(actor, 'tags'):
            tags = list(actor.tags)
            for tag in ('StoryboardGenerated', 'StoryboardMoodLighting'):
                if tag not in tags:
                    tags.append(tag)
            actor.tags = tags
    except Exception as e:
        _log_warning("MoodLighting: could not tag spawned actor: {0}".format(e))


def _spawn_actor_of_class(class_name: str, spawned_names: List[str]) -> Optional[Any]:
    """Spawn a light/fog actor by class name, tag it, and record the spawn."""
    actor_class = getattr(unreal, class_name, None) if unreal is not None else None
    if actor_class is None:
        _log_warning("MoodLighting: cannot spawn unknown class '{0}'".format(class_name))
        return None

    location = unreal.Vector(0.0, 0.0, 400.0)
    rotation = unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0)
    actor = None
    try:
        subsystem = _get_actor_subsystem()
        if subsystem is not None and hasattr(subsystem, 'spawn_actor_from_class'):
            actor = subsystem.spawn_actor_from_class(actor_class, location, rotation)
        elif hasattr(unreal, 'EditorLevelLibrary'):
            _log_warning("MoodLighting: spawning '{0}' via EditorLevelLibrary fallback".format(class_name))
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(actor_class, location, rotation)
    except Exception as e:
        _log_warning("MoodLighting: failed to spawn {0}: {1}".format(class_name, e))
        return None

    if actor is not None:
        _tag_spawned_actor(actor)
        spawned_names.append(class_name)
        _log("[MoodLighting] Spawned missing {0}".format(class_name))
    return actor


def _get_component(actor: Any, component_class_name: str) -> Optional[Any]:
    """Get a component by class (hasattr-guarded), with attribute fallbacks."""
    component_class = getattr(unreal, component_class_name, None) if unreal is not None else None
    if component_class is not None and hasattr(actor, 'get_component_by_class'):
        try:
            component = actor.get_component_by_class(component_class)
            if component is not None:
                return component
        except Exception as e:
            _log_warning("MoodLighting: get_component_by_class failed: {0}".format(e))
    # Older reflected attribute fallbacks (ALight.light_component, fog 'component')
    for attr in ('light_component', 'component'):
        try:
            if hasattr(actor, attr):
                component = getattr(actor, attr)
                if component is not None:
                    return component
        except Exception:
            continue
    return None


def _set_component_value(component: Any, setter_name: str, property_name: str, value: Any) -> bool:
    """Set a value via the setter when present, else set_editor_property."""
    try:
        if setter_name and hasattr(component, setter_name):
            getattr(component, setter_name)(value)
            return True
    except Exception as e:
        _log_warning("MoodLighting: {0} failed ({1}); trying set_editor_property".format(setter_name, e))
    try:
        if hasattr(component, 'set_editor_property'):
            component.set_editor_property(property_name, value)
            return True
    except Exception as e:
        _log_warning("MoodLighting: could not set '{0}': {1}".format(property_name, e))
    return False


def _set_actor_rotation(actor: Any, pitch: float, yaw: float) -> None:
    """Rotate an actor, tolerating engine versions with/without teleport arg."""
    rotation = unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)
    try:
        actor.set_actor_rotation(rotation, False)
    except TypeError:
        try:
            actor.set_actor_rotation(rotation)
        except Exception as e:
            _log_warning("MoodLighting: could not rotate actor: {0}".format(e))
    except Exception as e:
        _log_warning("MoodLighting: could not rotate actor: {0}".format(e))


def _apply_directional_light(actor: Any, preset: Dict[str, Any]) -> bool:
    """Point and tune the sun for the preset. Returns True when touched."""
    _set_actor_rotation(actor, preset['sun_pitch'], preset['sun_yaw'])
    component = _get_component(actor, 'DirectionalLightComponent')
    if component is None:
        _log_warning("MoodLighting: no DirectionalLightComponent found; rotation only")
        return True  # Rotation alone still counts as touched
    _set_component_value(component, 'set_intensity', 'intensity', float(preset['intensity']))
    r, g, b = preset['color']
    color = unreal.LinearColor(r=r, g=g, b=b, a=1.0)
    _set_component_value(component, 'set_light_color', 'light_color', color)
    return True


def _apply_sky_light(actor: Any, preset: Dict[str, Any]) -> bool:
    """Scale the sky light intensity for the preset. Returns True when touched."""
    component = _get_component(actor, 'SkyLightComponent')
    if component is None:
        _log_warning("MoodLighting: no SkyLightComponent found on sky light actor")
        return False
    touched = _set_component_value(component, 'set_intensity', 'intensity',
                                   float(preset['sky_intensity_scale']))
    try:
        if hasattr(component, 'recapture_sky'):
            component.recapture_sky()
    except Exception as e:
        _log_warning("MoodLighting: recapture_sky failed: {0}".format(e))
    return touched


def _apply_fog(actor: Any, fog: Dict[str, Any]) -> bool:
    """Apply fog color/density from the preset. Returns True when touched."""
    component = _get_component(actor, 'ExponentialHeightFogComponent')
    if component is None:
        _log_warning("MoodLighting: no ExponentialHeightFogComponent found")
        return False
    touched = _set_component_value(component, 'set_fog_density', 'fog_density',
                                   float(fog['density']))
    r, g, b = fog['color']
    color = unreal.LinearColor(r=r, g=g, b=b, a=1.0)
    # Property name changed across engine versions; try new then old.
    if not _set_component_value(component, '', 'fog_inscattering_luminance', color):
        _set_component_value(component, 'set_fog_inscattering_color',
                             'fog_inscattering_color', color)
    return touched


def apply_mood(mood_text: str) -> Dict[str, Any]:
    """
    Resolve a mood and apply its lighting preset to the current level.

    Finds (or spawns) a DirectionalLight and SkyLight and tunes them; fog is
    applied only when an ExponentialHeightFog exists or can be spawned.
    Spawned actors are tagged 'StoryboardGenerated' + 'StoryboardMoodLighting'.

    Args:
        mood_text: Free-form mood text (e.g. 'dark', 'sunset', 'scary').

    Returns:
        {'status': 'ok'|'error', 'preset': str or None,
         'actors_touched': int, 'spawned': [class names], 'errors': [str]}
        Never raises; failures land in 'errors' (and 'status' when fatal).
    """
    result = {'status': 'error', 'preset': None, 'actors_touched': 0,
              'spawned': [], 'errors': []}
    try:
        if unreal is None:
            result['errors'].append('unreal module unavailable (not running inside the editor)')
            return result

        preset_name = resolve_mood(mood_text)
        if preset_name is None:
            result['errors'].append("could not resolve mood '{0}' to a preset".format(mood_text))
            _log_warning("[MoodLighting] Unrecognized mood '{0}'; known presets: {1}".format(
                mood_text, ', '.join(sorted(MOOD_PRESETS.keys()))))
            return result

        result['preset'] = preset_name
        preset = MOOD_PRESETS[preset_name]
        actors = _get_all_level_actors()

        # Directional light (sun): find or spawn
        sun = _find_actor_of_class(actors, 'DirectionalLight')
        if sun is None:
            sun = _spawn_actor_of_class('DirectionalLight', result['spawned'])
        if sun is not None:
            if _apply_directional_light(sun, preset):
                result['actors_touched'] += 1
        else:
            result['errors'].append('no DirectionalLight found or spawned')

        # Sky light: find or spawn
        sky = _find_actor_of_class(actors, 'SkyLight')
        if sky is None:
            sky = _spawn_actor_of_class('SkyLight', result['spawned'])
        if sky is not None:
            if _apply_sky_light(sky, preset):
                result['actors_touched'] += 1
        else:
            result['errors'].append('no SkyLight found or spawned')

        # Fog: only when the preset wants it AND an actor exists or spawns
        fog_settings = preset.get('fog')
        if fog_settings:
            fog_actor = _find_actor_of_class(actors, 'ExponentialHeightFog')
            if fog_actor is None:
                fog_actor = _spawn_actor_of_class('ExponentialHeightFog', result['spawned'])
            if fog_actor is not None:
                if _apply_fog(fog_actor, fog_settings):
                    result['actors_touched'] += 1
            else:
                _log("[MoodLighting] No ExponentialHeightFog available; skipping fog for '{0}'".format(preset_name))

        result['status'] = 'ok' if result['actors_touched'] > 0 else 'error'
        if result['status'] == 'error' and not result['errors']:
            result['errors'].append('no lighting actors could be touched')
        _log("[MoodLighting] Preset '{0}' applied: {1} actor(s) touched, {2} spawned".format(
            preset_name, result['actors_touched'], len(result['spawned'])))
        return result

    except Exception as e:
        # apply_mood must never raise
        result['errors'].append(str(e))
        _log_warning("[MoodLighting] Unexpected failure: {0}".format(e))
        return result

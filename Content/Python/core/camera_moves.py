# Copyright (c) 2026 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Camera Moves for StoryboardTo3D

Maps storyboard shot types to subtle camera moves keyed onto a shot
sequence's camera binding:

    close  -> slow push-in (forward dolly, ~8 percent of the
              camera-to-subject distance, fallback 60 UE units)
    medium -> lateral drift (~40 UE units)
    wide   -> slow pan (~4 degrees yaw), falling back to a gentle
              lateral track when no rotation channel is identifiable
    other  -> no move (Auto/OTS/POV/unknown stay static)

Sequencer channel APIs are the most version-variant part of the UE
Python surface, so every unreal attribute access here is guarded and
apply_camera_move() never raises. Feature is opt-in via the
'sequence.camera_moves' setting (see core/sequence_generator.py).
"""

import math
from typing import Any, Dict, List, Optional, Tuple

# unreal is only available inside the editor. Guard it so this module
# can be imported (and move resolution unit-tested) outside UE.
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False

# Move tuning constants
PUSH_IN_FRACTION = 0.08          # close-up dolly: fraction of camera-to-subject distance
PUSH_IN_FALLBACK_UNITS = 60.0    # close-up dolly when no subject location is known
LATERAL_DRIFT_UNITS = 40.0       # medium-shot sideways drift
PAN_YAW_DEGREES = 4.0            # wide-shot slow pan


def _log(message):
    """Log info, falling back to print outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def _log_warning(message):
    """Log warning, falling back to print outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {}".format(message))


def resolve_move(shot_type) -> str:
    """
    Map a shot type (string or enum-like) to a move preset name.

    Returns one of 'push_in', 'lateral_drift', 'pan', 'none'.
    Matching is case-insensitive and substring based so 'Close-up',
    'close_up', 'ECU', 'extreme_close_up', 'medium_close' etc. all
    resolve. Check order matters: close before wide before medium so
    'medium_close' pushes in and 'medium_wide' pans.
    """
    raw = getattr(shot_type, 'value', shot_type)
    name = str(raw or '').strip().lower()
    if not name:
        return 'none'
    if 'close' in name or 'ecu' in name:
        return 'push_in'
    if 'wide' in name:
        return 'pan'
    if 'medium' in name:
        return 'lateral_drift'
    return 'none'


def _extract_vector(value) -> Optional[Tuple[float, float, float]]:
    """Return (x, y, z) floats from an unreal.Vector-like object, or None."""
    try:
        return (float(value.x), float(value.y), float(value.z))
    except Exception:
        return None


def _extract_transform(transform) -> Optional[Tuple[Tuple[float, float, float], float, float]]:
    """Return ((x, y, z), yaw, pitch) from an unreal.Transform-like object, or None."""
    try:
        loc = _extract_vector(getattr(transform, 'translation', None))
        rotation = getattr(transform, 'rotation', None)
        rotator = None
        if rotation is not None and hasattr(rotation, 'rotator'):
            rotator = rotation.rotator()  # Quat -> Rotator
        elif rotation is not None and hasattr(rotation, 'yaw'):
            rotator = rotation  # already a Rotator
        if loc is None or rotator is None:
            return None
        return loc, float(rotator.yaw), float(rotator.pitch)
    except Exception:
        return None


def _resolve_current_transform(camera_binding, current_transform, notes: List[str]):
    """
    Determine the camera's transform at bind time. Order of preference:
    an explicit current_transform (actor or unreal.Transform), then the
    binding's spawnable object template. Returns ((x, y, z), yaw, pitch)
    or None; keying garbage relative to an unknown transform is worse
    than doing nothing.
    """
    # 1. Explicit transform or actor passed by the caller
    if current_transform is not None:
        source = current_transform
        if hasattr(source, 'get_actor_transform'):
            try:
                source = source.get_actor_transform()
            except Exception as e:
                notes.append("get_actor_transform failed: {}".format(e))
                source = None
        extracted = _extract_transform(source) if source is not None else None
        if extracted is not None:
            return extracted
        notes.append("could not read explicit current_transform")

    # 2. Spawnable object template on the binding
    if camera_binding is not None and hasattr(camera_binding, 'get_object_template'):
        try:
            template = camera_binding.get_object_template()
        except Exception as e:
            notes.append("get_object_template failed: {}".format(e))
            template = None
        if template is not None:
            # Templates are not spawned actors; read the root component's
            # relative transform instead of actor-level getters.
            try:
                root = template.get_editor_property('root_component')
                loc = _extract_vector(root.get_editor_property('relative_location'))
                rot = root.get_editor_property('relative_rotation')
                if loc is not None and hasattr(rot, 'yaw'):
                    return loc, float(rot.yaw), float(rot.pitch)
            except Exception as e:
                notes.append("template root component unreadable: {}".format(e))

    notes.append("camera transform at bind time could not be determined")
    return None


def _forward_vector(yaw: float, pitch: float) -> Tuple[float, float, float]:
    """UE-convention forward vector from yaw/pitch degrees (Z-up, pitch positive up)."""
    yaw_r = math.radians(yaw)
    pitch_r = math.radians(pitch)
    return (math.cos(yaw_r) * math.cos(pitch_r),
            math.sin(yaw_r) * math.cos(pitch_r),
            math.sin(pitch_r))


def _right_vector(yaw: float) -> Tuple[float, float, float]:
    """UE-convention right vector from yaw degrees (ignores pitch/roll)."""
    yaw_r = math.radians(yaw)
    return (-math.sin(yaw_r), math.cos(yaw_r), 0.0)


def _find_or_add_transform_track(camera_binding, notes: List[str]):
    """Find an existing 3D transform track on the binding, or add one."""
    track_class = getattr(unreal, 'MovieScene3DTransformTrack', None)
    if track_class is None:
        notes.append("unreal.MovieScene3DTransformTrack unavailable")
        return None

    if hasattr(camera_binding, 'find_tracks_by_type'):
        try:
            existing = camera_binding.find_tracks_by_type(track_class)
            if existing:
                return existing[0]
        except Exception as e:
            notes.append("find_tracks_by_type failed: {}".format(e))
    elif hasattr(camera_binding, 'get_tracks'):
        try:
            for track in camera_binding.get_tracks():
                if isinstance(track, track_class):
                    return track
        except Exception as e:
            notes.append("get_tracks scan failed: {}".format(e))

    if hasattr(camera_binding, 'add_track'):
        try:
            return camera_binding.add_track(track_class)
        except Exception as e:
            notes.append("add_track failed: {}".format(e))
    else:
        notes.append("binding has no add_track method")
    return None


def _get_or_add_section(track, start_frame: int, end_frame: int, notes: List[str]):
    """Get the track's first section or add one, spanning start to end frames."""
    section = None
    if hasattr(track, 'get_sections'):
        try:
            sections = track.get_sections()
            if sections:
                section = sections[0]
        except Exception as e:
            notes.append("get_sections failed: {}".format(e))
    if section is None:
        if not hasattr(track, 'add_section'):
            notes.append("track has no add_section method")
            return None
        try:
            section = track.add_section()
        except Exception as e:
            notes.append("add_section failed: {}".format(e))
            return None

    # Span the section across the shot; set_range is the older API.
    try:
        if hasattr(section, 'set_start_frame_bounded'):
            section.set_start_frame_bounded(True)
            section.set_start_frame(int(start_frame))
            section.set_end_frame_bounded(True)
            section.set_end_frame(int(end_frame))
        elif hasattr(section, 'set_range'):
            section.set_range(int(start_frame), int(end_frame))
        else:
            notes.append("section range API unavailable; leaving default range")
    except Exception as e:
        notes.append("setting section range failed: {}".format(e))
    return section


def _identify_channels(section, notes: List[str]) -> Dict[str, Any]:
    """
    Map channels to keys like 'location.x' / 'rotation.z' by name.
    Channel names vary slightly across UE versions, so match
    case-insensitively on substrings. Unidentifiable channels are
    skipped with a note.
    """
    channels = []
    try:
        if hasattr(section, 'get_all_channels'):
            channels = section.get_all_channels()
        elif hasattr(section, 'get_channels'):
            channels = section.get_channels()
        else:
            notes.append("section has no channel accessor")
    except Exception as e:
        notes.append("reading channels failed: {}".format(e))

    identified = {}
    for channel in channels or []:
        try:
            name = str(channel.get_name()).strip().lower() if hasattr(channel, 'get_name') else ''
        except Exception:
            name = ''
        if not name:
            notes.append("skipped a channel with no readable name")
            continue
        if 'location' in name or 'translation' in name:
            group = 'location'
        elif 'rotation' in name:
            group = 'rotation'
        else:
            continue  # scale and anything else: not needed
        axis = name[-1] if name[-1] in ('x', 'y', 'z') else None
        if axis is None:
            notes.append("skipped unidentifiable channel '{}'".format(name))
            continue
        identified.setdefault('{}.{}'.format(group, axis), channel)
    return identified


def _add_key(channel, frame: int, value: float, notes: List[str]) -> bool:
    """Add one key to a float channel. Returns True on success."""
    frame_class = getattr(unreal, 'FrameNumber', None)
    if frame_class is None or not hasattr(channel, 'add_key'):
        notes.append("channel keying API unavailable")
        return False
    try:
        channel.add_key(frame_class(int(frame)), float(value))
        return True
    except Exception as e:
        notes.append("add_key failed at frame {}: {}".format(frame, e))
        return False


def _key_channels(identified, targets, start_frame, end_frame, notes) -> int:
    """
    Write start/end keys. targets maps channel keys ('location.x', ...)
    to (start_value, end_value). Returns the number of channels fully keyed.
    """
    keyed = 0
    for channel_key, (start_value, end_value) in targets.items():
        channel = identified.get(channel_key)
        if channel is None:
            notes.append("channel '{}' not identifiable; skipped".format(channel_key))
            continue
        ok_start = _add_key(channel, start_frame, start_value, notes)
        ok_end = _add_key(channel, end_frame, end_value, notes)
        if ok_start and ok_end:
            keyed += 1
    return keyed


def apply_camera_move(sequence, camera_binding, shot_type, start_frame, end_frame,
                      subject_location=None, current_transform=None) -> Dict[str, Any]:
    """
    Key a subtle shot-type-appropriate camera move onto camera_binding.

    Args:
        sequence: the LevelSequence (unused directly; kept for API clarity)
        camera_binding: binding proxy returned by add_possessable/add_spawnable
        shot_type: shot type string or enum ('close-up', 'medium', 'wide', ...)
        start_frame / end_frame: display-rate frame range to key across
        subject_location: optional unreal.Vector of the shot's subject,
            used to scale the close-up push-in distance
        current_transform: optional camera actor or unreal.Transform giving
            the camera's transform at bind time (required for possessables,
            whose templates are not reachable from the binding)

    Returns:
        {'status': 'applied'|'skipped'|'error', 'move': str, 'notes': [str, ...]}
        Never raises.
    """
    result = {'status': 'skipped', 'move': 'none', 'notes': []}
    notes = result['notes']
    try:
        if not UNREAL_AVAILABLE:
            notes.append("unreal module unavailable; no move applied")
            return result
        if camera_binding is None:
            notes.append("no camera binding provided")
            return result

        move = resolve_move(shot_type)
        result['move'] = move
        if move == 'none':
            notes.append("no move preset for shot type '{}'".format(shot_type))
            return result

        transform = _resolve_current_transform(camera_binding, current_transform, notes)
        if transform is None:
            return result  # notes already explain why
        (loc_x, loc_y, loc_z), yaw, pitch = transform

        track = _find_or_add_transform_track(camera_binding, notes)
        if track is None:
            return result
        section = _get_or_add_section(track, start_frame, end_frame, notes)
        if section is None:
            return result
        identified = _identify_channels(section, notes)
        if not identified:
            notes.append("no usable transform channels found")
            return result

        targets = {}
        if move == 'pan':
            if 'rotation.z' in identified:
                targets['rotation.z'] = (yaw, yaw + PAN_YAW_DEGREES)
            else:
                # Wide-shot fallback: gentle lateral track instead of a pan
                notes.append("rotation.z channel not identifiable; "
                             "falling back to gentle lateral track")
                move = 'lateral_drift'
                result['move'] = 'pan_fallback_lateral'

        if move == 'push_in':
            distance = PUSH_IN_FALLBACK_UNITS
            subject = _extract_vector(subject_location) if subject_location is not None else None
            if subject is not None:
                to_subject = math.sqrt((subject[0] - loc_x) ** 2 +
                                       (subject[1] - loc_y) ** 2 +
                                       (subject[2] - loc_z) ** 2)
                if to_subject > 1.0:
                    distance = PUSH_IN_FRACTION * to_subject
                else:
                    notes.append("subject too close; using fallback push-in distance")
            else:
                notes.append("no subject location; using fallback push-in distance")
            fwd = _forward_vector(yaw, pitch)
            targets['location.x'] = (loc_x, loc_x + fwd[0] * distance)
            targets['location.y'] = (loc_y, loc_y + fwd[1] * distance)
            targets['location.z'] = (loc_z, loc_z + fwd[2] * distance)
        elif move == 'lateral_drift':
            right = _right_vector(yaw)
            targets['location.x'] = (loc_x, loc_x + right[0] * LATERAL_DRIFT_UNITS)
            targets['location.y'] = (loc_y, loc_y + right[1] * LATERAL_DRIFT_UNITS)
            targets['location.z'] = (loc_z, loc_z)

        keyed = _key_channels(identified, targets, start_frame, end_frame, notes)
        if keyed > 0:
            result['status'] = 'applied'
            notes.append("keyed {} channel(s) from frame {} to {}".format(
                keyed, start_frame, end_frame))
        else:
            notes.append("no channels were keyed")

    except Exception as e:
        result['status'] = 'error'
        notes.append("unexpected failure: {}".format(e))
        _log_warning("[CameraMoves] Unexpected failure: {}".format(e))
    return result

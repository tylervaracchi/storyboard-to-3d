# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Engine version detection and API compatibility helpers.

Supported range: Unreal Engine 5.4 - 5.8. Importable outside UE
(the unreal import is guarded) so unit tests can run anywhere.
"""

import re

try:
    import unreal
except ImportError:
    unreal = None


def _parse_engine_version():
    """Return (major, minor, patch) ints, or (0, 0, 0) outside UE."""
    if unreal is None:
        return (0, 0, 0)
    try:
        raw = unreal.SystemLibrary.get_engine_version()
        # Example raw value: "5.6.1-38445549+++UE5+Release-5.6"
        match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", str(raw))
        if match:
            return (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3) or 0),
            )
    except Exception as exc:
        if hasattr(unreal, "log_warning"):
            unreal.log_warning(
                "engine_compat: could not parse engine version: {0}".format(exc)
            )
    return (0, 0, 0)


ENGINE_VERSION = _parse_engine_version()
ENGINE_MAJOR = ENGINE_VERSION[0]
ENGINE_MINOR = ENGINE_VERSION[1]

# Version gate booleans. All False outside UE or if parsing failed.
IS_UE_5_4_PLUS = ENGINE_VERSION >= (5, 4, 0)
IS_UE_5_5_PLUS = ENGINE_VERSION >= (5, 5, 0)
IS_UE_5_6_PLUS = ENGINE_VERSION >= (5, 6, 0)
IS_UE_5_7_PLUS = ENGINE_VERSION >= (5, 7, 0)
IS_UE_5_8_PLUS = ENGINE_VERSION >= (5, 8, 0)


def get_time_unit():
    """
    Return the sequencer time-unit enum class for this engine.

    UE 5.4+ prefers unreal.MovieSceneTimeUnit; unreal.SequenceTimeUnit
    is the deprecated older name (both exist through 5.8). Returns None
    outside UE or if neither enum is available, so callers must handle
    a None result by omitting the time_unit argument entirely.
    """
    if unreal is None:
        return None
    if hasattr(unreal, "MovieSceneTimeUnit"):
        return unreal.MovieSceneTimeUnit
    if hasattr(unreal, "SequenceTimeUnit"):
        return unreal.SequenceTimeUnit
    if hasattr(unreal, "log_warning"):
        unreal.log_warning(
            "engine_compat: no time-unit enum found; falling back to "
            "add_key calls without a time_unit argument"
        )
    return None

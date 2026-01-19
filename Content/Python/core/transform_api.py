# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PROPER TRANSFORM APPLICATION FOR SEQUENCER - ULTRA-ROBUST VERSION

Works across ALL UE 5.x versions by handling API differences.

API COMPATIBILITY:
- UE 5.0-5.3: Uses SequenceTimeUnit
- UE 5.4-5.6: Uses MovieSceneTimeUnit
- Fallback: Works without time_unit parameter
"""

import unreal


# Detect which TimeUnit enum is available
if hasattr(unreal, 'MovieSceneTimeUnit'):
    TIME_UNIT = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    TIME_UNIT_NAME = "MovieSceneTimeUnit"
elif hasattr(unreal, 'SequenceTimeUnit'):
    TIME_UNIT = unreal.SequenceTimeUnit.DISPLAY_RATE
    TIME_UNIT_NAME = "SequenceTimeUnit"
else:
    TIME_UNIT = None
    TIME_UNIT_NAME = "None (using fallback)"

unreal.log(f"Using time unit: {TIME_UNIT_NAME}")


def apply_transform_to_spawnable(sequence, spawnable_binding, location_delta, rotation_delta, frame_number=0):
    """
    Apply transform changes to a spawnable in Sequencer by adding keyframes.

    ULTRA-COMPATIBLE: Works across UE 5.0-5.6 by handling API differences.

    Args:
        sequence: The LevelSequence asset
        spawnable_binding: The MovieSceneBindingProxy for the spawnable
        location_delta: Dict with 'x', 'y', 'z' deltas in centimeters
        rotation_delta: Dict with 'pitch', 'yaw', 'roll' deltas in degrees
        frame_number: Which frame to set the keyframe (default: 0)

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        # Step 1: Find the transform track
        transform_track = None
        for track in spawnable_binding.get_tracks():
            if isinstance(track, unreal.MovieScene3DTransformTrack):
                transform_track = track
                break

        if not transform_track:
            unreal.log_warning(f"No transform track found for spawnable")
            return False

        # Step 2: Get the transform section
        sections = transform_track.get_sections()
        if not sections:
            unreal.log_warning(f"No sections in transform track")
            return False

        section = sections[0]

        # Step 3: Get ALL channels from the section
        channels = _get_channels_safe(section)

        if not channels:
            unreal.log_error("Could not get channels from section!")
            return False

        if len(channels) < 9:
            unreal.log_error(f"Expected 9 channels, got {len(channels)}")
            return False

        # Step 4: Get existing values
        frame_time = unreal.FrameNumber(frame_number)

        # Channels: LocX, LocY, LocZ, RotRoll, RotPitch, RotYaw, ScaleX, ScaleY, ScaleZ
        location_x_channel = channels[0]
        location_y_channel = channels[1]
        location_z_channel = channels[2]
        rotation_roll_channel = channels[3]
        rotation_pitch_channel = channels[4]
        rotation_yaw_channel = channels[5]

        # Get current values
        current_loc_x = _get_channel_value_at_frame(location_x_channel, frame_number)
        current_loc_y = _get_channel_value_at_frame(location_y_channel, frame_number)
        current_loc_z = _get_channel_value_at_frame(location_z_channel, frame_number)
        current_roll = _get_channel_value_at_frame(rotation_roll_channel, frame_number)
        current_pitch = _get_channel_value_at_frame(rotation_pitch_channel, frame_number)
        current_yaw = _get_channel_value_at_frame(rotation_yaw_channel, frame_number)

        # Step 5: Apply deltas
        new_loc_x = current_loc_x + location_delta.get('x', 0)
        new_loc_y = current_loc_y + location_delta.get('y', 0)
        new_loc_z = current_loc_z + location_delta.get('z', 0)
        new_roll = current_roll + rotation_delta.get('roll', 0)
        new_pitch = current_pitch + rotation_delta.get('pitch', 0)
        new_yaw = current_yaw + rotation_delta.get('yaw', 0)

        # Step 6: Add keyframes
        _add_keyframe_safe(location_x_channel, frame_time, new_loc_x)
        _add_keyframe_safe(location_y_channel, frame_time, new_loc_y)
        _add_keyframe_safe(location_z_channel, frame_time, new_loc_z)
        _add_keyframe_safe(rotation_roll_channel, frame_time, new_roll)
        _add_keyframe_safe(rotation_pitch_channel, frame_time, new_pitch)
        _add_keyframe_safe(rotation_yaw_channel, frame_time, new_yaw)

        # Step 7: Refresh sequencer
        unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()

        unreal.log(f"Transform applied: Loc({new_loc_x:.1f}, {new_loc_y:.1f}, {new_loc_z:.1f}) Rot({new_pitch:.1f}, {new_yaw:.1f}, {new_roll:.1f})")

        return True

    except Exception as e:
        unreal.log_error(f"Failed to apply transform: {e}")
        import traceback
        traceback.print_exc()
        return False


def _get_channels_safe(section):
    """Get channels with multiple fallback approaches."""

    # Approach 1: Direct method
    try:
        if hasattr(section, 'get_all_channels'):
            channels = section.get_all_channels()
            if channels and len(channels) > 0:
                unreal.log(f"Got {len(channels)} channels via section.get_all_channels()")
                return channels
    except Exception as e:
        unreal.log_warning(f"Approach 1 failed: {e}")

    # Approach 2: MovieSceneSectionExtensions
    try:
        if hasattr(unreal, 'MovieSceneSectionExtensions'):
            channels = unreal.MovieSceneSectionExtensions.get_all_channels(section)
            if channels and len(channels) > 0:
                unreal.log(f"Got {len(channels)} channels via MovieSceneSectionExtensions")
                return channels
    except Exception as e:
        unreal.log_warning(f"Approach 2 failed: {e}")

    # Approach 3: get_channels_by_type
    try:
        if hasattr(section, 'get_channels_by_type'):
            channels = section.get_channels_by_type(unreal.MovieSceneScriptingDoubleChannel)
            if channels and len(channels) > 0:
                unreal.log(f"Got {len(channels)} channels via get_channels_by_type")
                return channels
    except Exception as e:
        unreal.log_warning(f"Approach 3 failed: {e}")

    unreal.log_error("All approaches to get channels failed!")
    return None


def _add_keyframe_safe(channel, frame_time, value):
    """
    Add keyframe with compatibility across UE versions.
    Tries multiple parameter combinations.
    """

    # Approach 1: With time_unit parameter (if available)
    if TIME_UNIT is not None:
        try:
            channel.add_key(
                time=frame_time,
                new_value=value,
                sub_frame=0.0,
                time_unit=TIME_UNIT,
                interpolation=unreal.MovieSceneKeyInterpolation.AUTO
            )
            return
        except TypeError:
            # time_unit parameter might not be accepted
            pass
        except Exception as e:
            unreal.log_warning(f"add_key with time_unit failed: {e}")

    # Approach 2: Without time_unit but with interpolation
    try:
        channel.add_key(
            time=frame_time,
            new_value=value,
            sub_frame=0.0,
            interpolation=unreal.MovieSceneKeyInterpolation.AUTO
        )
        return
    except TypeError:
        pass
    except Exception as e:
        unreal.log_warning(f"add_key with interpolation failed: {e}")

    # Approach 3: Minimal parameters only
    try:
        channel.add_key(
            time=frame_time,
            new_value=value
        )
        return
    except Exception as e:
        unreal.log_error(f"All add_key approaches failed: {e}")
        raise


def _get_channel_value_at_frame(channel, frame_number):
    """Get current value of a channel at a frame."""

    try:
        keys = channel.get_keys()

        if not keys:
            try:
                if channel.has_default():
                    return channel.get_default()
            except:
                pass
            return 0.0

        # Find key at this frame
        for key in keys:
            try:
                key_time = key.get_time()
                if hasattr(key_time, 'frame_number'):
                    if key_time.frame_number.value == frame_number:
                        return key.get_value()
                elif hasattr(key_time, 'value'):
                    if key_time.value == frame_number:
                        return key.get_value()
            except:
                continue

        # No key at this frame, return first key's value
        return keys[0].get_value()

    except Exception as e:
        unreal.log_warning(f"Could not get channel value: {e}")
        return 0.0


def test_transform_api():
    """Test the transform API"""

    unreal.log("="*80)
    unreal.log("TESTING TRANSFORM API - ULTRA-ROBUST VERSION")
    unreal.log("="*80)

    try:
        sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()

        if not sequence:
            unreal.log_error("No sequence open!")
            return False

        unreal.log(f"Sequence: {sequence.get_name()}")

        spawnables = sequence.get_spawnables()
        if not spawnables:
            unreal.log_error("No spawnables!")
            return False

        spawnable = spawnables[0]
        name = str(spawnable.get_display_name())
        unreal.log(f"Testing with: {name}")

        # Apply test movement
        location_delta = {'x': 10, 'y': 0, 'z': 0}
        rotation_delta = {'pitch': 0, 'yaw': 5, 'roll': 0}

        unreal.log(f"\n Applying: +10cm X, +5deg Yaw")

        success = apply_transform_to_spawnable(
            sequence,
            spawnable,
            location_delta,
            rotation_delta,
            frame_number=0
        )

        if success:
            unreal.log("\n" + "="*80)
            unreal.log("TRANSFORM API TEST PASSED!")
            unreal.log("="*80)
            unreal.log("Check viewport - spawnable should have moved!")
            unreal.log("Check timeline - you should see keyframes!")
            return True
        else:
            unreal.log_error("\n Test failed!")
            return False

    except Exception as e:
        unreal.log_error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_transform_api()

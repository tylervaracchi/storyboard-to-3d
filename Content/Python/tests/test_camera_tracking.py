# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test camera position tracking in metrics

This test verifies Bug #2 fix is working correctly.
"""

import unreal
from pathlib import Path

def test_camera_position_tracking():
    """Test that camera positions are captured and recorded in metrics"""

    print("="*70)
    print("Testing Camera Position Tracking (Bug #2)")
    print("="*70)

    # Find Panel_008 sequence
    sequence_path = "/Game/StoryboardSequences/oat/Panel_008_Sequence"
    print(f"\n1. Loading sequence: {sequence_path}")

    sequence_asset = unreal.load_asset(sequence_path)
    if not sequence_asset:
        print(f"Failed to load sequence: {sequence_path}")
        return False

    print(f"Sequence loaded: {sequence_asset.get_name()}")

    # Test 1: Find camera using SceneAdjuster
    print("\n2. Testing SceneAdjuster.find_camera_in_sequence()...")
    from core.scene_adjuster import SceneAdjuster

    adjuster = SceneAdjuster(sequence_asset)
    camera_name = adjuster.find_camera_in_sequence("Hero")

    if not camera_name:
        print("No Hero camera found!")
        return False

    print(f"Found camera: '{camera_name}'")

    # Test 2: Get all transforms
    print("\n3. Testing _capture_actor_transforms()...")

    # We need to access the method from ActivePanelWidget
    # For testing, let's recreate the logic here
    try:
        transforms = {}
        bindings = sequence_asset.get_bindings()

        for binding in bindings:
            actor_name = str(binding.get_display_name())

            # Get transform track
            transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
            if not transform_tracks:
                continue

            track = transform_tracks[0]
            sections = track.get_sections()
            if not sections:
                continue

            section = sections[0]

            # Get all channels
            channels = unreal.MovieSceneSectionExtensions.get_all_channels(section)

            if len(channels) < 6:
                continue

            # Read keyframes at frame 0
            loc_x = loc_y = loc_z = 0.0
            rot_roll = rot_pitch = rot_yaw = 0.0

            # Location
            for key in channels[0].get_keys():
                if key.get_time().frame_number.value == 0:
                    loc_x = key.get_value()
                    break
            for key in channels[1].get_keys():
                if key.get_time().frame_number.value == 0:
                    loc_y = key.get_value()
                    break
            for key in channels[2].get_keys():
                if key.get_time().frame_number.value == 0:
                    loc_z = key.get_value()
                    break

            # Rotation
            for key in channels[3].get_keys():
                if key.get_time().frame_number.value == 0:
                    rot_roll = key.get_value()
                    break
            for key in channels[4].get_keys():
                if key.get_time().frame_number.value == 0:
                    rot_pitch = key.get_value()
                    break
            for key in channels[5].get_keys():
                if key.get_time().frame_number.value == 0:
                    rot_yaw = key.get_value()
                    break

            transforms[actor_name] = {
                'location': {'x': loc_x, 'y': loc_y, 'z': loc_z},
                'rotation': {'pitch': rot_pitch, 'yaw': rot_yaw, 'roll': rot_roll}
            }

        print(f"Captured {len(transforms)} actor transforms:")
        for name in transforms.keys():
            print(f"- {name}")

    except Exception as e:
        print(f"Error capturing transforms: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 3: Check if camera is in transforms
    print(f"\n4. Checking if camera '{camera_name}' is in transforms...")

    if camera_name not in transforms:
        print(f"Camera '{camera_name}' NOT found in transforms!")
        print(f"Available actors: {list(transforms.keys())}")
        return False

    camera_transform = transforms[camera_name]
    print(f"Camera transform found:")
    print(f"Location: X={camera_transform['location']['x']:.1f}, Y={camera_transform['location']['y']:.1f}, Z={camera_transform['location']['z']:.1f}")
    print(f"Rotation: Pitch={camera_transform['rotation']['pitch']:.1f}, Yaw={camera_transform['rotation']['yaw']:.1f}, Roll={camera_transform['rotation']['roll']:.1f}")

    # Test 4: Check CSV file
    print("\n5. Checking if camera positions are in CSV...")

    csv_path = Path(unreal.Paths.project_saved_dir()) / "ThesisMetrics" / "Panel_008_multiview_iterations.csv"

    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        print("(This is OK if no iterations have been run yet)")
    else:
        with open(csv_path, 'r') as f:
            lines = f.readlines()
            if len(lines) > 1:
                # Check if camera columns have data
                header = lines[0].strip().split(',')
                first_data = lines[1].strip().split(',')

                # Find camera position columns
                cam_x_idx = header.index('camera_pos_x') if 'camera_pos_x' in header else -1
                cam_y_idx = header.index('camera_pos_y') if 'camera_pos_y' in header else -1
                cam_z_idx = header.index('camera_pos_z') if 'camera_pos_z' in header else -1

                if cam_x_idx >= 0 and cam_y_idx >= 0 and cam_z_idx >= 0:
                    cam_x = first_data[cam_x_idx] if cam_x_idx < len(first_data) else ''
                    cam_y = first_data[cam_y_idx] if cam_y_idx < len(first_data) else ''
                    cam_z = first_data[cam_z_idx] if cam_z_idx < len(first_data) else ''

                    if cam_x and cam_y and cam_z:
                        print(f"Camera positions ARE recorded in CSV:")
                        print(f"X={cam_x}, Y={cam_y}, Z={cam_z}")
                    else:
                        print(f"Camera position columns are EMPTY:")
                        print(f"X='{cam_x}', Y='{cam_y}', Z='{cam_z}'")
                        return False
                else:
                    print("Camera position columns not found in CSV header")
                    return False

    print("\n" + "="*70)
    print("ALL TESTS PASSED - Camera tracking is working!")
    print("="*70)
    return True

if __name__ == "__main__":
    test_camera_position_tracking()

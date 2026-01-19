# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Camera System for StoryboardTo3D
Professional camera control and movement generation
"""

import unreal
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class ShotType(Enum):
    """Standard shot types"""
    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    MEDIUM_WIDE = "medium_wide"
    MEDIUM = "medium"
    MEDIUM_CLOSE = "medium_close"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"

class CameraMovement(Enum):
    """Camera movement types"""
    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRUCK = "truck"
    PEDESTAL = "pedestal"
    ZOOM = "zoom"
    HANDHELD = "handheld"
    CRANE = "crane"
    ORBIT = "orbit"

class TransitionType(Enum):
    """Transition types between shots"""
    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    WIPE = "wipe"
    PUSH = "push"
    IRIS = "iris"

@dataclass
class CameraShot:
    """Camera shot data"""
    shot_type: ShotType
    location: unreal.Vector
    rotation: unreal.Rotator
    focal_length: float = 35.0
    aperture: float = 2.8
    focus_distance: float = 1000.0
    movement: CameraMovement = CameraMovement.STATIC
    movement_speed: float = 1.0
    duration: float = 3.0
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT

class CameraSystem:
    """
    Professional camera system for cinematic generation
    """

    # Shot type to focal length mapping (35mm equivalent)
    FOCAL_LENGTH_MAP = {
        ShotType.EXTREME_WIDE: 14,
        ShotType.WIDE: 24,
        ShotType.MEDIUM_WIDE: 35,
        ShotType.MEDIUM: 50,
        ShotType.MEDIUM_CLOSE: 85,
        ShotType.CLOSE_UP: 135,
        ShotType.EXTREME_CLOSE_UP: 200
    }

    # Shot type to distance multiplier
    DISTANCE_MAP = {
        ShotType.EXTREME_WIDE: 5.0,
        ShotType.WIDE: 3.0,
        ShotType.MEDIUM_WIDE: 2.0,
        ShotType.MEDIUM: 1.5,
        ShotType.MEDIUM_CLOSE: 1.0,
        ShotType.CLOSE_UP: 0.5,
        ShotType.EXTREME_CLOSE_UP: 0.3
    }

    def __init__(self):
        """Initialize camera system"""
        self.cameras = []
        self.active_camera = None
        self.sequence = None

    def create_camera(self,
                     name: str,
                     location: unreal.Vector,
                     rotation: unreal.Rotator,
                     shot_type: ShotType = ShotType.MEDIUM) -> unreal.CineCameraActor:
        """
        Create a cinematic camera

        Args:
            name: Camera name
            location: World location
            rotation: World rotation
            shot_type: Type of shot

        Returns:
            Created camera actor
        """
        # Spawn camera
        camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.CineCameraActor,
            location,
            rotation
        )

        if camera:
            camera.set_actor_label(name)

            # Get camera component
            camera_component = camera.get_cine_camera_component()

            # Set focal length based on shot type
            focal_length = self.FOCAL_LENGTH_MAP.get(shot_type, 35)
            camera_component.set_field_of_view(self.focal_to_fov(focal_length))

            # Set cinematic defaults
            camera_component.focus_settings.focus_method = unreal.CameraFocusMethod.TRACKING
            camera_component.current_aperture = 2.8

            # Enable depth of field
            post_process = camera_component.post_process_settings
            post_process.override_depth_of_field_focal_distance = True
            post_process.override_depth_of_field_fstop = True
            post_process.depth_of_field_fstop = 2.8

            self.cameras.append(camera)
            self.active_camera = camera

            unreal.log(f"Created camera: {name} at {location}")

        return camera

    def setup_shot(self,
                  camera: unreal.CineCameraActor,
                  target: unreal.Actor,
                  shot_type: ShotType,
                  offset: Optional[unreal.Vector] = None) -> None:
        """
        Setup camera for a specific shot

        Args:
            camera: Camera actor
            target: Target actor to frame
            shot_type: Type of shot
            offset: Optional position offset
        """
        if not camera or not target:
            return

        # Get target bounds
        origin, extent = target.get_actor_bounds(False)

        # Calculate camera distance based on shot type
        distance_multiplier = self.DISTANCE_MAP.get(shot_type, 1.5)
        base_distance = max(extent.x, extent.y, extent.z) * 2
        camera_distance = base_distance * distance_multiplier

        # Calculate camera position
        forward = target.get_actor_forward_vector()
        right = target.get_actor_right_vector()
        up = target.get_actor_up_vector()

        # Default offset for 3/4 view
        if offset is None:
            offset = forward * -1 + right * 0.5 + up * 0.3
            offset.normalize()

        camera_pos = origin + (offset * camera_distance)

        # Set camera position
        camera.set_actor_location(camera_pos)

        # Look at target
        self.look_at(camera, origin)

        # Set focal distance
        camera_component = camera.get_cine_camera_component()
        camera_component.focus_settings.manual_focus_distance = camera_distance

        # Set focal length
        focal_length = self.FOCAL_LENGTH_MAP.get(shot_type, 35)
        camera_component.set_field_of_view(self.focal_to_fov(focal_length))

    def look_at(self, camera: unreal.CineCameraActor, target: unreal.Vector) -> None:
        """
        Make camera look at target

        Args:
            camera: Camera actor
            target: Target location
        """
        if not camera:
            return

        camera_loc = camera.get_actor_location()
        direction = target - camera_loc
        direction.normalize()

        # Calculate rotation
        rotation = unreal.MathLibrary.make_rot_from_x(direction)
        camera.set_actor_rotation(rotation)

    def create_camera_movement(self,
                             camera: unreal.CineCameraActor,
                             movement: CameraMovement,
                             start: unreal.Transform,
                             end: unreal.Transform,
                             duration: float = 3.0) -> None:
        """
        Create camera movement animation

        Args:
            camera: Camera actor
            movement: Type of movement
            start: Start transform
            end: End transform
            duration: Movement duration
        """
        if not self.sequence or not camera:
            return

        # Get or create camera track
        camera_binding = self.sequence.add_possessable(camera)

        # Add transform track
        transform_track = camera_binding.add_track(unreal.MovieScene3DTransformTrack)
        transform_section = transform_track.add_section()

        # Set time range
        start_frame = 0
        end_frame = int(duration * 30)  # 30 fps
        transform_section.set_range(start_frame, end_frame)

        # Add keyframes
        channels = transform_section.get_channels()

        # Location channels
        for i, channel in enumerate(channels[:3]):
            start_val = [start.translation.x, start.translation.y, start.translation.z][i]
            end_val = [end.translation.x, end.translation.y, end.translation.z][i]

            # Add keys
            channel.add_key(start_frame, start_val)
            channel.add_key(end_frame, end_val)

            # Set interpolation
            if movement == CameraMovement.HANDHELD:
                # Add noise for handheld
                self.add_handheld_noise(channel, start_frame, end_frame)
            else:
                # Smooth interpolation
                for key in channel.get_keys():
                    key.set_interpolation_mode(unreal.MovieSceneKeyInterpolation.CUBIC)

    def add_handheld_noise(self, channel, start_frame: int, end_frame: int) -> None:
        """
        Add handheld camera shake

        Args:
            channel: Animation channel
            start_frame: Start frame
            end_frame: End frame
        """
        import random

        num_keys = 10
        frame_step = (end_frame - start_frame) / num_keys

        for i in range(1, num_keys):
            frame = start_frame + int(i * frame_step)
            base_value = channel.evaluate(frame)
            noise = random.uniform(-2, 2)  # Small random offset
            channel.add_key(frame, base_value + noise)

    def apply_rule_of_thirds(self, camera: unreal.CineCameraActor,
                           target: unreal.Actor,
                           position: str = "right_upper") -> None:
        """
        Position target using rule of thirds

        Args:
            camera: Camera actor
            target: Target actor
            position: Grid position (left_upper, center, right_lower, etc.)
        """
        if not camera or not target:
            return

        # Get camera component
        camera_component = camera.get_cine_camera_component()

        # Calculate screen positions
        positions = {
            "left_upper": (-0.33, -0.33),
            "center_upper": (0, -0.33),
            "right_upper": (0.33, -0.33),
            "left_center": (-0.33, 0),
            "center": (0, 0),
            "right_center": (0.33, 0),
            "left_lower": (-0.33, 0.33),
            "center_lower": (0, 0.33),
            "right_lower": (0.33, 0.33)
        }

        screen_offset = positions.get(position, (0, 0))

        # Apply offset to camera rotation
        current_rot = camera.get_actor_rotation()
        yaw_offset = screen_offset[0] * 30  # Degrees
        pitch_offset = screen_offset[1] * 20  # Degrees

        new_rot = unreal.Rotator(
            current_rot.pitch + pitch_offset,
            current_rot.yaw + yaw_offset,
            current_rot.roll
        )

        camera.set_actor_rotation(new_rot)

    def create_depth_of_field(self,
                            camera: unreal.CineCameraActor,
                            focus_target: unreal.Actor,
                            aperture: float = 2.8) -> None:
        """
        Setup depth of field

        Args:
            camera: Camera actor
            focus_target: Actor to focus on
            aperture: F-stop value
        """
        if not camera:
            return

        camera_component = camera.get_cine_camera_component()

        # Enable DOF
        camera_component.focus_settings.focus_method = unreal.CameraFocusMethod.TRACKING
        camera_component.focus_settings.tracking_focus_settings.actor_to_track = focus_target

        # Set aperture
        camera_component.current_aperture = aperture

        # Update post process
        post_process = camera_component.post_process_settings
        post_process.override_depth_of_field_fstop = True
        post_process.depth_of_field_fstop = aperture

    def focal_to_fov(self, focal_length: float, sensor_width: float = 36.0) -> float:
        """
        Convert focal length to field of view

        Args:
            focal_length: Focal length in mm
            sensor_width: Sensor width in mm (default 35mm)

        Returns:
            Field of view in degrees
        """
        return math.degrees(2 * math.atan(sensor_width / (2 * focal_length)))

    def generate_shot_sequence(self, shots: List[CameraShot]) -> unreal.LevelSequence:
        """
        Generate a sequence from camera shots

        Args:
            shots: List of camera shots

        Returns:
            Generated level sequence
        """
        # Create sequence
        sequence_name = "Generated_Sequence"
        sequence_path = "/Game/StoryboardTo3D/Sequences"

        # Create sequence asset
        factory = unreal.LevelSequenceFactoryNew()
        sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            sequence_name,
            sequence_path,
            unreal.LevelSequence,
            factory
        )

        if not sequence:
            unreal.log_error("Failed to create sequence")
            return None

        self.sequence = sequence
        current_time = 0

        for i, shot in enumerate(shots):
            # Create camera for shot
            camera_name = f"Camera_{i+1:03d}"
            camera = self.create_camera(
                camera_name,
                shot.location,
                shot.rotation,
                shot.shot_type
            )

            if camera:
                # Add to sequence
                start_frame = int(current_time * 30)
                end_frame = int((current_time + shot.duration) * 30)

                # Add camera cut track ()
                movie_scene = sequence.get_movie_scene()
                if not movie_scene:
                    unreal.log_error("Failed to get movie scene")
                    continue

                camera_cut_track = movie_scene.add_track(unreal.MovieSceneCameraCutTrack)
                camera_cut_section = camera_cut_track.add_section()
                camera_cut_section.set_range(start_frame, end_frame)

                # Bind camera
                camera_binding = sequence.add_possessable(camera)
                camera_cut_section.set_camera_binding_id(camera_binding.get_binding_id())

                current_time += shot.duration

        unreal.log(f"Generated sequence with {len(shots)} shots")
        return sequence

    def analyze_180_rule(self, camera1: unreal.CineCameraActor,
                        camera2: unreal.CineCameraActor,
                        subject: unreal.Actor) -> bool:
        """
        Check if camera placement follows 180-degree rule

        Args:
            camera1: First camera
            camera2: Second camera
            subject: Subject actor

        Returns:
            True if rule is followed
        """
        if not all([camera1, camera2, subject]):
            return True

        # Get positions
        cam1_pos = camera1.get_actor_location()
        cam2_pos = camera2.get_actor_location()
        subject_pos = subject.get_actor_location()

        # Calculate vectors
        vec1 = cam1_pos - subject_pos
        vec2 = cam2_pos - subject_pos

        # Normalize
        vec1.normalize()
        vec2.normalize()

        # Calculate angle
        dot = vec1.x * vec2.x + vec1.y * vec2.y
        angle = math.degrees(math.acos(min(1, max(-1, dot))))

        # Check if within 180 degrees
        return angle <= 180

# Global camera system instance
_camera_system = None

def get_camera_system() -> CameraSystem:
    """Get global camera system instance"""
    global _camera_system
    if _camera_system is None:
        _camera_system = CameraSystem()
    return _camera_system

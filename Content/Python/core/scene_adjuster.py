# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Automatically applies AI positioning recommendations to Unreal scene
"""
import unreal
from typing import Dict, List, Any, Optional

class SceneAdjuster:
    """Applies AI positioning recommendations to actors and cameras"""

    def __init__(self, sequence_asset=None, use_absolute_positioning=False):
        """
        Initialize SceneAdjuster

        Args:
            sequence_asset: Level sequence to apply adjustments to
            use_absolute_positioning: If True, treat position values as absolute coordinates.
                                     If False (default), treat as relative adjustments.
        """
        self.editor_actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.sequence_asset = sequence_asset
        self.use_absolute_positioning = use_absolute_positioning

    def find_actor_by_name(self, actor_name: str) -> Optional[unreal.Actor]:
        """Find an actor in the current level by name"""
        all_actors = self.editor_actor_subsystem.get_all_level_actors()

        for actor in all_actors:
            if actor.get_actor_label() == actor_name:
                return actor
            # Also check if the name is part of the label
            if actor_name.lower() in actor.get_actor_label().lower():
                return actor

        unreal.log_warning(f"Actor '{actor_name}' not found in level")

        # Try finding in sequence if available
        if self.sequence_asset:
            unreal.log(f"Searching in sequence bindings...")
            return self.find_actor_in_sequence(actor_name)

        return None

    def find_actor_in_sequence(self, actor_name: str) -> Optional[unreal.Actor]:
        """Find an actor bound in a sequence (possessable/spawnable)

        NOTE: For spawnables, returns None because the template can't be directly modified.
        Caller should use apply_adjustment_to_sequence() instead.
        """
        if not self.sequence_asset:
            return None

        try:
            bindings = self.sequence_asset.get_bindings()

            for binding in bindings:
                binding_name = str(binding.get_display_name())  # Convert Text to string

                if actor_name.lower() in binding_name.lower():
                    unreal.log(f"Found '{binding_name}' in sequence bindings")

                    # For spawnables, get the object template
                    object_template = binding.get_object_template()
                    if object_template:
                        unreal.log("This is a spawnable - using keyframe API")
                        # Return None to signal caller to use sequence keyframe API
                        return None

                    # For possessables, try to find the bound actor in the level
                    # Get the binding ID and resolve it
                    binding_id = binding.get_id()

                    # Try to find actor with matching possessable GUID
                    all_actors = self.editor_actor_subsystem.get_all_level_actors()
                    for actor in all_actors:
                        # Check if this actor matches the binding
                        # (This is tricky - possessables are bound by GUID)
                        # For now, return None and we'll handle this differently
                        pass

                    unreal.log_warning(f"Could not resolve binding to actor (may be spawnable)")
                    return None

            unreal.log_warning(f"'{actor_name}' not found in sequence bindings")

        except Exception as e:
            unreal.log_error(f"Error searching sequence: {e}")

        return None

    def list_all_actors(self):
        """List all actors in level and sequence"""
        unreal.log("\n" + "="*70)
        unreal.log("ACTORS IN SCENE")
        unreal.log("="*70)

        # Level actors
        unreal.log("\nLevel Actors:")
        all_actors = self.editor_actor_subsystem.get_all_level_actors()
        for actor in all_actors:
            label = actor.get_actor_label()
            actor_type = actor.get_class().get_name()
            unreal.log(f"- {label} ({actor_type})")

        # Sequence actors
        if self.sequence_asset:
            unreal.log("\nSequence Bindings:")
            try:
                bindings = self.sequence_asset.get_bindings()
                for binding in bindings:
                    binding_name = str(binding.get_display_name())
                    unreal.log(f"- {binding_name}")
            except Exception as e:
                unreal.log_warning(f"Could not list sequence bindings: {e}")

        unreal.log("="*70 + "\n")

    def apply_position(self, actor: unreal.Actor, position: Dict[str, float]) -> bool:
        """Apply position to actor (using named parameters to avoid memory bug)"""
        try:
            old_location = actor.get_actor_location()

            new_location = unreal.Vector(
                x=position['x'],
                y=position['y'],
                z=position['z']
            )

            actor.set_actor_location(
                new_location=new_location,
                sweep=False,
                teleport=True
            )

            verify_location = actor.get_actor_location()

            if abs(verify_location.x - old_location.x) < 0.01 and \
               abs(verify_location.y - old_location.y) < 0.01 and \
               abs(verify_location.z - old_location.z) < 0.01:
                unreal.log_warning("Location did not change")

            unreal.log(f"Moved {actor.get_actor_label()} to X={position['x']}, Y={position['y']}, Z={position['z']}")
            return True

        except Exception as e:
            unreal.log_error(f"Failed to move actor: {e}")
            return False

    def apply_rotation(self, actor: unreal.Actor, rotation: Dict[str, float]) -> bool:
        """Apply rotation to actor (using named parameters to avoid memory bug)"""
        try:
            old_rotation = actor.get_actor_rotation()

            new_rotation = unreal.Rotator(
                pitch=rotation.get('pitch', 0.0),
                yaw=rotation.get('yaw', 0.0),
                roll=rotation.get('roll', 0.0)
            )

            actor.set_actor_rotation(
                new_rotation=new_rotation,
                teleport_physics=True
            )

            verify_rotation = actor.get_actor_rotation()

            if abs(verify_rotation.pitch - old_rotation.pitch) < 0.01 and \
               abs(verify_rotation.yaw - old_rotation.yaw) < 0.01 and \
               abs(verify_rotation.roll - old_rotation.roll) < 0.01:
                unreal.log_warning("Rotation did not change")

            unreal.log(f"Rotated {actor.get_actor_label()} to Pitch={rotation.get('pitch', 0)}, Yaw={rotation.get('yaw', 0)}, Roll={rotation.get('roll', 0)}")
            return True

        except Exception as e:
            unreal.log_error(f"Failed to rotate actor: {e}")
            return False

    def apply_adjustment(self, adjustment: Dict[str, Any]) -> bool:
        """Apply a single adjustment from AI recommendation"""
        actor_name = adjustment.get('actor')
        adj_type = adjustment.get('type')

        if not actor_name or not adj_type:
            unreal.log_warning("Invalid adjustment: missing actor or type")
            return False

        # Try to find actor in level first
        actor = self.find_actor_by_name(actor_name)

        # If not in level and we have a sequence, apply to sequence binding
        if not actor and self.sequence_asset:
            return self.apply_adjustment_to_sequence(actor_name, adjustment)

        if not actor:
            return False

        # Apply based on type
        if adj_type == 'move' and 'position' in adjustment:
            return self.apply_position(actor, adjustment['position'])

        elif adj_type == 'rotate' and 'rotation' in adjustment:
            return self.apply_rotation(actor, adjustment['rotation'])

        else:
            unreal.log_warning(f"Unknown adjustment type: {adj_type}")
            return False

    def apply_adjustment_to_sequence(self, actor_name: str, adjustment: Dict[str, Any]) -> bool:
        """Apply adjustment directly to sequence binding by setting keyframes in transform tracks"""
        try:
            # Ensure sequence is open in editor (required for channel access)
            unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(self.sequence_asset)

            bindings = self.sequence_asset.get_bindings()

            # Find the binding
            target_binding = None
            for binding in bindings:
                binding_name = str(binding.get_display_name())
                if actor_name.lower() in binding_name.lower():
                    target_binding = binding
                    break

            if not target_binding:
                unreal.log_warning(f"Binding not found for {actor_name}")
                return False

            adj_type = adjustment.get('type')

            # Get or create transform track
            transform_tracks = target_binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)

            if not transform_tracks:
                transform_track = target_binding.add_track(unreal.MovieScene3DTransformTrack)
            else:
                transform_track = transform_tracks[0]

            # Get or create section
            sections = transform_track.get_sections()
            if not sections:
                section = transform_track.add_section()
                section.set_start_frame(0)
                section.set_end_frame(1000)
            else:
                section = sections[0]

            # Get all 9 transform channels: [0-2] Location, [3-5] Rotation, [6-8] Scale
            channels = section.get_all_channels()

            if not channels or len(channels) < 9:
                unreal.log_error(f"Could not access transform channels (got {len(channels) if channels else 0})")
                return False

            # Create keyframe at frame 0 (you can change this)
            frame = unreal.FrameNumber(0)

            if adj_type == 'move' and 'position' in adjustment:
                pos = adjustment['position']

                # Read current values at frame 0 (if they exist)
                current_x = 0.0
                current_y = 0.0
                current_z = 0.0

                # Try to get existing keyframe values
                try:
                    all_keys_x = channels[0].get_keys()
                    all_keys_y = channels[1].get_keys()
                    all_keys_z = channels[2].get_keys()

                    # Find keyframe at frame 0
                    for key in all_keys_x:
                        if key.get_time().frame_number.value == 0:
                            current_x = key.get_value()
                            break
                    for key in all_keys_y:
                        if key.get_time().frame_number.value == 0:
                            current_y = key.get_value()
                            break
                    for key in all_keys_z:
                        if key.get_time().frame_number.value == 0:
                            current_z = key.get_value()
                            break

                except:
                    pass

                # Apply positioning based on mode
                if self.use_absolute_positioning:
                    # ABSOLUTE MODE: Use AI values directly as target coordinates
                    new_x = float(pos['x'])
                    new_y = float(pos['y'])
                    new_z = float(pos['z'])
                else:
                    # RELATIVE MODE (default): Add AI values to current position
                    new_x = current_x + float(pos['x'])
                    new_y = current_y + float(pos['y'])
                    new_z = current_z + float(pos['z'])

                # VALIDATE POSITIONS: Prevent impossible locations
                binding_name = str(target_binding.get_display_name()).lower()
                is_camera = 'camera' in binding_name

                # Determine bounds
                if is_camera:
                    # Camera bounds: reasonable positioning around scene origin
                    min_x, max_x = -2000.0, 2000.0
                    min_y, max_y = -2000.0, 2000.0
                    min_z, max_z = 50.0, 1000.0  # Never underground, max 10m height
                else:
                    # Actor bounds (characters, props)
                    min_x, max_x = -5000.0, 5000.0  # Wide range for placement
                    min_y, max_y = -5000.0, 5000.0
                    min_z, max_z = -10.0, 300.0  # Ground level ±10cm to 3m height

                # Clamp values
                original_x, original_y, original_z = new_x, new_y, new_z
                new_x = max(min_x, min(max_x, new_x))
                new_y = max(min_y, min(max_y, new_y))
                new_z = max(min_z, min(max_z, new_z))

                # Log if clamped
                if abs(original_x - new_x) > 0.1 or abs(original_y - new_y) > 0.1 or abs(original_z - new_z) > 0.1:
                    unreal.log_warning(f"Position clamped: X={new_x:.2f}, Y={new_y:.2f}, Z={new_z:.2f}")

                # Set Location X/Y/Z channels [0-2] with ABSOLUTE values
                channels[0].add_key(frame, new_x)
                channels[1].add_key(frame, new_y)
                channels[2].add_key(frame, new_z)

                unreal.log(f"Set position keyframes at frame 0")
                unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
                return True

            elif adj_type == 'rotate' and 'rotation' in adjustment:
                rot = adjustment['rotation']
                pitch = float(rot.get('pitch', 0.0))
                yaw = float(rot.get('yaw', 0.0))
                roll = float(rot.get('roll', 0.0))

                # CRITICAL: Channel order is Roll, Pitch, Yaw (NOT Pitch, Yaw, Roll!)
                # channels[3] = Roll
                # channels[4] = Pitch
                # channels[5] = Yaw
                channels[3].add_key(frame, roll)    # Roll
                channels[4].add_key(frame, pitch)   # Pitch
                channels[5].add_key(frame, yaw)     # Yaw

                unreal.log("Set rotation keyframes at frame 0")
                unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
                return True

            else:
                unreal.log_warning(f"Unknown adjustment type: {adj_type}")
                return False

        except Exception as e:
            unreal.log_error(f"Error applying to sequence: {e}")
            return False

    def find_camera_in_sequence(self, camera_pattern: str = "Hero") -> Optional[str]:
        """Find camera binding in sequence (looks for Hero camera by default)"""
        if not self.sequence_asset:
            return None

        try:
            bindings = self.sequence_asset.get_bindings()

            for binding in bindings:
                binding_name = str(binding.get_display_name())

                # Look for Hero camera or CineCameraActor
                if camera_pattern.lower() in binding_name.lower() and "camera" in binding_name.lower():
                    unreal.log(f"Found camera: '{binding_name}'")
                    return binding_name

            unreal.log_warning(f"Camera with pattern '{camera_pattern}' not found")
            return None

        except Exception as e:
            unreal.log_error(f"Error finding camera: {e}")
            return None

    def calculate_look_at_rotation(self, camera_pos: Dict, target_pos: Dict) -> Dict:
        """
        Calculate rotation needed for camera to look at target

        Args:
            camera_pos: {x, y, z} camera position
            target_pos: {x, y, z} character position OR center point between characters

        Returns:
            {pitch, yaw, roll} rotation values in degrees
        """
        import math

        # SIMPLIFIED FOR T-POSE PROOF-OF-CONCEPT:
        # Characters at Z=0 (ground level), height ~170 units
        # For medium shot, look at chest/head level (~85-100 units up)
        # target_pos is already the look-at point (center between characters)
        # Add offset to look at mid-body height for better framing
        head_offset = 85.0  # Look at chest level for medium shot (half character height)
        target_head_z = target_pos['z'] + head_offset

        # Direction vector from camera to target HEAD
        dx = target_pos['x'] - camera_pos['x']
        dy = target_pos['y'] - camera_pos['y']
        dz = target_head_z - camera_pos['z']  # Look at HEAD, not feet

        # Calculate horizontal distance
        horizontal_dist = math.sqrt(dx*dx + dy*dy)

        # Calculate yaw (left/right rotation around Z-axis)
        # atan2(dy, dx) gives angle in XY plane
        yaw = math.degrees(math.atan2(dy, dx))

        # Calculate pitch (up/down rotation)
        # Unreal: negative pitch = look down, positive pitch = look up
        # atan2 gives correct sign: negative dz (target below) → negative angle → look down
        pitch = math.degrees(math.atan2(dz, horizontal_dist))

        # Roll usually 0 for cameras
        roll = 0.0

        return {'pitch': pitch, 'yaw': yaw, 'roll': roll}

    def _get_actor_position_from_sequence(self, actor_name: str, skip_cameras: bool = True) -> Optional[Dict]:
        """
        Get any actor's position from sequence keyframes at frame 0 (including cameras if skip_cameras=False)

        Args:
            actor_name: Name of actor to find
            skip_cameras: If True, skip camera bindings (default True for backwards compatibility)

        Returns:
            {x, y, z} position dict or None
        """
        if not self.sequence_asset:
            return None

        try:
            bindings = self.sequence_asset.get_bindings()

            for binding in bindings:
                binding_name = str(binding.get_display_name())

                # Optionally skip cameras and lights
                if skip_cameras and ('camera' in binding_name.lower() or 'light' in binding_name.lower()):
                    continue

                # Check if this is the actor we're looking for
                if actor_name.lower() in binding_name.lower():
                    # Get transform track
                    transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
                    if not transform_tracks:
                        continue

                    section = transform_tracks[0].get_sections()[0]
                    channels = section.get_all_channels()

                    if not channels or len(channels) < 3:
                        continue

                    # Get position at frame 0 (channels [0-2] are Location X/Y/Z)
                    x_val = 0.0
                    y_val = 0.0
                    z_val = 0.0

                    # Get keyframes from each channel
                    all_keys_x = channels[0].get_keys()
                    all_keys_y = channels[1].get_keys()
                    all_keys_z = channels[2].get_keys()

                    # Find keyframe at frame 0
                    for key in all_keys_x:
                        if key.get_time().frame_number.value == 0:
                            x_val = key.get_value()
                            break
                    for key in all_keys_y:
                        if key.get_time().frame_number.value == 0:
                            y_val = key.get_value()
                            break
                    for key in all_keys_z:
                        if key.get_time().frame_number.value == 0:
                            z_val = key.get_value()
                            break

                    return {'x': x_val, 'y': y_val, 'z': z_val}

        except Exception as e:
            unreal.log_error(f"Error getting actor position: {e}")

        return None

    def get_character_position_from_sequence(self, character_name: str) -> Optional[Dict]:
        """
        Get character position from sequence keyframes at frame 0

        Args:
            character_name: Name of character to find

        Returns:
            {x, y, z} position dict or None
        """
        if not self.sequence_asset:
            return None

        try:
            bindings = self.sequence_asset.get_bindings()

            for binding in bindings:
                binding_name = str(binding.get_display_name())

                # Skip cameras and lights
                if 'camera' in binding_name.lower() or 'light' in binding_name.lower():
                    continue

                # Check if this is the character we're looking for
                if character_name.lower() in binding_name.lower():
                    # Get transform track
                    transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
                    if not transform_tracks:
                        unreal.log_warning(f"No transform track for {binding_name}")
                        continue

                    section = transform_tracks[0].get_sections()[0]
                    channels = section.get_all_channels()

                    if not channels or len(channels) < 3:
                        unreal.log_warning(f"Invalid channels for {binding_name}")
                        continue

                    # Get position at frame 0 (channels [0-2] are Location X/Y/Z)
                    # Read keyframe values at frame 0
                    x_val = 0.0
                    y_val = 0.0
                    z_val = 0.0

                    # Get keyframes from each channel
                    all_keys_x = channels[0].get_keys()
                    all_keys_y = channels[1].get_keys()
                    all_keys_z = channels[2].get_keys()

                    # Find keyframe at frame 0
                    for key in all_keys_x:
                        if key.get_time().frame_number.value == 0:
                            x_val = key.get_value()
                            break
                    for key in all_keys_y:
                        if key.get_time().frame_number.value == 0:
                            y_val = key.get_value()
                            break
                    for key in all_keys_z:
                        if key.get_time().frame_number.value == 0:
                            z_val = key.get_value()
                            break

                    unreal.log(f"Found character '{binding_name}' at: X={x_val:.1f}, Y={y_val:.1f}, Z={z_val:.1f}")
                    return {'x': x_val, 'y': y_val, 'z': z_val}

            unreal.log_warning(f"Character '{character_name}' not found in sequence")

        except Exception as e:
            unreal.log_error(f"Error getting character position: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

        # Fallback: assume origin with sitting head height for framing
        # If character is at Z=90 (sitting simulation), head is at ~Z=140 (90 base + 50 head offset)
        # Camera should look at head/face level (~140cm for sitting, ~160cm standing)
        unreal.log_warning(f"\n FALLBACK TRIGGERED: Character '{character_name}' not found in sequence!")
        unreal.log_warning(f"Using fallback position: (0, 0, 140) [sitting head height]")
        unreal.log_warning(f"This may cause incorrect camera look-at calculations!")
        return {'x': 0, 'y': 0, 'z': 140}  # Assume sitting character head at ~140cm height

    def apply_camera_adjustment(self, camera_adjustments: Dict[str, Any]) -> bool:
        """
        Apply camera position and rotation adjustments with automatic look-at

        CRITICAL: If position is provided, rotation is AUTO-CALCULATED to look at
        the main character. This ensures camera always frames the subject correctly.
        """
        if not camera_adjustments.get('needs_adjustment'):
            return True

        try:
            # Find the hero camera
            camera_name = self.find_camera_in_sequence("Hero")

            if not camera_name:
                unreal.log_warning("Hero camera not found in sequence")
                return False

            unreal.log(f"Applying camera adjustments to: {camera_name}")

            # VALIDATION: Warn if AI provided rotation (should always be null)
            if 'rotation' in camera_adjustments and camera_adjustments['rotation'] is not None:
                unreal.log_warning("AI provided camera rotation, but rotation is auto-calculated via look-at")
                unreal.log_warning("AI-provided rotation will be IGNORED to prevent incorrect camera angles")

            success = True
            new_camera_pos = None

            # Apply position if present and valid
            if 'position' in camera_adjustments and camera_adjustments['position'] is not None:
                new_camera_pos = camera_adjustments['position']

                # VALIDATE: In RELATIVE mode, check if camera will end up behind characters
                # Note: Get camera's actual position, not character position (was reading wrong actor)
                if not self.use_absolute_positioning:
                    # Get camera's current position from sequence (need to check camera binding, not character)
                    camera_current_pos = self._get_actor_position_from_sequence(camera_name, skip_cameras=False)

                    # Get characters' average X position to determine "front" vs "behind"
                    character_names = ['Oat', 'Sprout']
                    character_x_positions = []
                    for char_name in character_names:
                        char_pos = self.get_character_position_from_sequence(char_name)
                        if char_pos:
                            character_x_positions.append(char_pos['x'])

                    if camera_current_pos and character_x_positions:
                        avg_character_x = sum(character_x_positions) / len(character_x_positions)
                        final_camera_x = camera_current_pos['x'] + new_camera_pos['x']

                        # If camera ends up BEHIND characters' average position, warn but don't auto-fix
                        # (Auto-fix was causing camera to move in wrong direction)
                        if final_camera_x > avg_character_x + 50:  # 50cm tolerance
                            unreal.log_warning(f"Camera would be BEHIND characters")
                            unreal.log_warning(f"Camera final X: {final_camera_x:.1f}, Characters avg X: {avg_character_x:.1f}")
                            unreal.log_warning(f"Keeping AI's adjustment - AI should correct this on next iteration")
                            # Don't auto-flip - let AI learn from the result

                pos_adjustment = {
                    'actor': camera_name,
                    'type': 'move',
                    'position': new_camera_pos,
                    'reason': camera_adjustments.get('reason', 'Camera repositioning')
                }
                if not self.apply_adjustment_to_sequence(camera_name, pos_adjustment):
                    success = False
                else:
                    unreal.log(f"Camera adjustment applied: X={new_camera_pos['x']:.1f}, Y={new_camera_pos['y']:.1f}, Z={new_camera_pos['z']:.1f}")

            # CRITICAL: Calculate look-at rotation to point camera at character(s)
            if new_camera_pos:
                unreal.log(f"\n Calculating look-at rotation...")

                # IMPROVED: For multiple characters, look at CENTER point between them
                # This gives better medium shot framing than focusing on one character
                character_names_to_try = ['Oat', 'Sprout']
                character_positions = []

                unreal.log(f"Searching for characters: {character_names_to_try}")
                for char_name in character_names_to_try:
                    pos = self.get_character_position_from_sequence(char_name)
                    if pos:
                        character_positions.append(pos)
                        unreal.log(f"Found {char_name} at: X={pos['x']:.1f}, Y={pos['y']:.1f}, Z={pos['z']:.1f}")
                    else:
                        unreal.log_warning(f"Could not find {char_name} in sequence")

                # Calculate center point between all characters
                target_pos = None
                if len(character_positions) > 1:
                    # Multiple characters: use center point for balanced framing
                    avg_x = sum(p['x'] for p in character_positions) / len(character_positions)
                    avg_y = sum(p['y'] for p in character_positions) / len(character_positions)
                    avg_z = sum(p['z'] for p in character_positions) / len(character_positions)
                    target_pos = {'x': avg_x, 'y': avg_y, 'z': avg_z}
                    unreal.log(f"Using center point between {len(character_positions)} characters")
                elif len(character_positions) == 1:
                    # Single character: look at that character
                    target_pos = character_positions[0]
                    unreal.log(f"Using single character position")
                else:
                    # Fallback: look at any non-camera actor
                    unreal.log("Looking for any character in scene...")
                    try:
                        bindings = self.sequence_asset.get_bindings()
                        for binding in bindings:
                            binding_name = str(binding.get_display_name()).lower()
                            if 'camera' not in binding_name and 'light' not in binding_name:
                                target_pos = self.get_character_position_from_sequence(str(binding.get_display_name()))
                                if target_pos:
                                    break
                    except:
                        pass

                if target_pos:
                    #  DIAGNOSTIC: Log what target_pos we're using for look-at
                    unreal.log(f"\n DIAGNOSTIC: Look-at calculation inputs:")
                    unreal.log(f"Camera position: X={new_camera_pos['x']:.1f}, Y={new_camera_pos['y']:.1f}, Z={new_camera_pos['z']:.1f}")
                    unreal.log(f"Target position: X={target_pos['x']:.1f}, Y={target_pos['y']:.1f}, Z={target_pos['z']:.1f}")
                    unreal.log(f"Target with head_offset (+85): Z={target_pos['z'] + 85.0:.1f}")

                    # Calculate rotation to look at target
                    calculated_rotation = self.calculate_look_at_rotation(new_camera_pos, target_pos)

                    unreal.log(f"Look-at target: X={target_pos['x']:.1f}, Y={target_pos['y']:.1f}, Z={target_pos['z']:.1f}")
                    unreal.log(f"Calculated rotation:")
                    unreal.log(f"Pitch={calculated_rotation['pitch']:.1f}° (up/down tilt)")
                    unreal.log(f"Yaw={calculated_rotation['yaw']:.1f}° (left/right turn)")
                    unreal.log(f"Roll={calculated_rotation['roll']:.1f}° (camera tilt)")

                    # Apply the calculated rotation
                    rot_adjustment = {
                        'actor': camera_name,
                        'type': 'rotate',
                        'rotation': calculated_rotation,
                        'reason': 'Auto-calculated look-at rotation'
                    }
                    if not self.apply_adjustment_to_sequence(camera_name, rot_adjustment):
                        success = False
                    else:
                        unreal.log(f"Camera rotation applied (auto look-at)")
                else:
                    unreal.log_warning("No character found to look at, camera pointing forward")

            # If rotation provided explicitly (without position), REJECT IT
            elif 'rotation' in camera_adjustments and camera_adjustments['rotation'] is not None:
                unreal.log_warning("AI provided camera rotation - IGNORING (rotation should be null)")
                unreal.log_warning("Camera rotation is auto-calculated via look-at, AI should not provide rotation values")
                unreal.log("Skipping AI-provided rotation to prevent incorrect camera angles")
                # DO NOT APPLY - rotation should always be auto-calculated via look-at

            return success

        except Exception as e:
            unreal.log_error(f"Error applying camera adjustment: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

    def apply_all_adjustments(self, ai_response: Dict[str, Any]) -> Dict[str, int]:
        """Apply all adjustments from AI response (actors + camera)"""
        unreal.log("\n" + "="*70)
        unreal.log("APPLYING AI RECOMMENDATIONS")
        unreal.log("="*70)

        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'camera_applied': False
        }

        # Apply actor adjustments
        adjustments = ai_response.get('adjustments', [])

        if adjustments:
            unreal.log(f"\nFound {len(adjustments)} actor adjustments to apply\n")

            for i, adjustment in enumerate(adjustments, 1):
                results['total'] += 1

                actor_name = adjustment.get('actor', 'Unknown')
                adj_type = adjustment.get('type', 'unknown')
                reason = adjustment.get('reason', 'No reason provided')

                unreal.log(f"[{i}/{len(adjustments)}] {actor_name} ({adj_type}): {reason}")

                if self.apply_adjustment(adjustment):
                    results['success'] += 1
                else:
                    results['failed'] += 1
        else:
            unreal.log("\nNo actor adjustments needed\n")

        # Apply camera adjustments
        camera_adjustments = ai_response.get('camera_adjustments', {})
        if camera_adjustments:
            unreal.log("="*70)
            unreal.log("APPLYING CAMERA ADJUSTMENTS")
            unreal.log("="*70 + "\n")

            if self.apply_camera_adjustment(camera_adjustments):
                results['camera_applied'] = True
                unreal.log("Camera adjustments applied")
            else:
                unreal.log_warning("Camera adjustments failed")

        # Summary
        unreal.log("="*70)
        unreal.log(f"Applied {results['success']}/{results['total']} actor adjustments")
        if results['failed'] > 0:
            unreal.log_warning(f"Failed: {results['failed']}")
        if results['camera_applied']:
            unreal.log("Camera adjustments applied")
        unreal.log("="*70 + "\n")

        return results


def test_scene_adjuster():
    """Test the scene adjuster with a sample AI response"""

    # Sample AI response (like what you got)
    sample_response = {
        "match_score": 60,
        "analysis": "Test adjustment",
        "adjustments": [
            {
                "actor": "Oat",
                "type": "move",
                "reason": "Oat needs to be seated",
                "position": {"x": 0, "y": -0.5, "z": 0}
            },
            {
                "actor": "Oat",
                "type": "rotate",
                "reason": "Face forward",
                "rotation": {"pitch": 0, "yaw": 180, "roll": 0}
            }
        ]
    }

    adjuster = SceneAdjuster()
    results = adjuster.apply_all_adjustments(sample_response)

    return results

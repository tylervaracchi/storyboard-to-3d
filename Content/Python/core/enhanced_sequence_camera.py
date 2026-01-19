# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Enhanced Camera Cut Track and Viewport Locking for Unreal Engine 5.6
Properly creates camera cut tracks and locks viewport when generating scenes
"""

import unreal

class EnhancedSequenceCamera:
    """Handles camera cut track creation and viewport locking for sequences"""

    def __init__(self):
        self.sequence = None
        self.camera_actor = None
        self.camera_cut_track = None

    def setup_sequence_with_camera_cuts(self, sequence_path, camera_actor, duration_frames=90):
        """
        Complete setup: Create sequence with camera cut track and lock viewport

        Args:
            sequence_path: Path to the level sequence
            camera_actor: The CineCameraActor to use
            duration_frames: Duration of the sequence in frames

        Returns:
            dict: Setup result with sequence, camera binding, and lock status
        """

        result = {
            'success': False,
            'sequence': None,
            'camera_binding': None,
            'viewport_locked': False,
            'camera_cut_track': None,
            'errors': []
        }

        try:
            # Step 1: Load or create the sequence
            unreal.log(f"[CameraSetup] Loading sequence: {sequence_path}")
            self.sequence = self._load_or_create_sequence(sequence_path, duration_frames)

            if not self.sequence:
                result['errors'].append("Failed to load/create sequence")
                return result

            result['sequence'] = self.sequence
            self.camera_actor = camera_actor

            # Step 2: Add camera to sequence as possessable
            unreal.log(f"[CameraSetup] Adding camera to sequence...")
            camera_binding = self._add_camera_to_sequence()

            if not camera_binding:
                result['errors'].append("Failed to add camera to sequence")
                return result

            result['camera_binding'] = camera_binding

            # Step 3: Create camera cut track
            unreal.log(f"[CameraSetup] Creating camera cut track...")
            self.camera_cut_track = self._create_camera_cut_track(camera_binding, duration_frames)

            if not self.camera_cut_track:
                result['errors'].append("Failed to create camera cut track")
                return result

            result['camera_cut_track'] = self.camera_cut_track

            # Step 4: Open sequence in editor
            unreal.log(f"[CameraSetup] Opening sequence in editor...")
            self._open_sequence_in_editor()

            # Step 5: Lock viewport to camera cuts
            unreal.log(f"[CameraSetup] Locking viewport to camera cuts...")
            viewport_locked = self._lock_viewport_to_camera_cuts()
            result['viewport_locked'] = viewport_locked

            if viewport_locked:
                unreal.log("Viewport successfully locked to camera cuts!")
            else:
                result['errors'].append("Could not lock viewport (may need manual lock)")

            # Step 6: Save the sequence
            unreal.EditorAssetLibrary.save_asset(sequence_path)
            unreal.log(f"[CameraSetup] Sequence saved: {sequence_path}")

            result['success'] = True

            # Print summary
            self._print_setup_summary(result)

        except Exception as e:
            unreal.log_error(f"[CameraSetup] Exception during setup: {e}")
            result['errors'].append(str(e))

        return result

    def _load_or_create_sequence(self, sequence_path, duration_frames):
        """Load existing sequence or create new one"""

        if unreal.EditorAssetLibrary.does_asset_exist(sequence_path):
            # Load existing
            sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)
            unreal.log(f"Loaded existing sequence")
        else:
            # Create new
            factory = unreal.LevelSequenceFactoryNew()

            # Extract name and path
            parts = sequence_path.split('/')
            asset_name = parts[-1]
            package_path = '/'.join(parts[:-1])

            # Ensure directory exists
            if not unreal.EditorAssetLibrary.does_directory_exist(package_path):
                unreal.EditorAssetLibrary.make_directory(package_path)

            sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name=asset_name,
                package_path=package_path,
                asset_class=unreal.LevelSequence,
                factory=factory
            )
            unreal.log(f"Created new sequence")

        if sequence:
            # Configure sequence settings - SIMPLIFIED for UE 5.6
            # Set frame rate (30 fps)
            sequence.set_display_rate(unreal.FrameRate(30, 1))

            # Set playback range using direct methods (more reliable in UE 5.6)
            sequence.set_playback_start(0)
            sequence.set_playback_end(duration_frames)

            unreal.log(f"Configured: 30fps, 0-{duration_frames} frames")

        return sequence

    def _add_camera_to_sequence(self):
        """Add camera actor to sequence as possessable"""

        if not self.camera_actor or not self.sequence:
            unreal.log_error("No camera actor or sequence available")
            return None

        # Check if camera is already in sequence
        movie_scene = self.sequence.get_movie_scene()
        if not movie_scene:
            unreal.log_error("No movie scene found")
            return None

        # Add as possessable (references existing actor in level)
        camera_binding = self.sequence.add_possessable(self.camera_actor)

        if camera_binding:
            unreal.log(f"Added camera as possessable: {self.camera_actor.get_actor_label()}")

            # Add a transform track for the camera
            transform_track = camera_binding.add_track(unreal.MovieScene3DTransformTrack)
            if transform_track:
                transform_section = transform_track.add_section()
                if transform_section:
                    # Set section to cover entire sequence
                    transform_section.set_start_frame_bounded(True)
                    transform_section.set_end_frame_bounded(True)
                    transform_section.set_start_frame(0)
                    transform_section.set_end_frame(90)
                    unreal.log("Added transform track to camera")
        else:
            unreal.log_error("Failed to add camera binding")

        return camera_binding

    def _create_camera_cut_track(self, camera_binding, duration_frames):
        """Create camera cut track and add camera to it"""

        movie_scene = self.sequence.get_movie_scene()
        if not movie_scene:
            unreal.log_error("No movie scene available")
            return None

        # Check for existing camera cut track
        camera_cut_track = None

        # UE 5.6 uses get_tracks() instead of get_master_tracks()
        all_tracks = movie_scene.get_tracks()

        for track in all_tracks:
            # Check if it's a camera cut track
            if isinstance(track, unreal.MovieSceneCameraCutTrack):
                camera_cut_track = track
                unreal.log("Found existing camera cut track")
                # Remove old sections
                sections = track.get_sections()
                for section in sections:
                    track.remove_section(section)
                break

        # Create new camera cut track if needed
        if not camera_cut_track:
            camera_cut_track = movie_scene.add_track(unreal.MovieSceneCameraCutTrack)
            unreal.log("Created new camera cut track")

        if camera_cut_track:
            # Create camera cut section
            camera_cut_section = camera_cut_track.add_section()

            if camera_cut_section:
                # Set the camera binding
                camera_binding_id = camera_binding.get_binding_id()
                camera_cut_section.set_camera_binding_id(camera_binding_id)

                # Set section range
                camera_cut_section.set_start_frame_bounded(True)
                camera_cut_section.set_end_frame_bounded(True)
                camera_cut_section.set_start_frame(0)
                camera_cut_section.set_end_frame(duration_frames)

                unreal.log(f"Camera cut section created (0-{duration_frames} frames)")
                unreal.log(f"Bound to camera: {self.camera_actor.get_actor_label()}")

                return camera_cut_track
            else:
                unreal.log_error("Failed to create camera cut section")
        else:
            unreal.log_error("Failed to create camera cut track")

        return None

    def _open_sequence_in_editor(self):
        """Open the sequence in the Sequencer editor"""

        if not self.sequence:
            return False

        try:
            # Open in asset editor
            asset_editor_subsystem = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
            if asset_editor_subsystem:
                asset_editor_subsystem.open_editor_for_assets([self.sequence])
                unreal.log("Sequence opened in editor")
                return True
        except Exception as e:
            unreal.log_error(f"Failed to open sequence: {e}")

        # Alternative method using LevelSequenceEditorBlueprintLibrary
        try:
            unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(self.sequence)
            unreal.log("Sequence opened via LevelSequenceEditorBlueprintLibrary")
            return True
        except Exception as e:
            unreal.log_error(f"Alternative open method also failed: {e}")

        return False

    def _lock_viewport_to_camera_cuts(self):
        """Lock the viewport to camera cuts using the API"""

        try:
            # Method 1: Direct API call (UE 5.0+)
            unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)

            # Verify the lock status
            is_locked = unreal.LevelSequenceEditorBlueprintLibrary.is_lock_camera_cut_to_viewport()

            if is_locked:
                unreal.log("Viewport locked to camera cuts via API")

                # Refresh the sequence UI to show the lock
                unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()

                return True
            else:
                unreal.log_warning("Lock command executed but viewport not locked")

        except AttributeError as e:
            # API might not be available in this version
            unreal.log_warning(f"API method not available: {e}")

            # Try alternative approaches
            try:
                # Select the camera cut track to make the lock button visible
                if self.camera_cut_track:
                    unreal.LevelSequenceEditorBlueprintLibrary.empty_selection()
                    unreal.LevelSequenceEditorBlueprintLibrary.select_tracks([self.camera_cut_track])
                    unreal.log("Camera cut track selected - lock button should be visible")

                    # Print manual instructions
                    self._print_manual_lock_instructions()
                    return False

            except Exception as e2:
                unreal.log_error(f"Alternative selection method failed: {e2}")

        except Exception as e:
            unreal.log_error(f"Failed to lock viewport: {e}")

        return False

    def _print_manual_lock_instructions(self):
        """Print instructions for manual viewport locking"""

        unreal.log("\n" + "="*70)
        unreal.log("MANUAL VIEWPORT LOCK REQUIRED")
        unreal.log("="*70)
        unreal.log("The Camera Cut Track has been created and selected.")
        unreal.log("TO LOCK VIEWPORT:")
        unreal.log("1. Look at the Camera Cuts track in Sequencer")
        unreal.log("2. Click the  Camera Lock icon on the track header")
        unreal.log("3. The viewport will switch to the camera view")
        unreal.log("ALTERNATIVE:")
        unreal.log("- Right-click Camera Cuts track → Lock Viewport")
        unreal.log("="*70)

    def _print_setup_summary(self, result):
        """Print a summary of the setup results"""

        unreal.log("\n" + "="*70)
        unreal.log("CAMERA SETUP SUMMARY")
        unreal.log("="*70)

        if result['success']:
            unreal.log("SETUP SUCCESSFUL")
            unreal.log(f"Sequence: {result['sequence'].get_name() if result['sequence'] else 'None'}")
            unreal.log(f"Camera: {self.camera_actor.get_actor_label() if self.camera_actor else 'None'}")
            unreal.log(f"Camera Cut Track: {'Created' if result['camera_cut_track'] else 'Failed'}")
            unreal.log(f"Viewport Lock: {' Locked' if result['viewport_locked'] else ' Manual lock needed'}")

            if not result['viewport_locked']:
                unreal.log("ℹ Click the camera lock icon on the Camera Cuts track")
        else:
            unreal.log("SETUP FAILED")
            unreal.log("Errors:")
            for error in result['errors']:
                unreal.log(f"- {error}")

        unreal.log("="*70)


def integrate_with_scene_builder(scene_data):
    """
    Integration function to be called from scene_builder.py
    Call this after generating the scene to properly set up camera cuts

    Args:
        scene_data: The scene data dict from scene_builder

    Returns:
        bool: Success status
    """

    # Check if we have the required data
    if not scene_data.get('sequence') or not scene_data.get('camera'):
        unreal.log_warning("[CameraIntegration] Missing sequence or camera in scene data")
        return False

    sequence_path = scene_data['sequence'].get('path')
    camera_actor = scene_data['camera']

    if not sequence_path or not camera_actor:
        unreal.log_warning("[CameraIntegration] Invalid sequence path or camera actor")
        return False

    # Create the enhanced camera setup
    camera_setup = EnhancedSequenceCamera()

    # Run the complete setup
    result = camera_setup.setup_sequence_with_camera_cuts(
        sequence_path=sequence_path,
        camera_actor=camera_actor,
        duration_frames=90  # 3 seconds at 30fps
    )

    return result['success']


# Example usage for testing
def test_camera_setup():
    """Test function to demonstrate the camera setup"""

    # Create a test camera
    camera_location = unreal.Vector(-300, 0, 180)
    test_camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CineCameraActor,
        location=camera_location
    )

    if test_camera:
        test_camera.set_actor_label("Test_CineCameraActor")

        # Setup the sequence with camera
        camera_setup = EnhancedSequenceCamera()
        result = camera_setup.setup_sequence_with_camera_cuts(
            sequence_path="/Game/TestSequences/TestCameraSequence",
            camera_actor=test_camera,
            duration_frames=90
        )

        if result['success']:
            unreal.log("\n Test completed successfully!")
            unreal.log(f"Viewport locked: {result['viewport_locked']}")
        else:
            unreal.log("\n Test failed")
            unreal.log(f"Errors: {result['errors']}")
    else:
        unreal.log_error("Failed to create test camera")


if __name__ == "__main__":
    unreal.log("\n" + "="*80)
    unreal.log("ENHANCED CAMERA CUT TRACK AND VIEWPORT LOCKING FOR UE 5.6")
    unreal.log("="*80)
    unreal.log("\nThis module provides:")
    unreal.log("1. Automatic camera cut track creation")
    unreal.log("2. Camera binding to sequences")
    unreal.log("3. Viewport locking to camera cuts")
    unreal.log("4. Integration with scene_builder.py")
    unreal.log("\nUsage:")
    unreal.log("from core.enhanced_sequence_camera import integrate_with_scene_builder")
    unreal.log("integrate_with_scene_builder(scene_data)")
    unreal.log("\nTo test:")
    unreal.log("from core.enhanced_sequence_camera import test_camera_setup")
    unreal.log("test_camera_setup()")
    unreal.log("="*80)

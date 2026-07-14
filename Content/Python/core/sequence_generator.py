# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Sequence Generator Module

Creates Unreal Engine Level Sequences from scene data. Handles camera bindings,
actor bindings, and master sequence assembly for multi-shot workflows.
"""

import unreal
from typing import Optional, List, Dict, Any


class SequenceGenerator:
    """
    Generates Level Sequences from scene data with show-specific organization.
    
    Creates individual shot sequences and can combine them into master sequences
    for playback. Sequences are organized by show in the content browser.
    
    Attributes:
        show_name: Name of the current show for sequence naming.
        sequence_dir: Content browser path for storing sequences.
    
    Example:
        >>> generator = SequenceGenerator(show_name="MyShow")
        >>> sequence = generator.create_sequence(scene_data, duration=3.0)
    """

    def __init__(self, show_name: Optional[str] = None):
        """
        Initialize the sequence generator.
        
        Args:
            show_name: Optional show name for organizing sequences.
                      Sequences will be stored in /Game/StoryboardSequences/{show_name}/.
        """
        self.show_name = show_name
        if show_name:
            self.sequence_dir = f'/Game/StoryboardSequences/{show_name}/'
        else:
            self.sequence_dir = '/Game/StoryboardSequences/'
        unreal.log(f"SequenceGenerator initialized for show: {show_name or 'No show'}")

    def create_sequence(self, scene_data: Dict[str, Any], duration: float = 3.0) -> Optional[unreal.LevelSequence]:
        """
        Create a Level Sequence for a scene.
        
        Creates or loads an existing sequence, sets up playback range,
        and binds camera and actors from the scene data.
        
        Args:
            scene_data: Dictionary containing scene information with keys:
                - panel_index: Index for sequence naming
                - camera: Optional camera actor to bind
                - actors: List of actors to bind to sequence
            duration: Sequence duration in seconds (default 3.0).
        
        Returns:
            Created or loaded LevelSequence asset, or None if creation fails.
        
        Example:
            >>> scene = {'panel_index': 1, 'camera': cam_actor, 'actors': [actor1]}
            >>> seq = generator.create_sequence(scene, duration=5.0)
        """
        if not scene_data:
            return None

        # Generate sequence name
        panel_index = scene_data.get('panel_index', 0)
        if self.show_name:
            sequence_name = f"{self.show_name}_Shot_{panel_index:03d}"
        else:
            sequence_name = f"Shot_{panel_index:03d}"
        sequence_path = f"{self.sequence_dir}{sequence_name}"

        unreal.log(f"Creating sequence: {sequence_name} for show: {self.show_name or 'No show'}")

        asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

        # Ensure directory exists
        if not asset_subsystem.does_directory_exist(self.sequence_dir):
            asset_subsystem.make_directory(self.sequence_dir)

        # Load existing or create new
        if asset_subsystem.does_asset_exist(sequence_path):
            sequence = asset_subsystem.load_asset(sequence_path)
            unreal.log(f"Loaded existing sequence: {sequence_name}")
        else:
            sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name=sequence_name,
                package_path=self.sequence_dir,
                asset_class=unreal.LevelSequence,
                factory=unreal.LevelSequenceFactoryNew()
            )

            if not sequence:
                unreal.log_error(f"Failed to create sequence: {sequence_name}")
                return None

            unreal.log(f"Created new sequence: {sequence_name}")

        # Configure movie scene
        movie_scene = sequence.get_movie_scene()
        if not movie_scene:
            unreal.log_error("Failed to get movie scene")
            return None

        # Set playback range
        fps = 30
        start_frame = 0
        end_frame = int(duration * fps)
        sequence.set_playback_start(start_frame)
        sequence.set_playback_end(end_frame)

        # Bind camera
        if scene_data.get('camera'):
            camera_binding = self.add_camera_to_sequence(sequence, scene_data['camera'], duration)

            # Optional shot-type camera move (opt-in via 'sequence.camera_moves',
            # default OFF; sequence generation is unaffected when unset)
            if camera_binding is not None:
                self._maybe_apply_camera_move(
                    sequence, camera_binding, scene_data, start_frame, end_frame
                )

        # Bind actors
        for actor in scene_data.get('actors', []):
            self.add_actor_to_sequence(sequence, actor, duration)

        # Save
        asset_subsystem.save_asset(sequence_path)

        unreal.log(f"Sequence created successfully: {sequence_name}")
        return sequence

    def add_camera_to_sequence(self, sequence: unreal.LevelSequence, camera: unreal.Actor, duration: float) -> Optional[Any]:
        """
        Add camera to sequence with camera cut track.

        Binds the camera as a possessable and creates a camera cut track
        so the sequence uses this camera for playback.

        Args:
            sequence: Target Level Sequence to add camera to.
            camera: Camera actor to bind.
            duration: Duration for the camera cut section in seconds.

        Returns:
            The camera's binding proxy on success, or None. Typed as Any
            because the proxy class name varies across UE versions
            (SequencerBindingProxy vs MovieSceneBindingProxy).
        """
        if not camera:
            return None

        # Bind camera
        camera_binding = sequence.add_possessable(camera)

        # Get movie scene
        movie_scene = sequence.get_movie_scene()
        if not movie_scene:
            unreal.log_error("Failed to get movie scene for camera cut track")
            return None

        # Add camera cuts track
        camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)

        # Configure cut section
        camera_cut_section = camera_cut_track.add_section()
        camera_cut_section.set_start_frame_bounded(True)
        camera_cut_section.set_start_frame(0)
        camera_cut_section.set_end_frame_bounded(True)
        camera_cut_section.set_end_frame(int(duration * 30))

        # Bind camera to cut track
        camera_binding_id = sequence.make_binding_id(
            camera_binding, 
            unreal.MovieSceneObjectBindingSpace.LOCAL
        )
        camera_cut_section.set_camera_binding_id(camera_binding_id)

        unreal.log("Camera added to sequence")
        return camera_binding

    def _maybe_apply_camera_move(
        self,
        sequence: unreal.LevelSequence,
        camera_binding: Any,
        scene_data: Dict[str, Any],
        start_frame: int,
        end_frame: int
    ) -> None:
        """
        Apply an optional shot-type camera move to the bound camera.

        Gated by the 'sequence.camera_moves' setting (default False, so
        behavior is unchanged unless a user opts in). Reads the shot type
        from scene_data ('shot_type' / 'shot', or nested under 'analysis')
        and delegates to core.camera_moves. Fully wrapped in try/except:
        sequence generation can never break because of a camera move.
        """
        try:
            # Feature flag, read via the settings manager with an inline
            # default (same pattern as core.external_validator.get_configured)
            try:
                from core.settings_manager import get_setting
                enabled = get_setting('sequence.camera_moves', False)
            except Exception as e:
                unreal.log(f"[CameraMoves] Settings unavailable ({e}); camera moves disabled")
                return
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in ('1', 'true', 'yes', 'on')
            if not enabled:
                return

            # Shot type: panel analysis and the UI use 'shot_type'
            # (occasionally 'shot'), sometimes nested under 'analysis'
            shot_type = scene_data.get('shot_type') or scene_data.get('shot')
            if not shot_type:
                analysis = scene_data.get('analysis')
                if isinstance(analysis, dict):
                    shot_type = analysis.get('shot_type') or analysis.get('shot')
            if not shot_type:
                unreal.log("[CameraMoves] Enabled but scene data carries no shot type; skipping")
                return

            # The camera here is a possessed live actor, so its transform
            # is readable now and passed along explicitly
            current_transform = None
            camera = scene_data.get('camera')
            if camera is not None and hasattr(camera, 'get_actor_transform'):
                try:
                    current_transform = camera.get_actor_transform()
                except Exception:
                    current_transform = None

            # First bound actor doubles as the subject for push-in scaling
            subject_location = None
            actors = scene_data.get('actors') or []
            if actors and hasattr(actors[0], 'get_actor_location'):
                try:
                    subject_location = actors[0].get_actor_location()
                except Exception:
                    subject_location = None

            from core import camera_moves
            result = camera_moves.apply_camera_move(
                sequence,
                camera_binding,
                shot_type,
                start_frame,
                end_frame,
                subject_location=subject_location,
                current_transform=current_transform
            )
            unreal.log(
                f"[CameraMoves] {result.get('status')} (shot type: {shot_type}, "
                f"move: {result.get('move')}, notes: {'; '.join(result.get('notes', []))})"
            )
        except Exception as e:
            unreal.log_warning(f"[CameraMoves] Failed, sequence unaffected: {e}")

    def add_actor_to_sequence(self, sequence: unreal.LevelSequence, actor: unreal.Actor, duration: float) -> None:
        """
        Add actor to sequence as possessable.
        
        Binds the actor to the sequence for potential animation or transform tracks.
        
        Args:
            sequence: Target Level Sequence to add actor to.
            actor: Actor to bind.
            duration: Sequence duration (reserved for future track setup).
        """
        if not actor:
            return

        sequence.add_possessable(actor)
        unreal.log(f"Actor {actor.get_name()} added to sequence")

    def create_master_sequence(
        self,
        sequences: List[unreal.LevelSequence],
        durations: Optional[List[Optional[float]]] = None
    ) -> Optional[unreal.LevelSequence]:
        """
        Create master sequence combining multiple shot sequences.

        Creates a sequence with a subsequence track containing all provided
        sequences in order. Useful for assembling multiple shots into a
        continuous playback.

        Args:
            sequences: List of Level Sequences to combine.
            durations: Optional list of per-shot durations in seconds,
                parallel to sequences (e.g. each panel's stored 'duration'
                metadata). When provided, entry i overrides the length of
                shot i in the master. Entries that are None (or a too-short
                list) fall back to that shot's own playback range, which is
                the historical behavior when durations is omitted.

        Returns:
            Master Level Sequence containing all shots, or None if creation fails.

        Example:
            >>> shots = [shot1_seq, shot2_seq, shot3_seq]
            >>> master = generator.create_master_sequence(shots, durations=[2.0, 3.5, 4.0])
        """
        if not sequences:
            unreal.log_warning("No sequences to combine")
            return None

        # Generate master name
        if self.show_name:
            master_name = f"{self.show_name}_Master_Sequence"
        else:
            master_name = "Master_Sequence"
        master_path = f"{self.sequence_dir}{master_name}"

        unreal.log(f"Creating master sequence with {len(sequences)} shots")

        asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

        # Ensure directory exists
        if not asset_subsystem.does_directory_exist(self.sequence_dir):
            asset_subsystem.make_directory(self.sequence_dir)

        # Load existing or create new
        if asset_subsystem.does_asset_exist(master_path):
            master = asset_subsystem.load_asset(master_path)
        else:
            master = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name=master_name,
                package_path=self.sequence_dir,
                asset_class=unreal.LevelSequence,
                factory=unreal.LevelSequenceFactoryNew()
            )

        if not master:
            unreal.log_error("Failed to create master sequence")
            return None

        # Get movie scene
        movie_scene = master.get_movie_scene()
        if not movie_scene:
            unreal.log_error("Failed to get movie scene from master sequence")
            return None

        # Add subsequence track
        sub_track = master.add_track(unreal.MovieSceneSubTrack)

        # Add each sequence
        fps = 30
        current_time = 0
        for index, seq in enumerate(sequences):
            if not seq:
                continue

            # Create section for this sequence
            section = sub_track.add_section()
            section.set_sequence(seq)

            # Set timing
            section.set_start_frame_bounded(True)
            section.set_start_frame(current_time)

            # Per-panel stored duration wins; fall back to the shot's own range
            duration = None
            if durations is not None and index < len(durations) and durations[index] is not None:
                duration = int(round(durations[index] * fps))
                if duration <= 0:
                    unreal.log_warning(
                        f"Ignoring non-positive duration {durations[index]} for shot {index}"
                    )
                    duration = None

            if duration is None:
                seq_movie_scene = seq.get_movie_scene()
                if seq_movie_scene:
                    duration = seq.get_playback_end() - seq.get_playback_start()
                else:
                    duration = 90  # Default 3 seconds at 30fps

            section.set_end_frame_bounded(True)
            section.set_end_frame(current_time + duration)

            current_time += duration

            unreal.log(f"Added subsequence: {seq.get_name()} ({duration} frames)")

        # Match the master's playback range to the assembled shots so
        # playback and rendering cover every subsequence exactly
        master.set_playback_start(0)
        master.set_playback_end(current_time)

        # Save master
        asset_subsystem.save_asset(master_path)

        unreal.log(f"Master sequence created: {master_name}")
        return master

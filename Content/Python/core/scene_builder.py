# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.

"""
Scene Builder Module

Builds Unreal Engine scenes from storyboard panel analysis data. Orchestrates
the complete scene generation pipeline: location loading, sequence creation,
camera setup, character/prop spawning, lighting, and positioning.

The build order follows production logic:
    1. Location/Environment setup
    2. Level Sequence creation
    3. Camera setup
    4. Character spawning
    5. Prop spawning
    6. Lighting setup
    7. Final positioning
    8. Sequence binding
"""

import unreal
from typing import Optional, Dict, Any, List
from core.error_handler import OperationErrorCollector


class SceneBuilder:
    """
    Builds 3D scenes in Unreal Engine from storyboard analysis data.
    
    Coordinates all scene generation components including asset matching,
    sequence generation, and actor spawning. All generated actors are
    spawnable within the Level Sequence (not placed in the outliner).
    
    Attributes:
        world: Reference to the editor world.
        actors: List of spawned actors.
        show_name: Name of the current show for asset lookup.
        asset_matcher: AssetMatcher instance for finding assets.
        sequence_generator: SequenceGenerator for creating sequences.
    
    Example:
        >>> builder = SceneBuilder(show_name="MyShow")
        >>> scene = builder.build_scene(analysis_data, panel_index=0)
        >>> print(f"Created {len(scene['characters'])} characters")
    """

    def __init__(self, show_name: Optional[str] = None):
        """
        Initialize the scene builder.
        
        Args:
            show_name: Optional show name for loading show-specific assets.
                      When provided, assets are matched from the show's library.
        """
        self.world = None
        self.actors: List[Any] = []
        self.show_name = show_name
        
        from core.asset_matcher import AssetMatcher
        from core.sequence_generator import SequenceGenerator
        
        self.asset_matcher = AssetMatcher(show_name=show_name)
        self.sequence_generator = SequenceGenerator(show_name=show_name)
        unreal.log(f"SceneBuilder initialized for show: {show_name or 'No show'}")

    def build_scene(self, analysis: Dict[str, Any], panel_index: int = 0, 
                    auto_camera: bool = True, auto_lighting: bool = True) -> Optional[Dict[str, Any]]:
        """
        Build a complete scene from analysis data.
        
        Main entry point for scene generation. Creates a Level Sequence with
        all actors as spawnables. Supports undo via ScopedEditorTransaction.
        
        Args:
            analysis: Panel analysis dictionary containing:
                - characters: List of character names to spawn
                - props: List of prop names to spawn
                - location: Location name to load
                - shot_type: Camera shot type ('close', 'medium', 'wide')
                - mood: Scene mood for lighting ('neutral', 'dark', 'bright')
                - time_of_day: Time setting for lighting
            panel_index: Index for sequence naming (default 0).
            auto_camera: Whether to create camera automatically (default True).
            auto_lighting: Whether to create lighting automatically (default True).
        
        Returns:
            Scene data dictionary containing:
                - panel_index: The panel index
                - location: Location configuration
                - sequence: Sequence asset and metadata
                - actors: All spawned actor configs
                - characters: Character configs
                - props: Prop configs
                - lights: Light configs
                - camera: Camera config
                - positioning: Positioning metadata
            Returns None if scene creation fails.
        
        Example:
            >>> analysis = {'characters': ['Hero'], 'shot_type': 'medium'}
            >>> scene = builder.build_scene(analysis, panel_index=1)
        """
        from core.entity_validator import validate_actors

        # Validate AI-suggested characters against available assets
        available_actors = []
        if self.show_name and hasattr(self.asset_matcher, 'show_library'):
            lib_dict = self.asset_matcher.show_library.get('characters', {})
            available_actors = list(lib_dict.keys())
            unreal.log(f"Found {len(available_actors)} available actors: {available_actors}")
        else:
            unreal.log_warning(f"Cannot validate - show_name: {self.show_name}")

        ai_characters = analysis.get('characters', [])
        if available_actors and ai_characters:
            unreal.log(f"Validating {len(ai_characters)} AI suggestions: {ai_characters}")
            validated_characters = validate_actors(ai_characters, available_actors)
            analysis['characters'] = validated_characters

            rejected = set(ai_characters) - set(validated_characters)
            if rejected:
                unreal.log_error(f"BLOCKED HALLUCINATIONS: {rejected}")
            else:
                unreal.log(f"All {len(validated_characters)} characters validated")
        
        with unreal.ScopedEditorTransaction(f"Generate Panel {panel_index}") as trans:
            unreal.log(f"Starting build_scene with panel_index={panel_index}")

            self.world = unreal.EditorLevelLibrary.get_editor_world()
            if not self.world:
                unreal.log_error("No editor world found")
                trans.cancel()
                return None

            unreal.log("SCENE BUILDER: Starting production-ordered generation")
            unreal.log("Order: Location -> Sequence -> Camera -> Characters -> Props -> Lighting -> Positioning")

            scene_data = {
                'panel_index': panel_index,
                'location': None,
                'sequence': None,
                'actors': [],
                'characters': [],
                'props': [],
                'lights': [],
                'camera': None,
                'positioning': {}
            }

            try:
                # STEP 1: Location/Environment
                location_name = analysis.get('location') or analysis.get('location_type', 'Default')
                if location_name in ['Exterior', 'Interior', 'Auto-detect']:
                    location_name = 'Default'
                    
                unreal.log(f"Resolved location: {location_name}")
                scene_data['location'] = self._setup_location(location_name, analysis)

                # STEP 2: Sequence
                scene_data['sequence'] = self._create_sequence(panel_index, analysis)
                if not scene_data['sequence'].get('asset'):
                    unreal.log_error("Failed to create sequence - canceling")
                    trans.cancel()
                    return None

                # STEP 3: Camera
                if auto_camera:
                    scene_data['camera'] = self._setup_initial_camera(analysis)

                # STEP 4: Characters
                scene_data['characters'] = self._spawn_characters(analysis)
                scene_data['actors'].extend(scene_data['characters'])

                # STEP 5: Props
                scene_data['props'] = self._spawn_props(analysis)
                scene_data['actors'].extend(scene_data['props'])

                # STEP 6: Lighting
                if auto_lighting:
                    scene_data['lights'] = self._setup_lighting(analysis, scene_data['location'])

                # STEP 7: Positioning
                scene_data['positioning'] = self._position_actors(scene_data, analysis)
                if scene_data['camera']:
                    self._adjust_camera_framing(scene_data['camera'], scene_data)

                # STEP 8: Add to sequence
                if scene_data['sequence'].get('asset'):
                    self._add_actors_to_sequence(scene_data)

                # Summary
                unreal.log(f"\nScene generation complete!")
                unreal.log(f"Location: {scene_data['location'].get('type', 'Default')}")
                unreal.log(f"Characters: {len(scene_data['characters'])}")
                unreal.log(f"Props: {len(scene_data['props'])}")
                unreal.log(f"Lights: {len(scene_data['lights'])}")
                
                return scene_data

            except Exception as e:
                unreal.log_error(f"Critical error in scene building: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())
                trans.cancel()
                return None

    def _setup_location(self, location_name: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load location level from asset library.
        
        Args:
            location_name: Name of location to load.
            analysis: Panel analysis for context.
        
        Returns:
            Location data dict with 'name', 'type', 'loaded' status.
        """
        location_data = {'name': location_name, 'type': location_name}

        self.clear_build_area()

        if self.show_name and location_name not in ['Location Unknown', 'Auto-detect', 'Unknown', 'Default']:
            unreal.log(f"Looking for location '{location_name}' in show '{self.show_name}'...")

            try:
                from core.utils import get_shows_manager
                import json

                shows_manager = get_shows_manager()
                library_path = shows_manager.shows_root / self.show_name / 'asset_library.json'

                if library_path.exists():
                    with open(library_path, 'r') as f:
                        library = json.load(f)

                    locations = library.get('locations', {})
                    if location_name in locations:
                        location_info = locations[location_name]
                        location_path = location_info.get('asset_path', '')

                        if location_path:
                            unreal.log(f"Loading level: {location_path}")
                            location_data['level_path'] = location_path
                            location_data['found'] = True
                            
                            success = unreal.EditorLevelLibrary.load_level(location_path)
                            location_data['loaded'] = success
                            
                            if success:
                                unreal.log(f"Level loaded: {location_name}")
                                import time
                                time.sleep(0.5)
                            else:
                                unreal.log_error(f"Failed to load level: {location_path}")

                        return location_data
                    else:
                        unreal.log_warning(f"Location '{location_name}' not in library")
                        unreal.log_warning(f"Available: {list(locations.keys())}")
                        
            except Exception as e:
                unreal.log_error(f"Error accessing asset library: {e}")

        return location_data

    def _create_sequence(self, panel_index: int, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create Level Sequence for the scene.
        
        Args:
            panel_index: Panel index for naming.
            analysis: Panel analysis for context.
        
        Returns:
            Sequence data dict with 'asset', 'path', 'name'.
        """
        sequence_data = {}

        try:
            sequence_name = f"Panel_{panel_index:03d}_Sequence"
            unreal.log(f"Creating sequence: {sequence_name}")

            sequence_path = f"/Game/StoryboardSequences"
            if self.show_name:
                sequence_path = f"/Game/StoryboardSequences/{self.show_name}"

            if not unreal.EditorAssetLibrary.does_directory_exist(sequence_path):
                unreal.EditorAssetLibrary.make_directory(sequence_path)

            full_path = f"{sequence_path}/{sequence_name}"

            if unreal.EditorAssetLibrary.does_asset_exist(full_path):
                sequence = unreal.EditorAssetLibrary.load_asset(full_path)
                unreal.log(f"Using existing sequence: {sequence_name}")
            else:
                factory = unreal.LevelSequenceFactoryNew()
                sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                    sequence_name, sequence_path, unreal.LevelSequence, factory
                )

                if sequence:
                    sequence.set_display_rate(unreal.FrameRate(30, 1))
                    sequence.set_playback_start(0)
                    sequence.set_playback_end(90)
                    unreal.log(f"Created sequence: {sequence_name}")
                else:
                    unreal.log_error("Failed to create sequence!")
                    return sequence_data

            sequence_data['asset'] = sequence
            sequence_data['path'] = full_path
            sequence_data['name'] = sequence_name

            self.last_sequence_path = full_path
            self.sequence_path = full_path

        except Exception as e:
            unreal.log_error(f"Exception in sequence creation: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

        return sequence_data

    def _spawn_characters(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Prepare character spawn configurations.
        
        Characters are not spawned directly but configured for spawnable
        creation within the Level Sequence.
        
        Args:
            analysis: Panel analysis containing 'characters' list.
        
        Returns:
            List of character config dicts with 'type', 'name', 'position', etc.
        """
        character_configs = []
        character_names = analysis.get('characters', [])
        error_collector = OperationErrorCollector("Character Spawning")

        if not character_names:
            unreal.log("No characters to spawn")
            return character_configs

        asset_paths = self._get_asset_paths_from_library()
        location_type = analysis.get('location_type', 'outdoor')
        props_list = analysis.get('props', [])
        num_chars = len(character_names)

        unreal.log(f"Positioning {num_chars} character(s) for {location_type} scene")

        for i, char_name in enumerate(character_names):
            try:
                unreal.log(f"Preparing character config: {char_name}")

                char_path = self._find_asset_path(char_name, asset_paths, 'characters')
                position = self._calculate_character_position(i, num_chars, location_type, props_list)
                
                unreal.log(f"Position: X={position.x:.0f}, Y={position.y:.0f}, Z={position.z:.0f}")

                if char_path:
                    if not unreal.EditorAssetLibrary.does_asset_exist(char_path):
                        error_collector.add_error(char_name, f"Asset does not exist: {char_path}")
                        character_configs.append(self._create_placeholder_config(char_name, position))
                        continue

                    character_configs.append({
                        'type': 'spawnable',
                        'asset_path': char_path,
                        'name': char_name,
                        'position': position,
                        'rotation': unreal.Rotator(pitch=0, yaw=0, roll=0),
                        'is_placeholder': False
                    })
                    unreal.log(f"Config created: {char_name}")
                else:
                    error_collector.add_warning(char_name, "Not found in asset library")
                    character_configs.append(self._create_placeholder_config(char_name, position))

            except Exception as e:
                error_collector.add_error(char_name, str(e))
                character_configs.append(self._create_placeholder_config(
                    char_name, unreal.Vector(0, len(character_configs) * 100, 0)
                ))

        error_collector.log_summary()
        return character_configs

    def _spawn_props(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Prepare prop spawn configurations.
        
        Props are configured for spawnable creation within the Level Sequence.
        
        Args:
            analysis: Panel analysis containing 'props' or 'objects' list.
        
        Returns:
            List of prop config dicts with 'type', 'name', 'position', etc.
        """
        prop_configs = []
        prop_names = analysis.get('props', []) or analysis.get('objects', [])
        error_collector = OperationErrorCollector("Prop Spawning")

        if not prop_names:
            unreal.log("No props to spawn")
            return prop_configs

        asset_paths = self._get_asset_paths_from_library()

        for i, prop_name in enumerate(prop_names):
            try:
                unreal.log(f"Preparing prop config: {prop_name}")

                prop_path = self._find_asset_path(prop_name, asset_paths, 'props')
                position = unreal.Vector(0, 0, 0)  # AI positioning handles placement

                if prop_path:
                    if not unreal.EditorAssetLibrary.does_asset_exist(prop_path):
                        error_collector.add_error(prop_name, f"Asset does not exist: {prop_path}")
                        prop_configs.append(self._create_placeholder_config(prop_name, position))
                        continue

                    prop_configs.append({
                        'type': 'spawnable',
                        'asset_path': prop_path,
                        'name': prop_name,
                        'position': position,
                        'is_placeholder': False
                    })
                    unreal.log(f"Config created: {prop_name}")
                else:
                    error_collector.add_warning(prop_name, "Not found in asset library")
                    prop_configs.append(self._create_placeholder_config(prop_name, position))

            except Exception as e:
                error_collector.add_error(prop_name, str(e))
                prop_configs.append(self._create_placeholder_config(prop_name, unreal.Vector(0, 0, 0)))

        error_collector.log_summary()
        return prop_configs

    def _setup_lighting(self, analysis: Dict[str, Any], location_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create lighting configuration for the scene.
        
        Sets up three-point lighting (key, fill, rim) with intensity
        based on mood analysis.
        
        Args:
            analysis: Panel analysis containing 'mood' and 'time_of_day'.
            location_data: Location info for context.
        
        Returns:
            List of light config dicts for spawnable creation.
        """
        light_configs = []
        mood = analysis.get('mood', 'neutral')

        # Base intensity adjusted by mood
        base_intensity = 2.0
        if mood == 'dark':
            base_intensity = 1.0
        elif mood == 'bright':
            base_intensity = 3.0

        # Three-point lighting setup
        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Key Light',
            'position': unreal.Vector(-300, -200, 400),
            'intensity': base_intensity * 1000,
            'color': unreal.LinearColor(r=1.0, g=1.0, b=1.0)
        })

        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Fill Light',
            'position': unreal.Vector(-300, 200, 350),
            'intensity': base_intensity * 500,
            'color': unreal.LinearColor(r=1.0, g=1.0, b=1.0)
        })

        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Rim Light',
            'position': unreal.Vector(400, 0, 300),
            'intensity': base_intensity * 300,
            'color': unreal.LinearColor(r=1.0, g=1.0, b=1.0)
        })

        unreal.log(f"Prepared {len(light_configs)} light configs")
        return light_configs

    def _setup_initial_camera(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create camera configuration based on shot type.
        
        Args:
            analysis: Panel analysis containing 'shot_type'.
        
        Returns:
            Camera config dict for spawnable creation.
        """
        shot_type = analysis.get('shot_type', 'medium')

        distance_map = {
            'close': 150,
            'medium': 300,
            'wide': 600,
            'extreme_wide': 1000
        }

        distance = distance_map.get(shot_type, 300)
        camera_pos = unreal.Vector(-distance, 0, 180)

        focal_length = 50.0
        if 'close' in shot_type:
            focal_length = 85.0
        elif 'wide' in shot_type:
            focal_length = 24.0

        camera_config = {
            'type': 'spawnable',
            'class': unreal.CineCameraActor,
            'position': camera_pos,
            'rotation': unreal.Rotator(0, 0, 0),
            'label': f"Hero_StoryboardCamera_Shot_{shot_type}",
            'shot_type': shot_type,
            'focal_length': focal_length
        }

        unreal.log(f"Camera config prepared for {shot_type} shot")
        return camera_config

    def _position_actors(self, scene_data: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict]:
        """
        Handle final actor positioning.
        
        Positioning is pre-calculated in spawn configs; this step is a placeholder
        for future refinement logic.
        
        Args:
            scene_data: Current scene data.
            analysis: Panel analysis for context.
        
        Returns:
            Empty list (positioning handled in configs).
        """
        unreal.log("Positioning handled by spawnable configs")
        return []

    def _adjust_camera_framing(self, camera: Dict[str, Any], scene_data: Dict[str, Any]) -> None:
        """
        Adjust camera framing for scene.
        
        Camera framing is applied when spawned in sequence.
        
        Args:
            camera: Camera config dict.
            scene_data: Scene data for context.
        """
        unreal.log("Camera framing will be set when spawned in sequence")

    def clear_build_area(self) -> None:
        """
        Clear previously generated storyboard actors from the level.
        
        Removes all actors tagged with 'StoryboardGenerated'.
        """
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        cleared_count = 0

        for actor in all_actors:
            if actor and hasattr(actor, 'tags'):
                if 'StoryboardGenerated' in actor.tags:
                    unreal.EditorLevelLibrary.destroy_actor(actor)
                    cleared_count += 1

        if cleared_count > 0:
            unreal.log(f"Cleared {cleared_count} previous storyboard actors")

    def _calculate_character_position(self, char_index: int, num_chars: int, 
                                       location_type: str, props_list: List[str]) -> unreal.Vector:
        """
        Calculate initial character position.
        
        All characters start at origin; AI positioning workflow handles
        final placement based on storyboard analysis.
        
        Args:
            char_index: Index of character (0-based).
            num_chars: Total number of characters.
            location_type: Type of location scene.
            props_list: List of props in scene.
        
        Returns:
            Vector at origin (0, 0, 0).
        """
        return unreal.Vector(x=0.0, y=0.0, z=0.0)

    def _get_asset_paths_from_library(self) -> Optional[Dict[str, Any]]:
        """
        Load asset paths from show's asset library.
        
        Returns:
            Asset library dict or None if unavailable.
        """
        if not self.show_name:
            return None

        try:
            from core.utils import get_shows_manager
            import json

            shows_manager = get_shows_manager()
            library_path = shows_manager.shows_root / self.show_name / 'asset_library.json'

            if library_path.exists():
                with open(library_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            unreal.log_error(f"Failed to load asset library: {e}")

        return None

    def _find_asset_path(self, name: str, asset_paths: Optional[Dict], category: str) -> Optional[str]:
        """
        Find asset path by name in library.
        
        Args:
            name: Asset name to find.
            asset_paths: Loaded asset library.
            category: Category to search ('characters', 'props').
        
        Returns:
            Asset path string or None.
        """
        if not asset_paths or category not in asset_paths:
            return None

        # Exact match
        if name in asset_paths[category]:
            return asset_paths[category][name].get('asset_path', '')

        # Partial match
        for lib_name, info in asset_paths[category].items():
            if name.lower() in lib_name.lower() or lib_name.lower() in name.lower():
                unreal.log(f"Found partial match '{lib_name}'")
                return info.get('asset_path', '')

        return None

    def _create_placeholder_config(self, name: str, position: unreal.Vector) -> Dict[str, Any]:
        """
        Create placeholder config for missing assets.
        
        Args:
            name: Name of the missing asset.
            position: Spawn position.
        
        Returns:
            Placeholder config dict.
        """
        return {
            'type': 'spawnable_placeholder',
            'name': name,
            'position': position,
            'is_placeholder': True
        }

    def _create_spawnable_from_config(self, sequence: unreal.LevelSequence, 
                                       config: Dict[str, Any], actor_type: str) -> Optional[Any]:
        """
        Create spawnable actor in sequence from config.
        
        Args:
            sequence: Target Level Sequence.
            config: Actor configuration dict.
            actor_type: Type hint ('character' or 'prop').
        
        Returns:
            Spawnable binding or None on failure.
        """
        try:
            name = config.get('name', 'Actor')
            position = config.get('position', unreal.Vector(0, 0, 0))
            rotation = config.get('rotation', unreal.Rotator(0, 0, 0))
            is_placeholder = config.get('is_placeholder', False)

            if is_placeholder:
                unreal.log(f"Creating placeholder spawnable: {name}")
                spawnable = sequence.add_spawnable_from_class(unreal.StaticMeshActor)
                if spawnable:
                    object_template = spawnable.get_object_template()
                    if object_template:
                        static_mesh_component = object_template.static_mesh_component
                        if static_mesh_component:
                            cube = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube')
                            if cube:
                                static_mesh_component.set_static_mesh(cube)
                        object_template.set_actor_scale3d(unreal.Vector(0.5, 0.5, 2.0))

                    spawnable.set_display_name(f"{name}_Placeholder")
                    self._set_spawnable_transform(spawnable, position, rotation)
                    return spawnable
            else:
                asset_path = config.get('asset_path', '')
                if not asset_path:
                    unreal.log_error(f"No asset path for {name}")
                    return None

                if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
                    unreal.log_error(f"Asset doesn't exist: {asset_path}")
                    return None

                asset = unreal.EditorAssetLibrary.load_asset(asset_path)
                if not asset:
                    unreal.log_error(f"Failed to load asset: {asset_path}")
                    return None

                spawnable = None

                # Try as blueprint
                if 'BP_' in asset_path or 'blueprint' in asset_path.lower():
                    try:
                        blueprint_class = unreal.EditorAssetLibrary.load_blueprint_class(asset_path)
                        if blueprint_class:
                            spawnable = sequence.add_spawnable_from_class(blueprint_class)
                    except:
                        pass

                # Try as instance
                if not spawnable:
                    try:
                        spawnable = sequence.add_spawnable_from_instance(asset)
                    except:
                        pass

                if spawnable:
                    spawnable.set_display_name(name)
                    self._set_spawnable_transform(spawnable, position, rotation)
                    return spawnable
                else:
                    unreal.log_error(f"Failed to create spawnable for: {name}")
                    return None

        except Exception as e:
            unreal.log_error(f"Error creating spawnable: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return None

    def _set_spawnable_transform(self, spawnable: Any, position: unreal.Vector, 
                                  rotation: unreal.Rotator) -> None:
        """
        Set transform keyframes for a spawnable actor.
        
        Args:
            spawnable: Spawnable binding to configure.
            position: Initial position.
            rotation: Initial rotation.
        """
        try:
            transform_track = spawnable.add_track(unreal.MovieScene3DTransformTrack)
            if transform_track:
                transform_section = transform_track.add_section()
                if transform_section:
                    transform_section.set_start_frame_bounded(True)
                    transform_section.set_end_frame_bounded(True)
                    transform_section.set_start_frame(0)
                    transform_section.set_end_frame(90)

                    channels = transform_section.get_all_channels()
                    if len(channels) >= 6:
                        channels[0].add_key(unreal.FrameNumber(0), position.x)
                        channels[1].add_key(unreal.FrameNumber(0), position.y)
                        channels[2].add_key(unreal.FrameNumber(0), position.z)
                        channels[3].add_key(unreal.FrameNumber(0), rotation.roll)
                        channels[4].add_key(unreal.FrameNumber(0), rotation.pitch)
                        channels[5].add_key(unreal.FrameNumber(0), rotation.yaw)
        except Exception as e:
            unreal.log_error(f"Failed to set spawnable transform: {e}")

    def _create_spawnable_actor(self, sequence: unreal.LevelSequence, 
                                 config: Dict[str, Any]) -> Optional[Any]:
        """
        Create spawnable actor (camera or light) in sequence.
        
        Args:
            sequence: Target Level Sequence.
            config: Actor configuration with 'class', 'position', etc.
        
        Returns:
            Spawnable binding or None on failure.
        """
        try:
            actor_class = config['class']
            spawnable = sequence.add_spawnable_from_class(actor_class)
            
            if not spawnable:
                unreal.log_error(f"Failed to create spawnable for {config.get('name', 'actor')}")
                return None

            object_template = spawnable.get_object_template()
            if not object_template:
                unreal.log_error("Failed to get object template")
                return None

            # Set transform
            transform_track = spawnable.add_track(unreal.MovieScene3DTransformTrack)
            if transform_track:
                transform_section = transform_track.add_section()
                if transform_section:
                    transform_section.set_start_frame_bounded(True)
                    transform_section.set_end_frame_bounded(True)
                    transform_section.set_start_frame(0)
                    transform_section.set_end_frame(90)

                    position = config.get('position', unreal.Vector(0, 0, 0))
                    rotation = config.get('rotation', unreal.Rotator(0, 0, 0))

                    channels = transform_section.get_all_channels()
                    if len(channels) >= 6:
                        channels[0].add_key(unreal.FrameNumber(0), position.x)
                        channels[1].add_key(unreal.FrameNumber(0), position.y)
                        channels[2].add_key(unreal.FrameNumber(0), position.z)
                        channels[3].add_key(unreal.FrameNumber(0), rotation.roll)
                        channels[4].add_key(unreal.FrameNumber(0), rotation.pitch)
                        channels[5].add_key(unreal.FrameNumber(0), rotation.yaw)

            # Configure by type
            if actor_class == unreal.CineCameraActor:
                camera_component = object_template.get_cine_camera_component()
                if camera_component:
                    camera_component.filmback.sensor_width = 36.0
                    camera_component.filmback.sensor_height = 24.0
                    camera_component.current_focal_length = config.get('focal_length', 50.0)
                    camera_component.current_aperture = 2.8

                    focus_settings = camera_component.focus_settings
                    focus_settings.focus_method = unreal.CameraFocusMethod.DISABLE
                    camera_component.set_editor_property('focus_settings', focus_settings)

                    post_process = camera_component.post_process_settings
                    post_process.override_depth_of_field_fstop = True
                    post_process.depth_of_field_fstop = 32.0
                    post_process.override_depth_of_field_focal_distance = True
                    post_process.depth_of_field_focal_distance = 100000.0
                    camera_component.set_editor_property('post_process_settings', post_process)

                spawnable.set_display_name(config.get('label', 'Camera'))

            elif actor_class == unreal.PointLight:
                light_component = object_template.point_light_component
                if light_component:
                    light_component.set_intensity(config.get('intensity', 5000.0))
                    light_component.set_light_color(config.get('color', unreal.LinearColor(1.0, 1.0, 1.0)))

                spawnable.set_display_name(config.get('name', 'Light'))

            return spawnable

        except Exception as e:
            unreal.log_error(f"Error creating spawnable: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return None

    def _add_actors_to_sequence(self, scene_data: Dict[str, Any]) -> None:
        """
        Add all actors to the sequence as spawnables.
        
        Creates camera, lights, characters, and props as spawnable actors
        within the Level Sequence.
        
        Args:
            scene_data: Complete scene data with all configs.
        """
        sequence = scene_data['sequence'].get('asset')
        sequence_path = scene_data['sequence'].get('path')

        if not sequence:
            unreal.log_error("No sequence asset found!")
            return

        unreal.log(f"Opening sequence: {sequence_path}")
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
        unreal.log("\nADDING ACTORS TO SEQUENCE")

        try:
            movie_scene = sequence.get_movie_scene()
            if not movie_scene:
                unreal.log_warning("No movie scene found")
                return

            spawned_camera = None
            spawned_lights = []
            spawned_characters = []
            spawned_props = []

            # Camera
            camera_config = scene_data.get('camera')
            if camera_config and isinstance(camera_config, dict) and camera_config.get('type') == 'spawnable':
                unreal.log("Creating spawnable camera...")
                spawned_camera = self._create_spawnable_actor(sequence, camera_config)

            # Lights
            for light_config in scene_data.get('lights', []):
                if isinstance(light_config, dict) and light_config.get('type') == 'spawnable':
                    spawned_light = self._create_spawnable_actor(sequence, light_config)
                    if spawned_light:
                        spawned_lights.append(spawned_light)

            # Characters
            for char_config in scene_data.get('characters', []):
                if isinstance(char_config, dict):
                    spawned = self._create_spawnable_from_config(sequence, char_config, 'character')
                    if spawned:
                        spawned_characters.append(spawned)

            # Props
            for prop_config in scene_data.get('props', []):
                if isinstance(prop_config, dict):
                    spawned = self._create_spawnable_from_config(sequence, prop_config, 'prop')
                    if spawned:
                        spawned_props.append(spawned)

            # Camera cuts
            if spawned_camera:
                self._setup_camera_cuts_spawnable(movie_scene, spawned_camera, sequence)

            unreal.log(f"Sequence complete!")
            unreal.log(f"Camera: {'Yes' if spawned_camera else 'No'}")
            unreal.log(f"Lights: {len(spawned_lights)}")
            unreal.log(f"Characters: {len(spawned_characters)}")
            unreal.log(f"Props: {len(spawned_props)}")

        except Exception as e:
            unreal.log_error(f"Error adding actors: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

        # Save
        try:
            unreal.EditorAssetLibrary.save_asset(sequence_path)
            unreal.log(f"Sequence saved: {sequence_path}")
        except Exception as e:
            unreal.log_error(f"Failed to save sequence: {e}")

    def _setup_camera_cuts_spawnable(self, movie_scene: Any, camera_spawnable: Any, 
                                      sequence: unreal.LevelSequence) -> None:
        """
        Setup camera cuts track for spawnable camera.
        
        Args:
            movie_scene: MovieScene object.
            camera_spawnable: Camera spawnable binding.
            sequence: Parent Level Sequence.
        """
        try:
            unreal.log("Setting up Camera Cuts Track...")

            existing_tracks = sequence.find_tracks_by_type(unreal.MovieSceneCameraCutTrack)

            if existing_tracks and len(existing_tracks) > 0:
                camera_cut_track = existing_tracks[0]
            else:
                camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)

            if not camera_cut_track:
                unreal.log_error("Failed to create camera cut track!")
                return

            # Clear existing sections
            sections = camera_cut_track.get_sections()
            if sections:
                for section in sections:
                    camera_cut_track.remove_section(section)

            camera_cut_section = camera_cut_track.add_section()
            if not camera_cut_section:
                unreal.log_error("Failed to create camera cut section!")
                return

            binding_id = unreal.MovieSceneSequenceExtensions.get_binding_id(
                sequence, camera_spawnable
            )

            camera_cut_section.set_camera_binding_id(binding_id)
            camera_cut_section.set_range(0, 90)
            camera_cut_section.set_start_frame_bounded(True)
            camera_cut_section.set_end_frame_bounded(True)

            unreal.log("Camera cuts track configured")

        except Exception as e:
            unreal.log_error(f"Failed to setup camera cuts: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

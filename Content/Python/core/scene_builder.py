# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

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

import re

import unreal
from typing import Optional, Dict, Any, List, Tuple
from core.error_handler import OperationErrorCollector


def _trace_ground_z_editor(x, y, z_hint):
    """Ground Z at (x, y) via a downward line trace in the open editor
    world, or None. Failures are LOGGED (a silent trace failure is how
    stage anchors ended up with estimated, floating Z values). All
    world/hit references are locals that die on return."""
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = ues.get_editor_world() if ues else None
        if world is None:
            unreal.log("[GroundTrace] No editor world available")
            return None
        hit = unreal.SystemLibrary.line_trace_single(
            world,
            unreal.Vector(float(x), float(y), float(z_hint) + 2000.0),
            unreal.Vector(float(x), float(y), float(z_hint) - 5000.0),
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
            False, [], unreal.DrawDebugTrace.NONE, True)
        if not hit:
            unreal.log(f"[GroundTrace] No hit below ({x:.0f}, {y:.0f})")
            return None
        try:
            return float(unreal.GameplayStatics.break_hit_result(hit)[4].z)
        except Exception:
            try:
                return float(hit.to_tuple()[4].z)
            except Exception as parse_err:
                unreal.log_warning(f"[GroundTrace] Hit result parse failed: {parse_err}")
                return None
    except Exception as e:
        unreal.log_warning(f"[GroundTrace] Trace failed: {e}")
        return None


def _attached_prop_matches(prop_name: str, attached_name: str) -> bool:
    """Case-insensitive exact or word-boundary substring match, mirroring
    the library matcher's exact-then-partial semantics."""
    prop_lower = prop_name.strip().lower()
    attached_lower = attached_name.strip().lower()
    if not prop_lower or not attached_lower:
        return False
    if prop_lower == attached_lower:
        return True
    return bool(
        re.search(r'\b' + re.escape(attached_lower) + r'\b', prop_lower) or
        re.search(r'\b' + re.escape(prop_lower) + r'\b', attached_lower)
    )


def filter_attached_props(props: List[Any], resolved_characters: List[Any],
                          library: Optional[Dict[str, Any]]) -> List[Any]:
    """Drop detected props that are already part of a spawned character.

    Character entries in asset_library.json may carry an optional
    'attached_props' list (e.g. the Farmer skeletal mesh already holds a
    scythe). Any detected prop matching such an entry - for a character
    actually being spawned - must not spawn as a standalone prop, be
    placeholder-cubed, or trigger a gen3d rescue.

    Pure function (no editor state) so it is directly testable outside
    Unreal. Entries without 'attached_props' change nothing.

    Args:
        props: Detected prop names for the scene.
        resolved_characters: Character names being spawned (canonical
            library keys or aliases).
        library: Loaded asset library dict (expects a 'characters' map).

    Returns:
        New list with attached props removed; order preserved.
    """
    props = list(props or [])
    if not props or not resolved_characters or not isinstance(library, dict):
        return props

    char_lib = library.get('characters', {})
    if not isinstance(char_lib, dict):
        return props

    # Resolve each spawned character to its library entry (exact key,
    # case-insensitive key, or alias - same lookup order as the matcher)
    # and collect (character_name, attached_prop_name) pairs.
    attached_pairs = []
    for char_name in resolved_characters:
        if not isinstance(char_name, str):
            continue
        entry = char_lib.get(char_name)
        lib_key = char_name
        if not isinstance(entry, dict):
            char_lower = char_name.strip().lower()
            entry = None
            for key, info in char_lib.items():
                if not isinstance(info, dict):
                    continue
                aliases = info.get('aliases', [])
                if isinstance(aliases, str):
                    aliases = [a.strip() for a in aliases.split(',') if a.strip()]
                alias_lowers = [a.strip().lower() for a in aliases
                                if isinstance(a, str)]
                if key.strip().lower() == char_lower or char_lower in alias_lowers:
                    entry = info
                    lib_key = key
                    break
        if not isinstance(entry, dict):
            continue
        attached = entry.get('attached_props', [])
        if isinstance(attached, str):
            attached = [a.strip() for a in attached.split(',') if a.strip()]
        if not isinstance(attached, (list, tuple)):
            continue
        for attached_name in attached:
            if isinstance(attached_name, str) and attached_name.strip():
                attached_pairs.append((lib_key, attached_name))

    if not attached_pairs:
        return props

    kept = []
    for prop in props:
        owner = None
        if isinstance(prop, str):
            for char_key, attached_name in attached_pairs:
                if _attached_prop_matches(prop, attached_name):
                    owner = char_key
                    break
        if owner is not None:
            unreal.log(f"Prop '{prop}' is attached to character '{owner}' "
                       f"- skipping standalone spawn")
        else:
            kept.append(prop)
    return kept


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
        # (config, spawnable) pairs from the latest _add_actors_to_sequence
        # run; consumed by the optional auto-animation step.
        self._last_spawned_character_pairs: List[Any] = []
        
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
        # (library keys PLUS each entry's aliases, mapped back to keys).
        available_actors = []
        alias_to_key = {}
        if self.show_name and hasattr(self.asset_matcher, 'show_library'):
            lib_dict = self.asset_matcher.show_library.get('characters', {})
            available_actors = list(lib_dict.keys())
            for lib_key, lib_info in lib_dict.items():
                aliases = lib_info.get('aliases', []) if isinstance(lib_info, dict) else []
                if isinstance(aliases, str):
                    aliases = [a.strip() for a in aliases.split(',') if a.strip()]
                for alias in aliases:
                    if isinstance(alias, str) and alias.strip():
                        alias_clean = alias.strip()
                        alias_to_key[alias_clean.lower()] = lib_key
                        available_actors.append(alias_clean)
            unreal.log(f"Found {len(lib_dict)} available actors "
                       f"(+{len(alias_to_key)} aliases): {list(lib_dict.keys())}")
        else:
            unreal.log_warning(f"Cannot validate - show_name: {self.show_name}")

        ai_characters = analysis.get('characters', [])
        if available_actors and ai_characters:
            unreal.log(f"Validating {len(ai_characters)} AI suggestions: {ai_characters}")
            validated_characters = validate_actors(ai_characters, available_actors)

            rejected = set(ai_characters) - set(validated_characters)
            if rejected:
                # Gen3D rescue (opt-in, 'gen3d.enabled'): an entity missing from
                # the library is not necessarily a hallucination. Runs before the
                # transaction opens because generation can block for minutes.
                rescued = self._gen3d_rescue(sorted(rejected), analysis)
                if rescued:
                    validated_characters = list(validated_characters) + rescued
                    rejected -= set(rescued)
            # Map alias matches back to their canonical library keys
            # (deduplicated) so downstream spawning uses real entry names.
            canonical_characters = []
            for validated_name in validated_characters:
                canonical = alias_to_key.get(str(validated_name).lower(), validated_name)
                if canonical not in canonical_characters:
                    canonical_characters.append(canonical)
            validated_characters = canonical_characters
            analysis['characters'] = validated_characters

            if rejected:
                unreal.log_error(f"BLOCKED HALLUCINATIONS: {rejected}")
            else:
                unreal.log(f"All {len(validated_characters)} characters validated")

        # Drop props that are already attached to a spawned character
        # (e.g. the Farmer mesh holds its own scythe). MUST run before the
        # gen3d prop rescue below and before _spawn_props: an attached
        # prop must never be generated, matched, or placeholder-cubed.
        try:
            filter_library = self._get_asset_paths_from_library()
            resolved_chars = analysis.get('characters', [])
            if analysis.get('props'):
                analysis['props'] = filter_attached_props(
                    analysis['props'], resolved_chars, filter_library)
            # _spawn_props falls back to 'objects' when 'props' is empty
            if analysis.get('objects'):
                analysis['objects'] = filter_attached_props(
                    analysis['objects'], resolved_chars, filter_library)
        except Exception as e:
            unreal.log_warning(f"Attached-prop filter failed: {e}")

        # Props get the same gen3d rescue: a prop with no library match
        # would otherwise silently spawn as a placeholder cube. Runs
        # before the transaction because generation can block for minutes.
        ai_props = analysis.get('props', [])
        if ai_props and self.show_name and hasattr(self.asset_matcher, 'show_library'):
            try:
                prop_lib = {'props': self.asset_matcher.show_library.get('props', {})}
                missing_props = [p for p in ai_props if isinstance(p, str)
                                 and not self._find_asset_path(p, prop_lib, 'props')]
                if missing_props:
                    rescued_props = self._gen3d_rescue(missing_props, analysis,
                                                       category='props')
                    if rescued_props:
                        unreal.log(f"[Gen3D] props rescued: {rescued_props}")
            except Exception as e:
                unreal.log_warning(f"[Gen3D] prop rescue check failed: {e}")

        # STEP 1: Location/Environment. Runs BEFORE the transaction opens:
        # loading a level resets the undo buffer, and doing that inside an
        # open ScopedEditorTransaction leaves the transaction dead and can
        # crash/corrupt editor state on a later Ctrl+Z.
        location_name = analysis.get('location') or analysis.get('location_type', 'Default')
        if location_name in ['Exterior', 'Interior', 'Auto-detect']:
            location_name = 'Default'

        unreal.log(f"Resolved location: {location_name}")
        # Remember the resolved name for the stage-anchor lookup: the
        # UI-built analysis often carries the location under
        # 'location_type' (not 'location'), and downstream setup steps
        # receive that same dict
        self._resolved_location_name = location_name
        try:
            location_result = self._setup_location(location_name, analysis)
        except Exception as e:
            unreal.log_error(f"Location setup failed: {e}")
            location_result = {'name': location_name, 'type': location_name}

        with unreal.ScopedEditorTransaction(f"Generate Panel {panel_index}") as trans:
            unreal.log(f"Starting build_scene with panel_index={panel_index}")

            self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            if not self.world:
                unreal.log_error("No editor world found")
                trans.cancel()
                return None

            unreal.log("SCENE BUILDER: Starting production-ordered generation")
            unreal.log("Order: Location -> Sequence -> Camera -> Characters -> Props -> Lighting -> Positioning")

            scene_data = {
                'panel_index': panel_index,
                'location': location_result,
                'sequence': None,
                'actors': [],
                'characters': [],
                'props': [],
                'lights': [],
                'camera': None,
                'positioning': {}
            }

            try:
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

                # STEP 9: Optional enhancements (mood lighting, auto
                # animation). Both settings default OFF, so the default
                # path is unchanged; failures never break scene building.
                self._apply_optional_enhancements(scene_data, analysis)

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

        # Own small transaction (closed before any load_level below) so
        # clearing stays undoable without ever spanning a map load.
        with unreal.ScopedEditorTransaction("Clear Storyboard Build Area"):
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
                            
                            success = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(location_path)
                            location_data['loaded'] = success
                            
                            if success:
                                unreal.log(f"Level loaded: {location_name}")
                                # No settle sleep: LevelEditorSubsystem.
                                # load_level is synchronous in editor Python,
                                # so the level is already loaded when the
                                # call returns (the old time.sleep(0.5) just
                                # froze the UI half a second per panel).
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

            if not unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_directory_exist(sequence_path):
                unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).make_directory(sequence_path)

            full_path = f"{sequence_path}/{sequence_name}"

            if unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_asset_exist(full_path):
                sequence = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).load_asset(full_path)
                unreal.log(f"Using existing sequence: {sequence_name}")
                # Remove prior spawnable bindings so regenerating the same
                # panel does not stack duplicate cameras/lights/actors.
                try:
                    # Close first: the sequence is typically still open in
                    # Sequencer from the previous Generate, and mutating an
                    # open sequence can crash or leave dangling editor state.
                    unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
                except Exception as e:
                    unreal.log_warning(f"Could not close sequence before cleanup: {e}")
                try:
                    for binding in list(sequence.get_bindings()):
                        binding.remove()
                    sequence.set_playback_start(0)
                    sequence.set_playback_end(90)
                    unreal.log(f"Cleared prior bindings from {sequence_name}")
                except Exception as e:
                    unreal.log_error(f"Failed to clear prior bindings: {e}")
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

    # ------------------------------------------------------------------
    # Location stage anchor (camera_start / stage_center from the library)
    # ------------------------------------------------------------------

    def _ensure_stage_anchor(self, analysis: Dict[str, Any]) -> None:
        """Resolve this location's stage anchor once per location.

        Locations added from the Content Browser record the editor camera
        pose ('camera_start') and a traced ground point in front of it
        ('stage_center') into their library entry. Building the scene
        there instead of at world origin keeps characters and camera out
        of whatever geometry the map happens to have at (0,0,0) - e.g.
        a cornfield or a fence line. Entries without an anchor keep the
        legacy world-origin behavior unchanged.
        """
        # The location name can arrive under 'location' OR 'location_type'
        # (the UI-built analysis uses the latter - same resolution chain as
        # build_scene). The name resolved at location-setup time goes FIRST:
        # it is provably the value the level loader actually consumed.
        candidates = []
        resolved = str(getattr(self, '_resolved_location_name', '') or '').strip()
        if resolved and resolved != 'Default':
            candidates.append(resolved)
        for key in ('location', 'location_type'):
            value = str(analysis.get(key) or '').strip()
            if value and value not in candidates and value not in (
                    'Exterior', 'Interior', 'Auto-detect', 'exterior',
                    'interior', 'outdoor', 'indoor', 'Default'):
                candidates.append(value)

        memo_key = '|'.join(candidates)
        if getattr(self, '_anchor_memo_key', None) == memo_key:
            return
        self._anchor_memo_key = memo_key
        self._stage_center = unreal.Vector(0.0, 0.0, 0.0)
        self._stage_yaw = 0.0
        self._camera_start = None
        loc_name = candidates[0] if candidates else ''

        try:
            def _find_entry(location_map):
                for candidate in candidates:
                    found = location_map.get(candidate)
                    if isinstance(found, dict):
                        return candidate, found
                    cand_lower = candidate.lower()
                    for key, info in location_map.items():
                        if isinstance(info, dict) and key.strip().lower() == cand_lower:
                            return key, info
                return None, None

            library = self._get_asset_paths_from_library() or {}
            locations = library.get('locations')
            if not isinstance(locations, dict):
                locations = {}
            found_key, entry = _find_entry(locations)
            if entry is None:
                # The in-memory library can be stale or trimmed (a
                # long-lived matcher in batch runs won't see locations
                # added mid-batch); the show's asset_library.json on
                # disk is authoritative
                disk_locations = self._read_show_locations_from_disk()
                if disk_locations:
                    found_key, entry = _find_entry(disk_locations)
                    if entry is not None:
                        locations = disk_locations
            if entry is None:
                unreal.log("[StageAnchor] No library entry for location "
                           "candidates {0} (library has: {1}); building at "
                           "world origin".format(
                               candidates, list(locations.keys())[:5]))
                return
            loc_name = found_key

            center = entry.get('stage_center')
            if isinstance(center, dict):
                cx = float(center.get('x', 0.0) or 0.0)
                cy = float(center.get('y', 0.0) or 0.0)
                cz = float(center.get('z', 0.0) or 0.0)
                # Refine Z against the ACTUAL terrain while the level is
                # open: add-time anchors can carry an estimated Z (when
                # the add-time trace failed), which leaves characters
                # floating above / sunk into the ground
                traced_z = _trace_ground_z_editor(cx, cy, cz)
                if traced_z is not None and abs(traced_z - cz) > 10.0:
                    unreal.log("[StageAnchor] Ground trace corrected stage Z "
                               "{0:.0f} -> {1:.0f}".format(cz, traced_z))
                    cz = traced_z
                    self._persist_stage_z(loc_name, traced_z)
                self._stage_center = unreal.Vector(cx, cy, cz)

            cam = entry.get('camera_start')
            if isinstance(cam, dict) and isinstance(cam.get('location'), dict):
                self._camera_start = cam
                rot = cam.get('rotation') or {}
                try:
                    self._stage_yaw = float(rot.get('yaw', 0.0) or 0.0)
                except (TypeError, ValueError):
                    self._stage_yaw = 0.0

            if self._camera_start is not None or isinstance(center, dict):
                unreal.log("[StageAnchor] '{0}': building at stage center "
                           "({1:.0f}, {2:.0f}, {3:.0f}), yaw {4:.0f}{5}".format(
                               loc_name, self._stage_center.x,
                               self._stage_center.y, self._stage_center.z,
                               self._stage_yaw,
                               ", camera_start recorded" if self._camera_start else ""))
            else:
                unreal.log("[StageAnchor] '{0}' has no stage anchor; building at "
                           "world origin. Add the location from the Content "
                           "Browser (with the map open at a clear vantage) to "
                           "record one.".format(loc_name))
        except Exception as e:
            unreal.log_warning(f"[StageAnchor] Could not resolve anchor: {e}")

    def _persist_stage_z(self, loc_name: str, new_z: float) -> None:
        """Write a ground-trace-corrected stage Z back to the show's
        asset_library.json so the correction sticks (and the survey/prompt
        data stays consistent). Best-effort; never raises."""
        try:
            if not self.show_name or not loc_name:
                return
            import json
            from core.utils import get_shows_manager
            library_path = (get_shows_manager().shows_root / self.show_name
                            / 'asset_library.json')
            if not library_path.exists():
                return
            with open(str(library_path), 'r') as f:
                data = json.load(f)
            entry = (data.get('locations') or {}).get(loc_name)
            if isinstance(entry, dict) and isinstance(entry.get('stage_center'), dict):
                entry['stage_center']['z'] = float(new_z)
                with open(str(library_path), 'w') as f:
                    json.dump(data, f, indent=2)
                unreal.log(f"[StageAnchor] Corrected stage Z persisted to {library_path.name}")
        except Exception as e:
            unreal.log_warning(f"[StageAnchor] Could not persist corrected Z: {e}")

    def _read_show_locations_from_disk(self) -> Dict[str, Any]:
        """Locations dict read directly from the show's asset_library.json.

        Fallback for _ensure_stage_anchor when the matcher's in-memory
        library has no usable 'locations' section. Returns {} on any
        failure; never raises."""
        try:
            if not self.show_name:
                return {}
            import json
            from core.utils import get_shows_manager
            library_path = (get_shows_manager().shows_root / self.show_name
                            / 'asset_library.json')
            if not library_path.exists():
                return {}
            with open(str(library_path), 'r') as f:
                data = json.load(f)
            locations = data.get('locations') if isinstance(data, dict) else None
            return locations if isinstance(locations, dict) else {}
        except Exception as e:
            unreal.log_warning(f"[StageAnchor] Disk read of locations failed: {e}")
            return {}

    def _offset_from_stage(self, offset: unreal.Vector) -> unreal.Vector:
        """World position for an offset defined stage-relative (offsets
        assume the camera looks down +X): rotate by the stage yaw and
        translate to the stage center. With no anchor this is identity."""
        import math
        yaw_rad = math.radians(getattr(self, '_stage_yaw', 0.0) or 0.0)
        cos_y, sin_y = math.cos(yaw_rad), math.sin(yaw_rad)
        center = getattr(self, '_stage_center', None)
        if center is None:
            center = unreal.Vector(0.0, 0.0, 0.0)
        return unreal.Vector(
            center.x + offset.x * cos_y - offset.y * sin_y,
            center.y + offset.x * sin_y + offset.y * cos_y,
            center.z + offset.z)

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

        # Build at the location's stage anchor (world origin when none)
        self._ensure_stage_anchor(analysis)
        # Default facing: back toward the stage camera so iteration 1
        # starts with characters looking roughly into the lens
        default_yaw = (getattr(self, '_stage_yaw', 0.0) + 180.0) % 360.0

        unreal.log(f"Positioning {num_chars} character(s) for {location_type} scene")

        for i, char_name in enumerate(character_names):
            try:
                unreal.log(f"Preparing character config: {char_name}")

                char_path = self._find_asset_path(char_name, asset_paths, 'characters')
                position = self._offset_from_stage(
                    self._calculate_character_position(i, num_chars, location_type, props_list))

                unreal.log(f"Position: X={position.x:.0f}, Y={position.y:.0f}, Z={position.z:.0f}")

                if char_path:
                    if not unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_asset_exist(char_path):
                        error_collector.add_error(char_name, f"Asset does not exist: {char_path}")
                        character_configs.append(self._create_placeholder_config(char_name, position))
                        continue

                    character_configs.append({
                        'type': 'spawnable',
                        'asset_path': char_path,
                        'name': char_name,
                        'position': position,
                        'rotation': unreal.Rotator(pitch=0, yaw=default_yaw, roll=0),
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
        self._ensure_stage_anchor(analysis)

        for i, prop_name in enumerate(prop_names):
            try:
                unreal.log(f"Preparing prop config: {prop_name}")

                prop_path = self._find_asset_path(prop_name, asset_paths, 'props')
                # Stage anchor keeps the initial spawn out of blind geometry;
                # AI positioning handles final placement
                position = self._offset_from_stage(unreal.Vector(0, 0, 0))

                if prop_path:
                    if not unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_asset_exist(prop_path):
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

        # Three-point lighting rig around the stage anchor (world origin
        # when the location has none)
        self._ensure_stage_anchor(analysis)
        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Key Light',
            'position': self._offset_from_stage(unreal.Vector(-300, -200, 400)),
            'intensity': base_intensity * 1000,
            'color': unreal.LinearColor(r=1.0, g=1.0, b=1.0)
        })

        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Fill Light',
            'position': self._offset_from_stage(unreal.Vector(-300, 200, 350)),
            'intensity': base_intensity * 500,
            'color': unreal.LinearColor(r=1.0, g=1.0, b=1.0)
        })

        light_configs.append({
            'type': 'spawnable',
            'class': unreal.PointLight,
            'name': 'Rim Light',
            'position': self._offset_from_stage(unreal.Vector(400, 0, 300)),
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

        focal_length = 50.0
        if 'close' in shot_type:
            focal_length = 85.0
        elif 'wide' in shot_type:
            focal_length = 24.0

        # Camera placement: the location's recorded camera_start is a
        # KNOWN-GOOD vantage (it is exactly what the user was looking at
        # when the location was added), so use it verbatim. Otherwise
        # fall back to the shot-distance offset behind the stage center.
        self._ensure_stage_anchor(analysis)
        camera_start = getattr(self, '_camera_start', None)
        if isinstance(camera_start, dict):
            cam_loc = camera_start.get('location') or {}
            cam_rot = camera_start.get('rotation') or {}
            camera_pos = unreal.Vector(
                float(cam_loc.get('x', 0.0) or 0.0),
                float(cam_loc.get('y', 0.0) or 0.0),
                float(cam_loc.get('z', 180.0) or 180.0))
            camera_rotation = unreal.Rotator(
                pitch=float(cam_rot.get('pitch', 0.0) or 0.0),
                yaw=float(cam_rot.get('yaw', 0.0) or 0.0),
                roll=float(cam_rot.get('roll', 0.0) or 0.0))
            unreal.log("[StageAnchor] Hero camera starting at the location's recorded camera_start")
        else:
            camera_pos = self._offset_from_stage(unreal.Vector(-distance, 0, 180))
            camera_rotation = unreal.Rotator(
                pitch=0.0, yaw=getattr(self, '_stage_yaw', 0.0) or 0.0, roll=0.0)

        camera_config = {
            'type': 'spawnable',
            'class': unreal.CineCameraActor,
            'position': camera_pos,
            'rotation': camera_rotation,
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
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = actor_subsystem.get_all_level_actors()
        cleared_count = 0

        for actor in all_actors:
            if actor and hasattr(actor, 'tags'):
                if 'StoryboardGenerated' in actor.tags:
                    actor_subsystem.destroy_actor(actor)
                    cleared_count += 1

        if cleared_count > 0:
            unreal.log(f"Cleared {cleared_count} previous storyboard actors")

    def _calculate_character_position(self, char_index: int, num_chars: int,
                                       location_type: str, props_list: List[str]) -> unreal.Vector:
        """
        Calculate initial character position (stage-relative).

        Characters are spread along the stage Y axis (perpendicular to the
        camera after the stage-yaw rotation) so multiple actors never
        spawn stacked inside each other - the AI refinement loop then
        only adjusts spacing instead of untangling a fused blob.

        Args:
            char_index: Index of character (0-based).
            num_chars: Total number of characters.
            location_type: Type of location scene.
            props_list: List of props in scene.

        Returns:
            Stage-relative Vector; _offset_from_stage converts to world.
        """
        spread = (char_index - (num_chars - 1) / 2.0) * 150.0
        return unreal.Vector(x=0.0, y=spread, z=0.0)

    def _get_asset_paths_from_library(self) -> Optional[Dict[str, Any]]:
        """
        Load asset paths from show's asset library.
        
        Returns:
            Asset library dict or None if unavailable.
        """
        if not self.show_name:
            return None

        # The asset matcher already parsed asset_library.json at
        # construction - reuse it instead of re-reading the file from disk
        # on every call (this used to run twice per build via
        # _spawn_characters/_spawn_props, plus a third read in
        # _setup_location).
        try:
            matcher_library = getattr(self.asset_matcher, 'show_library', None)
            if isinstance(matcher_library, dict) and matcher_library:
                return matcher_library
        except Exception:
            pass

        # Fallback: disk read (only if the matcher has no library)
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

        name_lower = name.lower()

        # Exact alias match (case-insensitive). Must run BEFORE the loose
        # substring pass so aliases are not shadowed by substring hits
        # (e.g. alias 'tree' vs key 'Treasure Chest'). Aliases may be
        # stored as a list or a comma-separated string.
        for lib_name, info in asset_paths[category].items():
            aliases = info.get('aliases', []) if isinstance(info, dict) else []
            if isinstance(aliases, str):
                aliases = [a.strip() for a in aliases.split(',') if a.strip()]
            for alias in aliases:
                if isinstance(alias, str) and alias.strip().lower() == name_lower:
                    unreal.log(f"Found alias match '{lib_name}' for '{name}'")
                    return info.get('asset_path', '')

        # Partial match
        for lib_name, info in asset_paths[category].items():
            if name_lower in lib_name.lower() or lib_name.lower() in name_lower:
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
                            cube = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).load_asset('/Engine/BasicShapes/Cube')
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

                if not unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_asset_exist(asset_path):
                    unreal.log_error(f"Asset doesn't exist: {asset_path}")
                    return None

                asset = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).load_asset(asset_path)
                if not asset:
                    unreal.log_error(f"Failed to load asset: {asset_path}")
                    return None

                spawnable = None

                # Mesh ASSETS cannot become spawnables directly:
                # add_spawnable_from_instance(StaticMesh) creates a binding
                # with NO object template - it accepts keyframes but renders
                # NOTHING (this made gen3d meshes like the Tripo ghost
                # invisible). Wrap the mesh in its proper actor class and
                # assign it on the spawnable's template instead.
                def _discard_broken(broken):
                    try:
                        if broken is not None:
                            broken.remove()
                    except Exception:
                        pass

                try:
                    if isinstance(asset, unreal.StaticMesh):
                        spawnable = sequence.add_spawnable_from_class(unreal.StaticMeshActor)
                        template = spawnable.get_object_template() if spawnable else None
                        component = getattr(template, 'static_mesh_component', None) if template else None
                        if component:
                            component.set_static_mesh(asset)
                            unreal.log(f"Spawnable '{name}': StaticMeshActor wrapping {asset_path}")
                        else:
                            unreal.log_warning(f"Spawnable '{name}': could not access the StaticMeshActor template")
                            _discard_broken(spawnable)
                            spawnable = None
                    elif isinstance(asset, unreal.SkeletalMesh):
                        spawnable = sequence.add_spawnable_from_class(unreal.SkeletalMeshActor)
                        template = spawnable.get_object_template() if spawnable else None
                        component = getattr(template, 'skeletal_mesh_component', None) if template else None
                        if component:
                            try:
                                component.set_skeletal_mesh_asset(asset)
                            except AttributeError:
                                component.set_skeletal_mesh(asset)
                            unreal.log(f"Spawnable '{name}': SkeletalMeshActor wrapping {asset_path}")
                        else:
                            unreal.log_warning(f"Spawnable '{name}': could not access the SkeletalMeshActor template")
                            _discard_broken(spawnable)
                            spawnable = None
                except Exception as mesh_err:
                    unreal.log_warning(f"Mesh spawnable wrap failed for {name}: {mesh_err}")
                    _discard_broken(spawnable)
                    spawnable = None

                # Try as blueprint
                if not spawnable and ('BP_' in asset_path or 'blueprint' in asset_path.lower()):
                    try:
                        blueprint_class = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).load_blueprint_class(asset_path)
                        if blueprint_class:
                            spawnable = sequence.add_spawnable_from_class(blueprint_class)
                    except:
                        pass

                # Try as instance (actors and other spawnable-capable assets)
                if not spawnable:
                    try:
                        spawnable = sequence.add_spawnable_from_instance(asset)
                    except:
                        pass

                # A binding without an object template renders nothing.
                # Fail loudly instead of silently keyframing an invisible
                # actor for the next twenty minutes.
                if spawnable:
                    try:
                        if spawnable.get_object_template() is None:
                            unreal.log_error(
                                f"Spawnable '{name}' was created WITHOUT an object template "
                                f"(asset type {type(asset).__name__}) - it would be invisible. "
                                "Removing the broken binding.")
                            try:
                                spawnable.remove()
                            except Exception:
                                pass
                            spawnable = None
                    except Exception:
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
            self._last_spawned_character_pairs = []
            for char_config in scene_data.get('characters', []):
                if isinstance(char_config, dict):
                    spawned = self._create_spawnable_from_config(sequence, char_config, 'character')
                    if spawned:
                        spawned_characters.append(spawned)
                        self._last_spawned_character_pairs.append((char_config, spawned))

            # Props
            for prop_config in scene_data.get('props', []):
                if isinstance(prop_config, dict):
                    spawned = self._create_spawnable_from_config(sequence, prop_config, 'prop')
                    if spawned:
                        spawned_props.append(spawned)

            # Camera cuts
            if spawned_camera:
                self._setup_camera_cuts_spawnable(movie_scene, spawned_camera, sequence)

                # Optional shot-type camera move (opt-in via
                # 'sequence.camera_moves', default OFF; the default path
                # is unchanged when unset)
                self._maybe_apply_camera_move(
                    sequence, spawned_camera, camera_config, scene_data)

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
            unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).save_asset(sequence_path)
            unreal.log(f"Sequence saved: {sequence_path}")
        except Exception as e:
            unreal.log_error(f"Failed to save sequence: {e}")

    def _maybe_apply_camera_move(self, sequence: unreal.LevelSequence,
                                 camera_binding: Any,
                                 camera_config: Dict[str, Any],
                                 scene_data: Dict[str, Any]) -> None:
        """
        Apply an optional shot-type camera move to the spawnable camera.

        Gated by the 'sequence.camera_moves' setting (default False, so
        behavior is unchanged unless a user opts in). This is the live
        pipeline's counterpart of the hook in
        core.sequence_generator._maybe_apply_camera_move: the binding
        here is the spawnable created by _create_spawnable_actor, whose
        transform lives in camera_config (the template is not keyed), so
        the transform is passed along explicitly. Fully wrapped in
        try/except: sequence assembly can never break because of a
        camera move.
        """
        try:
            enabled = self._read_optional_setting('sequence.camera_moves', False)
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in ('1', 'true', 'yes', 'on')
            if not enabled:
                return

            shot_type = None
            if isinstance(camera_config, dict):
                shot_type = camera_config.get('shot_type')
            if not shot_type:
                unreal.log("[CameraMoves] Enabled but camera config carries "
                           "no shot type; skipping")
                return

            # Key across the shot's playback range (0-90 by default)
            start_frame, end_frame = 0, 90
            try:
                start_frame = int(sequence.get_playback_start())
                end_frame = int(sequence.get_playback_end())
            except Exception as e:
                unreal.log(f"[CameraMoves] Could not read playback range ({e}); "
                           f"using frames {start_frame}-{end_frame}")

            # The spawnable's transform was keyed from camera_config in
            # _create_spawnable_actor; rebuild it for the move baseline
            current_transform = None
            try:
                position = camera_config.get('position')
                rotation = camera_config.get('rotation')
                if position is not None and rotation is not None:
                    current_transform = unreal.Transform(
                        location=position, rotation=rotation)
            except Exception as e:
                unreal.log_warning(f"[CameraMoves] Could not build the camera "
                                   f"transform from config: {e}")
                current_transform = None

            # First positioned character doubles as the subject for
            # push-in scaling (mirrors the sequence_generator hook)
            subject_location = None
            try:
                for char_config in scene_data.get('characters') or []:
                    if isinstance(char_config, dict) and \
                            char_config.get('position') is not None:
                        subject_location = char_config.get('position')
                        break
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
                "[CameraMoves] {0} (shot type: {1}, move: {2}, notes: {3})".format(
                    result.get('status'), shot_type, result.get('move'),
                    '; '.join(result.get('notes', []))))
        except Exception as e:
            unreal.log_warning(f"[CameraMoves] Failed, sequence unaffected: {e}")

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

    # ========================================
    # OPTIONAL ENHANCEMENTS (default ON, settings-gated)
    # ========================================

    def _read_optional_setting(self, path: str, default: Any = False) -> Any:
        """
        Read a setting with an inline default, mirroring the pattern used
        by core.external_validator.ExternalValidator.get_configured().

        Args:
            path: Dot-notation settings path (e.g. 'scene.auto_animation').
            default: Value returned when settings are unavailable.

        Returns:
            The setting value, or the default on any failure. Never raises.
        """
        try:
            from core.settings_manager import get_setting
        except Exception as e:
            unreal.log_warning(f"Settings manager unavailable ({e}); using default for '{path}'")
            return default
        try:
            return get_setting(path, default)
        except Exception as e:
            unreal.log_warning(f"Could not read setting '{path}': {e}; using default")
            return default

    def _apply_optional_enhancements(self, scene_data: Dict[str, Any],
                                     analysis: Dict[str, Any]) -> None:
        """
        Apply optional, opt-in scene enhancements at the end of a build.

        (a) Mood lighting when 'scene.apply_mood_lighting' is truthy and
            the analysis carries a mood (time_of_day as fallback).
        (b) Auto animation when 'scene.auto_animation' is truthy, for
            spawned characters whose source entity has action text.

        Both default ON (matching settings_manager defaults; the Features
        tab can turn them off); every failure is logged and swallowed so
        scene building is never broken by these steps.
        """
        # (a) Mood lighting
        try:
            if self._read_optional_setting('scene.apply_mood_lighting', True):
                mood = analysis.get('mood') or analysis.get('time_of_day')
                if mood:
                    from core import mood_lighting
                    result = mood_lighting.apply_mood(str(mood))
                    unreal.log(
                        "[MoodLighting] mood '{0}' -> preset '{1}' "
                        "(status: {2}, actors touched: {3})".format(
                            mood, result.get('preset'), result.get('status'),
                            result.get('actors_touched', 0)))
                    for error in result.get('errors') or []:
                        unreal.log_warning(f"[MoodLighting] {error}")
                else:
                    unreal.log("[MoodLighting] apply_mood_lighting is on but "
                               "analysis carries no mood; skipping")
        except Exception as e:
            unreal.log_warning(f"[MoodLighting] Failed (scene build unaffected): {e}")

        # (b) Auto animation
        try:
            if self._read_optional_setting('scene.auto_animation', True):
                self._apply_auto_animations(analysis)
            else:
                unreal.log("[AnimationPicker] scene.auto_animation is OFF "
                           "(Features tab); characters stay in T-pose")
        except Exception as e:
            unreal.log_warning(f"[AnimationPicker] Failed (scene build unaffected): {e}")

        # (c) Focus policy sweep - ALWAYS on. Per-creation-site disables
        # cannot reach cameras that already exist (a sequence keeps its
        # camera template across runs), so enforce on everything.
        try:
            self._disable_focus_on_all_cameras()
        except Exception as e:
            unreal.log_warning(f"[FocusSweep] Failed (scene build unaffected): {e}")

    def _get_entity_action_text(self, analysis: Dict[str, Any],
                                entity_name: str) -> Optional[str]:
        """
        Find action/description text for a spawned entity in the analysis.

        Character entries are usually plain name strings, but richer AI
        responses return dicts (with 'action'/'description' style fields),
        and script/importer flows carry scene-level 'action'/'actions' text.

        Returns:
            Action text string, or None when the entity has none.
        """
        try:
            entries = analysis.get('characters') or []
            if isinstance(entries, (list, tuple)):
                wanted = str(entity_name).strip().lower()
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    entry_name = str(entry.get('name', '')).strip().lower()
                    if entry_name and entry_name != wanted:
                        continue
                    for key in ('action', 'description', 'pose', 'activity'):
                        text = entry.get(key)
                        if isinstance(text, str) and text.strip():
                            return text.strip()

            action = analysis.get('action')
            if isinstance(action, str) and action.strip():
                return self._focus_action_text(action.strip(), entity_name)

            actions = analysis.get('actions')
            if isinstance(actions, str) and actions.strip():
                return self._focus_action_text(actions.strip(), entity_name)
            if isinstance(actions, (list, tuple)):
                joined = ' '.join(str(a) for a in actions if a)
                if joined.strip():
                    return self._focus_action_text(joined.strip(), entity_name)
        except Exception as e:
            unreal.log_warning(f"[AnimationPicker] Could not read action text: {e}")
        return None

    @staticmethod
    def _focus_action_text(text: str, entity_name: str) -> str:
        """Narrow scene-level action text to the clauses mentioning the
        entity. With one shared description ("A farmer ... stands ...,
        looking startled at a floating ghost"), every character used to
        match the FIRST verb in the text - the ghost got the farmer's
        'stands' instead of its own 'floating'. Falls back to the full
        text when the entity is not mentioned by name."""
        try:
            wanted = str(entity_name).strip().lower().strip('()').strip()
            if not wanted:
                return text
            clauses = [c.strip() for c in re.split(r'[.;,]', text) if c.strip()]
            hits = [c for c in clauses if wanted in c.lower()]
            if hits:
                return '. '.join(hits)
        except Exception:
            pass
        return text

    def _apply_auto_animations(self, analysis: Dict[str, Any]) -> None:
        """
        Match and apply animations to spawned skeletal characters.

        Uses the (config, spawnable) pairs recorded by
        _add_actors_to_sequence; the spawnable's object template is the
        animation target (non-skeletal templates are skipped by the
        matcher with a log).
        """
        pairs = getattr(self, '_last_spawned_character_pairs', None) or []
        if not pairs:
            unreal.log("[AnimationPicker] auto_animation is on but no "
                       "spawned characters to animate")
            return

        # Self-heal the show's animation library BEFORE matching:
        # characters added before Content-Browser skeleton discovery
        # existed (or whose discovery failed) leave the show without an
        # animation_library.json, so the matcher only ever sees the
        # sample fallback and every character stays in T-pose.
        self._ensure_animation_library(pairs)

        from core.animation_matcher import AnimationMatcher
        matcher = AnimationMatcher(show_name=self.show_name)
        applied = 0

        for config, spawnable in pairs:
            try:
                name = config.get('name', 'Actor') if isinstance(config, dict) else 'Actor'
                action_text = self._get_entity_action_text(analysis, name)
                if not action_text:
                    unreal.log(f"[AnimationPicker] No action/description text for '{name}'; skipping")
                    continue

                anim_path = matcher.find_animation(action_text)
                if not anim_path:
                    unreal.log(f"[AnimationPicker] No animation match for '{name}' (action: '{action_text}')")
                    continue

                # Sequencer-native animation track first: binding-level, no
                # live-actor lookup, persists in the sequence, evaluates on
                # every capture. Component single-node playback is the
                # fallback for engines/bindings where the track fails.
                if self._add_animation_track_to_spawnable(spawnable, anim_path, name):
                    applied += 1
                    unreal.log(f"[AnimationPicker] Applied '{anim_path}' to '{name}' via sequencer track (action: '{action_text}')")
                    continue

                target, component = self._skeletal_animation_target(spawnable, name)
                if component is None:
                    unreal.log(f"[AnimationPicker] '{name}' has no SkeletalMeshComponent "
                               f"on its template or live actor (static character?); cannot animate")
                    continue

                if matcher.apply_animation_to_actor(target, anim_path):
                    applied += 1
                    unreal.log(f"[AnimationPicker] Applied '{anim_path}' to '{name}' (action: '{action_text}')")
                else:
                    unreal.log(f"[AnimationPicker] Could not apply '{anim_path}' to '{name}' (not skeletal?)")
            except Exception as e:
                unreal.log_warning(f"[AnimationPicker] Error animating one actor: {e}")

        unreal.log(f"[AnimationPicker] Animations applied: {applied}/{len(pairs)}")

    def _disable_focus_on_all_cameras(self) -> None:
        """
        Plugin-wide policy: NO camera focuses (autofocus blur breaks the
        AI's storyboard comparisons). Sweeps every CineCameraActor in the
        level AND every camera spawnable template in the open sequence,
        forcing focus_method=DISABLE - covering cameras created before the
        per-creation-site disables existed. Never raises.
        """
        def _disable(component):
            try:
                if component is None:
                    return False
                fs = component.focus_settings
                if fs.focus_method == unreal.CameraFocusMethod.DISABLE:
                    return False
                fs.focus_method = unreal.CameraFocusMethod.DISABLE
                component.set_editor_property('focus_settings', fs)
                return True
            except Exception:
                return False

        fixed = 0
        # Level cameras (scout cameras, hand-placed cine cameras)
        try:
            actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            for actor in actor_sub.get_all_level_actors() or []:
                if isinstance(actor, unreal.CineCameraActor):
                    if _disable(actor.get_cine_camera_component()):
                        fixed += 1
        except Exception as e:
            unreal.log_warning(f"[FocusSweep] Level scan failed: {e}")

        # Sequence camera templates (persist across builds in the asset)
        try:
            sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
            bindings = sequence.get_bindings() if sequence else []
            for binding in bindings or []:
                try:
                    template = binding.get_object_template()
                except Exception:
                    template = None
                if template is not None and isinstance(template, unreal.CineCameraActor):
                    if _disable(template.get_cine_camera_component()):
                        fixed += 1
        except Exception as e:
            unreal.log_warning(f"[FocusSweep] Sequence scan failed: {e}")

        if fixed:
            unreal.log(f"[FocusSweep] Disabled focus on {fixed} camera(s) "
                       f"(plugin-wide no-focus policy)")
        else:
            unreal.log("[FocusSweep] All cameras already have focus disabled")

    @staticmethod
    def _skeletal_component_of(actor: Any) -> Optional[Any]:
        """SkeletalMeshComponent of an actor/template, or None. Guarded."""
        if actor is None:
            return None
        component = getattr(actor, 'skeletal_mesh_component', None)
        if component is None and hasattr(actor, 'get_component_by_class') \
                and hasattr(unreal, 'SkeletalMeshComponent'):
            try:
                component = actor.get_component_by_class(
                    unreal.SkeletalMeshComponent)
            except Exception:
                component = None
        return component

    @staticmethod
    def _skeletal_mesh_of_component(component: Any) -> Optional[Any]:
        """SkeletalMesh asset assigned to a component, or None. Guarded."""
        if component is None:
            return None
        if hasattr(component, 'get_skeletal_mesh_asset'):
            try:
                mesh = component.get_skeletal_mesh_asset()
                if mesh is not None:
                    return mesh
            except Exception:
                pass
        for prop in ('skeletal_mesh_asset', 'skeletal_mesh'):
            try:
                mesh = component.get_editor_property(prop)
                if mesh is not None:
                    return mesh
            except Exception:
                continue
        return None

    def _skeletal_animation_target(self, spawnable: Any,
                                   label: Optional[str] = None) -> Tuple[Any, Any]:
        """
        Resolve (target, component) for animating a spawnable character.

        The object template is preferred (edits there survive respawns),
        but BLUEPRINT templates carry no constructed components - SCS
        components only exist on spawned instances - so fall back to the
        LIVE bound actor. Bound-actor lookup tries the binding-id API
        first, then scans the level by actor label (UE 5.8's
        get_bound_objects rejects a raw binding proxy). Returns
        (None, None)-ish when nothing has a SkeletalMeshComponent
        (static characters).
        """
        template = None
        if hasattr(spawnable, 'get_object_template'):
            try:
                template = spawnable.get_object_template()
            except Exception:
                template = None
        component = self._skeletal_component_of(template)
        if component is not None:
            return template, component

        # (1) Bound objects via a proper MovieSceneObjectBindingID
        bound = []
        try:
            binding_id = unreal.MovieSceneSequenceExtensions.get_binding_id(
                spawnable.sequence, spawnable)
            bound = unreal.LevelSequenceEditorBlueprintLibrary.get_bound_objects(
                binding_id) or []
        except Exception as e:
            unreal.log(f"[AnimationPicker] binding-id lookup unavailable ({e}); "
                       f"falling back to level scan")
        for obj in bound:
            comp = self._skeletal_component_of(obj)
            if comp is not None:
                unreal.log("[AnimationPicker] Using the LIVE bound actor as "
                           "animation target (Blueprint template has no "
                           "components)")
                return obj, comp

        # (2) Level scan by label: spawned spawnables carry their binding's
        # display name as the actor label
        wanted = None
        try:
            wanted = str(label or spawnable.get_display_name()).strip()
        except Exception:
            wanted = str(label or '').strip()
        if wanted:
            try:
                actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                for actor in actor_sub.get_all_level_actors() or []:
                    try:
                        if str(actor.get_actor_label()).strip() != wanted:
                            continue
                    except Exception:
                        continue
                    comp = self._skeletal_component_of(actor)
                    if comp is not None:
                        unreal.log(f"[AnimationPicker] Found live actor "
                                   f"'{wanted}' by level scan; using it as "
                                   f"animation target")
                        return actor, comp
            except Exception as e:
                unreal.log(f"[AnimationPicker] Level scan failed ({e})")
        return template, None

    def _add_animation_track_to_spawnable(self, spawnable: Any,
                                          anim_path: str,
                                          name: str) -> bool:
        """
        Sequencer-native animation: a SkeletalAnimation track + section on
        the character's binding. Preferred over component-level single-node
        playback: it needs no live-actor lookup, persists in the sequence
        asset, scrubs with the timeline, and re-applies on every
        evaluation (so respawns cannot lose it). Never raises.
        """
        try:
            if not hasattr(unreal, 'MovieSceneSkeletalAnimationTrack'):
                return False
            asset = unreal.get_editor_subsystem(
                unreal.EditorAssetSubsystem).load_asset(anim_path)
            if asset is None:
                unreal.log_warning(f"[AnimationPicker] Animation asset not "
                                   f"found: {anim_path}")
                return False
            if hasattr(unreal, 'AnimSequence') and not isinstance(
                    asset, unreal.AnimSequence):
                unreal.log_warning(f"[AnimationPicker] {anim_path} is not an "
                                   f"AnimSequence")
                return False

            # Idempotent rebuilds: one animation track per character
            try:
                for track in list(spawnable.get_tracks() or []):
                    if isinstance(track, unreal.MovieSceneSkeletalAnimationTrack):
                        spawnable.remove_track(track)
            except Exception:
                pass

            track = spawnable.add_track(unreal.MovieSceneSkeletalAnimationTrack)
            section = track.add_section()

            end_frame = 240
            try:
                end_frame = int(spawnable.sequence.get_playback_end())
            except Exception:
                pass
            try:
                section.set_range(0, max(end_frame, 1))
            except Exception:
                try:
                    section.set_start_frame_bounded(True)
                    section.set_end_frame_bounded(True)
                except Exception:
                    pass

            params = section.get_editor_property('params')
            params.set_editor_property('animation', asset)
            section.set_editor_property('params', params)

            unreal.log(f"[AnimationPicker] Animation track added for '{name}': "
                       f"{anim_path} (frames 0-{end_frame})")
            return True
        except Exception as e:
            unreal.log_warning(f"[AnimationPicker] Animation track failed for "
                               f"'{name}' ({e}); trying component playback")
            return False

    def _ensure_animation_library(self, pairs) -> None:
        """
        Build/refresh the show's animation_library.json from the spawned
        skeletal characters' skeletons (idempotent: existing entries are
        never overwritten; skeletons without compatible AnimSequences just
        log). Runs once per distinct skeletal mesh per build. Never raises.
        """
        try:
            from core.animation_cataloger import (
                build_show_animation_library_for_skeleton)
        except Exception as e:
            unreal.log_warning(f"[AnimationPicker] Animation cataloger "
                               f"unavailable ({e}); library self-heal skipped")
            return

        seen = set()
        for config, spawnable in pairs:
            try:
                entity_name = config.get('name') if isinstance(config, dict) else None
                target, component = self._skeletal_animation_target(
                    spawnable, entity_name)
                if component is None:
                    continue  # static mesh character; nothing to discover

                mesh = self._skeletal_mesh_of_component(component)
                if mesh is None:
                    continue

                mesh_path = str(mesh.get_path_name())
                if not mesh_path or mesh_path in seen:
                    continue
                seen.add(mesh_path)

                result = build_show_animation_library_for_skeleton(
                    self.show_name, mesh_path)
                if result.get('added'):
                    unreal.log(f"[AnimationPicker] Discovered "
                               f"{result['added']} animation(s) for skeleton "
                               f"of {mesh_path}")
                elif result.get('skipped_reason'):
                    unreal.log(f"[AnimationPicker] Library self-heal for "
                               f"{mesh_path}: {result['skipped_reason']}")
            except Exception as e:
                unreal.log_warning(f"[AnimationPicker] Library self-heal "
                                   f"failed for one character: {e}")

    def _gen3d_rescue(self, rejected_names, analysis: Dict[str, Any],
                      category: str = 'characters') -> list:
        """
        Try to generate rejected/missing entities via the optional gen3d
        tier instead of dropping them (characters) or falling back to
        placeholder cubes (props).

        Only active when 'gen3d.enabled' is on and a provider key exists
        (gen3d_factory.get_configured() returns None otherwise). Each
        rescued entity is generated, imported, written into the show's
        asset_library.json so the spawn steps can resolve it, and
        returned so the caller accepts it. Any failure just leaves the
        entity missing, exactly as before.
        """
        rescued = []
        try:
            from core.gen3d import gen3d_factory
            if gen3d_factory.get_configured() is None:
                return rescued
        except ImportError:
            return rescued
        except Exception as e:
            unreal.log_warning(f"[Gen3D] rescue unavailable: {e}")
            return rescued

        description = analysis.get('scene_description') or analysis.get('description')
        if not isinstance(description, str):
            description = None

        # Optional panel image for the gen3d image mode ('gen3d.mode').
        # The key is threaded in by the UI call sites; when absent the
        # matcher stays in text mode, so behavior is unchanged.
        panel_image_path = analysis.get('panel_image_path')
        if not isinstance(panel_image_path, str) or not panel_image_path.strip():
            panel_image_path = None

        # Only freshly generated assets may be rescued: find_best_match
        # searches every tier, and force-accepting a fuzzy/library hit on
        # a rejected name would defeat EntityValidator.
        try:
            from core.gen3d.importer import GENERATED_ASSET_PATH as generated_root
        except Exception:
            generated_root = '/Game/StoryboardTo3D/Generated'

        for name in rejected_names:
            try:
                asset = self.asset_matcher.find_best_match(
                    name, category=category, description=description,
                    panel_image_path=panel_image_path)
                if asset is None or not hasattr(asset, 'get_path_name'):
                    continue
                asset_path = asset.get_path_name()
                if not asset_path:
                    continue
                if not str(asset_path).startswith(generated_root):
                    unreal.log(f"[Gen3D] match for {name} came from the "
                               f"library tiers, not generation; leaving it rejected")
                    continue
                if self._register_rescued_asset(name, asset_path, description,
                                                category=category):
                    rescued.append(name)
                    unreal.log(f"[Gen3D] rescued {category[:-1]} '{name}' -> {asset_path}")
            except Exception as e:
                unreal.log_warning(f"[Gen3D] rescue failed for '{name}': {e}")

        return rescued

    def _register_rescued_asset(self, name: str, asset_path: str,
                                description: Optional[str] = None,
                                category: str = 'characters') -> bool:
        """
        Write a rescued entity into the show's asset_library.json (the
        file the spawn steps resolve asset paths from) and mirror it
        into the in-memory show_library used for validation.
        """
        if not self.show_name:
            return False
        try:
            from core.utils import get_shows_manager
            import json

            shows_manager = get_shows_manager()
            library_path = shows_manager.shows_root / self.show_name / 'asset_library.json'
            library = {}
            if library_path.exists():
                with open(library_path, 'r') as f:
                    library = json.load(f)

            entry = {
                'asset_path': asset_path,
                'description': description or 'AI-generated 3D asset (gen3d)',
                'aliases': []
            }
            library.setdefault(category, {})[name] = entry
            with open(library_path, 'w') as f:
                json.dump(library, f, indent=2)

            if hasattr(self.asset_matcher, 'show_library') and isinstance(
                    self.asset_matcher.show_library, dict):
                self.asset_matcher.show_library.setdefault(category, {})[name] = entry
            return True
        except Exception as e:
            unreal.log_warning(f"[Gen3D] could not register '{name}' in the show library: {e}")
            return False

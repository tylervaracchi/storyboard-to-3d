# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
PROPER UE5 SEQUENCE POPULATION
Based on Epic's official documentation
"""

import unreal

def open_and_populate_sequence(sequence_asset, actors_to_add):
    """
    Opens a sequence and adds actors to it using the proper UE5 Python API
    Based on Epic's official documentation
    """

    # Get the required subsystems
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_seq_subsystem = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)

    if not level_seq_subsystem:
        unreal.log_error("Could not get LevelSequenceEditorSubsystem")
        return False

    # Open the sequence in the editor
    unreal.log(f"Opening sequence: {sequence_asset}")
    level_seq_subsystem.open_level_sequence(sequence_asset)

    # Get the current sequence (the one we just opened)
    current_sequence = level_seq_subsystem.get_current_level_sequence()
    if not current_sequence:
        unreal.log_error("No current sequence after opening")
        return False

    unreal.log(f"Current sequence: {current_sequence}")

    # Select the actors we want to add
    actor_subsystem.clear_actor_selection_set()
    for actor in actors_to_add:
        actor_subsystem.select_actor(actor)

    # Get selected actors
    selected_actors = actor_subsystem.get_selected_level_actors()
    unreal.log(f"Selected {len(selected_actors)} actors")

    # Add the actors to the sequence as possessables
    bindings = level_seq_subsystem.add_actors(selected_actors)

    if bindings:
        unreal.log(f"Added {len(bindings)} actors to sequence")

        # Convert possessables to spawnables if needed
        for binding in bindings:
            # This makes them spawnable (sequence-owned)
            level_seq_subsystem.convert_to_spawnable(binding)
            unreal.log(f"Converted {binding} to spawnable")

    # Add a camera with camera cut track
    camera_binding = level_seq_subsystem.create_camera(spawnable=True)
    if camera_binding:
        unreal.log("Added camera with camera cut track")

    # Refresh the sequencer UI
    unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()

    return True

def populate_sequence_from_scene_builder(scene_data):
    """
    Specifically for our scene builder workflow
    """
    sequence_asset = scene_data.get('sequence', {}).get('asset')
    if not sequence_asset:
        unreal.log_error("No sequence asset in scene data")
        return

    # Collect actors
    actors = []
    if scene_data.get('camera'):
        actors.append(scene_data['camera'])
    actors.extend(scene_data.get('characters', []))
    actors.extend(scene_data.get('props', []))

    # Open and populate
    return open_and_populate_sequence(sequence_asset, actors)

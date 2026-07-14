# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Shared helpers for the core.importers package.

Private module (leading underscore, not re-exported from __init__.py) so
storyboarder_importer.py and image_folder_importer.py can share logging
fallbacks and show/episode lookup logic without duplicating it.

The `unreal` import is guarded so this module (and anything that only
imports the helpers below) can still be imported outside the Unreal Editor
Python environment, e.g. for `python -m py_compile` or offline unit tests.
Actually creating shows/episodes still requires running inside the editor,
since ShowsManager/EpisodesManager themselves import `unreal` unconditionally.
"""

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False


def log(message):
    """Log info, falling back to print() outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log'):
        unreal.log(message)
    else:
        print(message)


def log_warning(message):
    """Log a warning, falling back to print() outside the editor."""
    if UNREAL_AVAILABLE and hasattr(unreal, 'log_warning'):
        unreal.log_warning(message)
    else:
        print("WARNING: {0}".format(message))


def get_or_create_show(shows_manager, show_name):
    """
    Find an existing show by display name or safe (folder) name.

    Creates a new show via ShowsManager.create_show() if no match is found.

    Args:
        shows_manager: A ShowsManager instance (see core/shows_manager.py).
        show_name: The display name or safe_name of the target show.

    Returns:
        Tuple of (show_safe_name, show_metadata_dict).
    """
    for metadata in shows_manager.get_all_shows():
        if metadata.get('name') == show_name or metadata.get('safe_name') == show_name:
            return metadata.get('safe_name'), metadata

    _show_path, metadata = shows_manager.create_show(show_name)
    return metadata.get('safe_name'), metadata


def get_or_create_episode(episodes_manager, show_safe_name, episode_name):
    """
    Find an existing episode by display name or safe (folder) name within a show.

    Creates a new episode via EpisodesManager.create_episode() if no match is found.

    Args:
        episodes_manager: An EpisodesManager instance (see core/episodes_manager.py).
        show_safe_name: The safe_name (folder name) of the parent show.
        episode_name: The display name or safe_name of the target episode.

    Returns:
        Tuple of (episode_safe_name, episode_metadata_dict).
    """
    for metadata in episodes_manager.get_show_episodes(show_safe_name):
        if metadata.get('name') == episode_name or metadata.get('safe_name') == episode_name:
            return metadata.get('safe_name'), metadata

    _episode_path, metadata = episodes_manager.create_episode(show_safe_name, episode_name)
    return metadata.get('safe_name'), metadata


def import_staged_files_to_episode(episodes_manager, show_safe_name, episode_safe_name, staged_files):
    """
    Thin wrapper around EpisodesManager.import_panels_to_episode() that never
    raises, so callers can treat a manager failure as "zero files imported"
    instead of aborting the whole batch.

    Returns:
        List of destination path strings (may be shorter than staged_files
        if the manager silently skipped an entry, or empty on error).
    """
    if not staged_files:
        return []
    try:
        return episodes_manager.import_panels_to_episode(show_safe_name, episode_safe_name, staged_files)
    except Exception as exc:
        log_warning("import_panels_to_episode failed: {0}".format(exc))
        return []

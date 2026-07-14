# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Storyboarder Importer

Imports a Wonder Unit Storyboarder project (a `.storyboarder` JSON file plus
a sibling `images/` folder) into a StoryboardTo3D show/episode.

`.storyboarder` file shape (relevant fields only):
    {
      "boards": [
        {
          "url": "board-abc123.png",   # filename inside the sibling images/ folder
          "duration": 2000,             # optional, milliseconds
          "dialogue": "...",            # optional
          "action": "..."               # optional
        },
        ...
      ]
    }

EpisodesManager.import_panels_to_episode() (see core/episodes_manager.py)
only accepts a list of image file paths -- it has no concept of per-panel
dialogue/action/duration. So this module copies the board images through
that manager (matching how every other panel-import path in this plugin
works) and returns the text/duration metadata in the result dict instead of
writing it into a manager-owned file. See the 'notes' entry in the result
for how a caller can persist it (e.g. into episode_path/panels_metadata.json,
matching the schema ui/main_window.py already uses).
"""

import json
import shutil
import tempfile
from pathlib import Path

from core.importers._common import (
    UNREAL_AVAILABLE,
    get_or_create_episode,
    get_or_create_show,
    import_staged_files_to_episode,
    log,
)


def _new_result():
    return {
        'imported': 0,
        'skipped': [],
        'notes': [],
        'panels': [],
        'show_safe_name': None,
        'episode_safe_name': None,
    }


def _duration_ms_to_seconds(raw_duration):
    """Best-effort conversion of a Storyboarder 'duration' (ms) to seconds."""
    if raw_duration is None:
        return None
    try:
        return float(raw_duration) / 1000.0
    except (TypeError, ValueError):
        return None


def import_storyboarder(path, show_name, episode_name):
    """
    Import a `.storyboarder` project into a show/episode, creating either if
    they don't already exist.

    Args:
        path: Path to the `.storyboarder` JSON file. The board images are
            expected in an `images` folder next to this file.
        show_name: Display name or safe_name of the target show.
        episode_name: Display name or safe_name of the target episode.

    Returns:
        dict with keys:
            imported (int): number of board images successfully copied.
            skipped (list[dict]): boards that could not be imported, each
                with 'index' and 'reason' (and 'url' when known).
            notes (list[str]): human-readable notes, including any caveats
                about metadata that could not be persisted by the managers.
            panels (list[dict]): one entry per imported board, in board
                order, with 'index', 'source_name', 'dest_name', 'dest_path',
                'duration_seconds' (float or None), 'dialogue', 'action'.
            show_safe_name / episode_safe_name (str or None): resolved
                folder names for the show/episode used.
    """
    result = _new_result()

    if not UNREAL_AVAILABLE:
        result['notes'].append(
            "unreal module is not available; import_storyboarder must run inside the "
            "Unreal Editor Python environment. No files were copied."
        )
        return result

    storyboarder_path = Path(path)
    if not storyboarder_path.exists():
        result['notes'].append("Storyboarder file not found: {0}".format(path))
        return result

    try:
        with open(storyboarder_path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except Exception as exc:
        result['notes'].append("Failed to parse .storyboarder JSON: {0}".format(exc))
        return result

    boards = data.get('boards') if isinstance(data, dict) else None
    if not isinstance(boards, list):
        result['notes'].append("No 'boards' array found in .storyboarder file; nothing to import.")
        return result

    images_dir = storyboarder_path.parent / "images"
    if not images_dir.exists():
        result['notes'].append("Expected sibling 'images' folder not found at: {0}".format(images_dir))

    # Lazy import: ShowsManager/EpisodesManager unconditionally `import unreal`,
    # so they can only be imported once we know we're inside the editor.
    try:
        from core.shows_manager import ShowsManager
        from core.episodes_manager import EpisodesManager
    except ImportError as exc:
        result['notes'].append("Could not import shows/episodes managers: {0}".format(exc))
        return result

    shows_manager = ShowsManager()
    episodes_manager = EpisodesManager()

    show_safe_name, _show_meta = get_or_create_show(shows_manager, show_name)
    episode_safe_name, _episode_meta = get_or_create_episode(episodes_manager, show_safe_name, episode_name)
    result['show_safe_name'] = show_safe_name
    result['episode_safe_name'] = episode_safe_name

    board_entries = []

    with tempfile.TemporaryDirectory(prefix="storyboarder_import_") as staging_dir:
        staging_path = Path(staging_dir)

        for index, board in enumerate(boards):
            if not isinstance(board, dict):
                result['skipped'].append({'index': index, 'reason': "Board entry is not an object"})
                continue

            url = board.get('url')
            if not url:
                result['skipped'].append({'index': index, 'reason': "Board has no 'url'"})
                continue

            source_image = images_dir / url
            if not source_image.exists():
                result['skipped'].append({
                    'index': index,
                    'url': url,
                    'reason': "Image file not found: {0}".format(source_image),
                })
                continue

            # Zero-padded sequence prefix so the destination Panels/ folder
            # sorts back into storyboard order (EpisodesManager keeps the
            # source filename, and panel grids list Panels/ with a plain
            # alphabetical glob).
            staged_name = "{0:03d}_{1}".format(index, source_image.name)
            staged_path = staging_path / staged_name
            try:
                shutil.copy2(source_image, staged_path)
            except Exception as exc:
                result['skipped'].append({
                    'index': index,
                    'url': url,
                    'reason': "Failed to stage image: {0}".format(exc),
                })
                continue

            board_entries.append({
                'index': index,
                'staged_path': staged_path,
                'source_name': source_image.name,
                'duration_seconds': _duration_ms_to_seconds(board.get('duration')),
                'dialogue': board.get('dialogue') or '',
                'action': board.get('action') or '',
            })

        if board_entries:
            staged_files = [str(entry['staged_path']) for entry in board_entries]
            imported_paths = import_staged_files_to_episode(
                episodes_manager, show_safe_name, episode_safe_name, staged_files
            )

            for entry, dest_path in zip(board_entries, imported_paths):
                dest = Path(dest_path)
                result['panels'].append({
                    'index': entry['index'],
                    'source_name': entry['source_name'],
                    'dest_name': dest.name,
                    'dest_path': str(dest),
                    'duration_seconds': entry['duration_seconds'],
                    'dialogue': entry['dialogue'],
                    'action': entry['action'],
                })
                result['imported'] += 1

            if len(imported_paths) != len(board_entries):
                result['notes'].append(
                    "EpisodesManager reported {0} imported file(s) for {1} staged board(s); "
                    "the remainder were skipped by the manager (e.g. missing on disk).".format(
                        len(imported_paths), len(board_entries)
                    )
                )

    if result['imported'] > 0:
        result['notes'].append(
            "EpisodesManager.import_panels_to_episode() only accepts image file paths, so "
            "dialogue/action/duration text was not written into any manager-owned file. It is "
            "returned per-panel in this result's 'panels' list (keyed by 'dest_name'). To persist "
            "it, write it into <episode_path>/panels_metadata.json keyed by panel filename, "
            "matching the schema ui/main_window.py already uses (see save_panel_metadata)."
        )

    log("import_storyboarder: imported {0} panel(s), skipped {1}, show='{2}' episode='{3}'".format(
        result['imported'], len(result['skipped']), show_safe_name, episode_safe_name
    ))

    return result

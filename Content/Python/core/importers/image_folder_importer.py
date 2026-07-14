# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Image Folder Importer

Imports a flat folder of images (for example a ComfyUI output folder) into a
StoryboardTo3D show/episode as ordered panels, using natural sort so numeric
suffixes order correctly (frame2.png before frame10.png).
"""

import re
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

_DIGIT_RUN = re.compile(r'(\d+)')


def natural_key(value):
    """
    Sort key that orders strings/paths the way humans expect
    (frame2.png before frame10.png, not the other way around).

    Splits the name on runs of digits and converts each digit run to an int,
    so numeric portions compare numerically while the surrounding text still
    compares case-insensitively.

    Args:
        value: A str or pathlib.Path. If a Path, only its filename is used.

    Returns:
        A list safe to pass as a `key=` for sorted()/sort().
    """
    name = value.name if isinstance(value, Path) else str(value)
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in _DIGIT_RUN.split(name)]


def _collect_images(source_folder, pattern):
    """Glob `source_folder` for `pattern` (semicolon-separated globs), deduped, natural-sorted."""
    globs = [chunk.strip() for chunk in pattern.split(';') if chunk.strip()]
    if not globs:
        globs = ['*.png', '*.jpg', '*.jpeg']

    matched = {}
    for glob_pattern in globs:
        # Path.glob() is case-sensitive on some platforms (e.g. Linux), so also
        # try an uppercase-extension variant. Matches are deduped by resolved
        # path below, so this is harmless on case-insensitive filesystems too.
        for candidate_pattern in (glob_pattern, glob_pattern.upper()):
            for candidate in source_folder.glob(candidate_pattern):
                if candidate.is_file():
                    matched[str(candidate.resolve())] = candidate

    return sorted(matched.values(), key=natural_key)


def import_image_folder(folder, show_name, episode_name, pattern='*.png;*.jpg;*.jpeg'):
    """
    Import every image in `folder` into a show/episode, in natural-sort order.

    Args:
        folder: Path to a folder containing images (e.g. a ComfyUI output folder).
        show_name: Display name or safe_name of the target show (created if missing).
        episode_name: Display name or safe_name of the target episode (created if missing).
        pattern: Semicolon-separated glob patterns to match. Defaults to
            '*.png;*.jpg;*.jpeg'.

    Returns:
        dict with keys:
            imported (int): number of images successfully copied.
            skipped (list[dict]): files that could not be imported, each with
                'source' and 'reason'.
            notes (list[str]): human-readable notes.
            panels (list[dict]): one entry per imported image, in natural-sort
                order, with 'source_name', 'dest_name', 'dest_path'.
            show_safe_name / episode_safe_name (str or None): resolved folder
                names for the show/episode used.
    """
    result = {
        'imported': 0,
        'skipped': [],
        'notes': [],
        'panels': [],
        'show_safe_name': None,
        'episode_safe_name': None,
    }

    if not UNREAL_AVAILABLE:
        result['notes'].append(
            "unreal module is not available; import_image_folder must run inside the "
            "Unreal Editor Python environment. No files were copied."
        )
        return result

    source_folder = Path(folder)
    if not source_folder.is_dir():
        result['notes'].append("Folder not found: {0}".format(folder))
        return result

    image_files = _collect_images(source_folder, pattern)
    if not image_files:
        result['notes'].append("No files matched pattern '{0}' in folder: {1}".format(pattern, source_folder))
        return result

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

    with tempfile.TemporaryDirectory(prefix="image_folder_import_") as staging_dir:
        staging_path = Path(staging_dir)
        staged_files = []
        source_names = []

        for index, image_file in enumerate(image_files):
            # Zero-padded sequence prefix so the destination Panels/ folder
            # sorts back into the natural-sort order we computed here
            # (EpisodesManager keeps the source filename, and panel grids
            # list Panels/ with a plain alphabetical glob).
            staged_name = "{0:03d}_{1}".format(index, image_file.name)
            staged_path = staging_path / staged_name
            try:
                shutil.copy2(image_file, staged_path)
            except Exception as exc:
                result['skipped'].append({'source': str(image_file), 'reason': str(exc)})
                continue
            staged_files.append(str(staged_path))
            source_names.append(image_file.name)

        imported_paths = import_staged_files_to_episode(
            episodes_manager, show_safe_name, episode_safe_name, staged_files
        )

        for source_name, dest_path in zip(source_names, imported_paths):
            dest = Path(dest_path)
            result['panels'].append({
                'source_name': source_name,
                'dest_name': dest.name,
                'dest_path': str(dest),
            })
            result['imported'] += 1

        if len(imported_paths) != len(staged_files):
            result['notes'].append(
                "EpisodesManager reported {0} imported file(s) for {1} staged image(s); "
                "the remainder were skipped by the manager (e.g. missing on disk).".format(
                    len(imported_paths), len(staged_files)
                )
            )

    log("import_image_folder: imported {0} panel(s), skipped {1}, show='{2}' episode='{3}'".format(
        result['imported'], len(result['skipped']), show_safe_name, episode_safe_name
    ))

    return result

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Animatic Renderer Module

Renders a master Level Sequence to disk through Movie Render Queue (MRQ).

Honest note on output format: MRQ's built-in movie encoders vary a lot
between engine versions and platforms, so the most version-stable path is a
PNG image sequence. This module prefers PNG frames and falls back to Apple
ProRes only when the PNG setting class is unavailable. Turn the rendered
frames into an MP4 with ffmpeg:

    ffmpeg -framerate 30 -i "MasterSequence.%04d.png" -c:v libx264 \
        -pix_fmt yuv420p animatic.mp4

Requires the Movie Render Queue plugin. Every MRQ class lookup is guarded
because the Python API surface differs across UE 5.4 - 5.8.
"""

import os

try:
    import unreal
except ImportError:
    unreal = None

MRQ_MISSING_MSG = (
    "Movie Render Queue API is unavailable. Enable the 'Movie Render Queue' "
    "plugin (Edit > Plugins), restart the editor, and try again."
)

# Keep a reference to the active executor; MRQ aborts if it is GC'd mid-render
_ACTIVE_EXECUTOR = None


def _get_class(name):
    """Return unreal.<name> if it exists, else None (version-safe lookup)."""
    if unreal is not None and hasattr(unreal, name):
        return getattr(unreal, name)
    return None


def _error(notes):
    if unreal is not None:
        unreal.log_error("AnimaticRenderer: {0}".format(notes))
    return {'status': 'error', 'output_dir': None, 'notes': notes}


def _default_output_dir():
    """Resolve <Project>/Saved/StoryboardTo3D/Animatics with a safe fallback."""
    saved = "Saved"
    try:
        if unreal is not None and hasattr(unreal, 'Paths'):
            saved = unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.project_saved_dir())
    except Exception as exc:
        if unreal is not None:
            unreal.log_warning("AnimaticRenderer: could not resolve Saved dir "
                               "({0}); using relative path".format(exc))
    return os.path.join(saved, "StoryboardTo3D", "Animatics")


def _normalize_asset_path(path):
    """Append the object name ('/Game/A/B' -> '/Game/A/B.B') if missing."""
    name = path.rsplit('/', 1)[-1]
    if '.' not in name:
        return "{0}.{1}".format(path, name)
    return path


def _current_level_path():
    """Best-effort object path of the currently loaded editor level."""
    if _get_class('UnrealEditorSubsystem') is not None:
        try:
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            if world:
                return world.get_path_name()
        except Exception:
            pass
    if _get_class('EditorLevelLibrary') is not None:
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            if world:
                return world.get_path_name()
        except Exception:
            pass
    return None


def render_animatic(master_sequence_path, level_path=None):
    """
    Render a master sequence to disk via Movie Render Queue.

    Writes a 1920x1080 PNG frame sequence (the most version-stable MRQ
    output; see the module docstring for the ffmpeg command that turns
    the frames into an MP4) to Saved/StoryboardTo3D/Animatics, falling
    back to Apple ProRes when the PNG class is missing. Rendering runs
    asynchronously in PIE; 'started' means MRQ accepted the job.

    Args:
        master_sequence_path: Content path of the master Level Sequence,
            e.g. '/Game/StoryboardSequences/MyShow/MyShow_Master_Sequence'.
        level_path: Optional content path of the map to render in. Defaults
            to the currently loaded editor level.

    Returns:
        Dict with 'status' ('started' or 'error'), 'output_dir', 'notes'.
    """
    global _ACTIVE_EXECUTOR
    if unreal is None:
        return _error("The 'unreal' module is unavailable. Run this inside "
                      "the Unreal Editor Python environment.")

    subsystem_cls = _get_class('MoviePipelineQueueSubsystem')
    job_cls = _get_class('MoviePipelineExecutorJob')
    executor_cls = _get_class('MoviePipelinePIEExecutor')
    output_setting_cls = _get_class('MoviePipelineOutputSetting')
    deferred_cls = _get_class('MoviePipelineDeferredPassBase')
    png_cls = _get_class('MoviePipelineImageSequenceOutput_PNG')
    prores_cls = _get_class('MoviePipelineAppleProResOutput')

    missing = [n for n, c in (
        ('MoviePipelineQueueSubsystem', subsystem_cls),
        ('MoviePipelineExecutorJob', job_cls),
        ('MoviePipelinePIEExecutor', executor_cls),
        ('MoviePipelineOutputSetting', output_setting_cls),
        ('MoviePipelineDeferredPassBase', deferred_cls),
    ) if c is None]
    if png_cls is None and prores_cls is None:
        missing.append('MoviePipelineImageSequenceOutput_PNG')
    if missing:
        return _error("{0} (missing: {1})".format(MRQ_MISSING_MSG, ', '.join(missing)))

    map_path = level_path or _current_level_path()
    if not map_path:
        return _error("Could not determine the current level. Pass level_path "
                      "explicitly, e.g. '/Game/Maps/MyMap'.")

    output_dir = _default_output_dir()
    try:
        os.makedirs(output_dir, exist_ok=True)

        subsystem = unreal.get_editor_subsystem(subsystem_cls)
        if subsystem is None:
            return _error(MRQ_MISSING_MSG)
        queue = subsystem.get_queue()
        for old_job in list(queue.get_jobs()):
            queue.delete_job(old_job)

        job = queue.allocate_new_job(job_cls)
        job.sequence = unreal.SoftObjectPath(_normalize_asset_path(master_sequence_path))
        job.map = unreal.SoftObjectPath(_normalize_asset_path(map_path))

        config = job.get_configuration()
        if png_cls is not None:
            output_format = 'PNG frame sequence'
            config.find_or_add_setting_by_class(png_cls)
        else:
            output_format = 'Apple ProRes movie'
            unreal.log_warning("AnimaticRenderer: PNG output class missing; "
                               "falling back to Apple ProRes")
            config.find_or_add_setting_by_class(prores_cls)

        out_setting = config.find_or_add_setting_by_class(output_setting_cls)
        dir_prop = unreal.DirectoryPath()
        dir_prop.set_editor_property('path', output_dir)
        out_setting.set_editor_property('output_directory', dir_prop)
        out_setting.set_editor_property('file_name_format', '{sequence_name}.{frame_number}')
        out_setting.set_editor_property('output_resolution', unreal.IntPoint(1920, 1080))

        config.find_or_add_setting_by_class(deferred_cls)

        _ACTIVE_EXECUTOR = executor_cls()
        if not hasattr(subsystem, 'render_queue_with_executor_instance'):
            return _error(MRQ_MISSING_MSG + " (render_queue_with_executor_instance not found)")
        subsystem.render_queue_with_executor_instance(_ACTIVE_EXECUTOR)
    except Exception as exc:
        return _error("MRQ render failed: {0}. If MRQ classes are missing, "
                      "enable the Movie Render Queue plugin.".format(exc))

    notes = ("Render started (PIE, asynchronous). Output: {0} at 1920x1080 in {1}. "
             "To make an MP4 from PNG frames: ffmpeg -framerate 30 -i "
             "\"<SequenceName>.%04d.png\" -c:v libx264 -pix_fmt yuv420p animatic.mp4"
             ).format(output_format, output_dir)
    unreal.log("AnimaticRenderer: {0}".format(notes))
    return {'status': 'started', 'output_dir': output_dir, 'notes': notes}

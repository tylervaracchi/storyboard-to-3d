# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
USD Exporter Module

Exports the currently loaded editor level to a USD file so scenes built by
StoryboardTo3D can travel to other DCCs (Houdini, Maya, Blender, Omniverse).

Uses unreal.AssetExportTask with the unreal.LevelExporterUSD exporter, plus
unreal.LevelExporterUSDOptions when the running engine exposes it. Both
classes ship with the 'USD Importer' plugin; if they are absent this module
returns a clear error instead of raising. All version-specific attribute
access is hasattr-guarded because the USD Python surface shifts across
UE 5.4 - 5.8.
"""

import os

try:
    import unreal
except ImportError:
    unreal = None

USD_MISSING_MSG = (
    "USD export classes are unavailable. Enable the 'USD Importer' plugin "
    "(Edit > Plugins > search 'USD'), restart the editor, and try again."
)

_USD_EXTENSIONS = ('.usd', '.usda', '.usdc', '.usdz')


def _error(message):
    if unreal is not None:
        unreal.log_error("UsdExporter: {0}".format(message))
    return {'status': 'error', 'error': message}


def _get_editor_world():
    """Best-effort handle to the currently loaded editor world."""
    if hasattr(unreal, 'UnrealEditorSubsystem'):
        try:
            world = unreal.get_editor_subsystem(
                unreal.UnrealEditorSubsystem).get_editor_world()
            if world:
                return world
        except Exception:
            pass
    if hasattr(unreal, 'EditorLevelLibrary'):
        try:
            return unreal.EditorLevelLibrary.get_editor_world()
        except Exception:
            pass
    return None


def export_level_usd(output_path):
    """
    Export the currently loaded editor level to a USD file.

    Args:
        output_path: Destination file path. Should end in .usd, .usda,
            .usdc, or .usdz; '.usda' is appended when the extension is
            not a USD one. Parent directories are created as needed.

    Returns:
        Dict with 'status' ('success' or 'error') and either 'path'
        (the file written) or 'error' (a human-readable message, e.g.
        instructions to enable the USD Importer plugin).
    """
    if unreal is None:
        return _error("The 'unreal' module is unavailable. Run this inside "
                      "the Unreal Editor Python environment.")

    if not hasattr(unreal, 'LevelExporterUSD') or not hasattr(unreal, 'AssetExportTask'):
        return _error(USD_MISSING_MSG)

    if not output_path:
        return _error("output_path is required, e.g. "
                      "'D:/Exports/my_scene.usda'.")
    if not str(output_path).lower().endswith(_USD_EXTENSIONS):
        output_path = "{0}.usda".format(output_path)
        unreal.log_warning(
            "UsdExporter: no USD extension given; writing {0}".format(output_path))

    world = _get_editor_world()
    if world is None:
        return _error("Could not resolve the current editor world; make sure "
                      "a level is loaded.")

    try:
        parent_dir = os.path.dirname(os.path.abspath(output_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        task = unreal.AssetExportTask()
        task.set_editor_property('object', world)
        task.set_editor_property('filename', output_path)
        task.set_editor_property('exporter', unreal.LevelExporterUSD())
        task.set_editor_property('automated', True)
        task.set_editor_property('prompt', False)
        task.set_editor_property('replace_identical', True)

        # Options class is version/plugin dependent; export works without it
        if hasattr(unreal, 'LevelExporterUSDOptions'):
            try:
                task.set_editor_property('options', unreal.LevelExporterUSDOptions())
            except Exception as exc:
                unreal.log_warning(
                    "UsdExporter: could not attach LevelExporterUSDOptions "
                    "({0}); exporting with defaults".format(exc))
        else:
            unreal.log_warning(
                "UsdExporter: LevelExporterUSDOptions not found in this "
                "engine version; exporting with defaults")

        if not (hasattr(unreal, 'Exporter')
                and hasattr(unreal.Exporter, 'run_asset_export_task')):
            return _error(USD_MISSING_MSG + " (Exporter.run_asset_export_task not found)")

        succeeded = unreal.Exporter.run_asset_export_task(task)

        task_errors = []
        try:
            task_errors = [str(e) for e in (task.get_editor_property('errors') or [])]
        except Exception:
            pass

        if not succeeded or task_errors:
            detail = '; '.join(task_errors) if task_errors else 'unknown exporter failure'
            return _error("USD export failed: {0}. If USD classes are missing "
                          "or the exporter refused the level, check that the "
                          "USD Importer plugin is enabled.".format(detail))
    except Exception as exc:
        return _error("USD export raised: {0}. If this mentions missing USD "
                      "classes, enable the USD Importer plugin.".format(exc))

    unreal.log("UsdExporter: level exported to {0}".format(output_path))
    return {'status': 'success', 'path': output_path}

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
StoryboardTo3D Plugin for Unreal Engine 5

Main entry point for plugin initialization and UI launch.
Provides the core interface for converting storyboard panels to 3D scenes.
"""

import unreal
import sys
from pathlib import Path


# Path Setup
plugin_path = Path(__file__).parent
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

# Global State
_window_instance = None
_initialized = False


def initialize_core_systems():
    """
    One-time initialization of all core systems.
    
    Returns:
        bool: True if initialization successful, False otherwise.
    """
    global _initialized
    if _initialized:
        return True

    unreal.log("Initializing StoryboardTo3D Plugin...")
    
    try:
        from asset_library_manager import get_asset_library
        get_asset_library()
        unreal.log("Asset library initialized")
    except Exception as e:
        unreal.log_warning(f"Asset library initialization: {e}")

    # Check Qt availability
    qt_available = check_qt_availability()
    if not qt_available:
        unreal.log_error("Qt not available - UI will not work")
        unreal.log_error("Please run: {0}".format(_qt_install_command()))
        _notify_qt_missing()
        return False

    # Initialize core modules
    try:
        from core.shows_manager import ShowsManager
        from core.episodes_manager import EpisodesManager
        from core.scene_builder import SceneBuilder
        from core.sequence_generator import SequenceGenerator
        unreal.log("Core modules loaded")
    except Exception as e:
        unreal.log_error(f"Core modules failed: {e}")
        return False

    _initialized = True
    unreal.log("Plugin initialization complete")
    return True


def _qt_install_command():
    """
    Build the exact pip command that installs the plugin's Python
    requirements into the engine's embedded Python.

    Returns:
        str: A copy-pasteable command line.
    """
    requirements = plugin_path / "requirements.txt"
    python_exe = "<UE engine Python>"
    try:
        engine_python = (Path(unreal.Paths.engine_dir()) / "Binaries" /
                         "ThirdParty" / "Python3" / "Win64" / "python.exe")
        if engine_python.exists():
            python_exe = str(engine_python)
    except Exception:
        pass
    return '"{0}" -m pip install -r "{1}"'.format(python_exe, requirements)


def _notify_qt_missing():
    """
    Surface the missing-Qt failure in an editor dialog (no Qt needed).

    Without this, a fresh install with no PySide6 fails invisibly unless
    the user has the Output Log open. unreal.EditorDialog draws with
    Slate, so it works precisely when Qt does not. Never raises.
    """
    message = (
        "The StoryboardTo3D window needs PySide6, which is not installed "
        "for Unreal's Python.\n\n"
        "Run this in a terminal, then restart Unreal:\n\n"
        "{0}".format(_qt_install_command())
    )
    try:
        if hasattr(unreal, "EditorDialog") and hasattr(unreal.EditorDialog, "show_message"):
            unreal.EditorDialog.show_message(
                "StoryboardTo3D - PySide6 Required",
                message,
                unreal.AppMsgType.OK
            )
    except Exception as e:
        unreal.log_warning(f"Could not show missing-Qt dialog: {e}")


def check_qt_availability():
    """
    Check which Qt version is available.

    Returns:
        str or None: "PySide6", "PySide2", or None if unavailable.
    """
    try:
        from PySide6.QtWidgets import QApplication
        import PySide6
        unreal.log(f"PySide6 available (v{PySide6.__version__})")
        return "PySide6"
    except ImportError:
        try:
            from PySide2.QtWidgets import QApplication
            unreal.log("PySide2 available (fallback mode)")
            return "PySide2"
        except ImportError:
            return None


def cleanup():
    """
    Cleanup window before reload.
    
    Call this BEFORE importlib.reload() to avoid EXCEPTION_ACCESS_VIOLATION.
    """
    global _window_instance

    if _window_instance is not None:
        try:
            unreal.log("Cleaning up old window...")
            _window_instance.close()
            _window_instance.deleteLater()
            unreal.log("Window cleanup complete")
        except Exception as e:
            unreal.log_warning(f"Cleanup error (non-critical): {e}")
        finally:
            _window_instance = None


def get_window():
    """
    Get the active window instance, or show it if not already open.
    
    Returns:
        ModernStoryboardWindow: The main window instance.
    
    Example:
        import main
        window = main.get_window()
        widget = window.active_panel_widget
    """
    global _window_instance

    if _window_instance is None:
        return show_window()

    try:
        if not _window_instance.isVisible():
            _window_instance.show()
            _window_instance.raise_()
            _window_instance.activateWindow()
    except:
        return show_window()

    return _window_instance


def get_active_panel():
    """
    Get the active panel widget for direct method access.
    
    Returns:
        ActivePanelWidget: The widget that handles positioning and iteration.
    
    Example:
        import main
        widget = main.get_active_panel()
        widget.test_positioning_phase3()
    """
    window = get_window()
    if window and hasattr(window, 'active_panel_widget'):
        return window.active_panel_widget
    return None


def show_window():
    """
    Show the StoryboardTo3D UI window.
    
    Returns:
        ModernStoryboardWindow: The main window instance, or None on failure.
    """
    global _window_instance

    # Initialize core systems if needed
    if not _initialized:
        if not initialize_core_systems():
            unreal.log_error("Failed to initialize core systems")
            return None

    # Check Qt
    qt_version = check_qt_availability()
    if not qt_version:
        unreal.log_error("Qt not available. Please install PySide6 or PySide2")
        unreal.log_error("Run: {0}".format(_qt_install_command()))
        _notify_qt_missing()
        return None

    # Import Qt
    if qt_version == "PySide6":
        from PySide6.QtWidgets import QApplication
    else:
        from PySide2.QtWidgets import QApplication

    # Get or create app
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Create or show window
    if not _window_instance:
        try:
            from ui.main_window import ModernStoryboardWindow
            _window_instance = ModernStoryboardWindow()
            unreal.log("UI window created")
        except Exception as e:
            unreal.log_error(f"Failed to create window: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return None

    _window_instance.show()
    _window_instance.raise_()
    _window_instance.activateWindow()

    # Keep window reference alive
    try:
        import __main__
        __main__.w = _window_instance
    except:
        pass

    return _window_instance


# Alias for convenience
launch = show_window


def quick_import(folder_path):
    """
    Quick import storyboard folder.
    
    Args:
        folder_path: Path to folder containing storyboard images.
    
    Returns:
        list: List of imported panel paths.
    """
    from core.shows_manager import ShowsManager
    from pathlib import Path

    folder = Path(folder_path)
    if not folder.exists():
        unreal.log_error(f"Folder not found: {folder_path}")
        return []

    # Find images
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_files.extend(folder.glob(ext))

    if image_files:
        manager = ShowsManager()
        show_name = folder.name
        show_path, metadata = manager.create_show(show_name)
        imported = manager.import_panels_to_show(
            metadata['safe_name'], 
            [str(f) for f in image_files]
        )
        unreal.log(f"Imported {len(imported)} panels to show: {show_name}")
        return imported
    else:
        unreal.log_warning("No images found in folder")
        return []


def test_systems():
    """
    Test all systems are working.
    
    Returns:
        bool: True if all systems pass, False otherwise.
    """
    unreal.log("StoryboardTo3D Systems Test")

    results = []

    # Test core imports
    try:
        from core.shows_manager import ShowsManager
        from core.episodes_manager import EpisodesManager
        from core.scene_builder import SceneBuilder
        from core.sequence_generator import SequenceGenerator
        from core.panel_analyzer import PanelAnalyzer
        from core.asset_matcher import AssetMatcher
        results.append(("Core modules", True))
    except ImportError as e:
        results.append(("Core modules", False, str(e)))

    # Test Qt
    qt = check_qt_availability()
    results.append((f"Qt ({qt})" if qt else "Qt", qt is not None))

    # Test AI client
    try:
        from api.ai_client_enhanced import AIClient
        results.append(("AI client", True))
    except:
        results.append(("AI client", False))

    # Test settings
    try:
        from core.settings_manager import get_settings
        settings = get_settings()
        results.append(("Settings manager", True))
    except:
        results.append(("Settings manager", False))

    # Log results
    for result in results:
        name = result[0]
        passed = result[1]
        status = "PASS" if passed else "FAIL"
        unreal.log(f"  {name}: {status}")

    return all(r[1] for r in results)


def on_unreal_shutdown():
    """Cleanup when Unreal is shutting down to prevent crash."""
    global _window_instance
    if _window_instance is not None:
        try:
            unreal.log("Unreal shutting down - cleaning up Qt window...")
            _window_instance.close()
            _window_instance.deleteLater()
            _window_instance = None
        except:
            pass


def register_mcp_toolset():
    """
    Attempt to load the optional UE 5.8+ MCP toolset.

    Safe on any engine version: mcp_toolset no-ops with a single log line
    below UE 5.8 (where unreal.ToolsetDefinition does not exist), and any
    unexpected import error is caught here so plugin startup never breaks.

    Returns:
        bool: True if the module imported cleanly, False otherwise.
    """
    try:
        import mcp_toolset  # noqa: F401 (import registers the toolset)
        return True
    except Exception as e:
        unreal.log_warning(f"Optional MCP toolset failed to load (non-critical): {e}")
        return False


# Auto-initialize on import
if __name__ != "__main__":
    initialize_core_systems()

    # Optional UE 5.8 MCP integration (no-op on older engines, never fatal)
    register_mcp_toolset()

    # Register shutdown cleanup
    try:
        import atexit
        atexit.register(on_unreal_shutdown)
    except:
        pass


# Direct execution
if __name__ == "__main__":
    window = show_window()
    if window:
        print("StoryboardTo3D ready")

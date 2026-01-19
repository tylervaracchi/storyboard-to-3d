# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
StoryboardTo3D Integration Verification
Run this in Unreal Python Console to verify everything is properly integrated
"""

import unreal
import sys
from pathlib import Path

def verify_integration():
    """
    Comprehensive integration verification
    Returns: (success: bool, report: str)
    """

    report_lines = []
    errors = []
    warnings = []

    report_lines.append("=" * 70)
    report_lines.append("STORYBOARD TO 3D - INTEGRATION VERIFICATION")
    report_lines.append("=" * 70)

    # 1. Check plugin path
    report_lines.append("\n Plugin Path Check")

    # Handle both normal import and exec() scenarios
    try:
        plugin_path = Path(__file__).parent.parent
    except NameError:
        # When run via exec(), __file__ is not defined
        plugin_path = Path(r"D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python")
        report_lines.append("   (Using hardcoded path - run via exec())")

    report_lines.append(f"Plugin location: {plugin_path}")

    if str(plugin_path) in sys.path:
        report_lines.append(" Plugin path in sys.path")
    else:
        errors.append("Plugin path NOT in sys.path")
        report_lines.append(f" Plugin path NOT in sys.path")
        report_lines.append(f"   Adding it now...")
        sys.path.insert(0, str(plugin_path))

    # 2. Check core modules
    report_lines.append("\n Core Modules")
    core_modules = [
        ('core.shows_manager', 'ShowsManager'),
        ('core.episodes_manager', 'EpisodesManager'),
        ('core.panel_analyzer', 'PanelAnalyzer'),
        ('core.asset_matcher', 'AssetMatcher'),
        ('core.scene_builder', 'SceneBuilder'),
        ('core.sequence_generator', 'SequenceGenerator'),
        ('core.utils', 'get_shows_manager'),
        ('core.settings_manager', 'get_settings_manager'),
    ]

    for module_name, class_name in core_modules:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)  # Verify class exists
            report_lines.append(f" {module_name}.{class_name}")
        except ImportError as e:
            errors.append(f"{module_name}: {e}")
            report_lines.append(f" {module_name}: Import failed")
        except AttributeError as e:
            errors.append(f"{module_name}.{class_name}: {e}")
            report_lines.append(f" {module_name}.{class_name}: Not found")
        except Exception as e:
            warnings.append(f"{module_name}: {e}")
            report_lines.append(f"  {module_name}: {e}")

    # 3. Check UI modules
    report_lines.append("\n UI Modules")
    ui_modules = [
        ('ui.main_window', 'ModernStoryboardWindow'),
        ('ui.settings.dialog', 'SettingsDialog'),
    ]

    for module_name, class_name in ui_modules:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            report_lines.append(f" {module_name}.{class_name}")
        except ImportError as e:
            errors.append(f"{module_name}: {e}")
            report_lines.append(f" {module_name}: Import failed")
        except Exception as e:
            warnings.append(f"{module_name}: {e}")
            report_lines.append(f"  {module_name}: {e}")

    # 4. Check Qt availability
    report_lines.append("\n🪟 Qt Framework")
    qt_available = False
    try:
        from PySide6.QtWidgets import QApplication
        report_lines.append(" PySide6 available")
        qt_available = True
    except ImportError:
        try:
            from PySide2.QtWidgets import QApplication
            report_lines.append(" PySide2 available (fallback)")
            qt_available = True
        except ImportError:
            errors.append("Qt not available (PySide6 or PySide2 required)")
            report_lines.append(" Qt not available")

    # 5. Check C++ bridge
    report_lines.append("\n C++ Bridge")
    try:
        bridge = unreal.StoryboardPythonBridge()
        project_dir = bridge.get_project_content_dir()
        report_lines.append(" C++ Bridge available")
        report_lines.append(f"   Project dir: {project_dir}")
    except Exception as e:
        warnings.append(f"C++ Bridge not available (Python-only mode): {e}")
        report_lines.append("  C++ Bridge not available (will use Python-only mode)")

    # 6. Check main.py functions
    report_lines.append("\n  Main Entry Points")
    try:
        import main
        if hasattr(main, 'show_window'):
            report_lines.append(" main.show_window() available")
        else:
            errors.append("main.show_window() not found")
            report_lines.append(" main.show_window() not found")

        if hasattr(main, 'initialize_core_systems'):
            report_lines.append(" main.initialize_core_systems() available")
        else:
            warnings.append("main.initialize_core_systems() not found")
            report_lines.append("  main.initialize_core_systems() not found")
    except ImportError as e:
        errors.append(f"main.py: {e}")
        report_lines.append(f" main.py import failed: {e}")

    # 7. Summary
    report_lines.append("\n" + "=" * 70)
    report_lines.append("SUMMARY")
    report_lines.append("=" * 70)

    if errors:
        report_lines.append(f"\n {len(errors)} CRITICAL ERROR(S) FOUND:")
        for error in errors:
            report_lines.append(f"   • {error}")

    if warnings:
        report_lines.append(f"\n  {len(warnings)} WARNING(S):")
        for warning in warnings:
            report_lines.append(f"   • {warning}")

    if not errors and not warnings:
        report_lines.append("\n ALL CHECKS PASSED!")
        report_lines.append("\n Plugin is fully integrated and ready to use!")
        report_lines.append("\n To launch:")
        report_lines.append("   import main")
        report_lines.append("   main.show_window()")
    elif not errors:
        report_lines.append("\n  PLUGIN READY WITH LIMITED FUNCTIONALITY")
        report_lines.append("\n To launch:")
        report_lines.append("   import main")
        report_lines.append("   main.show_window()")
    else:
        report_lines.append("\n PLUGIN NOT READY - FIX ERRORS ABOVE")

    report_lines.append("=" * 70)

    report = "\n".join(report_lines)
    success = len(errors) == 0

    return success, report

if __name__ == "__main__":
    # Run verification
    success, report = verify_integration()

    # Print report
    for line in report.split("\n"):
        unreal.log(line)

    # Return success status
    if success:
        unreal.log("\n Verification complete - Plugin ready!")
    else:
        unreal.log_error("\n Verification failed - See errors above")

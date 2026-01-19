# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Quick Integration Check - Safe for exec()
Run in Unreal Python Console
"""

import unreal
import sys
from pathlib import Path

# Add plugin path
plugin_path = Path(r"D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python")
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))
    unreal.log(f"Added to sys.path: {plugin_path}")

unreal.log("=" * 70)
unreal.log("QUICK INTEGRATION CHECK")
unreal.log("=" * 70)

errors = []
warnings = []

# Check core modules
unreal.log("\n Core Modules:")
try:
    from core import shows_manager, episodes_manager, scene_builder
    unreal.log("Core modules importable")
except Exception as e:
    errors.append(f"Core modules: {e}")
    unreal.log(f"Core modules: {e}")

# Check UI modules
unreal.log("\n UI Modules:")
try:
    from ui import main_window
    unreal.log("UI modules importable")
except Exception as e:
    errors.append(f"UI modules: {e}")
    unreal.log(f"UI modules: {e}")

# Check Qt
unreal.log("\n🪟 Qt Framework:")
qt_ok = False
try:
    from PySide6.QtWidgets import QApplication
    unreal.log("PySide6 available")
    qt_ok = True
except ImportError:
    try:
        from PySide2.QtWidgets import QApplication
        unreal.log("PySide2 available")
        qt_ok = True
    except ImportError:
        errors.append("No Qt framework (install PySide6)")
        unreal.log("No Qt (pip install PySide6)")

# Check main.py
unreal.log("\n  Entry Point:")
try:
    import main
    if hasattr(main, 'show_window'):
        unreal.log("main.show_window() available")
    else:
        errors.append("main.show_window() not found")
        unreal.log("main.show_window() missing")
except Exception as e:
    errors.append(f"main.py: {e}")
    unreal.log(f"main.py: {e}")

# Summary
unreal.log("\n" + "=" * 70)
if errors:
    unreal.log(f"FAILED: {len(errors)} error(s)")
    for err in errors:
        unreal.log(f"• {err}")
    unreal.log("\nFix errors above, then try:")
    unreal.log("exec(open(r'D:\\PythonStoryboardToUE\\LAUNCH_PLUGIN.py').read())")
else:
    unreal.log("ALL CHECKS PASSED!")
    unreal.log("\n Ready to launch! Run one of:")
    unreal.log("exec(open(r'D:\\PythonStoryboardToUE\\LAUNCH_PLUGIN.py').read())")
    unreal.log("OR")
    unreal.log("import main; main.show_window()")
unreal.log("=" * 70)

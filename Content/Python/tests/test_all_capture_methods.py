# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test ALL possible screenshot/capture methods in Unreal Engine Python API
Run this to discover what actually works in UE 5.6
"""

import unreal
import time
from pathlib import Path


def test_method_1_highresshot():
    """Method 1: HighResShot command (KNOWN TO WORK)"""
    print("\n" + "="*70)
    print("METHOD 1: HighResShot Command")
    print("="*70)

    try:
        unreal.SystemLibrary.execute_console_command(None, "HighResShot 1 filename=test_method1")
        time.sleep(3.0)

        screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
        files = list(screenshots_dir.glob("test_method1*.png"))

        if files:
            print(f"SUCCESS: {files[0].name}")
            return True
        else:
            print("FAILED: No file created")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_method_2_screenshot_systemlibrary():
    """Method 2: Screenshot via SystemLibrary"""
    print("\n" + "="*70)
    print("METHOD 2: Screenshot via SystemLibrary")
    print("="*70)

    try:
        # Delete old screenshots first
        screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
        before_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()

        unreal.SystemLibrary.execute_console_command(None, "Screenshot")
        time.sleep(3.0)

        after_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()
        new_files = after_files - before_files

        if new_files:
            print(f"SUCCESS: {len(new_files)} new files")
            return True
        else:
            print("FAILED: No new files created")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_method_3_screenshot_leveleditor():
    """Method 3: Screenshot via LevelEditorSubsystem"""
    print("\n" + "="*70)
    print("METHOD 3: Screenshot via LevelEditorSubsystem")
    print("="*70)

    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not level_editor:
            print("FAILED: LevelEditorSubsystem not available")
            return False

        screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
        before_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()

        level_editor.execute_console_command("Screenshot")
        time.sleep(3.0)

        after_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()
        new_files = after_files - before_files

        if new_files:
            print(f"SUCCESS: {len(new_files)} new files")
            return True
        else:
            print("FAILED: No new files created")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_method_4_automation_library():
    """Method 4: AutomationLibrary.take_automation_screenshot"""
    print("\n" + "="*70)
    print("METHOD 4: AutomationLibrary.take_automation_screenshot")
    print("="*70)

    try:
        automation_lib = unreal.AutomationLibrary()
        options = unreal.AutomationScreenshotOptions()
        options.resolution = unreal.Vector2D(800, 600)

        screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
        before_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()

        # Try different parameter combinations
        automation_lib.take_automation_screenshot("test_method4", None, "", "", options)
        time.sleep(3.0)

        after_files = set(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else set()
        new_files = after_files - before_files

        if new_files:
            print(f"SUCCESS: {len(new_files)} new files")
            return True
        else:
            print("FAILED: No new files created")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_method_5_editor_screenshot():
    """Method 5: EditorScreenshotLibrary (if it exists)"""
    print("\n" + "="*70)
    print("METHOD 5: EditorScreenshotLibrary (checking if exists)")
    print("="*70)

    try:
        # Check if this exists
        if hasattr(unreal, 'EditorScreenshotLibrary'):
            print("EditorScreenshotLibrary EXISTS!")
            # Try to use it
            return False  # Would need to test actual methods
        else:
            print("EditorScreenshotLibrary does not exist")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_method_6_take_screenshot():
    """Method 6: Direct take_screenshot if it exists"""
    print("\n" + "="*70)
    print("METHOD 6: Searching for any take_screenshot methods")
    print("="*70)

    # Search unreal module for screenshot methods
    screenshot_methods = []
    for item in dir(unreal):
        if 'screenshot' in item.lower():
            screenshot_methods.append(item)

    if screenshot_methods:
        print(f"Found {len(screenshot_methods)} screenshot-related items:")
        for method in screenshot_methods:
            print(f"- {method}")
        return False  # Just discovery
    else:
        print("No screenshot methods found")
        return False


def test_method_7_capture_methods():
    """Method 7: Search for any capture methods"""
    print("\n" + "="*70)
    print("METHOD 7: Searching for any capture methods")
    print("="*70)

    capture_methods = []
    for item in dir(unreal):
        if 'capture' in item.lower():
            capture_methods.append(item)

    if capture_methods:
        print(f"Found {len(capture_methods)} capture-related items:")
        for method in capture_methods:
            print(f"- {method}")
        return False  # Just discovery
    else:
        print("No capture methods found")
        return False


def run_all_tests():
    """Run all capture method tests"""
    print("\n" + "="*80)
    print("TESTING ALL POSSIBLE SCREENSHOT/CAPTURE METHODS")
    print("="*80)

    results = {
        "Method 1 (HighResShot)": test_method_1_highresshot(),
        "Method 2 (Screenshot SystemLibrary)": test_method_2_screenshot_systemlibrary(),
        "Method 3 (Screenshot LevelEditor)": test_method_3_screenshot_leveleditor(),
        "Method 4 (AutomationLibrary)": test_method_4_automation_library(),
        "Method 5 (EditorScreenshotLibrary)": test_method_5_editor_screenshot(),
        "Method 6 (Search screenshot methods)": test_method_6_take_screenshot(),
        "Method 7 (Search capture methods)": test_method_7_capture_methods(),
    }

    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)

    working_methods = []
    for method_name, success in results.items():
        status = " WORKS" if success else " DOESN'T WORK"
        print(f"{status}: {method_name}")
        if success:
            working_methods.append(method_name)

    print("\n" + "="*80)
    if working_methods:
        print(f"{len(working_methods)} WORKING METHOD(S) FOUND:")
        for method in working_methods:
            print(f"- {method}")
    else:
        print("NO WORKING METHODS FOUND")
    print("="*80)


# Run if executed directly
if __name__ == "__main__":
    run_all_tests()

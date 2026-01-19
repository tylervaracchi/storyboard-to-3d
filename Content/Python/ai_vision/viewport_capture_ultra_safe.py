# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ULTRA SAFE Viewport Capture - Using new recommended APIs
Avoids all deprecated functions
"""

import unreal
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

class ViewportCaptureUltraSafe:
    """
    Ultra-safe viewport capture using only the newest, safest APIs
    """

    def __init__(self):
        """Initialize with safe defaults"""
        self.capture_dir = Path(unreal.Paths.project_saved_dir()) / "ViewportCaptures"
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        unreal.log("[ViewportCaptureUltraSafe] Initialized")

    def take_screenshot_safest(self) -> Optional[str]:
        """
        The absolute safest way to take a screenshot
        Uses the new recommended subsystem instead of deprecated functions
        """
        try:
            unreal.log("[ViewportCaptureUltraSafe] Taking screenshot with safest method...")

            # Get the level editor subsystem (new recommended way)
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if level_editor_subsystem:
                # Execute console command through the subsystem
                level_editor_subsystem.execute_console_command("Screenshot")
                unreal.log("[ViewportCaptureUltraSafe] Screenshot command executed")

                # Wait for file
                time.sleep(1.0)

                # Find screenshot
                screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots"
                if screenshots_dir.exists():
                    # Look for any PNG files
                    png_files = list(screenshots_dir.rglob("*.png"))

                    if png_files:
                        # Get most recent
                        latest = max(png_files, key=lambda p: p.stat().st_mtime)
                        unreal.log(f"[ViewportCaptureUltraSafe] Found screenshot: {latest}")
                        return str(latest)

            # Fallback: Try without subsystem
            unreal.log("[ViewportCaptureUltraSafe] Trying fallback method...")
            unreal.SystemLibrary.execute_console_command(None, "Screenshot")

            time.sleep(1.0)

            screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots"
            if screenshots_dir.exists():
                png_files = list(screenshots_dir.rglob("*.png"))
                if png_files:
                    latest = max(png_files, key=lambda p: p.stat().st_mtime)
                    return str(latest)

            unreal.log_warning("[ViewportCaptureUltraSafe] No screenshot found")
            return None

        except Exception as e:
            unreal.log_error(f"[ViewportCaptureUltraSafe] Error: {e}")
            return None

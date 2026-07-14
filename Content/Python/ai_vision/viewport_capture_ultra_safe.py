# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
ULTRA SAFE Viewport Capture - Using new recommended APIs
Avoids all deprecated functions
"""

import unreal
import time
from pathlib import Path
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
        Take a viewport screenshot and return the newest capture file.

        Note: the Screenshot console command queues the capture for a future
        rendered frame, so this method snapshots the pre-existing files first
        and only returns a file that appeared (or was rewritten) after the
        command was issued - never a stale capture from an earlier run.
        """
        try:
            unreal.log("[ViewportCaptureUltraSafe] Taking screenshot...")

            screenshots_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots"
            before = {}
            if screenshots_dir.exists():
                before = {p: p.stat().st_mtime for p in screenshots_dir.rglob("*.png")}

            issued_at = time.time()
            # SystemLibrary is the console-command API that exists across UE 5.4-5.8.
            # (LevelEditorSubsystem has no execute_console_command method.)
            unreal.SystemLibrary.execute_console_command(None, "Screenshot")

            # The engine needs to render at least one frame to fulfill the request.
            # Poll briefly; on an idle editor the file typically lands well under 5s.
            deadline = time.time() + 10.0
            while time.time() < deadline:
                time.sleep(0.25)
                if not screenshots_dir.exists():
                    continue
                for p in screenshots_dir.rglob("*.png"):
                    mtime = p.stat().st_mtime
                    if mtime >= issued_at and (p not in before or mtime > before[p]):
                        unreal.log(f"[ViewportCaptureUltraSafe] Captured: {p}")
                        return str(p)

            unreal.log_warning(
                "[ViewportCaptureUltraSafe] No new screenshot appeared within 10s. "
                "The editor may not have rendered a frame while Python was blocking; "
                "prefer unreal.AutomationLibrary.take_high_res_screenshot for async capture."
            )
            return None

        except Exception as e:
            unreal.log_error(f"[ViewportCaptureUltraSafe] Error: {e}")
            return None

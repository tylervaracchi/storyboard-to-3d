# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Debug Logger System with Levels
Centralized logging with configurable verbosity levels
"""

import unreal
from enum import IntEnum
from typing import Any, Optional
import traceback
from datetime import datetime

class LogLevel(IntEnum):
    """Logging levels (lower number = more verbose)"""
    DEBUG = 0      # Everything including debug info
    INFO = 1       # Normal operations
    WARNING = 2    # Warnings and important info
    ERROR = 3      # Errors only
    CRITICAL = 4   # Critical errors only
    SILENT = 5     # No logging

class DebugLogger:
    """
    Centralized logging system with levels

    Usage:
        from core.debug_logger import logger

        logger.debug("Detailed info")
        logger.info("Normal operation")
        logger.warning("Something to note")
        logger.error("Something went wrong")
        logger.critical("Critical failure")
    """

    def __init__(self):
        self._level = LogLevel.INFO  # Default level
        self._log_to_file = False
        self._log_file_path = None
        self._include_timestamp = True
        self._include_module = True

        # Color codes for terminal (if supported)
        self._colors = {
            'DEBUG': '',
            'INFO': '',
            'WARNING': '',
            'ERROR': '',
            'CRITICAL': ''
        }

    def set_level(self, level: LogLevel):
        """Set the logging level"""
        self._level = level
        level_names = {
            LogLevel.DEBUG: "DEBUG",
            LogLevel.INFO: "INFO",
            LogLevel.WARNING: "WARNING",
            LogLevel.ERROR: "ERROR",
            LogLevel.CRITICAL: "CRITICAL",
            LogLevel.SILENT: "SILENT"
        }
        unreal.log(f"Logger level set to: {level_names.get(level, 'UNKNOWN')}")

    def get_level(self) -> LogLevel:
        """Get current logging level"""
        return self._level

    def enable_file_logging(self, file_path: str):
        """Enable logging to file"""
        self._log_to_file = True
        self._log_file_path = file_path
        unreal.log(f"File logging enabled: {file_path}")

    def disable_file_logging(self):
        """Disable logging to file"""
        self._log_to_file = False
        unreal.log("File logging disabled")

    def debug(self, message: str, module: Optional[str] = None):
        """Log debug message (most verbose)"""
        self._log(LogLevel.DEBUG, message, module)

    def info(self, message: str, module: Optional[str] = None):
        """Log info message (normal operations)"""
        self._log(LogLevel.INFO, message, module)

    def warning(self, message: str, module: Optional[str] = None):
        """Log warning message"""
        self._log(LogLevel.WARNING, message, module)

    def error(self, message: str, module: Optional[str] = None, exc_info: bool = False):
        """Log error message"""
        self._log(LogLevel.ERROR, message, module)
        if exc_info:
            self._log_exception()

    def critical(self, message: str, module: Optional[str] = None, exc_info: bool = False):
        """Log critical error message"""
        self._log(LogLevel.CRITICAL, message, module)
        if exc_info:
            self._log_exception()

    def _log(self, level: LogLevel, message: str, module: Optional[str] = None):
        """Internal logging method"""
        # Check if message should be logged based on level
        if level < self._level:
            return

        # Build log message
        parts = []

        # Add timestamp
        if self._include_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            parts.append(f"[{timestamp}]")

        # Add level with icon
        level_name = LogLevel(level).name
        icon = self._colors.get(level_name, '')
        parts.append(f"{icon} [{level_name}]")

        # Add module
        if self._include_module and module:
            parts.append(f"[{module}]")

        # Add message
        parts.append(message)

        formatted_message = " ".join(parts)

        # Output to Unreal log with appropriate function
        if level >= LogLevel.CRITICAL:
            unreal.log_error(formatted_message)
        elif level >= LogLevel.ERROR:
            unreal.log_error(formatted_message)
        elif level >= LogLevel.WARNING:
            unreal.log_warning(formatted_message)
        else:
            unreal.log(formatted_message)

        # Output to file if enabled
        if self._log_to_file and self._log_file_path:
            self._write_to_file(formatted_message)

    def _log_exception(self):
        """Log exception traceback"""
        tb = traceback.format_exc()
        self._log(LogLevel.ERROR, f"Exception traceback:\n{tb}", None)

    def _write_to_file(self, message: str):
        """Write log message to file"""
        try:
            with open(self._log_file_path, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception as e:
            unreal.log_error(f"Failed to write to log file: {e}")

    # Context managers for temporary level changes

    class LevelContext:
        """Context manager for temporary level change"""
        def __init__(self, logger, level):
            self.logger = logger
            self.level = level
            self.old_level = None

        def __enter__(self):
            self.old_level = self.logger.get_level()
            self.logger.set_level(self.level)
            return self

        def __exit__(self, *args):
            self.logger.set_level(self.old_level)

    def temporary_level(self, level: LogLevel):
        """
        Context manager for temporary level change

        Usage:
            with logger.temporary_level(LogLevel.DEBUG):
                # Detailed logging here
                logger.debug("This will show")
        """
        return self.LevelContext(self, level)


# Global logger instance
logger = DebugLogger()

# Convenience functions

def set_debug_mode(enabled: bool = True):
    """Quick function to enable/disable debug mode"""
    if enabled:
        logger.set_level(LogLevel.DEBUG)
        unreal.log("Debug mode ENABLED - All logs will be shown")
    else:
        logger.set_level(LogLevel.INFO)
        unreal.log("ℹ Debug mode DISABLED - Normal logging")

def set_quiet_mode(enabled: bool = True):
    """Quick function to enable/disable quiet mode"""
    if enabled:
        logger.set_level(LogLevel.WARNING)
        unreal.log("Quiet mode ENABLED - Only warnings and errors")
    else:
        logger.set_level(LogLevel.INFO)
        unreal.log("Quiet mode DISABLED - Normal logging")

def set_silent_mode(enabled: bool = True):
    """Quick function to enable/disable silent mode"""
    if enabled:
        logger.set_level(LogLevel.SILENT)
    else:
        logger.set_level(LogLevel.INFO)
        unreal.log("Silent mode DISABLED - Normal logging")


# Example usage and testing

def test_logger():
    """Test all logging levels"""
    unreal.log("\n" + "="*70)
    unreal.log("TESTING DEBUG LOGGER")
    unreal.log("="*70)

    # Test all levels
    unreal.log("\n1. Testing at INFO level (default):")
    logger.set_level(LogLevel.INFO)
    logger.debug("This is a DEBUG message (should not show)")
    logger.info("This is an INFO message (should show)")
    logger.warning("This is a WARNING message (should show)")
    logger.error("This is an ERROR message (should show)")
    logger.critical("This is a CRITICAL message (should show)")

    # Test DEBUG level
    unreal.log("\n2. Testing at DEBUG level (verbose):")
    logger.set_level(LogLevel.DEBUG)
    logger.debug("This DEBUG message should now show")
    logger.info("Info message")

    # Test WARNING level
    unreal.log("\n3. Testing at WARNING level (quiet):")
    logger.set_level(LogLevel.WARNING)
    logger.debug("Debug message (hidden)")
    logger.info("Info message (hidden)")
    logger.warning("Warning message (shown)")
    logger.error("Error message (shown)")

    # Test with module names
    unreal.log("\n4. Testing with module names:")
    logger.set_level(LogLevel.INFO)
    logger.info("Message from scene_builder", module="scene_builder")
    logger.warning("Message from camera_system", module="camera_system")

    # Test context manager
    unreal.log("\n5. Testing temporary level context:")
    logger.set_level(LogLevel.WARNING)
    logger.debug("Before context (hidden)")

    with logger.temporary_level(LogLevel.DEBUG):
        logger.debug("Inside context (shown)")

    logger.debug("After context (hidden again)")

    # Reset to normal
    logger.set_level(LogLevel.INFO)

    unreal.log("\n" + "="*70)
    unreal.log("Logger test complete")
    unreal.log("="*70 + "\n")


if __name__ == "__main__":
    unreal.log("Debug Logger System Loaded")
    unreal.log("Usage: from core.debug_logger import logger")
    unreal.log("logger.info('My message')")
    unreal.log("logger.set_level(LogLevel.DEBUG)")

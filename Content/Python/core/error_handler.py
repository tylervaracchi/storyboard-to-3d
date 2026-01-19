# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Error Handler - Production error collection for batch operations
"""

import unreal
from datetime import datetime

class OperationErrorCollector:
    """Collects errors during batch operations"""

    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.errors = []
        self.warnings = []
        self.start_time = datetime.now()

    def add_error(self, item_name, error_message):
        """Add an error"""
        self.errors.append({
            'item': item_name,
            'message': str(error_message),
            'timestamp': datetime.now()
        })
        unreal.log_error(f"[{self.operation_name}] Error on {item_name}: {error_message}")

    def add_warning(self, item_name, warning_message):
        """Add a warning"""
        self.warnings.append({
            'item': item_name,
            'message': str(warning_message),
            'timestamp': datetime.now()
        })
        unreal.log_warning(f"[{self.operation_name}] Warning on {item_name}: {warning_message}")

    def has_errors(self):
        """Check if any errors occurred"""
        return len(self.errors) > 0

    def get_summary(self):
        """Get operation summary"""
        duration = (datetime.now() - self.start_time).total_seconds()

        summary = f"\n{'='*60}\n"
        summary += f"Operation: {self.operation_name}\n"
        summary += f"Duration: {duration:.2f}s\n"
        summary += f"Errors: {len(self.errors)}\n"
        summary += f"Warnings: {len(self.warnings)}\n"

        if self.errors:
            summary += f"\nERRORS:\n"
            for err in self.errors:
                summary += f"  - {err['item']}: {err['message']}\n"

        if self.warnings:
            summary += f"\nWARNINGS:\n"
            for warn in self.warnings:
                summary += f"  - {warn['item']}: {warn['message']}\n"

        summary += f"{'='*60}\n"

        return summary

    def log_summary(self):
        """Log the summary"""
        unreal.log(self.get_summary())

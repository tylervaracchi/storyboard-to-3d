# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Advanced Settings Tab for StoryboardTo3D
"""

import unreal
from pathlib import Path

try:
    from PySide6.QtWidgets import *
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    USING_PYSIDE6 = True
except ImportError:
    from PySide2.QtWidgets import *
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    USING_PYSIDE6 = False


class AdvancedTab(QWidget):
    """Advanced settings tab"""

    settings_changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Debug Options
        debug_group = QGroupBox("Debug Options")
        debug_layout = QVBoxLayout()

        # Enable debug mode
        self.debug_mode_check = QCheckBox("Enable debug mode")
        self.debug_mode_check.stateChanged.connect(self.on_change)
        debug_layout.addWidget(self.debug_mode_check)

        # Verbose logging
        self.verbose_logging_check = QCheckBox("Verbose logging")
        self.verbose_logging_check.stateChanged.connect(self.on_change)
        debug_layout.addWidget(self.verbose_logging_check)

        # Log AI requests
        self.log_ai_requests_check = QCheckBox("Log AI requests/responses")
        self.log_ai_requests_check.stateChanged.connect(self.on_change)
        debug_layout.addWidget(self.log_ai_requests_check)

        # Show timings
        self.show_timings_check = QCheckBox("Show operation timings")
        self.show_timings_check.stateChanged.connect(self.on_change)
        debug_layout.addWidget(self.show_timings_check)

        # Save debug info
        self.save_debug_info_check = QCheckBox("Save debug information to file")
        self.save_debug_info_check.stateChanged.connect(self.on_change)
        debug_layout.addWidget(self.save_debug_info_check)

        debug_group.setLayout(debug_layout)
        layout.addWidget(debug_group)

        # Experimental Features
        experimental_group = QGroupBox("Experimental Features")
        experimental_layout = QVBoxLayout()

        warning_label = QLabel(" These features may be unstable")
        warning_label.setStyleSheet("color: #FFA500; font-style: italic;")
        experimental_layout.addWidget(warning_label)

        # Multi-panel generation
        self.multi_panel_gen_check = QCheckBox("Enable multi-panel batch generation")
        self.multi_panel_gen_check.stateChanged.connect(self.on_change)
        experimental_layout.addWidget(self.multi_panel_gen_check)

        # Auto scene matching
        self.auto_scene_match_check = QCheckBox("Auto-match scenes across panels")
        self.auto_scene_match_check.stateChanged.connect(self.on_change)
        experimental_layout.addWidget(self.auto_scene_match_check)

        # AI-powered camera
        self.ai_camera_check = QCheckBox("AI-powered camera movements")
        self.ai_camera_check.stateChanged.connect(self.on_change)
        experimental_layout.addWidget(self.ai_camera_check)

        # Smart asset suggestions
        self.smart_assets_check = QCheckBox("Smart asset suggestions")
        self.smart_assets_check.stateChanged.connect(self.on_change)
        experimental_layout.addWidget(self.smart_assets_check)

        # Real-time preview
        self.realtime_preview_check = QCheckBox("Real-time 3D preview")
        self.realtime_preview_check.stateChanged.connect(self.on_change)
        experimental_layout.addWidget(self.realtime_preview_check)

        experimental_group.setLayout(experimental_layout)
        layout.addWidget(experimental_group)

        # Cache Management
        cache_group = QGroupBox("Cache Management")
        cache_layout = QVBoxLayout()

        # Cache info
        cache_info_layout = QHBoxLayout()
        cache_info_layout.addWidget(QLabel("Cache Size:"))
        self.cache_size_label = QLabel("Calculating...")
        cache_info_layout.addWidget(self.cache_size_label)
        cache_info_layout.addStretch()

        self.calculate_cache_btn = QPushButton("Calculate")
        self.calculate_cache_btn.clicked.connect(self.calculate_cache_size)
        cache_info_layout.addWidget(self.calculate_cache_btn)

        cache_layout.addLayout(cache_info_layout)

        # Cache limits
        cache_limit_layout = QHBoxLayout()
        cache_limit_layout.addWidget(QLabel("Max Cache Size:"))
        self.cache_limit_spin = QSpinBox()
        self.cache_limit_spin.setRange(100, 10000)
        self.cache_limit_spin.setSuffix(" MB")
        self.cache_limit_spin.setValue(1000)
        self.cache_limit_spin.valueChanged.connect(self.on_change)
        cache_limit_layout.addWidget(self.cache_limit_spin)
        cache_limit_layout.addStretch()
        cache_layout.addLayout(cache_limit_layout)

        # Clear cache buttons
        cache_btn_layout = QHBoxLayout()

        clear_analysis_btn = QPushButton("Clear Analysis Cache")
        clear_analysis_btn.clicked.connect(self.clear_analysis_cache)
        cache_btn_layout.addWidget(clear_analysis_btn)

        clear_thumbnails_btn = QPushButton("Clear Thumbnails")
        clear_thumbnails_btn.clicked.connect(self.clear_thumbnails_cache)
        cache_btn_layout.addWidget(clear_thumbnails_btn)

        clear_all_btn = QPushButton("Clear All Cache")
        clear_all_btn.clicked.connect(self.clear_all_cache)
        cache_btn_layout.addWidget(clear_all_btn)

        cache_btn_layout.addStretch()
        cache_layout.addLayout(cache_btn_layout)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # Developer Options
        dev_group = QGroupBox("Developer Options")
        dev_layout = QVBoxLayout()

        # Show internal data
        self.show_internal_data_check = QCheckBox("Show internal data structures")
        self.show_internal_data_check.stateChanged.connect(self.on_change)
        dev_layout.addWidget(self.show_internal_data_check)

        # Enable hot reload
        self.hot_reload_check = QCheckBox("Enable hot reload")
        self.hot_reload_check.stateChanged.connect(self.on_change)
        dev_layout.addWidget(self.hot_reload_check)

        # Skip validation
        self.skip_validation_check = QCheckBox("Skip validation checks")
        self.skip_validation_check.stateChanged.connect(self.on_change)
        dev_layout.addWidget(self.skip_validation_check)

        # Console output
        self.console_output_check = QCheckBox("Enable console output")
        self.console_output_check.stateChanged.connect(self.on_change)
        dev_layout.addWidget(self.console_output_check)

        dev_group.setLayout(dev_layout)
        layout.addWidget(dev_group)

        # Reset buttons
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()

        reset_tab_btn = QPushButton("Reset Tab")
        reset_tab_btn.clicked.connect(self.reset_tab_settings)
        reset_layout.addWidget(reset_tab_btn)

        reset_all_btn = QPushButton("Reset All Settings")
        reset_all_btn.clicked.connect(self.reset_all_settings)
        reset_all_btn.setStyleSheet("QPushButton { color: #FF6B6B; }")
        reset_layout.addWidget(reset_all_btn)

        layout.addLayout(reset_layout)

        layout.addStretch()

    def on_change(self):
        """Handle any change"""
        self.settings_changed.emit()

    def calculate_cache_size(self):
        """Calculate cache size"""
        try:
            from pathlib import Path
            cache_path = Path(__file__).parent.parent.parent / ".cache"

            if cache_path.exists():
                size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                self.cache_size_label.setText(f"{size_mb:.1f} MB")
            else:
                self.cache_size_label.setText("0 MB")
        except Exception as e:
            self.cache_size_label.setText("Error")
            unreal.log_error(f"Failed to calculate cache size: {e}")

    def clear_analysis_cache(self):
        """Clear analysis cache"""
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Clear all AI analysis cache?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                cache_path = Path(__file__).parent.parent.parent / ".cache" / "ai_analysis"
                if cache_path.exists():
                    import shutil
                    shutil.rmtree(cache_path)
                    cache_path.mkdir(parents=True, exist_ok=True)
                QMessageBox.information(self, "Success", "Analysis cache cleared")
                self.calculate_cache_size()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear cache: {e}")

    def clear_thumbnails_cache(self):
        """Clear thumbnails cache"""
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Clear all thumbnail cache?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                cache_path = Path(__file__).parent.parent.parent / ".cache" / "thumbnails"
                if cache_path.exists():
                    import shutil
                    shutil.rmtree(cache_path)
                    cache_path.mkdir(parents=True, exist_ok=True)
                QMessageBox.information(self, "Success", "Thumbnail cache cleared")
                self.calculate_cache_size()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear cache: {e}")

    def clear_all_cache(self):
        """Clear all cache"""
        reply = QMessageBox.question(
            self,
            "Clear All Cache",
            "This will clear ALL cached data. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                cache_path = Path(__file__).parent.parent.parent / ".cache"
                if cache_path.exists():
                    import shutil
                    shutil.rmtree(cache_path)
                    cache_path.mkdir(parents=True, exist_ok=True)
                QMessageBox.information(self, "Success", "All cache cleared")
                self.cache_size_label.setText("0 MB")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear cache: {e}")

    def reset_tab_settings(self):
        """Reset this tab's settings to defaults"""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset advanced settings to defaults?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Reset to defaults
            self.debug_mode_check.setChecked(False)
            self.verbose_logging_check.setChecked(False)
            self.log_ai_requests_check.setChecked(False)
            self.show_timings_check.setChecked(False)
            self.save_debug_info_check.setChecked(False)

            self.multi_panel_gen_check.setChecked(False)
            self.auto_scene_match_check.setChecked(False)
            self.ai_camera_check.setChecked(False)
            self.smart_assets_check.setChecked(False)
            self.realtime_preview_check.setChecked(False)

            self.cache_limit_spin.setValue(1000)

            self.show_internal_data_check.setChecked(False)
            self.hot_reload_check.setChecked(False)
            self.skip_validation_check.setChecked(False)
            self.console_output_check.setChecked(False)

            self.on_change()

    def reset_all_settings(self):
        """Reset ALL settings to defaults"""
        reply = QMessageBox.question(
            self,
            "Reset All Settings",
            "This will reset ALL settings to defaults.\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # This would trigger a full reset in the parent dialog
            self.parent().parent().reset_all_settings()

    def load_settings(self):
        """Load settings into UI"""
        debug = self.settings.get('debug', {})
        experimental = self.settings.get('experimental', {})
        cache = self.settings.get('cache', {})
        developer = self.settings.get('developer', {})

        # Debug options
        self.debug_mode_check.setChecked(debug.get('debug_mode', False))
        self.verbose_logging_check.setChecked(debug.get('verbose_logging', False))
        self.log_ai_requests_check.setChecked(debug.get('log_ai_requests', False))
        self.show_timings_check.setChecked(debug.get('show_timings', False))
        self.save_debug_info_check.setChecked(debug.get('save_debug_info', False))

        # Experimental features
        self.multi_panel_gen_check.setChecked(experimental.get('multi_panel_generation', False))
        self.auto_scene_match_check.setChecked(experimental.get('auto_scene_matching', False))
        self.ai_camera_check.setChecked(experimental.get('ai_camera_movements', False))
        self.smart_assets_check.setChecked(experimental.get('smart_asset_suggestions', False))
        self.realtime_preview_check.setChecked(experimental.get('realtime_preview', False))

        # Cache management
        self.cache_limit_spin.setValue(cache.get('max_cache_size_mb', 1000))
        self.calculate_cache_size()

        # Developer options
        self.show_internal_data_check.setChecked(developer.get('show_internal_data', False))
        self.hot_reload_check.setChecked(developer.get('hot_reload', False))
        self.skip_validation_check.setChecked(developer.get('skip_validation', False))
        self.console_output_check.setChecked(developer.get('console_output', False))

    def get_settings(self):
        """Get settings from UI"""
        return {
            'debug': {
                'debug_mode': self.debug_mode_check.isChecked(),
                'verbose_logging': self.verbose_logging_check.isChecked(),
                'log_ai_requests': self.log_ai_requests_check.isChecked(),
                'show_timings': self.show_timings_check.isChecked(),
                'save_debug_info': self.save_debug_info_check.isChecked()
            },
            'experimental': {
                'multi_panel_generation': self.multi_panel_gen_check.isChecked(),
                'auto_scene_matching': self.auto_scene_match_check.isChecked(),
                'ai_camera_movements': self.ai_camera_check.isChecked(),
                'smart_asset_suggestions': self.smart_assets_check.isChecked(),
                'realtime_preview': self.realtime_preview_check.isChecked()
            },
            'cache': {
                'max_cache_size_mb': self.cache_limit_spin.value()
            },
            'developer': {
                'show_internal_data': self.show_internal_data_check.isChecked(),
                'hot_reload': self.hot_reload_check.isChecked(),
                'skip_validation': self.skip_validation_check.isChecked(),
                'console_output': self.console_output_check.isChecked()
            }
        }

    def on_settings_saved(self):
        """Called when settings are saved"""
        pass

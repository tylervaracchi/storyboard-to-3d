# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
General Settings Tab for StoryboardTo3D
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


class GeneralTab(QWidget):
    """General settings tab"""

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

        # UI Preferences
        ui_group = QGroupBox("UI Preferences")
        ui_layout = QVBoxLayout()

        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "Auto"])
        self.theme_combo.currentTextChanged.connect(self.on_change)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        ui_layout.addLayout(theme_layout)

        # Auto-save
        self.auto_save_check = QCheckBox("Auto-save project changes")
        self.auto_save_check.stateChanged.connect(self.on_change)
        ui_layout.addWidget(self.auto_save_check)

        # Auto-backup
        self.auto_backup_check = QCheckBox("Create automatic backups")
        self.auto_backup_check.stateChanged.connect(self.on_change)
        ui_layout.addWidget(self.auto_backup_check)

        # Backup interval
        backup_layout = QHBoxLayout()
        backup_layout.addWidget(QLabel("Backup interval:"))
        self.backup_interval_spin = QSpinBox()
        self.backup_interval_spin.setRange(5, 60)
        self.backup_interval_spin.setSuffix(" minutes")
        self.backup_interval_spin.valueChanged.connect(self.on_change)
        backup_layout.addWidget(self.backup_interval_spin)
        backup_layout.addStretch()
        ui_layout.addLayout(backup_layout)

        # Show tooltips
        self.show_tooltips_check = QCheckBox("Show helpful tooltips")
        self.show_tooltips_check.stateChanged.connect(self.on_change)
        ui_layout.addWidget(self.show_tooltips_check)

        # Confirm deletions
        self.confirm_delete_check = QCheckBox("Confirm before deleting")
        self.confirm_delete_check.stateChanged.connect(self.on_change)
        ui_layout.addWidget(self.confirm_delete_check)

        ui_group.setLayout(ui_layout)
        layout.addWidget(ui_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout()

        # Thumbnail size
        thumb_layout = QHBoxLayout()
        thumb_layout.addWidget(QLabel("Thumbnail size:"))
        self.thumb_size_combo = QComboBox()
        self.thumb_size_combo.addItems(["Small (80px)", "Medium (120px)", "Large (160px)"])
        self.thumb_size_combo.currentTextChanged.connect(self.on_change)
        thumb_layout.addWidget(self.thumb_size_combo)
        thumb_layout.addStretch()
        perf_layout.addLayout(thumb_layout)

        # Max panels to display
        panels_layout = QHBoxLayout()
        panels_layout.addWidget(QLabel("Max panels to display:"))
        self.max_panels_spin = QSpinBox()
        self.max_panels_spin.setRange(10, 200)
        self.max_panels_spin.setSingleStep(10)
        self.max_panels_spin.valueChanged.connect(self.on_change)
        panels_layout.addWidget(self.max_panels_spin)
        panels_layout.addStretch()
        perf_layout.addLayout(panels_layout)

        # Cache AI responses
        self.cache_ai_check = QCheckBox("Cache AI analysis results")
        self.cache_ai_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.cache_ai_check)

        # Hardware acceleration
        self.hw_accel_check = QCheckBox("Enable hardware acceleration")
        self.hw_accel_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.hw_accel_check)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Default Settings
        defaults_group = QGroupBox("Defaults")
        defaults_layout = QVBoxLayout()

        # Default panel duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Default panel duration:"))
        self.default_duration_spin = QDoubleSpinBox()
        self.default_duration_spin.setRange(0.5, 10.0)
        self.default_duration_spin.setSingleStep(0.5)
        self.default_duration_spin.setSuffix(" seconds")
        self.default_duration_spin.valueChanged.connect(self.on_change)
        duration_layout.addWidget(self.default_duration_spin)
        duration_layout.addStretch()
        defaults_layout.addLayout(duration_layout)

        # Default shot type
        shot_layout = QHBoxLayout()
        shot_layout.addWidget(QLabel("Default shot type:"))
        self.default_shot_combo = QComboBox()
        self.default_shot_combo.addItems(["Auto", "Wide", "Medium", "Close-up", "ECU", "OTS", "POV"])
        self.default_shot_combo.currentTextChanged.connect(self.on_change)
        shot_layout.addWidget(self.default_shot_combo)
        shot_layout.addStretch()
        defaults_layout.addLayout(shot_layout)

        defaults_group.setLayout(defaults_layout)
        layout.addWidget(defaults_group)

        layout.addStretch()

    def on_change(self):
        """Handle any change"""
        self.settings_changed.emit()

    def load_settings(self):
        """Load settings into UI"""
        general = self.settings.get('general', {})
        ui_prefs = self.settings.get('ui_preferences', {})
        performance = self.settings.get('performance', {})
        defaults = self.settings.get('defaults', {})

        # UI Preferences
        self.theme_combo.setCurrentText(ui_prefs.get('theme', 'Dark'))
        self.auto_save_check.setChecked(general.get('auto_save', True))
        self.auto_backup_check.setChecked(general.get('auto_backup', True))
        self.backup_interval_spin.setValue(general.get('backup_interval', 10))
        self.show_tooltips_check.setChecked(ui_prefs.get('show_tooltips', True))
        self.confirm_delete_check.setChecked(ui_prefs.get('confirm_delete', True))

        # Performance
        thumb_size = performance.get('thumbnail_size', 120)
        if thumb_size <= 80:
            self.thumb_size_combo.setCurrentIndex(0)
        elif thumb_size <= 120:
            self.thumb_size_combo.setCurrentIndex(1)
        else:
            self.thumb_size_combo.setCurrentIndex(2)

        self.max_panels_spin.setValue(performance.get('max_panels_display', 50))
        self.cache_ai_check.setChecked(performance.get('cache_ai_results', True))
        self.hw_accel_check.setChecked(performance.get('hardware_acceleration', True))

        # Defaults
        self.default_duration_spin.setValue(defaults.get('panel_duration', 3.0))
        self.default_shot_combo.setCurrentText(defaults.get('shot_type', 'Auto'))

    def get_settings(self):
        """Get settings from UI"""
        # Parse thumbnail size
        thumb_text = self.thumb_size_combo.currentText()
        if "80" in thumb_text:
            thumb_size = 80
        elif "120" in thumb_text:
            thumb_size = 120
        else:
            thumb_size = 160

        return {
            'general': {
                'auto_save': self.auto_save_check.isChecked(),
                'auto_backup': self.auto_backup_check.isChecked(),
                'backup_interval': self.backup_interval_spin.value()
            },
            'ui_preferences': {
                'theme': self.theme_combo.currentText(),
                'show_tooltips': self.show_tooltips_check.isChecked(),
                'confirm_delete': self.confirm_delete_check.isChecked()
            },
            'performance': {
                'thumbnail_size': thumb_size,
                'max_panels_display': self.max_panels_spin.value(),
                'cache_ai_results': self.cache_ai_check.isChecked(),
                'hardware_acceleration': self.hw_accel_check.isChecked()
            },
            'defaults': {
                'panel_duration': self.default_duration_spin.value(),
                'shot_type': self.default_shot_combo.currentText()
            }
        }

    def on_settings_saved(self):
        """Called when settings are saved"""
        pass

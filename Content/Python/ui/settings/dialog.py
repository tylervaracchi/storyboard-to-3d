# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Settings Dialog for StoryboardTo3D - Refactored Main Dialog
Split from the massive 111KB file into manageable modules
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

# Import settings tabs
from .tabs import (
    GeneralTab,
    AISettingsTab,
    OllamaSettingsTab,
    PathsTab,
    AdvancedTab
)

# Import settings manager
from core.settings_manager import get_settings, update_settings


class SettingsDialog(QDialog):
    """Main settings dialog - refactored version"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.changes_made = False

        self.setWindowTitle("StoryboardTo3D Settings")
        self.setModal(True)
        self.setMinimumSize(800, 600)

        self.setup_ui()
        self.apply_theme()
        self.load_current_settings()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("settingsTabWidget")

        # Create tabs
        self.general_tab = GeneralTab(self.settings)
        self.ai_tab = AISettingsTab(self.settings)
        self.ollama_tab = OllamaSettingsTab(self.settings)
        self.paths_tab = PathsTab(self.settings)
        self.advanced_tab = AdvancedTab(self.settings)

        # Add tabs
        self.tab_widget.addTab(self.general_tab, " General")
        self.tab_widget.addTab(self.ai_tab, " AI Settings")
        self.tab_widget.addTab(self.ollama_tab, " Ollama")
        self.tab_widget.addTab(self.paths_tab, " Paths")
        self.tab_widget.addTab(self.advanced_tab, " Advanced")

        layout.addWidget(self.tab_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Apply button
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_settings)
        button_layout.addWidget(self.apply_btn)

        # OK button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.ok_clicked)
        self.ok_btn.setDefault(True)
        button_layout.addWidget(self.ok_btn)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Connect change signals
        self.connect_change_signals()

    def connect_change_signals(self):
        """Connect signals to track changes"""
        # Each tab should emit settings_changed signal
        self.general_tab.settings_changed.connect(self.on_settings_changed)
        self.ai_tab.settings_changed.connect(self.on_settings_changed)
        self.ollama_tab.settings_changed.connect(self.on_settings_changed)
        self.paths_tab.settings_changed.connect(self.on_settings_changed)
        self.advanced_tab.settings_changed.connect(self.on_settings_changed)

    def on_settings_changed(self):
        """Handle settings change"""
        self.changes_made = True
        self.apply_btn.setEnabled(True)

    def load_current_settings(self):
        """Load current settings into UI"""
        # Each tab loads its own settings
        self.general_tab.load_settings()
        self.ai_tab.load_settings()
        self.ollama_tab.load_settings()
        self.paths_tab.load_settings()
        self.advanced_tab.load_settings()

        self.apply_btn.setEnabled(False)

    def apply_settings(self):
        """Apply settings without closing"""
        # Gather settings from all tabs
        new_settings = {}
        new_settings.update(self.general_tab.get_settings())
        new_settings.update(self.ai_tab.get_settings())
        new_settings.update(self.ollama_tab.get_settings())
        new_settings.update(self.paths_tab.get_settings())
        new_settings.update(self.advanced_tab.get_settings())

        # Save settings
        if update_settings(new_settings):
            self.settings = new_settings
            self.changes_made = False
            self.apply_btn.setEnabled(False)
            unreal.log("Settings applied successfully")

            # Notify tabs that settings were saved
            self.general_tab.on_settings_saved()
            self.ai_tab.on_settings_saved()
            self.ollama_tab.on_settings_saved()
            self.paths_tab.on_settings_saved()
            self.advanced_tab.on_settings_saved()
        else:
            QMessageBox.warning(self, "Error", "Failed to save settings")

    def ok_clicked(self):
        """OK button clicked"""
        if self.changes_made:
            self.apply_settings()
        self.accept()

    def apply_theme(self):
        """Apply dark theme to dialog"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1A1A1A;
                color: #CCCCCC;
            }

            QTabWidget::pane {
                border: 1px solid #2A2A2A;
                background-color: #0A0A0A;
            }

            QTabBar::tab {
                background-color: #1A1A1A;
                color: #CCCCCC;
                padding: 8px 16px;
                margin-right: 2px;
            }

            QTabBar::tab:selected {
                background-color: #0EA5E9;
                color: #FFFFFF;
            }

            QTabBar::tab:hover {
                background-color: #2A2A2A;
            }

            QPushButton {
                background-color: #2A2A2A;
                color: #CCCCCC;
                border: 1px solid #3A3A3A;
                padding: 6px 16px;
                border-radius: 4px;
            }

            QPushButton:hover {
                background-color: #3A3A3A;
            }

            QPushButton:pressed {
                background-color: #0EA5E9;
            }

            QGroupBox {
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                color: #CCCCCC;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #0EA5E9;
            }

            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #0A0A0A;
                border: 1px solid #2A2A2A;
                color: #CCCCCC;
                padding: 4px;
                border-radius: 4px;
            }

            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #0EA5E9;
            }

            QCheckBox {
                color: #CCCCCC;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }

            QCheckBox::indicator:unchecked {
                background-color: #0A0A0A;
                border: 1px solid #2A2A2A;
                border-radius: 2px;
            }

            QCheckBox::indicator:checked {
                background-color: #0EA5E9;
                border: 1px solid #0EA5E9;
                border-radius: 2px;
            }

            QSlider::groove:horizontal {
                border: 1px solid #2A2A2A;
                height: 6px;
                background: #0A0A0A;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                background: #0EA5E9;
                border: 1px solid #0EA5E9;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }

            QListWidget {
                background-color: #0A0A0A;
                border: 1px solid #2A2A2A;
                color: #CCCCCC;
            }

            QListWidget::item:selected {
                background-color: #0EA5E9;
            }

            QTextEdit {
                background-color: #0A0A0A;
                border: 1px solid #2A2A2A;
                color: #CCCCCC;
            }

            QLabel {
                color: #CCCCCC;
            }
        """)

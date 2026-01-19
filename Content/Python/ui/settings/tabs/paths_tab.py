# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Paths Settings Tab for StoryboardTo3D
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


class PathsTab(QWidget):
    """Paths configuration settings tab"""

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

        # Content Paths
        content_group = QGroupBox("Content Paths")
        content_layout = QVBoxLayout()

        # Shows root path
        shows_layout = QHBoxLayout()
        shows_layout.addWidget(QLabel("Shows Root:"))
        self.shows_path_edit = QLineEdit()
        self.shows_path_edit.setReadOnly(True)
        self.shows_path_edit.textChanged.connect(self.on_change)
        shows_layout.addWidget(self.shows_path_edit)

        shows_browse_btn = QPushButton("Browse")
        shows_browse_btn.clicked.connect(lambda: self.browse_path(self.shows_path_edit))
        shows_layout.addWidget(shows_browse_btn)

        content_layout.addLayout(shows_layout)

        # Templates path
        templates_layout = QHBoxLayout()
        templates_layout.addWidget(QLabel("Templates:"))
        self.templates_path_edit = QLineEdit()
        self.templates_path_edit.textChanged.connect(self.on_change)
        templates_layout.addWidget(self.templates_path_edit)

        templates_browse_btn = QPushButton("Browse")
        templates_browse_btn.clicked.connect(lambda: self.browse_path(self.templates_path_edit))
        templates_layout.addWidget(templates_browse_btn)

        content_layout.addLayout(templates_layout)

        # Cache path
        cache_layout = QHBoxLayout()
        cache_layout.addWidget(QLabel("Cache:"))
        self.cache_path_edit = QLineEdit()
        self.cache_path_edit.textChanged.connect(self.on_change)
        cache_layout.addWidget(self.cache_path_edit)

        cache_browse_btn = QPushButton("Browse")
        cache_browse_btn.clicked.connect(lambda: self.browse_path(self.cache_path_edit))
        cache_layout.addWidget(cache_browse_btn)

        content_layout.addLayout(cache_layout)

        # Backups path
        backups_layout = QHBoxLayout()
        backups_layout.addWidget(QLabel("Backups:"))
        self.backups_path_edit = QLineEdit()
        self.backups_path_edit.textChanged.connect(self.on_change)
        backups_layout.addWidget(self.backups_path_edit)

        backups_browse_btn = QPushButton("Browse")
        backups_browse_btn.clicked.connect(lambda: self.browse_path(self.backups_path_edit))
        backups_layout.addWidget(backups_browse_btn)

        content_layout.addLayout(backups_layout)

        content_group.setLayout(content_layout)
        layout.addWidget(content_group)

        # Export Paths
        export_group = QGroupBox("Export Paths")
        export_layout = QVBoxLayout()

        # Default export path
        export_default_layout = QHBoxLayout()
        export_default_layout.addWidget(QLabel("Default Export:"))
        self.export_path_edit = QLineEdit()
        self.export_path_edit.textChanged.connect(self.on_change)
        export_default_layout.addWidget(self.export_path_edit)

        export_browse_btn = QPushButton("Browse")
        export_browse_btn.clicked.connect(lambda: self.browse_path(self.export_path_edit))
        export_default_layout.addWidget(export_browse_btn)

        export_layout.addLayout(export_default_layout)

        # Renders path
        renders_layout = QHBoxLayout()
        renders_layout.addWidget(QLabel("Renders:"))
        self.renders_path_edit = QLineEdit()
        self.renders_path_edit.textChanged.connect(self.on_change)
        renders_layout.addWidget(self.renders_path_edit)

        renders_browse_btn = QPushButton("Browse")
        renders_browse_btn.clicked.connect(lambda: self.browse_path(self.renders_path_edit))
        renders_layout.addWidget(renders_browse_btn)

        export_layout.addLayout(renders_layout)

        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        # File Management
        file_group = QGroupBox("File Management")
        file_layout = QVBoxLayout()

        # Auto-organize files
        self.auto_organize_check = QCheckBox("Auto-organize imported files")
        self.auto_organize_check.stateChanged.connect(self.on_change)
        file_layout.addWidget(self.auto_organize_check)

        # Copy files on import
        self.copy_on_import_check = QCheckBox("Copy files on import (vs. reference)")
        self.copy_on_import_check.stateChanged.connect(self.on_change)
        file_layout.addWidget(self.copy_on_import_check)

        # Convert images to standard format
        self.convert_images_check = QCheckBox("Convert images to standard format")
        self.convert_images_check.stateChanged.connect(self.on_change)
        file_layout.addWidget(self.convert_images_check)

        # Image format
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Image format:"))
        self.image_format_combo = QComboBox()
        self.image_format_combo.addItems(["PNG", "JPG", "TGA", "EXR"])
        self.image_format_combo.currentTextChanged.connect(self.on_change)
        format_layout.addWidget(self.image_format_combo)
        format_layout.addStretch()
        file_layout.addLayout(format_layout)

        # Max image resolution
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(QLabel("Max resolution:"))
        self.max_resolution_combo = QComboBox()
        self.max_resolution_combo.addItems(["Original", "2048", "4096", "8192"])
        self.max_resolution_combo.currentTextChanged.connect(self.on_change)
        resolution_layout.addWidget(self.max_resolution_combo)
        resolution_layout.addStretch()
        file_layout.addLayout(resolution_layout)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Path shortcuts info
        info_group = QGroupBox("Path Variables")
        info_layout = QVBoxLayout()

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(100)
        info_text.setHtml("""
        <style>
            body { color: #CCCCCC; font-size: 11px; }
            code { color: #0EA5E9; }
        </style>
        <body>
        <p>You can use these variables in paths:</p>
        <ul>
            <li><code>{project}</code> - Current project directory</li>
            <li><code>{content}</code> - Content folder</li>
            <li><code>{plugin}</code> - Plugin directory</li>
            <li><code>{show}</code> - Current show name</li>
            <li><code>{episode}</code> - Current episode name</li>
        </ul>
        </body>
        """)
        info_layout.addWidget(info_text)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        layout.addStretch()

    def on_change(self):
        """Handle any change"""
        self.settings_changed.emit()

    def browse_path(self, line_edit):
        """Browse for folder"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            line_edit.text() or str(Path.home())
        )

        if folder:
            line_edit.setText(folder)

    def load_settings(self):
        """Load settings into UI"""
        paths = self.settings.get('paths', {})
        file_management = self.settings.get('file_management', {})

        # Content paths
        self.shows_path_edit.setText(paths.get('shows_root', '/Game/Content/StoryboardTo3D/Shows'))
        self.templates_path_edit.setText(paths.get('templates', '{plugin}/Templates'))
        self.cache_path_edit.setText(paths.get('cache', '{plugin}/.cache'))
        self.backups_path_edit.setText(paths.get('backups', '{content}/StoryboardTo3D/Settings/backups'))

        # Export paths
        self.export_path_edit.setText(paths.get('export_default', '{project}/Exports'))
        self.renders_path_edit.setText(paths.get('renders', '{project}/Renders'))

        # File management
        self.auto_organize_check.setChecked(file_management.get('auto_organize', True))
        self.copy_on_import_check.setChecked(file_management.get('copy_on_import', True))
        self.convert_images_check.setChecked(file_management.get('convert_images', False))
        self.image_format_combo.setCurrentText(file_management.get('image_format', 'PNG'))
        self.max_resolution_combo.setCurrentText(file_management.get('max_resolution', 'Original'))

    def get_settings(self):
        """Get settings from UI"""
        return {
            'paths': {
                'shows_root': self.shows_path_edit.text(),
                'templates': self.templates_path_edit.text(),
                'cache': self.cache_path_edit.text(),
                'backups': self.backups_path_edit.text(),
                'export_default': self.export_path_edit.text(),
                'renders': self.renders_path_edit.text()
            },
            'file_management': {
                'auto_organize': self.auto_organize_check.isChecked(),
                'copy_on_import': self.copy_on_import_check.isChecked(),
                'convert_images': self.convert_images_check.isChecked(),
                'image_format': self.image_format_combo.currentText(),
                'max_resolution': self.max_resolution_combo.currentText()
            }
        }

    def on_settings_saved(self):
        """Called when settings are saved"""
        pass

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Asset Library management widget for StoryboardTo3D
"""

import json
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


class AssetLibraryWidget(QWidget):
    """Widget for managing show asset library"""

    library_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_show = None
        self.current_show_path = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        self.setObjectName("assetLibraryColumn")
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ASSET LIBRARY header
        header = self.create_section_header("ASSET LIBRARY")
        layout.addWidget(header)

        # Content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Current show name
        self.asset_lib_show_label = QLabel("No show selected")
        self.asset_lib_show_label.setStyleSheet("color: #0EA5E9; font-size: 11px; font-weight: bold; padding: 5px;")
        content_layout.addWidget(self.asset_lib_show_label)

        # Scroll area for asset mappings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Characters mapping
        char_group = QGroupBox("Characters")
        char_layout = QVBoxLayout()

        self.char_mappings_list = QListWidget()
        self.char_mappings_list.setMaximumHeight(120)
        char_layout.addWidget(self.char_mappings_list)

        char_btn_layout = QHBoxLayout()
        add_char_map_btn = QPushButton("+")
        add_char_map_btn.setMaximumWidth(30)
        add_char_map_btn.clicked.connect(self.add_character_mapping)
        char_btn_layout.addWidget(add_char_map_btn)

        edit_char_map_btn = QPushButton("")
        edit_char_map_btn.setMaximumWidth(30)
        edit_char_map_btn.clicked.connect(self.edit_character_mapping)
        char_btn_layout.addWidget(edit_char_map_btn)

        remove_char_map_btn = QPushButton("-")
        remove_char_map_btn.setMaximumWidth(30)
        remove_char_map_btn.clicked.connect(self.remove_character_mapping)
        char_btn_layout.addWidget(remove_char_map_btn)

        char_btn_layout.addStretch()
        char_layout.addLayout(char_btn_layout)
        char_group.setLayout(char_layout)
        scroll_layout.addWidget(char_group)

        # Props mapping
        props_group = QGroupBox("Props")
        props_layout = QVBoxLayout()

        self.prop_mappings_list = QListWidget()
        self.prop_mappings_list.setMaximumHeight(120)
        props_layout.addWidget(self.prop_mappings_list)

        props_btn_layout = QHBoxLayout()
        add_prop_map_btn = QPushButton("+")
        add_prop_map_btn.setMaximumWidth(30)
        add_prop_map_btn.clicked.connect(self.add_prop_mapping)
        props_btn_layout.addWidget(add_prop_map_btn)

        edit_prop_map_btn = QPushButton("")
        edit_prop_map_btn.setMaximumWidth(30)
        edit_prop_map_btn.clicked.connect(self.edit_prop_mapping)
        props_btn_layout.addWidget(edit_prop_map_btn)

        remove_prop_map_btn = QPushButton("-")
        remove_prop_map_btn.setMaximumWidth(30)
        remove_prop_map_btn.clicked.connect(self.remove_prop_mapping)
        props_btn_layout.addWidget(remove_prop_map_btn)

        props_btn_layout.addStretch()
        props_layout.addLayout(props_btn_layout)
        props_group.setLayout(props_layout)
        scroll_layout.addWidget(props_group)

        # Locations mapping
        locations_group = QGroupBox("Locations")
        locations_layout = QVBoxLayout()

        self.location_mappings_list = QListWidget()
        self.location_mappings_list.setMaximumHeight(120)
        locations_layout.addWidget(self.location_mappings_list)

        locations_btn_layout = QHBoxLayout()
        add_location_map_btn = QPushButton("+")
        add_location_map_btn.setMaximumWidth(30)
        add_location_map_btn.clicked.connect(self.add_location_mapping)
        locations_btn_layout.addWidget(add_location_map_btn)

        edit_location_map_btn = QPushButton("")
        edit_location_map_btn.setMaximumWidth(30)
        edit_location_map_btn.clicked.connect(self.edit_location_mapping)
        locations_btn_layout.addWidget(edit_location_map_btn)

        remove_location_map_btn = QPushButton("-")
        remove_location_map_btn.setMaximumWidth(30)
        remove_location_map_btn.clicked.connect(self.remove_location_mapping)
        locations_btn_layout.addWidget(remove_location_map_btn)

        locations_btn_layout.addStretch()
        locations_layout.addLayout(locations_btn_layout)
        locations_group.setLayout(locations_layout)
        scroll_layout.addWidget(locations_group)

        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        content_layout.addWidget(scroll)

        # Scan button at bottom
        scan_btn = QPushButton(" Scan Assets")
        scan_btn.clicked.connect(self.scan_for_show_assets)
        content_layout.addWidget(scan_btn)

        # Auto-save note
        auto_save_label = QLabel(" Auto-saves on changes")
        auto_save_label.setStyleSheet("color: #4ADE80; font-size: 10px; padding: 5px;")
        auto_save_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(auto_save_label)

        layout.addWidget(content_widget)

    def create_section_header(self, text):
        """Create section header"""
        header = QWidget()
        header.setObjectName("sectionHeader")
        header.setFixedHeight(35)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 0, 10, 0)

        label = QLabel(text)
        label.setObjectName("sectionHeaderText")
        layout.addWidget(label)

        return header

    def set_show(self, show_data):
        """Set the current show and load its asset library"""
        if show_data:
            self.current_show = show_data['safe_name']
            from core.shows_manager import ShowsManager
            self.current_show_path = ShowsManager().shows_root / self.current_show
            self.asset_lib_show_label.setText(f"Show: {show_data['name']}")
            self.load_show_asset_library()
        else:
            self.current_show = None
            self.current_show_path = None
            self.asset_lib_show_label.setText("No show selected")
            self.clear_library()

    def load_show_asset_library(self):
        """Load asset library for current show"""
        if not self.current_show:
            return

        # Clear lists
        self.char_mappings_list.clear()
        self.prop_mappings_list.clear()
        self.location_mappings_list.clear()

        # Load library
        library_path = self.current_show_path / "asset_library.json"
        if library_path.exists():
            with open(library_path, 'r') as f:
                library = json.load(f)

                # Load characters
                for name, path in library.get('characters', {}).items():
                    self.char_mappings_list.addItem(f"{name} → {path}")

                # Load props
                for name, path in library.get('props', {}).items():
                    self.prop_mappings_list.addItem(f"{name} → {path}")

                # Load locations
                for name, path in library.get('locations', {}).items():
                    self.location_mappings_list.addItem(f"{name} → {path}")

    def clear_library(self):
        """Clear the library lists"""
        self.char_mappings_list.clear()
        self.prop_mappings_list.clear()
        self.location_mappings_list.clear()

    def auto_save_asset_library(self):
        """Auto-save asset library silently"""
        if not self.current_show:
            return

        library = {
            'characters': {},
            'props': {},
            'locations': {}
        }

        # Save characters
        for i in range(self.char_mappings_list.count()):
            text = self.char_mappings_list.item(i).text()
            if ' → ' in text:
                name, path = text.split(' → ')
                library['characters'][name] = path

        # Save props
        for i in range(self.prop_mappings_list.count()):
            text = self.prop_mappings_list.item(i).text()
            if ' → ' in text:
                name, path = text.split(' → ')
                library['props'][name] = path

        # Save locations
        for i in range(self.location_mappings_list.count()):
            text = self.location_mappings_list.item(i).text()
            if ' → ' in text:
                name, path = text.split(' → ')
                library['locations'][name] = path

        # Write file
        library_path = self.current_show_path / "asset_library.json"
        with open(library_path, 'w') as f:
            json.dump(library, f, indent=2)

        unreal.log(f"Auto-saved asset library for show: {self.current_show}")
        self.library_updated.emit()

    def add_character_mapping(self):
        """Add character to asset mapping"""
        self.add_asset_mapping('Character', self.char_mappings_list)
        self.auto_save_asset_library()

    def edit_character_mapping(self):
        """Edit selected character mapping"""
        self.edit_asset_mapping(self.char_mappings_list)
        self.auto_save_asset_library()

    def remove_character_mapping(self):
        """Remove selected character mapping"""
        current = self.char_mappings_list.currentItem()
        if current:
            self.char_mappings_list.takeItem(self.char_mappings_list.row(current))
            self.auto_save_asset_library()

    def add_prop_mapping(self):
        """Add prop to asset mapping"""
        self.add_asset_mapping('Prop', self.prop_mappings_list)
        self.auto_save_asset_library()

    def edit_prop_mapping(self):
        """Edit selected prop mapping"""
        self.edit_asset_mapping(self.prop_mappings_list)
        self.auto_save_asset_library()

    def remove_prop_mapping(self):
        """Remove selected prop mapping"""
        current = self.prop_mappings_list.currentItem()
        if current:
            self.prop_mappings_list.takeItem(self.prop_mappings_list.row(current))
            self.auto_save_asset_library()

    def add_location_mapping(self):
        """Add location to asset mapping"""
        self.add_asset_mapping('Location', self.location_mappings_list)
        self.auto_save_asset_library()

    def edit_location_mapping(self):
        """Edit selected location mapping"""
        self.edit_asset_mapping(self.location_mappings_list)
        self.auto_save_asset_library()

    def remove_location_mapping(self):
        """Remove selected location mapping"""
        current = self.location_mappings_list.currentItem()
        if current:
            self.location_mappings_list.takeItem(self.location_mappings_list.row(current))
            self.auto_save_asset_library()

    def add_asset_mapping(self, asset_type, list_widget):
        """Generic method to add asset mapping"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add {asset_type} Mapping")
        dialog.setModal(True)

        layout = QFormLayout()

        name_edit = QLineEdit()
        path_edit = QLineEdit()
        path_edit.setPlaceholderText(f"/Game/Path/To/{asset_type}")

        layout.addRow("Name:", name_edit)
        layout.addRow("Asset Path:", path_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        dialog.setLayout(layout)

        if dialog.exec_():
            name = name_edit.text()
            path = path_edit.text()
            if name and path:
                list_widget.addItem(f"{name} → {path}")

    def edit_asset_mapping(self, list_widget):
        """Edit selected asset mapping"""
        current = list_widget.currentItem()
        if not current:
            return

        text = current.text()
        if ' → ' not in text:
            return

        name, path = text.split(' → ')

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Mapping")
        dialog.setModal(True)

        layout = QFormLayout()

        name_edit = QLineEdit(name)
        path_edit = QLineEdit(path)

        layout.addRow("Name:", name_edit)
        layout.addRow("Asset Path:", path_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        dialog.setLayout(layout)

        if dialog.exec_():
            new_name = name_edit.text()
            new_path = path_edit.text()
            if new_name and new_path:
                current.setText(f"{new_name} → {new_path}")

    def scan_for_show_assets(self):
        """Scan Content Browser for available assets"""
        unreal.log("Scanning Content Browser for assets...")

        # Get asset registry
        asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

        # Count assets by type
        skeletal_meshes = asset_registry.get_assets_by_class("SkeletalMesh")
        static_meshes = asset_registry.get_assets_by_class("StaticMesh")
        blueprints = asset_registry.get_assets_by_class("Blueprint")
        worlds = asset_registry.get_assets_by_class("World")

        msg = f"Found:\n"
        msg += f"• {len(skeletal_meshes)} Skeletal Meshes\n"
        msg += f"• {len(static_meshes)} Static Meshes\n"
        msg += f"• {len(blueprints)} Blueprints\n"
        msg += f"• {len(worlds)} Levels"

        QMessageBox.information(self, "Asset Scan", msg)

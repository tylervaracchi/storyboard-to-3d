# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
ASSET LIBRARY UI WIDGET WITH THUMBNAILS
Full implementation for the StoryboardTo3D UI - SHOW SPECIFIC VERSION
"""

import unreal
import json
import re
from pathlib import Path
from core.utils import sanitize_asset_data, ensure_library_structure, get_shows_manager

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

# Content Browser asset name prefixes stripped when prettifying names
ASSET_NAME_PREFIXES = ('SM_', 'SK_', 'BP_')


def prettify_asset_name(raw_name):
    """Turn an asset name like SM_HayBale_01 into a display name (Hay Bale 01).

    Strips a leading SM_/SK_/BP_ prefix, then splits on underscores, dashes
    and camelCase boundaries. Acronyms and digit runs are kept as-is.
    """
    name = str(raw_name)
    for prefix in ASSET_NAME_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    words = []
    for chunk in name.replace('-', '_').split('_'):
        if not chunk:
            continue
        parts = re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+', chunk)
        if not parts:
            parts = [chunk]
        for word in parts:
            if word.isupper() or word.isdigit():
                words.append(word)
            else:
                words.append(word[0].upper() + word[1:])
    return ' '.join(words) if words else str(raw_name)


def _asset_is_instance_of(asset, class_name):
    """isinstance check against an unreal class that may not exist in
    every engine version. Never raises."""
    cls = getattr(unreal, class_name, None)
    if cls is None:
        return False
    try:
        return isinstance(asset, cls)
    except Exception:
        return False


def build_entry_from_asset(asset):
    """Build an asset library entry from a loaded Unreal asset object.

    Pure helper (no UI, no disk writes) so it can be tested headlessly.
    Supports StaticMesh, SkeletalMesh and Blueprint assets.

    Returns a dict:
        {
            'name': prettified display name,
            'category': suggested category ('characters' for SkeletalMesh
                        and Blueprint assets, 'props' otherwise),
            'entry': {'asset_path', 'description', 'aliases', 'thumbnail'}
        }
    or None when the asset is unsupported or unreadable.
    """
    if asset is None:
        return None
    is_skeletal = _asset_is_instance_of(asset, 'SkeletalMesh')
    is_blueprint = _asset_is_instance_of(asset, 'Blueprint')
    is_static = _asset_is_instance_of(asset, 'StaticMesh')
    is_world = _asset_is_instance_of(asset, 'World')
    if not (is_static or is_skeletal or is_blueprint or is_world):
        return None
    try:
        raw_name = str(asset.get_name())
    except Exception:
        raw_name = 'Asset'
    try:
        asset_path = str(asset.get_path_name())
    except Exception as e:
        unreal.log_warning(f"build_entry_from_asset: get_path_name failed: {e}")
        return None
    # Object paths look like /Pkg/Name.Name; the library stores the
    # package form (/Pkg/Name), which every loader in this codebase accepts
    if '.' in asset_path:
        package, obj_name = asset_path.rsplit('.', 1)
        if package.rsplit('/', 1)[-1] == obj_name:
            asset_path = package
    if is_world:
        category = 'locations'
    elif is_skeletal or is_blueprint:
        category = 'characters'
    else:
        category = 'props'
    return {
        'name': prettify_asset_name(raw_name),
        'category': category,
        'entry': {
            'asset_path': asset_path,
            'description': '',
            'aliases': [],
            'thumbnail': {'type': 'none', 'path': None},
        },
    }

class ShowSpecificAssetLibrary:
    """Asset library manager for a specific show"""

    def __init__(self, show_path=None):
        self.show_path = show_path
        self.library = {}
        # Don't auto-load on init

    def set_show(self, show_path):
        """Change the current show"""
        self.show_path = show_path
        self.load_library()  # Load only once here

    def load_library(self):
        """Load the asset library for current show"""
        if not self.show_path:
            self.library = ensure_library_structure({})
            return

        library_path = Path(self.show_path) / "asset_library.json"
        if library_path.exists():
            try:
                with open(library_path, 'r') as f:
                    raw_library = json.load(f)
                    # Sanitize all assets on load
                    self.library = ensure_library_structure(raw_library)
                    for category in self.library:
                        if isinstance(self.library[category], dict):
                            for name in list(self.library[category].keys()):
                                self.library[category][name] = sanitize_asset_data(
                                    self.library[category][name]
                                )
                    unreal.log(f"Loaded asset library for show: {self.show_path.name}")
            except Exception as e:
                unreal.log_warning(f"Failed to load asset library: {e}")
                self.library = ensure_library_structure({})
        else:
            self.library = ensure_library_structure({})
            unreal.log(f"Created new asset library for show: {self.show_path.name if self.show_path else 'No show'}")

    def save_library(self):
        """Save the library to the show folder"""
        if not self.show_path:
            unreal.log_warning("No show selected, cannot save asset library")
            return

        library_path = Path(self.show_path) / "asset_library.json"
        try:
            with open(library_path, 'w') as f:
                json.dump(self.library, f, indent=2)
            unreal.log(f"Saved asset library for show: {self.show_path.name}")
        except Exception as e:
            unreal.log_error(f"Failed to save asset library: {e}")

    def add_asset(self, category, name, asset_path, description, aliases, save=True):
        """Add or update an asset in the library.

        Pass save=False when adding many assets in a loop and call
        save_library() once at the end (avoids one full-file write per
        asset)."""
        if category not in self.library:
            self.library[category] = {}

        # Get thumbnail info if it already exists
        existing = self.library[category].get(name, {})
        thumbnail_info = existing.get("thumbnail", {"type": "placeholder", "path": None})

        self.library[category][name] = {
            "asset_path": asset_path,
            "description": description,
            "aliases": aliases or [],
            "thumbnail": thumbnail_info
        }

        if save:
            self.save_library()


class AssetLibraryWidget(QWidget):
    """Asset Library column with thumbnails and descriptions - SHOW SPECIFIC"""

    library_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library = ShowSpecificAssetLibrary()  # Start with no show
        self.selected_asset = None
        self.current_show = None
        self.current_show_path = None
        self.setup_ui()
        self.refresh_library()

    def set_show(self, show_data):
        """Set the current show and load its asset library"""
        if show_data:
            self.current_show = show_data.get('safe_name')
            # Get the show path from the shared ShowsManager singleton
            # (constructing a fresh ShowsManager here re-ran mkdir + logging
            # on every show selection)
            self.current_show_path = get_shows_manager().shows_root / self.current_show

            unreal.log(f"Asset Library: Loading assets for show '{show_data.get('name')}'")

            # Update the library to use this show
            self.library.set_show(self.current_show_path)

            # Update UI
            self.show_label.setText(f"Show: {show_data.get('name')}")
            self.show_label.setStyleSheet("color: #0EA5E9; font-weight: bold;")

            # Clear selection
            self.selected_asset = None

            # Refresh the display
            self.refresh_library()
        else:
            self.current_show = None
            self.current_show_path = None
            self.library.set_show(None)
            self.show_label.setText("No show selected")
            self.show_label.setStyleSheet("color: #808080;")
            self.clear_library()

    def setup_ui(self):
        """Setup the Asset Library UI with thumbnails"""
        self.setObjectName("assetLibraryColumn")

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setObjectName("sectionHeader")
        header.setFixedHeight(35)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 10, 0)

        label = QLabel("ASSET LIBRARY")
        label.setObjectName("sectionHeaderText")
        header_layout.addWidget(label)

        # Add button in header
        add_btn = QPushButton("+")
        add_btn.setFixedSize(20, 20)
        add_btn.clicked.connect(self.add_new_asset)
        add_btn.setToolTip("Add new asset to this show")
        header_layout.addWidget(add_btn)

        layout.addWidget(header)

        # Show label
        self.show_label = QLabel("No show selected")
        self.show_label.setStyleSheet("color: #808080; padding: 5px; font-size: 11px;")
        layout.addWidget(self.show_label)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search assets...")
        self.search_input.textChanged.connect(self.filter_assets)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                margin: 5px;
                background: #2a2a2a;
                border: 1px solid #444;
                color: white;
            }
        """)
        layout.addWidget(self.search_input)

        # Category tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #1a1a1a;
            }
            QTabBar::tab {
                background: #2a2a2a;
                color: white;
                padding: 5px 10px;
            }
            QTabBar::tab:selected {
                background: #3a3a3a;
            }
        """)
        layout.addWidget(self.tabs, 1)

        # Create tabs for each category
        self.character_list = self.create_asset_list("characters")
        self.tabs.addTab(self.character_list, "Characters")

        self.prop_list = self.create_asset_list("props")
        self.tabs.addTab(self.prop_list, "Props")

        self.location_list = self.create_asset_list("locations")
        self.tabs.addTab(self.location_list, "Locations")

        # Asset details panel
        self.details_panel = self.create_details_panel()
        layout.addWidget(self.details_panel)

        # Buttons at bottom
        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(5, 5, 5, 5)
        button_layout.setSpacing(5)

        # Row 1: Add and Delete
        row1_layout = QHBoxLayout()

        add_btn = QPushButton("➕ Add Asset")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self.add_new_asset)
        add_btn.setToolTip("Add a new asset to this show")
        row1_layout.addWidget(add_btn)

        add_selected_btn = QPushButton("📥 Add Selected from Content Browser")
        add_selected_btn.setObjectName("primaryButton")
        add_selected_btn.clicked.connect(self.add_selected_from_content_browser)
        add_selected_btn.setToolTip(
            "Add the assets currently selected in the Content Browser to this show")
        row1_layout.addWidget(add_selected_btn)

        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self.delete_selected_asset)
        delete_btn.setToolTip("Delete the selected asset")
        row1_layout.addWidget(delete_btn)

        button_layout.addLayout(row1_layout)

        # Row 2: Edit and Capture
        row2_layout = QHBoxLayout()

        edit_btn = QPushButton("✏️ Edit")
        edit_btn.setObjectName("secondaryButton")
        edit_btn.clicked.connect(self.edit_selected_asset)
        edit_btn.setToolTip("Edit the selected asset")
        row2_layout.addWidget(edit_btn)

        capture_btn = QPushButton("📸 Capture")
        capture_btn.setObjectName("secondaryButton")
        capture_btn.clicked.connect(self.capture_thumbnail_for_selected)
        capture_btn.setToolTip("Capture thumbnail from viewport")
        row2_layout.addWidget(capture_btn)

        button_layout.addLayout(row2_layout)

        # Row 3: Refresh and AI cataloging
        row3_layout = QHBoxLayout()

        refresh_btn = QPushButton("🔄 Refresh Library")
        refresh_btn.clicked.connect(self.force_refresh)
        refresh_btn.setToolTip("Reload assets from disk")
        row3_layout.addWidget(refresh_btn)

        ai_describe_all_btn = QPushButton("🤖 AI Describe All")
        ai_describe_all_btn.clicked.connect(self.ai_describe_all_assets)
        ai_describe_all_btn.setToolTip(
            "AI-describe every asset in this show that has no description "
            "yet (one small image call per asset; user aliases are kept)")
        row3_layout.addWidget(ai_describe_all_btn)

        button_layout.addLayout(row3_layout)

        layout.addWidget(button_container)

    def edit_selected_asset(self):
        """Edit with ENHANCED thumbnail dialog"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        unreal.log(f"Edit button clicked. Widget ID: {id(self)}, Selected: {self.selected_asset}")

        try:
            # Try to import the enhanced dialog. asset_edit_dialog.py lives
            # in the plugin's Content/Python root, which is already on
            # sys.path when the UI is running (the old hardcoded
            # D:\PythonStoryboardToUE sys.path.insert risked importing a
            # stale dev-machine copy ahead of the live one).
            from asset_edit_dialog import AssetEditDialog

            if not self.selected_asset:
                unreal.log(f"No selection! Widget has selected_asset: {hasattr(self, 'selected_asset')}")
                QMessageBox.warning(self, "No Selection", "Please select an asset first")
                return

            category, name = self.selected_asset

            # Clean name (remove emojis)
            for emoji in ['📸', '🎨', '📦', '⚪']:
                name = name.replace(emoji, '').strip()

            unreal.log(f"Opening ENHANCED dialog for {name} ({category})")

            # Open ENHANCED dialog with thumbnail support
            dialog = AssetEditDialog(name, category, self)
            dialog.asset_updated.connect(lambda n, c: self.on_asset_updated(n, c))

            if dialog.exec_():
                # Dialog accepted - refresh will happen via signal
                pass

        except ImportError as e:
            # Fall back to simple dialog
            unreal.log(f"Using fallback dialog: {e}")
            self.edit_selected_asset_fallback()

    def edit_selected_asset_fallback(self):
        """Fallback edit method"""
        if not self.selected_asset:
            QMessageBox.warning(self, "No Selection", "Please select an asset first")
            return

        category, name = self.selected_asset

        # Get current data
        asset_data = self.library.library.get(category, {}).get(name, {})

        dialog = AddAssetDialog(self, edit_mode=True, existing_data={
            "category": category,
            "name": name,
            "path": asset_data.get("asset_path", ""),
            "description": asset_data.get("description", ""),
            "aliases": asset_data.get("aliases", [])
        })

        if dialog.exec_():
            asset_info = dialog.get_asset_info()

            # Update library
            self.library.add_asset(
                asset_info["category"],
                asset_info["name"],
                asset_info["path"],
                asset_info["description"],
                asset_info["aliases"]
            )

            # Refresh
            self.refresh_library()
            self.library_updated.emit()

    def create_asset_list(self, category):
        """Create scrollable list with thumbnails for a category"""
        list_widget = QListWidget()
        list_widget.setViewMode(QListWidget.IconMode)
        list_widget.setIconSize(QSize(64, 64))
        list_widget.setMovement(QListWidget.Static)
        list_widget.setResizeMode(QListWidget.Adjust)
        list_widget.setSpacing(10)
        list_widget.setWordWrap(True)
        list_widget.setTextElideMode(Qt.ElideNone)

        list_widget.setStyleSheet("""
            QListWidget {
                background: #1a1a1a;
                border: none;
            }
            QListWidget::item {
                background: #2a2a2a;
                border-radius: 4px;
                padding: 5px;
                color: white;
                width: 80px;
                height: 100px;
            }
            QListWidget::item:selected {
                background: #3a3a3a;
                border: 2px solid #0EA5E9;
            }
            QListWidget::item:hover {
                background: #333;
            }
        """)

        list_widget.itemClicked.connect(lambda item: self.on_asset_selected(category, item))
        list_widget.itemDoubleClicked.connect(lambda item: self.on_asset_double_clicked(category, item))

        return list_widget

    def create_details_panel(self):
        """Create panel showing selected asset details"""
        panel = QGroupBox("Asset Details")
        panel.setMaximumHeight(200)
        panel.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout(panel)

        # Thumbnail preview
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(64, 64)
        self.preview_label.setScaledContents(True)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 1px solid #666;
                background: #2a2a2a;
            }
        """)

        # Asset info
        self.name_label = QLabel("Select an asset")
        self.name_label.setStyleSheet("font-weight: bold;")

        self.description_text = QTextEdit()
        self.description_text.setMaximumHeight(60)
        self.description_text.setReadOnly(True)
        self.description_text.setPlaceholderText("Asset description")
        self.description_text.setStyleSheet("""
            QTextEdit {
                background: #2a2a2a;
                border: 1px solid #444;
                color: #ccc;
                padding: 3px;
            }
        """)

        self.path_label = QLabel("Path: None")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.path_label.setWordWrap(True)

        self.aliases_label = QLabel("Aliases: None")
        self.aliases_label.setStyleSheet("color: #888; font-size: 11px;")
        self.aliases_label.setWordWrap(True)

        # Layout
        info_layout = QHBoxLayout()
        info_layout.addWidget(self.preview_label)

        text_layout = QVBoxLayout()
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.description_text)
        text_layout.addWidget(self.path_label)
        text_layout.addWidget(self.aliases_label)
        text_layout.addStretch()

        info_layout.addLayout(text_layout, 1)
        layout.addLayout(info_layout)

        return panel

    def refresh_library(self):
        """Refresh all asset lists from library - NO RELOAD FROM DISK"""
        # Remember current selection
        previous_selection = self.selected_asset

        # Clear lists
        self.character_list.clear()
        self.prop_list.clear()
        self.location_list.clear()

        if not self.current_show:
            self.clear_details_panel()
            return

        # DON'T reload library - it's already loaded!
        # Just use what we have in memory

        # Show asset counts
        char_count = len(self.library.library.get("characters", {}))
        prop_count = len(self.library.library.get("props", {}))
        loc_count = len(self.library.library.get("locations", {}))

        unreal.log(f"Refreshed library - {char_count} characters, {prop_count} props, {loc_count} locations for show: {self.current_show}")

        # Add characters
        for name, data in self.library.library.get("characters", {}).items():
            self.add_asset_item(self.character_list, name, data)

        # Add props
        for name, data in self.library.library.get("props", {}).items():
            self.add_asset_item(self.prop_list, name, data)

        # Add locations
        for name, data in self.library.library.get("locations", {}).items():
            self.add_asset_item(self.location_list, name, data)

        # Restore selection if it still exists
        if previous_selection:
            category, name = previous_selection
            # Check if asset still exists
            if name in self.library.library.get(category, {}):
                # Find and select the item
                list_widget = None
                if category == "characters":
                    list_widget = self.character_list
                elif category == "props":
                    list_widget = self.prop_list
                elif category == "locations":
                    list_widget = self.location_list

                if list_widget:
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        if item.text() == name:
                            list_widget.setCurrentItem(item)
                            # Trigger selection to update details
                            self.on_asset_selected(category, item)
                            break
            else:
                # Asset was deleted, clear selection
                self.clear_details_panel()

    def clear_library(self):
        """Clear all lists when no show is selected"""
        self.character_list.clear()
        self.prop_list.clear()
        self.location_list.clear()
        self.selected_asset = None
        self.name_label.setText("Select an asset")
        self.description_text.clear()
        self.path_label.setText("Path: None")
        self.aliases_label.setText("Aliases: None")
        self.preview_label.setText("")

    def add_asset_item(self, list_widget, name, data):
        """Add an asset item with thumbnail to the list"""
        # Use central sanitization
        data = sanitize_asset_data(data)

        item = QListWidgetItem(name)

        # Get thumbnail
        thumb_info = data.get("thumbnail", {})
        thumb_path = thumb_info.get("path")
        thumb_type = thumb_info.get("type", "none")

        # Create icon
        if thumb_path and Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                icon = QIcon(pixmap)
            else:
                icon = self.create_placeholder_icon(name, thumb_type)
        else:
            icon = self.create_placeholder_icon(name, thumb_type)

        item.setIcon(icon)
        item.setData(Qt.UserRole, data)

        # Add tooltip with description
        tooltip = f"{name}\n{data.get('description', 'No description')[:100]}"
        if thumb_type == "placeholder":
            tooltip += "\n📦 Placeholder thumbnail"
        elif thumb_type == "manual":
            tooltip += "\n📸 Manual thumbnail"
        elif thumb_type == "content_browser":
            tooltip += "\n🎨 Auto thumbnail"

        item.setToolTip(tooltip)

        list_widget.addItem(item)

    def create_placeholder_icon(self, name, asset_type):
        """Create a colored placeholder icon"""
        pixmap = QPixmap(64, 64)

        # Choose color based on type
        if "character" in asset_type.lower():
            color = QColor(100, 150, 255)  # Blue
        elif "prop" in asset_type.lower():
            color = QColor(100, 255, 150)  # Green
        elif "location" in asset_type.lower():
            color = QColor(200, 100, 255)  # Purple
        else:
            color = QColor(150, 150, 150)  # Gray

        pixmap.fill(color)

        # Add text
        painter = QPainter(pixmap)
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, name[:3].upper())
        painter.end()

        return QIcon(pixmap)

    def on_asset_selected(self, category, item):
        """Handle asset selection - SOURCE OF TRUTH"""
        if not item:
            self.clear_details_panel()
            return

        self.selected_asset = (category, item.text())
        unreal.log(f"Asset selected: {self.selected_asset}")  # Debug log

        # Get fresh data from library (source of truth)
        self.update_details_panel_from_library(category, item.text())

    def update_details_panel_from_library(self, category, name):
        """Update details panel from library data (source of truth)"""
        # Get data directly from library
        asset_data = self.library.library.get(category, {}).get(name, {})

        # Use central sanitization
        asset_data = sanitize_asset_data(asset_data)

        if not asset_data:
            self.clear_details_panel()
            return

        # Update all fields from source of truth
        self.name_label.setText(name)
        self.name_label.setStyleSheet("font-weight: bold; color: #ffffff;")

        # Description
        description = asset_data.get("description", "No description")
        self.description_text.setPlainText(description)

        # Asset Path
        asset_path = asset_data.get('asset_path', 'Not specified')
        if asset_path and asset_path != 'Not specified':
            self.path_label.setText(f"Path: {asset_path}")
            self.path_label.setStyleSheet("color: #4ade80; font-size: 11px;")  # Green for valid path
        else:
            self.path_label.setText("Path: Not specified")
            self.path_label.setStyleSheet("color: #f87171; font-size: 11px;")  # Red for missing

        # Aliases
        aliases = asset_data.get("aliases", [])
        if aliases:
            self.aliases_label.setText(f"Aliases: {', '.join(aliases[:5])}")
            if len(aliases) > 5:
                self.aliases_label.setText(self.aliases_label.text() + "...")
        else:
            self.aliases_label.setText("Aliases: None")

        # Thumbnail - most complex part
        self.update_thumbnail_preview(asset_data)

    def update_thumbnail_preview(self, asset_data):
        """Update thumbnail preview from asset data"""
        thumb_info = asset_data.get("thumbnail", {})
        thumb_path = thumb_info.get("path")
        thumb_type = thumb_info.get("type", "none")

        if thumb_path and Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)

                # Add border based on type
                if thumb_type == "manual":
                    self.preview_label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #4ade80;
                            background: #2a2a2a;
                        }
                    """)  # Green border for manual
                elif thumb_type == "content_browser":
                    self.preview_label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #60a5fa;
                            background: #2a2a2a;
                        }
                    """)  # Blue border for auto
                else:
                    self.preview_label.setStyleSheet("""
                        QLabel {
                            border: 1px solid #666;
                            background: #2a2a2a;
                        }
                    """)
            else:
                self.show_placeholder_preview()
        else:
            self.show_placeholder_preview()

    def show_placeholder_preview(self):
        """Show placeholder in preview"""
        self.preview_label.clear()
        self.preview_label.setText("📦")
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 1px dashed #666;
                background: #2a2a2a;
                color: #666;
                font-size: 24px;
            }
        """)

    def clear_details_panel(self):
        """Clear the details panel when nothing selected"""
        self.selected_asset = None
        self.name_label.setText("Select an asset")
        self.name_label.setStyleSheet("font-weight: normal; color: #808080;")
        self.description_text.clear()
        self.path_label.setText("Path: None")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.aliases_label.setText("Aliases: None")
        self.show_placeholder_preview()

    def on_asset_double_clicked(self, category, item):
        """Handle double-click - browse for asset"""
        self.edit_selected_asset()

    def on_asset_updated(self, asset_name, category):
        """Handle when an asset is updated in the edit dialog"""
        unreal.log(f"Asset updated: {asset_name} in {category}")

        # Refresh the library from disk (source of truth)
        self.refresh_library()

        # Re-select the item if it was selected
        if self.selected_asset and self.selected_asset == (category, asset_name):
            # Update the details panel with fresh data
            self.update_details_panel_from_library(category, asset_name)

            # Find and re-select the item in the list
            list_widget = None
            if category == "characters":
                list_widget = self.character_list
            elif category == "props":
                list_widget = self.prop_list
            elif category == "locations":
                list_widget = self.location_list

            if list_widget:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    if item.text() == asset_name:
                        list_widget.setCurrentItem(item)
                        break

        # Emit that library was updated
        self.library_updated.emit()
        unreal.log(f"UI refreshed after {asset_name} update")

    def capture_thumbnail_for_selected(self):
        """Capture manual thumbnail for selected asset"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        if not self.selected_asset:
            QMessageBox.warning(self, "No Selection", "Please select an asset first")
            return

        category, name = self.selected_asset

        # Use the real thumbnail pipeline (same one the Content Browser add
        # flow uses); the old handler called a placeholder that did nothing
        # while promising a library refresh that never came
        entry = self.library.library.get(category, {}).get(name, {})
        asset_path = entry.get('asset_path', '')
        if not asset_path:
            QMessageBox.warning(
                self, "No Asset Path",
                f"'{name}' has no asset path in the library.\n\n"
                "Edit the asset and browse to its Unreal asset first.")
            return

        reply = QMessageBox.question(
            self,
            "Capture Thumbnail",
            f"Generate a thumbnail for '{name}' now?\n\n"
            f"Asset: {asset_path}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            from core.thumbnail_generator import (
                generate_asset_thumbnail, safe_thumbnail_filename,
                LOCATION_THUMBNAIL_DEFERRED
            )
            thumb_dir = Path(self.current_show_path) / "Thumbnails"
            out_png = thumb_dir / (safe_thumbnail_filename(name) + ".png")
            status = generate_asset_thumbnail(asset_path, str(out_png))
            if status == LOCATION_THUMBNAIL_DEFERRED:
                # Location whose level is not open: a map placeholder PNG
                # was written. Keep type 'placeholder' (NOT 'manual') so a
                # later run can replace it with a real viewport capture.
                if out_png.exists():
                    self.library.library[category][name]['thumbnail'] = {
                        'type': 'placeholder',
                        'path': str(out_png),
                    }
                    self.library.save_library()
                    self.refresh_library()
                    self.library_updated.emit()
                QMessageBox.information(
                    self, "Location Thumbnail Deferred",
                    f"'{name}' is a level that is not currently open in the "
                    "editor, so a map placeholder was saved instead.\n\n"
                    "Open that level and capture again to get a real "
                    "viewport thumbnail.")
            elif status:
                self.library.library[category][name]['thumbnail'] = {
                    'type': 'manual',
                    'path': str(out_png),
                }
                self.library.save_library()
                self.refresh_library()
                self.library_updated.emit()
                QMessageBox.information(
                    self, "Thumbnail Captured",
                    f"Thumbnail saved for '{name}':\n{out_png}")
            else:
                QMessageBox.warning(
                    self, "Thumbnail Failed",
                    f"Could not generate a thumbnail for '{name}'.\n\n"
                    "Check the Output Log for details (the asset may not "
                    "load, or the render may have failed).")
        except Exception as e:
            QMessageBox.warning(
                self, "Thumbnail Failed",
                f"Thumbnail generation errored for '{name}':\n{e}")

    def get_active_category(self):
        """Category of the currently selected tab, or None if unknown"""
        try:
            index = self.tabs.currentIndex()
        except Exception:
            return None
        return {0: 'characters', 1: 'props', 2: 'locations'}.get(index)

    def _gather_level_landmark_actors(self, cx, cy, radius, limit=30):
        """Ground-truth landmark inventory from the open level: labels and
        exact world positions/sizes of the significant placed actors near
        the stage. The engine already knows where everything is - the AI
        only needs to NAME things, never measure them.

        Returns a list of one-line strings ready for the survey prompt.
        Never raises.
        """
        lines = []
        try:
            actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            if actor_subsystem is None:
                return lines
            skip_terms = ('light', 'volume', 'playerstart', 'fog', 'sky',
                          'atmosphere', 'postprocess', 'camera', 'brush',
                          'landscape', 'navmesh', 'worldsettings', 'recast',
                          'reflection', 'audio', 'capture', 'trigger')
            candidates = []
            for actor in actor_subsystem.get_all_level_actors() or []:
                try:
                    class_name = type(actor).__name__.lower()
                    label = str(actor.get_actor_label())
                    if any(term in class_name for term in skip_terms):
                        continue
                    if any(term in label.lower() for term in skip_terms):
                        continue
                    loc = actor.get_actor_location()
                    dx, dy = float(loc.x) - cx, float(loc.y) - cy
                    if (dx * dx + dy * dy) ** 0.5 > radius:
                        continue
                    origin, extent = actor.get_actor_bounds(False)
                    max_extent = max(float(extent.x), float(extent.y), float(extent.z))
                    if max_extent < 100.0:  # ignore sub-1m clutter
                        continue
                    candidates.append((max_extent, label, loc, extent))
                except Exception:
                    continue
            candidates.sort(key=lambda item: item[0], reverse=True)
            for _, label, loc, extent in candidates[:limit]:
                lines.append(
                    f"- {label}: (X={float(loc.x):.0f}, Y={float(loc.y):.0f}, "
                    f"Z={float(loc.z):.0f}), size {float(extent.x) / 50.0:.0f}x"
                    f"{float(extent.y) / 50.0:.0f}x{float(extent.z) / 50.0:.0f}m")
        except Exception as e:
            unreal.log_warning(f"[Survey] Actor inventory unavailable: {e}")
        return lines

    def _survey_location(self, name, stage_center, describe_provider):
        """Map the open level: capture a posed top-down overview plus four
        compass views around the stage anchor (temporary SceneCapture2D,
        the editor viewport is never moved), then have the vision provider
        turn them into a landmark map with estimated world coordinates.

        This follows the posed-multi-view approach used by VLM spatial
        mapping systems: a top-down map with a known ground span is the
        coordinate reference, eye-level views identify what things are.
        SceneBuilder / the positioning prompt consume the result so the
        AI knows where the barn, fences, and open areas actually are.

        Args:
            name: location display name (used for filenames/logs).
            stage_center: (x, y, z) tuple of the recorded stage anchor.
            describe_provider: vision provider to build the landmark map,
                or None to capture posed images only.

        Returns:
            Survey dict {'points': [...], 'landmarks': [...],
            'open_areas': [...]} or None when nothing could be captured.
            Never raises.
        """
        try:
            from core.thumbnail_generator import capture_level_view, safe_thumbnail_filename
            cx, cy, cz = (float(stage_center[0]), float(stage_center[1]),
                          float(stage_center[2]))

            survey_dir = Path(self.current_show_path) / "Survey"
            base = safe_thumbnail_filename(name)

            top_height = 2500.0   # capture FOV is ~90 deg -> ground span ~2x height
            eye_height = 170.0
            shots = [
                ('top_down',
                 unreal.Vector(cx, cy, cz + top_height),
                 unreal.Rotator(pitch=-90.0, yaw=0.0, roll=0.0)),
                ('yaw000',
                 unreal.Vector(cx, cy, cz + eye_height),
                 unreal.Rotator(pitch=-5.0, yaw=0.0, roll=0.0)),
                ('yaw090',
                 unreal.Vector(cx, cy, cz + eye_height),
                 unreal.Rotator(pitch=-5.0, yaw=90.0, roll=0.0)),
                ('yaw180',
                 unreal.Vector(cx, cy, cz + eye_height),
                 unreal.Rotator(pitch=-5.0, yaw=180.0, roll=0.0)),
                ('yaw270',
                 unreal.Vector(cx, cy, cz + eye_height),
                 unreal.Rotator(pitch=-5.0, yaw=270.0, roll=0.0)),
            ]

            points = []
            for tag, loc, rot in shots:
                png = survey_dir / f"{base}_{tag}.png"
                try:
                    if capture_level_view(loc, rot, str(png), 640):
                        points.append({
                            'tag': tag,
                            'image': str(png),
                            'camera': {
                                'location': {'x': float(loc.x), 'y': float(loc.y), 'z': float(loc.z)},
                                'rotation': {'pitch': float(rot.pitch), 'yaw': float(rot.yaw), 'roll': float(rot.roll)},
                            },
                        })
                    else:
                        unreal.log_warning(f"[Survey] Capture failed for '{tag}'")
                except Exception as shot_err:
                    unreal.log_warning(f"[Survey] Capture errored for '{tag}': {shot_err}")

            if not points:
                unreal.log_warning(f"[Survey] No survey captures for '{name}'")
                return None

            # Burn a labeled world-coordinate grid onto the top-down map
            # (Scaffold/Set-of-Mark protocol: VLMs read coordinates off a
            # labeled grid far more reliably than they estimate them)
            span = top_height * 2.0
            for point in points:
                if point['tag'] != 'top_down':
                    continue
                try:
                    from core.thumbnail_generator import overlay_coordinate_grid
                    grid_png = survey_dir / f"{base}_top_down_grid.png"
                    if overlay_coordinate_grid(point['image'], str(grid_png),
                                               cx, cy, span):
                        point['image'] = str(grid_png)
                        point['grid'] = True
                except Exception as grid_err:
                    unreal.log_warning(f"[Survey] Grid overlay failed: {grid_err}")

            # Ground-truth actor inventory: exact names + coordinates from
            # the engine (the AI's job is naming/regions, not measuring)
            inventory_lines = self._gather_level_landmark_actors(cx, cy, span / 2.0)

            survey = {'points': points, 'landmarks': [], 'open_areas': []}
            unreal.log(f"[Survey] '{name}': captured {len(points)} posed views, "
                       f"{len(inventory_lines)} inventory actors")

            if describe_provider is None:
                unreal.log("[Survey] No AI provider; posed images stored without a landmark map")
                return survey

            span = int(span)
            pose_lines = []
            for idx, point in enumerate(points, 1):
                cam = point['camera']
                if point['tag'] == 'top_down':
                    grid_note = (" Yellow gridlines with X=/Y= labels show EXACT world "
                                 "coordinates - read positions off them; the red circle "
                                 "marks the stage center." if point.get('grid') else "")
                    pose_lines.append(
                        f"Image {idx} (TOP-DOWN MAP): camera at "
                        f"({cam['location']['x']:.0f}, {cam['location']['y']:.0f}, {cam['location']['z']:.0f}) "
                        "looking straight down. The image TOP edge points toward +X, the RIGHT edge "
                        f"toward +Y. The visible ground spans roughly {span}x{span} units and the image "
                        f"center is world point ({cx:.0f}, {cy:.0f}).{grid_note}")
                else:
                    yaw = cam['rotation']['yaw']
                    pose_lines.append(
                        f"Image {idx}: eye-level camera at ({cam['location']['x']:.0f}, "
                        f"{cam['location']['y']:.0f}, {cam['location']['z']:.0f}) looking yaw {yaw:.0f} deg.")

            inventory_block = ""
            if inventory_lines:
                inventory_block = (
                    "\nGROUND-TRUTH ACTOR INVENTORY (exact engine coordinates - "
                    "prefer these over visual estimates; your job is to give them "
                    "human-meaningful names and group them):\n"
                    + "\n".join(inventory_lines[:30]) + "\n")

            survey_prompt = (
                "You are mapping a 3D game level for cinematic staging. All "
                f"{len(points)} images are posed screenshots of the SAME level.\n"
                "Units: Unreal (1 meter = 100 units). Coordinates: X forward, Y right, "
                "Z up; yaw 0 looks toward +X, yaw 90 toward +Y.\n\n"
                + "\n".join(pose_lines) + "\n"
                + inventory_block +
                "\nTask: identify up to 12 major landmarks (buildings, structures, "
                "terrain features, fences, roads) and up to 4 open clear areas "
                "suitable for staging characters. For anything in the inventory, "
                "use its exact coordinates and give it a human-readable name; for "
                "regions (clearings, paths, crop fields) read coordinates off the "
                "labeled grid on the TOP-DOWN map. Use the eye-level views to "
                "recognize what things are. Ground Z near the stage is about "
                f"{cz:.0f}.\n"
                'Return STRICT JSON only: {"landmarks": [{"name": str, "x": float, '
                '"y": float, "z": float, "notes": str}], "open_areas": '
                '[{"name": str, "x": float, "y": float}]}')

            try:
                result = describe_provider.analyze_images(
                    [p['image'] for p in points], survey_prompt, max_tokens=2048)
                if isinstance(result, dict) and result.get('success'):
                    from core.json_extractor import parse_llm_json
                    parsed = parse_llm_json(result.get('response') or '')
                    if isinstance(parsed, dict):
                        landmarks = [lm for lm in (parsed.get('landmarks') or [])
                                     if isinstance(lm, dict) and lm.get('name')][:12]
                        open_areas = [oa for oa in (parsed.get('open_areas') or [])
                                      if isinstance(oa, dict) and oa.get('name')][:4]
                        survey['landmarks'] = landmarks
                        survey['open_areas'] = open_areas
                        unreal.log(f"[Survey] '{name}': mapped {len(landmarks)} landmarks, "
                                   f"{len(open_areas)} open areas "
                                   f"(cost ${float(result.get('cost') or 0.0):.4f})")
                        for lm in landmarks:
                            try:
                                unreal.log(f"[Survey]   {lm.get('name')}: "
                                           f"({float(lm.get('x', 0)):.0f}, {float(lm.get('y', 0)):.0f})")
                            except (TypeError, ValueError):
                                pass
                else:
                    reason = result.get('error') if isinstance(result, dict) else 'no result'
                    unreal.log_warning(f"[Survey] Landmark mapping call failed: {reason}")
            except Exception as map_err:
                unreal.log_warning(f"[Survey] Landmark mapping errored: {map_err}")

            return survey
        except Exception as e:
            unreal.log_warning(f"[Survey] Survey failed for '{name}': {e}")
            return None

    def _capture_location_on_add(self, name, asset_path, out_png,
                                 describe_provider=None):
        """Open a location's map, capture the editor viewport as its
        thumbnail, record the camera pose plus a traced ground point as
        the location's stage anchor, run the multi-view survey (posed
        captures -> AI landmark map), then restore the previously open map.

        The recorded 'camera_start' / 'stage_center' are what SceneBuilder
        uses to build scenes at a known-good vantage instead of world
        origin (which may be inside scenery); 'survey' feeds the
        positioning prompt's SCENE LANDMARKS.

        Returns {'thumbnail': bool, 'camera_start': dict|None,
        'stage_center': dict|None, 'survey': dict|None}. Never raises.
        """
        result = {'thumbnail': False, 'camera_start': None,
                  'stage_center': None, 'survey': None}
        try:
            from core.thumbnail_generator import (
                generate_asset_thumbnail, LOCATION_THUMBNAIL_DEFERRED)
            wanted = str(asset_path).split('.')[0]

            ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

            # Remember the currently open map so we can put the user back
            prev_level = None
            try:
                world = ues.get_editor_world()
                if world:
                    prev_level = str(world.get_package().get_name())
            except Exception:
                prev_level = None

            def _load(path):
                try:
                    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                    if les and hasattr(les, 'load_level'):
                        return bool(les.load_level(path))
                except Exception:
                    pass
                try:
                    return bool(unreal.EditorLevelLibrary.load_level(path))
                except Exception as load_err:
                    unreal.log_warning(f"[LocationAdd] Could not load {path}: {load_err}")
                    return False

            needs_load = (prev_level or '') != wanted
            if needs_load:
                unreal.log(f"[LocationAdd] '{name}': opening map for thumbnail capture...")
                if not _load(wanted):
                    return result

            # Viewport capture (generate_asset_thumbnail routes level
            # assets to the open-level capture path)
            status = generate_asset_thumbnail(asset_path, str(out_png))
            result['thumbnail'] = (status is True)
            if status == LOCATION_THUMBNAIL_DEFERRED:
                unreal.log_warning(
                    f"[LocationAdd] Viewport capture unavailable for '{name}' "
                    "(map placeholder written instead)")

            # Record the editor camera as the location's stage anchor
            try:
                info = ues.get_level_viewport_camera_info()
                if info:
                    cam_loc, cam_rot = info
                    result['camera_start'] = {
                        'location': {'x': float(cam_loc.x), 'y': float(cam_loc.y), 'z': float(cam_loc.z)},
                        'rotation': {'pitch': float(cam_rot.pitch), 'yaw': float(cam_rot.yaw), 'roll': float(cam_rot.roll)},
                    }
                    forward = unreal.MathLibrary.get_forward_vector(cam_rot)
                    target_x = float(cam_loc.x) + float(forward.x) * 500.0
                    target_y = float(cam_loc.y) + float(forward.y) * 500.0
                    target_z = float(cam_loc.z) + float(forward.z) * 500.0

                    ground_z = None
                    try:
                        world = ues.get_editor_world()
                        hit = unreal.SystemLibrary.line_trace_single(
                            world,
                            unreal.Vector(target_x, target_y, target_z + 1000.0),
                            unreal.Vector(target_x, target_y, target_z - 5000.0),
                            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                            False, [], unreal.DrawDebugTrace.NONE, True)
                        if hit:
                            hit_values = unreal.GameplayStatics.break_hit_result(hit)
                            ground_z = float(hit_values[4].z)
                    except Exception as trace_err:
                        unreal.log(f"[LocationAdd] Ground trace unavailable ({trace_err}); "
                                   "estimating ground from camera height")
                    if ground_z is None:
                        ground_z = float(cam_loc.z) - 160.0

                    result['stage_center'] = {'x': target_x, 'y': target_y, 'z': ground_z}
                    unreal.log(f"[LocationAdd] '{name}': stage anchor recorded at "
                               f"({target_x:.0f}, {target_y:.0f}, {ground_z:.0f}) "
                               "from the current viewport. Scenes for this "
                               "location will build there.")

                    # Multi-view survey: posed captures + AI landmark map
                    # so the positioner knows where things are in this map
                    result['survey'] = self._survey_location(
                        name, (target_x, target_y, ground_z), describe_provider)
                else:
                    unreal.log_warning("[LocationAdd] No viewport camera info available; "
                                       "no stage anchor recorded")
            except Exception as cam_err:
                unreal.log_warning(f"[LocationAdd] Could not record the viewport camera: {cam_err}")

            # Put the user back in the map they had open
            if needs_load and prev_level and not prev_level.startswith('/Temp'):
                unreal.log(f"[LocationAdd] Restoring previous map: {prev_level}")
                _load(prev_level)
        except Exception as e:
            unreal.log_warning(f"[LocationAdd] Capture flow failed for '{name}': {e}")
        return result

    def add_selected_from_content_browser(self):
        """Add the assets selected in the Content Browser to the library"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        eul = getattr(unreal, 'EditorUtilityLibrary', None)
        if eul is None or not hasattr(eul, 'get_selected_assets'):
            QMessageBox.warning(
                self, "Not Available",
                "EditorUtilityLibrary.get_selected_assets is not available "
                "in this engine version.")
            return

        try:
            selected = list(eul.get_selected_assets())
        except Exception as e:
            QMessageBox.warning(
                self, "Error",
                f"Could not read the Content Browser selection: {e}")
            return

        if not selected:
            QMessageBox.information(
                self, "Nothing Selected",
                "Select one or more assets in the Content Browser first, "
                "then click this button.\n\n"
                "Supported: Static Meshes, Skeletal Meshes, Blueprints, "
                "and Levels (added as locations).")
            return

        active_category = self.get_active_category()
        added = []
        skipped = []
        thumb_dir = Path(self.current_show_path) / "Thumbnails"

        # AI auto-describe everything we add (same cataloger as the Edit
        # dialog / AI Describe All: one small image call per asset, using
        # the thumbnail captured below). One shared provider for the
        # whole selection; unavailable provider just skips describing.
        describe_asset = None
        merge_aliases = None
        describe_provider = None
        described_count = 0
        describe_cost = 0.0
        try:
            from core.asset_cataloger import (
                describe_asset as _describe_asset,
                merge_aliases as _merge_aliases,
                _create_provider,
            )
            describe_provider = _create_provider()
            if describe_provider is None:
                unreal.log_warning("Auto-describe skipped: no AI provider configured")
            else:
                describe_asset = _describe_asset
                merge_aliases = _merge_aliases
        except Exception as e:
            unreal.log_warning(f"Auto-describe unavailable: {e}")

        for asset in selected:
            built = build_entry_from_asset(asset)
            if built is None:
                try:
                    label = str(asset.get_name())
                except Exception:
                    label = str(asset)
                skipped.append(f"{label} (unsupported type)")
                continue

            name = built['name']
            if built['category'] == 'locations':
                # Levels are always locations, regardless of the active tab:
                # a map filed under characters/props would break spawning
                category = 'locations'
            else:
                category = active_category or built['category']
            if name in self.library.library.get(category, {}):
                skipped.append(f"{name} (already in {category})")
                continue

            asset_path = built['entry']['asset_path']
            # save=False: one save_library() write after the loop instead of
            # rewriting asset_library.json once per asset (plus once per
            # thumbnail) for an N-asset selection
            self.library.add_asset(category, name, asset_path, "", [], save=False)
            added.append(f"{name} ({category})")
            unreal.log(f"Added asset from Content Browser: {name} -> {asset_path} [{category}]")

            if category == 'locations':
                # Levels: open the map, capture the viewport as the
                # thumbnail, record the camera pose + stage anchor for
                # scene builds, then restore the previously open map.
                try:
                    from core.thumbnail_generator import safe_thumbnail_filename
                    out_png = thumb_dir / (safe_thumbnail_filename(name) + ".png")
                    capture = self._capture_location_on_add(
                        name, asset_path, out_png, describe_provider)
                    entry = self.library.library[category][name]
                    if capture.get('thumbnail'):
                        entry['thumbnail'] = {
                            'type': 'viewport',
                            'path': str(out_png),
                        }
                    if capture.get('camera_start'):
                        entry['camera_start'] = capture['camera_start']
                    if capture.get('stage_center'):
                        entry['stage_center'] = capture['stage_center']
                    if capture.get('survey'):
                        entry['survey'] = capture['survey']
                except Exception as e:
                    unreal.log_warning(f"Location capture flow errored for {name}: {e}")
            else:
                # Auto-generate a thumbnail; a failure here only logs.
                # Content Browser thumbnail first (cached/editor-rendered via
                # the C++ helper), then the turntable capture as fallback.
                try:
                    from core.thumbnail_generator import (
                        generate_asset_thumbnail, safe_thumbnail_filename,
                        try_export_editor_thumbnail
                    )
                    out_png = thumb_dir / (safe_thumbnail_filename(name) + ".png")
                    if try_export_editor_thumbnail(asset_path, str(out_png)) \
                            or generate_asset_thumbnail(asset_path, str(out_png)):
                        self.library.library[category][name]['thumbnail'] = {
                            'type': 'content_browser',
                            'path': str(out_png),
                        }
                    else:
                        unreal.log_warning(f"Thumbnail generation failed for {name}")
                except Exception as e:
                    unreal.log_warning(f"Thumbnail generation errored for {name}: {e}")

            # AI auto-describe the freshly added entry from its thumbnail
            # (no extra click needed; failures only log and the asset can
            # still be described later via Edit or AI Describe All)
            if describe_asset is not None:
                try:
                    entry = self.library.library[category][name]
                    unreal.log(f"Auto-describing '{name}' with AI...")
                    described = describe_asset(
                        name, entry, provider=describe_provider,
                        thumb_dir=str(thumb_dir))
                    if isinstance(described, dict):
                        entry['description'] = described['description']
                        entry['aliases'] = merge_aliases(
                            entry.get('aliases'), described.get('aliases'))
                        if category == 'characters' and described.get('attached_props'):
                            entry['attached_props'] = described['attached_props']
                        describe_cost += float(described.get('cost') or 0.0)
                        described_count += 1
                        unreal.log(f"Auto-described '{name}': {entry['description'][:80]}")
                    else:
                        unreal.log_warning(
                            f"Auto-describe returned nothing for '{name}' "
                            "(use Edit or AI Describe All to retry)")
                except Exception as e:
                    unreal.log_warning(f"Auto-describe errored for '{name}': {e}")

        # Single write for the whole selection (adds + thumbnails)
        if added:
            self.library.save_library()

        self.refresh_library()
        self.library_updated.emit()

        summary = f"Added {len(added)} asset(s) to this show."
        if added:
            summary += "\n\n" + "\n".join(added[:10])
        if described_count:
            summary += (f"\n\nAI described: {described_count} asset(s)"
                        f" (est. ${describe_cost:.4f})")
        if skipped:
            summary += "\n\nSkipped:\n" + "\n".join(skipped[:10])
        QMessageBox.information(self, "Add from Content Browser", summary)

    def add_new_asset(self):
        """Add a new asset to the library"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        dialog = AddAssetDialog(self)
        if dialog.exec_():
            asset_info = dialog.get_asset_info()

            # Add to library
            self.library.add_asset(
                asset_info["category"],
                asset_info["name"],
                asset_info["path"],
                asset_info["description"],
                asset_info["aliases"]
            )

            # Refresh display
            self.refresh_library()
            self.library_updated.emit()

            unreal.log(f"Added asset: {asset_info['name']} to {asset_info['category']}")

    def delete_selected_asset(self):
        """Delete the selected asset from the library"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        if not self.selected_asset:
            QMessageBox.warning(self, "No Selection", "Please select an asset first")
            return

        category, name = self.selected_asset

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Asset",
            f"Are you sure you want to delete '{name}' from {category}?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Delete from library
            if category in self.library.library and name in self.library.library[category]:
                del self.library.library[category][name]
                self.library.save_library()

                # Clear selection
                self.selected_asset = None
                self.clear_details_panel()

                # Refresh display
                self.refresh_library()
                self.library_updated.emit()

                unreal.log(f"Deleted asset: {name} from {category}")
                QMessageBox.information(self, "Deleted", f"'{name}' has been deleted.")
            else:
                QMessageBox.warning(self, "Error", "Asset not found in library")

    def force_refresh(self):
        """Force reload the library from disk"""
        if not self.current_show:
            QMessageBox.information(self, "No Show", "Please select a show first")
            return

        unreal.log(f"Force refreshing library for show: {self.current_show}")

        # THIS is where we reload from disk
        self.library.load_library()

        # Then refresh display
        self.refresh_library()

        # Show counts
        char_count = len(self.library.library.get("characters", {}))
        prop_count = len(self.library.library.get("props", {}))
        loc_count = len(self.library.library.get("locations", {}))

        QMessageBox.information(
            self,
            "Library Refreshed",
            f"Reloaded from disk:\n\n"
            f"Characters: {char_count}\n"
            f"Props: {prop_count}\n"
            f"Locations: {loc_count}\n\n"
            f"Total: {char_count + prop_count + loc_count} assets"
        )

    def ai_describe_all_assets(self):
        """AI-describe every asset in this show's library that is missing a
        description (existing descriptions and user aliases are preserved).
        Costs roughly one small image call per described asset."""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        try:
            from core.asset_cataloger import catalog_library
        except Exception as e:
            QMessageBox.warning(
                self, "AI Describe All",
                f"AI cataloger is unavailable: {e}")
            return

        reply = QMessageBox.question(
            self,
            "AI Describe All",
            "Send every asset without a description to the configured AI "
            "provider?\n\nCost: about one small image call per asset. "
            "Assets that already have descriptions are skipped, and your "
            "existing aliases are kept.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        progress = QProgressDialog(
            "AI describing assets...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        def report(index, total, name):
            progress.setMaximum(max(total, 1))
            progress.setValue(min(index, total))
            if name:
                progress.setLabelText(f"AI describing {index + 1} of {total}:\n{name}")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            result = catalog_library(
                self.current_show, overwrite=False, progress_cb=report)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "AI Describe All", f"Cataloging failed: {e}")
            return
        finally:
            progress.close()

        # catalog_library saved asset_library.json on disk; reload the
        # shared in-memory library so the widget matches, then refresh
        self.library.load_library()
        self.refresh_library()
        self.library_updated.emit()

        described = len(result.get('described', []))
        skipped = len(result.get('skipped', []))
        failed = result.get('failed', [])
        summary = (
            f"Described: {described}\n"
            f"Skipped (already described or cancelled): {skipped}\n"
            f"Failed: {len(failed)}"
        )
        cost = result.get('cost', 0.0)
        if cost:
            summary += f"\n\nEstimated AI cost: ${cost:.4f}"
        if result.get('error'):
            summary += f"\n\n{result['error']}"
        if failed:
            summary += "\n\nFailed entries (see Output Log):\n" + ", ".join(failed[:10])
        QMessageBox.information(self, "AI Describe All", summary)

    def filter_assets(self, text):
        """Filter assets based on search text"""
        text = text.lower()

        # Filter all lists
        for list_widget in [self.character_list, self.prop_list, self.location_list]:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                data = item.data(Qt.UserRole)

                # Check name, description, and aliases
                visible = (text in item.text().lower() or
                          text in data.get("description", "").lower() or
                          any(text in alias.lower() for alias in data.get("aliases", [])))

                item.setHidden(not visible)


class AddAssetDialog(QDialog):
    """Dialog for adding/editing assets"""

    def __init__(self, parent=None, edit_mode=False, existing_data=None):
        super().__init__(parent)
        self.edit_mode = edit_mode
        self.existing_data = existing_data or {}
        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI"""
        self.setWindowTitle("Edit Asset" if self.edit_mode else "Add Asset")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Category
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["characters", "props", "locations"])
        if self.existing_data.get("category"):
            self.category_combo.setCurrentText(self.existing_data["category"])
        category_layout.addWidget(self.category_combo)
        layout.addLayout(category_layout)

        # Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit(self.existing_data.get("name", ""))
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Asset Path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Asset Path:"))
        self.path_input = QLineEdit(self.existing_data.get("path", ""))
        self.path_input.setPlaceholderText("/Game/Characters/BP_Character")
        path_layout.addWidget(self.path_input)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_asset)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # Description
        layout.addWidget(QLabel("Description:"))
        self.description_input = QTextEdit()
        self.description_input.setPlainText(self.existing_data.get("description", ""))
        self.description_input.setMaximumHeight(60)
        layout.addWidget(self.description_input)

        # Aliases
        layout.addWidget(QLabel("Aliases (comma-separated):"))
        self.aliases_input = QLineEdit()
        if self.existing_data.get("aliases"):
            self.aliases_input.setText(", ".join(self.existing_data["aliases"]))
        self.aliases_input.setPlaceholderText("dog, puppy, canine")
        layout.addWidget(self.aliases_input)

        # Buttons
        button_layout = QHBoxLayout()

        ok_btn = QPushButton("Save" if self.edit_mode else "Add")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def browse_asset(self):
        """Browse for asset path"""
        # Simple input dialog for now
        path, ok = QInputDialog.getText(
            self,
            "Asset Path",
            "Enter asset path:",
            text=self.path_input.text()
        )
        if ok:
            self.path_input.setText(path)

    def get_asset_info(self):
        """Get the asset information from the dialog"""
        aliases = [a.strip() for a in self.aliases_input.text().split(",") if a.strip()]

        return {
            "category": self.category_combo.currentText(),
            "name": self.name_input.text(),
            "path": self.path_input.text(),
            "description": self.description_input.toPlainText(),
            "aliases": aliases
        }

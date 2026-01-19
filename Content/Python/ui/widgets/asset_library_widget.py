# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ASSET LIBRARY UI WIDGET WITH THUMBNAILS
Full implementation for the StoryboardTo3D UI - SHOW SPECIFIC VERSION
"""

import unreal
import json
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

def capture_thumbnail(asset_name):
    """Capture thumbnail for asset - placeholder function"""
    unreal.log(f"Thumbnail capture requested for: {asset_name}")
    unreal.log("Manual thumbnail capture: Take a screenshot using Unreal's viewport tools")
    # Future: Implement automated thumbnail capture
    pass

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

    def add_asset(self, category, name, asset_path, description, aliases):
        """Add or update an asset in the library"""
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
            # Get the show path from ShowsManager
            from core.shows_manager import ShowsManager
            manager = ShowsManager()
            self.current_show_path = manager.shows_root / self.current_show

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
        self.search_input.setPlaceholderText(" Search assets...")
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

        add_btn = QPushButton(" Add Asset")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self.add_new_asset)
        add_btn.setToolTip("Add a new asset to this show")
        row1_layout.addWidget(add_btn)

        delete_btn = QPushButton(" Delete")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self.delete_selected_asset)
        delete_btn.setToolTip("Delete the selected asset")
        row1_layout.addWidget(delete_btn)

        button_layout.addLayout(row1_layout)

        # Row 2: Edit and Capture
        row2_layout = QHBoxLayout()

        edit_btn = QPushButton(" Edit")
        edit_btn.setObjectName("secondaryButton")
        edit_btn.clicked.connect(self.edit_selected_asset)
        edit_btn.setToolTip("Edit the selected asset")
        row2_layout.addWidget(edit_btn)

        capture_btn = QPushButton(" Capture")
        capture_btn.setObjectName("secondaryButton")
        capture_btn.clicked.connect(self.capture_thumbnail_for_selected)
        capture_btn.setToolTip("Capture thumbnail from viewport")
        row2_layout.addWidget(capture_btn)

        button_layout.addLayout(row2_layout)

        # Row 3: Refresh
        refresh_btn = QPushButton(" Refresh Library")
        refresh_btn.clicked.connect(self.force_refresh)
        refresh_btn.setToolTip("Reload assets from disk")
        button_layout.addWidget(refresh_btn)

        layout.addWidget(button_container)

    def edit_selected_asset(self):
        """Edit with ENHANCED thumbnail dialog"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        unreal.log(f"Edit button clicked. Widget ID: {id(self)}, Selected: {self.selected_asset}")

        try:
            # Try to import the enhanced dialog
            import sys
            sys.path.insert(0, r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python')
            from asset_edit_dialog import AssetEditDialog

            if not self.selected_asset:
                unreal.log(f"No selection! Widget has selected_asset: {hasattr(self, 'selected_asset')}")
                QMessageBox.warning(self, "No Selection", "Please select an asset first")
                return

            category, name = self.selected_asset

            # Clean name (remove emojis)
            for emoji in ['', '', '', '']:
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
            tooltip += "\n Placeholder thumbnail"
        elif thumb_type == "manual":
            tooltip += "\n Manual thumbnail"
        elif thumb_type == "content_browser":
            tooltip += "\n Auto thumbnail"

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
        self.preview_label.setText("")
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

        reply = QMessageBox.information(
            self,
            "Capture Thumbnail",
            f"Position '{name}' nicely in the viewport, then click OK to capture thumbnail.\n\n" +
            "The screenshot will be ready in 30-40 seconds.",
            QMessageBox.Ok | QMessageBox.Cancel
        )

        if reply == QMessageBox.Ok:
            capture_thumbnail(name)
            QMessageBox.information(
                self,
                "Capture Started",
                f"Thumbnail capture started for '{name}'.\n\n" +
                "It will be ready in 30-40 seconds.\n" +
                "The library will auto-update when ready."
            )

            # Schedule refresh
            QTimer.singleShot(45000, self.refresh_library)  # Refresh after 45 seconds

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

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Show management widgets for StoryboardTo3D
"""

import unreal
from pathlib import Path
from core.shows_manager import ShowsManager
from .custom_widgets import ShowButton

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


class ShowManagerWidget(QWidget):
    """Widget for managing shows"""

    show_selected = Signal(object)
    shows_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.shows = []
        self.shows_manager = ShowsManager()
        self.current_show = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        self.setObjectName("leftColumn")
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # SHOWS header
        header = self.create_section_header("SHOWS")
        layout.addWidget(header)

        # Search bar
        search_widget = QWidget()
        search_widget.setObjectName("searchWidget")
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(10, 5, 10, 5)

        self.show_search = QLineEdit()
        self.show_search.setPlaceholderText(" Search...")
        self.show_search.textChanged.connect(self.filter_shows)
        search_layout.addWidget(self.show_search)

        # Sort dropdown
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "Name (A-Z)",
            "Name (Z-A)",
            "Date Created ↓",
            "Date Created ↑",
            "Date Modified ↓",
            "Date Modified ↑"
        ])
        self.sort_combo.currentTextChanged.connect(self.sort_shows)
        self.sort_combo.setMaximumWidth(100)
        search_layout.addWidget(self.sort_combo)

        layout.addWidget(search_widget)

        # Shows list container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.shows_container = QWidget()
        self.shows_layout = QVBoxLayout(self.shows_container)
        self.shows_layout.setSpacing(5)
        self.shows_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.shows_container)
        layout.addWidget(scroll, 1)

        # New show button
        new_btn = QPushButton("+ New Show")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(self.new_show)
        layout.addWidget(new_btn)

        # Import/Export buttons
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(10, 5, 10, 10)

        import_btn = QPushButton("")
        import_btn.setToolTip("Import Show")
        import_btn.clicked.connect(self.import_show)
        btn_layout.addWidget(import_btn)

        export_btn = QPushButton("")
        export_btn.setToolTip("Export Show")
        export_btn.clicked.connect(self.export_show)
        btn_layout.addWidget(export_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(self.refresh_shows_list)
        btn_layout.addWidget(refresh_btn)

        layout.addWidget(btn_widget)

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

    def refresh_shows_list(self):
        """Refresh shows list with buttons"""
        # Clear existing
        while self.shows_layout.count():
            item = self.shows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Load shows
        self.shows = self.shows_manager.get_all_shows()

        if self.shows:
            # Apply current sort
            self.apply_show_sort()

            for show in self.shows:
                btn = ShowButton(show, self)
                btn.clicked.connect(lambda checked, s=show: self.on_show_selected(s))
                btn.customContextMenuRequested.connect(lambda pos, s=show: self.show_context_menu(pos, s))
                self.shows_layout.addWidget(btn)
        else:
            placeholder = QLabel("No shows yet.\nClick '+ New Show'")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #404040; padding: 20px;")
            self.shows_layout.addWidget(placeholder)

        self.shows_layout.addStretch()
        self.shows_updated.emit()

    def on_show_selected(self, show_data):
        """Handle show selection"""
        self.current_show = show_data

        # Update button states
        for i in range(self.shows_layout.count()):
            item = self.shows_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'show_data'):
                btn = item.widget()
                is_selected = btn.show_data == show_data
                btn.setChecked(is_selected)
                btn.update_style()

        self.show_selected.emit(show_data)

    def filter_shows(self, text):
        """Filter shows list"""
        for i in range(self.shows_layout.count()):
            item = self.shows_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'show_data'):
                    visible = text.lower() in widget.show_data['name'].lower()
                    widget.setVisible(visible)

    def sort_shows(self, sort_type):
        """Sort shows list"""
        self.apply_show_sort()
        self.refresh_shows_list()

    def apply_show_sort(self):
        """Apply current sort to shows"""
        if not self.shows:
            return

        sort_type = self.sort_combo.currentText() if hasattr(self, 'sort_combo') else "Name (A-Z)"

        if "Name" in sort_type:
            self.shows.sort(key=lambda x: x['name'].lower(), reverse="Z-A" in sort_type)
        elif "Date Created" in sort_type:
            self.shows.sort(key=lambda x: x.get('created', ''), reverse="↓" in sort_type)
        elif "Date Modified" in sort_type:
            self.shows.sort(key=lambda x: x.get('modified', ''), reverse="↓" in sort_type)

    def show_context_menu(self, pos, show):
        """Show context menu for show"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1A1A;
                color: #CCCCCC;
                border: 1px solid #2A2A2A;
            }
            QMenu::item:selected {
                background-color: #0EA5E9;
            }
        """)

        duplicate_action = menu.addAction(" Duplicate")
        rename_action = menu.addAction(" Rename")
        menu.addSeparator()
        delete_action = menu.addAction(" Delete")

        action = menu.exec_(self.mapToGlobal(pos))

        if action == duplicate_action:
            self.duplicate_show(show)
        elif action == rename_action:
            self.rename_show(show)
        elif action == delete_action:
            self.delete_show(show)

    def new_show(self):
        """Create new show"""
        name, ok = QInputDialog.getText(self, "New Show", "Enter show name:")
        if ok and name:
            show_path, metadata = self.shows_manager.create_show(name)
            self.refresh_shows_list()
            unreal.log(f"Created show: {name}")

    def duplicate_show(self, show):
        """Duplicate a show"""
        new_path = self.shows_manager.duplicate_show(show['safe_name'])
        if new_path:
            self.refresh_shows_list()
            unreal.log(f"Duplicated show: {show['name']}")

    def rename_show(self, show):
        """Rename a show"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Show",
            "Enter new name:",
            text=show['name']
        )
        if ok and new_name:
            if self.shows_manager.rename_show(show['safe_name'], new_name):
                self.refresh_shows_list()
                unreal.log(f"Renamed show to: {new_name}")

    def delete_show(self, show):
        """Delete a show"""
        reply = QMessageBox.question(
            self,
            "Delete Show",
            f"Are you sure you want to delete '{show['name']}'?\nThis will delete all episodes and panels.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.shows_manager.delete_show(show['safe_name']):
                self.refresh_shows_list()
                unreal.log(f"Deleted show: {show['name']}")

    def import_show(self):
        """Import show from folder"""
        folder = QFileDialog.getExistingDirectory(self, "Import Show")
        if folder:
            unreal.log(f"Importing show from: {folder}")
            # TODO: Implement import logic

    def export_show(self):
        """Export show to folder"""
        if self.current_show:
            folder = QFileDialog.getExistingDirectory(self, "Export To")
            if folder:
                unreal.log(f"Exporting show to: {folder}")
                # TODO: Implement export logic

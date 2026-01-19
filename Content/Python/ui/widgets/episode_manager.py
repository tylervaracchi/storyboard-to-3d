# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Episode management widgets for StoryboardTo3D
"""

import unreal
from pathlib import Path
from core.episodes_manager import EpisodesManager
from .custom_widgets import EpisodeButton

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


class EpisodeManagerWidget(QWidget):
    """Widget for managing episodes"""

    episode_selected = Signal(object)
    episodes_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.episodes = []
        self.episodes_manager = EpisodesManager()
        self.current_show = None
        self.current_episode = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        self.setObjectName("episodesColumn")
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # EPISODES header
        header = self.create_section_header("EPISODES")
        layout.addWidget(header)

        # Current show label
        self.episodes_show_label = QLabel("No show selected")
        self.episodes_show_label.setStyleSheet("color: #0EA5E9; font-size: 11px; padding: 5px;")
        layout.addWidget(self.episodes_show_label)

        # Episodes list container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.episodes_container = QWidget()
        self.episodes_layout = QVBoxLayout(self.episodes_container)
        self.episodes_layout.setSpacing(5)
        self.episodes_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.episodes_container)
        layout.addWidget(scroll, 1)

        # New episode button
        new_ep_btn = QPushButton("+ New Episode")
        new_ep_btn.setObjectName("primaryButton")
        new_ep_btn.clicked.connect(self.new_episode)
        layout.addWidget(new_ep_btn)

        # Import/Export buttons
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(10, 5, 10, 10)

        import_btn = QPushButton("")
        import_btn.setToolTip("Import Episode")
        import_btn.clicked.connect(self.import_episode)
        btn_layout.addWidget(import_btn)

        export_btn = QPushButton("")
        export_btn.setToolTip("Export Episode")
        export_btn.clicked.connect(self.export_episode)
        btn_layout.addWidget(export_btn)

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

    def set_show(self, show_data):
        """Set the current show and load episodes"""
        if show_data:
            self.current_show = show_data['safe_name']
            self.episodes_show_label.setText(f"Show: {show_data['name']}")
            self.load_show_episodes()
        else:
            self.current_show = None
            self.episodes_show_label.setText("No show selected")
            self.clear_episodes()

    def load_show_episodes(self):
        """Load episodes for current show"""
        # Clear existing
        self.clear_episodes()

        if not self.current_show:
            placeholder = QLabel("Select a show first")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #404040; padding: 20px;")
            self.episodes_layout.addWidget(placeholder)
            self.episodes_layout.addStretch()
            return

        # Load episodes
        self.episodes = self.episodes_manager.get_show_episodes(self.current_show)

        if self.episodes:
            # Sort by episode number
            self.episodes.sort(key=lambda x: x.get('number', 0))

            for episode in self.episodes:
                btn = EpisodeButton(episode, self)
                btn.clicked.connect(lambda checked, e=episode: self.on_episode_selected(e))
                btn.customContextMenuRequested.connect(lambda pos, e=episode: self.episode_context_menu(pos, e))
                self.episodes_layout.addWidget(btn)
        else:
            placeholder = QLabel("No episodes yet.\nClick '+ New Episode'")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #404040; padding: 20px;")
            self.episodes_layout.addWidget(placeholder)

        self.episodes_layout.addStretch()
        self.episodes_updated.emit()

    def clear_episodes(self):
        """Clear episodes list"""
        while self.episodes_layout.count():
            item = self.episodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_episode_selected(self, episode_data):
        """Handle episode selection"""
        self.current_episode = episode_data

        # Update button states
        for i in range(self.episodes_layout.count()):
            item = self.episodes_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'episode_data'):
                btn = item.widget()
                is_selected = btn.episode_data == episode_data
                btn.setChecked(is_selected)
                btn.update_style()

        self.episode_selected.emit(episode_data)

    def new_episode(self):
        """Create new episode"""
        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        name, ok = QInputDialog.getText(self, "New Episode", "Enter episode name:")
        if ok and name:
            episode_path, metadata = self.episodes_manager.create_episode(self.current_show, name)
            self.load_show_episodes()
            unreal.log(f"Created episode: {name}")

            # Auto-select the new episode
            self.on_episode_selected(metadata)

    def episode_context_menu(self, pos, episode):
        """Show context menu for episode"""
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
            self.duplicate_episode(episode)
        elif action == rename_action:
            self.rename_episode(episode)
        elif action == delete_action:
            self.delete_episode(episode)

    def duplicate_episode(self, episode):
        """Duplicate an episode"""
        if not self.current_show:
            return

        new_path = self.episodes_manager.duplicate_episode(self.current_show, episode['safe_name'])
        if new_path:
            self.load_show_episodes()
            unreal.log(f"Duplicated episode: {episode['name']}")
        else:
            QMessageBox.warning(self, "Error", f"Failed to duplicate episode '{episode['name']}'")

    def rename_episode(self, episode):
        """Rename an episode"""
        if not self.current_show:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Episode",
            "Enter new name:",
            text=episode['name']
        )
        if ok and new_name and new_name != episode['name']:
            if self.episodes_manager.rename_episode(self.current_show, episode['safe_name'], new_name):
                self.load_show_episodes()
                unreal.log(f"Renamed {episode['name']} to {new_name}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to rename episode '{episode['name']}'")

    def delete_episode(self, episode):
        """Delete an episode"""
        if not self.current_show:
            return

        reply = QMessageBox.question(
            self,
            "Delete Episode",
            f"Are you sure you want to delete '{episode['name']}'?\nThis will delete all panels in the episode.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.episodes_manager.delete_episode(self.current_show, episode['safe_name']):
                if self.current_episode and self.current_episode['safe_name'] == episode['safe_name']:
                    self.current_episode = None
                self.load_show_episodes()
                unreal.log(f"Deleted episode: {episode['name']}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to delete episode '{episode['name']}'")

    def import_episode(self):
        """Import episode"""
        unreal.log("Import episode - TODO")

    def export_episode(self):
        """Export episode"""
        unreal.log("Export episode - TODO")

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Panel management widgets for StoryboardTo3D
"""

import json
import unreal
from .custom_widgets import PanelCard

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


class PanelGrid(QWidget):
    """Grid layout for panels with drag & drop support"""

    panel_clicked = Signal(object)
    panels_reordered = Signal()
    # Context-menu requests handled by the main window (which owns the
    # analyzer and the on-disk episode data)
    panel_analyze_requested = Signal(object)
    panel_delete_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.panels = []
        self.panel_cards = []
        self.setAcceptDrops(True)

        # Create grid layout
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        # Set column count (adjusted for 6-column layout)
        self.columns = 3

    def set_panels(self, panels):
        """Set panels and create cards"""
        # Clear existing cards
        self.clear()

        self.panels = panels
        self.panel_cards = []

        # Create cards (no per-card logging: rebuilding the grid used to spam
        # O(N*8) lines into the UE Output Log)
        for i, panel in enumerate(panels):
            card = PanelCard(panel, self)
            card.clicked.connect(self._on_panel_clicked)
            card.customContextMenuRequested.connect(lambda pos, p=panel: self.show_context_menu(pos, p))

            # Add to grid
            row = i // self.columns
            col = i % self.columns
            self.grid_layout.addWidget(card, row, col)
            self.panel_cards.append(card)

        # Add stretch at the end
        self.grid_layout.setRowStretch(len(panels) // self.columns + 1, 1)

    def _on_panel_clicked(self, panel_data):
        """Handle panel click - ensure only one is selected"""
        # Deselect all cards
        for card in self.panel_cards:
            card.set_selected(False)

        # Select the clicked card
        clicked_card = next((card for card in self.panel_cards if card.panel_data == panel_data), None)
        if clicked_card:
            clicked_card.set_selected(True)

        # Emit the clicked signal
        self.panel_clicked.emit(panel_data)

    def clear(self):
        """Clear all cards"""
        for card in self.panel_cards:
            card.deleteLater()
        self.panel_cards = []

        # Clear layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def handle_panel_drop(self, target_card, source_data):
        """Handle panel drop for reordering"""
        try:
            source_panel = json.loads(source_data)
            target_panel = target_card.panel_data

            # Find indices
            source_idx = next((i for i, p in enumerate(self.panels) if p['path'] == source_panel['path']), None)
            target_idx = next((i for i, p in enumerate(self.panels) if p['path'] == target_panel['path']), None)

            if source_idx is not None and target_idx is not None and source_idx != target_idx:
                # Reorder panels
                self.panels.insert(target_idx, self.panels.pop(source_idx))
                self.set_panels(self.panels)
                self.panels_reordered.emit()
        except Exception as e:
            unreal.log_error(f"Drop error: {e}")

    def show_context_menu(self, pos, panel):
        """Show context menu for panel"""
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

        # Add actions ("Duplicate" removed until actually implemented -
        # it was a silent no-op)
        analyze_action = menu.addAction(" Analyze")
        menu.addSeparator()
        delete_action = menu.addAction(" Delete")

        # Execute menu
        action = menu.exec_(self.mapToGlobal(pos))

        # Handle actions
        if action == analyze_action:
            self.analyze_panel(panel)
        elif action == delete_action:
            self.delete_panel(panel)

    def analyze_panel(self, panel):
        """Analyze a panel: delegate to the main window's analyzer"""
        unreal.log(f"Analyze requested from context menu: {panel['name']}")
        self.panel_analyze_requested.emit(panel)

    def delete_panel(self, panel):
        """Delete a panel (file + metadata, via the main window)"""
        reply = QMessageBox.question(
            self,
            "Delete Panel",
            f"Are you sure you want to delete '{panel['name']}'?\n\n"
            "This removes the panel image from the episode's Panels folder.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # The main window removes the file and metadata entry, then
            # reloads; removing only from the in-memory list made the panel
            # reappear on the next episode load
            self.panel_delete_requested.emit(panel)

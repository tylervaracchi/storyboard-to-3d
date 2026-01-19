# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Custom widget classes for StoryboardTo3D UI
"""

import json
from pathlib import Path

# Qt imports with compatibility
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


class ShowButton(QPushButton):
    """Custom button for shows with hover effects"""
    def __init__(self, show_data, parent=None):
        super().__init__(show_data['name'], parent)
        self.show_data = show_data
        self.setObjectName("showButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setCheckable(True)
        self.update_style()

    def update_style(self):
        """Update button style based on selection"""
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton#showButton {
                    background-color: #0EA5E9;
                    color: #FFFFFF;
                    border: 2px solid #0EA5E9;
                    border-radius: 4px;
                    padding: 10px;
                    text-align: left;
                    font-size: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton#showButton {
                    background-color: #1A1A1A;
                    color: #CCCCCC;
                    border: 1px solid #2A2A2A;
                    border-radius: 4px;
                    padding: 10px;
                    text-align: left;
                    font-size: 12px;
                }
                QPushButton#showButton:hover {
                    background-color: #2A2A2A;
                    border-color: #3A3A3A;
                }
            """)


class EpisodeButton(QPushButton):
    """Custom button for episodes with hover effects"""
    def __init__(self, episode_data, parent=None):
        super().__init__(episode_data['name'], parent)
        self.episode_data = episode_data
        self.setObjectName("episodeButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setCheckable(True)
        self.update_style()

    def update_style(self):
        """Update button style based on selection"""
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton#episodeButton {
                    background-color: #0EA5E9;
                    color: #FFFFFF;
                    border: 2px solid #0EA5E9;
                    border-radius: 4px;
                    padding: 10px;
                    text-align: left;
                    font-size: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton#episodeButton {
                    background-color: #1A1A1A;
                    color: #CCCCCC;
                    border: 1px solid #2A2A2A;
                    border-radius: 4px;
                    padding: 10px;
                    text-align: left;
                    font-size: 12px;
                }
                QPushButton#episodeButton:hover {
                    background-color: #2A2A2A;
                    border-color: #3A3A3A;
                }
            """)


class PanelCard(QFrame):
    """Custom card widget for panels with drag support"""

    clicked = Signal(object)

    def __init__(self, panel_data, parent=None):
        super().__init__(parent)
        self.panel_data = panel_data
        self.is_selected = False
        self.setObjectName("panelCard")
        self.setFrameStyle(QFrame.Box)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAcceptDrops(True)

        # Setup UI
        self.setup_ui()
        self.update_style()

    def setup_ui(self):
        """Setup the panel card UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Thumbnail container with checkmark overlay
        thumb_container = QWidget()
        thumb_container.setFixedSize(120, 80)
        thumb_layout_main = QVBoxLayout(thumb_container)
        thumb_layout_main.setContentsMargins(0, 0, 0, 0)

        # Create a stacked widget for thumbnail + checkmark overlay
        thumb_stack = QWidget()
        thumb_stack.setFixedSize(120, 80)

        # Thumbnail
        self.thumb_label = QLabel(thumb_stack)
        self.thumb_label.setGeometry(0, 0, 120, 80)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("border: 1px solid #2A2A2A; border-radius: 4px; background-color: #0A0A0A;")

        # Load thumbnail preserving aspect ratio
        pixmap = QPixmap(self.panel_data['path'])
        if not pixmap.isNull():
            scaled = pixmap.scaled(120, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_label.setPixmap(scaled)
        else:
            self.thumb_label.setText("No Image")

        # Checkmark overlay (top-right corner)
        self.checkmark_label = QLabel(thumb_stack)
        self.checkmark_label.setGeometry(90, 5, 25, 25)
        self.checkmark_label.setText("")
        self.checkmark_label.setAlignment(Qt.AlignCenter)
        self.checkmark_label.setStyleSheet("""
            background-color: #00AA00;
            color: white;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
        """)
        # Raise checkmark above thumbnail
        self.checkmark_label.raise_()
        # Check if panel has been analyzed
        # More robust check: analysis exists and is not None
        analysis_data = self.panel_data.get('analysis')
        has_analysis = analysis_data is not None

        # If it's a dict, also check it's not empty
        if has_analysis and isinstance(analysis_data, dict):
            has_analysis = len(analysis_data) > 0

        # DEBUG: Log checkmark visibility
        import unreal
        panel_name = Path(self.panel_data['path']).name
        unreal.log(f"[PanelCard] {panel_name}:")
        unreal.log(f"analysis is not None: {analysis_data is not None}")
        unreal.log(f"analysis type: {type(analysis_data)}")
        if isinstance(analysis_data, dict):
            unreal.log(f"analysis keys: {list(analysis_data.keys()) if analysis_data else 'empty dict'}")
        unreal.log(f"=> has_analysis: {has_analysis}")
        unreal.log(f"=> checkmark visible: {has_analysis}")

        self.checkmark_label.setVisible(has_analysis)

        thumb_layout_main.addWidget(thumb_stack, 0, Qt.AlignCenter)
        layout.addWidget(thumb_container)

        # Panel name
        name_label = QLabel(Path(self.panel_data['path']).name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: #CCCCCC; font-size: 10px;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # Status
        self.status_label = QLabel("Not analyzed")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #808080; font-size: 9px;")
        layout.addWidget(self.status_label)

        # Update status based on analysis
        self.update_status(has_analysis)

    def update_status(self, analyzed=False):
        """Update the panel card status"""
        import unreal
        unreal.log(f"[PanelCard.update_status] analyzed={analyzed}")

        if analyzed:
            self.status_label.setText(" Analyzed")
            self.status_label.setStyleSheet("color: #00AA00; font-size: 9px;")
            if hasattr(self, 'checkmark_label'):
                self.checkmark_label.setVisible(True)
                unreal.log(f"[PanelCard.update_status] Checkmark set to VISIBLE")
        else:
            self.status_label.setText("Not analyzed")
            self.status_label.setStyleSheet("color: #808080; font-size: 9px;")
            if hasattr(self, 'checkmark_label'):
                self.checkmark_label.setVisible(False)
                unreal.log(f"[PanelCard.update_status] Checkmark set to HIDDEN")

    def update_style(self):
        """Update card style based on selection"""
        if self.is_selected:
            self.setStyleSheet("""
                QFrame#panelCard {
                    background-color: #0EA5E9;
                    border: 3px solid #0EA5E9;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#panelCard {
                    background-color: #1A1A1A;
                    border: 2px solid #2A2A2A;
                    border-radius: 8px;
                }
                QFrame#panelCard:hover {
                    background-color: #2A2A2A;
                    border-color: #3A3A3A;
                }
            """)

    def set_selected(self, selected):
        """Set selection state"""
        self.is_selected = selected
        self.update_style()

    def mousePressEvent(self, event):
        """Handle mouse press for selection and drag start"""
        if event.button() == Qt.LeftButton:
            # Emit click signal first (parent will handle deselection logic)
            self.clicked.emit(self.panel_data)

            # Start drag
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(json.dumps(self.panel_data))
            drag.setMimeData(mime_data)

            if self.thumb_label.pixmap():
                drag.setPixmap(self.thumb_label.pixmap())
            drag.setHotSpot(event.pos())

            drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event for reordering"""
        if event.mimeData().hasText():
            self.parent().handle_panel_drop(self, event.mimeData().text())
            event.acceptProposedAction()

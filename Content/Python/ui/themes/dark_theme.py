# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Dark theme stylesheet for StoryboardTo3D
"""

def get_dark_stylesheet():
    """Return the complete dark theme stylesheet"""
    return """
    QMainWindow {
        background-color: #0A0A0A;
    }

    #mainWidget {
        background-color: #0A0A0A;
    }

    /* Columns */
    #leftColumn, #rightColumn {
        background-color: #111111;
    }

    #assetLibraryColumn {
        background-color: #0F0F0F;
        border-left: 1px solid #2A2A2A;
        border-right: 1px solid #2A2A2A;
    }

    #episodesColumn {
        background-color: #0D0D0D;
        border-left: 1px solid #2A2A2A;
        border-right: 1px solid #2A2A2A;
    }

    #centerColumn {
        background-color: #0A0A0A;
        border-left: 1px solid #2A2A2A;
        border-right: 1px solid #2A2A2A;
    }

    #scriptColumn {
        background-color: #0D0D0D;
        border-left: 1px solid #2A2A2A;
    }

    /* Headers */
    #sectionHeader {
        background-color: #1A1A1A;
        border-bottom: 1px solid #2A2A2A;
    }

    #sectionHeaderText {
        color: #808080;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
    }

    /* Toolbar */
    QToolBar {
        background-color: #1A1A1A;
        border-bottom: 1px solid #2A2A2A;
        padding: 4px;
    }

    QToolButton {
        background-color: #2A2A2A;
        color: #CCCCCC;
        border: 1px solid #3A3A3A;
        border-radius: 4px;
        padding: 6px 12px;
    }

    QToolButton:hover {
        background-color: #3A3A3A;
        border-color: #0EA5E9;
    }

    QToolButton:disabled {
        background-color: #1A1A1A;
        color: #404040;
    }

    /* Buttons */
    QPushButton {
        background-color: #2A2A2A;
        color: #CCCCCC;
        border: 1px solid #3A3A3A;
        border-radius: 4px;
        padding: 6px;
        font-size: 11px;
    }

    QPushButton:hover {
        background-color: #3A3A3A;
    }

    #primaryButton {
        background-color: #0EA5E9;
        color: #FFFFFF;
        border: none;
        font-weight: bold;
    }

    #primaryButton:hover {
        background-color: #0284C7;
    }

    #primaryButton:pressed {
        background-color: #0369A1;
    }

    #secondaryButton {
        background-color: #374151;
        color: #FFFFFF;
        border: 1px solid #4B5563;
    }

    #secondaryButton:hover {
        background-color: #4B5563;
    }

    #dangerButton {
        background-color: #991B1B;
        color: #FFFFFF;
        border: none;
    }

    #dangerButton:hover {
        background-color: #DC2626;
    }

    #dangerButton:pressed {
        background-color: #7F1D1D;
    }

    #importButton {
        background-color: #1A1A1A;
        color: #0EA5E9;
        border: 2px dashed #2A2A2A;
        padding: 15px;
    }

    /* Inputs */
    QLineEdit, QComboBox, QDoubleSpinBox {
        background-color: #1A1A1A;
        border: 1px solid #2A2A2A;
        border-radius: 4px;
        padding: 4px;
        color: #FFFFFF;
        font-size: 11px;
    }

    QLineEdit:focus, QComboBox:focus {
        border-color: #0EA5E9;
    }

    /* Scrollbars */
    QScrollBar:vertical {
        background-color: #0A0A0A;
        width: 8px;
    }

    QScrollBar::handle:vertical {
        background-color: #2A2A2A;
        border-radius: 4px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #3A3A3A;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }

    /* GroupBox */
    QGroupBox {
        color: #CCCCCC;
        border: 1px solid #2A2A2A;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
        font-size: 11px;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: #808080;
    }

    /* ListWidget */
    QListWidget {
        background-color: #0A0A0A;
        border: 1px solid #2A2A2A;
        color: #CCCCCC;
        font-size: 11px;
    }

    QListWidget::item:selected {
        background-color: #0EA5E9;
    }

    QListWidget::item:hover {
        background-color: #1A1A1A;
    }

    /* TextEdit */
    QTextEdit {
        background-color: #0A0A0A;
        border: 1px solid #2A2A2A;
        color: #CCCCCC;
    }

    /* Progress Bar */
    QProgressBar {
        border: 1px solid #2A2A2A;
        border-radius: 4px;
        text-align: center;
        background-color: #1A1A1A;
    }

    QProgressBar::chunk {
        background-color: #0EA5E9;
        border-radius: 3px;
    }

    /* Other */
    QLabel {
        color: #CCCCCC;
        font-size: 11px;
    }

    #infoText {
        color: #808080;
    }

    #previewFrame {
        background-color: #0A0A0A;
        border: 1px solid #2A2A2A;
        border-radius: 4px;
    }

    /* Menu */
    QMenuBar {
        background-color: #1A1A1A;
        color: #CCCCCC;
    }

    QMenuBar::item:selected {
        background-color: #2A2A2A;
    }

    QMenu {
        background-color: #1A1A1A;
        color: #CCCCCC;
        border: 1px solid #2A2A2A;
    }

    QMenu::item:selected {
        background-color: #0EA5E9;
    }

    QMenu::separator {
        height: 1px;
        background-color: #2A2A2A;
        margin: 4px 0;
    }

    /* Dialog */
    QDialog {
        background-color: #1A1A1A;
    }

    QDialogButtonBox QPushButton {
        min-width: 80px;
    }

    /* Tab Widget */
    QTabWidget::pane {
        border: 1px solid #2A2A2A;
        background-color: #0A0A0A;
    }

    QTabBar::tab {
        background-color: #1A1A1A;
        color: #808080;
        padding: 8px 16px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background-color: #0A0A0A;
        color: #FFFFFF;
    }

    QTabBar::tab:hover {
        background-color: #2A2A2A;
    }

    /* Splitter */
    QSplitter::handle {
        background-color: #2A2A2A;
    }

    QSplitter::handle:horizontal {
        width: 2px;
    }

    QSplitter::handle:vertical {
        height: 2px;
    }

    /* Message Box */
    QMessageBox {
        background-color: #1A1A1A;
    }

    QMessageBox QLabel {
        color: #CCCCCC;
    }

    /* Tooltips */
    QToolTip {
        background-color: #2A2A2A;
        color: #CCCCCC;
        border: 1px solid #3A3A3A;
        padding: 4px;
    }
    """

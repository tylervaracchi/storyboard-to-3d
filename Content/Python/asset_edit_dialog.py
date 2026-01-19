# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ASSET LIBRARY EDIT DIALOG WITH THUMBNAIL SUPPORT
Enhanced UI for editing assets with image preview and upload
"""

from core.utils import sanitize_asset_data
import unreal
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QGroupBox, QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor
from pathlib import Path

class AssetEditDialog(QDialog):
    """Enhanced edit dialog with thumbnail support"""

    asset_updated = Signal(str, str)  # asset_name, category

    def __init__(self, asset_name, category, parent=None):
        super().__init__(parent)
        self.asset_name = asset_name
        self.category = category

        # Get the library from parent widget (AssetLibraryWidget)
        if parent and hasattr(parent, 'library'):
            self.lib = parent.library
        else:
            # Fallback to creating a show-specific library
            from ui.widgets.asset_library_widget import ShowSpecificAssetLibrary
            self.lib = ShowSpecificAssetLibrary()
            unreal.log_warning("AssetEditDialog: No parent library, using empty library")

        self.thumbnail_path = None
        self.original_data = {}

        self.setWindowTitle(f"Edit {asset_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setup_ui()
        self.load_asset_data()

    def setup_ui(self):
        """Create the UI with thumbnail section"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel(f"<h2>Edit {self.asset_name}</h2>")
        layout.addWidget(title)

        # Main content area
        content_layout = QHBoxLayout()

        # Left side - Thumbnail
        thumbnail_group = QGroupBox("Thumbnail")
        thumbnail_layout = QVBoxLayout()

        # Thumbnail display
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setMinimumSize(256, 256)
        self.thumbnail_label.setMaximumSize(256, 256)
        self.thumbnail_label.setFrameStyle(QFrame.Box)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #666;
                background-color: #2b2b2b;
                border-radius: 5px;
            }
        """)
        thumbnail_layout.addWidget(self.thumbnail_label)

        # Thumbnail info
        self.thumbnail_info = QLabel("No thumbnail")
        self.thumbnail_info.setAlignment(Qt.AlignCenter)
        thumbnail_layout.addWidget(self.thumbnail_info)

        # Thumbnail buttons
        thumb_btn_layout = QVBoxLayout()

        self.browse_btn = QPushButton(" Browse Image...")
        self.browse_btn.clicked.connect(self.browse_thumbnail)
        thumb_btn_layout.addWidget(self.browse_btn)

        self.capture_btn = QPushButton(" Capture from Viewport")
        self.capture_btn.clicked.connect(self.capture_viewport)
        thumb_btn_layout.addWidget(self.capture_btn)

        self.generate_btn = QPushButton(" Auto Generate")
        self.generate_btn.clicked.connect(self.generate_thumbnail)
        thumb_btn_layout.addWidget(self.generate_btn)

        self.clear_btn = QPushButton(" Clear Thumbnail")
        self.clear_btn.clicked.connect(self.clear_thumbnail)
        thumb_btn_layout.addWidget(self.clear_btn)

        thumbnail_layout.addLayout(thumb_btn_layout)
        thumbnail_layout.addStretch()
        thumbnail_group.setLayout(thumbnail_layout)
        content_layout.addWidget(thumbnail_group)

        # Right side - Asset details
        details_group = QGroupBox("Asset Details")
        details_layout = QVBoxLayout()

        # Name (read-only)
        details_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(self.asset_name)
        self.name_edit.setReadOnly(True)
        self.name_edit.setStyleSheet("QLineEdit { background-color: #1a1a1a; }")
        details_layout.addWidget(self.name_edit)

        # Asset path
        details_layout.addWidget(QLabel("Asset Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/Game/Path/To/Asset")
        details_layout.addWidget(self.path_edit)

        # Browse for asset
        self.browse_asset_btn = QPushButton(" Browse Unreal Asset...")
        self.browse_asset_btn.clicked.connect(self.browse_unreal_asset)
        details_layout.addWidget(self.browse_asset_btn)

        # Description
        details_layout.addWidget(QLabel("Description:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("Describe this asset...")
        details_layout.addWidget(self.desc_edit)

        # Aliases
        details_layout.addWidget(QLabel("Aliases (comma-separated):"))
        self.aliases_edit = QLineEdit()
        self.aliases_edit.setPlaceholderText("dog, puppy, canine")
        details_layout.addWidget(self.aliases_edit)

        # Category (read-only)
        details_layout.addWidget(QLabel("Category:"))
        self.category_label = QLabel(f"<b>{self.category}</b>")
        details_layout.addWidget(self.category_label)

        details_layout.addStretch()
        details_group.setLayout(details_layout)
        content_layout.addWidget(details_group)

        layout.addLayout(content_layout)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton(" Save Changes")
        self.save_btn.clicked.connect(self.save_changes)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5a2d;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d6a3d;
            }
        """)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def load_asset_data(self):
        """Load existing asset data"""
        asset_dict = self.lib.library.get(self.category, {})
        if self.asset_name in asset_dict:
            # Use central sanitization
            asset_data = sanitize_asset_data(asset_dict[self.asset_name])

            # Update library if it was sanitized
            if asset_dict[self.asset_name] != asset_data:
                asset_dict[self.asset_name] = asset_data
                self.lib.save_library()

            self.original_data = asset_data.copy()

            # Load fields
            self.path_edit.setText(asset_data.get('asset_path', ''))
            self.desc_edit.setText(asset_data.get('description', ''))

            # Load aliases
            aliases = asset_data.get('aliases', [])
            if aliases:
                self.aliases_edit.setText(', '.join(aliases))

            # Load thumbnail
            self.load_thumbnail(asset_data)

    def load_thumbnail(self, asset_data):
        """Load and display thumbnail"""
        thumbnail_info = asset_data.get('thumbnail', {})
        thumb_type = thumbnail_info.get('type', 'none')
        thumb_path = thumbnail_info.get('path', '')

        if thumb_type == 'none' or not thumb_path:
            self.show_placeholder_thumbnail()
            self.thumbnail_info.setText("No thumbnail")
            return

        # Check if file exists
        if Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled)
                self.thumbnail_path = thumb_path

                # Update info
                if thumb_type == 'manual':
                    self.thumbnail_info.setText(" Manual thumbnail")
                elif thumb_type == 'content_browser':
                    self.thumbnail_info.setText(" Auto-generated")
                else:
                    self.thumbnail_info.setText(" Placeholder")
            else:
                self.show_placeholder_thumbnail()
                self.thumbnail_info.setText(" Thumbnail file corrupted")
        else:
            self.show_placeholder_thumbnail()
            self.thumbnail_info.setText(" Thumbnail file missing")

    def show_placeholder_thumbnail(self):
        """Show a placeholder when no thumbnail exists"""
        pixmap = QPixmap(256, 256)
        pixmap.fill(QColor(43, 43, 43))

        painter = QPainter(pixmap)
        painter.setPen(QColor(100, 100, 100))
        painter.setFont(painter.font())
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "No Image\n\nClick Browse\nor Capture")
        painter.end()

        self.thumbnail_label.setPixmap(pixmap)

    def browse_thumbnail(self):
        """Browse for an image file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Thumbnail Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_path:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                # Copy to thumbnails directory
                thumb_dir = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "AssetThumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)

                dest_path = thumb_dir / f"{self.asset_name}_manual.png"
                pixmap.save(str(dest_path))

                # Display it
                scaled = pixmap.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled)
                self.thumbnail_path = str(dest_path)
                self.thumbnail_info.setText(" Manual thumbnail")

                unreal.log(f"Thumbnail saved to: {dest_path}")

    def capture_viewport(self):
        """Capture thumbnail from current viewport"""
        try:
            # Take screenshot
            thumb_dir = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "AssetThumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path = thumb_dir / f"{self.asset_name}_viewport.png"

            # Use Unreal's screenshot command
            unreal.SystemLibrary.execute_console_command(
                None,
                f'HighResShot 256x256 filename="{screenshot_path}"'
            )

            # Wait a moment for screenshot to save
            import time
            time.sleep(0.5)

            # Load and display
            if screenshot_path.exists():
                pixmap = QPixmap(str(screenshot_path))
                scaled = pixmap.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled)
                self.thumbnail_path = str(screenshot_path)
                self.thumbnail_info.setText(" Viewport capture")

                QMessageBox.information(self, "Success", "Viewport captured!\n\nMake sure the asset was visible in the viewport.")
            else:
                QMessageBox.warning(self, "Error", "Failed to capture viewport")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to capture viewport: {e}")

    def generate_thumbnail(self):
        """Auto-generate thumbnail from asset"""
        try:
            asset_path = self.path_edit.text()
            if not asset_path:
                QMessageBox.warning(self, "Error", "Please specify an asset path first")
                return

            # Try to generate a placeholder for now
            # In production, this would capture from Content Browser
            thumb_dir = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "AssetThumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)

            # Create a simple placeholder
            thumb_path = thumb_dir / f"{self.asset_name}_auto.png"

            # For now, just create a colored placeholder
            pixmap = QPixmap(256, 256)
            if 'character' in self.category.lower():
                pixmap.fill(QColor(100, 150, 255))  # Blue
            elif 'prop' in self.category.lower():
                pixmap.fill(QColor(100, 255, 150))  # Green
            else:
                pixmap.fill(QColor(200, 100, 255))  # Purple

            pixmap.save(str(thumb_path))

            # Display it
            scaled = pixmap.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled)
            self.thumbnail_path = str(thumb_path)
            self.thumbnail_info.setText(" Auto-generated")

            QMessageBox.information(self, "Success", "Placeholder thumbnail generated!")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to generate thumbnail: {e}")

    def clear_thumbnail(self):
        """Clear the current thumbnail"""
        self.thumbnail_path = None
        self.show_placeholder_thumbnail()
        self.thumbnail_info.setText("No thumbnail")

    def browse_unreal_asset(self):
        """Browse for Unreal asset (simplified)"""
        # In a real implementation, this would open Unreal's asset picker
        QMessageBox.information(
            self,
            "Browse Asset",
            "Copy the asset path from Content Browser:\n\n"
            "1. Right-click asset in Content Browser\n"
            "2. Copy Reference\n"
            "3. Paste here (remove the type prefix)"
        )

    def save_changes(self):
        """Save all changes to the asset"""
        try:
            # Update asset data
            asset_path = self.path_edit.text()
            description = self.desc_edit.toPlainText()
            aliases_text = self.aliases_edit.text()

            # Parse aliases
            aliases = []
            if aliases_text:
                aliases = [a.strip() for a in aliases_text.split(',') if a.strip()]

            # Update thumbnail in library structure
            asset_dict = self.lib.library.get(self.category, {})
            if self.asset_name not in asset_dict:
                asset_dict[self.asset_name] = {}

            asset_dict[self.asset_name]['asset_path'] = asset_path
            asset_dict[self.asset_name]['description'] = description
            asset_dict[self.asset_name]['aliases'] = aliases

            # Update thumbnail info
            if self.thumbnail_path:
                if 'manual' in self.thumbnail_path:
                    thumb_type = 'manual'
                elif 'viewport' in self.thumbnail_path:
                    thumb_type = 'manual'
                elif '_cb' in self.thumbnail_path:
                    thumb_type = 'content_browser'
                elif '_auto' in self.thumbnail_path:
                    thumb_type = 'placeholder'
                else:
                    thumb_type = 'placeholder'

                asset_dict[self.asset_name]['thumbnail'] = {
                    'type': thumb_type,
                    'path': self.thumbnail_path
                }

            # Save library
            self.lib.save_library()

            # Emit signal
            self.asset_updated.emit(self.asset_name, self.category)

            QMessageBox.information(self, "Success", f"{self.asset_name} updated successfully!")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")


def open_edit_dialog(asset_name, category, parent=None):
    """Convenience function to open the edit dialog"""
    dialog = AssetEditDialog(asset_name, category, parent)
    return dialog.exec_()


# Test function
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Test with Oat
    dialog = AssetEditDialog("Oat", "characters")
    dialog.show()

    sys.exit(app.exec())

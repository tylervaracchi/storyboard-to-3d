# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Main Window for StoryboardTo3D - Refactored version
Uses modular widgets for better organization and performance
"""

import unreal
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from collections import deque

# Add plugin path
plugin_path = Path(__file__).parent.parent
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

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

# Import widgets
from ui.widgets import (
    ShowManagerWidget,
    EpisodeManagerWidget,
    AssetLibraryWidget,
    PanelGrid
)

# Import core modules
from core.panel_analyzer import PanelAnalyzer
from core.asset_matcher import AssetMatcher
from core.scene_builder import SceneBuilder
from core.sequence_generator import SequenceGenerator
from core.utils import get_shows_manager, get_episodes_manager

# Import settings dialog from refactored module
from ui.settings.dialog import SettingsDialog

# Import AI client
try:
    from api.ai_client_enhanced import EnhancedAIClient, create_ai_client
except ImportError:
    from api.ai_client import AIClient as EnhancedAIClient, create_ai_client


class ModernStoryboardWindow(QMainWindow):
    """
    Modern UI with 6-column layout including Episodes - Refactored version
    """

    def __init__(self):
        super().__init__()

        # Core components
        self.panels = []
        self.current_show = None
        self.current_show_path = None
        self.current_episode = None
        self.current_episode_path = None
        self.active_panel = None

        # Core modules - initialized without show context
        self.analyzer = PanelAnalyzer()
        self.shows_manager = get_shows_manager()  # Use singleton
        self.episodes_manager = get_episodes_manager()  # Use singleton
        self.sequence_generator = SequenceGenerator()

        # These will be updated with show context
        self.asset_matcher = None
        self.scene_builder = None

        # Initialize AI client
        self.setup_ai_client()

        # Undo/Redo system
        self.undo_stack = deque(maxlen=50)
        self.redo_stack = deque(maxlen=50)

        # Load settings
        self.settings = self.load_settings()

        # Setup UI
        self.init_ui()

        # Apply theme
        self.apply_modern_dark_theme()

        # Initialize widgets
        self.setup_widget_connections()

        # Initial load
        self.show_manager.refresh_shows_list()
        self.sync_content_browser()
        self.setup_periodic_sync()

    def init_ui(self):
        """Initialize the modern UI with 6 columns"""
        self.setWindowTitle("StoryboardTo3D - Professional Edition")
        self.setGeometry(100, 100, 1800, 900)

        # Set window icon
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

        # Create main widget FIRST
        main_widget = QWidget()
        main_widget.setObjectName("mainWidget")
        self.setCentralWidget(main_widget)

        # Main horizontal layout - 6 columns
        main_layout = QHBoxLayout(main_widget)
        main_layout.setSpacing(1)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Column 1: Shows (15%)
        self.show_manager = ShowManagerWidget()
        main_layout.addWidget(self.show_manager, 15)

        # Column 2: Asset Library (15%)
        self.asset_library = AssetLibraryWidget()
        main_layout.addWidget(self.asset_library, 15)

        # Column 3: Episodes (15%)
        self.episode_manager = EpisodeManagerWidget()
        main_layout.addWidget(self.episode_manager, 15)

        # Column 4: Panels (35%)
        center_column = self.create_center_column()
        main_layout.addWidget(center_column, 35)

        # Column 5: Active Panel (20%)
        right_column = self.create_right_column()
        main_layout.addWidget(right_column, 20)

        # Create menu bar and toolbar AFTER widgets are created
        self.create_menu_bar()
        self.create_main_toolbar()

    def setup_widget_connections(self):
        """Setup connections between widgets"""
        # Show selection updates episodes and asset library
        self.show_manager.show_selected.connect(self.on_show_selected)

        # Episode selection updates panels
        self.episode_manager.episode_selected.connect(self.on_episode_selected)

        # Panel selection updates active panel
        self.panel_grid.panel_clicked.connect(self.on_panel_clicked)
        self.panel_grid.panels_reordered.connect(self.on_panels_reordered)

    def on_show_selected(self, show_data):
        """Handle show selection"""
        self.current_show = show_data['safe_name']
        self.current_show_path = self.shows_manager.shows_root / self.current_show

        # UPDATE ALL CORE MODULES WITH SHOW CONTEXT
        from core.asset_matcher import AssetMatcher
        from core.scene_builder import SceneBuilder
        from core.sequence_generator import SequenceGenerator

        self.asset_matcher = AssetMatcher(show_name=self.current_show)
        self.scene_builder = SceneBuilder(show_name=self.current_show)
        self.sequence_generator = SequenceGenerator(show_name=self.current_show)

        unreal.log(f"All core modules updated for show: {self.current_show}")
        unreal.log(f"- AssetMatcher: Ready with show library")
        unreal.log(f"- SceneBuilder: Will use show-specific assets")
        unreal.log(f"- SequenceGenerator: Will save to show-specific folder")

        # Update dependent widgets
        self.episode_manager.set_show(show_data)
        self.asset_library.set_show(show_data)

        # IMPORTANT: Wait for asset library to load, then update active panel widget
        # The asset library loads asynchronously, so we need to ensure it's loaded
        QTimer.singleShot(100, lambda: self.update_active_panel_context())

        # Clear panels until episode is selected
        self.panels = []
        self.panel_grid.set_panels([])
        self.panels_episode_label.setText("Select an episode")
        if hasattr(self, 'active_panel_widget'):
            self.active_panel_widget.clear_panel()

    def update_active_panel_context(self):
        """Update active panel widget with show context after asset library loads"""
        if hasattr(self, 'active_panel_widget') and hasattr(self, 'asset_library'):
            unreal.log(f"[MainWindow] Updating active panel context for show: {self.current_show}")

            # Check if asset library has loaded its data
            if hasattr(self.asset_library, 'library'):
                # asset_library is the widget, asset_library.library is ShowSpecificAssetLibrary object
                show_library_obj = self.asset_library.library
                unreal.log(f"[MainWindow] Asset library object type: {type(show_library_obj)}")

                # Get the actual data dictionary from the library object
                if hasattr(show_library_obj, 'library') and show_library_obj.library:
                    library_data = show_library_obj.library
                    locations = library_data.get('locations', {})
                    characters = library_data.get('characters', {})
                    unreal.log(f"[MainWindow] Asset library contains:")
                    unreal.log(f"- {len(locations)} locations: {list(locations.keys())}")
                    unreal.log(f"- {len(characters)} characters: {list(characters.keys())}")
            else:
                unreal.log("[MainWindow] Asset library widget has no 'library' attribute yet")
                # Try again after another delay
                QTimer.singleShot(500, lambda: self.update_active_panel_context())
                return

            self.active_panel_widget.set_show_context(
                self.current_show,
                self.asset_library  # Pass the asset library widget
            )

    def on_episode_selected(self, episode_data):
        """Handle episode selection"""
        self.current_episode = episode_data['safe_name']
        self.current_episode_path = Path(episode_data['path'])

        # Update panels label
        self.panels_episode_label.setText(f"Episode: {episode_data['name']}")

        # Load panels for this episode
        self.load_episode_panels()

    def load_episode_panels(self):
        """Load panels for current episode"""
        if not self.current_episode_path:
            return

        panels_path = self.current_episode_path / "Panels"
        if panels_path.exists():
            self.panels = []
            panel_files = sorted(panels_path.glob("*.png")) + sorted(panels_path.glob("*.jpg"))

            # Load panel metadata
            metadata_file = self.current_episode_path / "panels_metadata.json"
            panel_metadata = {}
            if metadata_file.exists():
                try:
                    import json
                    with open(metadata_file, 'r') as f:
                        panel_metadata = json.load(f)
                except Exception as e:
                    unreal.log_warning(f"Failed to load panel metadata: {e}")

            for panel_file in panel_files:
                panel_name = panel_file.name
                # Load saved analysis data if it exists
                saved_data = panel_metadata.get(panel_name, {})



                self.panels.append({
                    'path': str(panel_file),
                    'name': panel_name,
                    'analysis': saved_data.get('analysis'),
                    'characters': saved_data.get('characters', []),
                    'props': saved_data.get('props', []),
                    'location': saved_data.get('location', ''),
                    'shot_type': saved_data.get('shot_type', '')
                })

            self.panel_grid.set_panels(self.panels)
        else:
            self.panels = []
            self.panel_grid.set_panels([])

    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()
        menubar.setObjectName("menuBar")

        # File menu
        file_menu = menubar.addMenu("File")

        new_action = QAction("New Show", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.show_manager.new_show)
        file_menu.addAction(new_action)

        new_episode_action = QAction("New Episode", self)
        new_episode_action.setShortcut("Ctrl+Shift+N")
        new_episode_action.triggered.connect(self.episode_manager.new_episode)
        file_menu.addAction(new_episode_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        self.undo_menu_action = QAction("Undo", self)
        self.undo_menu_action.setShortcut("Ctrl+Z")
        self.undo_menu_action.triggered.connect(self.undo)
        self.undo_menu_action.setEnabled(False)
        edit_menu.addAction(self.undo_menu_action)

        self.redo_menu_action = QAction("Redo", self)
        self.redo_menu_action.setShortcut("Ctrl+Y")
        self.redo_menu_action.triggered.connect(self.redo)
        self.redo_menu_action.setEnabled(False)
        edit_menu.addAction(self.redo_menu_action)

        # Import menu
        import_menu = menubar.addMenu(" Import")
        import_action = QAction("Import Panels", self)
        import_action.triggered.connect(self.import_panels_dialog)
        import_menu.addAction(import_action)

        # Analyze menu
        analyze_menu = menubar.addMenu(" Analyze")
        analyze_all = QAction("Analyze All", self)
        analyze_all.triggered.connect(self.analyze_all_panels)
        analyze_menu.addAction(analyze_all)

    def create_main_toolbar(self):
        """Create main toolbar"""
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)

        # Add spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Undo action
        self.undo_action = QAction("↶ Undo", self)
        self.undo_action.setToolTip("Undo last action (Ctrl+Z)")
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        toolbar.addAction(self.undo_action)

        # Redo action
        self.redo_action = QAction("↷ Redo", self)
        self.redo_action.setToolTip("Redo last action (Ctrl+Y)")
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        toolbar.addAction(self.redo_action)

        toolbar.addSeparator()

        # Settings action
        settings_action = QAction(" Settings", self)
        settings_action.setToolTip("Open Settings (Ctrl+,)")
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

    def create_center_column(self):
        """Create center column with panel grid"""
        column = QWidget()
        column.setObjectName("centerColumn")
        main_layout = QHBoxLayout(column)
        main_layout.setSpacing(1)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left side - Panels
        panels_section = QWidget()
        panels_layout = QVBoxLayout(panels_section)
        panels_layout.setSpacing(0)
        panels_layout.setContentsMargins(0, 0, 0, 0)

        # PANELS header
        header = self.create_section_header("PANELS")
        panels_layout.addWidget(header)

        # Episode label
        self.panels_episode_label = QLabel("Select an episode")
        self.panels_episode_label.setStyleSheet("color: #808080; font-size: 10px; padding: 5px;")
        panels_layout.addWidget(self.panels_episode_label)

        # Import button
        import_widget = QWidget()
        import_layout = QHBoxLayout(import_widget)
        import_layout.setContentsMargins(10, 10, 10, 10)

        import_btn = QPushButton(" Import Panels")
        import_btn.setObjectName("importButton")
        import_btn.clicked.connect(self.import_panels_dialog)
        import_layout.addWidget(import_btn)

        panels_layout.addWidget(import_widget)

        # Panel grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.panel_grid = PanelGrid()
        scroll.setWidget(self.panel_grid)
        panels_layout.addWidget(scroll, 1)

        main_layout.addWidget(panels_section, 3)

        # Script Analyzer section removed

        return column

    def create_right_column(self):
        """Create right column with active panel details"""
        from ui.widgets.active_panel_widget import ActivePanelWidget
        self.active_panel_widget = ActivePanelWidget(parent=self)

        # Connect signals
        self.active_panel_widget.analyze_panel.connect(self.analyze_active_panel)
        self.active_panel_widget.generate_scene.connect(self.generate_active_panel)

        # Pass asset library reference to active panel widget
        self.active_panel_widget.asset_library = self.asset_library

        return self.active_panel_widget

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

    def import_panels_dialog(self):
        """Import panels dialog"""
        if not self.current_episode:
            QMessageBox.warning(self, "No Episode", "Please select an episode first")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Panels",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )

        if files:
            imported = self.episodes_manager.import_panels_to_episode(
                self.current_show,
                self.current_episode,
                files
            )
            self.load_episode_panels()
            unreal.log(f"Imported {len(imported)} panels to episode")

    # Implement remaining required methods...
    def setup_ai_client(self):
        """Setup AI client"""
        try:
            self.ai_client = create_ai_client()
        except Exception as e:
            self.ai_client = None
            unreal.log_warning(f"AI client initialization failed: {e}")

    def load_settings(self):
        """Load application settings"""
        try:
            from core.settings_manager import get_settings
            return get_settings()
        except:
            return {}

    def open_settings(self):
        """Open settings dialog"""
        try:
            dialog = SettingsDialog(self)
            if dialog.exec_():
                self.settings = self.load_settings()
                unreal.log("Settings updated")
        except Exception as e:
            unreal.log_error(f"Failed to open settings: {e}")

    def sync_content_browser(self):
        """Sync with Unreal Content Browser"""
        try:
            unreal.EditorAssetLibrary.sync_browser_to_objects([])
        except:
            pass

    def setup_periodic_sync(self):
        """Setup periodic content browser sync"""
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_content_browser)
        self.sync_timer.start(5000)  # Sync every 5 seconds

    def on_panel_clicked(self, panel_data):
        """Handle panel click"""
        # CRITICAL: Save current panel before switching
        if self.active_panel and self.active_panel != panel_data:
            unreal.log(f"[MainWindow] Switching panels: saving {self.active_panel['name']}")
            # Get current UI state from active panel widget
            if hasattr(self, 'active_panel_widget'):
                # Update active_panel with current UI state
                self.active_panel['characters'] = [
                    self.active_panel_widget.characters_list.item(i).text()
                    for i in range(self.active_panel_widget.characters_list.count())
                ]
                self.active_panel['props'] = [
                    self.active_panel_widget.props_list.item(i).text()
                    for i in range(self.active_panel_widget.props_list.count())
                ]
                self.active_panel['location'] = self.active_panel_widget.location_combo.currentText()
                self.active_panel['shot_type'] = self.active_panel_widget.shot_type_combo.currentText()

                # Save it
                self.save_panel_metadata(self.active_panel)
                unreal.log(f"Saved before switching")

        # Now switch to new panel
        self.active_panel = panel_data
        if hasattr(self, 'active_panel_widget'):
            self.active_panel_widget.set_panel(panel_data)

    def save_panel_metadata(self, panel_data):
        """Save panel analysis data to episode metadata file"""
        if not self.current_episode_path:
            return

        try:
            import json
            metadata_file = self.current_episode_path / "panels_metadata.json"

            # Load existing metadata
            panel_metadata = {}
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    panel_metadata = json.load(f)

            # Update metadata for this panel
            panel_name = panel_data['name']

            # Don't save "Auto" or "Auto-detect" as they're defaults
            location = panel_data.get('location', '')
            if location in ['Auto-detect', 'Auto', '']:
                location = ''

            shot_type = panel_data.get('shot_type', '')
            if shot_type in ['Auto', '']:
                shot_type = ''

            panel_metadata[panel_name] = {
                'analysis': panel_data.get('analysis'),
                'characters': panel_data.get('characters', []),
                'props': panel_data.get('props', []),
                'location': location,
                'shot_type': shot_type
            }

            # Save metadata
            with open(metadata_file, 'w') as f:
                json.dump(panel_metadata, f, indent=2)

            unreal.log(f"Saved panel metadata: {panel_name}")
            unreal.log(f"- Characters: {panel_data.get('characters', [])}")
            unreal.log(f"- Props: {panel_data.get('props', [])}")
            unreal.log(f"- Location: {panel_data.get('location', '')}")
            unreal.log(f"- Shot type: {panel_data.get('shot_type', '')}")
            unreal.log(f"- Has analysis: {panel_data.get('analysis') is not None}")
            # This ensures we don't lose analysis data from other panels
            unreal.log(f"[SaveMeta] Reloading all panels from metadata file...")

            # Reload metadata
            with open(metadata_file, 'r') as f:
                reloaded_metadata = json.load(f)

            # Update ALL panels in the list with their saved data
            for i, p in enumerate(self.panels):
                saved_data = reloaded_metadata.get(p['name'], {})
                if saved_data.get('analysis'):
                    self.panels[i]['analysis'] = saved_data['analysis']
                    self.panels[i]['characters'] = saved_data.get('characters', [])
                    self.panels[i]['props'] = saved_data.get('props', [])
                    self.panels[i]['location'] = saved_data.get('location', '')
                    self.panels[i]['shot_type'] = saved_data.get('shot_type', '')
                    unreal.log(f"[{i}] {p['name']}: Loaded analysis from file")
                else:
                    # No saved data - keep whatever is in memory
                    pass

            # Refresh the panel grid to update visual indicators (checkmarks)
            unreal.log(f"[SaveMeta] About to refresh grid with {len(self.panels)} panels")

            # Force a complete refresh
            self.panel_grid.set_panels(self.panels)

            # Re-select the active panel to maintain selection
            if self.active_panel:
                for card in self.panel_grid.panel_cards:
                    if card.panel_data['name'] == self.active_panel['name']:
                        card.set_selected(True)
                        break

            # Log what the cards received
            unreal.log(f"[SaveMeta] Grid refreshed, checking cards:")
            for i, card in enumerate(self.panel_grid.panel_cards):
                has_it = card.panel_data.get('analysis') is not None
                unreal.log(f"Card {i}: {card.panel_data['name']} - has_analysis: {has_it}")

        except Exception as e:
            unreal.log_error(f"Failed to save panel metadata: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def on_panels_reordered(self):
        """Handle panels reorder"""
        unreal.log("Panels reordered")

    def undo(self):
        """Undo last action"""
        if self.undo_stack:
            action = self.undo_stack.pop()
            self.redo_stack.append(action)
            unreal.log("Undo")
            self.update_undo_redo_state()

    def redo(self):
        """Redo last undone action"""
        if self.redo_stack:
            action = self.redo_stack.pop()
            self.undo_stack.append(action)
            unreal.log("Redo")
            self.update_undo_redo_state()

    def update_undo_redo_state(self):
        """Update undo/redo button states"""
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(bool(self.undo_stack))
        if hasattr(self, 'redo_action'):
            self.redo_action.setEnabled(bool(self.redo_stack))
        if hasattr(self, 'undo_menu_action'):
            self.undo_menu_action.setEnabled(bool(self.undo_stack))
        if hasattr(self, 'redo_menu_action'):
            self.redo_menu_action.setEnabled(bool(self.redo_stack))

    def apply_modern_dark_theme(self):
        """Apply dark theme - moved to separate file for better organization"""
        from ui.themes.dark_theme import get_dark_stylesheet
        self.setStyleSheet(get_dark_stylesheet())

    # Placeholder methods for AI functionality
    def analyze_all_panels(self):
        """Analyze all panels with show context"""
        if not self.panels:
            QMessageBox.warning(self, "No Panels", "No panels to analyze")
            return

        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        unreal.log(f"Analyzing {len(self.panels)} panels for show: {self.current_show}")

        analyzed = 0
        for panel in self.panels:
            try:
                analysis = self.analyzer.analyze_panel(
                    panel['path'],
                    show_name=self.current_show
                )
                panel['analysis'] = analysis
                analyzed += 1
            except Exception as e:
                unreal.log_error(f"Failed to analyze {panel['name']}: {e}")

        unreal.log(f"Analyzed {analyzed}/{len(self.panels)} panels")
        QMessageBox.information(self, "Analysis Complete",
                               f"Successfully analyzed {analyzed} of {len(self.panels)} panels")

    def analyze_active_panel(self):
        """Analyze active panel with show context"""
        if not self.active_panel:
            QMessageBox.warning(self, "No Panel", "Please select a panel first")
            return

        unreal.log(f"Analyzing panel: {self.active_panel['name']}")

        # Analyze with show context for better recognition
        try:
            analysis = self.analyzer.analyze_panel(
                self.active_panel['path'],
                show_name=self.current_show if self.current_show else None
            )

            self.active_panel['analysis'] = analysis

            # Update active panel widget if it exists
            if hasattr(self, 'active_panel_widget'):
                self.active_panel_widget.update_analysis(analysis)

            unreal.log(f"Panel analyzed: {len(analysis.get('characters', []))} characters, "
                      f"{len(analysis.get('props', []))} props detected")

        except Exception as e:
            unreal.log_error(f"Analysis failed: {e}")
            QMessageBox.warning(self, "Error", f"Failed to analyze panel:\n{str(e)}")

    def generate_active_panel(self):
        """Generate scene for active panel using show-specific assets"""
        if not self.active_panel:
            QMessageBox.warning(self, "No Panel", "Please select a panel first")
            return

        if not self.current_show:
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        if not self.scene_builder:
            # Initialize with current show if needed
            from core.scene_builder import SceneBuilder
            self.scene_builder = SceneBuilder(show_name=self.current_show)

        unreal.log(f"Generating scene for panel: {self.active_panel['name']}")
        unreal.log(f"Using assets from show: {self.current_show}")

        # Analyze panel if not already done
        if not self.active_panel.get('analysis'):
            unreal.log("Analyzing panel first...")
            # Run analysis with show context
            analysis = self.analyzer.analyze_panel(
                self.active_panel['path'],
                show_name=self.current_show  # Pass show context
            )
            self.active_panel['analysis'] = analysis

        # Build the scene with show-specific assets
        try:
            scene_data = self.scene_builder.build_scene(
                self.active_panel['analysis'],
                panel_index=self.panels.index(self.active_panel) if self.active_panel in self.panels else 0
            )

            if scene_data:
                unreal.log(f"Scene generated with {len(scene_data['actors'])} actors")
                QMessageBox.information(self, "Success",
                    f"Scene generated!\n\n"
                    f"Actors: {len(scene_data['actors'])}\n"
                    f"Camera: {'Yes' if scene_data['camera'] else 'No'}\n"
                    f"Lights: {len(scene_data['lights'])}")
            else:
                QMessageBox.warning(self, "Error", "Failed to generate scene")

        except Exception as e:
            unreal.log_error(f"Scene generation failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to generate scene:\n{str(e)}")

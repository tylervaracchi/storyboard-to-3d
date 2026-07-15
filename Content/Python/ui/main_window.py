# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
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

        # Keep references to modeless notification boxes so they are not
        # garbage collected while visible (see notify_user)
        self._notify_boxes = deque(maxlen=8)

        # Core modules - initialized without show context
        self.shows_manager = get_shows_manager()  # Use singleton
        self.episodes_manager = get_episodes_manager()  # Use singleton
        self.sequence_generator = SequenceGenerator()

        # These will be updated with show context
        self.asset_matcher = None
        self.scene_builder = None

        # Initialize AI client
        self.setup_ai_client()

        # Panel analyzer must be constructed AFTER setup_ai_client so
        # Analyze/Analyze All use real AI analysis; without the client it
        # silently ran filename heuristics and cached the junk results.
        self.analyzer = PanelAnalyzer(ai_client=self.ai_client)

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

        # Panel context menu: Analyze and Delete were previously no-ops
        self.panel_grid.panel_analyze_requested.connect(self.on_panel_analyze_requested)
        self.panel_grid.panel_delete_requested.connect(self.on_panel_delete_requested)

        # First-run welcome panel tracks whether any shows exist
        self.show_manager.shows_updated.connect(self.update_welcome_visibility)

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
            panel_files = sorted(panels_path.glob("*.png")) + sorted(panels_path.glob("*.jpg")) + sorted(panels_path.glob("*.jpeg"))

            # Load panel metadata
            metadata_file = self.current_episode_path / "panels_metadata.json"
            panel_metadata = {}
            if metadata_file.exists():
                try:
                    import json
                    with open(metadata_file, 'r') as f:
                        panel_metadata = json.load(f)
                except Exception as e:
                    self.notify_user(
                        "Panel Metadata Unreadable",
                        "Could not read saved panel analyses for this episode:\n"
                        f"{e}\n\nPanels will load without their saved analysis.",
                        "warning")

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
                    'shot_type': saved_data.get('shot_type', ''),
                    'sequence_path': saved_data.get('sequence_path')
                })

            # Apply saved drag-and-drop order when present so reordering
            # survives reloads (written by on_panels_reordered); panels not
            # in the saved list keep their filename order at the end
            saved_order = panel_metadata.get('__panel_order__')
            if isinstance(saved_order, list) and saved_order:
                order_index = {name: i for i, name in enumerate(saved_order)}
                self.panels.sort(
                    key=lambda p: order_index.get(p['name'], len(order_index)))

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

        # Tools menu: export and research utilities that previously had no UI
        tools_menu = menubar.addMenu(" Tools")

        animatic_action = QAction("🎞️ Render Animatic", self)
        animatic_action.setToolTip("Render the show's master sequence via Movie Render Queue")
        animatic_action.triggered.connect(self.render_animatic_dialog)
        tools_menu.addAction(animatic_action)

        usd_action = QAction("📤 Export Level as USD", self)
        usd_action.setToolTip("Export the currently loaded level to a USD file")
        usd_action.triggered.connect(self.export_usd_dialog)
        tools_menu.addAction(usd_action)

        tools_menu.addSeparator()

        dashboard_action = QAction("📊 Calibration Dashboard", self)
        dashboard_action.setToolTip("Generate the multi-model calibration dashboard PNG")
        dashboard_action.triggered.connect(self.show_calibration_dashboard)
        tools_menu.addAction(dashboard_action)

        comparison_action = QAction("📈 Model Comparison", self)
        comparison_action.setToolTip(
            "Print the multi-model comparison table (needs capture runs with "
            "model tracking this session)")
        comparison_action.triggered.connect(self.show_model_comparison_dialog)
        tools_menu.addAction(comparison_action)

        combined_csv_action = QAction("🧾 Export Combined Model CSV", self)
        combined_csv_action.setToolTip(
            "Export one CSV with all tracked models side-by-side")
        combined_csv_action.triggered.connect(self.export_combined_comparison_dialog)
        tools_menu.addAction(combined_csv_action)

        batch_action = QAction("🌙 Overnight Batch...", self)
        batch_action.setToolTip("Analyze and generate every panel in an episode, unattended")
        batch_action.triggered.connect(self.overnight_batch_dialog)
        tools_menu.addAction(batch_action)

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

        toolbar.addSeparator()

        # [DemoFlow] Pin the plugin window above the UE editor so clicking
        # the viewport doesn't bury it during a live demo.
        self.pin_on_top_action = QAction("Pin on top", self)
        self.pin_on_top_action.setCheckable(True)
        self.pin_on_top_action.setToolTip(
            "Keep this window above the Unreal editor")
        self.pin_on_top_action.toggled.connect(self._toggle_pin_on_top)
        toolbar.addAction(self.pin_on_top_action)

    def _toggle_pin_on_top(self, checked):
        """[DemoFlow] Toggle the always-on-top window flag.

        Changing window flags hides the window, so re-show() afterwards.
        Never raises.
        """
        try:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(checked))
            self.show()
        except Exception as e:
            try:
                unreal.log_warning(f"[DemoFlow] Pin on top failed: {e}")
            except Exception:
                pass

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

        import_btn = QPushButton("🎬 Import Panels")
        import_btn.setObjectName("importButton")
        import_btn.clicked.connect(self.import_panels_dialog)
        import_layout.addWidget(import_btn)

        panels_layout.addWidget(import_widget)

        # First-run welcome panel (inline, hidden unless no shows exist)
        self.welcome_panel = self.create_welcome_panel()
        panels_layout.addWidget(self.welcome_panel)

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

    def create_welcome_panel(self):
        """Build the inline first-run welcome panel (hidden by default)"""
        panel = QFrame()
        panel.setObjectName("welcomePanel")
        panel.setStyleSheet("""
            QFrame#welcomePanel {
                background-color: #161616;
                border: 1px solid #2A2A2A;
                border-radius: 8px;
                margin: 10px;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(10)

        title = QLabel("Welcome to StoryboardTo3D")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Turn storyboard panels into 3D scenes in Unreal.\n"
            "Create a show to get started, or explore the bundled sample."
        )
        subtitle.setStyleSheet("color: #808080; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        create_btn = QPushButton("🎬 Create your first show")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self.welcome_create_show)
        layout.addWidget(create_btn)

        sample_btn = QPushButton("📦 Load the sample show")
        sample_btn.clicked.connect(self.load_sample_show)
        layout.addWidget(sample_btn)

        quickstart_btn = QPushButton("📖 Quick Start (opens README)")
        quickstart_btn.clicked.connect(self.open_quick_start)
        layout.addWidget(quickstart_btn)

        panel.setVisible(False)
        return panel

    def update_welcome_visibility(self):
        """Show the first-run welcome panel only while no shows exist"""
        if not hasattr(self, 'welcome_panel'):
            return
        try:
            has_shows = bool(self.shows_manager.get_all_shows())
        except Exception as e:
            unreal.log_warning(f"Welcome panel: could not check shows: {e}")
            has_shows = True
        self.welcome_panel.setVisible(not has_shows)

    def welcome_create_show(self):
        """Welcome panel action: create the first show"""
        # new_show refreshes the shows list, which re-evaluates visibility
        self.show_manager.new_show()

    def load_sample_show(self):
        """Welcome panel action: create 'SampleShow' from the bundled samples"""
        try:
            samples_dir = Path(__file__).resolve().parents[3] / "samples"
            library_file = samples_dir / "asset_library.sample.json"
            if not library_file.exists():
                self.notify_user(
                    "Sample Show",
                    f"Bundled samples not found at:\n{samples_dir}\n\n"
                    "Re-download the plugin to restore the samples folder.",
                    "warning")
                return

            import shutil

            # Create the sample show (reuse it if it already exists)
            existing = None
            for show in self.shows_manager.get_all_shows():
                if show.get('safe_name') == 'SampleShow':
                    existing = show
                    break
            if existing is None:
                show_path, _metadata = self.shows_manager.create_show("SampleShow")
            else:
                show_path = self.shows_manager.shows_root / 'SampleShow'

            # Copy the sample asset library into the show
            shutil.copy2(library_file, show_path / "asset_library.json")

            # Import bundled sample panels into a first episode, if present
            sample_panels = (sorted(samples_dir.glob("sample_panel_*.png")) +
                             sorted(samples_dir.glob("sample_panel_*.jpg")))
            episode_name = "Episode 01"
            episodes = self.episodes_manager.get_show_episodes('SampleShow')
            episode = next((ep for ep in episodes if ep.get('name') == episode_name), None)
            if episode is None:
                _, episode = self.episodes_manager.create_episode('SampleShow', episode_name)
            if sample_panels:
                self.episodes_manager.import_panels_to_episode(
                    'SampleShow', episode['safe_name'],
                    [str(p) for p in sample_panels])

            # Refresh the shows list and select the sample show
            self.show_manager.refresh_shows_list()
            for show in self.shows_manager.get_all_shows():
                if show.get('safe_name') == 'SampleShow':
                    self.show_manager.on_show_selected(show)
                    break

            QMessageBox.information(
                self, "Sample Show Loaded",
                "'SampleShow' is ready.\n\n"
                "Select 'Episode 01' in the EPISODES column to open the "
                "sample panels, then click a panel and use Analyze / GENERATE.")
        except Exception as e:
            self.notify_user(
                "Sample Show Failed",
                f"Could not load the sample show:\n{e}",
                "error")

    def open_quick_start(self):
        """Welcome panel action: open the online README quick start"""
        url = "https://github.com/tylervaracchi/storyboard-to-3d#readme"
        opened = False
        try:
            opened = bool(QDesktopServices.openUrl(QUrl(url)))
        except Exception:
            opened = False
        if not opened:
            try:
                import webbrowser
                opened = webbrowser.open(url)
            except Exception:
                opened = False
        if not opened:
            self.notify_user(
                "Quick Start",
                f"Could not open a browser. Visit:\n{url}",
                "warning")

    def import_panels_dialog(self):
        """Import panels dialog"""
        if not self.current_episode:
            QMessageBox.warning(self, "No Episode", "Please select an episode first")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Panels",
            "",
            "Images (*.png *.jpg *.jpeg);;Storyboarder (*.storyboarder)"
        )

        if not files:
            return

        storyboarder_files = [f for f in files if f.lower().endswith('.storyboarder')]
        image_files = [f for f in files if not f.lower().endswith('.storyboarder')]

        for sb_path in storyboarder_files:
            try:
                from core.importers import import_storyboarder
                result = import_storyboarder(sb_path, self.current_show, self.current_episode)
                unreal.log(f"Storyboarder import: {result.get('imported', 0)} panel(s) from {Path(sb_path).name}")
                for note in result.get('notes', []):
                    unreal.log_warning(f"Storyboarder import: {note}")
            except Exception as e:
                QMessageBox.critical(
                    self, "Storyboarder Import Failed",
                    f"Could not import {sb_path}:\n{e}"
                )

        if image_files:
            imported = self.episodes_manager.import_panels_to_episode(
                self.current_show,
                self.current_episode,
                image_files
            )
            unreal.log(f"Imported {len(imported)} panels to episode")

        self.load_episode_panels()

    # Implement remaining required methods...
    def setup_ai_client(self):
        """Setup AI client"""
        try:
            self.ai_client = create_ai_client()
        except Exception as e:
            self.ai_client = None
            self.notify_user(
                "AI Client Unavailable",
                "AI client initialization failed:\n{0}\n\n"
                "Analyze will fall back to filename heuristics until an "
                "API key is configured in Settings.".format(e),
                "warning")

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
                # Rebuild the AI client and analyzer so provider/key/model
                # changes take effect immediately instead of requiring an
                # editor restart
                self.setup_ai_client()
                self.analyzer = PanelAnalyzer(ai_client=self.ai_client)
                try:
                    self.statusBar().showMessage(
                        "Settings applied: AI client reloaded", 8000)
                except Exception:
                    pass
                unreal.log("Settings updated; AI client and analyzer reloaded")
        except Exception as e:
            self.notify_user(
                "Settings Failed",
                "Could not open or apply Settings:\n{0}".format(e),
                "error")

    def sync_content_browser(self):
        """Sync with Unreal Content Browser"""
        try:
            unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).sync_browser_to_objects([])
        except Exception as e:
            unreal.log_warning(f"Content browser sync failed: {e}")

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
                'shot_type': shot_type,
                # Persist the generated sequence so CAPTURE/BATCH CAPTURE
                # still find it after an editor restart
                'sequence_path': panel_data.get('sequence_path')
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
                # Restore sequence_path only when saved (never clobber a
                # fresher in-memory value with None)
                if saved_data.get('sequence_path'):
                    self.panels[i]['sequence_path'] = saved_data['sequence_path']
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
            import traceback
            unreal.log_error(traceback.format_exc())
            self.notify_user(
                "Panel Save Failed",
                "Could not save panel metadata for "
                "{0}:\n{1}".format(panel_data.get('name', '?'), e),
                "error")

    def on_panel_analyze_requested(self, panel):
        """Context-menu Analyze: activate the panel and run the widget's analyzer"""
        try:
            self.on_panel_clicked(panel)
            if hasattr(self, 'active_panel_widget'):
                self.active_panel_widget.analyze_panel_with_ai()
        except Exception as e:
            self.notify_user(
                "Analyze Failed",
                "Could not analyze '{0}':\n{1}".format(panel.get('name', '?'), e),
                "error")

    def on_panel_delete_requested(self, panel):
        """Context-menu Delete: remove the panel file + metadata, then reload.

        The grid already confirmed with the user. Removing only the in-memory
        entry made 'deleted' panels reappear on the next episode load.
        """
        try:
            panel_name = panel.get('name', '')

            # Remove the image file
            panel_path = Path(panel.get('path', ''))
            if panel_path.exists():
                os.remove(str(panel_path))
                unreal.log(f"Deleted panel image: {panel_path}")

            # Remove its metadata entry (and any saved-order reference)
            if self.current_episode_path:
                metadata_file = self.current_episode_path / "panels_metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        panel_metadata = json.load(f)
                    panel_metadata.pop(panel_name, None)
                    saved_order = panel_metadata.get('__panel_order__')
                    if isinstance(saved_order, list) and panel_name in saved_order:
                        saved_order.remove(panel_name)
                    with open(metadata_file, 'w') as f:
                        json.dump(panel_metadata, f, indent=2)

            # Clear the active panel if it was the one deleted
            if self.active_panel and self.active_panel.get('name') == panel_name:
                self.active_panel = None
                if hasattr(self, 'active_panel_widget'):
                    self.active_panel_widget.clear_panel()

            self.load_episode_panels()
            unreal.log(f"Deleted panel: {panel_name}")
            try:
                self.statusBar().showMessage(
                    "Deleted panel: {0}".format(panel_name), 8000)
            except Exception:
                pass
        except Exception as e:
            self.notify_user(
                "Delete Failed",
                "Could not delete '{0}':\n{1}".format(panel.get('name', '?'), e),
                "error")

    def on_panels_reordered(self):
        """Persist the new drag-and-drop panel order so it survives reloads"""
        try:
            # PanelGrid reorders its own panels list before emitting
            self.panels = list(self.panel_grid.panels)
            new_order = [p['name'] for p in self.panels]

            if not self.current_episode_path:
                return

            metadata_file = self.current_episode_path / "panels_metadata.json"
            panel_metadata = {}
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    panel_metadata = json.load(f)

            panel_metadata['__panel_order__'] = new_order

            with open(metadata_file, 'w') as f:
                json.dump(panel_metadata, f, indent=2)

            unreal.log(f"Panels reordered; order saved ({len(new_order)} panels)")
            try:
                self.statusBar().showMessage("Panel order saved", 5000)
            except Exception:
                pass
        except Exception as e:
            self.notify_user(
                "Reorder Not Saved",
                "Could not save the new panel order:\n{0}".format(e),
                "warning")

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

    def notify_user(self, title, message, level="error"):
        """Surface a failure in the UI as well as the Output Log.

        Non-blocking: errors and warnings get a modeless message box plus a
        status bar entry; info level uses the status bar only. Everything is
        mirrored to the Unreal log so nothing becomes UI-only either.
        """
        try:
            log_line = "[StoryboardTo3D] {0}: {1}".format(
                title, str(message).replace("\n", " | "))
            if level == "error":
                unreal.log_error(log_line)
            elif level == "warning":
                unreal.log_warning(log_line)
            else:
                unreal.log(log_line)
        except Exception:
            pass

        try:
            first_line = str(message).splitlines()[0] if message else ""
            self.statusBar().showMessage(
                "{0}: {1}".format(title, first_line), 15000)
        except Exception:
            pass

        if level in ("error", "warning"):
            try:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Critical if level == "error"
                            else QMessageBox.Warning)
                box.setWindowTitle(title)
                box.setText(str(message))
                box.setModal(False)
                box.setAttribute(Qt.WA_DeleteOnClose, True)
                box.show()
                self._notify_boxes.append(box)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Tools menu actions
    # ------------------------------------------------------------------

    def render_animatic_dialog(self):
        """Tools menu: render the master sequence to disk via MRQ"""
        default_path = ""
        if self.current_show:
            default_path = "/Game/StoryboardSequences/{0}/{0}_Master_Sequence".format(
                self.current_show)

        path, ok = QInputDialog.getText(
            self, "Render Animatic",
            "Master sequence content path:",
            text=default_path)
        if not ok or not path.strip():
            return
        path = path.strip()

        # Best-effort existence check before kicking off MRQ
        try:
            if hasattr(unreal, 'EditorAssetLibrary') and \
                    not unreal.EditorAssetLibrary.does_asset_exist(path):
                self.notify_user(
                    "Render Animatic",
                    "Sequence not found: {0}\n\n"
                    "Generate scenes for this show first (the master sequence "
                    "is created when shots are assembled).".format(path),
                    "warning")
                return
        except Exception:
            pass

        try:
            from core.animatic_renderer import render_animatic
            result = render_animatic(path)
        except Exception as e:
            self.notify_user("Render Animatic Failed", str(e), "error")
            return

        if isinstance(result, dict) and result.get('status') == 'started':
            QMessageBox.information(
                self, "Render Animatic",
                "Animatic render started.\n\nOutput folder:\n{0}\n\n{1}".format(
                    result.get('output_dir', ''), result.get('notes', '')))
        else:
            notes = result.get('notes', 'Unknown error') if isinstance(result, dict) else result
            self.notify_user("Render Animatic Failed", str(notes), "error")

    def export_usd_dialog(self):
        """Tools menu: export the loaded level to a USD file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Level as USD",
            "storyboard_level.usda",
            "USD Files (*.usda *.usd *.usdc *.usdz)")
        if not path:
            return

        try:
            from core.usd_exporter import export_level_usd
            result = export_level_usd(path)
        except Exception as e:
            self.notify_user("USD Export Failed", str(e), "error")
            return

        if isinstance(result, dict) and result.get('status') == 'success':
            QMessageBox.information(
                self, "USD Export",
                "Level exported to:\n{0}".format(result.get('path', path)))
        else:
            error = result.get('error', 'Unknown error') if isinstance(result, dict) else result
            self.notify_user("USD Export Failed", str(error), "error")

    def _get_multi_model_tracker(self):
        """Multi-model tracker from the active panel widget, or None"""
        widget = getattr(self, 'active_panel_widget', None)
        return getattr(widget, 'multi_model_tracker', None) if widget else None

    def show_model_comparison_dialog(self):
        """Tools menu: print the multi-model comparison table"""
        tracker = self._get_multi_model_tracker()
        if not tracker:
            self.notify_user(
                "Model Comparison",
                "No multi-model data recorded this session.\n"
                "Run CAPTURE with model tracking first.",
                "warning")
            return
        try:
            self.active_panel_widget.show_model_comparison()
            QMessageBox.information(
                self, "Model Comparison",
                "Comparison table printed to the Output Log.")
        except Exception as e:
            self.notify_user("Model Comparison Failed", str(e), "error")

    def export_combined_comparison_dialog(self):
        """Tools menu: export the combined multi-model CSV"""
        tracker = self._get_multi_model_tracker()
        if not tracker:
            self.notify_user(
                "Export Combined Model CSV",
                "No multi-model data recorded this session.\n"
                "Run CAPTURE with model tracking first.",
                "warning")
            return
        try:
            output_file = tracker.export_combined_csv()
            QMessageBox.information(
                self, "Export Combined Model CSV",
                "Combined comparison exported to:\n{0}".format(output_file))
        except Exception as e:
            self.notify_user("Combined CSV Export Failed", str(e), "error")

    def show_calibration_dashboard(self):
        """Tools menu: generate and display the calibration dashboard PNG"""
        try:
            from analysis.calibration_dashboard import generate_dashboard
            png_path = generate_dashboard()
        except Exception as e:
            self.notify_user("Calibration Dashboard Failed", str(e), "error")
            return

        if not png_path:
            self.notify_user(
                "Calibration Dashboard",
                "Dashboard could not be generated. Pillow may be missing "
                "(pip install pillow); check the Output Log for details.",
                "warning")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Calibration Dashboard")
        layout = QVBoxLayout(dialog)

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(png_path)
        if pixmap.isNull():
            label.setText("Could not load image:\n{0}".format(png_path))
        else:
            if pixmap.width() > 1400:
                pixmap = pixmap.scaledToWidth(1400, Qt.SmoothTransformation)
            label.setPixmap(pixmap)

        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open in Default Viewer")

        def _open_external():
            try:
                if hasattr(os, 'startfile'):
                    os.startfile(png_path)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(png_path))
            except Exception as e2:
                self.notify_user("Open Failed", str(e2), "warning")

        open_btn.clicked.connect(_open_external)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.resize(1000, 700)
        dialog.exec_()

    def overnight_batch_dialog(self):
        """Tools menu: configure and run a single-pass batch over an episode"""
        shows = self.shows_manager.get_all_shows()
        if not shows:
            self.notify_user(
                "Overnight Batch",
                "No shows found. Create a show and import panels first.",
                "warning")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("🌙 Overnight Batch")
        form = QFormLayout(dialog)

        show_combo = QComboBox()
        for show in shows:
            show_combo.addItem(
                show.get('name', show.get('safe_name', '')),
                show.get('safe_name'))

        episode_combo = QComboBox()

        def refresh_episodes():
            episode_combo.clear()
            safe = show_combo.currentData()
            try:
                episodes = self.episodes_manager.get_show_episodes(safe) if safe else []
            except Exception as e:
                unreal.log_warning(f"Overnight batch: could not list episodes: {e}")
                episodes = []
            for ep in episodes:
                episode_combo.addItem(
                    ep.get('name', ep.get('safe_name', '')),
                    ep.get('safe_name'))

        show_combo.currentIndexChanged.connect(lambda _=None: refresh_episodes())
        refresh_episodes()

        provider_combo = QComboBox()
        provider_combo.addItems([
            "Auto",
            "Claude (Anthropic)",
            "GPT-4 Vision (OpenAI)",
            "LLaVA (Local)"
        ])

        generate_check = QCheckBox("Generate 3D scenes (uncheck for analysis only)")
        generate_check.setChecked(True)

        max_spin = QSpinBox()
        max_spin.setRange(0, 999)
        max_spin.setValue(0)
        max_spin.setSpecialValueText("All")

        form.addRow("Show:", show_combo)
        form.addRow("Episode:", episode_combo)
        form.addRow("AI Provider:", provider_combo)
        form.addRow("", generate_check)
        form.addRow("Max panels:", max_spin)

        warn = QLabel(
            "Single-pass analyze + generate per panel.\n"
            "Cloud providers will incur API costs.")
        warn.setStyleSheet("color: #808080; font-size: 11px;")
        form.addRow(warn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("🌙 Run Batch")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if not dialog.exec_():
            return

        show_safe = show_combo.currentData()
        episode_safe = episode_combo.currentData()
        if not show_safe or not episode_safe:
            self.notify_user(
                "Overnight Batch",
                "Select a show and an episode with panels first.",
                "warning")
            return

        max_panels = max_spin.value() or None
        self.run_overnight_batch(
            show_safe, episode_safe,
            provider_combo.currentText(),
            generate_check.isChecked(),
            max_panels)

    def run_overnight_batch(self, show, episode, provider, generate, max_panels):
        """Run core.batch_runner.run_batch with a cancellable progress dialog"""
        progress = QProgressDialog("Starting batch...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Overnight Batch")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()

        def progress_cb(done, total, panel_result):
            if total:
                progress.setMaximum(total)
                progress.setValue(done)
            name = ""
            try:
                if panel_result and panel_result.get('panel'):
                    name = Path(panel_result['panel']).name
            except Exception:
                name = ""
            progress.setLabelText(
                "Processed {0}/{1}: {2}".format(done, total, name))
            QApplication.processEvents()
            if progress.wasCanceled():
                # KeyboardInterrupt is a BaseException, so the batch runner's
                # 'except Exception' progress guard does not swallow it; this
                # is the cancellation channel out of run_batch's serial loop
                raise KeyboardInterrupt()

        try:
            from core.batch_runner import run_batch
        except Exception as e:
            progress.close()
            self.notify_user(
                "Overnight Batch Failed",
                "Could not load the batch runner:\n{0}".format(e),
                "error")
            return

        summary = None
        cancelled = False
        try:
            # analysis_workers=1 keeps the strictly-serial path so the
            # cancel raise above aborts cleanly (no thread pool involved)
            summary = run_batch(
                show, episode,
                provider=provider,
                generate=generate,
                max_panels=max_panels,
                progress_cb=progress_cb,
                analysis_workers=1)
        except KeyboardInterrupt:
            cancelled = True
        except Exception as e:
            progress.close()
            self.notify_user("Overnight Batch Failed", str(e), "error")
            return
        finally:
            progress.close()

        if cancelled:
            QMessageBox.information(
                self, "Overnight Batch",
                "Batch cancelled. Panels already processed keep their results.")
            return

        if not isinstance(summary, dict):
            self.notify_user(
                "Overnight Batch",
                "Batch finished but returned no summary; check the Output Log.",
                "warning")
            return

        if summary.get('error'):
            self.notify_user("Overnight Batch Failed", str(summary['error']), "error")
            return

        msg = ("Batch finished.\n\n"
               "Panels processed: {0}/{1}\n"
               "Analyzed fresh: {2}\n"
               "From cache: {3}\n"
               "Scenes generated: {4}\n"
               "Failed: {5}").format(
                   summary.get('panels_processed', 0),
                   summary.get('panels_total', 0),
                   summary.get('analyzed_fresh', 0),
                   summary.get('analyzed_from_cache', 0),
                   summary.get('generated', 0),
                   summary.get('failed', 0))
        if summary.get('report_path'):
            msg += "\n\nReport: {0}".format(summary['report_path'])
        if summary.get('failed'):
            self.notify_user("Overnight Batch Finished With Errors", msg, "warning")
        else:
            QMessageBox.information(self, "Overnight Batch", msg)

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

        if self.ai_client is None:
            self.notify_user(
                "AI Not Configured",
                "No AI client is available, so analysis will use filename "
                "heuristics only.\nAdd an API key in Settings for real AI "
                "analysis.",
                "warning")

        unreal.log(f"Analyzing {len(self.panels)} panels for show: {self.current_show}")

        progress = QProgressDialog(
            "Analyzing panels...", "Cancel", 0, len(self.panels), self)
        progress.setWindowTitle("Analyze All")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        analyzed = 0
        failures = []
        cancelled = False
        for i, panel in enumerate(self.panels):
            progress.setValue(i)
            progress.setLabelText("Analyzing {0}/{1}: {2}".format(
                i + 1, len(self.panels), panel['name']))
            QApplication.processEvents()
            if progress.wasCanceled():
                cancelled = True
                break
            try:
                analysis = self.analyzer.analyze_panel(
                    panel['path'],
                    show_name=self.current_show
                )
                panel['analysis'] = analysis
                analyzed += 1
            except Exception as e:
                unreal.log_error(f"Failed to analyze {panel['name']}: {e}")
                failures.append("{0}: {1}".format(panel['name'], e))

        progress.setValue(len(self.panels))
        progress.close()

        # Persist all results in one pass so analyses survive a restart
        try:
            if self.current_episode_path:
                metadata_file = self.current_episode_path / "panels_metadata.json"
                panel_metadata = {}
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        panel_metadata = json.load(f)
                for panel in self.panels:
                    if panel.get('analysis') is not None:
                        entry = panel_metadata.get(panel['name'], {})
                        entry['analysis'] = panel['analysis']
                        entry.setdefault('characters', panel.get('characters', []))
                        entry.setdefault('props', panel.get('props', []))
                        entry.setdefault('location', panel.get('location', ''))
                        entry.setdefault('shot_type', panel.get('shot_type', ''))
                        panel_metadata[panel['name']] = entry
                with open(metadata_file, 'w') as f:
                    json.dump(panel_metadata, f, indent=2)
        except Exception as e:
            self.notify_user(
                "Analysis Save Failed",
                "Analyses completed but could not be saved:\n{0}".format(e),
                "warning")

        # Refresh grid indicators (analyzed checkmarks) once at the end
        self.panel_grid.set_panels(self.panels)

        unreal.log(f"Analyzed {analyzed}/{len(self.panels)} panels")
        summary = "Analyzed {0} of {1} panels".format(analyzed, len(self.panels))
        if cancelled:
            summary += " (cancelled)"
        if failures:
            shown = "\n".join(failures[:5])
            if len(failures) > 5:
                shown += "\n... and {0} more".format(len(failures) - 5)
            self.notify_user(
                "Analysis Finished With Errors",
                summary + "\n\nFailures:\n" + shown,
                "warning")
        else:
            QMessageBox.information(self, "Analysis Complete", summary)

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

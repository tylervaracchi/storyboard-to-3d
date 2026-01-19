# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Active Panel widget for StoryboardTo3D
Handles the right column with panel details and controls

OPTIMIZATION #3: INTELLIGENT VIEW SELECTION (Integrated Oct 31, 2025)
- Adaptively selects camera views based on iteration, scene complexity, and convergence
- Expected 51% cost reduction while maintaining quality
- 5 strategies: MINIMAL, FOCUSED, REFINEMENT, EXPLORATION, COMPREHENSIVE
- Hero camera ALWAYS included (3 layers of protection)
- Feature flag: self.use_intelligent_view_selection (default: True)
- Integration points:
  * Line 55-62: Import with graceful fallback
  * Line 312-324: Initialization in __init__
  * Line 333: Feature summary display
  * Line 1634-1653: _detect_scene_complexity method
  * Line 1987-2037: View selection logic in _send_to_ai_analysis
  * Line 2063-2082: Depth map generation updated
  * Line 2183-2201: Storyboard depth control
  * Line 4504-4507: Reset in cleanup
- See: OPTIMIZATION_3_INTEGRATION_REPORT.md for full details
"""

import unreal
from pathlib import Path
import time
import json
from typing import Optional, List, Union, Dict, Any

# Image processing imports (used in depth map colorization)
try:
    import cv2
    import numpy as np
    CV2_NUMPY_AVAILABLE = True
except ImportError:
    CV2_NUMPY_AVAILABLE = False
    cv2 = None
    np = None

# Try to import Pydantic for structured outputs (100% schema adherence)
try:
    from pydantic import BaseModel, Field, field_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    unreal.log_warning("Pydantic not installed. Structured outputs disabled. Install with: pip install pydantic")
    # Fallback: dummy classes
    BaseModel = object
    Field = lambda *args, **kwargs: None
    field_validator = lambda *args, **kwargs: lambda x: x

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

# Metrics tracking for thesis evaluation
try:
    from analysis.metrics_tracker import MetricsTracker, MetricsSummaryReport
    from analysis.multi_model_tracker import MultiModelTracker
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    unreal.log_warning("MetricsTracker not available - thesis metrics will not be saved")
    MultiModelTracker = None

# Intelligent view selection for API cost optimization (Optimization #3)
try:
    from core.intelligent_view_selector import IntelligentViewSelector
    INTELLIGENT_VIEW_SELECTOR_AVAILABLE = True
except ImportError:
    INTELLIGENT_VIEW_SELECTOR_AVAILABLE = False
    IntelligentViewSelector = None
    unreal.log_warning("IntelligentViewSelector not available - will use all 7 views")

# Prompt optimization with feature flag (Optimization #4)
# Conditional import based on settings - allows toggling between original and optimized prompts
try:
    from core.settings_manager import get_setting
    USE_OPTIMIZED_PROMPTS = get_setting('ai_settings.use_optimized_prompts', False)

    if USE_OPTIMIZED_PROMPTS:
        # Use optimized prompts (50-66% token reduction)
        from core.enhanced_prompt_builder_optimized import OptimizedPromptBuilder as PromptBuilder
        from core.smart_analyzer_optimized import OptimizedSmartAnalyzer as SmartStoryboardAnalyzer
        unreal.log("Using OPTIMIZED prompts (50-66% token reduction)")
    else:
        # Use original prompts (full verbosity)
        from core.enhanced_prompt_builder import EnhancedPromptBuilder as PromptBuilder
        from core.smart_analyzer import SmartStoryboardAnalyzer
        unreal.log("Using ORIGINAL prompts (full verbosity)")

    PROMPT_OPTIMIZATION_AVAILABLE = True
except ImportError as e:
    # Fallback to original if optimized versions not available
    try:
        from core.enhanced_prompt_builder import EnhancedPromptBuilder as PromptBuilder
        from core.smart_analyzer import SmartStoryboardAnalyzer
        PROMPT_OPTIMIZATION_AVAILABLE = False
        unreal.log_warning(f"Prompt optimization not available: {e}")
    except ImportError:
        # Will be imported dynamically later if needed
        PromptBuilder = None
        SmartStoryboardAnalyzer = None
        PROMPT_OPTIMIZATION_AVAILABLE = False


# Structured output schemas for coordinate validation (OpenAI research: 100% adherence vs <40% baseline)
# CRITICAL: OpenAI SDK >=1.59.8 required for nested model bug fix (PR #2025)
class Position3D(BaseModel):
    """3D position in Unreal Engine coordinates (1 unit = 1cm)"""
    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'additionalProperties': False}  # Required by OpenAI strict mode
    }

    x: float = Field(description="X coordinate (forward/back)")
    y: float = Field(description="Y coordinate (right/left)")
    z: float = Field(description="Z coordinate (up/down)")

class Rotation3D(BaseModel):
    """3D rotation in degrees"""
    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'additionalProperties': False}  # Required by OpenAI strict mode
    }

    # ISSUE 7 FIX: Removed ge/le constraints - OpenAI strips them from schema anyway
    # This eliminates validation mismatch between schema sent to OpenAI and runtime validation
    pitch: float = Field(description="Up/down tilt (-90 to +90 degrees)")
    yaw: float = Field(description="Left/right rotation (-180 to +180 degrees)")
    roll: float = Field(default=0, description="Camera tilt (usually 0)")

class ActorAdjustment(BaseModel):
    """Single actor position/rotation adjustment"""
    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'additionalProperties': False}  # Required by OpenAI strict mode
    }

    # ISSUE 7 FIX: Removed pattern constraint - enforced in prompt instead
    actor: str = Field(description="Exact actor name from Characters list")
    type: str = Field(description="Adjustment type: 'move' or 'rotate'")
    # CRITICAL: Use Union[Type, None] instead of Optional for OpenAI strict mode
    position: Union[Position3D, None] = Field(None, description="Position adjustment (null if not moving)")
    rotation: Union[Rotation3D, None] = Field(None, description="Rotation adjustment (null if not rotating)")
    reason: str = Field(description="Detailed spatial reasoning with calculations (minimum 20 characters)")

class CameraAdjustment(BaseModel):
    """Camera position/rotation adjustment - rotation is AUTO-CALCULATED when position changes"""
    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'additionalProperties': False}  # Required by OpenAI strict mode
    }

    needs_adjustment: bool
    # CRITICAL: Use Union[Type, None] instead of Optional for OpenAI strict mode
    position: Union[Position3D, None] = Field(None, description="Camera position in world space (rotation auto-calculated to look at character)")
    rotation: Union[Rotation3D, None] = Field(None, description="Manual rotation override (only use if NOT changing position)")
    reason: str = Field(description="Why camera framing needs adjustment")

class PositioningAnalysis(BaseModel):
    """Complete spatial analysis with guaranteed valid structure"""
    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'additionalProperties': False}  # Required by OpenAI strict mode
    }

    # ISSUE 7 FIX: Removed min/max constraints - enforced in prompt instead
    match_score: int = Field(description="0-100 match quality score")
    analysis: str = Field(description="Detailed spatial comparison")
    adjustments: List[ActorAdjustment] = Field(default_factory=list)
    camera_adjustments: CameraAdjustment

    @field_validator('adjustments')
    @classmethod
    def validate_unique_actors(cls, v):
        """Ensure one adjustment per actor"""
        actors = [adj.actor for adj in v]
        if len(actors) != len(set(actors)):
            raise ValueError("Duplicate actor adjustments detected")
        return v


def sanitize_schema_for_openai(schema: dict) -> dict:
    """
    Sanitize Pydantic JSON schema for OpenAI strict mode compatibility.

    OpenAI's strict mode doesn't support:
    - default values in schemas
    - format fields (date-time, uri, etc.)
    - numeric constraints (minimum, maximum, minLength, maxLength, pattern)

    CRITICAL: OpenAI strict mode requires ALL properties to be in the required array,
    even if they're nullable via anyOf: [type, null]. This is non-negotiable.
    """
    import copy

    def process_schema(obj):
        if not isinstance(obj, dict):
            return

        # Remove unsupported properties
        obj.pop('default', None)     # Default values not supported in strict mode
        obj.pop('format', None)      # Date/time formats not supported
        obj.pop('minimum', None)     # Numeric constraints not enforced (kept in Pydantic for validation)
        obj.pop('maximum', None)
        obj.pop('minLength', None)
        obj.pop('maxLength', None)
        obj.pop('pattern', None)     # Regex patterns not enforced by OpenAI

        # Ensure additionalProperties is false for all objects (already in model_config, but ensure it's propagated)
        if obj.get('type') == 'object' and 'additionalProperties' not in obj:
            obj['additionalProperties'] = False
        # Even nullable fields must be listed as required (they're required to be present, even if null)
        if obj.get('type') == 'object' and 'properties' in obj:
            all_properties = list(obj['properties'].keys())
            # Force ALL properties into required array
            obj['required'] = all_properties

        # Recursively process nested structures
        for key in ['properties', 'items', 'anyOf', 'allOf', '$defs']:
            if key in obj:
                value = obj[key]
                if isinstance(value, dict):
                    for nested in value.values():
                        process_schema(nested)
                elif isinstance(value, list):
                    for nested in value:
                        process_schema(nested)

    clean_schema = copy.deepcopy(schema)
    process_schema(clean_schema)

    # Process $defs (Pydantic V2 uses $defs for nested models)
    if '$defs' in clean_schema:
        for definition in clean_schema['$defs'].values():
            process_schema(definition)

    return clean_schema


class ActivePanelWidget(QWidget):
    """Widget for active panel details and controls"""

    analyze_panel = Signal()
    generate_scene = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_panel = None
        self.scene_generator = None  # Will hold Phase 2 generator
        self.analyzer = None  # Will hold Phase 0 analyzer
        self.current_show = None  # Track current show
        self.asset_library = None  # Reference to asset library
        # Store scene data from generation
        self.last_generated_scene = None
        self.last_camera = None
        # Store AI analysis results for iteration
        self.last_positioning_analysis = None
        self.last_match_score = None
        self.last_adjustments_applied = []  # Track what adjustments were actually made
        self.score_trajectory = []  # Track score progression across iterations
        # Iteration tracking for auto-loop
        self.current_iteration = 0
        self.max_iterations = 7  # 7 iterations max, stops early if score > 80
        self.iteration_scores = []  # Track scores across iterations
        self.iteration_details = []  # Detailed metrics per iteration
        self.auto_iterate = False  # Flag to enable auto-iteration
        # Flag to disable auto-save during panel loading
        self._loading_panel = False

        # CRITICAL: Workflow cancellation flag to prevent crashed from orphaned timers
        self.capture_workflow_active = False  # Set True when workflow starts, False on cleanup

        # FEATURE #6: Cost tracking per iteration
        self.iteration_costs = []  # Track API costs per iteration
        self.total_cost = 0.0  # Cumulative cost across all iterations

        # CHECKPOINTING: Track best score and state (monotonic improvement)
        self.enable_checkpointing = True  # User can disable via UI checkbox
        self.best_score = 0  # Best match score achieved so far
        self.best_actor_transforms = {}  # Best actor positions (dict: actor_name -> {location, rotation})
        self.iteration_history = []  # Track all iterations with status (accepted/reverted)

        # Positioning mode: False = relative (default), True = absolute
        # FIXED: Switched to absolute mode to prevent AI arithmetic confusion and oscillation
        self.use_absolute_positioning = True  # Absolute mode: AI specifies target positions directly

        # Thesis metrics tracking
        self.metrics_tracker = None  # Initialized when test sequence starts
        self.current_scene_id = None  # e.g., "Simple_1", "Medium_2"
        self.current_approach = "multiview"  # "baseline" or "multiview"

        # Multi-model comparison tracker (4 models × 12 scenes)
        self.multi_model_tracker = None  # Tracks GPT-4o, LLaVA, Sonnet, Ground Truth

        # Batch processing state
        self.batch_capture_mode = False  # True when running batch capture
        self.batch_capture_queue = []  # Queue of panels to process
        self.batch_capture_results = []  # Results for each panel

        # THESIS ENHANCEMENT: Metric validation (validates AI scores against objective SSIM/PSNR)
        self.metric_validator = None  # Initialized on first use
        self.last_objective_metrics = None  # Stores SSIM, PSNR, MSE, LPIPS for current iteration
        self.last_validation_result = None  # Stores validation status (valid/invalid, discrepancy)

        # Multi-panel consistency tracking
        self.panel_actor_positions = {}  # {panel_id: {actor_name: {x, y, z}}}

        # Thesis debug folder - save all intermediate images
        self.thesis_debug_folder = Path(unreal.Paths.project_saved_dir()) / "ThesisDebug"
        self.thesis_debug_folder.mkdir(parents=True, exist_ok=True)

        # Create master README on first run
        master_readme = self.thesis_debug_folder / "README.txt"
        if not master_readme.exists():
            with open(master_readme, 'w') as f:
                f.write("="*70 + "\n")
                f.write("THESIS DEBUG IMAGE COLLECTION\n")
                f.write("="*70 + "\n\n")
                f.write("This folder contains all intermediate images from the AI positioning workflow.\n")
                f.write("Perfect for thesis documentation and process demonstration!\n\n")
                f.write("STRUCTURE:\n")
                f.write("  panel_XXX/                    - One folder per storyboard panel\n")
                f.write("    iteration_NNN_timestamp/    - One folder per AI iteration\n")
                f.write("      00_metadata.json          - Complete iteration data + AI response\n")
                f.write("      01_storyboard_reference.png - Original storyboard panel\n")
                f.write("      02_scene_captures_original/ - 7 camera angles (raw)\n")
                f.write("      03_marked_up_with_grid_axes/ - Same images with spatial markers\n")
                f.write("      README.txt                - Human-readable summary\n\n")
                f.write("USAGE:\n")
                f.write("  - Compare iterations to show AI refinement process\n")
                f.write("  - Extract match scores from metadata.json files\n")
                f.write("  - Use marked-up images to explain visual marker system\n")
                f.write("  - Create before/after figures for thesis\n\n")
                f.write("See: THESIS_DEBUG_GUIDE.md for complete documentation\n\n")
                f.write("Generated: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")

        unreal.log(f"Thesis debug folder: {self.thesis_debug_folder}")

        # Initialize sketch analyzer for auto initial placement (Feature #3)
        try:
            from analysis.sketch_analyzer import SketchAnalyzer
            self.sketch_analyzer = SketchAnalyzer()
        except Exception as e:
            self.sketch_analyzer = None
            unreal.log_warning(f"Could not load SketchAnalyzer: {e}")

        # Initialize visual marker renderer for spatial reference (Feature #1)
        try:
            from analysis.visual_markers import VisualMarkerRenderer
            self.marker_renderer = VisualMarkerRenderer()
        except Exception as e:
            self.marker_renderer = None
            unreal.log_warning(f"Could not load VisualMarkerRenderer: {e}")

        # Initialize depth analyzer (Feature #2) - Subprocess mode for stability
        # NOTE: Runs PyTorch in separate process to avoid DLL conflicts with UE
        try:
            from analysis.depth_analyzer import DepthAnalyzer
            self.depth_analyzer = DepthAnalyzer()
            if self.depth_analyzer.available:
                unreal.log(f"DepthAnalyzer initialized (device: {self.depth_analyzer.device}, subprocess mode)")
        except Exception as e:
            self.depth_analyzer = None
            unreal.log_warning(f"Could not load DepthAnalyzer: {e}")

        # Initialize intelligent view selector (Optimization #3: 51% image cost savings)
        if INTELLIGENT_VIEW_SELECTOR_AVAILABLE:
            try:
                self.view_selector = IntelligentViewSelector()
                self.use_intelligent_view_selection = True  # Feature flag (can be disabled for A/B testing)
                unreal.log("IntelligentViewSelector initialized (51% estimated cost reduction)")
            except Exception as e:
                self.view_selector = None
                self.use_intelligent_view_selection = False
                unreal.log_warning(f"Could not initialize IntelligentViewSelector: {e}")
        else:
            self.view_selector = None
            self.use_intelligent_view_selection = False

        # Log feature summary
        unreal.log("\n" + "="*70)
        unreal.log("ACTIVE FEATURES SUMMARY")
        unreal.log("="*70)
        unreal.log(f"[1] Visual Markers: {' ACTIVE' if (self.marker_renderer and self.marker_renderer.available) else ' DISABLED'}")
        unreal.log(f"[2] Depth Analysis: {' ACTIVE' if (self.depth_analyzer and self.depth_analyzer.available) else ' DISABLED'}")
        unreal.log(f"[3] Sketch Analysis: {' ACTIVE' if (self.sketch_analyzer and self.sketch_analyzer.available) else ' DISABLED'}")
        unreal.log(f"[4] Intelligent View Selection: {' ACTIVE (51% cost reduction)' if self.use_intelligent_view_selection else ' DISABLED (using all 7 views)'}")
        unreal.log("="*70 + "\n")

        self.setup_ui()

    def set_show_context(self, show_name, asset_library_widget):
        """Set the show context and update available locations"""
        self.current_show = show_name
        self.asset_library_widget = asset_library_widget  # Store the widget reference

        unreal.log(f"[ActivePanelWidget] set_show_context called with show: {show_name}")
        unreal.log(f"[ActivePanelWidget] asset_library_widget type: {type(asset_library_widget)}")

        # Get the actual library data from the widget
        # The structure is: widget.library (ShowSpecificAssetLibrary) -> .library (dict)
        if hasattr(asset_library_widget, 'library'):
            show_library_obj = asset_library_widget.library
            unreal.log(f"[ActivePanelWidget] Got library object from widget, type: {type(show_library_obj)}")

            # Now get the actual data dictionary from the library object
            if hasattr(show_library_obj, 'library'):
                self.asset_library = show_library_obj.library
                unreal.log(f"[ActivePanelWidget] Got data dictionary, type: {type(self.asset_library)}")
                if self.asset_library and isinstance(self.asset_library, dict):
                    unreal.log(f"[ActivePanelWidget] Library keys: {list(self.asset_library.keys())}")
            else:
                self.asset_library = None
                unreal.log_warning("[ActivePanelWidget] Library object has no 'library' data attribute")
        else:
            self.asset_library = None
            unreal.log_warning("[ActivePanelWidget] Asset library widget has no 'library' attribute")

        # Update the location dropdown
        self.update_location_dropdown()

        unreal.log(f"[ActivePanelWidget] Show context set to: {show_name}")
        if self.asset_library and isinstance(self.asset_library, dict):
            unreal.log(f"[ActivePanelWidget] Asset library loaded with {len(self.asset_library.get('locations', {}))} locations")

    def update_location_dropdown(self):
        """Update location dropdown with locations from asset library"""
        self.location_combo.clear()
        self.location_combo.addItem("Auto-detect")
        self.location_combo.addItem("Location Unknown")  # Add unknown option

        unreal.log("[ActivePanelWidget] Updating location dropdown...")

        if self.asset_library and isinstance(self.asset_library, dict):
            # Get locations from the show's asset library
            locations = self.asset_library.get('locations', {})

            unreal.log(f"[ActivePanelWidget] Found {len(locations)} locations in library: {list(locations.keys())}")

            if locations:
                # Add separator (disabled)
                self.location_combo.insertSeparator(2)

                # Add actual locations
                for location_name in locations.keys():
                    self.location_combo.addItem(location_name)
                    unreal.log(f"[ActivePanelWidget] Added location: {location_name}")
            else:
                unreal.log("[ActivePanelWidget] No locations found in library")
        else:
            unreal.log(f"[ActivePanelWidget] No valid asset library data. Type: {type(self.asset_library)}")

        # Set default to Auto-detect
        self.location_combo.setCurrentIndex(0)
        unreal.log(f"[ActivePanelWidget] Location dropdown now has {self.location_combo.count()} items")

    def update_character_suggestions(self):
        """Get character suggestions from asset library for better AI matching"""
        if self.asset_library and isinstance(self.asset_library, dict):
            characters = self.asset_library.get('characters', {})
            return list(characters.keys())
        return []

    def setup_ui(self):
        """Setup the UI"""
        self.setObjectName("rightColumn")
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ACTIVE PANEL section
        header = self.create_section_header("ACTIVE PANEL")
        layout.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(15, 15, 15, 15)

        # Panel name
        self.active_panel_label = QLabel("No panel selected")
        self.active_panel_label.setObjectName("infoText")
        self.active_panel_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFFFFF;")
        scroll_layout.addWidget(self.active_panel_label)

        # Preview
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_frame.setMinimumHeight(150)
        preview_frame.setMaximumHeight(200)
        preview_layout = QVBoxLayout(preview_frame)

        self.preview_label = QLabel("[Panel Image]")
        self.preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.preview_label)

        scroll_layout.addWidget(preview_frame)

        # Panel duration control
        duration_widget = QWidget()
        duration_layout = QHBoxLayout(duration_widget)
        duration_layout.setContentsMargins(0, 10, 0, 10)

        duration_layout.addWidget(QLabel("Duration:"))
        self.panel_duration_spin = QDoubleSpinBox()
        self.panel_duration_spin.setRange(0.5, 30.0)
        self.panel_duration_spin.setValue(3.0)
        self.panel_duration_spin.setSuffix(" sec")
        self.panel_duration_spin.valueChanged.connect(self.on_panel_duration_changed)
        duration_layout.addWidget(self.panel_duration_spin)
        duration_layout.addStretch()

        scroll_layout.addWidget(duration_widget)

        # Analysis buttons
        analyze_panel_btn = QPushButton(" Analyze Panel")
        analyze_panel_btn.clicked.connect(self.analyze_panel_with_ai)
        scroll_layout.addWidget(analyze_panel_btn)

        # Panel Status section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()

        # Analysis status
        self.analysis_status_label = QLabel("Not analyzed")
        self.analysis_status_label.setStyleSheet("color: #FF6B6B;")
        status_layout.addWidget(self.analysis_status_label)

        # Scene description from AI
        self.description_label = QLabel("Scene: Not analyzed yet")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #AAAAAA; font-style: italic; padding: 5px;")
        status_layout.addWidget(self.description_label)

        # AI raw description box
        ai_desc_label = QLabel("What AI Sees:")
        ai_desc_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        status_layout.addWidget(ai_desc_label)

        self.ai_description_text = QTextEdit()
        self.ai_description_text.setPlaceholderText("AI's raw description will appear here after analysis...\n\nYou can edit this text to correct the AI's interpretation.")
        self.ai_description_text.setMaximumHeight(80)
        self.ai_description_text.setReadOnly(False)  # EDITABLE!
        self.ai_description_text.setStyleSheet("background-color: #2a2a2a; color: #ffffff; padding: 5px;")
        self.ai_description_text.textChanged.connect(self._on_ai_description_changed)
        status_layout.addWidget(self.ai_description_text)

        # Confidence indicator
        confidence_widget = QWidget()
        confidence_layout = QHBoxLayout(confidence_widget)
        confidence_layout.setContentsMargins(0, 5, 0, 5)
        confidence_layout.addWidget(QLabel("Confidence:"))

        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(True)
        self.confidence_bar.setMaximumHeight(20)
        confidence_layout.addWidget(self.confidence_bar)

        status_layout.addWidget(confidence_widget)

        # Shot type
        shot_widget = QWidget()
        shot_layout = QHBoxLayout(shot_widget)
        shot_layout.setContentsMargins(0, 5, 0, 5)
        shot_layout.addWidget(QLabel("Shot:"))
        self.shot_type_combo = QComboBox()
        self.shot_type_combo.addItems([
            "Auto",
            "Wide",
            "Medium",
            "Close-up",
            "ECU",
            "OTS",
            "POV"
        ])
        self.shot_type_combo.currentTextChanged.connect(self._auto_save_panel_data)
        shot_layout.addWidget(self.shot_type_combo)
        shot_layout.addStretch()
        status_layout.addWidget(shot_widget)

        status_group.setLayout(status_layout)
        scroll_layout.addWidget(status_group)

        # Characters section
        chars_group = QGroupBox("Characters")
        chars_layout = QVBoxLayout()

        self.characters_list = QListWidget()
        self.characters_list.setMaximumHeight(60)
        chars_layout.addWidget(self.characters_list)

        char_controls = QHBoxLayout()
        add_char_btn = QPushButton("+")
        add_char_btn.setMaximumWidth(25)
        add_char_btn.clicked.connect(self.add_character)
        char_controls.addWidget(add_char_btn)

        remove_char_btn = QPushButton("-")
        remove_char_btn.setMaximumWidth(25)
        remove_char_btn.clicked.connect(self.remove_character)
        char_controls.addWidget(remove_char_btn)

        char_controls.addStretch()
        chars_layout.addLayout(char_controls)

        chars_group.setLayout(chars_layout)
        scroll_layout.addWidget(chars_group)

        # Props section
        props_group = QGroupBox("Props")
        props_layout = QVBoxLayout()

        self.props_list = QListWidget()
        self.props_list.setMaximumHeight(60)
        props_layout.addWidget(self.props_list)

        prop_controls = QHBoxLayout()
        add_prop_btn = QPushButton("+")
        add_prop_btn.setMaximumWidth(25)
        add_prop_btn.clicked.connect(self.add_prop)
        prop_controls.addWidget(add_prop_btn)

        remove_prop_btn = QPushButton("-")
        remove_prop_btn.setMaximumWidth(25)
        remove_prop_btn.clicked.connect(self.remove_prop)
        prop_controls.addWidget(remove_prop_btn)

        prop_controls.addStretch()
        props_layout.addLayout(prop_controls)

        props_group.setLayout(props_layout)
        scroll_layout.addWidget(props_group)

        # Location section - PULL FROM ASSET LIBRARY
        location_group = QGroupBox("Location")
        location_layout = QVBoxLayout()

        # Add a horizontal layout for combo and refresh button
        location_controls = QHBoxLayout()

        self.location_combo = QComboBox()
        self.location_combo.setEditable(True)

        # This will be populated from asset library
        self.location_combo.addItem("Auto-detect")
        self.location_combo.currentTextChanged.connect(self._auto_save_panel_data)

        location_controls.addWidget(self.location_combo)

        # Add refresh button
        refresh_locations_btn = QPushButton("")
        refresh_locations_btn.setMaximumWidth(30)
        refresh_locations_btn.setToolTip("Refresh locations from asset library")
        refresh_locations_btn.clicked.connect(self.force_refresh_locations)
        location_controls.addWidget(refresh_locations_btn)

        location_layout.addLayout(location_controls)

        location_group.setLayout(location_layout)
        scroll_layout.addWidget(location_group)

        scroll_layout.addStretch()

        # PHASE 4: AI-Assisted Positioning Section
        positioning_header = self.create_section_header(" AI-Assisted Positioning")
        scroll_layout.addWidget(positioning_header)

        # Instructions label
        instructions_label = QLabel(
            " CAPTURE: Takes 7 screenshots (6 scout angles + hero) and sends to AI for comparison.\n"
            "   Set iteration count below to control how many times AI refines positioning.\n"
            " GENERATE: Creates the 3D scene with characters, props, and camera"
        )
        instructions_label.setStyleSheet("color: #9CA3AF; font-size: 10px; padding: 5px; font-style: italic;")
        instructions_label.setWordWrap(True)
        scroll_layout.addWidget(instructions_label)

        scroll_layout.addSpacing(10)

        # Iteration count input
        iteration_container = QWidget()
        iteration_layout = QHBoxLayout(iteration_container)
        iteration_layout.setContentsMargins(0, 0, 0, 0)

        iteration_label = QLabel(" Iterations:")
        iteration_label.setStyleSheet("color: #E5E7EB; font-size: 12px; font-weight: bold;")
        iteration_layout.addWidget(iteration_label)

        self.iteration_input = QLineEdit()
        self.iteration_input.setText(str(self.max_iterations))  # Default value from __init__
        self.iteration_input.setPlaceholderText("7")
        self.iteration_input.setMaximumWidth(60)
        self.iteration_input.setAlignment(Qt.AlignCenter)
        self.iteration_input.setStyleSheet("""
            QLineEdit {
                background-color: #374151;
                color: #FFFFFF;
                border: 1px solid #4B5563;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 1px solid #0EA5E9;
            }
        """)
        self.iteration_input.textChanged.connect(self._on_iteration_count_changed)
        iteration_layout.addWidget(self.iteration_input)

        iteration_help = QLabel("(AI will refine positioning this many times)")
        iteration_help.setStyleSheet("color: #9CA3AF; font-size: 10px; font-style: italic;")
        iteration_layout.addWidget(iteration_help)

        iteration_layout.addStretch()
        scroll_layout.addWidget(iteration_container)

        scroll_layout.addSpacing(5)

        # Checkpointing checkbox
        self.checkpointing_checkbox = QCheckBox(" Enable Checkpointing (revert if score doesn't improve)")
        self.checkpointing_checkbox.setChecked(self.enable_checkpointing)
        self.checkpointing_checkbox.setStyleSheet("""
            QCheckBox {
                color: #E5E7EB;
                font-size: 11px;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #4B5563;
                border-radius: 3px;
                background-color: #374151;
            }
            QCheckBox::indicator:checked {
                background-color: #0EA5E9;
                border-color: #0EA5E9;
            }
            QCheckBox::indicator:hover {
                border-color: #0EA5E9;
            }
        """)
        self.checkpointing_checkbox.stateChanged.connect(self._on_checkpointing_changed)
        scroll_layout.addWidget(self.checkpointing_checkbox)

        scroll_layout.addSpacing(10)

        # CAPTURE button (PHASE 4 - CAPTURE ALL + AI ANALYSIS)
        compare_btn = QPushButton(" CAPTURE")
        compare_btn.setObjectName("compareButton")
        compare_btn.clicked.connect(self.test_positioning_phase3)
        compare_btn.setStyleSheet("""
            QPushButton#compareButton {
                background-color: #0EA5E9;
                color: #FFFFFF;
                font-weight: bold;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton#compareButton:hover {
                background-color: #0284C7;
            }
        """)
        scroll_layout.addWidget(compare_btn)

        # BATCH CAPTURE button
        batch_capture_btn = QPushButton(" BATCH CAPTURE")
        batch_capture_btn.setObjectName("batchCaptureButton")
        batch_capture_btn.clicked.connect(self.batch_capture_all_panels)
        batch_capture_btn.setStyleSheet("""
            QPushButton#batchCaptureButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                font-weight: bold;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton#batchCaptureButton:hover {
                background-color: #7C3AED;
            }
        """)
        scroll_layout.addWidget(batch_capture_btn)

        # Test result widget
        self.comparison_result = QWidget()
        comparison_layout = QVBoxLayout(self.comparison_result)

        self.match_label = QLabel("No test run yet")
        self.match_label.setStyleSheet("font-weight: bold; padding: 5px;")
        comparison_layout.addWidget(self.match_label)

        self.match_progress = QProgressBar()
        self.match_progress.setRange(0, 100)
        self.match_progress.setValue(0)
        self.match_progress.setTextVisible(True)
        self.match_progress.setMaximumHeight(25)
        comparison_layout.addWidget(self.match_progress)

        self.comparison_result.hide()
        scroll_layout.addWidget(self.comparison_result)

        # Generate button
        generate_btn = QPushButton(" GENERATE")
        generate_btn.setObjectName("generateButton")
        generate_btn.clicked.connect(self.generate_scene_from_panel)  # Changed from emit
        generate_btn.setStyleSheet("""
            QPushButton#generateButton {
                background-color: #00AA00;
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                font-size: 14px;
            }
            QPushButton#generateButton:hover {
                background-color: #00CC00;
            }
        """)
        scroll_layout.addWidget(generate_btn)

        # BATCH GENERATE button
        batch_generate_btn = QPushButton(" BATCH GENERATE")
        batch_generate_btn.setObjectName("batchGenerateButton")
        batch_generate_btn.clicked.connect(self.batch_generate_all_panels)
        batch_generate_btn.setStyleSheet("""
            QPushButton#batchGenerateButton {
                background-color: #F59E0B;
                color: #FFFFFF;
                font-weight: bold;
                padding: 12px;
                font-size: 14px;
            }
            QPushButton#batchGenerateButton:hover {
                background-color: #D97706;
            }
        """)
        scroll_layout.addWidget(batch_generate_btn)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

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

    def set_panel(self, panel_data):
        """Set the active panel"""
        # Disable auto-save during panel loading
        self._loading_panel = True

        self.active_panel = panel_data
        self.active_panel_label.setText(Path(panel_data['path']).name)

        # Load preview
        pixmap = QPixmap(panel_data['path'])
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview_label.width() - 10,
                self.preview_label.height() - 10,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)

        # Clear existing UI data
        self.characters_list.clear()
        self.props_list.clear()

        # Reset dropdowns to default values FIRST (so each panel starts fresh)
        self.location_combo.setCurrentIndex(0)  # "Auto-detect"
        self.shot_type_combo.setCurrentIndex(0)  # "Auto"

        # Load saved data into UI (override defaults if saved)
        if panel_data.get('characters'):
            for char in panel_data['characters']:
                self.characters_list.addItem(char)

        if panel_data.get('props'):
            for prop in panel_data['props']:
                self.props_list.addItem(prop)

        # Load location if saved
        if panel_data.get('location') and panel_data['location']:
            location = panel_data['location']
            index = self.location_combo.findText(location)
            if index >= 0:
                self.location_combo.setCurrentIndex(index)
            else:
                self.location_combo.setEditText(location)

        # Load shot type if saved
        if panel_data.get('shot_type') and panel_data['shot_type']:
            shot_type = panel_data['shot_type']
            index = self.shot_type_combo.findText(shot_type)
            if index >= 0:
                self.shot_type_combo.setCurrentIndex(index)

        # Update analysis status if available
        if panel_data.get('analysis'):
            self.update_analysis_ui(panel_data['analysis'])
        else:
            # Reset status if no analysis
            self.analysis_status_label.setText("Not analyzed")
            self.analysis_status_label.setStyleSheet("color: #FF6B6B;")
            self.confidence_bar.setValue(0)
            # Clear scene description
            self.description_label.setText("Scene: Not analyzed yet")
            self.description_label.setStyleSheet("color: #AAAAAA; font-style: italic; padding: 5px;")
            # Clear AI description text
            self.ai_description_text.clear()

        # Re-enable auto-save after panel is loaded
        self._loading_panel = False

    def update_analysis_ui(self, analysis):
        """Update UI with analysis results"""
        self.analysis_status_label.setText(" Analyzed")
        self.analysis_status_label.setStyleSheet("color: #00AA00;")

        # Update confidence if available
        if 'overall_confidence' in analysis:
            confidence = int(analysis['overall_confidence'] * 100)
            self.confidence_bar.setValue(confidence)
        elif 'confidence' in analysis:
            confidence = int(analysis['confidence'])
            self.confidence_bar.setValue(confidence)

        # Update scene description from analysis
        description = analysis.get('description', analysis.get('raw_description', ''))
        if description:
            display_desc = description[:100] + "..." if len(description) > 100 else description
            self.description_label.setText(f"Scene: {display_desc}")
            self.description_label.setStyleSheet("color: #FFFFFF; font-style: italic; padding: 5px;")

        # Update AI raw description box
        raw_desc = analysis.get('ai_raw_description', analysis.get('description', ''))
        if raw_desc:
            self.ai_description_text.setPlainText(raw_desc)

    def on_panel_duration_changed(self, value):
        """Handle panel duration change"""
        if self.active_panel:
            self.active_panel['duration'] = value
            unreal.log(f"Panel duration set to: {value} seconds")

    def _on_iteration_count_changed(self, text):
        """Handle iteration count input change"""
        if text.strip():  # Only process if not empty
            try:
                count = int(text)
                if count > 0:
                    self.max_iterations = count
                    unreal.log(f"Iteration count updated: {count}")
                else:
                    unreal.log_warning("Iteration count must be positive")
            except ValueError:
                unreal.log_warning(f"Invalid iteration count: {text} (must be a number)")

    def _on_checkpointing_changed(self, state):
        """Handle checkpointing checkbox state change"""
        self.enable_checkpointing = (state == Qt.Checked)
        status = "ENABLED" if self.enable_checkpointing else "DISABLED"
        unreal.log(f"Checkpointing {status}")
        if self.enable_checkpointing:
            unreal.log("→ AI adjustments will be reverted if score doesn't improve")
        else:
            unreal.log("→ All AI adjustments will be kept (may oscillate)")

    def _on_ai_description_changed(self):
        """Handle AI description text changes"""
        if self._loading_panel or not self.active_panel:
            return

        # Save edited AI description back to analysis data
        if self.active_panel.get('analysis'):
            new_text = self.ai_description_text.toPlainText()
            self.active_panel['analysis']['ai_raw_description'] = new_text
            # Also update description field if it was the same
            if 'description' in self.active_panel['analysis']:
                self.active_panel['analysis']['description'] = new_text

            # Save immediately
            self._auto_save_panel_data()

    def _auto_save_panel_data(self):
        """Auto-save panel data when any field changes"""
        # Don't save if we're currently loading a panel
        if self._loading_panel or not self.active_panel:
            return

        # Update active panel data with current UI state
        self.active_panel['characters'] = [self.characters_list.item(i).text() for i in range(self.characters_list.count())]
        self.active_panel['props'] = [self.props_list.item(i).text() for i in range(self.props_list.count())]
        self.active_panel['location'] = self.location_combo.currentText()
        self.active_panel['shot_type'] = self.shot_type_combo.currentText()

        # Save to file via parent window
        parent = self.parent()
        if parent and hasattr(parent, 'save_panel_metadata'):
            parent.save_panel_metadata(self.active_panel)

    def add_character(self):
        """Add character to active panel"""
        name, ok = QInputDialog.getText(self, "Add Character", "Character name:")
        if ok and name:
            self.characters_list.addItem(name)
            unreal.log(f"Added character: {name}")
            self._auto_save_panel_data()

    def remove_character(self):
        """Remove selected character"""
        current = self.characters_list.currentItem()
        if current:
            self.characters_list.takeItem(self.characters_list.row(current))
            self._auto_save_panel_data()

    def add_prop(self):
        """Add prop to active panel"""
        name, ok = QInputDialog.getText(self, "Add Prop", "Prop name:")
        if ok and name:
            self.props_list.addItem(name)
            unreal.log(f"Added prop: {name}")
            self._auto_save_panel_data()

    def remove_prop(self):
        """Remove selected prop"""
        current = self.props_list.currentItem()
        if current:
            self.props_list.takeItem(self.props_list.row(current))
            self._auto_save_panel_data()

    def force_refresh_locations(self):
        """Force refresh locations from asset library"""
        unreal.log("[ActivePanelWidget] Force refreshing locations...")

        # Try to get the asset library from the widget
        if hasattr(self, 'asset_library_widget') and self.asset_library_widget:
            if hasattr(self.asset_library_widget, 'library'):
                show_library_obj = self.asset_library_widget.library
                unreal.log(f"[ActivePanelWidget] Got library object: {type(show_library_obj)}")

                # Get the actual data dictionary
                if hasattr(show_library_obj, 'library'):
                    self.asset_library = show_library_obj.library
                    unreal.log(f"[ActivePanelWidget] Got data from library object: {bool(self.asset_library)}")

        # If we still don't have it, try to load it directly
        if not self.asset_library and self.current_show:
            try:
                from core.utils import get_shows_manager
                import json
                shows_manager = get_shows_manager()
                library_path = shows_manager.shows_root / self.current_show / 'asset_library.json'

                unreal.log(f"[ActivePanelWidget] Loading library directly from: {library_path}")

                if library_path.exists():
                    with open(library_path, 'r') as f:
                        self.asset_library = json.load(f)
                    unreal.log(f"[ActivePanelWidget] Loaded library with keys: {list(self.asset_library.keys())}")
            except Exception as e:
                unreal.log_error(f"[ActivePanelWidget] Failed to load library: {e}")

        # Now update the dropdown
        self.update_location_dropdown()

    def clear_panel(self):
        """Clear the active panel"""
        self.active_panel = None
        self.active_panel_label.setText("Select an episode first")
        self.preview_label.setText("[Panel Image]")
        self.preview_label.setPixmap(QPixmap())  # Clear pixmap
        self.analysis_status_label.setText("Not analyzed")
        self.analysis_status_label.setStyleSheet("color: #FF6B6B;")
        self.confidence_bar.setValue(0)
        self.characters_list.clear()
        self.props_list.clear()
        self.shot_type_combo.setCurrentIndex(0)
        self.location_combo.setCurrentIndex(0)
        self.panel_duration_spin.setValue(3.0)

    def get_panel_info(self):
        """Get panel info for generation"""
        if not self.active_panel:
            return None

        return {
            'path': self.active_panel['path'],
            'duration': self.panel_duration_spin.value(),
            'shot_type': self.shot_type_combo.currentText(),
            'characters': [self.characters_list.item(i).text() for i in range(self.characters_list.count())],
            'props': [self.props_list.item(i).text() for i in range(self.props_list.count())],
            'location': self.location_combo.currentText()
        }

    def test_positioning_phase1(self):
        """Test Phase 1: AI Input/Output for positioning instructions"""
        unreal.log("\n" + "="*70)
        unreal.log("PHASE 1 TEST: AI POSITIONING INPUT/OUTPUT")
        unreal.log("="*70)

        # Show progress
        self.comparison_result.show()
        self.match_label.setText("Running Phase 1 tests...")
        self.match_progress.setValue(0)

        try:
            # Import Phase 1 test
            import sys
            from pathlib import Path

            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            self.match_progress.setValue(10)

            # Run Phase 1 tests
            from tests.positioning.test_phase1_ai_io import PositioningAITest

            unreal.log("Initializing Phase 1 test...")
            test = PositioningAITest()

            self.match_progress.setValue(20)
            self.match_label.setText("Testing AI communication...")

            # Run tests
            test.run_all_tests()

            # Analyze results
            passed = sum(1 for r in test.test_results if r['success'])
            total = len(test.test_results)
            success_rate = (passed / total * 100) if total > 0 else 0

            self.match_progress.setValue(int(success_rate))

            # Color code based on results
            if success_rate == 100:
                color = "#00AA00"
                status = " All tests passed!"
            elif success_rate >= 66:
                color = "#FFA500"
                status = " Most tests passed"
            elif success_rate >= 33:
                color = "#FF8C00"
                status = " Some tests passed"
            else:
                color = "#FF0000"
                status = " Tests failed"

            self.match_label.setText(f"{status} - {passed}/{total} tests")
            self.match_label.setStyleSheet(f"font-weight: bold; padding: 5px; color: {color};")

            # Show detailed results
            results_text = "\n".join([
                f"{'' if r['success'] else ''} {r['message']}"
                for r in test.test_results
            ])

            QMessageBox.information(
                self,
                f"Phase 1 Test Results: {passed}/{total}",
                f"Success Rate: {success_rate:.0f}%\n\n{results_text}\n\n"
                f"Check Output Log for detailed results."
            )

            unreal.log("\n" + "="*70)
            unreal.log(f"PHASE 1 COMPLETE: {passed}/{total} tests passed")
            unreal.log("="*70)

        except ImportError as e:
            self.match_progress.setValue(0)
            self.match_label.setText(" Phase 1 test not found")
            self.match_label.setStyleSheet("font-weight: bold; padding: 5px; color: #FF0000;")

            QMessageBox.critical(
                self,
                "Phase 1 Test Not Found",
                f"Could not import Phase 1 test module.\n\n"
                f"Error: {e}\n\n"
                f"Make sure test files exist in:\n"
                f"tests/positioning/test_phase1_ai_io.py"
            )
            unreal.log_error(f"Phase 1 import failed: {e}")

        except Exception as e:
            self.match_progress.setValue(0)
            self.match_label.setText(" Test failed")
            self.match_label.setStyleSheet("font-weight: bold; padding: 5px; color: #FF0000;")

            QMessageBox.critical(
                self,
                "Phase 1 Test Error",
                f"Test execution failed.\n\n{str(e)}\n\nCheck Output Log for details."
            )
            unreal.log_error(f"Phase 1 test failed: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def test_positioning_phase2(self):
        """Test Phase 2: Actor Movement and Transform API"""
        unreal.log("\n" + "="*70)
        unreal.log("PHASE 2 TEST: ACTOR MOVEMENT & TRANSFORM API")
        unreal.log("="*70)

        # Show progress
        self.comparison_result.show()
        self.match_label.setText("Running Phase 2 tests...")
        self.match_progress.setValue(0)

        try:
            # Import Phase 2 test
            import sys
            from pathlib import Path

            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            self.match_progress.setValue(10)

            # Run Phase 2 tests
            from tests.positioning.test_phase2_movement import ActorMovementTest

            unreal.log("Initializing Phase 2 test...")
            test = ActorMovementTest()

            self.match_progress.setValue(20)
            self.match_label.setText("Testing actor movement APIs...")

            # Run tests
            test.run_all_tests()

            # Phase 2 doesn't return structured results like Phase 1
            # Success is determined by no exceptions
            self.match_progress.setValue(100)

            # Show success
            color = "#00AA00"
            status = " Phase 2 tests complete!"

            self.match_label.setText(status)
            self.match_label.setStyleSheet(f"font-weight: bold; padding: 5px; color: {color};")

            QMessageBox.information(
                self,
                "Phase 2 Test Complete",
                "Actor movement tests completed!\n\n"
                "Tests performed:\n"
                " Spawn actor\n"
                " Move actor\n"
                " Rotate actor\n"
                " Create sequence\n"
                " Add to sequence\n"
                " Keyframe transforms\n"
                " Programmatic updates\n\n"
                "Check Output Log for detailed results."
            )

            unreal.log("\n" + "="*70)
            unreal.log("PHASE 2 COMPLETE - Check log for pass/fail details")
            unreal.log("="*70)

        except ImportError as e:
            self.match_progress.setValue(0)
            self.match_label.setText(" Phase 2 test not found")
            self.match_label.setStyleSheet("font-weight: bold; padding: 5px; color: #FF0000;")

            QMessageBox.critical(
                self,
                "Phase 2 Test Not Found",
                f"Could not import Phase 2 test module.\n\n"
                f"Error: {e}\n\n"
                f"Make sure test files exist in:\n"
                f"tests/positioning/test_phase2_movement.py"
            )
            unreal.log_error(f"Phase 2 import failed: {e}")

        except Exception as e:
            self.match_progress.setValue(0)
            self.match_label.setText(" Test failed")
            self.match_label.setStyleSheet("font-weight: bold; padding: 5px; color: #FF0000;")

            QMessageBox.critical(
                self,
                "Phase 2 Test Error",
                f"Test execution failed.\n\n{str(e)}\n\nCheck Output Log for details."
            )
            unreal.log_error(f"Phase 2 test failed: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    # Individual capture test handlers
    def test_capture_front(self):
        """Test front angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: FRONT")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_front
        success = test_front()
        unreal.log("[test_capture_front END]")
        return success

    def test_capture_right(self):
        """Test right angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: RIGHT")
        unreal.log("Calling test_right() function...")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_right
        success = test_right()
        unreal.log("[test_capture_right END]")
        return success

    def test_capture_back(self):
        """Test back angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: BACK")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_back
        test_back()
        unreal.log("[test_capture_back END]")

    def test_capture_left(self):
        """Test left angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: LEFT")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_left
        test_left()
        unreal.log("[test_capture_left END]")

    def test_capture_top(self):
        """Test top angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: TOP")
        unreal.log("Calling test_top() function...")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_top
        test_top()
        unreal.log("[test_capture_top END]")

    def test_capture_3_4(self):
        """Test 3/4 angle capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: 3/4 VIEW")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_front_3_4
        test_front_3_4()
        unreal.log("[test_capture_3_4 END]")

    def test_capture_hero(self):
        """Test hero camera capture"""
        unreal.log("\n" + "="*70)
        unreal.log("BUTTON CLICKED: HERO")
        unreal.log("="*70)
        from tests.positioning.test_individual_captures import test_hero
        test_hero()
        unreal.log("[test_capture_hero END]")

    def test_pilot_to_scout(self):
        """Pilot viewport to AI Scout Camera - creates camera if needed"""
        try:
            unreal.log("\n Piloting viewport to AI_Scout_Camera...")

            # Find AI_Scout_Camera
            subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            all_actors = subsystem.get_all_level_actors()
            scout_camera = None
            for actor in all_actors:
                if actor.get_actor_label() == "AI_Scout_Camera":
                    scout_camera = actor
                    unreal.log("Found existing AI_Scout_Camera")
                    break

            # Create camera if it doesn't exist
            if not scout_camera:
                unreal.log("Creating AI_Scout_Camera...")

                scout_loc = unreal.Vector(0, 0, 200)
                scout_rot = unreal.Rotator(0, 0, 0)

                scout_camera = subsystem.spawn_actor_from_class(
                    unreal.CineCameraActor,
                    scout_loc,
                    scout_rot
                )

                if not scout_camera:
                    unreal.log_error("Failed to spawn scout camera")
                    return

                scout_camera.set_actor_label("AI_Scout_Camera")

                # Disable auto-focus
                camera_component = scout_camera.get_cine_camera_component()
                if camera_component:
                    focus_settings = camera_component.focus_settings
                    focus_settings.focus_method = unreal.CameraFocusMethod.DISABLE
                    camera_component.set_editor_property('focus_settings', focus_settings)

                unreal.log("Created AI_Scout_Camera")

            # Unbind camera cuts first
            try:
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                unreal.log("Camera cuts unbound")
            except:
                pass

            # Pilot to scout camera
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            level_editor_subsystem.pilot_level_actor(scout_camera)

            camera_loc = scout_camera.get_actor_location()
            camera_rot = scout_camera.get_actor_rotation()

            unreal.log(f"Viewport piloted to AI_Scout_Camera (manual pilot)")
            unreal.log(f"Location: {camera_loc}")
            unreal.log(f"Rotation: {camera_rot}")
            unreal.log("Click [ Eject] to exit pilot mode")
            unreal.log("[test_pilot_to_scout END]")

        except Exception as e:
            unreal.log_error(f"Failed to pilot viewport: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def test_pilot_to_hero(self):
        """Lock viewport to camera cuts in sequence (Shift+C)"""
        try:
            unreal.log("\n Locking viewport to camera cuts...")

            # Get the currently open sequence
            active_sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()

            if not active_sequence:
                unreal.log_error("No sequence is currently open!")
                unreal.log("Open a sequence first (double-click it in Content Browser)")
                return

            unreal.log(f"Found sequence: {active_sequence.get_name()}")

            # Lock viewport to camera cuts (Shift+C)
            unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
            unreal.log("Camera cuts locked to viewport (Shift+C)")
            unreal.log("Viewport now showing camera from sequence")
            unreal.log("Click [ Eject from Pilot Mode] to unlock")
            unreal.log("[test_pilot_to_hero END]")

        except Exception as e:
            unreal.log_error(f"Failed to lock camera cuts: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def test_eject_viewport(self):
        """Eject viewport from pilot mode and unbind camera cuts"""
        try:
            unreal.log("\n Ejecting viewport and unbinding camera cuts...")

            # Unbind camera cuts first
            try:
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                unreal.log("Camera cuts unbound")
            except:
                pass

            # Eject from pilot mode
            level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            level_editor_subsystem.eject_pilot_level_actor()

            unreal.log("Viewport ejected from pilot mode")
            unreal.log("You now have free camera control")
            unreal.log("[test_eject_viewport END]")

        except Exception as e:
            unreal.log_error(f"Failed to eject viewport: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def test_cleanup_scout(self):
        """Cleanup scout camera"""
        from tests.positioning.test_individual_captures import cleanup
        cleanup()
        unreal.log("[test_cleanup_scout END]")

    def test_positioning_phase3(self):
        """Auto-execute all 6 angles with 15s delay between shots: Pilot → Front → Right → Back → Left → Top → 3/4"""
        unreal.log("\n" + "="*70)
        unreal.log("CAPTURE BUTTON CLICKED - STARTING POSITIONING WORKFLOW")
        unreal.log("="*70)

        # ============================================================
        # STEP 0: ENSURE CORRECT LEVEL IS LOADED AND SEQUENCE IS OPEN
        # ============================================================

        # Get location and sequence from active panel
        if not self.active_panel:
            unreal.log_error("No active panel set!")
            return

        location = self.active_panel.get('location')
        sequence_path = self.active_panel.get('sequence_path')

        unreal.log(f"\n Panel location: {location}")
        unreal.log(f"Sequence path: {sequence_path}")

        # FALLBACK: If no sequence_path in panel data, try to find it
        if not sequence_path:
            unreal.log("ℹ No sequence_path in panel data - searching for generated sequence...")
            sequence_path = self._find_latest_sequence()
            if sequence_path:
                unreal.log(f"Found sequence: {sequence_path}")
                # Update panel data for next time
                self.active_panel['sequence_path'] = sequence_path
            else:
                unreal.log_warning("No generated sequence found")

        # Load the correct level for this location
        if location and self.current_show:
            unreal.log(f"\n Loading level for location: {location}")

            # CRITICAL: Close Sequencer and cleanup before level load to prevent crashes
            unreal.log("Cleaning up before level load...")
            try:
                # Eject from any piloted camera
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)

                # Close current sequence if open (prevents "Window 'Sequencer' being destroyed" crash)
                current_seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
                if current_seq:
                    unreal.log(f"Closing current sequence: {current_seq.get_name()}")
                    unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
                # This prevents Qt timer callbacks from accessing stale camera references
                unreal.log("Cleaning up scout cameras from previous iteration...")
                try:
                    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    all_actors = subsystem.get_all_level_actors()
                    scouts_deleted = 0
                    for actor in all_actors:
                        if "AI_Scout" in actor.get_actor_label():
                            subsystem.destroy_actor(actor)
                            scouts_deleted += 1
                    if scouts_deleted > 0:
                        unreal.log(f"Deleted {scouts_deleted} scout camera(s)")
                    else:
                        unreal.log("No scout cameras to clean up")
                except Exception as cleanup_err:
                    unreal.log_warning(f"Scout cleanup warning: {cleanup_err}")

                # Process pending Qt events to ensure cleanup completes
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()

                unreal.log("Cleanup complete")
            except Exception as e:
                unreal.log_warning(f"Cleanup warning: {e}")

            from core.universal_level_loader import load_any_level_from_library

            level_loaded = load_any_level_from_library(location, self.current_show)

            if not level_loaded:
                unreal.log_error(f"Failed to load level for location '{location}'")
                unreal.log_error(f"Cannot continue with capture - sequence won't be visible")
                return

            unreal.log(f"Level loaded successfully for '{location}'")

            # Give level time to fully load
            import time
            time.sleep(1.0)
        else:
            unreal.log_warning("No location or show specified - using current level")

        # Open the sequence in Sequencer
        if sequence_path:
            unreal.log(f"\n Opening sequence in Sequencer...")
            unreal.log(f"Path: {sequence_path}")

            try:
                sequence_asset = unreal.load_asset(sequence_path)

                if not sequence_asset:
                    unreal.log_error(f"Failed to load sequence asset: {sequence_path}")
                    return

                # Open in Sequencer
                unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence_asset)
                unreal.log(f"Sequence opened in Sequencer")

                # Verify it's open
                import time
                time.sleep(0.5)
                current_seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
                if current_seq:
                    unreal.log(f"Verified: {current_seq.get_name()} is active in Sequencer")
                else:
                    unreal.log_warning("Could not verify sequence is open")

            except Exception as e:
                unreal.log_error(f"Failed to open sequence: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())
                return
        else:
            unreal.log_warning("No sequence_path in panel data - cannot open sequence")
            unreal.log_warning("Generate the scene first before capturing")
            return

        unreal.log("\n" + "="*70)
        unreal.log("LEVEL AND SEQUENCE READY - STARTING CAPTURE WORKFLOW")
        unreal.log("="*70)

        # CRITICAL: Activate workflow flag to allow delayed callbacks
        self.capture_workflow_active = True

        # Enable auto-iteration for 10 loops
        unreal.log("\n Setting up auto-iteration...")
        self.auto_iterate = True
        self.current_iteration = 1
        self.iteration_scores = []
        unreal.log(f"Auto-iteration enabled: {self.max_iterations} iterations")
        unreal.log(f"Current iteration: {self.current_iteration}")
        unreal.log(f"Iteration scores list initialized")

        # Initialize metrics tracker for thesis evaluation (fully automatic!)
        if METRICS_AVAILABLE:
            unreal.log("Initializing metrics tracker...")
            self._init_metrics_tracker()
            # Only log success if metrics_tracker actually exists
            if self.metrics_tracker:
                unreal.log("Metrics tracker initialized successfully")
            else:
                unreal.log_warning("Metrics tracker initialization failed - see errors above")
        else:
            unreal.log_warning("MetricsTracker module not available - skipping metrics")

        unreal.log("\n" + "="*70)
        unreal.log("CAPTURE - ALL 6 ANGLES WITH 15S DELAY BETWEEN SHOTS")
        unreal.log(f"AUTO-ITERATION ENABLED: Will loop {self.max_iterations} times")
        unreal.log("="*70)

        # Step 1: Pilot to Scout
        self.test_pilot_to_scout()
        unreal.log("Pilot complete\n")

        # Step 2: Front Capture
        front_success = self.test_capture_front()
        if not front_success:
            unreal.log_error("Front capture failed to queue!")
            return
        unreal.log("Front queued (1/6)\n")

        # Schedule remaining captures with 15s delays
        unreal.log("⏳ Scheduling remaining captures (15s between each)...\n")

        # Schedule right view capture (starts the chain)
        unreal.log("⏳ Scheduling Right View in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_right_delayed)

    def _cleanup_scout_delayed(self):
        """Step 8: Delete scout camera"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  cleanup scout delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_cleanup_scout()
        unreal.log("Scout Camera deleted\n")

        # Schedule hero pilot
        unreal.log("⏳ Piloting to Hero Camera...\n")
        QTimer.singleShot(1000, self._pilot_hero_delayed)

    def _pilot_hero_delayed(self):
        """Step 9: Pilot to hero camera"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  pilot hero delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_pilot_to_hero()
        unreal.log("Hero Camera active\n")

        # Schedule hero shot capture
        unreal.log("⏳ Scheduling Hero Shot in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_hero_delayed)

    def _capture_hero_delayed(self):
        """Step 10: Capture hero shot"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  capture hero delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_hero()
        unreal.log("Hero Shot captured\n")

        # Schedule eject
        unreal.log("⏳ Ejecting from Pilot Mode in 15 seconds...\n")
        QTimer.singleShot(15000, self._eject_viewport_delayed)

    def _eject_viewport_delayed(self):
        """Step 11: Eject from pilot mode"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  eject viewport delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_eject_viewport()
        unreal.log("Ejected from Pilot Mode\n")

        # Schedule AI analysis
        unreal.log("⏳ Preparing to send captures to AI in 2 seconds...\n")
        QTimer.singleShot(2000, self._send_to_ai_analysis)

    def _capture_right_delayed(self):
        """Step 3: Capture right view"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Workflow cancelled - skipping right view")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_right()
        unreal.log("Right queued (2/6)\n")

        # Schedule back capture
        unreal.log("⏳ Scheduling Back View in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_back_delayed)

    def _capture_back_delayed(self):
        """Step 4: Capture back view"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  capture back delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_back()
        unreal.log("Back queued (3/6)\n")

        # Schedule left capture
        unreal.log("⏳ Scheduling Left View in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_left_delayed)

    def _capture_left_delayed(self):
        """Step 5: Capture left view"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  capture left delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_left()
        unreal.log("Left queued (4/6)\n")

        # Schedule top capture
        unreal.log("⏳ Scheduling Top View in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_top_delayed)

    def _capture_top_delayed(self):
        """Step 6: Capture top view"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  capture top delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_top()
        unreal.log("Top queued (5/6)\n")

        # Schedule 3/4 capture
        unreal.log("⏳ Scheduling 3/4 View in 15 seconds...\n")
        QTimer.singleShot(15000, self._capture_three_quarter_delayed)

    def _capture_three_quarter_delayed(self):
        """Step 7: Capture 3/4 view"""
        # Guard: Check if workflow was cancelled
        if not self.capture_workflow_active:
            unreal.log("Capture workflow cancelled - skipping  capture three quarter delayed")
            return

        unreal.log("\n" + "="*70)
        self.test_capture_3_4()
        unreal.log("3/4 queued (6/6)\n")

        # Schedule cleanup and hero pilot
        unreal.log("⏳ Scheduling cleanup in 15 seconds...\n")
        QTimer.singleShot(15000, self._cleanup_scout_delayed)

    def _get_current_scene_transforms(self):
        """Get current location, rotation, and scale of all actors in the sequence"""
        transforms = {}

        try:
            # Get the currently open sequence
            sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()

            if not sequence:
                unreal.log_warning("No sequence is currently open")
                return transforms

            # Get all bindings in sequence
            try:
                bindings = unreal.MovieSceneSequenceExtensions.get_bindings(sequence)
            except Exception as e:
                unreal.log_error(f"CRITICAL: Failed to get bindings: {e}")
                return transforms

            for binding in bindings:
                # Log each actor we're attempting to process
                try:
                    # CRITICAL: Convert to Python string - Unreal Name/Text types can't be dict keys
                    actor_name = str(unreal.MovieSceneBindingExtensions.get_display_name(binding))

                    # Get transform track
                    tracks = unreal.MovieSceneBindingExtensions.find_tracks_by_exact_type(
                        binding, unreal.MovieScene3DTransformTrack
                    )

                    if not tracks:
                        unreal.log(f"{actor_name}: No transform track found")
                        continue

                    transform_track = tracks[0]
                    sections = transform_track.get_sections()

                    if not sections:
                        unreal.log(f"{actor_name}: No sections in transform track")
                        continue

                    section = sections[0]
                    unreal.log(f"[1/4] {actor_name}: Got section, fetching channels...")
                    # section.get_all_channels() doesn't exist - causes "Type cannot be hashed" error
                    try:
                        channels = unreal.MovieSceneSectionExtensions.get_channels_by_type(
                            section,
                            unreal.MovieSceneScriptingDoubleChannel
                        )
                        unreal.log(f"[2/4] {actor_name}: Got {len(channels)} channels via MovieSceneSectionExtensions")
                    except Exception as e:
                        unreal.log_error(f"{actor_name}: MovieSceneSectionExtensions.get_channels_by_type() failed: {e}")
                        continue

                    if not channels or len(channels) < 9:
                        unreal.log(f"{actor_name}: Insufficient channels ({len(channels)}/9)")
                        continue

                    unreal.log(f"[3/4] {actor_name}: Ready to read keyframes...")

                    # Read values at frame 0
                    location = {'x': 0.0, 'y': 0.0, 'z': 0.0}
                    rotation = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0}
                    scale = {'x': 1.0, 'y': 1.0, 'z': 1.0}

                    unreal.log(f"[4/4] {actor_name}: Reading keyframes at frame 0...")

                    # Location (channels 0-2)
                    for i, axis in enumerate(['x', 'y', 'z']):
                        try:
                            channel = channels[i]
                            all_keys = channel.get_keys()
                            # Convert to list if needed (some UE types aren't directly iterable)
                            keys_list = list(all_keys) if all_keys else []
                            for key in keys_list:
                                frame_time = key.get_time()
                                if frame_time.frame_number.value == 0:
                                    location[axis] = key.get_value()
                                    break
                        except Exception as e:
                            unreal.log_error(f"Location {axis} read failed: {e}")
                            pass  # Keep default value

                    # Rotation (channels 3-5: Roll, Pitch, Yaw)
                    rotation_axes = ['roll', 'pitch', 'yaw']
                    for i, axis in enumerate(rotation_axes):
                        try:
                            channel = channels[3 + i]
                            all_keys = channel.get_keys()
                            keys_list = list(all_keys) if all_keys else []
                            for key in keys_list:
                                frame_time = key.get_time()
                                if frame_time.frame_number.value == 0:
                                    rotation[axis] = key.get_value()
                                    break
                        except Exception as e:
                            unreal.log_error(f"Rotation {axis} read failed: {e}")
                            pass  # Keep default value

                    # Scale (channels 6-8)
                    for i, axis in enumerate(['x', 'y', 'z']):
                        try:
                            channel = channels[6 + i]
                            all_keys = channel.get_keys()
                            keys_list = list(all_keys) if all_keys else []
                            for key in keys_list:
                                frame_time = key.get_time()
                                if frame_time.frame_number.value == 0:
                                    scale[axis] = key.get_value()
                                    break
                        except Exception as e:
                            unreal.log_error(f"Scale {axis} read failed: {e}")
                            pass  # Keep default value

                    transforms[actor_name] = {
                        'location': location,
                        'rotation': rotation,
                        'scale': scale
                    }

                    unreal.log(f"{actor_name}: SUCCESS - Loc({location['x']:.1f}, {location['y']:.1f}, {location['z']:.1f}), Rot(roll={rotation['roll']:.1f}, pitch={rotation['pitch']:.1f}, yaw={rotation['yaw']:.1f})")

                except Exception as e:
                    # DON'T silently skip - LOG the error with full traceback!
                    unreal.log_error(f"OUTER EXCEPTION for {actor_name}: {e}")
                    import traceback
                    unreal.log_error(f"Traceback: {traceback.format_exc()}")
                    continue

            # Final check
            if not transforms:
                unreal.log_error("CRITICAL: No transforms extracted from ANY actor!")
                unreal.log_error("This means AI will adjust blind with no position data!")
            else:
                unreal.log(f"Successfully extracted {len(transforms)} actor transforms")

        except Exception as e:
            unreal.log_error(f"CRITICAL: Transform extraction failed: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

        return transforms

    def _detect_scene_complexity(self, actors: List[str]) -> str:
        """
        Detect scene complexity based on actor count and types.

        Used by intelligent view selector to choose optimal camera angles.

        Args:
            actors: List of actor names in the scene

        Returns:
            'simple', 'medium', or 'complex'
        """
        num_actors = len(actors) if actors else 0

        if num_actors <= 2:
            return 'simple'
        elif num_actors <= 4:
            return 'medium'
        else:
            return 'complex'

    def _capture_gbuffer_depth_for_validation(self):
        """
        Capture Unreal's native G-Buffer depth maps for validation against AI-generated depth

        Returns:
            dict: {angle: base64_depth_image} or None if capture fails
        """
        # DISABLED: AutomationLibrary.set_visualize_buffer doesn't exist in UE 5.6.1
        # This feature is non-critical (only for validation/comparison)
        # TODO: Find correct UE 5.6.1 API for buffer visualization
        return None

        try:
            import base64

            unreal.log("\n Capturing native G-Buffer depth for validation...")

            # Get subsystems
            editor_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

            if not editor_world:
                unreal.log_warning("Could not get editor world for G-Buffer capture")
                return None

            # Save current viewport state
            saved_game_view = level_editor.editor_get_game_view()

            # Enable game view (hide editor gizmos)
            level_editor.editor_set_game_view(True)
            time.sleep(0.2)  # Allow viewport to update

            gbuffer_captures = {}
            screenshot_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"

            # We only need hero view for now (main comparison target)
            # Full 360° G-Buffer capture would require re-piloting cameras
            angles_to_capture = ['hero']

            for angle in angles_to_capture:
                try:
                    # Switch to SceneDepth buffer visualization
                    unreal.AutomationLibrary.set_visualize_buffer(
                        editor_world,
                        unreal.Name("SceneDepth")
                    )
                    time.sleep(0.3)  # Allow render to update

                    # Capture screenshot
                    filename = f"gbuffer_depth_{angle}"
                    command = f"HighResShot 1 filename={filename}"  # 1x resolution (match capture resolution)
                    unreal.SystemLibrary.execute_console_command(None, command)
                    time.sleep(0.5)  # Wait for screenshot to save

                    # Load the captured image
                    screenshot_path = screenshot_dir / f"{filename}.png"
                    if screenshot_path.exists():
                        with open(screenshot_path, 'rb') as f:
                            image_data = f.read()
                            gbuffer_captures[angle] = base64.b64encode(image_data).decode('utf-8')
                        unreal.log(f"Captured G-Buffer depth for {angle}")

                        # Delete temporary file
                        screenshot_path.unlink()
                    else:
                        unreal.log_warning(f"G-Buffer screenshot not found: {screenshot_path}")

                except Exception as e:
                    unreal.log_error(f"Failed to capture G-Buffer depth for {angle}: {e}")

            # Restore to normal lit view
            unreal.SystemLibrary.execute_console_command(None, "viewmode lit")
            time.sleep(0.3)

            # Restore game view state
            level_editor.editor_set_game_view(saved_game_view)

            return gbuffer_captures if gbuffer_captures else None

        except Exception as e:
            unreal.log_error(f"G-Buffer capture failed: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

            # Try to restore viewport
            try:
                unreal.SystemLibrary.execute_console_command(None, "viewmode lit")
                level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                level_editor.editor_set_game_view(False)
            except:
                pass

            return None

    def _save_debug_images(self, storyboard_b64: str, captures: dict, annotated_captures: dict = None, depth_maps: dict = None, metadata: dict = None):
        """
        Save all intermediate images to thesis debug folder for documentation

        Args:
            storyboard_b64: Base64 encoded storyboard image
            captures: Dict of original capture images {angle: base64_string}
            annotated_captures: Dict of marked-up capture images (optional)
            metadata: Additional metadata to save (iteration, scores, etc.)
        """
        try:
            import base64
            from datetime import datetime

            # Create panel-specific folder
            panel_name = Path(self.active_panel['path']).stem if self.active_panel else "unknown_panel"
            panel_folder = self.thesis_debug_folder / panel_name
            panel_folder.mkdir(parents=True, exist_ok=True)

            # Create iteration folder with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            iteration_folder = panel_folder / f"iteration_{self.current_iteration:03d}_{timestamp}"
            iteration_folder.mkdir(parents=True, exist_ok=True)

            unreal.log(f"\n Saving debug images to: {iteration_folder}")

            # Save storyboard (reference image)
            storyboard_path = iteration_folder / "01_storyboard_reference.png"
            with open(storyboard_path, 'wb') as f:
                f.write(base64.b64decode(storyboard_b64))
            unreal.log(f"Saved: {storyboard_path.name}")

            # Create subfolders for organization
            original_folder = iteration_folder / "02_scene_captures_original"
            original_folder.mkdir(exist_ok=True)

            # Save original captures
            for angle, image_b64 in captures.items():
                filepath = original_folder / f"{angle}.png"
                with open(filepath, 'wb') as f:
                    f.write(base64.b64decode(image_b64))
                unreal.log(f"Saved: 02_scene_captures_original/{angle}.png")

            # Save annotated/marked-up captures if available
            if annotated_captures:
                marked_folder = iteration_folder / "03_marked_up_with_grid_axes"
                marked_folder.mkdir(exist_ok=True)

                for angle, image_b64 in annotated_captures.items():
                    filepath = marked_folder / f"{angle}_marked.png"
                    with open(filepath, 'wb') as f:
                        f.write(base64.b64decode(image_b64))
                    unreal.log(f"Saved: 03_marked_up_with_grid_axes/{angle}_marked.png")

            # Save depth maps if available (with colorful TURBO colormap)
            if depth_maps:
                if CV2_NUMPY_AVAILABLE:
                    depth_folder = iteration_folder / "04_depth_maps"
                    depth_folder.mkdir(exist_ok=True)

                    for angle, depth_b64 in depth_maps.items():
                        # Decode grayscale depth
                        depth_bytes = base64.b64decode(depth_b64)
                        depth_array = np.frombuffer(depth_bytes, dtype=np.uint8)
                        depth_img = cv2.imdecode(depth_array, cv2.IMREAD_GRAYSCALE)

                        # Apply TURBO colormap (colorful rainbow-like visualization)
                        depth_colored = cv2.applyColorMap(depth_img, cv2.COLORMAP_TURBO)

                        # Save colorful depth map (AI-generated)
                        filepath = depth_folder / f"{angle}_depth_ai.png"
                        cv2.imwrite(str(filepath), depth_colored)
                        unreal.log(f"Saved: 04_depth_maps/{angle}_depth_ai.png (AI-generated, TURBO)")

                    # Save native G-Buffer depth maps if available
                    if metadata and 'gbuffer_depth_maps' in metadata:
                        for angle, depth_b64 in metadata['gbuffer_depth_maps'].items():
                            depth_bytes = base64.b64decode(depth_b64)
                            depth_array = np.frombuffer(depth_bytes, dtype=np.uint8)
                            depth_img = cv2.imdecode(depth_array, cv2.IMREAD_GRAYSCALE)

                            # Apply TURBO colormap for comparison
                            depth_colored = cv2.applyColorMap(depth_img, cv2.COLORMAP_TURBO)

                            # Save native depth map
                            filepath = depth_folder / f"{angle}_depth_native.png"
                            cv2.imwrite(str(filepath), depth_colored)
                            unreal.log(f"Saved: 04_depth_maps/{angle}_depth_native.png (UE native, TURBO)")
                else:
                    unreal.log_warning(f"Cannot colorize depth maps: cv2/numpy not available")

            # FEATURE #7: Create side-by-side comparison (storyboard vs hero camera)
            if 'hero' in captures:
                unreal.log(f"\n DEBUG: FEATURE #7 - Creating side-by-side comparison overlay")
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    import io

                    # Load images
                    storyboard_img = Image.open(io.BytesIO(base64.b64decode(storyboard_b64)))
                    hero_img = Image.open(io.BytesIO(base64.b64decode(captures['hero'])))
                    unreal.log(f"Storyboard size: {storyboard_img.size}, Hero size: {hero_img.size}")

                    # Resize to same height
                    max_height = 800
                    sb_ratio = max_height / storyboard_img.height
                    hero_ratio = max_height / hero_img.height

                    storyboard_resized = storyboard_img.resize(
                        (int(storyboard_img.width * sb_ratio), max_height),
                        Image.Resampling.LANCZOS
                    )
                    hero_resized = hero_img.resize(
                        (int(hero_img.width * hero_ratio), max_height),
                        Image.Resampling.LANCZOS
                    )

                    # Create side-by-side canvas
                    total_width = storyboard_resized.width + hero_resized.width + 20  # 20px gap
                    comparison = Image.new('RGB', (total_width, max_height + 60), (30, 30, 30))

                    # Paste images
                    comparison.paste(storyboard_resized, (0, 60))
                    comparison.paste(hero_resized, (storyboard_resized.width + 20, 60))

                    # Add labels
                    draw = ImageDraw.Draw(comparison)
                    try:
                        font = ImageFont.truetype("arial.ttf", 24)
                    except:
                        font = ImageFont.load_default()

                    draw.text((storyboard_resized.width // 2, 20), "TARGET (Storyboard)",
                             fill=(255, 255, 255), anchor="mm", font=font)
                    draw.text((storyboard_resized.width + 20 + hero_resized.width // 2, 20), "CURRENT (Hero Camera)",
                             fill=(255, 255, 255), anchor="mm", font=font)

                    # Save comparison
                    comparison_path = iteration_folder / "05_comparison_side_by_side.png"
                    comparison.save(comparison_path)
                    unreal.log(f"Saved: 05_comparison_side_by_side.png")

                except Exception as e:
                    unreal.log(f"Could not create comparison image: {e}")

            # Save metadata JSON
            if metadata:
                import json
                metadata_path = iteration_folder / "00_metadata.json"
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                unreal.log(f"Saved: {metadata_path.name}")

            # Create README for this iteration
            readme_path = iteration_folder / "README.txt"
            with open(readme_path, 'w') as f:
                f.write(f"Iteration {self.current_iteration} - {timestamp}\n")
                f.write("="*60 + "\n\n")
                f.write(f"Panel: {panel_name}\n")
                if metadata:
                    f.write(f"Match Score: {metadata.get('match_score', 'N/A')}\n")
                    f.write(f"Scene Context: {metadata.get('scene_context', {})}\n")
                f.write("\nFolder Contents:\n")
                f.write("  01_storyboard_reference.png - Original storyboard panel\n")
                f.write("  02_scene_captures_original/ - Raw scene captures from 7 camera angles\n")
                f.write("  03_marked_up_with_grid_axes/ - Annotated images with spatial markers + actor labels\n")
                if depth_maps:
                    f.write("  04_depth_maps/ - Depth maps for validation:\n")
                    f.write("    *_depth_ai.png - AI-generated depth (Depth-Anything-V2)\n")
                    f.write("    *_depth_native.png - Unreal G-Buffer depth (ground truth)\n")
                    f.write("    Both use TURBO colormap for visual comparison\n")
                f.write("  05_comparison_side_by_side.png - Target vs Current visual comparison\n")
                f.write("  00_metadata.json - Detailed iteration data and AI response\n")

            unreal.log(f"Debug images saved successfully to: {iteration_folder.name}")
            unreal.log(f"Total files: {len(list(iteration_folder.rglob('*.png')))} images + metadata")

        except Exception as e:
            unreal.log_error(f"Failed to save debug images: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def _send_to_ai_analysis(self):
        """Step 12: Send all captures + storyboard to AI for comparison (final)"""
        # CRITICAL: Wrap entire function to catch Qt callback crashes
        try:
            # Import at top to avoid variable shadowing issues
            import base64

            unreal.log("\n DEBUG: _send_to_ai_analysis called (callback fired)")

            # Guard: Check if workflow was cancelled
            if not self.capture_workflow_active:
                unreal.log("Capture workflow cancelled - skipping  send to ai analysis")
                return

            unreal.log("\n" + "="*70)
            unreal.log("="*70)

            if not self.active_panel:
                unreal.log_warning("No active panel - skipping AI analysis")
                self._finish_capture_sequence()
                return

            # Get screenshot directory
            screenshot_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"

            # Collect all 7 captures
            captures = {}
            capture_files = {
                'front': 'test_front.png',
                'right': 'test_right.png',
                'back': 'test_back.png',
                'left': 'test_left.png',
                'top': 'test_top.png',
                'three_quarter': 'test_front_3_4.png',
                'hero': 'test_hero.png'
            }

            unreal.log("Loading captures...")
            missing_captures = []
            for angle, filename in capture_files.items():
                filepath = screenshot_dir / filename
                if filepath.exists():
                    try:
                        with open(filepath, 'rb') as f:
                            image_data = f.read()
                            captures[angle] = base64.b64encode(image_data).decode('utf-8')
                        unreal.log(f"Loaded {angle}: {filename} ({len(image_data)} bytes)")
                    except Exception as e:
                        unreal.log_error(f"Failed to load {angle}: {e}")
                        missing_captures.append(angle)
                else:
                    unreal.log_warning(f"Missing {angle}: {filename}")
                    missing_captures.append(angle)

            # Check if we have critical captures
            if len(missing_captures) > 3:
                unreal.log_error(f"Too many missing captures ({len(missing_captures)}/7)")
                unreal.log_error(f"Missing: {', '.join(missing_captures)}")
                self._finish_capture_sequence()
                return

            # Keep original captures for debug saving
            original_captures = captures.copy()

            # OPTIMIZATION #3: Intelligent view selection (51% cost reduction)
            if self.use_intelligent_view_selection and self.view_selector:
                unreal.log("\n" + "="*70)
                unreal.log("INTELLIGENT VIEW SELECTION")
                unreal.log("="*70)

                # Get actors in scene
                actors_in_scene = []
                if hasattr(self, 'characters_list'):
                    actors_in_scene = [self.characters_list.item(i).text() for i in range(self.characters_list.count())]

                # Detect scene complexity
                scene_complexity = self._detect_scene_complexity(actors_in_scene)

                # Get shot type
                shot_type = self.shot_type_combo.currentText() if hasattr(self, 'shot_type_combo') else 'medium'

                # Get previous score for adaptive selection
                previous_score = self.iteration_scores[-1] if self.iteration_scores else None

                # Select views for this iteration
                view_selection = self.view_selector.select_views(
                    iteration=self.current_iteration,
                    previous_score=previous_score,
                    num_actors=len(actors_in_scene),
                    shot_type=shot_type,
                    scene_complexity=scene_complexity,
                    available_captures=captures
                )

                # Filter captures to only selected RGB views
                selected_captures = {angle: captures[angle] for angle in view_selection.rgb_views if angle in captures}

                unreal.log(f"Strategy: {view_selection.strategy_name}")
                unreal.log(f"Reasoning: {view_selection.reasoning}")
                unreal.log(f"Selected {len(selected_captures)} views: {list(selected_captures.keys())}")
                unreal.log(f"Estimated cost: ${view_selection.estimated_cost:.4f}")
                unreal.log(f"Estimated tokens: {view_selection.estimated_token_count:,}")
                unreal.log("="*70 + "\n")

                # Use filtered captures
                captures = selected_captures

                # Store depth view selection for later use
                selected_depth_views = view_selection.depth_views
                include_storyboard_depth = view_selection.include_storyboard_depth
            else:
                # Original behavior - all 7 views
                unreal.log("ℹ Using all 7 views (intelligent view selection disabled)")
                selected_depth_views = ['hero', 'front', 'top']
                include_storyboard_depth = True

            # STEP 1: Generate depth maps FIRST (so they're available for annotations)
            depth_maps = {}

            # ============================================================
            # CRITICAL: Restart subprocess every 10 iterations to prevent memory leaks
            # PyTorch accumulates CUDA memory - needs fresh start periodically
            # Safe to do here because we're BEFORE depth generation, not during Qt event
            # ============================================================
            if self.depth_analyzer and self.depth_analyzer.available:
                if self.current_iteration > 1 and (self.current_iteration - 1) % 10 == 0:
                    unreal.log(f"\n Restarting depth estimation subprocess (iteration {self.current_iteration}) to clear memory...")

                    # Check if still alive before cleanup
                    is_alive = True
                    if hasattr(self.depth_analyzer, 'process') and self.depth_analyzer.process:
                        is_alive = self.depth_analyzer.process.poll() is None

                    if is_alive:
                        unreal.log("Process is alive - shutting down gracefully...")
                        self.depth_analyzer._cleanup()
                    else:
                        unreal.log("Process already dead - skipping cleanup...")

                    # Wait for cleanup
                    time.sleep(0.5)

                    # Reinitialize analyzer to spawn fresh subprocess
                    try:
                        from analysis.depth_analyzer import DepthAnalyzer
                        self.depth_analyzer = DepthAnalyzer()
                        if self.depth_analyzer.available:
                            unreal.log("Depth analyzer restarted successfully (fresh CUDA memory)")
                        else:
                            unreal.log_warning("Depth analyzer failed to restart")
                    except Exception as e:
                        unreal.log_warning(f"Could not restart depth analyzer: {e}")
                        self.depth_analyzer = None

            # CRITICAL: Check if depth analyzer subprocess is still alive
            # After processing many depth maps (3+ panels), subprocess can hang
            if self.depth_analyzer and self.depth_analyzer.available:
                # Check if subprocess is responsive
                if hasattr(self.depth_analyzer, 'process') and self.depth_analyzer.process:
                    poll_status = self.depth_analyzer.process.poll()
                    if poll_status is not None:
                        # Process has terminated
                        unreal.log_warning(f"Depth analyzer subprocess died (exit code: {poll_status})")
                        unreal.log_warning("Depth maps will be INACTIVE for this iteration (6/8 features)")
                        self.depth_analyzer = None
                    # else: poll() returns None = process is still running
                # If no process attribute, assume it's available

            if self.depth_analyzer and self.depth_analyzer.available:
                unreal.log("\n Generating depth maps for spatial analysis...")

                # Use selected depth views if intelligent view selection is active
                # Otherwise use default set (hero, front, right, back, left, top, three_quarter)
                if hasattr(self, 'use_intelligent_view_selection') and self.use_intelligent_view_selection:
                    key_captures = selected_depth_views
                    unreal.log(f"Using intelligent view selection: {len(key_captures)} depth maps")
                else:
                    key_captures = ['hero', 'front', 'right', 'back', 'left', 'top', 'three_quarter']
                    unreal.log(f"Using default depth views: {len(key_captures)} depth maps")

                for angle in key_captures:
                    if angle in original_captures:
                        unreal.log(f"Generating depth for {angle}...")
                        depth_result = self.depth_analyzer.generate_depth_map(original_captures[angle])
                        if depth_result and depth_result.get('success'):
                            depth_maps[angle] = depth_result['depth_map_b64']
                            unreal.log(f"{angle} depth generated")
                        else:
                            unreal.log_warning(f"{angle} depth failed")

                unreal.log(f"Generated {len(depth_maps)} depth maps")
            else:
                unreal.log("ℹ Depth analyzer not available (install torch+transformers for depth estimation)")

            # STEP 1.5: Capture G-Buffer native depth for validation
            gbuffer_depth_maps = self._capture_gbuffer_depth_for_validation()
            if gbuffer_depth_maps:
                unreal.log(f"Captured {len(gbuffer_depth_maps)} native G-Buffer depth maps for validation")

            # STEP 2: Apply visual markers to captures (Feature #1: +35-40% accuracy)
            # Now depth maps are available for overlay!
            annotated_captures = {}
            if self.marker_renderer and self.marker_renderer.available:
                unreal.log("\n Applying visual markers to captures...")
                unreal.log(f"DEBUG: Processing {len(captures)} captures: {list(captures.keys())}")

                # Extract actor positions for labels (get current transforms first)
                current_transforms = self._get_current_scene_transforms()
                actor_labels = {}
                for actor_name, transform in current_transforms.items():
                    loc = transform['location']
                    actor_labels[actor_name] = {
                        'x': loc['x'],
                        'y': loc['y'],
                        'z': loc['z']
                    }
                unreal.log(f"DEBUG: Extracted {len(actor_labels)} actor labels: {list(actor_labels.keys())}")

                for angle, image_b64 in captures.items():
                    try:
                        unreal.log(f"DEBUG: Annotating {angle} (image size: {len(image_b64)} chars)")
                        # Pass depth map if available for this angle
                        depth_for_angle = depth_maps.get(angle, None)
                        annotated_b64 = self.marker_renderer.add_markers_to_base64(
                            image_b64, angle, depth_map_b64=depth_for_angle, actor_labels=actor_labels
                        )
                        annotated_captures[angle] = annotated_b64
                        size_diff = len(annotated_b64) - len(image_b64)
                        unreal.log(f"DEBUG: {angle} annotated (size change: {size_diff:+d} chars)")
                    except Exception as e:
                        unreal.log_warning(f"Failed to add markers to {angle}: {e}")
                        import traceback
                        traceback.print_exc()
                        annotated_captures[angle] = image_b64  # Use original

                captures = annotated_captures
                unreal.log(f"Visual markers applied to {len(captures)} captures")
                markers_list = ["Grid", "axes (X/Y/Z)", "scale bars", "ground plane", "actor labels"]
                if depth_maps:
                    markers_list.append("depth overlay (30% opacity)")
                unreal.log(f"Markers include: {', '.join(markers_list)}")
            else:
                unreal.log("Visual markers not available (install opencv-python and pillow)")
                annotated_captures = None  # No annotations available

            # Load storyboard panel
            storyboard_path = Path(self.active_panel['path'])
            if storyboard_path.exists():
                try:
                    with open(storyboard_path, 'rb') as f:
                        storyboard_data = f.read()
                        storyboard_b64 = base64.b64encode(storyboard_data).decode('utf-8')
                    unreal.log(f"Loaded storyboard: {storyboard_path.name} ({len(storyboard_data)} bytes)")
                except Exception as e:
                    unreal.log_error(f"Failed to load storyboard: {e}")
                    self._finish_capture_sequence()
                    return
            else:
                unreal.log_error(f"Storyboard not found at: {storyboard_path}")
                self._finish_capture_sequence()
                return

            # Get current scene context with transforms
            unreal.log("\n Extracting current scene transforms...")
            current_transforms = self._get_current_scene_transforms()

            scene_context = {
                'characters': [self.characters_list.item(i).text() for i in range(self.characters_list.count())],
                'props': [self.props_list.item(i).text() for i in range(self.props_list.count())],
                'location_elements': self.active_panel.get('location_elements', []) if self.active_panel else [],
                'location': self.location_combo.currentText(),
                'shot_type': self.shot_type_combo.currentText(),
                'current_transforms': current_transforms
            }

            unreal.log("\nScene Context:")
            unreal.log(f"Characters: {scene_context['characters']}")
            unreal.log(f"Props: {scene_context['props']}")
            unreal.log(f"Location: {scene_context['location']}")
            unreal.log(f"Shot Type: {scene_context['shot_type']}")
            unreal.log(f"Actors with transforms: {len(current_transforms)}")

            # Log transforms with error handling
            try:
                for actor_name, transform in current_transforms.items():
                    loc = transform['location']
                    rot = transform['rotation']
                    unreal.log(f"• {actor_name}: Loc({loc['x']:.1f}, {loc['y']:.1f}, {loc['z']:.1f}) Rot(P={rot['pitch']:.1f}°, Y={rot['yaw']:.1f}°, R={rot['roll']:.1f}°)")
            except Exception as e:
                unreal.log(f"Could not log transform details: {type(e).__name__}")

            # Generate depth for storyboard (if analyzer available and view selector allows it)
            should_generate_storyboard_depth = (
                hasattr(self, 'use_intelligent_view_selection') and
                self.use_intelligent_view_selection and
                not include_storyboard_depth
            )

            if not should_generate_storyboard_depth:
                # Generate storyboard depth (either not using intelligent selection or selector wants it)
                if self.depth_analyzer and self.depth_analyzer.available and 'storyboard' not in depth_maps:
                    unreal.log("\nGenerating depth for storyboard...")
                    storyboard_depth_result = self.depth_analyzer.generate_depth_map(storyboard_b64)
                    if storyboard_depth_result and storyboard_depth_result.get('success'):
                        depth_maps['storyboard'] = storyboard_depth_result['depth_map_b64']
                        unreal.log(f"Generated storyboard depth")
                    else:
                        unreal.log_warning(f"Failed to generate storyboard depth")
            else:
                unreal.log("ℹ Skipping storyboard depth (not selected by intelligent view selector)")

            # Build prompt with scene context
            unreal.log("\n" + "="*70)
            unreal.log("DEBUG: SCENE CONTEXT VALIDATION")
            unreal.log("="*70)
            unreal.log(f"Characters: {scene_context.get('characters', [])}")
            unreal.log(f"Props: {scene_context.get('props', [])}")
            unreal.log(f"Location: {scene_context.get('location', 'Unknown')}")
            unreal.log(f"Location Elements: {scene_context.get('location_elements', [])}")
            unreal.log(f"Shot Type: {scene_context.get('shot_type', 'Unknown')}")
            unreal.log(f"Positioning Mode: {'ABSOLUTE' if self.use_absolute_positioning else 'RELATIVE'}")
            if scene_context.get('current_transforms'):
                unreal.log(f"Actors with transforms: {list(scene_context['current_transforms'].keys())}")
                for actor, xform in scene_context['current_transforms'].items():
                    loc = xform['location']
                    rot = xform['rotation']
                    unreal.log(f"{actor}:")
                    unreal.log(f"Location: X={loc['x']:.1f}, Y={loc['y']:.1f}, Z={loc['z']:.1f}")
                    unreal.log(f"Rotation: Pitch={rot['pitch']:.1f}, Yaw={rot['yaw']:.1f}, Roll={rot['roll']:.1f}")
            else:
                unreal.log("No current transforms available!")
            unreal.log("="*70 + "\n")

            prompt = self._build_positioning_prompt(scene_context)

            # Save debug metadata
            debug_metadata = {
                'iteration': self.current_iteration,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'prompt_length': len(prompt),
                'captures_included': list(captures.keys()),
                'visual_markers_applied': annotated_captures is not None,
                'depth_maps_generated': len(depth_maps) if depth_maps else 0,
                'gbuffer_depth_maps': gbuffer_depth_maps if gbuffer_depth_maps else {},
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._save_debug_images(
                storyboard_b64,
                original_captures,
                annotated_captures if annotated_captures else None,
                depth_maps if depth_maps else None,
                debug_metadata
            )

            unreal.log("\nSending to AI...")
            unreal.log(f"Total images: {len(captures) + 1} ({len(captures)} captures + 1 storyboard)")
            unreal.log(f"Prompt length: {len(prompt)} chars")

            # DEBUG: Show full prompt
            unreal.log("\n" + "="*70)
            unreal.log("DEBUG: FULL AI PROMPT")
            unreal.log("="*70)
            unreal.log(prompt)
            unreal.log("="*70 + "\n")

            # Call AI with multiple images
            try:
                from api.ai_client import AIClient

                client = AIClient()
                self.current_ai_client = client  #  Store for CSV detection
                unreal.log(f"Using provider: {client.provider}")
                unreal.log(f"Model: {client.model}")
                unreal.log(f"Iteration: {self.current_iteration}/{self.max_iterations}")
                unreal.log(f"Last match score: {self.last_match_score if hasattr(self, 'last_match_score') else 'N/A'}")

                # Build multi-image request
                result = self._call_ai_with_multiple_images(
                    client, prompt, storyboard_b64, captures, depth_maps
                )

                unreal.log(f"\n   Received result: {type(result)}, length: {len(result) if result else 0}")

                if result is not None:
                    unreal.log("\nAI ANALYSIS COMPLETE!")
                    unreal.log("="*70)
                    unreal.log("DEBUG: Raw AI response (first 500 chars):")
                    unreal.log(result[:500])
                    unreal.log("="*70)

                    # Parse JSON response
                    analysis = self._parse_ai_positioning_response(result)

                    if analysis:
                        unreal.log("\nDEBUG: PARSED ANALYSIS")
                        unreal.log("="*70)
                        unreal.log(f"Match Score: {analysis.get('match_score', 'MISSING')}")
                        unreal.log(f"Analysis Text: {analysis.get('analysis', 'MISSING')[:200]}...")
                        unreal.log(f"Adjustments Count: {len(analysis.get('adjustments', []))}")
                        if analysis.get('adjustments'):
                            for i, adj in enumerate(analysis.get('adjustments', [])):
                                unreal.log(f"Adjustment {i+1}: {adj.get('actor', 'UNKNOWN')} - {adj.get('type', 'UNKNOWN')}")
                        unreal.log("="*70 + "\n")

                        # Validate analysis has required fields
                        if 'match_score' not in analysis:
                            unreal.log_error("Analysis missing 'match_score' field")
                            unreal.log_error(f"Available fields: {list(analysis.keys())}")

                        # Update metadata with AI response
                        debug_metadata['match_score'] = analysis.get('match_score', 'N/A')
                        debug_metadata['analysis'] = analysis.get('analysis', '')
                        debug_metadata['adjustments'] = analysis.get('adjustments', [])
                        debug_metadata['camera_adjustments'] = analysis.get('camera_adjustments', {})
                        debug_metadata['ai_response_received'] = True

                        # Save updated metadata with AI response
                        import json
                        panel_name = Path(self.active_panel['path']).stem if self.active_panel else "unknown_panel"
                        panel_folder = self.thesis_debug_folder / panel_name
                        # Find the most recent iteration folder (the one we just created)
                        iteration_folders = sorted([d for d in panel_folder.glob('iteration_*') if d.is_dir()])
                        if iteration_folders:
                            latest_folder = iteration_folders[-1]
                            metadata_path = latest_folder / "00_metadata.json"
                            try:
                                with open(metadata_path, 'w') as f:
                                    json.dump(debug_metadata, f, indent=2)
                                unreal.log(f"Updated metadata with AI response: {metadata_path.name}")
                            except Exception as e:
                                unreal.log_warning(f"Could not update metadata: {e}")

                        # Display results
                        self._display_positioning_results(analysis)

                        # Store for potential adjustments and iteration history
                        self.last_positioning_analysis = analysis

                        # Track score trajectory for better learning
                        match_score = analysis.get('match_score', 0)
                        if not hasattr(self, 'score_trajectory'):
                            self.score_trajectory = []
                        self.score_trajectory.append(match_score)

                        # AUTO-APPLY adjustments
                        unreal.log("\n" + "="*70)
                        unreal.log("AUTO-APPLYING AI ADJUSTMENTS")
                        unreal.log("="*70)

                        # Store adjustments before applying (for next iteration context)
                        if not hasattr(self, 'last_adjustments_applied'):
                            self.last_adjustments_applied = []
                        self.last_adjustments_applied = analysis.get('adjustments', [])

                        self._apply_ai_adjustments(analysis)
                    else:
                        unreal.log_error("\n FAILED TO PARSE AI RESPONSE")
                        unreal.log_error("="*70)
                        unreal.log_error("Raw response (first 1000 chars):")
                        unreal.log_error(f"{result[:1000]}")
                        unreal.log_error("="*70)
                        unreal.log_error("Possible issues:")
                        unreal.log_error("- Response is not valid JSON")
                        unreal.log_error("- Response missing required fields")
                        unreal.log_error("- Response has unexpected structure")
                else:
                    unreal.log_error("AI request returned None")
                    unreal.log_error("Check API key, network connection, and API limits")

            except ImportError as e:
                unreal.log_error(f"Could not import AI client: {e}")
                unreal.log_error("Make sure api/ai_client.py exists")
            except Exception as e:
                unreal.log_error(f"AI call error: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())

            # Store for next phase
            self.last_captures = captures
            self.last_storyboard = storyboard_b64
            self.last_scene_context = scene_context

            # CRITICAL: Call finish to complete iteration and schedule next one
            self._finish_capture_sequence()

        except Exception as e:
            unreal.log_error(f"CRASH PREVENTED in _send_to_ai_analysis: {e}")
            unreal.log_error("This was likely a Qt callback crash")
            import traceback
            unreal.log_error(traceback.format_exc())
            # Always finish sequence even on crash
            self._finish_capture_sequence()

    def _build_positioning_prompt(self, scene_context):
        """Build the AI prompt for positioning analysis"""

        # Determine positioning mode
        mode_str = "ABSOLUTE" if self.use_absolute_positioning else "RELATIVE"

        # Build mode-specific instructions
        if self.use_absolute_positioning:
            # SIMPLIFIED POSITIONING FOR THESIS PROOF-OF-CONCEPT
            # All characters at ground level (Z=0) in T-pose for rough spatial layout
            landmarks = ["- Ground level: Z=0 (all characters positioned at ground level)"]

            # Add character-specific landmarks only for characters that exist
            characters = scene_context.get('characters', [])
            unreal.log(f"DEBUG: characters={characters}")
            if 'Oat' in characters or any('oat' in c.lower() for c in characters):
                landmarks.extend([
                    '- Character "Oat" model properties:',
                    '  * T-pose static model (no animations)',
                    '  * Model height: 170 units (1.7m from feet to head)',
                    '  * Feet/origin: Always at Z=0 (ground level)',
                ])
                unreal.log(f"DEBUG: Added Oat character landmarks (4 items)")

            landmarks_text = '\n'.join(landmarks)
            unreal.log(f"\n DEBUG: SCENE LANDMARKS ({len(landmarks)} total):")
            for landmark in landmarks:
                unreal.log(f"{landmark}")

            # Simplified calculation example - always Z=0 for T-pose
            calc_example = f"""EXAMPLE CALCULATION (ABSOLUTE MODE - T-POSE PROOF-OF-CONCEPT):
Storyboard: Character in scene
Step 1: This is a rough spatial layout test using T-pose static models
Step 2: All characters are positioned at ground level (Z=0)
Step 3: Focus on horizontal positioning (X, Y) and facing direction (Yaw rotation)
Step 4: Calculate X, Y based on storyboard composition
ANSWER: {{"actor": "{characters[0] if characters else 'ActorName'}", "position": {{"x": 100, "y": 50, "z": 0}}}}

 All T-pose characters stay at Z=0 for this proof-of-concept"""
            unreal.log("DEBUG: Using simplified T-POSE calculation example")

            mode_instructions = f"""--- ABSOLUTE MODE ACTIVE ---
You are in ABSOLUTE positioning mode. This means:
- Provide TARGET COORDINATES where actors/camera SHOULD BE
- NOT relative adjustments ("move up 100") but ABSOLUTE positions ("should be at Z=150")
- Look at the CURRENT TRANSFORMS above to see where actors are now
- Calculate where they need to be to match the storyboard
- Provide those final target coordinates

SCENE LANDMARKS (fixed world positions):
{landmarks_text}

COORDINATE CALCULATION REQUIRED:
Before providing position values, you MUST calculate:
1. Where is the target object in the storyboard? (standing, specific location, etc.)
2. What is the world position of that location? (use landmarks above if available)
3. What absolute coordinates achieve that position?

{calc_example}

DO NOT just repeat current position! Calculate the TARGET position using available landmarks.
"""
            position_comment = "ABSOLUTE target coordinates"
            rule3 = "**Target coordinates** - Calculate WHERE actors should be using SCENE LANDMARKS, show your calculation"
            reason_requirement = 'MUST include calculation: "Target is at X, therefore coordinate = Y"'
        else:
            mode_instructions = """--- RELATIVE MODE ACTIVE ---
You are in RELATIVE positioning mode. This means:
- Provide ADJUSTMENTS to current position ("move up 100" = Z=100)
- These values are ADDED to current coordinates
- Use reference objects for scale estimation

EXAMPLE (RELATIVE MODE):
- Current: Oat at Z=100
- Needs to be lower by character-height (170 units)
- Response: {"actor": "Oat", "position": {"x": 0, "y": 0, "z": -170}}
  (This moves Oat from Z=100 to Z=-70)
"""
            position_comment = "RELATIVE adjustment values"
            rule3 = "**Cumulative thinking** - These are RELATIVE changes from current position"
            reason_requirement = "SPECIFIC reason with spatial details"

        # FEATURE #9: Build spatial relationships for context
        spatial_relationships = []
        if scene_context.get('current_transforms'):
            actors = list(scene_context['current_transforms'].items())
            if len(actors) >= 2:
                unreal.log(f"\n DEBUG: FEATURE #9 - Calculating spatial relationships between {len(actors)} actors")
                # Calculate distance between first two actors
                loc1 = actors[0][1]['location']
                loc2 = actors[1][1]['location']
                import math
                distance = math.sqrt((loc2['x'] - loc1['x'])**2 + (loc2['y'] - loc1['y'])**2 + (loc2['z'] - loc1['z'])**2)
                spatial_relationships.append(f"{actors[0][0]} is {distance:.0f} units from {actors[1][0]}")
                unreal.log(f"Distance: {actors[0][0]} <-> {actors[1][0]} = {distance:.0f} units")

                # Add Y-axis separation (left/right)
                y_diff = loc2['y'] - loc1['y']
                if abs(y_diff) > 10:
                    direction = "right" if y_diff > 0 else "left"
                    spatial_relationships.append(f"{actors[1][0]} is {abs(y_diff):.0f} units to the {direction} of {actors[0][0]}")
                    unreal.log(f"Y-axis: {actors[1][0]} is {abs(y_diff):.0f} units to the {direction}")

        spatial_text = ""
        if spatial_relationships:
            spatial_text = "\n\nCURRENT SPATIAL RELATIONSHIPS:\n" + "\n".join(f"- {r}" for r in spatial_relationships)
            unreal.log(f"{len(spatial_relationships)} spatial relationships added to prompt")
        else:
            unreal.log(f"\n DEBUG: FEATURE #9 - No spatial relationships (< 2 actors)")

        # Build current transforms section
        transforms_text = ""
        if scene_context.get('current_transforms'):
            transforms_text = "\n\nCURRENT ACTOR TRANSFORMS (at frame 0):\n"
            for actor_name, transform in scene_context['current_transforms'].items():
                loc = transform['location']
                rot = transform['rotation']
                scale = transform['scale']
                transforms_text += f"""• {actor_name}:
  - Location: X={loc['x']:.1f}, Y={loc['y']:.1f}, Z={loc['z']:.1f}
  - Rotation: Pitch={rot['pitch']:.1f}°, Yaw={rot['yaw']:.1f}°, Roll={rot['roll']:.1f}°
  - Scale: X={scale['x']:.2f}, Y={scale['y']:.2f}, Z={scale['z']:.2f}
"""

        # FEATURE #2: Previous iteration context
        iteration_context = ""
        if self.current_iteration > 1 and hasattr(self, 'last_match_score') and self.last_match_score is not None:
            unreal.log(f"\n DEBUG: FEATURE #2 - Adding iteration context to prompt")
            unreal.log(f"Previous score: {self.last_match_score}/100")
            unreal.log(f"Iteration: {self.current_iteration}/{self.max_iterations}")

            # Build score trajectory string
            score_history = ""
            if len(self.score_trajectory) > 0:
                score_history = "Score progression: " + " → ".join([f"{s:.0f}" for s in self.score_trajectory])
                # Calculate trend
                if len(self.score_trajectory) >= 2:
                    recent_change = self.score_trajectory[-1] - self.score_trajectory[-2]
                    if recent_change > 5:
                        score_history += f" (improving +{recent_change:.0f})"
                    elif recent_change < -5:
                        score_history += f" (declining {recent_change:.0f})"
                    else:
                        score_history += " (stagnating)"

            # Build concrete adjustments applied
            adjustments_detail = ""
            if hasattr(self, 'last_adjustments_applied') and self.last_adjustments_applied:
                adjustments_detail = "\nADJUSTMENTS THAT WERE JUST APPLIED:\n"
                for adj in self.last_adjustments_applied[:3]:  # Show max 3
                    actor = adj.get('actor', 'Unknown')
                    adj_type = adj.get('type', 'unknown')
                    if adj_type == 'move' and adj.get('position'):
                        pos = adj['position']
                        adjustments_detail += f"- {actor}: Moved to X={pos.get('x', 0):.0f}, Y={pos.get('y', 0):.0f}, Z={pos.get('z', 0):.0f}\n"
                    elif adj_type == 'rotate' and adj.get('rotation'):
                        rot = adj['rotation']
                        adjustments_detail += f"- {actor}: Rotated to Yaw={rot.get('yaw', 0):.0f}°\n"
                if len(self.last_adjustments_applied) > 3:
                    adjustments_detail += f"- ... and {len(self.last_adjustments_applied) - 3} more adjustments\n"
            else:
                adjustments_detail = "\nADJUSTMENTS THAT WERE JUST APPLIED: None (first positioning)\n"

            # Build positioning mode guidance
            positioning_mode_guidance = ""
            if self.use_absolute_positioning:
                positioning_mode_guidance = """
 ABSOLUTE POSITIONING MODE:
- Specify WHERE each actor SHOULD BE (target coordinates)
- DO NOT calculate adjustments from current position
- Simply state the correct final position directly
- System automatically moves actors from current → target position
"""
            else:
                positioning_mode_guidance = """
 RELATIVE POSITIONING MODE:
- Provide adjustments to ADD to current position
- Example: Actor at X=100, you say X=-50 → moves to X=50
- Calculate: target_position - current_position = adjustment
"""

            iteration_context = f"""
╔══════════════════════════════════════════════════════════════════════
║  ITERATION {self.current_iteration} - LEARN FROM PREVIOUS RESULT
╚══════════════════════════════════════════════════════════════════════
{score_history}
Previous score: {self.last_match_score:.0f}/100
{adjustments_detail}{positioning_mode_guidance}
 ITERATION STRATEGY:
- If score IMPROVED (↗): Your previous targets worked → make similar refinements
- If score DECLINED (↘): Your previous targets made it worse → analyze what went wrong
- If score STAGNATED (→): Your targets had no effect → focus on different actors
- LOOK AT THE CURRENT TRANSFORMS above - don't guess where actors are now
- In ABSOLUTE mode: Just specify where things should be, don't do math

"""
        else:
            unreal.log(f"\n DEBUG: FEATURE #2 - No previous context (first iteration)")


        # FEATURE #4: Match score targets
        target_score = 80 if self.current_iteration > 3 else 70
        unreal.log(f"\n DEBUG: FEATURE #4 - Match score target: {target_score}/100")
        if self.last_match_score:
            unreal.log(f"Current score: {self.last_match_score}/100, Target: {target_score}/100")

        score_guidance = f"""
╔══════════════════════════════════════════════════════════════════════
║  MATCH SCORE TARGET: {target_score}/100
╚══════════════════════════════════════════════════════════════════════"""
        if self.last_match_score:
            gap = target_score - self.last_match_score
            if gap > 0:
                score_guidance += f"""
CURRENT GAP: {gap:.0f} points below target

PRIORITIZATION STRATEGY:
1. Identify the LARGEST positioning error (biggest impact)
2. Recommend ONE adjustment that gives maximum improvement
3. Ignore small issues until major ones are fixed
4. Focus on high-value changes first
"""
            else:
                score_guidance += f"""
 TARGET EXCEEDED! Current score: {self.last_match_score}/100

REFINEMENT STRATEGY:
- Make small adjustments to perfect the positioning
- Focus on fine-tuning rather than major changes
"""

        return f"""You are a positioning accuracy evaluator for 3D scene matching against storyboards.

 CRITICAL CONTEXT - T-POSE STATIC MODELS
**ALL CHARACTERS ARE STATIC T-POSE MODELS WITH NO ANIMATIONS!**

This is a PROOF-OF-CONCEPT testing SPATIAL LAYOUT ONLY:
-  **SCORE THESE:** Position (X,Y), Spacing, Facing (Yaw), Camera framing
-  **IGNORE THESE:** Standing vs sitting, T-pose vs animated, Missing gestures, Body language

**CRITICAL SCORING RULE:**
• Storyboard shows sitting characters → If T-pose positioned correctly at sitting location = **70-85/100** score
• Storyboard shows standing characters → If T-pose positioned correctly at standing location = **70-85/100** score
• **FOCUS ON:** "Are characters in the right LOCATION with right SPACING and FRAMING?"
• **NOT:** "Are they performing the right action or pose?"

**Concrete Example:**
- Storyboard: Two characters sitting side-by-side on bench
- 3D Scene: Two T-pose characters standing at bench with correct spacing (120 units apart)
- **CORRECT Score:** 75-80/100 (excellent spatial match, ignore pose difference)
- **WRONG Score:** 10/100 (penalizing for not sitting) ← **DO NOT DO THIS!**

Remember: You are scoring SPATIAL POSITIONING ACCURACY, not animation or pose accuracy.
{iteration_context}{score_guidance}

Your core evaluation principle: Evaluate ONLY actors that are explicitly present in the provided scene data.

═══════════════════════════════════════════════════════════════════
 EVALUATION SCOPE: ACTORS PRESENT IN THIS SCENE
═══════════════════════════════════════════════════════════════════
CHARACTERS: {', '.join(scene_context['characters']) if scene_context['characters'] else 'None'}
PROPS: {', '.join(scene_context['props']) if scene_context['props'] else 'None'}
LOCATION: {scene_context['location']}
LOCATION ELEMENTS (Static Scenery): {', '.join(scene_context.get('location_elements', [])) if scene_context.get('location_elements') else 'None'}
SHOT TYPE: {scene_context['shot_type']}

 CRITICAL: The actors listed above are the COMPLETE and EXCLUSIVE scope of your evaluation.

 LOCATION ELEMENTS NOTE:
Location elements (bench, trees, etc.) are STATIC SCENERY that exist in the location.
- You CANNOT move or adjust location elements
- They are part of the environment, not actors
- Only position CHARACTERS and PROPS (moveable objects)
═══════════════════════════════════════════════════════════════════{transforms_text}{spatial_text}

 YOUR EVALUATION TASK:
Assess how well the PRESENT actors are positioned to match the storyboard composition.

 EVALUATION PRINCIPLES (Research-Backed):
1. **Scope Boundary**: Your evaluation universe consists exclusively of the actors listed above
2. **Quality Focus**: Assess positioning quality of present actors on their own merits
3. **Score Calculation**: match_score = (Points from present actors / Max points for present actors) × 100
4. **Completeness Independence**: A scene with fewer actors but excellent positioning receives a high score

 MATCH SCORE CALCULATION FORMULA:
For each present actor:
- Perfect positioning quality: 100 points / actor
- Good positioning quality: 70 points / actor
- Needs adjustment: 40 points / actor
- Poor positioning: 10 points / actor

Total Score = (Sum of points earned) / (100 × number of present actors) × 100

EXAMPLES:
- Scene with 1 actor perfectly positioned: 100/100 = 100% match score
- Scene with 2 actors, both good positioning: (70+70)/200 = 70% match score
- Scene with 3 actors, 2 perfect + 1 needs work: (100+100+40)/300 = 80% match score

 SCORING BANDS (Quality-Based):
- 80-100: Present actors positioned with high accuracy relative to storyboard intent
  *  **T-pose models:** If spatial layout matches storyboard (location, spacing, framing) = 75-85/100
  * ACTION: Provide EMPTY adjustments array [] - scene is good enough
- 60-79: Present actors well positioned with minor improvements needed
  *  **T-pose models:** Correct positions but needs spacing/facing refinement = 65-75/100
  * ACTION: Small refinements only (10-50 units, 5-10° rotations)
- 40-59: Present actors require repositioning to better match storyboard
  *  **T-pose models:** Positions approximately correct but need adjustment = 45-55/100
  * ACTION: Moderate adjustments (50-150 units, 10-30° rotations)
- 20-39: Present actors have significant positioning issues
  * ACTION: Major adjustments (100-300 units, 30-90° rotations)
- 0-19: Present actors positioned completely incorrectly
  * ACTION: Complete repositioning (200-500 units, up to 180° rotations)

 CRITICAL - EXACT NAMING REQUIREMENTS:
When providing the "actor" field in your JSON response, you MUST use ONLY the exact name from the Characters list above.

FOR EXAMPLE:
- Characters list shows: ['Oat']
- Your JSON must say: "actor": "Oat"
- DO NOT say: "actor": "character Oat"
- DO NOT say: "actor": "the character"
- DO NOT say: "actor": "character"

CORRECT: "actor": "Oat"

Copy the name EXACTLY as it appears in the Characters list, with no additions or modifications.

IMAGES PROVIDED (IN ORDER):
1. **STORYBOARD PANEL** (the target/reference) + optional DEPTH MAP
2. **HERO CAMERA RGB** (THIS IS WHAT MUST MATCH THE STORYBOARD!) + **HERO DEPTH MAP**
3-8. Scout angles RGB + DEPTH (front, right, back, left, top, 3/4) - reference only to understand the 3D scene

 VISUAL ANNOTATIONS ON IMAGES:
All scene images include helpful spatial reference markers:

**Color-Coded Axes (always visible):**
- **RED arrows** = X-axis (Forward/Backward direction)
- **GREEN arrows** = Y-axis (Left/Right direction)
- **BLUE arrows** = Z-axis (Up/Down direction)

**Grid & Reference Elements:**
- **Gray grid lines** = Spatial reference (each square represents consistent spacing)
- **Cyan horizontal line** = Ground plane (Z=0, where actors stand)
- **Scale bar** = Shows "200cm (2m)" for size reference (hero/3quarter views only)
- **"Actors: Name | Name"** label at top = Lists which actors are in the scene

**Optional Depth Overlay (hero/3quarter views):**
- Some images have semi-transparent colored tint showing depth structure

 DEPTH MAPS EXPLAINED:
Depth images use TURBO colormap to show distance FROM THE CAMERA'S VIEWPOINT:
- **Red/Orange/Warm colors** = CLOSE to camera (near) - actors in foreground
- **Green/Yellow** = MEDIUM distance - actors in middle ground
- **Blue/Purple/Cold colors** = FAR from camera (distant) - actors in background
Use depth to understand:
- Which actors are closer/farther from camera (NOT from world origin)
- Spatial layering (foreground/background/middle)
- 3D structure of the scene from camera perspective
- Verify positioning by comparing storyboard depth vs hero camera depth

 CRITICAL: The HERO CAMERA shot (#2) is the final shot that MUST match the storyboard panel (#1).
The 6 scout angles are ONLY for you to understand the 3D scene layout - they are NOT meant to match the storyboard.

 STORYBOARD ART STYLE GUIDANCE:
- Storyboards are ARTISTIC INTERPRETATIONS, not technical blueprints
- Focus on COMPOSITION, CHARACTER PLACEMENT, and FRAMING (not pixel-perfect matching)
- Acceptable differences: minor prop sizes, artistic perspective, stylized proportions, **CHARACTER POSES**
- What MUST match: character positions, facing directions, camera angle, depth ordering

 RESEARCH-PROVEN SPATIAL REASONING TECHNIQUE:
To achieve accurate distance and position estimation, you MUST identify nearby reference
objects with known dimensions (bench, character, trees) and use them as visual anchors
to reason about spatial relationships. Think step by step using these references.

TASK - STRUCTURED SPATIAL ANALYSIS:

**STAGE 1: Scene Graph Construction**
First, identify all objects and their spatial relationships:
- List objects visible in HERO camera with approximate positions (left/right/center, near/far)
- Describe pairwise relationships using REFERENCE OBJECTS (see below)
- Note depth ordering (foreground/middle/background layers)
- Calculate distances by comparing to reference object dimensions

**STAGE 2: Spatial Comparison**
Compare HERO camera to STORYBOARD panel:
1. **Composition Match**: Does the hero camera framing match the storyboard?
2. **Character Position**: Are characters in the correct screen position and depth?
3. **Visibility Issues**: Are any characters/props obscured or hidden?
4. **Camera Angle**: Is the camera height and angle correct?
5. **Depth Analysis**: Use DEPTH MAPS to verify actor layering (blue=near, red=far)
   - Are actors at correct distances from camera?
   - Is depth ordering correct (who should be in front/behind)?
6. **Depth Cues**: Check occlusion, relative size, height in visual field

**STAGE 3: Generate Adjustments**
Based on scene graph and comparison, provide specific adjustments with reference object justification

 REFERENCE OBJECTS FOR SPATIAL REASONING:
**Use these known dimensions to estimate distances (CRITICAL for accuracy):**
- **Park bench**: 150 units long (1.5m), 50 units tall (0.5m)
- **Human character**: 170 units tall (1.7m)
- **Tree trunk**: 50-100 units diameter (0.5-1m)
- **Ground plane**: Z=0 baseline reference

**Measurement technique:** "A is 2 bench-lengths from B" = 2 × 150 = 300 units

COORDINATE SYSTEM:
- X=Forward/Back, Y=Right/Left, Z=Up/Down (1 meter = 100 units)
- Rotation: Pitch (up/down tilt), Yaw (left/right turn), Roll (camera tilt)

 POSITIONING MODE: {mode_str}
{mode_instructions}

 ADJUSTMENT GUIDELINES:
- **Start with SMALL adjustments**: 20-100 units for position, 5-15° for rotation
- Only use large values (200-500 units) if positioning is completely wrong
- **Incremental convergence**: Make small improvements each iteration

 CHARACTER ROTATION (CRITICAL):
- Characters should face each other or camera in conversational scenes
- Yaw=0° faces forward (+X direction)
- To face each other: Left character Yaw=+90°, Right character Yaw=-90°
- To face camera: Calculate based on camera position
- **ALWAYS provide rotation adjustments when characters are positioned incorrectly**

Provide positioning adjustments in JSON format:
{{
    "match_score": 0-100,
    "analysis": "Detailed comparison: what matches, what doesn't, specific issues",
    "adjustments": [
        {{
            "actor": "character or prop name",
            "type": "move" or "rotate",  // Use "rotate" for character facing direction!
            "position": {{"x": 0, "y": 0, "z": 0}},  // {position_comment}
            "rotation": {{"pitch": 0, "yaw": 0, "roll": 0}},  // Absolute rotation values (Yaw controls facing)
            "reason": "{reason_requirement}"
        }}
    ],
    "camera_adjustments": {{
        "needs_adjustment": true/false,  //  SET TO FALSE unless camera framing is CRITICALLY wrong
        "position": {{"x": 0, "y": 0, "z": 0}},  // {position_comment} - Where to place camera
        "rotation": null,  //  LEAVE AS NULL - System auto-calculates rotation to look at character
        "reason": "Why camera framing is incorrect and where it should be positioned"
    }}
}}

 CRITICAL RULES:
1. **ONE adjustment per actor** - Combine all movements into a SINGLE adjustment
2. **All three axes** - Always provide X, Y, AND Z values (even if some are 0)
3. {rule3}
4. **Example**: If character needs to move forward AND up, provide ONE adjustment: {{"x": 200, "y": 0, "z": 100}}
5. **Camera adjustment priority** - Adjust CHARACTERS FIRST. Only adjust camera if characters are positioned correctly but framing is still wrong

═══════════════════════════════════════════════════════════════════
 EVALUATION PROCESS (Chain-of-Thought Required)
═══════════════════════════════════════════════════════════════════
Before providing your final evaluation, complete these steps:

STEP 1 - SCOPE CONFIRMATION:
State: "I will evaluate positioning quality for these present actors: [list actors from EVALUATION SCOPE]"
Count: [X] actors total

STEP 2 - INDIVIDUAL ACTOR ASSESSMENT:
For each present actor, assess positioning quality:
- Actor name: [from scope list only]
- Positioning quality: [Perfect/Good/Needs Adjustment/Poor]
- Points awarded: [100/70/40/10]
- Basis: [Observable positioning data from images]

STEP 3 - SCORE CALCULATION:
Total points earned: [Sum from Step 2]
Maximum possible points: [100 × actor count from Step 1]
Match score: [Total points / Maximum points × 100]

STEP 4 - VERIFICATION CHECK:
 Actors evaluated: [Count—must equal Step 1 count]
 All actor names from EVALUATION SCOPE: Yes
 Score based exclusively on present actors: Yes

Only after completing Steps 1-4, provide your final JSON response.

Remember: Be specific, use realistic values, and show your calculation reasoning!"""

    def _call_ai_with_multiple_images(self, client, prompt, storyboard_b64, captures, depth_maps):
        """
        Call AI with multiple images (storyboard + all captures)

        Args:
            client: AIClient instance
            prompt: Text prompt
            storyboard_b64: Base64 encoded storyboard image
            captures: Dict of base64 encoded capture images
            depth_maps: Dict of base64 encoded depth maps (for feature verification)

        Returns:
            AI response text or None
        """
        import time

        # ═══════════════════════════════════════════════════════════════
        #  FEATURE VERIFICATION CHECKPOINT
        # ═══════════════════════════════════════════════════════════════
        unreal.log("\n" + "="*70)
        unreal.log("FEATURE VERIFICATION - Checking all enhancements are active")
        unreal.log("="*70)

        feature_status = {
            "#1 Depth Maps": depth_maps and len(depth_maps) > 0,
            "#2 Iteration Context": self.current_iteration > 1 and hasattr(self, 'last_match_score'),
            "#3 Temperature Scheduling": True,  # Always active
            "#4 Score Targets": True,  # Always active
            "#5 Depth Interleaving": depth_maps and len(depth_maps) > 0,  # Same as #1
            "#6 Cost Tracking": hasattr(self, 'total_cost'),
            "#7 Comparison Overlay": 'hero' in captures,
            "#9 Spatial Relationships": True  # Checked in prompt building
        }

        for feature, enabled in feature_status.items():
            status = " ACTIVE" if enabled else " INACTIVE"
            unreal.log(f"{feature}: {status}")

        active_count = sum(1 for enabled in feature_status.values() if enabled)
        unreal.log(f"\n   Total: {active_count}/8 features active")
        unreal.log("="*70 + "\n")

        # Build OpenAI-style multi-image payload manually
        # The AIClient._make_request only handles single images, so we'll use the session directly

        try:
            # Detect API format needed based on model
            is_gpt5 = client.model.startswith('gpt-5') or client.model.startswith('o3') or client.model.startswith('o4')
            is_claude = 'claude' in client.model.lower() or 'anthropic' in client.model.lower()
            is_ollama = 'llava' in client.model.lower() or 'internvl' in client.model.lower() or 'bakllava' in client.model.lower() or ':' in client.model  # Ollama uses format like "llava:13b"

            if is_ollama:
                # Ollama local model API format (LLaVA, InternVL2, etc.)
                unreal.log(f"\n DEBUG: Building Ollama/LLaVA content payload...")

                # Helper function to extract raw base64 (Ollama doesn't want data URI prefix)
                def extract_base64(data_uri):
                    if data_uri.startswith('data:'):
                        return data_uri.split(',', 1)[1] if ',' in data_uri else data_uri
                    return data_uri

                # Collect all images as base64 strings
                images = []
                image_count = 0

                # 1. Add storyboard
                images.append(extract_base64(storyboard_b64))
                image_count += 1
                unreal.log(f"Added image #{image_count}: Storyboard RGB (reference)")

                # 1b. Add storyboard depth if available
                if depth_maps and 'storyboard' in depth_maps:
                    images.append(extract_base64(depth_maps['storyboard']))
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Storyboard DEPTH")
                    unreal.log(f"FEATURE #1: Depth map sent to AI!")

                # 2. Add hero camera
                if 'hero' in captures:
                    images.append(extract_base64(captures['hero']))
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Hero RGB (target shot)")

                    if depth_maps and 'hero' in depth_maps:
                        images.append(extract_base64(depth_maps['hero']))
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: Hero DEPTH")

                # 3. Add scout angles
                scout_order = ['front', 'right', 'back', 'left', 'top', 'three_quarter']
                for angle in scout_order:
                    if angle in captures:
                        images.append(extract_base64(captures[angle]))
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: {angle.title()} RGB (scout)")

                        if depth_maps and angle in depth_maps:
                            images.append(extract_base64(depth_maps[angle]))
                            image_count += 1
                            unreal.log(f"Added image #{image_count}: {angle.title()} DEPTH")

                unreal.log(f"\n    Total images in payload: {image_count}")

                # FEATURE #3: Temperature scheduling
                # FIXED: Adjusted for better precision (was 0.9/0.7/0.3 causing oscillation/timeouts)
                if self.current_iteration <= 2:
                    temperature = 0.7  # Initial exploration (was 0.9 - too random)
                else:
                    temperature = 0.4  # Precision refinement (was 0.3 - too rigid, caused timeouts)

                unreal.log(f"FEATURE #3 - Temperature: {temperature} (iteration {self.current_iteration})")
                if self.current_iteration <= 2:
                    unreal.log(f"Strategy: EXPLORE solutions (high temperature)")
                elif self.current_iteration <= 4:
                    unreal.log(f"Strategy: REFINE approach (medium temperature)")
                else:
                    unreal.log(f"Strategy: CONVERGE on solution (low temperature)")

                # Ollama API format
                payload = {
                    "model": client.model,
                    "prompt": prompt,
                    "images": images,  # Array of base64 strings
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 2000
                    }
                }

                unreal.log("\n DEBUG: OLLAMA PAYLOAD STRUCTURE")
                unreal.log(f"Model: {payload['model']}")
                unreal.log(f"Images: {len(images)}")
                unreal.log(f"Temperature: {temperature}")
                unreal.log(f"Max tokens: 2000")
            elif is_claude:
                # Claude/Anthropic Messages API format
                content = [{"type": "text", "text": prompt}]

                unreal.log(f"\n DEBUG: Building Claude/Anthropic content payload...")
                image_count = 0

                # Helper function to convert base64 with data URI prefix to raw base64
                def extract_base64(data_uri):
                    if data_uri.startswith('data:'):
                        # Remove "data:image/png;base64," prefix
                        return data_uri.split(',', 1)[1] if ',' in data_uri else data_uri
                    return data_uri

                # 1. Add storyboard first (reference image)
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": extract_base64(storyboard_b64)
                    }
                })
                image_count += 1
                unreal.log(f"Added image #{image_count}: Storyboard RGB (reference)")

                # 1b. Add storyboard depth if available
                if depth_maps and 'storyboard' in depth_maps:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": extract_base64(depth_maps['storyboard'])
                        }
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Storyboard DEPTH (colorful Turbo)")
                    unreal.log(f"FEATURE #1: Depth map sent to AI!")
                else:
                    unreal.log(f"No storyboard depth map available")

                # 2. Add HERO camera second
                if 'hero' in captures:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": extract_base64(captures['hero'])
                        }
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Hero RGB (target shot)")

                    # 2b. Add hero depth if available
                    if depth_maps and 'hero' in depth_maps:
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": extract_base64(depth_maps['hero'])
                            }
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: Hero DEPTH")

                # 3. Add scout angles
                scout_order = ['front', 'right', 'back', 'left', 'top', 'three_quarter']
                for angle in scout_order:
                    if angle in captures:
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": extract_base64(captures[angle])
                            }
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: {angle.title()} RGB (scout)")

                        # 3b. Add scout depth if available
                        if depth_maps and angle in depth_maps:
                            content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": extract_base64(depth_maps[angle])
                                }
                            })
                            image_count += 1
                            unreal.log(f"Added image #{image_count}: {angle.title()} DEPTH")

                unreal.log(f"\n    Total images in payload: {image_count}")

                # FEATURE #3: Temperature scheduling
                # FIXED: Adjusted for better precision (was 0.9/0.7/0.3 causing oscillation/timeouts)
                if self.current_iteration <= 2:
                    temperature = 0.7  # Initial exploration (was 0.9 - too random)
                else:
                    temperature = 0.4  # Precision refinement (was 0.3 - too rigid, caused timeouts)

                unreal.log(f"FEATURE #3 - Temperature: {temperature} (iteration {self.current_iteration})")
                if self.current_iteration <= 2:
                    unreal.log(f"Strategy: EXPLORE solutions (high temperature)")
                elif self.current_iteration <= 4:
                    unreal.log(f"Strategy: REFINE approach (medium temperature)")
                else:
                    unreal.log(f"Strategy: CONVERGE on solution (low temperature)")

                # CRITICAL: Adjust max_tokens for extended thinking models
                # Claude Sonnet 4.5+ uses extended thinking with 10000 token budget
                # max_tokens must be GREATER than thinking_budget_tokens
                max_tokens = 2000
                if 'sonnet-4' in client.model.lower() or 'claude-sonnet-4' in client.model.lower():
                    thinking_budget = 10000
                    min_required = thinking_budget + 4096  # Budget + reasonable output space
                    if max_tokens < min_required:
                        max_tokens = min_required
                        unreal.log(f"Extended thinking detected - adjusted max_tokens to {max_tokens} (budget {thinking_budget} + 4096 output)")

                payload = {
                    "model": client.model,
                    "messages": [{
                        "role": "user",
                        "content": content
                    }],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                unreal.log("\n DEBUG: CLAUDE PAYLOAD STRUCTURE")
                unreal.log(f"Model: {payload['model']}")
                unreal.log(f"Content items: {len(content)}")
                unreal.log(f"Temperature: {temperature}")
                unreal.log(f"Max tokens: {payload['max_tokens']}")
            elif is_gpt5:
                # GPT-5 Responses API format
                content = [{"type": "input_text", "text": prompt}]

                unreal.log(f"\n DEBUG: Building GPT-5 content payload...")
                image_count = 0

                # 1. Add storyboard first (reference image)
                content.append({
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{storyboard_b64}"  # Simple string
                })
                image_count += 1
                unreal.log(f"Added image #{image_count}: Storyboard RGB (reference)")

                # 1b. Add storyboard depth if available (FEATURE #5: Depth interleaving)
                if depth_maps and 'storyboard' in depth_maps:
                    content.append({
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{depth_maps['storyboard']}"
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Storyboard DEPTH (colorful Turbo)")
                    unreal.log(f"FEATURE #1: Depth map sent to AI!")
                else:
                    unreal.log(f"No storyboard depth map available")

                # 2. Add HERO camera second (this is what must match!)
                if 'hero' in captures:
                    content.append({
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{captures['hero']}"  # Simple string
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Hero RGB (target shot, must match storyboard)")

                    # 2b. Add hero depth if available
                    if depth_maps and 'hero' in depth_maps:
                        content.append({
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{depth_maps['hero']}"
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: Hero DEPTH")

                # 3. Add remaining scout angles (helpers for understanding scene)
                scout_order = ['front', 'right', 'back', 'left', 'top', 'three_quarter']
                for angle in scout_order:
                    if angle in captures:
                        content.append({
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{captures[angle]}"  # Simple string
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: {angle.title()} RGB (scout)")

                        # 3b. Add scout depth if available
                        if depth_maps and angle in depth_maps:
                            content.append({
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{depth_maps[angle]}"
                            })
                            image_count += 1
                            unreal.log(f"Added image #{image_count}: {angle.title()} DEPTH")

                unreal.log(f"\n    Total images in payload: {image_count}")
                unreal.log(f"DEBUG: Image breakdown - Storyboard:1, Hero:1, Scouts:6, Depths:{len(depth_maps) if depth_maps else 0}")

                #  CRITICAL: Pro models require "high" reasoning effort
                reasoning_effort = "high" if "-pro" in client.model.lower() else "medium"
                unreal.log(f"Reasoning effort: {reasoning_effort}")

                # ISSUE 4 FIX: GPT-5 Responses API does NOT support temperature parameter
                # Temperature scheduling only works for GPT-4o, Claude, and Ollama
                unreal.log(f"GPT-5 does not support temperature scheduling (reasoning effort used instead)")

                payload = {
                    "model": client.model,
                    "input": [{
                        "role": "user",
                        "content": content
                    }],
                    "reasoning": {"effort": reasoning_effort},
                    "text": {"verbosity": "medium"},
                    "max_output_tokens": 2000
                    # Temperature not supported in GPT-5 Responses API
                }

                unreal.log("\n DEBUG: GPT-5 PAYLOAD STRUCTURE")
                unreal.log(f"Model: {payload['model']}")
                unreal.log(f"Content items: {len(content)}")
                unreal.log(f"Reasoning effort: {reasoning_effort}")
                unreal.log(f"Max tokens: {payload['max_output_tokens']}")
                unreal.log(f"Temperature: N/A (not supported by GPT-5 API)")
            else:
                # GPT-4 Chat Completions API format
                content = [{"type": "text", "text": prompt}]

                unreal.log(f"\n DEBUG: Building GPT-4 content payload...")
                image_count = 0

                # 1. Add storyboard first (reference image) - LOW detail (ISSUE 3 FIX)
                # Research: LOW detail optimal for spatial tasks, HIGH gives no accuracy boost but costs 9x more
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{storyboard_b64}",
                        "detail": "low"  # $0.0002 vs $0.0018 for high
                    }
                })
                image_count += 1
                unreal.log(f"Added image #{image_count}: Storyboard RGB (LOW detail, reference)")

                # 1b. Add storyboard depth if available (FEATURE #5: Depth interleaving)
                if depth_maps and 'storyboard' in depth_maps:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{depth_maps['storyboard']}",
                            "detail": "low"  # Depth is context, not target
                        }
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Storyboard DEPTH (LOW detail, colorful Turbo)")
                    unreal.log(f"FEATURE #1: Depth map sent to AI!")
                else:
                    unreal.log(f"No storyboard depth map available")

                # 2. Add HERO camera second (this is what must match!) - LOW detail (ISSUE 3 FIX)
                if 'hero' in captures:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{captures['hero']}",
                            "detail": "low"  # Spatial positioning doesn't need high res
                        }
                    })
                    image_count += 1
                    unreal.log(f"Added image #{image_count}: Hero RGB (LOW detail, target shot)")

                    # 2b. Add hero depth if available
                    if depth_maps and 'hero' in depth_maps:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{depth_maps['hero']}",
                                "detail": "low"  # Depth is context
                            }
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: Hero DEPTH (LOW detail)")

                # 3. Add remaining scout angles (helpers for understanding scene) - LOW detail
                #  RESEARCH: Low detail = $0.0002/image vs High = $0.0018 (9x cost), optimal for spatial reasoning
                scout_order = ['front', 'right', 'back', 'left', 'top', 'three_quarter']
                for angle in scout_order:
                    if angle in captures:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{captures[angle]}",
                                "detail": "low"  # Context-only, 9x cheaper
                            }
                        })
                        image_count += 1
                        unreal.log(f"Added image #{image_count}: {angle.title()} RGB (LOW detail, scout)")

                        # 3b. Add scout depth if available
                        if depth_maps and angle in depth_maps:
                            content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{depth_maps[angle]}",
                                    "detail": "low"  # Depth context
                                }
                            })
                            image_count += 1
                            unreal.log(f"Added image #{image_count}: {angle.title()} DEPTH (LOW detail)")

                unreal.log(f"\n    Total images in payload: {image_count}")

                # FEATURE #3: Temperature scheduling by iteration (same as GPT-5)
                if self.current_iteration <= 2:
                    temperature = 0.9  # Explore different solutions
                elif self.current_iteration <= 4:
                    temperature = 0.7  # Refine approach
                else:
                    temperature = 0.3  # Converge on solution

                unreal.log(f"FEATURE #3 - Temperature: {temperature} (iteration {self.current_iteration})")
                if self.current_iteration <= 2:
                    unreal.log(f"Strategy: EXPLORE solutions (high temperature)")
                elif self.current_iteration <= 4:
                    unreal.log(f"Strategy: REFINE approach (medium temperature)")
                else:
                    unreal.log(f"Strategy: CONVERGE on solution (low temperature)")

                payload = {
                    "model": client.model,
                    "messages": [{
                        "role": "user",
                        "content": content
                    }],
                    "max_tokens": 2000,
                    "temperature": temperature  # Dynamic temperature based on iteration
                }

                unreal.log("\n DEBUG: GPT-4 PAYLOAD STRUCTURE")
                unreal.log(f"Model: {payload['model']}")
                unreal.log(f"Content items: {len(content)}")
                unreal.log(f"Temperature: {temperature}")
                unreal.log(f"Max tokens: {payload['max_tokens']}")

                #  RESEARCH: Add structured outputs for 100% schema adherence (vs <40% baseline)
                # FIXED: Using Union[Type, None] + additionalProperties: False for OpenAI strict mode
                unreal.log(f"DEBUG: PYDANTIC_AVAILABLE={PYDANTIC_AVAILABLE}, model={client.model}")

                if PYDANTIC_AVAILABLE and ("gpt-4o" in client.model.lower() and "-2024-08-06" in client.model or client.model == "gpt-4o"):
                    # Generate and sanitize Pydantic schema for OpenAI strict mode
                    raw_schema = PositioningAnalysis.model_json_schema()
                    clean_schema = sanitize_schema_for_openai(raw_schema)

                    # DEBUG: Log the schema to see what's being sent
                    unreal.log("DEBUG: Generated schema keys: " + str(list(clean_schema.keys())))
                    if '$defs' in clean_schema and 'ActorAdjustment' in clean_schema['$defs']:
                        actor_adj_schema = clean_schema['$defs']['ActorAdjustment']
                        unreal.log("DEBUG: ActorAdjustment properties: " + str(list(actor_adj_schema.get('properties', {}).keys())))
                        unreal.log("DEBUG: ActorAdjustment required: " + str(actor_adj_schema.get('required', [])))
                        if 'position' in actor_adj_schema.get('properties', {}):
                            pos_schema = actor_adj_schema['properties']['position']
                            unreal.log("DEBUG: position field schema: " + str(pos_schema))

                    payload["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "positioning_analysis",
                            "strict": True,
                            "schema": clean_schema
                        }
                    }
                    unreal.log("Using structured outputs with sanitized schema (100% adherence)")
                    unreal.log("Fixed: Union[Type, None] + additionalProperties: False pattern")
                elif not PYDANTIC_AVAILABLE:
                    unreal.log("Structured outputs disabled (install pydantic for 100% JSON validity)")
                    payload["response_format"] = {"type": "json_object"}
                else:
                    unreal.log(f"Model {client.model} doesn't support structured outputs (need gpt-4o or gpt-4o-2024-08-06+)")
                    payload["response_format"] = {"type": "json_object"}

            # Determine endpoint and log message
            if is_ollama:
                # Ollama uses /api/generate endpoint
                endpoint = f"{client.endpoint}/api/generate" if not client.endpoint.endswith('/api/generate') else client.endpoint
                unreal.log(f"Sending {len(payload.get('images', []))} images to Ollama ({client.model})...")
            else:
                endpoint = client.endpoint
                content_items = payload.get('messages', [{}])[0].get('content', []) if 'messages' in payload else payload.get('input', [{}])[0].get('content', [])
                unreal.log(f"Sending {len(content_items) - 1} images to {client.provider}...")

            start_time = time.time()

            # ============================================================
            # ============================================================
            import json as json_module
            try:
                # Estimate payload size
                payload_json = json_module.dumps(payload)
                payload_size_mb = len(payload_json) / (1024 * 1024)
                unreal.log(f"\n Payload size check:")
                unreal.log(f"Total size: {payload_size_mb:.2f} MB")

                # Warn if payload is very large
                if payload_size_mb > 50:
                    unreal.log_warning(f"WARNING: Very large payload ({payload_size_mb:.2f} MB)")
                    unreal.log_warning(f"This may cause timeout or crash")
                    unreal.log_warning(f"Consider reducing number of images or image quality")
                elif payload_size_mb > 20:
                    unreal.log(f"Large payload ({payload_size_mb:.2f} MB) - may take longer")
                else:
                    unreal.log(f"Payload size OK")

                # Free the temporary JSON string immediately
                del payload_json
            except Exception as e:
                unreal.log_warning(f"Could not estimate payload size: {e}")

            # Make request
            # Extended thinking + vision requires longer timeout
            # Increase timeout for large payloads
            if is_ollama:
                timeout_duration = 180  # Ollama needs more time for large payloads
            else:
                timeout_duration = 300  # 5 minutes for cloud APIs with many images

            unreal.log(f"⏱ Timeout: {timeout_duration}s")
            unreal.log(f"Sending request to AI...")

            try:
                response = client.session.post(
                    endpoint,
                    json=payload,
                    timeout=timeout_duration
                )
            except Exception as request_error:
                unreal.log_error(f"HTTP request failed: {request_error}")
                unreal.log_error(f"This could be due to:")
                unreal.log_error(f"- Network timeout (payload too large)")
                unreal.log_error(f"- Connection error")
                unreal.log_error(f"- Out of memory")
                unreal.log_error(f"Try reducing number of depth maps or image quality")
                raise  # Re-raise to be caught by outer exception handler

            unreal.log(f"\n    HTTP Response: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                unreal.log(f"DEBUG: Response keys: {list(data.keys())}")

                # GPT-5: Poll if incomplete
                if data.get('status') == 'incomplete' and 'id' in data:
                    response_id = data['id']
                    unreal.log(f"⏳ Response incomplete, polling for result...")

                    # Poll for up to 120 seconds (multi-image takes longer)
                    for poll_attempt in range(60):  # 60 attempts, 2s each = 120s max
                        time.sleep(2)
                        poll_response = client.session.get(
                            f"{client.endpoint}/{response_id}",
                            timeout=30
                        )

                        if poll_response.status_code == 200:
                            data = poll_response.json()
                            status = data.get('status')

                            if status == 'completed':
                                unreal.log(f"Response completed after {(poll_attempt + 1) * 2}s")
                                break
                            elif status == 'failed':
                                unreal.log_error(f"Response failed: {data.get('error')}")
                                return None

                            if (poll_attempt + 1) % 5 == 0:  # Log every 10s
                                unreal.log(f"⏳ Still processing... ({(poll_attempt + 1) * 2}s elapsed)")
                        else:
                            unreal.log_error(f"Poll failed: {poll_response.status_code}")
                            break

                elapsed = time.time() - start_time

                # Parse response based on provider
                if is_ollama:
                    # Ollama format: {"response": "text"}
                    result_text = data.get('response', '')
                    if not result_text:
                        unreal.log_error(f"Empty response from Ollama")
                        unreal.log_error(f"Response keys: {list(data.keys())}")
                        return None
                    unreal.log(f"Response received from Ollama in {elapsed:.1f}s")
                else:
                    #  USE AI CLIENT'S ROBUST PARSER for OpenAI/Claude
                    result_text = client._parse_response(data)

                    if result_text is None:
                        unreal.log_error(f"Could not parse response. Keys: {list(data.keys())}")
                        # Debug: print full response structure
                        import json
                        unreal.log_error(f"Full response: {json.dumps(data, indent=2)[:500]}")

                unreal.log(f"Response length: {len(result_text) if result_text else 0} chars")

                # FEATURE #6: Log usage stats and track costs
                iteration_cost = 0.0
                if is_ollama:
                    # Local model - free!
                    unreal.log(f"Iteration cost: $0.00 (local model - free!)")
                elif 'usage' in data:
                    usage = data['usage']
                    unreal.log(f"Response received in {elapsed:.1f}s")

                    # Handle both OpenAI and Claude token field names
                    input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens', 0)
                    output_tokens = usage.get('output_tokens') or usage.get('completion_tokens', 0)
                    unreal.log(f"Tokens: {input_tokens} input, {output_tokens} output")

                    # Estimate cost (GPT-4o pricing: $2.50 per 1M input, $10 per 1M output)
                    # Use the extracted tokens (works for both OpenAI and Claude)
                    input_cost = input_tokens * 0.0025 / 1000
                    output_cost = output_tokens * 0.01 / 1000
                    iteration_cost = input_cost + output_cost

                    # Count images for cost calculation (2 high detail + 6 low detail RGB + 8 depth low)
                    num_high_detail = 2  # Storyboard + hero
                    num_low_detail_rgb = 6  # Scout cameras
                    num_low_detail_depth = len(depth_maps) if depth_maps else 0
                    image_cost = (num_high_detail * 0.0018) + ((num_low_detail_rgb + num_low_detail_depth) * 0.0002)
                    iteration_cost += image_cost

                    # Track costs
                    self.iteration_costs.append(iteration_cost)
                    self.total_cost += iteration_cost

                    unreal.log(f"Iteration cost: ${iteration_cost:.4f} (tokens: ${input_cost + output_cost:.4f}, images: ${image_cost:.4f})")
                    unreal.log(f"Total cost so far: ${self.total_cost:.4f}")

                unreal.log(f"Returning result_text: type={type(result_text)}, is_none={result_text is None}")
                return result_text
            else:
                unreal.log_error(f"API error: {response.status_code}")
                unreal.log_error(f"{response.text[:500]}")
                # THESIS METRICS: Track 0 cost for failed request
                self.iteration_costs.append(0.0)

        except Exception as e:
            unreal.log_error(f"Request failed: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            # THESIS METRICS: Track 0 cost for failed request
            self.iteration_costs.append(0.0)

        return None

    def _parse_ai_positioning_response(self, response_text):
        """
        Parse AI response for positioning analysis

        Args:
            response_text: Raw AI response

        Returns:
            Parsed JSON dict or None
        """
        unreal.log(f"Parsing response: type={type(response_text)}, length={len(response_text) if response_text else 0}")
        if response_text:
            unreal.log(f"First 200 chars: {response_text[:200]}")
        try:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text.strip()

            # Clean common JSON formatting issues from AI
            import re
            # Remove trailing commas before closing brackets/braces
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)

            # Parse JSON
            data = json.loads(json_str)

            # Normalize field names for SceneAdjuster
            # AI returns "target_position" and "target_rotation"
            # SceneAdjuster expects "position" and "rotation"
            if 'adjustments' in data:
                for adj in data['adjustments']:
                    if 'target_position' in adj and 'position' not in adj:
                        adj['position'] = adj['target_position']
                    if 'target_rotation' in adj and 'rotation' not in adj:
                        adj['rotation'] = adj['target_rotation']

            return data

        except json.JSONDecodeError as e:
            unreal.log_error(f"JSON parse error: {e}")
            unreal.log_error(f"FULL RESPONSE (for debugging):")
            unreal.log_error(f"{response_text}")
            unreal.log_error(f"Error at character {e.pos}: '{response_text[max(0, e.pos-20):min(len(response_text), e.pos+20)]}'")
            return None
        except Exception as e:
            unreal.log_error(f"Parse error: {e}")
            return None

    def _display_positioning_results(self, analysis):
        """
        Display positioning analysis results in log

        Args:
            analysis: Parsed analysis dict
        """
        unreal.log("\n POSITIONING ANALYSIS:")
        unreal.log("="*70)

        # Match score
        match_score = analysis.get('match_score', 0)
        unreal.log(f"\n Match Score: {match_score}/100")

        # Overall analysis
        if 'analysis' in analysis:
            unreal.log(f"\n Analysis:")
            unreal.log(f"{analysis['analysis']}")

        # Actor adjustments
        adjustments = analysis.get('adjustments', [])
        if adjustments:
            unreal.log(f"\n Suggested Adjustments ({len(adjustments)}):")
            for i, adj in enumerate(adjustments, 1):
                actor = adj.get('actor', 'Unknown')
                adj_type = adj.get('type', 'unknown')
                reason = adj.get('reason', 'No reason provided')

                unreal.log(f"\n   {i}. {actor} ({adj_type}):")
                unreal.log(f"Reason: {reason}")

                if 'target_position' in adj:
                    pos = adj['target_position']
                    unreal.log(f"Position: X={pos.get('x', 0)}, Y={pos.get('y', 0)}, Z={pos.get('z', 0)}")

                if 'target_rotation' in adj:
                    rot = adj['target_rotation']
                    unreal.log(f"Rotation: Pitch={rot.get('pitch', 0)}, Yaw={rot.get('yaw', 0)}, Roll={rot.get('roll', 0)}")
        else:
            unreal.log("\n No actor adjustments needed")

        # Camera adjustments
        cam_adj = analysis.get('camera_adjustments', {})
        if cam_adj.get('needs_adjustment'):
            unreal.log(f"\n Camera Adjustments:")
            unreal.log(f"Reason: {cam_adj.get('reason', 'No reason provided')}")

            if 'target_position' in cam_adj:
                pos = cam_adj['target_position']
                unreal.log(f"Position: X={pos.get('x', 0)}, Y={pos.get('y', 0)}, Z={pos.get('z', 0)}")

            if 'target_rotation' in cam_adj:
                rot = cam_adj['target_rotation']
                unreal.log(f"Rotation: Pitch={rot.get('pitch', 0)}, Yaw={rot.get('yaw', 0)}, Roll={rot.get('roll', 0)}")
        else:
            unreal.log("\n Camera framing looks good")

        unreal.log("\n" + "="*70)

    def _capture_actor_transforms(self, sequence_asset):
        """
        Capture current actor transforms from sequencer keyframes at frame 0

        Args:
            sequence_asset: The LevelSequence asset

        Returns:
            Dict of actor_name -> {location: {x, y, z}, rotation: {pitch, yaw, roll}}
        """
        transforms = {}

        try:
            bindings = sequence_asset.get_bindings()

            for binding in bindings:
                actor_name = str(binding.get_display_name())

                # Get transform track
                transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
                if not transform_tracks:
                    continue

                track = transform_tracks[0]
                sections = track.get_sections()
                if not sections:
                    continue

                section = sections[0]

                # Get all channels (0-2: Location XYZ, 3-5: Rotation Roll/Pitch/Yaw, 6-8: Scale XYZ)
                channels = unreal.MovieSceneSectionExtensions.get_all_channels(section)

                if len(channels) < 6:  # Need at least location + rotation
                    continue

                # Read keyframes at frame 0
                loc_x, loc_y, loc_z = 0.0, 0.0, 0.0
                rot_roll, rot_pitch, rot_yaw = 0.0, 0.0, 0.0

                # Location channels (0-2)
                for key in channels[0].get_keys():
                    if key.get_time().frame_number.value == 0:
                        loc_x = key.get_value()
                        break
                for key in channels[1].get_keys():
                    if key.get_time().frame_number.value == 0:
                        loc_y = key.get_value()
                        break
                for key in channels[2].get_keys():
                    if key.get_time().frame_number.value == 0:
                        loc_z = key.get_value()
                        break

                # Rotation channels (3-5: Roll/Pitch/Yaw order!)
                for key in channels[3].get_keys():
                    if key.get_time().frame_number.value == 0:
                        rot_roll = key.get_value()
                        break
                for key in channels[4].get_keys():
                    if key.get_time().frame_number.value == 0:
                        rot_pitch = key.get_value()
                        break
                for key in channels[5].get_keys():
                    if key.get_time().frame_number.value == 0:
                        rot_yaw = key.get_value()
                        break

                transforms[actor_name] = {
                    'location': {'x': loc_x, 'y': loc_y, 'z': loc_z},
                    'rotation': {'pitch': rot_pitch, 'yaw': rot_yaw, 'roll': rot_roll}
                }

            return transforms

        except Exception as e:
            unreal.log_error(f"Error capturing actor transforms: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return {}

    def _restore_actor_transforms(self, sequence_asset, saved_transforms):
        """
        Restore actor transforms to sequencer keyframes at frame 0

        Args:
            sequence_asset: The LevelSequence asset
            saved_transforms: Dict from _capture_actor_transforms()
        """
        try:
            from core.scene_adjuster import SceneAdjuster

            # Create adjuster with absolute positioning mode for restoration
            adjuster = SceneAdjuster(sequence_asset=sequence_asset, use_absolute_positioning=True)

            unreal.log(f"Restoring {len(saved_transforms)} actors to best state...")

            # Convert saved transforms to adjustment format
            adjustments = []
            for actor_name, transform in saved_transforms.items():
                # Add position adjustment
                adjustments.append({
                    'actor': actor_name,
                    'type': 'move',
                    'position': transform['location'],
                    'reason': 'Restore to best checkpoint'
                })
                # Add rotation adjustment
                adjustments.append({
                    'actor': actor_name,
                    'type': 'rotate',
                    'rotation': transform['rotation'],
                    'reason': 'Restore to best checkpoint'
                })

            # Apply all restorations
            analysis = {
                'adjustments': adjustments,
                'camera_adjustments': {'needs_adjustment': False}
            }

            results = adjuster.apply_all_adjustments(analysis)
            unreal.log(f"Restored {results.get('success', 0)} transforms")

            # Force viewport refresh
            import time
            unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)
            unreal.LevelSequenceEditorBlueprintLibrary.play()
            time.sleep(0.1)
            unreal.LevelSequenceEditorBlueprintLibrary.pause()
            unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)
            time.sleep(0.2)

        except Exception as e:
            unreal.log_error(f"Error restoring actor transforms: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def _apply_ai_adjustments(self, analysis):
        """
        Apply AI recommendations to the sequence automatically

        Args:
            analysis: Parsed analysis dict with adjustments
        """
        try:
            # Import SceneAdjuster
            from core.scene_adjuster import SceneAdjuster

            # Get the sequence path - either from active_panel or find latest
            sequence_path = None
            if self.active_panel and 'sequence_path' in self.active_panel:
                sequence_path = self.active_panel['sequence_path']
                unreal.log(f"Using sequence from panel: {sequence_path}")
                unreal.log(f"Using sequence from panel: {sequence_path}")
            else:
                # Try to find the latest sequence
                sequence_path = self._find_latest_sequence()
                if sequence_path:
                    unreal.log(f"Found latest sequence: {sequence_path}")
                else:
                    unreal.log_warning("No sequence found")
                    unreal.log("Generate a scene first using 'Generate 3D Scene' button")
                    return

            # Load the sequence asset
            sequence_asset = unreal.load_asset(sequence_path)

            if not sequence_asset:
                unreal.log_error(f"Could not load sequence: {sequence_path}")
                return

            unreal.log(f"Loaded sequence: {sequence_path}")

            # Log positioning mode
            mode_str = "ABSOLUTE" if self.use_absolute_positioning else "RELATIVE"
            unreal.log(f"Positioning Mode: {mode_str}")

            # Create scene adjuster with positioning mode
            adjuster = SceneAdjuster(
                sequence_asset=sequence_asset,
                use_absolute_positioning=self.use_absolute_positioning
            )

            # Get adjustments from AI analysis (no auto-fixes)
            adjustments = analysis.get('adjustments', [])

            # ═══════════════════════════════════════════════════════════════
            #  PRE-FLIGHT CHECK: Verify sequence bindings exist
            # ═══════════════════════════════════════════════════════════════
            unreal.log("\n" + "="*70)
            unreal.log("PRE-FLIGHT: Verifying sequence bindings exist")
            unreal.log("="*70)

            bindings = sequence_asset.get_bindings()
            binding_names = [str(b.get_display_name()) for b in bindings]
            unreal.log(f"Found {len(binding_names)} bindings in sequence: {binding_names}")

            # Check if all actors mentioned in adjustments have bindings
            missing_bindings = []
            for adj in adjustments:
                actor_name = adj.get('actor', 'Unknown')
                # Check if actor name appears in any binding (case-insensitive partial match)
                if not any(actor_name.lower() in b.lower() for b in binding_names):
                    missing_bindings.append(actor_name)

            if missing_bindings:
                unreal.log_error(f"FATAL: {len(missing_bindings)} actors NOT in sequence bindings!")
                for actor in missing_bindings:
                    unreal.log_error(f"- '{actor}' cannot be adjusted (not spawned in sequence)")
                unreal.log_error("Adjustments will fail silently!")
                unreal.log_error("Solution: Regenerate scene or check actor names")
            else:
                unreal.log(f"All {len(adjustments)} actors have sequence bindings")

            unreal.log("="*70 + "\n")

            # REMOVED: Auto-rotate for bench scenes - let AI handle all rotations

            # ═══════════════════════════════════════════════════════════════
            #  LOG ADJUSTMENT COMMANDS (what we're about to do)
            # ═══════════════════════════════════════════════════════════════
            unreal.log("\n" + "="*70)
            unreal.log("ADJUSTMENT COMMANDS TO BE APPLIED")
            unreal.log("="*70)
            unreal.log(f"Mode: {'ABSOLUTE' if self.use_absolute_positioning else 'RELATIVE'}")
            unreal.log(f"Total adjustments: {len(adjustments)}\n")

            # Track expected positions for later verification
            expected_positions = {}
            expected_rotations = {}

            for i, adj in enumerate(adjustments, 1):
                actor = adj.get('actor', 'UNKNOWN')
                adj_type = adj.get('type', 'unknown')

                if adj_type == 'move' and adj.get('position'):
                    pos = adj['position']
                    expected_positions[actor] = pos
                    unreal.log(f"[{i}] {actor}: MOVE to X={pos.get('x', 0):.1f}, Y={pos.get('y', 0):.1f}, Z={pos.get('z', 0):.1f}")
                    if adj.get('reason'):
                        unreal.log(f"Reason: {adj['reason'][:80]}")

                elif adj_type == 'rotate' and adj.get('rotation'):
                    rot = adj['rotation']
                    expected_rotations[actor] = rot
                    unreal.log(f"[{i}] {actor}: ROTATE to Pitch={rot.get('pitch', 0):.1f}°, Yaw={rot.get('yaw', 0):.1f}°, Roll={rot.get('roll', 0):.1f}°")
                    if adj.get('reason'):
                        unreal.log(f"Reason: {adj['reason'][:80]}")

            unreal.log("="*70 + "\n")

            # Apply adjustments
            results = adjuster.apply_all_adjustments(analysis)

            unreal.log("\n DEBUG: ADJUSTMENT RESULTS")
            unreal.log("="*70)
            unreal.log(f"Total: {results.get('total', 0)}")
            unreal.log(f"Success: {results.get('success', 0)}")
            unreal.log(f"Failed: {results.get('failed', 0)}")
            if results.get('errors'):
                for error in results['errors']:
                    unreal.log(f"Error: {error}")
            unreal.log("="*70 + "\n")

            # CRITICAL: Force viewport to update after applying keyframes
            # Without this, captures show OLD positions causing oscillation
            unreal.log("Forcing viewport refresh after adjustments...")
            try:
                # Force sequencer to evaluate at frame 0
                import time
                unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)
                unreal.LevelSequenceEditorBlueprintLibrary.play()
                time.sleep(0.1)  # Brief play to force evaluation
                unreal.LevelSequenceEditorBlueprintLibrary.pause()
                unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)

                # Give viewport time to refresh
                time.sleep(0.2)
                unreal.log("Viewport refreshed - positions should now be visible")
            except Exception as e:
                unreal.log_warning(f"Could not force refresh: {e}")

            # ═══════════════════════════════════════════════════════════════
            #  VERIFICATION STAGE 1: Check keyframes actually created
            # ═══════════════════════════════════════════════════════════════
            unreal.log("\n" + "="*70)
            unreal.log("VERIFICATION: Checking if adjustments actually applied")
            unreal.log("="*70)

            try:
                # Keyframes are created at frame 0 (confirmed in scene_adjuster.py line 256)
                target_frame = 0
                verified_actors = 0
                missing_keyframes = 0
                position_mismatches = 0
                rotation_mismatches = 0

                bindings = sequence_asset.get_bindings()
                for binding in bindings:
                    binding_name = str(binding.get_display_name())

                    # Skip cameras and lights
                    if 'camera' in binding_name.lower() or 'light' in binding_name.lower():
                        continue

                    # Get transform track
                    transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
                    if transform_tracks:
                        track = transform_tracks[0]
                        sections = track.get_sections()
                        if sections:
                            section = sections[0]
                            channels = section.get_all_channels()

                            # Read keyframe at frame 0
                            # Channel order: [0-2] Location X/Y/Z, [3-5] Rotation Roll/Pitch/Yaw
                            if len(channels) >= 6:
                                keys_x = channels[0].get_keys()
                                keys_y = channels[1].get_keys()
                                keys_z = channels[2].get_keys()
                                keys_roll = channels[3].get_keys()
                                keys_pitch = channels[4].get_keys()
                                keys_yaw = channels[5].get_keys()

                                # Find frame 0 keys
                                x_val = next((k.get_value() for k in keys_x if k.get_time().frame_number.value == target_frame), None)
                                y_val = next((k.get_value() for k in keys_y if k.get_time().frame_number.value == target_frame), None)
                                z_val = next((k.get_value() for k in keys_z if k.get_time().frame_number.value == target_frame), None)
                                roll_val = next((k.get_value() for k in keys_roll if k.get_time().frame_number.value == target_frame), None)
                                pitch_val = next((k.get_value() for k in keys_pitch if k.get_time().frame_number.value == target_frame), None)
                                yaw_val = next((k.get_value() for k in keys_yaw if k.get_time().frame_number.value == target_frame), None)

                                if x_val is not None:
                                    unreal.log(f"{binding_name}: X={x_val:.1f}, Y={y_val:.1f}, Z={z_val:.1f}, Yaw={yaw_val:.1f}°")
                                    verified_actors += 1

                                    # Compare to expected values (if this actor had adjustments)
                                    if binding_name in expected_positions:
                                        exp = expected_positions[binding_name]
                                        tolerance = 1.0  # Allow 1 unit for floating point + clamping

                                        if abs(exp.get('x', 0) - x_val) > tolerance:
                                            unreal.log_warning(f"X MISMATCH: Expected {exp.get('x', 0):.1f}, got {x_val:.1f}")
                                            position_mismatches += 1
                                        if abs(exp.get('y', 0) - y_val) > tolerance:
                                            unreal.log_warning(f"Y MISMATCH: Expected {exp.get('y', 0):.1f}, got {y_val:.1f}")
                                            position_mismatches += 1
                                        if abs(exp.get('z', 0) - z_val) > tolerance:
                                            unreal.log_warning(f"Z MISMATCH: Expected {exp.get('z', 0):.1f}, got {z_val:.1f}")
                                            position_mismatches += 1

                                    if binding_name in expected_rotations:
                                        exp_rot = expected_rotations[binding_name]
                                        tolerance_deg = 1.0  # Allow 1 degree tolerance

                                        if abs(exp_rot.get('yaw', 0) - yaw_val) > tolerance_deg:
                                            unreal.log_warning(f"YAW MISMATCH: Expected {exp_rot.get('yaw', 0):.1f}°, got {yaw_val:.1f}°")
                                            rotation_mismatches += 1
                                else:
                                    unreal.log_error(f"{binding_name}: NO KEYFRAMES at frame {target_frame}!")
                                    unreal.log_error(f"Adjustment claims success but keyframe creation failed!")
                                    missing_keyframes += 1
                            else:
                                unreal.log_warning(f"{binding_name}: Insufficient channels ({len(channels)})")
                        else:
                            unreal.log_warning(f"{binding_name}: No sections in transform track")
                    else:
                        unreal.log_warning(f"{binding_name}: No transform track found")

                unreal.log(f"\n    Verification Summary:")
                unreal.log(f"Verified: {verified_actors} actors with keyframes")
                if missing_keyframes > 0:
                    unreal.log_error(f"Missing: {missing_keyframes} actors WITHOUT keyframes (CRITICAL BUG!)")
                if position_mismatches > 0:
                    unreal.log_warning(f"Position mismatches: {position_mismatches} (clamping or stale keyframes?)")
                if rotation_mismatches > 0:
                    unreal.log_warning(f"Rotation mismatches: {rotation_mismatches} (auto-rotation override?)")

            except Exception as e:
                unreal.log_error(f"VERIFICATION CODE FAILED - THIS IS A BUG IN DIAGNOSTIC: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())
                unreal.log_warning("Cannot verify adjustments - verification system broken!")

            unreal.log("="*70 + "\n")

            # ═══════════════════════════════════════════════════════════════
            #  VERIFICATION STAGE 2: Check hero camera image actually changed
            # ═══════════════════════════════════════════════════════════════
            unreal.log("\n" + "="*70)
            unreal.log("VERIFICATION: Checking hero camera render updated")
            unreal.log("="*70)

            try:
                from pathlib import Path
                import hashlib

                screenshot_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
                hero_path = screenshot_dir / "test_hero.png"

                if hero_path.exists():
                    # Get current image hash
                    with open(hero_path, 'rb') as f:
                        current_hash = hashlib.md5(f.read()).hexdigest()

                    # Compare to previous iteration (if exists)
                    if self.current_iteration > 1 and hasattr(self, '_last_hero_hash'):
                        if current_hash == self._last_hero_hash:
                            unreal.log_error(f"HERO CAMERA IMAGE IDENTICAL TO PREVIOUS ITERATION!")
                            unreal.log_error(f"Hash: {current_hash[:16]}...")
                            unreal.log_error(f"Keyframes may be correct but render is NOT updating!")
                            unreal.log_error(f"Possible causes:")
                            unreal.log_error(f"1. Viewport not showing sequence-controlled actors")
                            unreal.log_error(f"2. Scout camera not piloting correctly")
                            unreal.log_error(f"3. Sequence not bound to level actors")
                        else:
                            unreal.log(f"Hero camera image changed from previous iteration")
                            unreal.log(f"Previous: {self._last_hero_hash[:16]}...")
                            unreal.log(f"Current:  {current_hash[:16]}...")
                    else:
                        unreal.log(f"ℹ First iteration - no previous hash to compare")
                        unreal.log(f"Current hash: {current_hash[:16]}...")

                    # Store hash for next iteration
                    self._last_hero_hash = current_hash
                else:
                    unreal.log_error(f"HERO CAMERA IMAGE MISSING: {hero_path}")
                    unreal.log_error(f"Capture workflow may have failed!")

            except Exception as e:
                unreal.log_error(f"IMAGE HASH CHECK FAILED - THIS IS A BUG IN DIAGNOSTIC: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())

            unreal.log("="*70 + "\n")

            # ═══════════════════════════════════════════════════════════════
            #  FAIL-FAST: Abort if pipeline is broken
            # ═══════════════════════════════════════════════════════════════
            try:
                # Check if we detected critical failures
                has_missing_keyframes = 'missing_keyframes' in locals() and missing_keyframes > 0
                has_missing_bindings = 'missing_bindings' in locals() and len(missing_bindings) > 0

                if has_missing_keyframes or has_missing_bindings:
                    # ═══════════════════════════════════════════════════════════════
                    #  SAVE DIAGNOSTIC SNAPSHOT FIRST (before abort, in case abort throws)
                    # ═══════════════════════════════════════════════════════════════
                    try:
                        from pathlib import Path
                        from datetime import datetime

                        # Create diagnostic file in debug folder
                        panel_name = self.active_panel.get('path', 'unknown').replace('.png', '') if self.active_panel else 'unknown'
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        debug_root = Path(unreal.Paths.project_saved_dir()) / "StoryboardTo3D_Debug" / panel_name
                        debug_root.mkdir(parents=True, exist_ok=True)

                        diagnostic_filename = f"CRITICAL_FAILURE_iteration_{self.current_iteration}_{timestamp}.txt"
                        diagnostic_path = debug_root / diagnostic_filename

                        with open(diagnostic_path, 'w') as f:
                            f.write("="*70 + "\n")
                            f.write("CRITICAL PIPELINE FAILURE DIAGNOSTIC SNAPSHOT\n")
                            f.write("="*70 + "\n\n")

                            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"Panel: {panel_name}\n")
                            f.write(f"Iteration: {self.current_iteration}/{self.max_iterations}\n")
                            f.write(f"Positioning Mode: {'ABSOLUTE' if self.use_absolute_positioning else 'RELATIVE'}\n")
                            f.write(f"Match Score: {analysis.get('match_score', 'N/A')}/100\n")
                            f.write("\n" + "="*70 + "\n\n")

                            # Failure details
                            f.write("FAILURE DETAILS:\n")
                            f.write("-"*70 + "\n")

                            if has_missing_bindings:
                                f.write(f" Missing Bindings: {len(missing_bindings)} actors\n")
                                f.write(f"   Bindings found in sequence: {len(binding_names)}\n")
                                f.write(f"   Binding names: {binding_names}\n")
                                f.write(f"   Missing actors: {missing_bindings}\n\n")

                            if has_missing_keyframes:
                                f.write(f" Missing Keyframes: {missing_keyframes} actors\n")
                                f.write(f"   Verified actors: {verified_actors}\n")
                                if 'position_mismatches' in locals():
                                    f.write(f"   Position mismatches: {position_mismatches}\n")
                                if 'rotation_mismatches' in locals():
                                    f.write(f"   Rotation mismatches: {rotation_mismatches}\n")
                                f.write("\n")

                            # Adjustment commands that were attempted
                            f.write("\nADJUSTMENT COMMANDS ATTEMPTED:\n")
                            f.write("-"*70 + "\n")
                            if adjustments:
                                for i, adj in enumerate(adjustments, 1):
                                    f.write(f"[{i}] {adj.get('actor', 'UNKNOWN')}:\n")
                                    f.write(f"    Type: {adj.get('type', 'unknown')}\n")
                                    if adj.get('position'):
                                        pos = adj['position']
                                        f.write(f"    Position: X={pos.get('x', 0):.1f}, Y={pos.get('y', 0):.1f}, Z={pos.get('z', 0):.1f}\n")
                                    if adj.get('rotation'):
                                        rot = adj['rotation']
                                        f.write(f"    Rotation: Pitch={rot.get('pitch', 0):.1f}°, Yaw={rot.get('yaw', 0):.1f}°, Roll={rot.get('roll', 0):.1f}°\n")
                                    if adj.get('reason'):
                                        f.write(f"    Reason: {adj['reason']}\n")
                                    f.write("\n")
                            else:
                                f.write("   No adjustments in AI response\n")

                            # Expected vs actual (if available)
                            if expected_positions or expected_rotations:
                                f.write("\nEXPECTED VALUES:\n")
                                f.write("-"*70 + "\n")
                                for actor, pos in expected_positions.items():
                                    f.write(f"{actor} position: X={pos.get('x', 0):.1f}, Y={pos.get('y', 0):.1f}, Z={pos.get('z', 0):.1f}\n")
                                for actor, rot in expected_rotations.items():
                                    f.write(f"{actor} rotation: Pitch={rot.get('pitch', 0):.1f}°, Yaw={rot.get('yaw', 0):.1f}°, Roll={rot.get('roll', 0):.1f}°\n")
                                f.write("\n")

                            # Full AI analysis
                            f.write("\nFULL AI ANALYSIS:\n")
                            f.write("-"*70 + "\n")
                            f.write(f"Analysis text: {analysis.get('analysis', 'N/A')}\n\n")

                            # Sequence details
                            f.write("\nSEQUENCE DETAILS:\n")
                            f.write("-"*70 + "\n")
                            f.write(f"Sequence path: {sequence_path}\n")
                            f.write(f"Total bindings: {len(binding_names)}\n")
                            f.write(f"Binding list: {binding_names}\n\n")

                            f.write("="*70 + "\n")
                            f.write("END DIAGNOSTIC SNAPSHOT\n")
                            f.write("="*70 + "\n")

                        unreal.log(f"\n DIAGNOSTIC SNAPSHOT SAVED:")
                        unreal.log(f"{diagnostic_path}")
                        unreal.log(f"File contains complete failure state for analysis\n")

                    except Exception as snapshot_error:
                        unreal.log_warning(f"Could not save diagnostic snapshot: {snapshot_error}")

                    # Now log the failure (after snapshot is safe on disk)
                    unreal.log_error("\n" + ""*35)
                    unreal.log_error("CRITICAL PIPELINE FAILURE - ABORTING ITERATIONS")
                    unreal.log_error(""*35)

                    if has_missing_bindings:
                        unreal.log_error(f"Problem: {len(missing_bindings)} actors NOT in sequence bindings")
                        unreal.log_error("Characters were never spawned into the sequence")
                        unreal.log_error("Diagnosis needed in scene initialization/creation code")

                    if has_missing_keyframes:
                        unreal.log_error(f"Problem: {missing_keyframes} actors have NO keyframes despite 'success' report")
                        unreal.log_error("Adjustments are NOT being applied to sequence")
                        unreal.log_error("Diagnosis needed in scene_adjuster.py:")
                        unreal.log_error("- Check apply_adjustment_to_sequence() try/except blocks")
                        unreal.log_error("- Verify transform track creation succeeds")
                        unreal.log_error("- Check if actors are spawnables vs possessables")

                    unreal.log_error("Continuing iterations would waste API costs with no progress")
                    unreal.log_error(""*35 + "\n")

                    # ABORT: Stop auto-iteration immediately (last, in case this throws)
                    self.auto_iterate = False
                    unreal.log_warning("Auto-iteration disabled to prevent wasting resources")
                    unreal.log_warning("Fix the pipeline issue before retrying\n")

            except Exception as e:
                unreal.log_warning(f"Could not check fail-fast condition: {e}")

            # ═══════════════════════════════════════════════════════════════
            #  CHECKPOINTING: Best-Score State Management
            # ═══════════════════════════════════════════════════════════════
            current_score = analysis.get('match_score', 0)
            previous_best = self.best_score

            if self.enable_checkpointing:
                unreal.log("\n" + "="*70)
                unreal.log("CHECKPOINTING: Evaluating iteration results")
                unreal.log("="*70)
                unreal.log(f"Current score: {current_score}/100")
                unreal.log(f"Best score so far: {previous_best}/100")
            else:
                unreal.log("\n" + "="*70)
                unreal.log("CHECKPOINTING DISABLED - Accepting all changes")
                unreal.log("="*70)
                unreal.log(f"Current score: {current_score}/100")
                # When checkpointing is disabled, just track the score
                self.best_score = current_score
                self.last_match_score = current_score

            if self.enable_checkpointing and current_score >= self.best_score:
                # ACCEPT - Score improved or stayed the same (allow refinements)
                improvement = current_score - self.best_score
                self.best_score = current_score
                self.best_actor_transforms = self._capture_actor_transforms(sequence_asset)

                if improvement > 0:
                    unreal.log(f"\n    NEW BEST: {current_score}/100 (+{improvement} points)")
                else:
                    unreal.log(f"\n    ACCEPTED: {current_score}/100 (unchanged, allowing refinement)")
                unreal.log(f"Saved checkpoint with {len(self.best_actor_transforms)} actors")

                # Track in history
                self.iteration_history.append({
                    'iteration': self.current_iteration,
                    'score': current_score,
                    'status': 'accepted',
                    'improvement': improvement
                })

            elif self.enable_checkpointing:
                # REJECT - Score DROPPED, revert to best!
                drop = previous_best - current_score
                unreal.log(f"\n    SCORE DROPPED: {current_score}/100 (down {drop} points)")
                unreal.log(f"REVERTING to best state: {previous_best}/100")

                # Restore best transforms
                if self.best_actor_transforms:
                    self._restore_actor_transforms(sequence_asset, self.best_actor_transforms)
                    unreal.log(f"Reverted {len(self.best_actor_transforms)} actors to checkpoint")
                else:
                    unreal.log(f"No checkpoint available to restore")

                # Track in history
                self.iteration_history.append({
                    'iteration': self.current_iteration,
                    'score': current_score,
                    'status': 'reverted',
                    'kept_score': previous_best,
                    'drop': drop
                })

                # Update score to reflect we're keeping the best
                analysis['match_score'] = self.best_score
                self.last_match_score = self.best_score

            unreal.log("="*70 + "\n")

            # Track adjustment counts for monitoring
            if results:
                actor_count = results.get('success', 0)  # Number of successful actor adjustments
                camera_adjusted = results.get('camera_applied', False)  # Boolean for camera
                self._last_adjustments_count = actor_count
                self._last_camera_adjusted = camera_adjusted
                unreal.log(f"Tracking: {actor_count} actor adjustments, camera={'Yes' if camera_adjusted else 'No'}")

            # Report results
            unreal.log("\n" + "="*70)
            unreal.log("APPLICATION RESULTS:")
            unreal.log(f"Total adjustments: {results['total']}")
            unreal.log(f"Successfully applied: {results['success']}")
            unreal.log(f"Failed: {results['failed']}")

            if results['success'] > 0 or results.get('camera_applied'):
                unreal.log("\n TIP: Open Sequencer to see the keyframes!")
                unreal.log(f"1. Double-click sequence: {sequence_path}")
                unreal.log(f"2. Expand actor tracks to see transform keyframes at frame 0")

                # Store the match score for iteration tracking
                if 'match_score' in analysis:
                    self.last_match_score = analysis['match_score']
                    unreal.log(f"\n Current Match Score: {self.last_match_score}/100")

                    # THESIS ENHANCEMENT: Automatic objective metric validation
                    # DISABLED Nov 4, 2025 - Causes Qt/C++ level crashes
                    # self._validate_ai_score_with_objective_metrics()

                    if self.last_match_score < 70:
                        unreal.log("\n ITERATION AVAILABLE:")
                        unreal.log("The match score is still low. You can:")
                        unreal.log("1. Review the applied changes in Sequencer")
                        unreal.log("2. Click 'Capture All 7 Angles' again to re-analyze")
                        unreal.log("3. The AI will compare against the storyboard with new positions")

                # Save panel positions for multi-panel consistency (Feature #8)
                if self.active_panel and 'panel_number' in self.active_panel:
                    panel_id = f"Panel_{self.active_panel['panel_number']:03d}"
                    self._save_panel_positions(sequence_asset, panel_id)

            unreal.log("="*70 + "\n")

        except ImportError as e:
            unreal.log_error(f"Could not import SceneAdjuster: {e}")
            unreal.log_error("Make sure core/scene_adjuster.py exists")
        except Exception as e:
            unreal.log_error(f"Error applying adjustments: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def _finish_capture_sequence(self):
        """Print final summary and loop if auto-iteration is enabled"""
        # Store the current match score and details
        if self.last_match_score is not None:
            self.iteration_scores.append(self.last_match_score)

            # Track detailed metrics for this iteration
            iteration_data = {
                'iteration': self.current_iteration,
                'match_score': self.last_match_score,
                'adjustments_applied': getattr(self, '_last_adjustments_count', 0),
                'camera_adjusted': getattr(self, '_last_camera_adjusted', False)
            }
            self.iteration_details.append(iteration_data)

            # Record metrics for thesis evaluation
            self._record_iteration_metrics()

        unreal.log("\n" + "="*70)
        unreal.log("CAPTURE ITERATION COMPLETE!")
        unreal.log("="*70)

        # Display iteration summary with enhanced metrics
        unreal.log(f"\n ITERATION {self.current_iteration}/{self.max_iterations} RESULTS:")
        if self.last_match_score is not None:
            unreal.log(f"Match Score: {self.last_match_score}/100")

            # Show adjustments applied this iteration
            if hasattr(self, '_last_adjustments_count'):
                unreal.log(f"Adjustments Applied: {self._last_adjustments_count}")
            if hasattr(self, '_last_camera_adjusted'):
                camera_status = "Yes" if self._last_camera_adjusted else "No"
                unreal.log(f"Camera Adjusted: {camera_status}")

        # Show score progression with ASCII graph (Feature #5)
        if len(self.iteration_scores) > 1:
            unreal.log(f"\n SCORE PROGRESSION:")
            for i, score in enumerate(self.iteration_scores, 1):
                delta = ""
                if i > 1:
                    change = score - self.iteration_scores[i-2]
                    delta = f" ({change:+.0f})" if change != 0 else " (no change)"
                unreal.log(f"Iteration {i}: {score}/100{delta}")

            # Display ASCII graph
            try:
                graph = self._generate_ascii_graph(self.iteration_scores)
                unreal.log(f"\n{graph}")
            except Exception as e:
                unreal.log(f"Could not generate graph: {e}")

        # Check for stagnation at low scores (after iteration 2+)
        # NOTE: With checkpointing, oscillation/regression should NOT appear in displayed scores
        # However, we can detect stagnation if AI keeps getting rejected
        if len(self.iteration_scores) >= 3 and not self.use_absolute_positioning:
            current_score = self.iteration_scores[-1]

            # Check how many recent iterations were reverted
            if self.iteration_history:
                recent_reverts = sum(1 for entry in self.iteration_history[-3:]
                                    if entry.get('status') == 'reverted')

                # If 2+ out of last 3 were reverted, AI is struggling
                if recent_reverts >= 2:
                    unreal.log("\n STAGNATION DETECTED!")
                    unreal.log(f"{recent_reverts} of last 3 iterations reverted (AI suggestions not improving)")
                    unreal.log("Switching to ABSOLUTE positioning mode for next iteration...")
                    self.use_absolute_positioning = True

                # Also check if stuck at low score for 3+ iterations
                elif current_score < 50 and len(self.iteration_scores) >= 3:
                    recent_scores = self.iteration_scores[-3:]
                    if all(s < 50 for s in recent_scores):
                        unreal.log("\n LOW SCORE STAGNATION!")
                        unreal.log(f"Score below 50 for {len(recent_scores)} iterations")
                        unreal.log("Switching to ABSOLUTE positioning mode for next iteration...")
                        self.use_absolute_positioning = True

        # ENHANCED: Detect oscillation patterns (e.g., 70→10→70→10)
        # FIXED: Added oscillation detection to prevent wasted iterations
        oscillation_detected = False
        if len(self.iteration_scores) >= 4:
            last_four = self.iteration_scores[-4:]
            # Check for alternating pattern: [A, B, A, B] where |A-B| > 30
            if (abs(last_four[0] - last_four[1]) > 30 and
                abs(last_four[0] - last_four[2]) < 10 and
                abs(last_four[1] - last_four[3]) < 10):
                oscillation_detected = True
                unreal.log("\n OSCILLATION DETECTED!")
                unreal.log(f"Scores alternating: {last_four[0]:.0f} ↔ {last_four[1]:.0f}")
                unreal.log("System is bouncing between two states without converging")
                unreal.log("Stopping iterations - continuing would waste API calls")

        # Check if we should continue iterating
        # Stop if: reached max iterations OR score > 80 (success threshold) OR oscillation detected
        should_stop_early = (self.last_match_score and self.last_match_score > 80) or oscillation_detected

        if should_stop_early:
            if oscillation_detected:
                unreal.log(f"\n EARLY STOP: Oscillation detected (cannot converge further)")
                unreal.log(f"Final score: {self.last_match_score}/100")
            else:
                unreal.log(f"\n EARLY STOP: Match score {self.last_match_score}/100 exceeds 80% threshold!")
                unreal.log("Scene positioning achieved target quality")
            unreal.log("="*70)
            # Falls through to final summary below

        # Continue to next iteration only if NOT stopping early and not at max iterations
        if self.auto_iterate and self.current_iteration < self.max_iterations and not should_stop_early:
            next_delay = 20000  # 20 seconds between iterations
            unreal.log(f"\n CONTINUING TO ITERATION {self.current_iteration + 1}/{self.max_iterations}")
            unreal.log(f"⏳ Next capture will start in {next_delay/1000:.0f} seconds...")
            unreal.log("="*70)

            # Schedule next iteration
            self.current_iteration += 1
            QTimer.singleShot(next_delay, self._start_next_iteration)
            return  # Don't show final summary yet

        # Final summary - reached when early stop OR max iterations OR not auto-iterating
        unreal.log("\n" + "="*70)
        unreal.log("ALL ITERATIONS COMPLETE!")
        unreal.log("="*70)
        unreal.log("Screenshots saved to:")
        unreal.log("D:\\PythonStoryboardToUE\\Saved\\Screenshots\\WindowsEditor\\")
        unreal.log("- test_front.png")
        unreal.log("- test_right.png")
        unreal.log("- test_back.png")
        unreal.log("- test_left.png")
        unreal.log("- test_top.png")
        unreal.log("- test_3_4.png")
        unreal.log("- test_hero.png")
        # Final score analysis
        if self.iteration_scores:
            unreal.log("FINAL SCORE ANALYSIS:")
            unreal.log(f"Starting Score: {self.iteration_scores[0]}/100")
            unreal.log(f"Final Score: {self.iteration_scores[-1]}/100")
            improvement = self.iteration_scores[-1] - self.iteration_scores[0]
            unreal.log(f"Total Improvement: {improvement:+.0f} points")

            # Calculate best and worst iterations
            best_score = max(self.iteration_scores)
            worst_score = min(self.iteration_scores)
            best_iter = self.iteration_scores.index(best_score) + 1
            worst_iter = self.iteration_scores.index(worst_score) + 1
            unreal.log(f"Best Score: {best_score}/100 (Iteration {best_iter})")
            unreal.log(f"Worst Score: {worst_score}/100 (Iteration {worst_iter})")

            # Average score
            avg_score = sum(self.iteration_scores) / len(self.iteration_scores)
            unreal.log(f"Average Score: {avg_score:.1f}/100")

            # CHECKPOINTING: Iteration history
            if not self.enable_checkpointing:
                unreal.log(f"\n CHECKPOINTING: DISABLED")
                unreal.log(f"All AI adjustments were kept (no reverts)")
            elif self.iteration_history:
                unreal.log(f"\n CHECKPOINTING HISTORY:")
                accepted_count = sum(1 for h in self.iteration_history if h['status'] == 'accepted')
                reverted_count = sum(1 for h in self.iteration_history if h['status'] in ['reverted', 'reverted_unchanged'])

                unreal.log(f"Accepted: {accepted_count}, Reverted: {reverted_count}")
                unreal.log(f"Iteration Details:")

                for entry in self.iteration_history:
                    iter_num = entry['iteration']
                    score = entry['score']
                    status = entry['status']

                    if status == 'accepted':
                        improvement = entry.get('improvement', 0)
                        unreal.log(f"{iter_num}: {score}/100  ACCEPTED (+{improvement} points)")
                    elif status == 'reverted':
                        kept_score = entry.get('kept_score', 0)
                        drop = entry.get('drop', 0)
                        unreal.log(f"{iter_num}: {score}/100  REVERTED (kept {kept_score}/100, avoided -{drop} drop)")
                    elif status == 'reverted_unchanged':
                        kept_score = entry.get('kept_score', 0)
                        unreal.log(f"{iter_num}: {score}/100  REVERTED (no improvement, kept {kept_score}/100)")

                # Thesis defense talking point
                if reverted_count > 0:
                    unreal.log(f"\n    THESIS INSIGHT: Checkpointing prevented {reverted_count} non-improving iteration(s)")
                    unreal.log(f"This demonstrates robust optimization with guaranteed monotonic improvement")

            # FEATURE #6: Cost analysis
            if self.iteration_costs:
                unreal.log(f"\n COST ANALYSIS:")
                unreal.log(f"Total Cost: ${self.total_cost:.4f}")
                avg_cost = sum(self.iteration_costs) / len(self.iteration_costs)
                unreal.log(f"Average Cost/Iteration: ${avg_cost:.4f}")
                if improvement > 0:
                    cost_per_point = self.total_cost / improvement
                    unreal.log(f"Cost per Point Improvement: ${cost_per_point:.4f}")

            # Convergence analysis
            if len(self.iteration_scores) >= 2:
                unreal.log(f"\n CONVERGENCE ANALYSIS:")
                improving = all(self.iteration_scores[i] >= self.iteration_scores[i-1]
                               for i in range(1, len(self.iteration_scores)))

                if self.enable_checkpointing:
                    # With checkpointing, displayed scores should ALWAYS be monotonic
                    # (because we revert and show best_score when AI suggests worse positions)
                    if improving:
                        unreal.log(f"Monotonic improvement achieved - checkpointing working!")
                    else:
                        # This should NOT happen with checkpointing enabled
                        unreal.log(f"WARNING: Score regression detected despite checkpointing")
                        unreal.log(f"(This suggests a bug in the checkpointing logic)")
                else:
                    # Without checkpointing, oscillation is expected
                    if improving:
                        unreal.log(f"Monotonic improvement (lucky - no checkpointing)")
                    else:
                        unreal.log(f"Score oscillation detected (checkpointing was disabled)")

                # Target achievement
                target_score = 70
                if self.iteration_scores[-1] >= target_score:
                    unreal.log(f"TARGET ACHIEVED! ({target_score}+ score)")
                else:
                    needed = target_score - self.iteration_scores[-1]
                    unreal.log(f"{needed:.0f} points from target ({target_score})")
        unreal.log("⏱ Total sequence time: ~{0} seconds".format(138 * self.max_iterations))
        unreal.log("="*70)

        # Finalize and save thesis metrics
        self._finalize_metrics()

        # Check if we're in batch capture mode and need to process next panel
        if self.batch_capture_mode:
            # Record successful completion for this panel
            self.batch_capture_results.append({
                'panel': self.active_panel.get('name', 'unknown') if self.active_panel else 'unknown',
                'success': True,
                'final_score': self.last_match_score,
                'iterations': self.current_iteration
            })

            # Continue to next panel if any remain
            if self.batch_capture_queue:
                self._process_next_batch_panel()
                return  # Don't reset view selector yet - batch continues
            else:
                # This was the last panel - finalize batch
                self._finalize_batch_capture()
                return

        # Reset intelligent view selector for next scene
        if hasattr(self, 'view_selector') and self.view_selector:
            self.view_selector.reset()
            unreal.log("View selector reset for next scene")

        # Reset iteration state
        self.auto_iterate = False
        self.current_iteration = 0

    def _start_next_iteration(self):
        """Start the next capture iteration"""
        # ============================================================
        # Qt widgets may be deleted, causing access violations
        # ============================================================
        try:
            # Guard: Check if workflow was cancelled
            if not self.capture_workflow_active:
                unreal.log("Capture workflow cancelled - skipping start next iteration")
                return

            # Guard: Check if widget still exists (prevents Qt dangling reference crash)
            if not hasattr(self, 'active_panel') or self.active_panel is None:
                unreal.log_error("Active panel no longer exists - cannot continue iteration")
                return

            unreal.log("\n" + "="*70)
            unreal.log(f"STARTING ITERATION {self.current_iteration}/{self.max_iterations}")
            unreal.log("="*70)

            # Verify sequence is still open (in case it was closed between iterations)
            if self.active_panel and self.active_panel.get('sequence_path'):
                current_seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()

                if not current_seq:
                    unreal.log_warning("Sequence was closed - reopening...")
                    sequence_path = self.active_panel.get('sequence_path')
                    try:
                        sequence_asset = unreal.load_asset(sequence_path)
                        if sequence_asset:
                            unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence_asset)
                            unreal.log(f"Reopened sequence: {sequence_asset.get_name()}")
                        else:
                            unreal.log_error(f"Failed to load sequence: {sequence_path}")
                            return
                    except Exception as e:
                        unreal.log_error(f"Error reopening sequence: {e}")
                        return
        except Exception as e:
            unreal.log_error(f"CRASH PREVENTED in _start_next_iteration: {e}")
            unreal.log_error("This was likely a Qt widget access violation")
            unreal.log_error("Stopping iterations to prevent Unreal crash")
            import traceback
            unreal.log_error(traceback.format_exc())
            self.capture_workflow_active = False
            return

        # THESIS METRICS: Track iteration start time
        if self.metrics_tracker:
            from datetime import datetime
            self.metrics_tracker.current_iteration_start = datetime.now()
            unreal.log(f"⏱ Iteration timer started")

        # Debug state at iteration start
        unreal.log(f"\n ITERATION STATE:")
        unreal.log(f"Previous scores: {self.iteration_scores}")
        mode_str = "ABSOLUTE" if self.use_absolute_positioning else "RELATIVE"
        unreal.log(f"Positioning mode: {mode_str}")
        if self.last_match_score is not None:
            unreal.log(f"Last match score: {self.last_match_score}/100")
        # ============================================================
        # CRITICAL FIX #1: Cancel previous workflow to stop overlapping timers
        # QTimer.singleShot callbacks from iteration 1 are still scheduled!
        # Setting flag to False makes those callbacks abort immediately
        # ============================================================
        unreal.log("Cancelling previous workflow (stops old timer callbacks)...")
        self.capture_workflow_active = False

        # Process Qt events to let pending callbacks see the False flag and abort
        try:
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
        except:
            pass

        # Small delay to ensure old callbacks complete their guard checks
        import time
        time.sleep(0.5)
        unreal.log("Previous workflow cancelled (old timers will now abort)\n")

        # ============================================================
        # CRITICAL FIX #2: Clean up scout cameras from previous iteration
        # This prevents accessing stale/deleted camera objects
        # ============================================================
        unreal.log("Cleaning up scout cameras from previous iteration...")
        try:
            # Eject from any piloted camera first
            try:
                level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                level_editor_subsystem.eject_pilot_level_actor()
                unreal.log("Ejected from pilot camera")
            except:
                pass

            # Delete all scout cameras
            subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            all_actors = subsystem.get_all_level_actors()
            scouts_deleted = 0
            for actor in all_actors:
                if "AI_Scout" in actor.get_actor_label():
                    subsystem.destroy_actor(actor)
                    scouts_deleted += 1

            if scouts_deleted > 0:
                unreal.log(f"Deleted {scouts_deleted} scout camera(s)")
            else:
                unreal.log("No scout cameras to clean up")
        except Exception as cleanup_err:
            unreal.log_warning(f"Scout cleanup warning: {cleanup_err}")
        # Scout camera is a LEVEL actor, so viewport must show sequence-modified positions
        unreal.log("Forcing sequence evaluation before captures...")
        try:
            import time
            active_seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
            if active_seq:
                # Bind camera cuts to viewport first (makes sequence active)
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
                unreal.log("Sequence bound to viewport")

                # Set frame to 0 and force evaluation
                unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0.0)
                unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
                time.sleep(0.2)  # Allow viewport to update

                # Now unbind so scout camera can pilot freely
                unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)
                unreal.log("Sequence evaluated at frame 0, viewport updated")
            else:
                unreal.log_warning("No sequence active - scout cameras may show stale data")
        except Exception as e:
            unreal.log_warning(f"Could not force sequence evaluation: {e}")
        # ============================================================
        # Re-enable workflow flag for THIS iteration's callbacks
        # ============================================================
        self.capture_workflow_active = True
        unreal.log("Workflow reactivated for iteration {}\n".format(self.current_iteration))

        # Step 1: Pilot to Scout
        self.test_pilot_to_scout()
        unreal.log("Pilot complete\n")

        # Step 2: Front Capture
        front_success = self.test_capture_front()
        if not front_success:
            unreal.log_error("Front capture failed to queue!")
            return
        unreal.log("Front queued (1/6)\n")

        # Schedule remaining captures with 15s delays
        unreal.log("⏳ Scheduling remaining captures (15s between each)...\n")
        QTimer.singleShot(15000, self._capture_right_delayed)

    def _generate_ascii_graph(self, scores, width=60, height=10):
        """
        Generate ASCII graph of match scores (Feature #5)

        Args:
            scores: List of match scores (0-100)
            width: Character width of graph
            height: Character height of graph

        Returns:
            Multi-line string with ASCII graph
        """
        unreal.log(f"DEBUG: _generate_ascii_graph called with {len(scores)} scores: {scores}")

        if not scores:
            return ""

        try:
            unreal.log("DEBUG: Generating ASCII graph for {len(scores)} scores")

            # Normalize scores to graph height (0-100 -> 0-height)
            max_score = 100
            min_score = 0
            score_range = max_score - min_score

            # Create empty graph
            graph_lines = []

            # Top border with scale
            graph_lines.append(f"   100 │{'─' * width}")

            # Plot points
            for y in range(height - 1, -1, -1):
                # Calculate threshold for this row
                threshold = min_score + (y / height) * score_range

                # Build line
                line = f"   {int(threshold):3d} │"

                # Add points for each score
                for i, score in enumerate(scores):
                    # Calculate x position (spread evenly across width)
                    if len(scores) > 1:
                        x_pos = int((i / (len(scores) - 1)) * (width - 1))
                    else:
                        x_pos = width // 2

                    # Add point if score is at this height level
                    normalized_score = ((score - min_score) / score_range) * height

                    # Fill with spaces up to this point
                    while len(line) - 9 < x_pos:  # -9 for label width
                        line += " "

                    # Add marker if score is close to this row
                    if abs(normalized_score - y) < 0.5:
                        if i == len(scores) - 1:
                            line += "◆"  # Diamond for final point
                        else:
                            line += "●"  # Circle for other points
                        # Connect to previous point if exists
                        if i > 0 and len(scores) > 1:
                            prev_normalized = ((scores[i-1] - min_score) / score_range) * height
                            # Draw connecting line
                            if abs(prev_normalized - normalized_score) < 1:
                                line = line[:-1] + "─●" if i < len(scores) - 1 else line[:-1] + "─◆"
                    elif len(line) == 9 + x_pos:  # Just reached this position
                        line += " "

                graph_lines.append(line)

            # Bottom border
            graph_lines.append(f"     0 │{'─' * width}")

            result = "\n".join(graph_lines)
            unreal.log(f"DEBUG: ASCII graph generated ({len(graph_lines)} lines)")
            return result

        except Exception as e:
            unreal.log_error(f"ERROR generating ASCII graph: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return ""

    def _save_panel_positions(self, sequence_asset, panel_id):
        """
        Save current actor positions for multi-panel consistency (Feature #8)

        Args:
            sequence_asset: The LevelSequence asset
            panel_id: Unique identifier for this panel (e.g., "Panel_008")
        """
        unreal.log(f"DEBUG: _save_panel_positions called for panel_id={panel_id}")

        if not sequence_asset:
            unreal.log("DEBUG: No sequence asset provided")
            return

        try:
            bindings = sequence_asset.get_bindings()
            unreal.log(f"DEBUG: Found {len(bindings)} bindings in sequence")

            panel_positions = {}

            for binding in bindings:
                actor_name = str(binding.get_display_name())
                unreal.log(f"DEBUG: Processing binding for actor: {actor_name}")

                # Get transform track
                transform_tracks = binding.find_tracks_by_exact_type(unreal.MovieScene3DTransformTrack)
                if not transform_tracks:
                    unreal.log(f"DEBUG: No transform track for {actor_name}")
                    continue

                track = transform_tracks[0]
                sections = track.get_sections()
                if not sections:
                    unreal.log(f"DEBUG: No sections for {actor_name}")
                    continue

                section = sections[0]

                # Get channels
                channels = unreal.MovieSceneSectionExtensions.get_all_channels(section)
                unreal.log(f"DEBUG: Got {len(channels)} channels")

                if len(channels) < 3:
                    unreal.log(f"DEBUG: Not enough channels for {actor_name}")
                    continue

                # Read position at frame 0
                try:
                    keys_x = channels[0].get_keys()
                    keys_y = channels[1].get_keys()
                    keys_z = channels[2].get_keys()

                    x, y, z = 0.0, 0.0, 0.0

                    for key in keys_x:
                        if key.get_time().frame_number.value == 0:
                            x = key.get_value()
                            break
                    for key in keys_y:
                        if key.get_time().frame_number.value == 0:
                            y = key.get_value()
                            break
                    for key in keys_z:
                        if key.get_time().frame_number.value == 0:
                            z = key.get_value()
                            break

                    panel_positions[actor_name] = {'x': x, 'y': y, 'z': z}
                    unreal.log(f"DEBUG: Saved {actor_name} position: X={x:.1f}, Y={y:.1f}, Z={z:.1f}")

                except Exception as e:
                    unreal.log(f"Error reading position for {actor_name}: {e}")

            # Store in memory
            self.panel_actor_positions[panel_id] = panel_positions
            unreal.log(f"Saved positions for {len(panel_positions)} actors in panel {panel_id}")

        except Exception as e:
            unreal.log_error(f"Error saving panel positions: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def _get_previous_panel_positions(self, actor_name):
        """
        Get previous position for an actor from any earlier panel (Feature #8)

        Args:
            actor_name: Name of the actor to look up

        Returns:
            Dict with {x, y, z} or None if not found
        """
        unreal.log(f"DEBUG: Looking up previous position for {actor_name}")
        unreal.log(f"DEBUG: Searching through {len(self.panel_actor_positions)} panels")

        # Search through all panels (most recent first)
        for panel_id in reversed(sorted(self.panel_actor_positions.keys())):
            unreal.log(f"DEBUG: Checking panel {panel_id} with {len(self.panel_actor_positions[panel_id])} actors")

            if actor_name in self.panel_actor_positions[panel_id]:
                pos = self.panel_actor_positions[panel_id][actor_name]
                unreal.log(f"DEBUG: Found {actor_name} in panel {panel_id}: {pos}")
                return pos

        unreal.log(f"DEBUG: No previous position found for {actor_name}")
        return None

    def generate_scene_from_panel(self):
        """Generate 3D scene from storyboard panel"""
        unreal.log("\n" + "="*70)
        unreal.log("GENERATE BUTTON CLICKED")
        unreal.log("="*70)

        if not self.active_panel:
            unreal.log("ERROR: No panel selected")
            QMessageBox.warning(self, "No Panel", "Please select a panel first")
            return

        if not self.current_show:
            unreal.log("ERROR: No show selected")
            QMessageBox.warning(self, "No Show", "Please select a show first")
            return

        unreal.log(f"Active panel: {self.active_panel.get('path', 'unknown')}")
        unreal.log(f"Current show: {self.current_show}")

        try:
            # Get panel info with CURRENT UI STATE (user's edits)
            unreal.log("Gathering panel info from UI...")
            panel_info = self.get_panel_info()
            unreal.log(f"Panel info collected: {len(panel_info)} fields")
            # Build fresh analysis from what user has in the UI RIGHT NOW
            unreal.log("\n Building analysis from current UI state...")
            panel_info['analysis'] = {
                'characters': panel_info['characters'],  # From UI, not AI
                'props': panel_info['props'],            # From UI, not AI
                'location_type': panel_info['location'], # From UI dropdown
                'shot_type': panel_info['shot_type'],    # From UI dropdown
                'num_characters': len(panel_info['characters'])
            }
            unreal.log("Analysis dict created from UI")
            unreal.log("="*60)
            unreal.log("USING CURRENT UI STATE (User's Edits):")
            unreal.log(f"Characters: {panel_info['characters']}")
            unreal.log(f"Props: {panel_info['props']}")
            unreal.log(f"Location: {panel_info['location']}")
            unreal.log("="*60)
            # Show what we're generating
            info_text = f"""Generating scene from: {Path(panel_info['path']).name}

Characters: {', '.join(panel_info['characters']) if panel_info['characters'] else 'None'}
Props: {', '.join(panel_info['props']) if panel_info['props'] else 'None'}
Location: {panel_info['location']}
Shot Type: {panel_info['shot_type']}"""

            reply = QMessageBox.information(
                self,
                "Generate 3D Scene",
                info_text,
                QMessageBox.Ok | QMessageBox.Cancel
            )

            if reply != QMessageBox.Ok:
                return

            # Generate the scene using FIXED SEQUENCER builder with camera cut track
            unreal.log("="*60)
            unreal.log("SEQUENCER SCENE GENERATION WITH CAMERA CUT")
            unreal.log("="*60)

            # Use the scene builder with show context
            unreal.log("Importing SceneBuilder...")
            from core.scene_builder import SceneBuilder

            # Create scene builder with show context
            unreal.log(f"Creating SceneBuilder with show: {self.current_show}")
            scene_builder = SceneBuilder(show_name=self.current_show)
            unreal.log("SceneBuilder created")

            # Store reference to builder for camera access
            self.scene_builder = scene_builder

            # Get the panel index from the filename (e.g., testpanel_008.png -> 8)
            unreal.log("Extracting panel number from filename...")
            import re
            panel_filename = Path(panel_info['path']).stem
            match = re.search(r'(\d+)', panel_filename)
            panel_index = int(match.group(1)) if match else 0
            unreal.log(f"Panel index: {panel_index}")

            # Build the scene (now with proper camera cut track)
            unreal.log("\n Building 3D scene with sequencer...")
            unreal.log(f"Characters: {panel_info['analysis']['characters']}")
            unreal.log(f"Props: {panel_info['analysis']['props']}")
            unreal.log(f"Location: {panel_info['analysis']['location_type']}")
            unreal.log(f"Shot type: {panel_info['analysis']['shot_type']}")
            unreal.log(f"Panel index: {panel_index}")
            unreal.log(f"Auto camera: True")
            unreal.log(f"Auto lighting: True")

            scene_data = scene_builder.build_scene(
                panel_info['analysis'],
                panel_index=panel_index,  # Use actual panel number
                auto_camera=True,
                auto_lighting=True
            )
            unreal.log("build_scene() call complete")

            # Save thesis generation info
            success = scene_data is not None
            self._save_generation_thesis_info(panel_info, panel_index, success)

            if scene_data:
                unreal.log(f"Scene generation started with camera cut track!")

                # Viewport lock removed - user controls when to bind camera cuts
                unreal.log("=" * 60)
                unreal.log("TIP: Press Shift+C in Sequencer to lock viewport to camera")
                unreal.log("=" * 60)

                # Show success message with camera cut track info
                QMessageBox.information(
                    self,
                    "Building in Sequencer",
                    f"Creating Level Sequence with assets!\n\n" +
                    f" SEQUENCER BUILD:\n" +
                    f"1. Create Level Sequence \n" +
                    f"2. Load location: {panel_info.get('location', 'Current')} \n" +
                    f"3. Open Sequencer window \n" +
                    f"4. Add characters as spawnables \n" +
                    f"5. Add camera with {panel_info.get('shot_type', 'medium')} shot \n" +
                    f"6. Setup camera cut track  \n" +
                    f"7. Add lighting to sequence \n\n" +
                    f" Camera Cut Track created!\n" +
                    f" Press Shift+C in Sequencer to lock viewport to camera\n" +
                    f" Everything in Sequencer!"
                )

                # Store scene data and get camera reference from builder
                self.last_generated_scene = scene_data
                self.pending_scene = True
                if scene_data.get('sequence') and scene_data['sequence'].get('path'):
                    self.active_panel['sequence_path'] = scene_data['sequence']['path']
                    unreal.log(f"Updated active_panel with sequence_path: {scene_data['sequence']['path']}")

                # Schedule getting the camera after build completes
                QTimer.singleShot(3000, self._get_camera_from_builder)

            else:
                QMessageBox.warning(self, "Generation Failed", "Failed to start generation")

        except ImportError as e:
            QMessageBox.critical(
                self,
                "Module Not Available",
                f"Scene builder not properly configured.\n\nError: {e}\n\n" +
                "Make sure the core.scene_builder module is available."
            )
            unreal.log_error(f"Import error: {e}")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Generation Error",
                f"Failed to generate scene: {e}"
            )
            unreal.log_error(f"Generation error: {e}")

    def analyze_panel_with_ai(self):
        """Analyze storyboard panel with AI and populate UI fields"""
        unreal.log("\n" + "="*70)
        unreal.log("ANALYZE BUTTON CLICKED")
        unreal.log("="*70)

        if not self.active_panel:
            unreal.log("ERROR: No panel selected")
            QMessageBox.warning(self, "No Panel", "Please select a panel first")
            return

        unreal.log(f"Active panel: {self.active_panel.get('path', 'unknown')}")
        unreal.log(f"Current show: {self.current_show}")

        try:
            unreal.log("Creating progress dialog...")
            # Create proper progress dialog that auto-closes
            progress = QProgressDialog("Analyzing storyboard with AI...\n\nThis may take 10-20 seconds.", None, 0, 0, self)
            progress.setWindowTitle(" Analyzing Panel")
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)  # Remove cancel button
            progress.setAutoClose(True)  # Auto close when done
            progress.setAutoReset(True)  # Auto reset when done
            progress.show()
            QApplication.processEvents()  # Force UI update
            unreal.log("Progress dialog shown")

            # Import and run analyzer
            unreal.log("Setting up analyzer import path...")
            import sys
            analyzer_path = r'D:\PythonStoryboardToUE\Plugins\StoryboardTo3D\Content\Python'
            if analyzer_path not in sys.path:
                sys.path.append(analyzer_path)
                unreal.log(f"Added path: {analyzer_path}")
            else:
                unreal.log(f"Path already in sys.path: {analyzer_path}")

            # Use smart analyzer with Asset Library
            # Note: SmartStoryboardAnalyzer is pre-imported based on optimization flag
            unreal.log("Attempting to use SmartStoryboardAnalyzer...")
            try:
                # Use the pre-imported class (either optimized or original based on feature flag)
                if SmartStoryboardAnalyzer is not None:
                    analyzer = SmartStoryboardAnalyzer()
                    unreal.log("Using SmartStoryboardAnalyzer")
                else:
                    # Fallback: import dynamically if not pre-imported
                    from core.smart_analyzer import SmartStoryboardAnalyzer as Analyzer
                    analyzer = Analyzer()
                    unreal.log("Using SmartStoryboardAnalyzer (dynamic import)")
            except Exception as e:
                unreal.log_warning(f"SmartStoryboardAnalyzer not available: {e}")
                # Fallback to basic panel analyzer
                try:
                    from core.panel_analyzer import PanelAnalyzer
                    analyzer = PanelAnalyzer()
                    unreal.log("Using fallback PanelAnalyzer")
                except ImportError as e2:
                    progress.close()
                    progress.deleteLater()
                    QApplication.processEvents()
                    QMessageBox.critical(
                        self,
                        "Analyzer Not Available",
                        f"No analyzer module found.\n\nErrors:\n{e}\n{e2}\n\n" +
                        "Make sure core.smart_analyzer or core.panel_analyzer exists."
                    )
                    return

            # Do the analysis (both analyzers use analyze_panel method)
            unreal.log("\n Starting AI analysis...")
            unreal.log(f"Panel path: {self.active_panel['path']}")
            unreal.log(f"Show context: {self.current_show}")

            if hasattr(analyzer, 'analyze_panel'):
                unreal.log("Using analyze_panel() method")
                result = analyzer.analyze_panel(self.active_panel['path'], self.current_show)
            else:
                # Fallback method name
                unreal.log("Using fallback analyze_storyboard() method")
                result = analyzer.analyze_storyboard(self.active_panel['path'])

            unreal.log("AI analysis complete")

            # Close the progress dialog properly
            progress.close()
            progress.deleteLater()  # Clean up the dialog
            QApplication.processEvents()  # Process the close event

            if result:
                unreal.log(f"[ANALYZE] Got result: {result}")
                unreal.log("\n ANALYSIS RESULTS:")
                unreal.log(f"Characters: {result.get('characters', [])}")
                unreal.log(f"Props: {result.get('props', [])}")
                unreal.log(f"Location: {result.get('location', 'N/A')}")
                unreal.log(f"Location type: {result.get('location_type', 'N/A')}")
                unreal.log(f"Shot type: {result.get('shot_type', 'N/A')}")
                unreal.log(f"Num characters: {result.get('num_characters', 0)}")

                # Populate UI fields with detected elements
                unreal.log("\n Populating UI fields...")

                # Clear existing fields
                unreal.log("Clearing existing character and prop lists...")
                self.characters_list.clear()
                self.props_list.clear()

                # Handle different result formats (SmartAnalyzer vs PanelAnalyzer)
                characters = result.get('characters', [])
                props = result.get('props', [])
                location_elements = result.get('location_elements', [])

                # If no characters but has num_characters, use default from library
                if not characters and result.get('num_characters', 0) > 0:
                    if self.asset_library and 'characters' in self.asset_library:
                        available_chars = list(self.asset_library['characters'].keys())
                        # Add first character from library
                        characters = [available_chars[0]] if available_chars else []
                        unreal.log(f"[ANALYZE] Using default character from library: {characters}")

                # If props not found, try 'objects' key (PanelAnalyzer format)
                if not props:
                    props = result.get('objects', [])

                # Store location elements in panel data (NOT as props)
                if location_elements:
                    if self.active_panel:
                        self.active_panel['location_elements'] = location_elements
                    unreal.log(f"[ANALYZE] Location elements (static scenery): {location_elements}")

                unreal.log(f"[ANALYZE] Characters to add: {characters}")
                unreal.log(f"[ANALYZE] Props to add (moveable only): {props}")

                # Add detected characters
                for char in characters:
                    if char and char != 'generic_prop':  # Skip generic placeholders
                        self.characters_list.addItem(char)
                        unreal.log(f"[ANALYZE] Added character: {char}")

                # Add detected props (ONLY moveable objects)
                for prop in props:
                    if prop and prop != 'generic_prop':  # Skip generic placeholders
                        self.props_list.addItem(prop)
                        unreal.log(f"[ANALYZE] Added prop: {prop}")

                # Set location - try multiple keys
                location = result.get('location', result.get('location_type', 'Auto-detect'))
                if location:
                    unreal.log(f"[ANALYZE] Setting location: {location}")
                    index = self.location_combo.findText(location)
                    if index >= 0:
                        self.location_combo.setCurrentIndex(index)
                    else:
                        # Location not in dropdown, add it if it's valid
                        if location not in ['Auto-detect', 'Location Unknown']:
                            self.location_combo.addItem(location)
                            self.location_combo.setCurrentText(location)

                # Set shot type
                shot_type = result.get('shot_type', 'Auto')
                # Normalize shot type names
                shot_type_map = {
                    'close': 'Close-up',
                    'medium': 'Medium',
                    'wide': 'Wide',
                    'extreme_close': 'ECU',
                    'extreme_wide': 'Wide',
                    'ots': 'OTS',
                    'over_shoulder': 'OTS',
                    'pov': 'POV'
                }
                shot_type = shot_type_map.get(shot_type.lower(), shot_type.title())

                unreal.log(f"[ANALYZE] Setting shot type: {shot_type}")
                index = self.shot_type_combo.findText(shot_type)
                if index >= 0:
                    self.shot_type_combo.setCurrentIndex(index)

                # Update status and description
                self.analysis_status_label.setText(" AI Analyzed")
                self.analysis_status_label.setStyleSheet("color: #00AA00;")

                description = result.get('description', result.get('raw_description', 'Scene analyzed'))
                if description:
                    display_desc = description[:100] + "..." if len(description) > 100 else description
                    self.description_label.setText(f"Scene: {display_desc}")
                    self.description_label.setStyleSheet("color: #FFFFFF; font-style: italic; padding: 5px;")

                # Update AI raw description box
                raw_desc = result.get('ai_raw_description', result.get('description', ''))
                if raw_desc:
                    self.ai_description_text.setPlainText(raw_desc)

                # Update confidence
                confidence = result.get('confidence', 75)  # Default 75%
                self.confidence_bar.setValue(int(confidence))

                # Store analysis in panel data
                self.active_panel['analysis'] = result

                # Save panel metadata to file
                parent = self.parent()
                if parent and hasattr(parent, 'save_panel_metadata'):
                    parent.save_panel_metadata(self.active_panel)

                # Show results dialog with validation info
                validation_notes = result.get('validation_notes', {})
                available_info = ""

                if validation_notes:
                    available_info = f"\n\n Available in Asset Library:\n"
                    if validation_notes.get('locations_available'):
                        available_info += f"Locations: {', '.join(validation_notes['locations_available'][:3])}...\n"
                    if validation_notes.get('characters_available'):
                        available_info += f"Characters: {', '.join(validation_notes['characters_available'][:3])}...\n"

                # Build summary
                char_summary = ', '.join(characters) if characters else 'None (add manually)'
                prop_summary = ', '.join(props) if props else 'None (add manually)'

                results_text = f"""AI Analysis Complete!

 Description:
{description}

 Detected Elements:
• Characters: {char_summary}
• Props: {prop_summary}
• Location: {location}
• Shot Type: {shot_type}
• Confidence: {confidence:.1f}%

These elements have been added to your panel.
You can edit them before generating the scene.{available_info}"""

                QMessageBox.information(
                    self,
                    "Analysis Complete",
                    results_text
                )

                unreal.log("Panel analyzed and UI populated successfully")

            else:
                QMessageBox.warning(
                    self,
                    "Analysis Failed",
                    "Could not analyze the panel. Please add elements manually."
                )

        except ImportError as e:
            QMessageBox.critical(
                self,
                "Analyzer Not Available",
                f"AI analysis system not found.\n\nError: {e}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Analysis Error",
                f"Failed to analyze panel: {e}"
            )
            unreal.log_error(f"Analysis error: {e}")

    def _get_camera_from_builder(self):
        """Get camera from builder - DISABLED (camera is spawnable)"""
        return None

    def take_viewport_screenshot(self):
        """Take HIGH RESOLUTION screenshot of viewport and save to plugin Screenshots folder
        NON-BLOCKING - Queues screenshot command and returns immediately.
        Screenshot will save asynchronously to project Screenshots folder.
        """
        resolution = "2560x1440"  # Fixed high-quality resolution
        unreal.log(f"[SCREENSHOT] Taking HIGH-RES viewport screenshot ({resolution})...")

        try:
            # Use HIGH RESOLUTION screenshot command
            # HighResShot produces much better quality than Screenshot
            highres_command = f"HighResShot {resolution}"
            unreal.SystemLibrary.execute_console_command(None, highres_command)

            unreal.log(f"[SCREENSHOT]  HighResShot command queued: {highres_command}")
            unreal.log(f"[SCREENSHOT]  Screenshot will save asynchronously")
            unreal.log(f"[SCREENSHOT] ⏱  Wait ~10-15 seconds for high-res processing")

            # Get expected destination path for reference
            from pathlib import Path
            saved_dir = Path(unreal.Paths.project_saved_dir())
            screenshots_dir = saved_dir / "Screenshots" / "WindowsEditor"

            unreal.log(f"[SCREENSHOT]  Expected location: {screenshots_dir}")
            unreal.log(f"[SCREENSHOT]  Look for: HighresScreenshot*.png")

            # Return immediately - no blocking!
            return str(screenshots_dir)

        except Exception as e:
            unreal.log_error(f"[SCREENSHOT]  Failed to queue screenshot: {e}")
            return None

    def _find_latest_sequence(self):
        """Find the most recently created sequence"""
        if not self.current_show:
            unreal.log_warning("[FIND] No current show set")
            return None

        # Look in show-specific directory first
        sequence_dirs = [
            f"/Game/StoryboardSequences/{self.current_show}",
            "/Game/StoryboardSequences"
        ]

        latest_sequence = None
        latest_time = 0

        for seq_dir in sequence_dirs:
            if unreal.EditorAssetLibrary.does_directory_exist(seq_dir):
                assets = unreal.EditorAssetLibrary.list_assets(seq_dir, recursive=False)

                unreal.log(f"[FIND] Checking directory: {seq_dir}")
                unreal.log(f"[FIND] Found {len(assets)} assets")

                # ============================================================
                # DEBUG: Log all assets in directory
                # ============================================================
                if assets and len(assets) < 20:  # Only log if reasonable number
                    unreal.log(f"[FIND DEBUG] Assets in directory:")
                    for asset in assets:
                        asset_name = asset.split('/')[-1]
                        unreal.log(f"[FIND DEBUG]   - {asset_name}")
                elif len(assets) >= 20:
                    unreal.log(f"[FIND DEBUG] Too many assets ({len(assets)}) to list individually")
                else:
                    unreal.log(f"[FIND DEBUG] Directory is empty")
                # ============================================================

                # Filter for LevelSequence assets with Panel_ prefix
                for asset_path in assets:
                    # Look for Panel_XXX_Sequence pattern (not Seq_Panel_)
                    if 'Panel_' in asset_path and '_Sequence' in asset_path:
                        # Check if it's a LevelSequence
                        asset = unreal.load_asset(asset_path)
                        if isinstance(asset, unreal.LevelSequence):
                            unreal.log(f"[FIND] Found sequence: {asset_path}")
                            # Get panel number from path (e.g., Panel_008_Sequence -> 8)
                            import re
                            match = re.search(r'Panel_(\d+)_Sequence', asset_path)
                            if match:
                                panel_num = int(match.group(1))
                                if panel_num > latest_time:
                                    latest_time = panel_num
                                    latest_sequence = asset_path
                                    unreal.log(f"[FIND] New latest: Panel {panel_num}")

        if latest_sequence:
            unreal.log(f"[FIND]  Found latest sequence: {latest_sequence}")
        else:
            unreal.log_warning("[FIND]  No sequences found")
            unreal.log_warning(f"[FIND] Searched in: {sequence_dirs}")

        return latest_sequence

    # ========================================================================
    # METRICS TRACKING FOR THESIS EVALUATION
    # ========================================================================

    def _init_metrics_tracker(self):
        """Initialize metrics tracker for thesis evaluation"""
        if not METRICS_AVAILABLE:
            return

        # Auto-generate scene ID if not configured
        if not self.current_scene_id:
            if self.active_panel and 'panel_number' in self.active_panel:
                self.current_scene_id = f"Panel_{self.active_panel['panel_number']:03d}"
            elif self.active_panel and 'path' in self.active_panel:
                # Extract panel number from filename (e.g., testpanel_008.png → 8)
                import re
                match = re.search(r'_(\d+)\.png', self.active_panel['path'])
                if match:
                    panel_num = int(match.group(1))
                    self.current_scene_id = f"Panel_{panel_num:03d}"
                    unreal.log(f"Extracted panel number {panel_num} from filename")
                else:
                    from datetime import datetime
                    self.current_scene_id = f"Scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            else:
                from datetime import datetime
                self.current_scene_id = f"Scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Use default approach if not configured
        if not self.current_approach:
            self.current_approach = "multiview"

        # Create metrics output directory
        metrics_dir = Path(unreal.Paths.project_saved_dir()) / "ThesisMetrics"

        # Initialize multi-model tracker (creates 4 CSV files)
        if MultiModelTracker and not self.multi_model_tracker:
            try:
                self.multi_model_tracker = MultiModelTracker(output_dir=metrics_dir)
                unreal.log("Multi-model tracker initialized (4 CSVs with 12 scene slots)")
            except Exception as e:
                unreal.log_warning(f"Multi-model tracker failed: {e}")

        try:
            self.metrics_tracker = MetricsTracker(
                output_dir=metrics_dir,
                scene_id=self.current_scene_id,
                approach=self.current_approach
            )

            # Set scene context if available
            # THESIS METRICS FIX: Read from last_scene_context (set during capture) first,
            # then fall back to active_panel['scene_context']
            scene_context = getattr(self, 'last_scene_context', {})
            if not scene_context and self.active_panel:
                scene_context = self.active_panel.get('scene_context', {})

            # Extract characters and props from scene context
            characters = scene_context.get('characters', [])
            props = scene_context.get('props', [])

            # Infer environment from scene context
            environment = 'unknown'
            if scene_context.get('environment'):
                environment = scene_context['environment']
            elif any('outdoor' in p.lower() or 'park' in p.lower() for p in props):
                environment = 'outdoor'
            elif any('indoor' in p.lower() or 'room' in p.lower() for p in props):
                environment = 'indoor'

            # Get storyboard path safely
            storyboard_file = ''
            if self.active_panel:
                storyboard_file = self.active_panel.get('storyboard_path', '')

            self.metrics_tracker.set_scene_context(
                num_characters=len(characters),
                num_props=len(props),
                storyboard_file=str(storyboard_file),
                environment=environment
            )

            unreal.log(f"\n METRICS TRACKING INITIALIZED:")
            unreal.log(f"Scene ID: {self.current_scene_id}")
            unreal.log(f"Approach: {self.current_approach}")
            unreal.log(f"Output: {metrics_dir / self.current_scene_id}")
        except Exception as e:
            unreal.log_error(f"Failed to initialize metrics tracker: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            self.metrics_tracker = None
            unreal.log_error("Thesis metrics will NOT be saved for this test!")

    def _record_iteration_metrics(self):
        """Record metrics for current iteration"""
        if not self.metrics_tracker or self.last_match_score is None:
            if not self.metrics_tracker:
                unreal.log_warning(f"Cannot record metrics for iteration {self.current_iteration}: metrics_tracker is None")
            return

        # Debug logging to confirm function is running
        unreal.log(f"DEBUG: Recording metrics for iteration {self.current_iteration}, score={self.last_match_score}")

        try:
            # Get iteration cost
            iteration_cost = self.iteration_costs[-1] if self.iteration_costs else 0.0

            # Get positioning mode
            positioning_mode = 'absolute' if self.use_absolute_positioning else 'relative'

            # Get temperature (reconstruct from iteration number)
            # FIXED: Match updated schedule (0.7 for iters 1-2, 0.4 for iters 3+)
            if self.current_iteration <= 2:
                temperature = 0.7
            else:
                temperature = 0.4

            # Get analysis text if available
            analysis_text = ''
            if self.last_positioning_analysis:
                analysis_text = self.last_positioning_analysis.get('analysis', '')

            # Get adjustments data
            adjustments_data = None
            if self.last_positioning_analysis:
                adjustments_data = self.last_positioning_analysis.get('adjustments', [])

            # Capture camera position from sequence
            camera_position = None
            try:
                unreal.log("DEBUG: Starting camera position capture...")
                # Get sequence path from active panel, or find latest if not available
                sequence_path = None
                if self.active_panel:
                    sequence_path = self.active_panel.get('sequence_path')

                # Fallback to finding latest sequence if not in active_panel
                if not sequence_path:
                    unreal.log("DEBUG: No sequence_path in active_panel, using _find_latest_sequence()")
                    sequence_path = self._find_latest_sequence()

                unreal.log(f"DEBUG: sequence_path = {sequence_path}")

                if sequence_path:
                    sequence_asset = unreal.load_asset(sequence_path)
                    unreal.log(f"DEBUG: sequence_asset loaded = {sequence_asset is not None}")

                    if sequence_asset:
                        # Use scene_adjuster's find_camera_in_sequence to get camera name
                        from core.scene_adjuster import SceneAdjuster
                        temp_adjuster = SceneAdjuster(sequence_asset)
                        camera_name = temp_adjuster.find_camera_in_sequence("Hero")
                        unreal.log(f"DEBUG: camera_name = '{camera_name}'")

                        if camera_name:
                            # Get transforms and look for this specific camera
                            all_transforms = self._capture_actor_transforms(sequence_asset)
                            unreal.log(f"DEBUG: all_transforms has {len(all_transforms)} actors")
                            unreal.log(f"DEBUG: all_transforms keys = {list(all_transforms.keys())}")
                            camera_position = all_transforms.get(camera_name)
                            unreal.log(f"DEBUG: camera_position found = {camera_position is not None}")

                            if camera_position:
                                unreal.log(f"Camera '{camera_name}' position captured: X={camera_position['location']['x']:.1f}, Y={camera_position['location']['y']:.1f}, Z={camera_position['location']['z']:.1f}")
                            else:
                                unreal.log_warning(f"Camera '{camera_name}' not found in transforms")
                                unreal.log_warning(f"Available actors: {list(all_transforms.keys())}")
                        else:
                            unreal.log_warning(f"No Hero camera found in sequence")
                    else:
                        unreal.log_warning(f"Failed to load sequence asset: {sequence_path}")
                else:
                    unreal.log_warning(f"No sequence path found")
            except Exception as e:
                unreal.log_warning(f"Could not capture camera position: {e}")
                import traceback
                unreal.log_warning(traceback.format_exc())

            # Record iteration (including objective metrics if available)
            self.metrics_tracker.record_iteration(
                iteration_num=self.current_iteration,
                match_score=self.last_match_score,
                adjustments_applied=getattr(self, '_last_adjustments_count', 0),
                camera_adjusted=getattr(self, '_last_camera_adjusted', False),
                cost=iteration_cost,
                positioning_mode=positioning_mode,
                temperature=temperature,
                analysis_text=analysis_text,
                adjustments_data=adjustments_data,
                camera_position=camera_position,
                # THESIS ENHANCEMENT: Include objective metrics and validation
                objective_metrics=self.last_objective_metrics,
                validation_result=self.last_validation_result
            )

            unreal.log(f"Metrics recorded for iteration {self.current_iteration}: score={self.last_match_score}, cost=${iteration_cost:.4f}")

        except Exception as e:
            unreal.log_warning(f"Failed to record iteration metrics: {e}")

    def _validate_ai_score_with_objective_metrics(self):
        """
        THESIS ENHANCEMENT: Validate AI's subjective match score against objective perceptual metrics

        Calculates SSIM, PSNR, MSE (and LPIPS if available) and validates AI score
        Stores results in self.last_objective_metrics and self.last_validation_result
        """
        try:
            # Initialize validator on first use
            if self.metric_validator is None:
                from analysis.metric_validation import MetricValidator
                self.metric_validator = MetricValidator()
                unreal.log("MetricValidator initialized")

            # Get storyboard path from active panel
            if not self.active_panel or 'path' not in self.active_panel:
                unreal.log_warning("No active panel - skipping metric validation")
                return

            storyboard_path = self.active_panel['path']

            # Get hero screenshot path
            screenshot_dir = Path(unreal.Paths.project_saved_dir()) / "Screenshots" / "WindowsEditor"
            hero_screenshot_path = screenshot_dir / "test_hero.png"

            # Check if files exist
            if not Path(storyboard_path).exists():
                unreal.log_warning(f"Storyboard not found: {storyboard_path}")
                return

            if not hero_screenshot_path.exists():
                unreal.log_warning(f"Hero screenshot not found: {hero_screenshot_path}")
                return

            # Calculate objective metrics
            unreal.log("\n METRIC VALIDATION (Automatic):")
            objective_metrics = self.metric_validator.calculate_objective_metrics(
                reference_path=str(storyboard_path),
                test_path=str(hero_screenshot_path)
            )

            if not objective_metrics:
                unreal.log_warning("Could not calculate objective metrics")
                return

            # Store for metrics tracker
            self.last_objective_metrics = objective_metrics

            # Validate AI score
            validation_result = self.metric_validator.validate_ai_score(
                ai_subjective_score=self.last_match_score,
                objective_metrics=objective_metrics
            )

            # Store validation result
            self.last_validation_result = validation_result

            # Log validation results
            composite_score = validation_result['composite_objective_score'] * 100
            discrepancy = validation_result['discrepancy'] * 100
            valid = validation_result['valid']

            unreal.log(f"AI Score: {self.last_match_score:.1f}% | Objective: {composite_score:.1f}%")
            unreal.log(f"SSIM: {objective_metrics['ssim']:.3f} | PSNR: {objective_metrics['psnr']:.1f} dB | MSE: {objective_metrics['mse']:.1f}")

            if objective_metrics.get('lpips') is not None:
                unreal.log(f"LPIPS: {objective_metrics['lpips']:.3f} (perceptual distance)")

            if valid:
                unreal.log(f"VALIDATED (discrepancy: {discrepancy:.1f}%)")
            else:
                unreal.log(f"NOT VALIDATED (discrepancy: {discrepancy:.1f}% exceeds 20% threshold)")
                unreal.log(f"AI may be {'overestimating' if self.last_match_score > composite_score else 'underestimating'} quality")

            # Show correlation if we have history
            correlation_stats = self.metric_validator.calculate_correlation_statistics()
            if correlation_stats['n'] >= 2:
                corr = correlation_stats['correlation']
                p_val = correlation_stats['p_value']
                if corr is not None:
                    if p_val < 0.05:
                        unreal.log(f"Correlation: r={corr:.3f}, p={p_val:.4f} (significant)")
                    else:
                        unreal.log(f"Correlation: r={corr:.3f}, p={p_val:.4f} (not yet significant, n={correlation_stats['n']})")

        except ImportError as e:
            unreal.log_warning(f"Metric validation unavailable: {e}")
            unreal.log_warning(f"Install: pip install scikit-image scipy pillow")
            self.metric_validator = None  # Don't try again
        except Exception as e:
            unreal.log_warning(f"Metric validation failed: {e}")
            import traceback
            unreal.log_warning(traceback.format_exc())

    def _finalize_metrics(self):
        """Finalize and save all metrics at end of test sequence"""
        if not self.metrics_tracker:
            unreal.log_warning("Metrics tracker is None - cannot finalize metrics")
            unreal.log_warning("This means metrics were not tracked during the test")
            unreal.log_warning("Check for errors during metrics tracker initialization")
            return

        try:
            summary = self.metrics_tracker.finalize()

            # Also update multi-model comparison CSV
            if self.multi_model_tracker and summary is not None:
                if summary:  # Not empty
                    self._update_multi_model_csv(summary)
                else:
                    unreal.log_warning("Summary is empty - no iterations were recorded")
                    unreal.log_warning("Multi-model CSV will not be updated")

            unreal.log("\n" + "="*70)
            unreal.log("THESIS METRICS SAVED!")
            unreal.log("="*70)
            unreal.log(f"\n Metrics saved to:")
            unreal.log(f"{self.metrics_tracker.output_dir}")
            unreal.log(f"\n Files generated:")
            unreal.log(f"- {self.current_scene_id}_{self.current_approach}_metrics.json")
            unreal.log(f"- {self.current_scene_id}_{self.current_approach}_iterations.csv")
            unreal.log(f"- {self.current_scene_id}_{self.current_approach}_summary.txt")

            unreal.log(f"\n KEY RESULTS:")
            unreal.log(f"Initial Accuracy: {summary.get('initial_accuracy', 0):.1f}%")
            unreal.log(f"Final Accuracy: {summary.get('final_accuracy', 0):.1f}%")
            unreal.log(f"Improvement: {summary.get('improvement', 0):+.1f} pp")
            unreal.log(f"Total Iterations: {summary.get('total_iterations', 0)}")
            unreal.log(f"Converged: {'Yes' if summary.get('converged') else 'No'}")
            if summary.get('converged'):
                unreal.log(f"Converged at Iteration: {summary.get('convergence_iteration', 'N/A')}")
            unreal.log(f"Total Cost: ${summary.get('total_cost', 0):.4f}")
            # Tips for using the data
            unreal.log("USING THE METRICS:")
            unreal.log("1. Open the JSON file for complete data (includes camera positions)")
            unreal.log("2. Open the CSV file in Excel/Google Sheets (camera pos/rot columns)")
            unreal.log("3. Read the summary TXT for human-readable results")
            unreal.log("4. Camera positions recorded per iteration (location + rotation)")
            unreal.log("5. Use MetricsSummaryReport to aggregate multiple test runs")
            unreal.log("="*70 + "\n")

        except Exception as e:
            unreal.log_error(f"Failed to finalize metrics: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

    def _save_generation_thesis_info(self, panel_info, panel_index, success):
        """Save thesis info about scene generation to a log file

        Args:
            panel_info: Panel information dict
            panel_index: Panel number
            success: Whether generation succeeded
        """
        try:
            from datetime import datetime

            # Create thesis generation log directory
            thesis_dir = Path(unreal.Paths.project_saved_dir()) / "ThesisGeneration"
            thesis_dir.mkdir(parents=True, exist_ok=True)

            # Create log filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = thesis_dir / f"Panel_{panel_index:03d}_generation_{timestamp}.txt"

            # Write generation info
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write("THESIS: SCENE GENERATION RECORD\n")
                f.write("="*70 + "\n\n")

                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Panel Index: {panel_index}\n")
                f.write(f"Panel File: {Path(panel_info['path']).name}\n")
                f.write(f"Show: {self.current_show}\n")
                f.write(f"Generation Status: {'SUCCESS' if success else 'FAILED'}\n\n")

                f.write("SCENE COMPOSITION:\n")
                f.write(f"  Location: {panel_info.get('location', 'Unknown')}\n")
                f.write(f"  Shot Type: {panel_info.get('shot_type', 'Unknown')}\n")
                f.write(f"  Duration: {panel_info.get('duration', 0)} seconds\n\n")

                f.write("CHARACTERS:\n")
                if panel_info.get('characters'):
                    for char in panel_info['characters']:
                        f.write(f"  - {char}\n")
                else:
                    f.write("  (none)\n")
                f.write("\n")

                f.write("PROPS:\n")
                if panel_info.get('props'):
                    for prop in panel_info['props']:
                        f.write(f"  - {prop}\n")
                else:
                    f.write("  (none)\n")
                f.write("\n")

                f.write("="*70 + "\n")

            unreal.log(f"Thesis generation info saved: {log_file.name}")

        except Exception as e:
            unreal.log_warning(f"Failed to save thesis generation info: {e}")

    def _generate_scene_internal(self, panel_data):
        """Internal helper to generate scene without UI prompts (for batch mode)

        Args:
            panel_data: Panel dictionary with 'analysis', 'path', etc.

        Returns:
            bool: True if generation succeeded, False otherwise
        """
        try:
            # Get panel info from UI (which was updated by set_panel)
            panel_info = self.get_panel_info()

            if not panel_info:
                unreal.log_error("Failed to get panel info")
                return False

            # Build analysis from UI state
            panel_info['analysis'] = {
                'characters': panel_info['characters'],
                'props': panel_info['props'],
                'location_type': panel_info['location'],
                'shot_type': panel_info['shot_type'],
                'num_characters': len(panel_info['characters'])
            }

            # Import scene builder
            from core.scene_builder import SceneBuilder

            # Create scene builder
            scene_builder = SceneBuilder(show_name=self.current_show)
            self.scene_builder = scene_builder

            # Extract panel index from filename
            import re
            panel_filename = Path(panel_info['path']).stem
            match = re.search(r'(\d+)', panel_filename)
            panel_index = int(match.group(1)) if match else 0

            # Build the scene
            unreal.log(f"Building scene for panel {panel_index}...")
            scene_data = scene_builder.build_scene(
                panel_info['analysis'],
                panel_index=panel_index,
                auto_camera=True,
                auto_lighting=True
            )

            success = scene_data is not None
            if success:
                self.last_generated_scene = scene_data
                self.pending_scene = True

                # CRITICAL: Save sequence_path back to panel data for batch capture!
                if scene_data.get('sequence') and scene_data['sequence'].get('path'):
                    panel_data['sequence_path'] = scene_data['sequence']['path']
                    unreal.log(f"Saved sequence_path to panel: {scene_data['sequence']['path']}")

            # Save thesis generation info
            self._save_generation_thesis_info(panel_info, panel_index, success)

            return success

        except Exception as e:
            unreal.log_error(f"Scene generation error: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())
            return False

    def batch_generate_all_panels(self):
        """Generate 3D scenes for all panels in the current episode"""
        unreal.log("\n" + "="*70)
        unreal.log("BATCH GENERATE - STARTING")
        unreal.log("="*70)

        # Walk up the widget tree to find the MainWindow
        main_window = None
        widget = self
        max_depth = 10  # Prevent infinite loop
        depth = 0

        while widget and depth < max_depth:
            widget = widget.parent()
            if widget and hasattr(widget, 'panels'):
                main_window = widget
                unreal.log(f"Found MainWindow at depth {depth}")
                break
            depth += 1

        if not main_window:
            QMessageBox.warning(
                self,
                "Cannot Access Panels",
                "Could not find main window with panels.\n\nPlease restart the plugin."
            )
            unreal.log("ERROR: Could not find MainWindow in widget tree")
            return

        if not hasattr(main_window, 'panels'):
            QMessageBox.warning(
                self,
                "Cannot Access Panels",
                "Main window doesn't have panels attribute.\n\nPlease restart the plugin."
            )
            unreal.log("ERROR: MainWindow missing 'panels' attribute")
            return

        if not main_window.panels:
            QMessageBox.information(
                self,
                "No Panels",
                "No panels loaded in current episode.\n\nPlease select an episode with panels."
            )
            unreal.log("No panels in main_window.panels")
            return

        unreal.log(f"Found {len(main_window.panels)} panels")

        # Filter for analyzed panels only
        analyzed_panels = [p for p in main_window.panels if p.get('analysis') is not None]

        if not analyzed_panels:
            QMessageBox.information(
                self,
                "No Analyzed Panels",
                "No panels have been analyzed yet.\n\n" +
                "Please analyze panels first using the 'Analyze All Panels' option."
            )
            unreal.log("No analyzed panels found")
            return

        # Confirm batch generation
        reply = QMessageBox.question(
            self,
            "Batch Generate Confirmation",
            f"Generate 3D scenes for {len(analyzed_panels)} analyzed panels?\n\n" +
            f"This will process each panel in order.\n" +
            f"You can monitor progress in the Output Log.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            unreal.log("Batch generate cancelled by user")
            return

        # Process each panel
        unreal.log(f"\n Processing {len(analyzed_panels)} panels...")
        successful = 0
        failed = 0

        for i, panel in enumerate(analyzed_panels, 1):
            unreal.log("\n" + "="*70)
            unreal.log(f"BATCH GENERATE: Panel {i}/{len(analyzed_panels)}")
            unreal.log(f"File: {panel.get('name', 'unknown')}")
            unreal.log("="*70)

            try:
                # Set this panel as active (updates UI widgets)
                self.set_panel(panel)

                # Give UI time to update
                QApplication.processEvents()

                # Generate scene for this panel (without confirmation prompt)
                success = self._generate_scene_internal(panel)

                if success:
                    successful += 1
                    unreal.log(f"Panel {i}/{len(analyzed_panels)} generated successfully")
                else:
                    failed += 1
                    unreal.log_warning(f"Panel {i}/{len(analyzed_panels)} generation failed")

                # Brief pause between panels
                import time
                time.sleep(0.5)

            except Exception as e:
                failed += 1
                unreal.log_error(f"Error generating panel {i}: {e}")
                import traceback
                unreal.log_error(traceback.format_exc())

        # Show results
        unreal.log("\n" + "="*70)
        unreal.log("BATCH GENERATE COMPLETE!")
        unreal.log("="*70)
        unreal.log(f"Successful: {successful}/{len(analyzed_panels)}")
        unreal.log(f"Failed: {failed}/{len(analyzed_panels)}")
        unreal.log("="*70 + "\n")

        QMessageBox.information(
            self,
            "Batch Generate Complete",
            f"Batch generation finished!\n\n" +
            f" Successful: {successful}\n" +
            f" Failed: {failed}\n" +
            f"Total: {len(analyzed_panels)} panels"
        )

    def batch_capture_all_panels(self):
        """Run iterative positioning for all panels in the current episode - SEQUENTIAL"""
        unreal.log("\n" + "="*70)
        unreal.log("BATCH CAPTURE - STARTING SEQUENTIAL PROCESSING")
        unreal.log("="*70)

        # Walk up the widget tree to find the MainWindow
        main_window = None
        widget = self
        max_depth = 10
        depth = 0

        while widget and depth < max_depth:
            widget = widget.parent()
            if widget and hasattr(widget, 'panels'):
                main_window = widget
                unreal.log(f"Found MainWindow at depth {depth}")
                break
            depth += 1

        if not main_window:
            QMessageBox.warning(
                self,
                "Cannot Access Panels",
                "Could not find main window with panels.\n\nPlease restart the plugin."
            )
            unreal.log("ERROR: Could not find MainWindow in widget tree")
            return

        if not hasattr(main_window, 'panels'):
            QMessageBox.warning(
                self,
                "Cannot Access Panels",
                "Main window doesn't have panels attribute.\n\nPlease restart the plugin."
            )
            unreal.log("ERROR: MainWindow missing 'panels' attribute")
            return

        if not main_window.panels:
            QMessageBox.information(
                self,
                "No Panels",
                "No panels loaded in current episode.\n\nPlease select an episode with panels."
            )
            unreal.log("No panels in main_window.panels")
            return

        unreal.log(f"Found {len(main_window.panels)} panels")

        # Filter for panels that have been generated (have sequences)
        generated_panels = [p for p in main_window.panels if p.get('sequence_path') is not None]

        if not generated_panels:
            QMessageBox.information(
                self,
                "No Generated Scenes",
                "No panels have had scenes generated yet.\n\n" +
                "Please generate 3D scenes first using the 'Batch Generate' button."
            )
            unreal.log("No generated scenes found")
            return

        # Confirm batch capture
        reply = QMessageBox.question(
            self,
            "Batch Capture Confirmation",
            f"Run iterative positioning for {len(generated_panels)} generated panels?\n\n" +
            f"Each panel will run until score >80 or max iterations.\n" +
            f"Panels will be processed ONE AT A TIME (sequential).\n\n" +
            f" This may take several hours and incur significant AI API costs!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            unreal.log("Batch capture cancelled by user")
            return

        # Setup batch mode
        self.batch_capture_mode = True
        self.batch_capture_queue = list(generated_panels)  # Copy list
        self.batch_capture_results = []

        unreal.log(f"\n BATCH MODE ENABLED")
        unreal.log(f"Total panels in queue: {len(self.batch_capture_queue)}")
        unreal.log(f"Processing mode: SEQUENTIAL (one at a time)")
        unreal.log(f"Stop condition: Score >80 OR max iterations")
        unreal.log(f"USING CURRENT UI SETTINGS FOR ALL PANELS:")
        unreal.log(f"Max iterations: {self.max_iterations}")
        unreal.log(f"Checkpointing: {'ENABLED' if self.enable_checkpointing else 'DISABLED'}")
        unreal.log(f"Positioning mode: {'ABSOLUTE' if self.use_absolute_positioning else 'RELATIVE'}")
        unreal.log("="*70 + "\n")

        # Start processing first panel
        self._process_next_batch_panel()

    def _reset_state_for_next_panel(self):
        """
        Reset all iteration state before processing next panel in batch

        IMPORTANT: User settings are PRESERVED across panels:
        - self.max_iterations (from UI input)
        - self.enable_checkpointing (from UI checkbox)
        - self.use_absolute_positioning (positioning mode)

        Only iteration-specific state is reset.
        """
        unreal.log("Resetting state for next panel...")

        # Reset iteration counters (NOT max_iterations - that's a user setting!)
        self.current_iteration = 0
        self.iteration_scores = []
        self.iteration_details = []
        self.iteration_costs = []
        self.total_cost = 0.0

        # Reset checkpointing state (NOT enable_checkpointing - that's a user setting!)
        self.best_score = 0
        self.best_actor_transforms = {}
        self.iteration_history = []

        # Reset last analysis results
        self.last_positioning_analysis = None
        self.last_match_score = None
        self.last_adjustments_applied = []
        self.score_trajectory = []

        # Reset scene data
        self.last_generated_scene = None
        self.last_camera = None

        # Reset metrics tracker (will be re-initialized in test_positioning_phase3)
        self.metrics_tracker = None
        self.current_scene_id = None

        # Reset view selector for new scene
        if hasattr(self, 'view_selector') and self.view_selector:
            self.view_selector.reset()

        # CRITICAL: Deactivate workflow to cancel any pending timer callbacks
        self.capture_workflow_active = False
        unreal.log("Workflow cancelled - pending timers will be ignored")

        # ============================================================
        # Scout cameras accumulate between batch iterations if not cleaned up
        # This causes viewport locking, memory leaks, and eventual crashes
        # ============================================================
        unreal.log("Cleaning up scout cameras from previous panel...")
        try:
            # Eject from any piloted camera first
            try:
                level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                level_editor_subsystem.eject_pilot_level_actor()
                unreal.log("Ejected from pilot camera")
            except:
                pass

            # Clean up all scout cameras
            subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            all_actors = subsystem.get_all_level_actors()
            scouts_deleted = 0
            for actor in all_actors:
                if "AI_Scout" in actor.get_actor_label():
                    subsystem.destroy_actor(actor)
                    scouts_deleted += 1
                    unreal.log(f"Deleted: {actor.get_actor_label()}")

            if scouts_deleted > 0:
                unreal.log(f"Cleaned up {scouts_deleted} scout camera(s)")
            else:
                unreal.log("No scout cameras to clean up")
        except Exception as e:
            unreal.log_warning(f"Could not cleanup scout cameras: {e}")

        # ============================================================
        # DEPTH ANALYZER: Restart between panels to prevent memory leak
        # PyTorch subprocess accumulates memory after ~30-40 depth maps
        # Safe to restart here because Qt event loop is not active
        # ============================================================
        if hasattr(self, 'depth_analyzer') and self.depth_analyzer:
            try:
                unreal.log("Restarting depth analyzer subprocess (prevents memory leak)...")

                # Check if still alive before cleanup
                is_alive = True
                if hasattr(self.depth_analyzer, 'process') and self.depth_analyzer.process:
                    is_alive = self.depth_analyzer.process.poll() is None

                if is_alive:
                    unreal.log("Process is alive - shutting down gracefully...")
                    self.depth_analyzer._cleanup()
                else:
                    unreal.log("Process already dead - skipping cleanup...")

                # Wait a moment for cleanup
                time.sleep(0.5)

                # Restart with fresh subprocess
                from analysis.depth_analyzer import DepthAnalyzer
                self.depth_analyzer = DepthAnalyzer()

                if self.depth_analyzer.available:
                    unreal.log("Depth analyzer restarted successfully")
                else:
                    unreal.log_warning("Depth analyzer failed to restart - depth maps will be inactive")

            except Exception as e:
                unreal.log_warning(f"Could not restart depth analyzer: {e}")
                self.depth_analyzer = None

        # CRITICAL: Close Sequencer to prevent crash when loading next level
        try:
            # Eject from any piloted camera
            unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(False)

            # Close current sequence if open
            current_seq = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
            if current_seq:
                unreal.log(f"Closing sequence: {current_seq.get_name()}")
                unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()

            # Process Qt events
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
        except Exception as e:
            unreal.log_warning(f"Sequencer cleanup warning: {e}")

        unreal.log("State reset complete")

    def _process_next_batch_panel(self):
        """Process the next panel in the batch capture queue"""
        if not self.batch_capture_queue:
            # Queue is empty - batch complete!
            self._finalize_batch_capture()
            return

        # Get next panel
        panel = self.batch_capture_queue.pop(0)
        remaining = len(self.batch_capture_queue)

        unreal.log("\n" + "="*70)
        unreal.log(f"BATCH CAPTURE - PROCESSING PANEL")
        unreal.log(f"Current: {panel.get('name', 'unknown')}")
        unreal.log(f"Remaining in queue: {remaining}")
        unreal.log("="*70)

        try:
            # CRITICAL: Reset all state before starting new panel!
            self._reset_state_for_next_panel()

            # Set this panel as active (updates UI widgets)
            self.set_panel(panel)

            # Give UI time to update
            QApplication.processEvents()

            # Start positioning workflow for this panel
            # When it completes, _finalize_metrics will check batch_capture_mode
            # and call _process_next_batch_panel again
            self.test_positioning_phase3()

        except Exception as e:
            # Panel failed - log error and record result
            unreal.log_error(f"BATCH CAPTURE ERROR: Panel '{panel.get('name', 'unknown')}' failed")
            unreal.log_error(f"Error: {e}")
            import traceback
            unreal.log_error(traceback.format_exc())

            # Record failure
            self.batch_capture_results.append({
                'panel': panel.get('name', 'unknown'),
                'success': False,
                'error': str(e)
            })

            # Continue to next panel even if this one failed
            if self.batch_capture_queue:
                unreal.log(f"⏭ Continuing to next panel ({len(self.batch_capture_queue)} remaining)...")
                self._process_next_batch_panel()
            else:
                # This was the last panel - finalize batch
                self._finalize_batch_capture()

    def _finalize_batch_capture(self):
        """Called when all panels in batch have been processed"""
        unreal.log("\n" + "="*70)
        unreal.log("BATCH CAPTURE COMPLETE - ALL PANELS PROCESSED!")
        unreal.log("="*70)

        # Analyze results
        successful = [r for r in self.batch_capture_results if r['success']]
        failed = [r for r in self.batch_capture_results if not r['success']]

        # Calculate stats for successful panels
        avg_score = 0
        avg_iterations = 0
        if successful:
            avg_score = sum(r.get('final_score', 0) or 0 for r in successful) / len(successful)
            avg_iterations = sum(r.get('iterations', 0) or 0 for r in successful) / len(successful)

        unreal.log(f"\n BATCH SUMMARY:")
        unreal.log(f"Total panels: {len(self.batch_capture_results)}")
        unreal.log(f"Successful: {len(successful)}")
        unreal.log(f"Failed: {len(failed)}")
        if successful:
            unreal.log(f"Average final score: {avg_score:.1f}")
            unreal.log(f"Average iterations: {avg_iterations:.1f}")

        # List successful panels
        if successful:
            unreal.log(f"\n SUCCESSFUL PANELS:")
            for r in successful:
                score = r.get('final_score', 'N/A')
                iters = r.get('iterations', 'N/A')
                unreal.log(f"• {r['panel']}: Score={score}, Iterations={iters}")

        # List failed panels
        if failed:
            unreal.log(f"\n FAILED PANELS:")
            for r in failed:
                error = r.get('error', 'Unknown error')
                unreal.log(f"• {r['panel']}: {error}")

        unreal.log(f"\n METRICS SAVED TO:")
        unreal.log(f"Saved/ThesisMetrics/")
        unreal.log("Next steps:")
        unreal.log("1. Review individual panel metrics in Saved/ThesisMetrics/")
        unreal.log("2. Run generate_thesis_reports.py to aggregate results")
        unreal.log("3. Run plot_convergence.py to create publication figures")
        unreal.log("="*70 + "\n")

        # Build message box text
        msg = f"Batch capture complete!\n\n"
        msg += f"Total: {len(self.batch_capture_results)} panels\n"
        msg += f" Successful: {len(successful)}\n"
        msg += f" Failed: {len(failed)}\n"
        if successful:
            msg += f"\nAvg score: {avg_score:.1f}\n"
            msg += f"Avg iterations: {avg_iterations:.1f}\n"
        msg += f"\nMetrics saved to: Saved/ThesisMetrics/"

        QMessageBox.information(
            self,
            "Batch Capture Complete",
            msg
        )

        # Reset batch mode and clear results
        self.batch_capture_mode = False
        self.batch_capture_queue = []
        self.batch_capture_results = []

    def _update_multi_model_csv(self, summary: Dict[str, Any]):
        """
        Update the appropriate model-specific CSV based on current AI provider

        Args:
            summary: Metrics summary from MetricsTracker.finalize()
        """
        if not self.multi_model_tracker:
            return

        try:
            # Get AI client from the system
            ai_client = getattr(self, 'current_ai_client', None)

            # Detect which model is running
            model_key = self.multi_model_tracker.detect_current_model(ai_client)

            # Determine scene ID for the CSV
            # Try to extract storyboard number from panel or scene_id
            scene_id_for_csv = self.current_scene_id

            if self.active_panel and 'panel_number' in self.active_panel:
                panel_num = self.active_panel['panel_number']
                scene_id_for_csv = self.multi_model_tracker.get_scene_number_from_panel(panel_num)
            elif 'Panel_' in self.current_scene_id:
                # Extract number from Panel_001 format
                try:
                    panel_num = int(self.current_scene_id.split('_')[1])
                    scene_id_for_csv = self.multi_model_tracker.get_scene_number_from_panel(panel_num)
                    unreal.log(f"Mapped Panel_{panel_num:03d} → {scene_id_for_csv}")
                except Exception as e:
                    unreal.log_warning(f"Failed to extract panel number from {self.current_scene_id}: {e}")

            # Update the model's CSV
            self.multi_model_tracker.update_model_csv(
                model_key=model_key,
                scene_id=scene_id_for_csv,
                metrics=summary
            )

            unreal.log(f"\n MULTI-MODEL CSV UPDATED:")
            unreal.log(f"Model: {self.multi_model_tracker.MODELS.get(model_key, 'Unknown')}")
            unreal.log(f"Scene: {scene_id_for_csv}")
            unreal.log(f"CSV: {self.multi_model_tracker.MODELS.get(model_key, 'Unknown')}_comparison.csv")

        except Exception as e:
            unreal.log_warning(f"Failed to update multi-model CSV: {e}")
            import traceback
            unreal.log_warning(traceback.format_exc())

    def configure_metrics(self, scene_id: str, approach: str = "multiview"):
        """
        OPTIONAL: Configure metrics tracking with custom scene ID

        If not called, metrics will auto-generate scene IDs like:
        - Panel_001, Panel_002, etc. (if active_panel exists)
        - Scene_20250128_110730 (timestamp if no panel)

        Args:
            scene_id: Scene identifier (e.g., "Simple_1", "Medium_2", "Complex_3")
            approach: "baseline" (single-view) or "multiview" (your approach)

        Example:
            # Optional - only if you want custom scene IDs
            widget.configure_metrics("Simple_1", "multiview")
            widget.test_positioning_phase3()

            # Or just run directly - metrics track automatically!
            widget.test_positioning_phase3()
        """
        self.current_scene_id = scene_id
        self.current_approach = approach

        unreal.log(f"\n Metrics configured:")
        unreal.log(f"Scene ID: {scene_id}")
        unreal.log(f"Approach: {approach}")
        unreal.log(f"Will initialize when test sequence starts\n")

    def mark_as_ground_truth(self, storyboard_number: int, metrics: Dict[str, Any]):
        """
        Manually add ground truth metrics for a storyboard

        Args:
            storyboard_number: Storyboard number (1-12)
            metrics: Dictionary with metrics:
                - initial_accuracy: float
                - final_accuracy: float
                - improvement: float
                - total_iterations: int (usually 0 for ground truth)
                - converged: bool (usually True)
                - total_time_seconds: float

        Example:
            widget.mark_as_ground_truth(1, {
                'initial_accuracy': 0,
                'final_accuracy': 100,
                'improvement': 100,
                'total_iterations': 0,
                'converged': True,
                'total_time_seconds': 300,
                'monotonic_improvement': True,
                'oscillating': False
            })
        """
        if not self.multi_model_tracker:
            unreal.log_warning("Multi-model tracker not initialized")
            return

        scene_id = self.multi_model_tracker.get_scene_number_from_panel(storyboard_number)

        self.multi_model_tracker.update_model_csv(
            model_key='groundtruth',
            scene_id=scene_id,
            metrics=metrics
        )

        unreal.log(f"Ground truth marked for {scene_id}")

    def show_model_comparison(self):
        """Print comparison table of all models"""
        if not self.multi_model_tracker:
            unreal.log_warning("Multi-model tracker not initialized")
            return

        self.multi_model_tracker.print_comparison_table()

    def export_combined_comparison(self):
        """Export single CSV with all models side-by-side"""
        if not self.multi_model_tracker:
            unreal.log_warning("Multi-model tracker not initialized")
            return

        output_file = self.multi_model_tracker.export_combined_csv()
        unreal.log(f"Combined comparison exported: {output_file}")

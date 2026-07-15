# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Features Settings Tab for StoryboardTo3D

One place to switch every optional feature on or off. Each toggle maps
to the exact settings key the feature reads at runtime, and every
default here matches the in-code default, so an untouched tab changes
nothing. Sections are written copy-then-overwrite so sibling keys that
only live in global_settings.json survive a dialog save.
"""

import unreal

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


class FeaturesTab(QWidget):
    """Optional-features settings tab: every experimental toggle in one place"""

    settings_changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Scene extras
        scene_group = QGroupBox("Scene Extras")
        scene_layout = QVBoxLayout()

        self.mood_lighting_check = QCheckBox("Mood lighting (map the panel's mood to light and fog presets)")
        self.mood_lighting_check.setToolTip(
            "Applies a lighting preset (night, golden hour, noir, tense...) from the "
            "panel's analyzed mood after the scene builds. Spawned lights are tagged "
            "StoryboardMoodLighting.")
        self.mood_lighting_check.stateChanged.connect(self.on_change)
        scene_layout.addWidget(self.mood_lighting_check)

        self.auto_animation_check = QCheckBox("Animation picker (play matched animations on skeletal characters)")
        self.auto_animation_check.setToolTip(
            "Matches each character's action text (running, sitting...) against the "
            "show's animation_library.json and plays the clip on skeletal actors. "
            "See samples/animation_library.sample.json for the format.")
        self.auto_animation_check.stateChanged.connect(self.on_change)
        scene_layout.addWidget(self.auto_animation_check)

        self.camera_moves_check = QCheckBox("Camera moves (shot type drives push-in / drift / pan)")
        self.camera_moves_check.setToolTip(
            "Keys a subtle camera move on each shot sequence: close-ups push in, "
            "mediums drift, wides pan.")
        self.camera_moves_check.stateChanged.connect(self.on_change)
        scene_layout.addWidget(self.camera_moves_check)

        scene_group.setLayout(scene_layout)
        layout.addWidget(scene_group)

        # Asset matching and generation
        matching_group = QGroupBox("Asset Matching && Generation")
        matching_layout = QVBoxLayout()

        self.semantic_matching_check = QCheckBox("Semantic asset matching (embeddings; needs OpenAI key)")
        self.semantic_matching_check.setToolTip(
            "Matches described objects to library assets by meaning ('canine' finds "
            "the dog) using OpenAI embeddings. Falls back to fuzzy matching on any failure.")
        self.semantic_matching_check.stateChanged.connect(self.on_change)
        matching_layout.addWidget(self.semantic_matching_check)

        self.gen3d_check = QCheckBox("Generative 3D fallback (create missing assets; needs Meshy or Tripo key)")
        self.gen3d_check.setToolTip(
            "When no library asset matches at all, generate the missing character or "
            "prop via a text-to-3D API, import it, and add it to the show library so "
            "it is reused instead of regenerated. Generation can take 1-3 minutes per "
            "asset. Keys: MESHY_API_KEY / TRIPO_API_KEY.")
        self.gen3d_check.stateChanged.connect(self.on_change)
        matching_layout.addWidget(self.gen3d_check)

        gen3d_row = QHBoxLayout()
        gen3d_row.addSpacing(24)
        gen3d_row.addWidget(QLabel("Provider:"))
        self.gen3d_provider_combo = QComboBox()
        self.gen3d_provider_combo.addItems(["meshy", "tripo"])
        self.gen3d_provider_combo.currentTextChanged.connect(self.on_change)
        gen3d_row.addWidget(self.gen3d_provider_combo)
        gen3d_row.addWidget(QLabel("Max generations per run:"))
        self.gen3d_max_spin = QSpinBox()
        self.gen3d_max_spin.setRange(0, 10)
        self.gen3d_max_spin.setValue(3)
        self.gen3d_max_spin.valueChanged.connect(self.on_change)
        gen3d_row.addWidget(self.gen3d_max_spin)
        gen3d_row.addStretch()
        matching_layout.addLayout(gen3d_row)

        gen3d_mode_row = QHBoxLayout()
        gen3d_mode_row.addSpacing(24)
        gen3d_mode_row.addWidget(QLabel("Generation mode:"))
        self.gen3d_mode_combo = QComboBox()
        self.gen3d_mode_combo.addItem("Text prompt (default)", "text")
        self.gen3d_mode_combo.addItem("Panel image crop", "image")
        self.gen3d_mode_combo.setToolTip(
            "Text prompt: generate missing assets from their name and "
            "description (existing behavior). Panel image crop: ask the vision "
            "provider for the entity's bounding box in the storyboard panel, "
            "crop it out, and generate from that image (Tripo only). Any "
            "failure in image mode falls back to the text prompt.")
        self.gen3d_mode_combo.currentIndexChanged.connect(self.on_change)
        gen3d_mode_row.addWidget(self.gen3d_mode_combo)
        gen3d_mode_row.addStretch()
        matching_layout.addLayout(gen3d_mode_row)

        self.genanim_check = QCheckBox("Generative animation fallback (create missing clips; needs Tripo or DeepMotion key)")
        self.genanim_check.setToolTip(
            "When no animation_library.json clip matches a character's action text, "
            "generate one via an animation API, import it to "
            "/Game/StoryboardTo3D/GeneratedAnims, and add it to the show library so "
            "it is reused instead of regenerated. Generation can take 1-4 minutes per "
            "clip and blocks the scene build while polling. Clips arrive on the "
            "provider's skeleton; retarget them to your characters with UE's IK "
            "Retargeter. Only runs when the Animation picker above is also on. "
            "Tripo needs TRIPO_API_KEY plus a one-time rig task id "
            "(genanim.tripo_rig_task_id); DeepMotion needs partner API credentials "
            "and base URL.")
        self.genanim_check.stateChanged.connect(self.on_change)
        matching_layout.addWidget(self.genanim_check)

        genanim_row = QHBoxLayout()
        genanim_row.addSpacing(24)
        genanim_row.addWidget(QLabel("Provider:"))
        self.genanim_provider_combo = QComboBox()
        self.genanim_provider_combo.addItems(["tripo", "deepmotion"])
        self.genanim_provider_combo.setToolTip(
            "tripo: preset clips (walk, run, jump...) retargeted onto a rigged proxy, "
            "about $0.10 per clip. deepmotion: true text-to-animation prompts, "
            "partner-gated API with unpublished pricing.")
        self.genanim_provider_combo.currentTextChanged.connect(self.on_change)
        genanim_row.addWidget(self.genanim_provider_combo)
        genanim_row.addWidget(QLabel("Max generations per run:"))
        self.genanim_max_spin = QSpinBox()
        self.genanim_max_spin.setRange(0, 10)
        self.genanim_max_spin.setValue(2)
        self.genanim_max_spin.valueChanged.connect(self.on_change)
        genanim_row.addWidget(self.genanim_max_spin)
        genanim_row.addStretch()
        matching_layout.addLayout(genanim_row)

        matching_group.setLayout(matching_layout)
        layout.addWidget(matching_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout()

        self.optimize_images_check = QCheckBox("Optimize image transport (downscale + JPEG before API calls)")
        self.optimize_images_check.setToolTip(
            "Downscales captures to a 1288 px long edge and re-encodes as JPEG before "
            "sending to the AI: typically 5-10x smaller payloads, faster and cheaper, "
            "no effect on scene judgment. On by default; turn off for byte-identical "
            "legacy payloads (e.g. exact thesis reproduction).")
        self.optimize_images_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.optimize_images_check)

        self.reduced_views_check = QCheckBox("Reduced refinement views (7 views on iteration 1, then hero+top+right)")
        self.reduced_views_check.setToolTip(
            "Refinement iterations capture 3 of 7 views, saving roughly a minute per "
            "iteration. The first iteration always captures the full set so the model "
            "gets complete spatial context.")
        self.reduced_views_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.reduced_views_check)

        self.optimized_prompts_check = QCheckBox(
            "Optimized prompts (50-66% fewer tokens) (takes effect after editor restart)")
        self.optimized_prompts_check.setToolTip(
            "Uses the compressed prompt builder and analyzer for AI calls. The flag "
            "is read once at module import, so toggling it requires restarting the "
            "editor (or reloading the plugin's Python) to apply.")
        self.optimized_prompts_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.optimized_prompts_check)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Cost
        cost_group = QGroupBox("API Cost")
        cost_layout = QVBoxLayout()

        self.files_api_check = QCheckBox("Files API image reuse (upload each panel once, Claude only)")
        self.files_api_check.setToolTip(
            "Uploads each image once and references it by ID instead of re-sending "
            "base64 every call. Applies wherever the Claude provider is built via the "
            "provider factory (auto-detect or explicit Claude selection). Falls back "
            "to inline images on any failure.")
        self.files_api_check.stateChanged.connect(self.on_change)
        cost_layout.addWidget(self.files_api_check)

        self.scoring_model_check = QCheckBox("Cheap re-scoring model (per-iteration scoring on Haiku)")
        self.scoring_model_check.setToolTip(
            "Runs scoring passes (external validation second-model checks and future "
            "refinement-loop wiring) on claude-haiku-4-5 while the main model handles "
            "full analysis. Does not yet apply to the main refinement loop.")
        self.scoring_model_check.stateChanged.connect(self.on_change)
        cost_layout.addWidget(self.scoring_model_check)

        cost_group.setLayout(cost_layout)
        layout.addWidget(cost_group)

        note = QLabel(
            "All features are off by default except image transport optimization. "
            "External validation lives on the General tab. Defaults here always match "
            "the plugin's in-code defaults.")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def on_change(self):
        """Emit change signal"""
        self.settings_changed.emit()

    def load_settings(self):
        """Load settings into UI"""
        scene = self.settings.get('scene', {})
        sequence = self.settings.get('sequence', {})
        asset_library = self.settings.get('asset_library', {})
        gen3d = self.settings.get('gen3d', {})
        genanim = self.settings.get('genanim', {})
        performance = self.settings.get('performance', {})
        cost = self.settings.get('cost', {})

        self.mood_lighting_check.setChecked(bool(scene.get('apply_mood_lighting', False)))
        self.auto_animation_check.setChecked(bool(scene.get('auto_animation', False)))
        self.camera_moves_check.setChecked(bool(sequence.get('camera_moves', False)))

        self.semantic_matching_check.setChecked(bool(asset_library.get('semantic_matching', False)))
        self.gen3d_check.setChecked(bool(gen3d.get('enabled', False)))
        self.gen3d_provider_combo.setCurrentText(str(gen3d.get('provider', 'meshy')))
        try:
            self.gen3d_max_spin.setValue(int(gen3d.get('max_per_run', 3)))
        except (TypeError, ValueError):
            self.gen3d_max_spin.setValue(3)
        mode = str(gen3d.get('mode', 'text')).strip().lower()
        mode_index = self.gen3d_mode_combo.findData(mode)
        self.gen3d_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)

        self.genanim_check.setChecked(bool(genanim.get('enabled', False)))
        self.genanim_provider_combo.setCurrentText(str(genanim.get('provider', 'tripo')))
        try:
            self.genanim_max_spin.setValue(int(genanim.get('max_per_run', 2)))
        except (TypeError, ValueError):
            self.genanim_max_spin.setValue(2)

        self.optimize_images_check.setChecked(bool(performance.get('optimize_images', True)))
        self.reduced_views_check.setChecked(bool(performance.get('reduced_refinement_views', False)))

        # ai_settings.use_optimized_prompts lives in the AI tab's section but
        # is owned by this checkbox; read-only access here cannot clobber
        ai_settings = self.settings.get('ai_settings', {})
        self.optimized_prompts_check.setChecked(bool(ai_settings.get('use_optimized_prompts', False)))

        self.files_api_check.setChecked(bool(cost.get('use_files_api', False)))
        self.scoring_model_check.setChecked(bool(cost.get('use_scoring_model', False)))

    def get_settings(self):
        """Get settings from UI"""
        # Copy-then-overwrite so sibling keys (e.g. gen3d.timeout_seconds,
        # cost.scoring_model) survive the dialog's wholesale section replace
        scene = dict(self.settings.get('scene', {}))
        scene['apply_mood_lighting'] = self.mood_lighting_check.isChecked()
        scene['auto_animation'] = self.auto_animation_check.isChecked()

        sequence = dict(self.settings.get('sequence', {}))
        sequence['camera_moves'] = self.camera_moves_check.isChecked()

        asset_library = dict(self.settings.get('asset_library', {}))
        asset_library['semantic_matching'] = self.semantic_matching_check.isChecked()

        gen3d = dict(self.settings.get('gen3d', {}))
        gen3d['enabled'] = self.gen3d_check.isChecked()
        gen3d['provider'] = self.gen3d_provider_combo.currentText()
        gen3d['max_per_run'] = self.gen3d_max_spin.value()
        gen3d['mode'] = self.gen3d_mode_combo.currentData() or 'text'

        # Copy-then-overwrite so sibling keys (e.g. genanim.timeout_seconds,
        # genanim.tripo_rig_task_id) survive the dialog save
        genanim = dict(self.settings.get('genanim', {}))
        genanim['enabled'] = self.genanim_check.isChecked()
        genanim['provider'] = self.genanim_provider_combo.currentText()
        genanim['max_per_run'] = self.genanim_max_spin.value()

        performance = dict(self.settings.get('performance', {}))
        performance['optimize_images'] = self.optimize_images_check.isChecked()
        performance['reduced_refinement_views'] = self.reduced_views_check.isChecked()

        cost = dict(self.settings.get('cost', {}))
        cost['use_files_api'] = self.files_api_check.isChecked()
        cost['use_scoring_model'] = self.scoring_model_check.isChecked()

        return {
            'scene': scene,
            'sequence': sequence,
            'asset_library': asset_library,
            'gen3d': gen3d,
            'genanim': genanim,
            'performance': performance,
            'cost': cost
        }

    def on_settings_saved(self):
        """Called after settings are saved.

        Writes ai_settings.use_optimized_prompts here via set_setting rather
        than returning an 'ai_settings' section from get_settings: the dialog
        merges tab sections with dict.update(), so two tabs returning the
        same top-level section would clobber each other wholesale (this tab
        runs after ai_tab and would wipe its freshly saved keys, or vice
        versa). set_setting mutates exactly one nested key on the settings
        manager's already-saved dict and auto-saves, so ai_tab's sibling keys
        provably survive.
        """
        try:
            from core.settings_manager import set_setting
            set_setting('ai_settings.use_optimized_prompts',
                        self.optimized_prompts_check.isChecked())
        except Exception as e:
            unreal.log_warning(
                f"Could not save ai_settings.use_optimized_prompts: {e}")

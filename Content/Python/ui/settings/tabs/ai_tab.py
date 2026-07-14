# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
AI Settings Tab for StoryboardTo3D - COMPLETE MODEL LIST
ALL VISION MODELS + GPT-5 PRO + ALL CLAUDE MODELS
"""

import unreal
from pathlib import Path

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


class AISettingsTab(QWidget):
    """AI configuration settings tab - COMPLETE MODEL LIST"""

    settings_changed = Signal()

    # Built-in Claude model list - used at startup and as the fallback when
    # the Anthropic Models API cannot be reached via "Refresh Models"
    CLAUDE_FALLBACK_MODELS = [
        # === CURRENT GENERATION ===
        "claude-sonnet-4-6",             # Recommended default (vision + sampling params)
        "claude-haiku-4-5",              # Fast + cheap for scoring passes
        "claude-opus-4-1-20250805",      # Most powerful of the sampling-compatible line

        # === LEGACY (thesis study model) ===
        "claude-sonnet-4-5-20250929",    # Model used in the published calibration research
        "claude-sonnet-4-20250514",
    ]

    # Built-in OpenAI model list - used at startup and as the fallback when
    # the OpenAI Models API cannot be reached via "Refresh Models"
    OPENAI_FALLBACK_MODELS = [
        # === GPT-5 SERIES (Aug 2025) ===
        "gpt-5",                    # Flagship reasoning + vision
        "gpt-5-pro",                # Extended reasoning (GPT-5 Pro)
        "gpt-5-mini",               # Faster, cheaper
        "gpt-5-nano",               # Fastest, cheapest
        "gpt-5-chat",               # Chat-optimized

        # === O-SERIES (Reasoning + Vision) ===
        "o3",                       # Advanced reasoning
        "o3-mini",                  # Fast reasoning
        "o3-pro",                   # Professional reasoning
        "o4-mini",                  # Latest mini reasoning
        "o4-mini-high",             # Enhanced reasoning

        # === GPT-4.1 SERIES (Apr 2025) ===
        "gpt-4.1",                  # 1M context, best coding
        "gpt-4.1-mini",             # Fast & efficient
        "gpt-4.1-nano",             # Fastest & cheapest

        # === GPT-4o SERIES (May 2024) ===
        "gpt-4o",                   # Proven balanced model
        "gpt-4o-mini",              # Budget option
        "chatgpt-4o-latest",        # Latest ChatGPT version

        # === GPT-4.5 SERIES ===
        "gpt-4.5-preview",          # Being deprecated July 2025

        # === GPT-4 LEGACY ===
        "gpt-4",                    # Original GPT-4
        "gpt-4-turbo",              # Faster version
        "gpt-4-vision-preview"      # Original vision model
    ]

    # Built-in Gemini model list - used at startup and as the fallback when
    # the Gemini Models API cannot be reached via "Refresh Models"
    GEMINI_FALLBACK_MODELS = [
        "gemini-2.5-pro",           # Strongest reasoning + vision
        "gemini-2.5-flash",         # Recommended default (fast + low cost)
    ]

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # AI Provider Selection
        provider_group = QGroupBox("AI Provider Selection")
        provider_layout = QVBoxLayout()

        provider_select_layout = QHBoxLayout()
        provider_select_layout.addWidget(QLabel("Active Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Auto", "LLaVA (Local)", "GPT-4 Vision (OpenAI)", "Claude (Anthropic)", "Gemini (Google)"])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        provider_select_layout.addWidget(self.provider_combo)
        provider_select_layout.addStretch()
        provider_layout.addLayout(provider_select_layout)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # === LLAVA (LOCAL) SETTINGS ===
        llava_group = QGroupBox("🏠 LLaVA (Local) - Free")
        llava_layout = QVBoxLayout()

        llava_url_layout = QHBoxLayout()
        llava_url_layout.addWidget(QLabel("Ollama URL:"))
        self.llava_url_edit = QLineEdit()
        self.llava_url_edit.setPlaceholderText("http://localhost:11434")
        self.llava_url_edit.textChanged.connect(self.on_change)
        llava_url_layout.addWidget(self.llava_url_edit)
        llava_layout.addLayout(llava_url_layout)

        test_llava_btn = QPushButton("Test LLaVA Connection")
        test_llava_btn.clicked.connect(self.test_llava)
        llava_layout.addWidget(test_llava_btn)

        llava_group.setLayout(llava_layout)
        layout.addWidget(llava_group)

        # === OPENAI SETTINGS ===
        openai_group = QGroupBox("🚀 GPT Vision (OpenAI) - Paid")
        openai_layout = QVBoxLayout()

        # OpenAI API Key (SEPARATE)
        openai_key_layout = QHBoxLayout()
        openai_key_layout.addWidget(QLabel("OpenAI API Key:"))
        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_api_key_edit.setPlaceholderText("sk-...")
        self.openai_api_key_edit.textChanged.connect(self.on_change)
        openai_key_layout.addWidget(self.openai_api_key_edit)

        self.show_openai_key_btn = QPushButton("👁")
        self.show_openai_key_btn.setCheckable(True)
        self.show_openai_key_btn.toggled.connect(lambda checked: self.toggle_key_visibility(
            self.openai_api_key_edit, self.show_openai_key_btn, checked
        ))
        self.show_openai_key_btn.setMaximumWidth(30)
        openai_key_layout.addWidget(self.show_openai_key_btn)
        openai_layout.addLayout(openai_key_layout)

        # OpenAI Model - ALL VISION MODELS
        openai_model_layout = QHBoxLayout()
        openai_model_layout.addWidget(QLabel("Model:"))
        self.openai_model_combo = QComboBox()
        self.openai_model_combo.addItems(self.OPENAI_FALLBACK_MODELS)
        self.openai_model_combo.currentTextChanged.connect(self.on_change)
        openai_model_layout.addWidget(self.openai_model_combo)

        # Refresh the dropdown from the live OpenAI Models API
        self.refresh_openai_models_btn = QPushButton("🔄 Refresh Models")
        self.refresh_openai_models_btn.setToolTip("Fetch the current model list from the OpenAI API (requires API key)")
        self.refresh_openai_models_btn.clicked.connect(self.refresh_openai_models)
        openai_model_layout.addWidget(self.refresh_openai_models_btn)

        openai_model_layout.addStretch()
        openai_layout.addLayout(openai_model_layout)

        # Model info label
        info_label = QLabel("💡 All models support vision | o-series = reasoning | GPT-5 = newest")
        info_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        info_label.setWordWrap(True)
        openai_layout.addWidget(info_label)

        test_openai_btn = QPushButton("Test OpenAI Connection")
        test_openai_btn.clicked.connect(self.test_openai)
        openai_layout.addWidget(test_openai_btn)

        openai_group.setLayout(openai_layout)
        layout.addWidget(openai_group)

        # === ANTHROPIC (CLAUDE) SETTINGS ===
        claude_group = QGroupBox("🧠 Claude (Anthropic) - Paid")
        claude_layout = QVBoxLayout()

        # Claude API Key (SEPARATE)
        claude_key_layout = QHBoxLayout()
        claude_key_layout.addWidget(QLabel("Anthropic API Key:"))
        self.claude_api_key_edit = QLineEdit()
        self.claude_api_key_edit.setEchoMode(QLineEdit.Password)
        self.claude_api_key_edit.setPlaceholderText("sk-ant-...")
        self.claude_api_key_edit.textChanged.connect(self.on_change)
        claude_key_layout.addWidget(self.claude_api_key_edit)

        self.show_claude_key_btn = QPushButton("👁")
        self.show_claude_key_btn.setCheckable(True)
        self.show_claude_key_btn.toggled.connect(lambda checked: self.toggle_key_visibility(
            self.claude_api_key_edit, self.show_claude_key_btn, checked
        ))
        self.show_claude_key_btn.setMaximumWidth(30)
        claude_key_layout.addWidget(self.show_claude_key_btn)
        claude_layout.addLayout(claude_key_layout)

        # Claude Model - ALL MODELS
        claude_model_layout = QHBoxLayout()
        claude_model_layout.addWidget(QLabel("Model:"))
        self.claude_model_combo = QComboBox()
        self.claude_model_combo.addItems(self.CLAUDE_FALLBACK_MODELS)
        self.claude_model_combo.currentTextChanged.connect(self.on_change)
        claude_model_layout.addWidget(self.claude_model_combo)

        # Refresh the dropdown from the live Anthropic Models API
        self.refresh_claude_models_btn = QPushButton("🔄 Refresh Models")
        self.refresh_claude_models_btn.setToolTip("Fetch the current model list from the Anthropic API (requires API key)")
        self.refresh_claude_models_btn.clicked.connect(self.refresh_claude_models)
        claude_model_layout.addWidget(self.refresh_claude_models_btn)

        claude_model_layout.addStretch()
        claude_layout.addLayout(claude_model_layout)

        # Claude info label
        claude_info_label = QLabel("⭐ Recommended: claude-sonnet-4-6 for best spatial reasoning | All support vision")
        claude_info_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        claude_info_label.setWordWrap(True)
        claude_layout.addWidget(claude_info_label)

        test_claude_btn = QPushButton("Test Claude Connection")
        test_claude_btn.clicked.connect(self.test_claude)
        claude_layout.addWidget(test_claude_btn)

        claude_group.setLayout(claude_layout)
        layout.addWidget(claude_group)

        # === GOOGLE GEMINI SETTINGS ===
        gemini_group = QGroupBox("✨ Google Gemini - Paid")
        gemini_layout = QVBoxLayout()

        # Gemini API Key (SEPARATE)
        gemini_key_layout = QHBoxLayout()
        gemini_key_layout.addWidget(QLabel("Gemini API Key:"))
        self.gemini_api_key_edit = QLineEdit()
        self.gemini_api_key_edit.setEchoMode(QLineEdit.Password)
        self.gemini_api_key_edit.setPlaceholderText("AIza...")
        self.gemini_api_key_edit.textChanged.connect(self.on_change)
        gemini_key_layout.addWidget(self.gemini_api_key_edit)

        self.show_gemini_key_btn = QPushButton("👁")
        self.show_gemini_key_btn.setCheckable(True)
        self.show_gemini_key_btn.toggled.connect(lambda checked: self.toggle_key_visibility(
            self.gemini_api_key_edit, self.show_gemini_key_btn, checked
        ))
        self.show_gemini_key_btn.setMaximumWidth(30)
        gemini_key_layout.addWidget(self.show_gemini_key_btn)
        gemini_layout.addLayout(gemini_key_layout)

        # Gemini Model
        gemini_model_layout = QHBoxLayout()
        gemini_model_layout.addWidget(QLabel("Model:"))
        self.gemini_model_combo = QComboBox()
        self.gemini_model_combo.addItems(self.GEMINI_FALLBACK_MODELS)
        self.gemini_model_combo.currentTextChanged.connect(self.on_change)
        gemini_model_layout.addWidget(self.gemini_model_combo)

        # Refresh the dropdown from the live Gemini Models API
        self.refresh_gemini_models_btn = QPushButton("🔄 Refresh Models")
        self.refresh_gemini_models_btn.setToolTip("Fetch the current model list from the Google Gemini API (requires API key)")
        self.refresh_gemini_models_btn.clicked.connect(self.refresh_gemini_models)
        gemini_model_layout.addWidget(self.refresh_gemini_models_btn)

        gemini_model_layout.addStretch()
        gemini_layout.addLayout(gemini_model_layout)

        # Gemini info label
        gemini_info_label = QLabel("⭐ Recommended: gemini-2.5-flash for fast, low-cost analysis | Both support vision")
        gemini_info_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        gemini_info_label.setWordWrap(True)
        gemini_layout.addWidget(gemini_info_label)

        gemini_group.setLayout(gemini_layout)
        layout.addWidget(gemini_group)

        # === MODEL SETTINGS ===
        model_group = QGroupBox("Model Settings")
        model_layout = QVBoxLayout()

        # Temperature
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setRange(0, 100)
        self.temperature_slider.setValue(70)
        self.temperature_slider.valueChanged.connect(self.on_temperature_changed)
        temp_layout.addWidget(self.temperature_slider)

        self.temperature_label = QLabel("0.7")
        self.temperature_label.setMinimumWidth(30)
        temp_layout.addWidget(self.temperature_label)
        temp_layout.addStretch()
        model_layout.addLayout(temp_layout)

        # Max tokens
        tokens_layout = QHBoxLayout()
        tokens_layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 8000)
        self.max_tokens_spin.setSingleStep(100)
        self.max_tokens_spin.setValue(2000)
        self.max_tokens_spin.valueChanged.connect(self.on_change)
        tokens_layout.addWidget(self.max_tokens_spin)
        tokens_layout.addStretch()
        model_layout.addLayout(tokens_layout)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # === ANALYSIS SETTINGS ===
        analysis_group = QGroupBox("Analysis Settings")
        analysis_layout = QVBoxLayout()

        #  CRITICAL: Multi-view capture toggle
        self.use_multiview_check = QCheckBox("Use Multi-View Capture (SceneCapture2D)")
        self.use_multiview_check.setChecked(False)  #  DISABLED BY DEFAULT (doesn't work with spawnables!)
        self.use_multiview_check.stateChanged.connect(self.on_change)
        analysis_layout.addWidget(self.use_multiview_check)

        multiview_note = QLabel("⚠️ Disable this if positioning doesn't change captures\n(Uses viewport screenshot instead - works with spawnables)")
        multiview_note.setStyleSheet("color: #ff8800; font-size: 10px; padding-left: 20px;")
        multiview_note.setWordWrap(True)
        analysis_layout.addWidget(multiview_note)

        # Auto-analyze
        self.auto_analyze_check = QCheckBox("Automatically analyze panels on import")
        self.auto_analyze_check.stateChanged.connect(self.on_change)
        analysis_layout.addWidget(self.auto_analyze_check)

        # Batch analysis
        self.batch_analysis_check = QCheckBox("Enable batch analysis")
        self.batch_analysis_check.stateChanged.connect(self.on_change)
        analysis_layout.addWidget(self.batch_analysis_check)

        # Analysis timeout
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Timeout:"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 120)
        self.timeout_spin.setSuffix(" seconds")
        self.timeout_spin.setValue(30)
        self.timeout_spin.valueChanged.connect(self.on_change)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        analysis_layout.addLayout(timeout_layout)

        # Retry on failure
        self.retry_check = QCheckBox("Retry on failure")
        self.retry_check.setChecked(True)
        self.retry_check.stateChanged.connect(self.on_change)
        analysis_layout.addWidget(self.retry_check)

        # Max retries
        retry_layout = QHBoxLayout()
        retry_layout.addWidget(QLabel("Max retries:"))
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 5)
        self.max_retries_spin.setValue(3)
        self.max_retries_spin.valueChanged.connect(self.on_change)
        retry_layout.addWidget(self.max_retries_spin)
        retry_layout.addStretch()
        analysis_layout.addLayout(retry_layout)

        analysis_group.setLayout(analysis_layout)
        layout.addWidget(analysis_group)

        layout.addStretch()

    def toggle_key_visibility(self, line_edit, button, checked):
        """Toggle API key visibility"""
        if checked:
            line_edit.setEchoMode(QLineEdit.Normal)
            button.setText("")
        else:
            line_edit.setEchoMode(QLineEdit.Password)
            button.setText("")

    def on_change(self):
        """Handle any change"""
        self.settings_changed.emit()

    def on_provider_changed(self, provider):
        """Handle provider change"""
        self.on_change()

    def on_temperature_changed(self, value):
        """Handle temperature slider change"""
        temp = value / 100.0
        self.temperature_label.setText(f"{temp:.1f}")
        self.on_change()

    def test_llava(self):
        """Test LLaVA connection"""
        progress = QProgressDialog("Testing LLaVA...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            import requests
            url = self.llava_url_edit.text() or "http://localhost:11434"
            response = requests.get(f"{url}/api/tags", timeout=5)

            progress.close()

            if response.status_code == 200:
                models = response.json().get('models', [])
                has_llava = any('llava' in m.get('name', '').lower() for m in models)

                if has_llava:
                    QMessageBox.information(self, "Success", " LLaVA is available and working!")
                else:
                    QMessageBox.warning(self, "Warning", "Ollama is running but LLaVA model not found.\nRun: ollama pull llava")
            else:
                QMessageBox.warning(self, "Failed", f"Ollama returned status {response.status_code}")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Connection failed: {str(e)}\n\nMake sure Ollama is running (ollama serve)")

    def test_openai(self):
        """Test OpenAI connection"""
        api_key = self.openai_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your OpenAI API key first")
            return

        progress = QProgressDialog("Testing OpenAI...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            import sys
            from pathlib import Path
            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            from core.ai_providers import GPT4VisionProvider

            gpt4v = GPT4VisionProvider(api_key=api_key)

            progress.close()

            if gpt4v.is_available():
                QMessageBox.information(self, "Success", " OpenAI API key is valid!")
            else:
                QMessageBox.warning(self, "Failed", "API key validation failed")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Test failed: {str(e)}")

    def test_claude(self):
        """Test Claude connection"""
        api_key = self.claude_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your Anthropic API key first")
            return

        progress = QProgressDialog("Testing Claude...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            import sys
            from pathlib import Path
            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            from core.ai_providers import ClaudeProvider

            claude = ClaudeProvider(api_key=api_key)

            progress.close()

            if claude.is_available():
                QMessageBox.information(self, "Success", " Anthropic API key is valid!")
            else:
                QMessageBox.warning(self, "Failed", "API key validation failed")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Test failed: {str(e)}")

    def refresh_claude_models(self):
        """Fetch available models from the Anthropic Models API and repopulate the dropdown"""
        api_key = self.claude_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your Anthropic API key first")
            return

        progress = QProgressDialog("Fetching Claude models...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        models = []
        try:
            import sys
            from pathlib import Path
            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            from core.ai_providers import ClaudeProvider

            models = ClaudeProvider.list_available_models(api_key)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Model refresh failed: {str(e)}")
            return

        progress.close()

        # Keep the current selection across the repopulate
        current = self.claude_model_combo.currentText()

        # Fall back to the hardcoded list if the API returned nothing
        items = models if models else list(self.CLAUDE_FALLBACK_MODELS)

        # Block signals so repopulating does not emit spurious settings_changed
        self.claude_model_combo.blockSignals(True)
        self.claude_model_combo.clear()
        self.claude_model_combo.addItems(items)

        index = self.claude_model_combo.findText(current)
        if index >= 0:
            self.claude_model_combo.setCurrentIndex(index)
        elif current:
            # Preserve a custom or no-longer-listed model at the top
            self.claude_model_combo.insertItem(0, current)
            self.claude_model_combo.setCurrentIndex(0)
        self.claude_model_combo.blockSignals(False)

        if models:
            unreal.log(f"[AI Settings] Loaded {len(models)} Claude models from the Anthropic API")
        else:
            unreal.log_warning("[AI Settings] Could not fetch models from the Anthropic API - keeping the built-in list")
            QMessageBox.warning(self, "Refresh Failed",
                                "Could not fetch models from the Anthropic API.\n"
                                "Check your API key and connection.\n"
                                "The built-in model list is still available.")

    def refresh_openai_models(self):
        """Fetch available models from the OpenAI Models API and repopulate the dropdown"""
        api_key = self.openai_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your OpenAI API key first")
            return

        progress = QProgressDialog("Fetching OpenAI models...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        models = []
        try:
            import requests
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json().get("data", [])

            # Keep only chat/vision-capable model families
            include_prefixes = ("gpt-4o", "gpt-4.", "gpt-5", "o3", "o4")
            exclude_terms = ("audio", "realtime", "transcribe", "tts",
                             "embedding", "image", "moderation")

            for entry in data:
                if not isinstance(entry, dict):
                    continue
                model_id = entry.get("id", "")
                if not model_id.startswith(include_prefixes):
                    continue
                if any(term in model_id for term in exclude_terms):
                    continue
                models.append(model_id)

            models.sort(reverse=True)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Model refresh failed: {str(e)}")
            return

        progress.close()

        # Keep the current selection across the repopulate
        current = self.openai_model_combo.currentText()

        # Fall back to the hardcoded list if the API returned nothing
        items = models if models else list(self.OPENAI_FALLBACK_MODELS)

        # Block signals so repopulating does not emit spurious settings_changed
        self.openai_model_combo.blockSignals(True)
        self.openai_model_combo.clear()
        self.openai_model_combo.addItems(items)

        index = self.openai_model_combo.findText(current)
        if index >= 0:
            self.openai_model_combo.setCurrentIndex(index)
        elif current:
            # Preserve a custom or no-longer-listed model at the top
            self.openai_model_combo.insertItem(0, current)
            self.openai_model_combo.setCurrentIndex(0)
        self.openai_model_combo.blockSignals(False)

        if models:
            unreal.log(f"[AI Settings] Loaded {len(models)} OpenAI models from the OpenAI API")
        else:
            unreal.log_warning("[AI Settings] Could not fetch models from the OpenAI API - keeping the built-in list")
            QMessageBox.warning(self, "Refresh Failed",
                                "Could not fetch models from the OpenAI API.\n"
                                "Check your API key and connection.\n"
                                "The built-in model list is still available.")

    def refresh_gemini_models(self):
        """Fetch available models from the Google Gemini API and repopulate the dropdown"""
        api_key = self.gemini_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your Gemini API key first")
            return

        progress = QProgressDialog("Fetching Gemini models...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        models = []
        try:
            import sys
            from pathlib import Path
            plugin_path = Path(unreal.Paths.project_content_dir()).parent / "Plugins" / "StoryboardTo3D" / "Content" / "Python"
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            # Prefer the provider's own model listing; fall back to a direct
            # REST call if the Gemini provider module is not available yet
            try:
                from core.ai_providers.gemini_provider import GeminiProvider
            except ImportError:
                GeminiProvider = None

            if GeminiProvider is not None and hasattr(GeminiProvider, "list_available_models"):
                models = GeminiProvider.list_available_models(api_key)
            else:
                models = self._fetch_gemini_models_direct(api_key)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Model refresh failed: {str(e)}")
            return

        progress.close()

        # Keep the current selection across the repopulate
        current = self.gemini_model_combo.currentText()

        # Fall back to the hardcoded list if the API returned nothing
        items = models if models else list(self.GEMINI_FALLBACK_MODELS)

        # Block signals so repopulating does not emit spurious settings_changed
        self.gemini_model_combo.blockSignals(True)
        self.gemini_model_combo.clear()
        self.gemini_model_combo.addItems(items)

        index = self.gemini_model_combo.findText(current)
        if index >= 0:
            self.gemini_model_combo.setCurrentIndex(index)
        elif current:
            # Preserve a custom or no-longer-listed model at the top
            self.gemini_model_combo.insertItem(0, current)
            self.gemini_model_combo.setCurrentIndex(0)
        self.gemini_model_combo.blockSignals(False)

        if models:
            unreal.log(f"[AI Settings] Loaded {len(models)} Gemini models from the Google Gemini API")
        else:
            unreal.log_warning("[AI Settings] Could not fetch models from the Google Gemini API - keeping the built-in list")
            QMessageBox.warning(self, "Refresh Failed",
                                "Could not fetch models from the Google Gemini API.\n"
                                "Check your API key and connection.\n"
                                "The built-in model list is still available.")

    def _fetch_gemini_models_direct(self, api_key):
        """Direct REST fallback for listing Gemini models when the provider module is unavailable.

        Queries GET https://generativelanguage.googleapis.com/v1beta/models and
        returns the model names (with the 'models/' prefix stripped) that
        support the generateContent method. Exceptions propagate to the caller.
        """
        import requests
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            timeout=10
        )
        response.raise_for_status()
        entries = response.json().get("models", [])

        models = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            methods = entry.get("supportedGenerationMethods") or entry.get("supported_actions") or []
            if "generateContent" not in methods:
                continue
            name = entry.get("name", "")
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name:
                models.append(name)
        return models

    def load_settings(self):
        """Load settings into UI"""
        ai_settings = self.settings.get('ai_settings', {})

        # Provider
        provider = ai_settings.get('provider', 'Auto')
        index = self.provider_combo.findText(provider)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)

        # LLaVA
        self.llava_url_edit.setText(ai_settings.get('llava_url', 'http://localhost:11434'))

        # OpenAI (SEPARATE KEY) - Default to gpt-4o (proven model)
        self.openai_api_key_edit.setText(ai_settings.get('openai_api_key', ''))
        self.openai_model_combo.setCurrentText(ai_settings.get('openai_model', 'gpt-4o'))

        # Claude (SEPARATE KEY) - Default to Sonnet 4.5 with extended thinking
        self.claude_api_key_edit.setText(ai_settings.get('claude_api_key', ''))
        self.claude_model_combo.setCurrentText(ai_settings.get('claude_model', 'claude-sonnet-4-6'))

        # Gemini (SEPARATE KEY) - Default to gemini-2.5-flash (fast + low cost)
        self.gemini_api_key_edit.setText(ai_settings.get('gemini_api_key', ''))
        self.gemini_model_combo.setCurrentText(ai_settings.get('gemini_model', 'gemini-2.5-flash'))

        # Model settings
        temp = int(ai_settings.get('temperature', 0.7) * 100)
        self.temperature_slider.setValue(temp)
        self.max_tokens_spin.setValue(ai_settings.get('max_tokens', 4000))

        # Analysis settings
        self.use_multiview_check.setChecked(ai_settings.get('use_multiview', False))  # Default FALSE
        self.auto_analyze_check.setChecked(ai_settings.get('auto_analyze', True))
        self.batch_analysis_check.setChecked(ai_settings.get('batch_analysis', True))
        self.timeout_spin.setValue(ai_settings.get('timeout', 30))
        self.retry_check.setChecked(ai_settings.get('retry_on_failure', True))
        self.max_retries_spin.setValue(ai_settings.get('max_retries', 3))

    def get_settings(self):
        """Get settings from UI - WITH SEPARATE KEYS"""
        # Copy-then-overwrite (same pattern as features_tab) so sibling keys
        # this tab does not manage (e.g. use_optimized_prompts) survive the
        # dialog's wholesale replacement of the ai_settings section
        ai_settings = dict(self.settings.get('ai_settings', {}))

        ai_settings['provider'] = self.provider_combo.currentText()

        # LLaVA
        ai_settings['llava_url'] = self.llava_url_edit.text()

        # OpenAI (SEPARATE)
        ai_settings['openai_api_key'] = self.openai_api_key_edit.text()
        ai_settings['openai_model'] = self.openai_model_combo.currentText()

        # Claude (SEPARATE)
        ai_settings['claude_api_key'] = self.claude_api_key_edit.text()
        ai_settings['claude_model'] = self.claude_model_combo.currentText()

        # Gemini (SEPARATE)
        ai_settings['gemini_api_key'] = self.gemini_api_key_edit.text()
        ai_settings['gemini_model'] = self.gemini_model_combo.currentText()

        # Model settings
        ai_settings['temperature'] = self.temperature_slider.value() / 100.0
        ai_settings['max_tokens'] = self.max_tokens_spin.value()

        # Analysis settings
        ai_settings['use_multiview'] = self.use_multiview_check.isChecked()
        ai_settings['auto_analyze'] = self.auto_analyze_check.isChecked()
        ai_settings['batch_analysis'] = self.batch_analysis_check.isChecked()
        ai_settings['timeout'] = self.timeout_spin.value()
        ai_settings['retry_on_failure'] = self.retry_check.isChecked()
        ai_settings['max_retries'] = self.max_retries_spin.value()

        return {'ai_settings': ai_settings}

    def on_settings_saved(self):
        """Called when settings are saved"""
        unreal.log("[AI Settings] Settings saved with ALL models!")

        # Verify keys are separate
        settings = self.get_settings()['ai_settings']
        openai_key = settings.get('openai_api_key', '')
        claude_key = settings.get('claude_api_key', '')

        if openai_key:
            unreal.log(f"OpenAI: {openai_key[:10]}...")
        if claude_key:
            unreal.log(f"Claude: {claude_key[:10]}...")

        if openai_key and claude_key and openai_key != claude_key:
            unreal.log("Keys are separate!")
        elif openai_key and claude_key and openai_key == claude_key:
            unreal.log_warning("Keys are the same - might be wrong!")

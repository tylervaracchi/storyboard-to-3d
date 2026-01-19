# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
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
        self.provider_combo.addItems(["Auto", "LLaVA (Local)", "GPT-4 Vision (OpenAI)", "Claude (Anthropic)"])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        provider_select_layout.addWidget(self.provider_combo)
        provider_select_layout.addStretch()
        provider_layout.addLayout(provider_select_layout)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # === LLAVA (LOCAL) SETTINGS ===
        llava_group = QGroupBox(" LLaVA (Local) - Free")
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
        openai_group = QGroupBox(" GPT Vision (OpenAI) - Paid")
        openai_layout = QVBoxLayout()

        # OpenAI API Key (SEPARATE)
        openai_key_layout = QHBoxLayout()
        openai_key_layout.addWidget(QLabel("OpenAI API Key:"))
        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_api_key_edit.setPlaceholderText("sk-...")
        self.openai_api_key_edit.textChanged.connect(self.on_change)
        openai_key_layout.addWidget(self.openai_api_key_edit)

        self.show_openai_key_btn = QPushButton("")
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
        self.openai_model_combo.addItems([
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
        ])
        self.openai_model_combo.currentTextChanged.connect(self.on_change)
        openai_model_layout.addWidget(self.openai_model_combo)
        openai_model_layout.addStretch()
        openai_layout.addLayout(openai_model_layout)

        # Model info label
        info_label = QLabel(" All models support vision | o-series = reasoning | GPT-5 = newest")
        info_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        info_label.setWordWrap(True)
        openai_layout.addWidget(info_label)

        test_openai_btn = QPushButton("Test OpenAI Connection")
        test_openai_btn.clicked.connect(self.test_openai)
        openai_layout.addWidget(test_openai_btn)

        openai_group.setLayout(openai_layout)
        layout.addWidget(openai_group)

        # === ANTHROPIC (CLAUDE) SETTINGS ===
        claude_group = QGroupBox(" Claude (Anthropic) - Paid")
        claude_layout = QVBoxLayout()

        # Claude API Key (SEPARATE)
        claude_key_layout = QHBoxLayout()
        claude_key_layout.addWidget(QLabel("Anthropic API Key:"))
        self.claude_api_key_edit = QLineEdit()
        self.claude_api_key_edit.setEchoMode(QLineEdit.Password)
        self.claude_api_key_edit.setPlaceholderText("sk-ant-...")
        self.claude_api_key_edit.textChanged.connect(self.on_change)
        claude_key_layout.addWidget(self.claude_api_key_edit)

        self.show_claude_key_btn = QPushButton("")
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
        self.claude_model_combo.addItems([
            # === CLAUDE 4 SERIES (2025) ===
            "claude-sonnet-4-5-20250929",    # Sept 2025 - NEWEST! Best coding
            "claude-opus-4-1-20250805",      # Aug 2025 - Most powerful
            "claude-sonnet-4-20250514",      # May 2025 - Claude Sonnet 4
            "claude-opus-4-20250514",        # May 2025 - Claude Opus 4

            # === CLAUDE 3.7 SERIES (Feb 2025) ===
            "claude-3-7-sonnet-20250219",    # Feb 2025 - Claude Sonnet 3.7

            # === CLAUDE 3.5 SERIES (Oct 2024) ===
            "claude-3-5-sonnet-20241022",    # Oct 2024 - Claude Sonnet 3.5
            "claude-3-5-haiku-20241022",     # Oct 2024 - Claude Haiku 3.5

            # === CLAUDE 3 SERIES (Mar 2024) ===
            "claude-3-opus-20240229",        # Mar 2024 - Claude Opus 3
            "claude-3-haiku-20240307"        # Mar 2024 - Claude Haiku 3
        ])
        self.claude_model_combo.currentTextChanged.connect(self.on_change)
        claude_model_layout.addWidget(self.claude_model_combo)
        claude_model_layout.addStretch()
        claude_layout.addLayout(claude_model_layout)

        # Claude info label
        claude_info_label = QLabel(" Recommended: Sonnet 4.5 for best spatial reasoning | All support vision")
        claude_info_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        claude_info_label.setWordWrap(True)
        claude_layout.addWidget(claude_info_label)

        test_claude_btn = QPushButton("Test Claude Connection")
        test_claude_btn.clicked.connect(self.test_claude)
        claude_layout.addWidget(test_claude_btn)

        claude_group.setLayout(claude_layout)
        layout.addWidget(claude_group)

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

        multiview_note = QLabel(" Disable this if positioning doesn't change captures\n(Uses viewport screenshot instead - works with spawnables)")
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
        self.claude_model_combo.setCurrentText(ai_settings.get('claude_model', 'claude-sonnet-4-5-20250929'))

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
        return {
            'ai_settings': {
                'provider': self.provider_combo.currentText(),

                # LLaVA
                'llava_url': self.llava_url_edit.text(),

                # OpenAI (SEPARATE)
                'openai_api_key': self.openai_api_key_edit.text(),
                'openai_model': self.openai_model_combo.currentText(),

                # Claude (SEPARATE)
                'claude_api_key': self.claude_api_key_edit.text(),
                'claude_model': self.claude_model_combo.currentText(),

                # Model settings
                'temperature': self.temperature_slider.value() / 100.0,
                'max_tokens': self.max_tokens_spin.value(),

                # Analysis settings
                'use_multiview': self.use_multiview_check.isChecked(),
                'auto_analyze': self.auto_analyze_check.isChecked(),
                'batch_analysis': self.batch_analysis_check.isChecked(),
                'timeout': self.timeout_spin.value(),
                'retry_on_failure': self.retry_check.isChecked(),
                'max_retries': self.max_retries_spin.value()
            }
        }

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

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
AI Settings Dialog - FIXED VERSION
Separate API key fields for OpenAI and Anthropic
"""

import unreal

try:
    from PySide6.QtWidgets import *
    from PySide6.QtCore import *
    from PySide6.QtGui import *
except ImportError:
    from PySide2.QtWidgets import *
    from PySide2.QtCore import *
    from PySide2.QtGui import *

from core.ai_settings import get_ai_settings
from core.ai_providers import AIProviderFactory


class AISettingsDialog(QDialog):
    """Settings dialog for AI providers with SEPARATE API key fields"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_ai_settings()
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the UI"""
        self.setWindowTitle("AI Provider Settings")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(" AI Vision Provider Settings")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 15px;")
        layout.addWidget(header)

        # Info box
        info = QLabel(
            "Configure AI providers for analyzing storyboards and positioning assets.\n"
            "At least one provider must be configured to use AI positioning."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #2A2A2A; padding: 10px; border-radius: 5px; color: #AAAAAA;")
        layout.addWidget(info)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self.create_provider_tab(), "Provider Selection")
        tabs.addTab(self.create_llava_tab(), "LLaVA (Free)")
        tabs.addTab(self.create_openai_tab(), "OpenAI (GPT-4V)")
        tabs.addTab(self.create_anthropic_tab(), "Anthropic (Claude)")
        layout.addWidget(tabs)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("padding: 5px; color: #888;")
        layout.addWidget(self.status_label)

        # Buttons
        button_box = QDialogButtonBox()

        save_btn = button_box.addButton("Save", QDialogButtonBox.AcceptRole)
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 20px; font-weight: bold;")

        test_btn = button_box.addButton("Test All", QDialogButtonBox.ActionRole)
        test_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px 20px;")

        cancel_btn = button_box.addButton(QDialogButtonBox.Cancel)
        cancel_btn.setStyleSheet("padding: 8px 20px;")

        button_box.accepted.connect(self.save_and_close)
        button_box.rejected.connect(self.reject)
        test_btn.clicked.connect(self.test_all_providers)

        layout.addWidget(button_box)

    def create_provider_tab(self):
        """Provider selection tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Provider selection
        provider_group = QGroupBox("Active Provider")
        provider_layout = QVBoxLayout()

        desc = QLabel(
            "Choose which AI provider to use for vision analysis.\n"
            "Auto mode automatically selects the best available provider."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #999; padding: 5px; font-size: 11px;")
        provider_layout.addWidget(desc)

        # Radio buttons for provider selection
        self.provider_auto = QRadioButton(" Auto (Recommended) - Automatically use best available")
        self.provider_llava = QRadioButton(" LLaVA (Local) - Free, runs on your machine")
        self.provider_gpt4v = QRadioButton(" GPT-4 Vision (OpenAI) - Fast and accurate")
        self.provider_claude = QRadioButton(" Claude 3.5 (Anthropic) - Best spatial reasoning")

        self.provider_auto.setChecked(True)

        provider_layout.addWidget(self.provider_auto)
        provider_layout.addWidget(self.provider_llava)
        provider_layout.addWidget(self.provider_gpt4v)
        provider_layout.addWidget(self.provider_claude)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # Provider status
        status_group = QGroupBox("Provider Status")
        status_layout = QVBoxLayout()

        self.status_list = QTextEdit()
        self.status_list.setReadOnly(True)
        self.status_list.setMaximumHeight(150)
        self.status_list.setStyleSheet("background-color: #1E1E1E; font-family: 'Consolas', monospace; font-size: 10px;")
        status_layout.addWidget(self.status_list)

        refresh_btn = QPushButton(" Refresh Status")
        refresh_btn.clicked.connect(self.refresh_status)
        status_layout.addWidget(refresh_btn)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        layout.addStretch()
        return widget

    def create_llava_tab(self):
        """LLaVA configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Info
        info = QLabel(
            " LLaVA - Local AI Vision\n\n"
            "LLaVA runs on your computer via Ollama. No internet required, completely free!\n\n"
            "• Cost: FREE\n"
            "• Speed: 10-20 seconds per analysis\n"
            "• Accuracy: Good (75-80%)\n"
            "• Privacy: 100% local, data never leaves your machine"
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #1E3A1E; padding: 15px; border-radius: 5px; color: #90EE90;")
        layout.addWidget(info)

        # Setup instructions
        setup_group = QGroupBox("Setup Instructions")
        setup_layout = QVBoxLayout()

        steps = QLabel(
            "1. Install Ollama: https://ollama.ai\n"
            "2. Open terminal/PowerShell\n"
            "3. Run: ollama serve\n"
            "4. Run: ollama pull llava\n"
            "5. Keep terminal open while using"
        )
        steps.setStyleSheet("font-family: 'Consolas', monospace; padding: 10px;")
        setup_layout.addWidget(steps)

        # URL setting
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("Ollama URL:"))
        self.llava_url = QLineEdit()
        self.llava_url.setPlaceholderText("http://localhost:11434")
        url_layout.addWidget(self.llava_url)
        setup_layout.addLayout(url_layout)

        # Test button
        test_llava_btn = QPushButton(" Test LLaVA Connection")
        test_llava_btn.clicked.connect(self.test_llava)
        setup_layout.addWidget(test_llava_btn)

        self.llava_status = QLabel("Not tested")
        self.llava_status.setStyleSheet("padding: 5px; color: #888;")
        setup_layout.addWidget(self.llava_status)

        setup_group.setLayout(setup_layout)
        layout.addWidget(setup_group)

        layout.addStretch()
        return widget

    def create_openai_tab(self):
        """OpenAI GPT-4V configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Info
        info = QLabel(
            " GPT-4 Vision - OpenAI API\n\n"
            "Fast and accurate AI vision from OpenAI. Requires API key and credits.\n\n"
            "• Cost: ~$0.02-0.03 per analysis\n"
            "• Speed: 2-5 seconds per analysis\n"
            "• Accuracy: Excellent (85-90%)\n"
            "• Internet: Required"
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #1E2A3A; padding: 15px; border-radius: 5px; color: #87CEEB;")
        layout.addWidget(info)

        # API Key
        key_group = QGroupBox("OpenAI API Key Configuration")
        key_layout = QVBoxLayout()

        # Instructions
        instructions = QLabel(
            "Get your API key:\n"
            "1. Go to: https://platform.openai.com/api-keys\n"
            "2. Click 'Create new secret key'\n"
            "3. Copy the key (starts with 'sk-')\n"
            "4. Paste below\n\n"
            " Minimum balance: $5"
        )
        instructions.setStyleSheet("font-size: 10px; color: #999; padding: 5px;")
        key_layout.addWidget(instructions)

        # API Key input
        key_input_layout = QHBoxLayout()
        key_input_layout.addWidget(QLabel("API Key:"))

        self.openai_key = QLineEdit()
        self.openai_key.setPlaceholderText("sk-...")
        self.openai_key.setEchoMode(QLineEdit.Password)
        key_input_layout.addWidget(self.openai_key)

        self.openai_show_btn = QPushButton("")
        self.openai_show_btn.setMaximumWidth(40)
        self.openai_show_btn.setCheckable(True)
        self.openai_show_btn.clicked.connect(lambda: self.toggle_visibility(self.openai_key, self.openai_show_btn))
        key_input_layout.addWidget(self.openai_show_btn)

        key_layout.addLayout(key_input_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self.openai_model = QComboBox()
        self.openai_model.addItems(["gpt-4o", "gpt-4o-mini", "gpt-4-vision-preview"])
        model_layout.addWidget(self.openai_model)
        model_layout.addStretch()
        key_layout.addLayout(model_layout)

        # Test button
        test_openai_btn = QPushButton(" Test OpenAI Connection")
        test_openai_btn.clicked.connect(self.test_openai)
        key_layout.addWidget(test_openai_btn)

        self.openai_status = QLabel("Not tested")
        self.openai_status.setStyleSheet("padding: 5px; color: #888;")
        key_layout.addWidget(self.openai_status)

        key_group.setLayout(key_layout)
        layout.addWidget(key_group)

        layout.addStretch()
        return widget

    def create_anthropic_tab(self):
        """Anthropic Claude configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Info
        info = QLabel(
            " Claude 3.5 Sonnet - Anthropic API\n\n"
            "Best spatial reasoning for positioning. Requires API key and credits.\n\n"
            "• Cost: ~$0.01-0.02 per analysis (CHEAPEST!)\n"
            "• Speed: 2-4 seconds per analysis\n"
            "• Accuracy: Excellent (90-95%) - BEST for positioning!\n"
            "• Internet: Required"
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #2A1E3A; padding: 15px; border-radius: 5px; color: #DDA0DD;")
        layout.addWidget(info)

        # API Key
        key_group = QGroupBox("Anthropic API Key Configuration")
        key_layout = QVBoxLayout()

        # Instructions
        instructions = QLabel(
            "Get your API key:\n"
            "1. Go to: https://console.anthropic.com/\n"
            "2. Click 'Get API Keys'\n"
            "3. Create new key\n"
            "4. Copy the key (starts with 'sk-ant-')\n"
            "5. Paste below\n\n"
            " Minimum balance: $5"
        )
        instructions.setStyleSheet("font-size: 10px; color: #999; padding: 5px;")
        key_layout.addWidget(instructions)

        # API Key input
        key_input_layout = QHBoxLayout()
        key_input_layout.addWidget(QLabel("API Key:"))

        self.anthropic_key = QLineEdit()
        self.anthropic_key.setPlaceholderText("sk-ant-...")
        self.anthropic_key.setEchoMode(QLineEdit.Password)
        key_input_layout.addWidget(self.anthropic_key)

        self.anthropic_show_btn = QPushButton("")
        self.anthropic_show_btn.setMaximumWidth(40)
        self.anthropic_show_btn.setCheckable(True)
        self.anthropic_show_btn.clicked.connect(lambda: self.toggle_visibility(self.anthropic_key, self.anthropic_show_btn))
        key_input_layout.addWidget(self.anthropic_show_btn)

        key_layout.addLayout(key_input_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self.anthropic_model = QComboBox()
        self.anthropic_model.addItems([
            "claude-3-5-sonnet-20241022",
            "claude-sonnet-4-20250514",
            "claude-3-opus-20240229"
        ])
        model_layout.addWidget(self.anthropic_model)
        model_layout.addStretch()
        key_layout.addLayout(model_layout)

        # Test button
        test_anthropic_btn = QPushButton(" Test Claude Connection")
        test_anthropic_btn.clicked.connect(self.test_anthropic)
        key_layout.addWidget(test_anthropic_btn)

        self.anthropic_status = QLabel("Not tested")
        self.anthropic_status.setStyleSheet("padding: 5px; color: #888;")
        key_layout.addWidget(self.anthropic_status)

        key_group.setLayout(key_layout)
        layout.addWidget(key_group)

        layout.addStretch()
        return widget

    def toggle_visibility(self, line_edit, button):
        """Toggle password visibility"""
        if button.isChecked():
            line_edit.setEchoMode(QLineEdit.Normal)
            button.setText("")
        else:
            line_edit.setEchoMode(QLineEdit.Password)
            button.setText("")

    def load_settings(self):
        """Load current settings"""
        # Provider selection
        provider = self.settings.get_provider()
        if provider == 'auto':
            self.provider_auto.setChecked(True)
        elif provider == 'llava':
            self.provider_llava.setChecked(True)
        elif provider == 'gpt4v':
            self.provider_gpt4v.setChecked(True)
        elif provider == 'claude':
            self.provider_claude.setChecked(True)

        # LLaVA
        self.llava_url.setText(self.settings.get('llava.url', 'http://localhost:11434'))

        # OpenAI - SEPARATE KEY
        openai_key = self.settings.get('gpt4v.api_key', '')
        if openai_key:
            self.openai_key.setText(openai_key)

        openai_model = self.settings.get('gpt4v.model', 'gpt-4o')
        index = self.openai_model.findText(openai_model)
        if index >= 0:
            self.openai_model.setCurrentIndex(index)

        # Anthropic - SEPARATE KEY
        anthropic_key = self.settings.get('claude.api_key', '')
        if anthropic_key:
            self.anthropic_key.setText(anthropic_key)

        anthropic_model = self.settings.get('claude.model', 'claude-3-5-sonnet-20241022')
        index = self.anthropic_model.findText(anthropic_model)
        if index >= 0:
            self.anthropic_model.setCurrentIndex(index)

        # Refresh status
        self.refresh_status()

    def save_settings(self):
        """Save all settings - FIXED to save keys separately"""
        # Provider selection
        if self.provider_auto.isChecked():
            self.settings.set_provider('auto')
        elif self.provider_llava.isChecked():
            self.settings.set_provider('llava')
        elif self.provider_gpt4v.isChecked():
            self.settings.set_provider('gpt4v')
        elif self.provider_claude.isChecked():
            self.settings.set_provider('claude')

        # LLaVA
        llava_url = self.llava_url.text().strip()
        if llava_url:
            self.settings.set('llava.url', llava_url)

        # OpenAI - Save to gpt4v.api_key
        openai_key = self.openai_key.text().strip()
        if openai_key:
            self.settings.set('gpt4v.api_key', openai_key)
            unreal.log(f"[Settings] Saved OpenAI key: {openai_key[:10]}...")

        openai_model = self.openai_model.currentText()
        self.settings.set('gpt4v.model', openai_model)

        # Anthropic - Save to claude.api_key (SEPARATE!)
        anthropic_key = self.anthropic_key.text().strip()
        if anthropic_key:
            self.settings.set('claude.api_key', anthropic_key)
            unreal.log(f"[Settings] Saved Anthropic key: {anthropic_key[:10]}...")

        anthropic_model = self.anthropic_model.currentText()
        self.settings.set('claude.model', anthropic_model)

        self.status_label.setText(" Settings saved!")
        unreal.log("[Settings] All settings saved successfully")

    def save_and_close(self):
        """Save and close dialog"""
        self.save_settings()
        self.accept()

    def refresh_status(self):
        """Refresh provider status"""
        self.status_list.clear()
        self.status_list.append("Checking provider status...\n")

        config = self.settings.get_all_provider_configs()
        providers = AIProviderFactory.get_available_providers(**config)

        for provider in providers:
            name = provider['name']
            if provider.get('available', False):
                self.status_list.append(f" {name} - Available")
                if 'speed' in provider:
                    self.status_list.append(f"   Speed: {provider['speed']}")
                if 'accuracy' in provider:
                    self.status_list.append(f"   Accuracy: {provider['accuracy']}")
            else:
                error = provider.get('error', 'Not available')
                self.status_list.append(f" {name} - {error}")
            self.status_list.append("")

        self.status_label.setText("Status refreshed")

    def test_llava(self):
        """Test LLaVA connection"""
        self.llava_status.setText("Testing...")
        self.llava_status.setStyleSheet("padding: 5px; color: orange;")
        QApplication.processEvents()

        try:
            from core.ai_providers import LLaVAProvider
            llava = LLaVAProvider(url=self.llava_url.text())

            if llava.is_available():
                self.llava_status.setText(" LLaVA is available and working!")
                self.llava_status.setStyleSheet("padding: 5px; color: green;")
            else:
                self.llava_status.setText(" LLaVA not available (check Ollama)")
                self.llava_status.setStyleSheet("padding: 5px; color: red;")
        except Exception as e:
            self.llava_status.setText(f" Error: {str(e)}")
            self.llava_status.setStyleSheet("padding: 5px; color: red;")

    def test_openai(self):
        """Test OpenAI connection"""
        self.openai_status.setText("Testing...")
        self.openai_status.setStyleSheet("padding: 5px; color: orange;")
        QApplication.processEvents()

        api_key = self.openai_key.text().strip()
        if not api_key:
            self.openai_status.setText(" No API key entered")
            self.openai_status.setStyleSheet("padding: 5px; color: red;")
            return

        try:
            from core.ai_providers import GPT4VisionProvider
            gpt4v = GPT4VisionProvider(api_key=api_key)

            if gpt4v.is_available():
                self.openai_status.setText(" OpenAI API key is valid!")
                self.openai_status.setStyleSheet("padding: 5px; color: green;")
            else:
                self.openai_status.setText(" API key not configured")
                self.openai_status.setStyleSheet("padding: 5px; color: red;")
        except Exception as e:
            self.openai_status.setText(f" Error: {str(e)}")
            self.openai_status.setStyleSheet("padding: 5px; color: red;")

    def test_anthropic(self):
        """Test Anthropic connection"""
        self.anthropic_status.setText("Testing...")
        self.anthropic_status.setStyleSheet("padding: 5px; color: orange;")
        QApplication.processEvents()

        api_key = self.anthropic_key.text().strip()
        if not api_key:
            self.anthropic_status.setText(" No API key entered")
            self.anthropic_status.setStyleSheet("padding: 5px; color: red;")
            return

        try:
            from core.ai_providers import ClaudeProvider
            claude = ClaudeProvider(api_key=api_key)

            if claude.is_available():
                self.anthropic_status.setText(" Anthropic API key is valid!")
                self.anthropic_status.setStyleSheet("padding: 5px; color: green;")
            else:
                self.anthropic_status.setText(" API key not configured")
                self.anthropic_status.setStyleSheet("padding: 5px; color: red;")
        except Exception as e:
            self.anthropic_status.setText(f" Error: {str(e)}")
            self.anthropic_status.setStyleSheet("padding: 5px; color: red;")

    def test_all_providers(self):
        """Test all providers"""
        self.status_label.setText("Testing all providers...")
        QApplication.processEvents()

        self.test_llava()
        self.test_openai()
        self.test_anthropic()
        self.refresh_status()

        self.status_label.setText(" All tests complete!")


def show_settings_dialog():
    """Show the settings dialog"""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    dialog = AISettingsDialog()
    result = dialog.exec_()

    if result == QDialog.Accepted:
        unreal.log("[Settings] Settings saved and dialog closed")
    else:
        unreal.log("[Settings] Dialog cancelled")

    return result


if __name__ == "__main__":
    show_settings_dialog()

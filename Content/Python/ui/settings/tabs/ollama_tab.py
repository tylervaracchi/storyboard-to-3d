# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Ollama Settings Tab for StoryboardTo3D
"""

import unreal
import subprocess
import requests
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


class OllamaSettingsTab(QWidget):
    """Ollama-specific settings tab"""

    settings_changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.available_models = []
        # Saved model names from settings; used to restore combo selections
        # after (re)population, including when Ollama is unreachable.
        self._saved_text_model = ''
        self._saved_vision_model = ''
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Ollama Server
        server_group = QGroupBox("Ollama Server")
        server_layout = QVBoxLayout()

        # Server URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("Server URL:"))
        self.server_url_edit = QLineEdit()
        self.server_url_edit.setText("http://localhost:11434")
        self.server_url_edit.textChanged.connect(self.on_change)
        url_layout.addWidget(self.server_url_edit)
        server_layout.addLayout(url_layout)

        # Server status
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Not checked")
        self.status_label.setStyleSheet("color: #808080;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self.check_status_btn = QPushButton("Check Status")
        # lambda: QPushButton.clicked emits checked=False, which would land
        # in check_server_status's allow_autostart parameter
        self.check_status_btn.clicked.connect(lambda: self.check_server_status())
        status_layout.addWidget(self.check_status_btn)

        server_layout.addLayout(status_layout)

        # Auto-start server
        self.auto_start_check = QCheckBox("Auto-start Ollama server if not running")
        self.auto_start_check.stateChanged.connect(self.on_change)
        server_layout.addWidget(self.auto_start_check)

        server_group.setLayout(server_layout)
        layout.addWidget(server_group)

        # Available Models
        models_group = QGroupBox("Available Models")
        models_layout = QVBoxLayout()

        # Models list
        self.models_list = QListWidget()
        self.models_list.setMaximumHeight(150)
        models_layout.addWidget(self.models_list)

        # Model management buttons
        model_btn_layout = QHBoxLayout()

        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        model_btn_layout.addWidget(self.refresh_models_btn)

        self.pull_model_btn = QPushButton("Pull Model")
        self.pull_model_btn.clicked.connect(self.pull_model_dialog)
        model_btn_layout.addWidget(self.pull_model_btn)

        self.delete_model_btn = QPushButton("Delete")
        self.delete_model_btn.clicked.connect(self.delete_model)
        model_btn_layout.addWidget(self.delete_model_btn)

        model_btn_layout.addStretch()
        models_layout.addLayout(model_btn_layout)

        models_group.setLayout(models_layout)
        layout.addWidget(models_group)

        # Model Settings
        model_settings_group = QGroupBox("Model Settings")
        model_settings_layout = QVBoxLayout()

        # Default text model
        text_model_layout = QHBoxLayout()
        text_model_layout.addWidget(QLabel("Default Text Model:"))
        self.default_text_model_combo = QComboBox()
        self.default_text_model_combo.currentTextChanged.connect(self.on_change)
        text_model_layout.addWidget(self.default_text_model_combo)
        text_model_layout.addStretch()
        model_settings_layout.addLayout(text_model_layout)

        # Default vision model
        vision_model_layout = QHBoxLayout()
        vision_model_layout.addWidget(QLabel("Default Vision Model:"))
        self.default_vision_model_combo = QComboBox()
        self.default_vision_model_combo.currentTextChanged.connect(self.on_change)
        vision_model_layout.addWidget(self.default_vision_model_combo)
        vision_model_layout.addStretch()
        model_settings_layout.addLayout(vision_model_layout)

        # Context length
        context_layout = QHBoxLayout()
        context_layout.addWidget(QLabel("Context Length:"))
        self.context_length_spin = QSpinBox()
        self.context_length_spin.setRange(512, 32768)
        self.context_length_spin.setSingleStep(512)
        self.context_length_spin.setValue(4096)
        self.context_length_spin.valueChanged.connect(self.on_change)
        context_layout.addWidget(self.context_length_spin)
        context_layout.addStretch()
        model_settings_layout.addLayout(context_layout)

        # GPU layers
        gpu_layout = QHBoxLayout()
        gpu_layout.addWidget(QLabel("GPU Layers:"))
        self.gpu_layers_spin = QSpinBox()
        self.gpu_layers_spin.setRange(0, 100)
        self.gpu_layers_spin.setValue(0)
        self.gpu_layers_spin.setSpecialValueText("Auto")
        self.gpu_layers_spin.valueChanged.connect(self.on_change)
        gpu_layout.addWidget(self.gpu_layers_spin)
        gpu_layout.addStretch()
        model_settings_layout.addLayout(gpu_layout)

        # Keep models loaded
        self.keep_loaded_check = QCheckBox("Keep models loaded in memory")
        self.keep_loaded_check.stateChanged.connect(self.on_change)
        model_settings_layout.addWidget(self.keep_loaded_check)

        model_settings_group.setLayout(model_settings_layout)
        layout.addWidget(model_settings_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout()

        # Number of parallel requests
        parallel_layout = QHBoxLayout()
        parallel_layout.addWidget(QLabel("Parallel Requests:"))
        self.parallel_requests_spin = QSpinBox()
        self.parallel_requests_spin.setRange(1, 10)
        self.parallel_requests_spin.setValue(1)
        self.parallel_requests_spin.valueChanged.connect(self.on_change)
        parallel_layout.addWidget(self.parallel_requests_spin)
        parallel_layout.addStretch()
        perf_layout.addLayout(parallel_layout)

        # Request timeout
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Request Timeout:"))
        self.request_timeout_spin = QSpinBox()
        self.request_timeout_spin.setRange(10, 300)
        self.request_timeout_spin.setSuffix(" seconds")
        self.request_timeout_spin.setValue(60)
        self.request_timeout_spin.valueChanged.connect(self.on_change)
        timeout_layout.addWidget(self.request_timeout_spin)
        timeout_layout.addStretch()
        perf_layout.addLayout(timeout_layout)

        # Use streaming
        self.use_streaming_check = QCheckBox("Use streaming responses")
        self.use_streaming_check.stateChanged.connect(self.on_change)
        perf_layout.addWidget(self.use_streaming_check)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        layout.addStretch()

    def on_change(self):
        """Handle any change"""
        self.settings_changed.emit()

    def check_server_status(self, allow_autostart=True):
        """Check Ollama server status.

        allow_autostart=False is used for the passive check when the dialog
        loads, so merely OPENING Settings never silently spawns an
        'ollama serve' subprocess; auto-start still works for explicit user
        actions (status/refresh buttons, model pulls) when the checkbox is on.
        """
        url = self.server_url_edit.text()

        try:
            response = requests.get(f"{url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.status_label.setText(" Connected")
                self.status_label.setStyleSheet("color: #00AA00;")

                # Parse models
                data = response.json()
                self.available_models = data.get('models', [])
                self.update_models_list()
            else:
                self.status_label.setText(f"Error: {response.status_code}")
                self.status_label.setStyleSheet("color: #FF6B6B;")
        except requests.exceptions.ConnectionError:
            self.status_label.setText(" Not running")
            self.status_label.setStyleSheet("color: #FF6B6B;")

            if allow_autostart and self.auto_start_check.isChecked():
                self.start_ollama_server()
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            self.status_label.setStyleSheet("color: #FF6B6B;")

    def start_ollama_server(self):
        """Try to start Ollama server"""
        try:
            # Try to start Ollama serve
            subprocess.Popen(["ollama", "serve"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

            # Wait a moment and check again
            QTimer.singleShot(2000, self.check_server_status)

            self.status_label.setText("Starting...")
            self.status_label.setStyleSheet("color: #FFA500;")
        except Exception as e:
            unreal.log_error(f"Failed to start Ollama: {e}")

    def refresh_models(self):
        """Refresh available models"""
        self.check_server_status()

    def update_models_list(self):
        """Update models list widget"""
        self.models_list.clear()

        text_models = []
        vision_models = []

        for model in self.available_models:
            name = model.get('name', '')
            size = model.get('size', 0)
            size_gb = size / (1024**3)

            item_text = f"{name} ({size_gb:.1f} GB)"
            self.models_list.addItem(item_text)

            # Categorize models
            if any(v in name.lower() for v in ['llava', 'bakllava', 'vision']):
                vision_models.append(name)
            else:
                text_models.append(name)

        # Update combo boxes. Prefer the live selection (so a user's manual
        # choice survives Refresh), falling back to the saved setting. Block
        # signals so repopulation does not mark the dialog dirty, and keep
        # the desired model selectable even if the server list omits it.
        desired_text = (self.default_text_model_combo.currentText()
                        or self._saved_text_model)
        desired_vision = (self.default_vision_model_combo.currentText()
                          or self._saved_vision_model)

        self.default_text_model_combo.blockSignals(True)
        self.default_text_model_combo.clear()
        self.default_text_model_combo.addItems(text_models)
        if desired_text:
            if desired_text not in text_models:
                self.default_text_model_combo.insertItem(0, desired_text)
            self.default_text_model_combo.setCurrentText(desired_text)
        self.default_text_model_combo.blockSignals(False)

        self.default_vision_model_combo.blockSignals(True)
        self.default_vision_model_combo.clear()
        self.default_vision_model_combo.addItems(vision_models)
        if desired_vision:
            if desired_vision not in vision_models:
                self.default_vision_model_combo.insertItem(0, desired_vision)
            self.default_vision_model_combo.setCurrentText(desired_vision)
        self.default_vision_model_combo.blockSignals(False)

    def pull_model_dialog(self):
        """Show dialog to pull new model"""
        model_name, ok = QInputDialog.getText(
            self,
            "Pull Model",
            "Enter model name (e.g., llama3.2, llava):"
        )

        if ok and model_name:
            self.pull_model(model_name)

    def pull_model(self, model_name):
        """Pull a model from Ollama.

        Parses the streamed JSON status lines so cancel and mid-stream
        errors no longer fall through to a fake 'Success' dialog, and the
        busy dialog shows real percent progress from completed/total bytes.
        """
        import json as _json

        progress = QProgressDialog(f"Pulling {model_name}...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        cancelled = False
        error_msg = None
        saw_success = False

        try:
            url = self.server_url_edit.text()
            response = requests.post(
                f"{url}/api/pull",
                json={"name": model_name},
                stream=True,
                # (connect, read) timeouts: a hung server otherwise froze the
                # editor behind a modal dialog whose Cancel is only polled
                # when a stream line arrives. A read timeout raises and is
                # surfaced by the existing except handler.
                timeout=(5, 30)
            )

            for line in response.iter_lines():
                if not line:
                    continue
                QApplication.processEvents()
                if progress.wasCanceled():
                    cancelled = True
                    break

                try:
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', 'ignore')
                    payload = _json.loads(line)
                except ValueError:
                    continue

                # Ollama reports stream errors as JSON lines
                if payload.get('error'):
                    error_msg = str(payload['error'])
                    break

                status = str(payload.get('status', ''))
                if status == 'success':
                    saw_success = True

                # Real percentage when the layer sizes are known
                total = payload.get('total')
                completed = payload.get('completed')
                if total and completed is not None:
                    try:
                        pct = int(int(completed) * 100 / int(total))
                        progress.setRange(0, 100)
                        progress.setValue(pct)
                        progress.setLabelText(
                            f"Pulling {model_name}... {pct}%"
                            + (f" ({status})" if status else ""))
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass
                elif status:
                    progress.setLabelText(f"Pulling {model_name}... {status}")

            progress.close()

            if cancelled:
                QMessageBox.information(
                    self, "Cancelled",
                    f"Pull of {model_name} was cancelled.\n\n"
                    "Ollama may keep partial layers; pulling again resumes.")
            elif error_msg:
                QMessageBox.warning(
                    self, "Error", f"Failed to pull model: {error_msg}")
            elif saw_success:
                self.refresh_models()
                QMessageBox.information(
                    self, "Success", f"Model {model_name} pulled successfully!")
            else:
                QMessageBox.warning(
                    self, "Incomplete",
                    f"The pull of {model_name} ended without Ollama reporting "
                    "success. Check the Ollama server logs and try again.")

        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "Error", f"Failed to pull model: {e}")

    def delete_model(self):
        """Delete selected model"""
        current = self.models_list.currentItem()
        if not current:
            return

        # Extract model name from the item text
        model_text = current.text()
        model_name = model_text.split(" (")[0]

        reply = QMessageBox.question(
            self,
            "Delete Model",
            f"Are you sure you want to delete '{model_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                url = self.server_url_edit.text()
                response = requests.delete(
                    f"{url}/api/delete",
                    json={"name": model_name},
                    timeout=(5, 30)  # don't freeze the editor on a hung server
                )

                if response.status_code == 200:
                    self.refresh_models()
                    QMessageBox.information(self, "Success", f"Model {model_name} deleted")
                else:
                    QMessageBox.warning(self, "Error", f"Failed to delete model: {response.text}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete model: {e}")

    def load_settings(self):
        """Load settings into UI"""
        ollama = self.settings.get('ollama', {})

        self.server_url_edit.setText(ollama.get('server_url', 'http://localhost:11434'))
        # Default False: auto-starting a local server should be an explicit
        # opt-in, not something Settings does silently on first open.
        self.auto_start_check.setChecked(ollama.get('auto_start', False))

        # setCurrentText on an empty non-editable QComboBox is a no-op, so
        # seed each combo with the saved model name. update_models_list()
        # re-selects it after the server's model list arrives; if Ollama is
        # unreachable, get_settings() still round-trips the saved value.
        self._saved_text_model = ollama.get('default_text_model', 'llama3.2')
        self._saved_vision_model = ollama.get('default_vision_model', 'llava')
        for combo, saved in (
                (self.default_text_model_combo, self._saved_text_model),
                (self.default_vision_model_combo, self._saved_vision_model)):
            combo.blockSignals(True)
            combo.clear()
            if saved:
                combo.addItem(saved)
                combo.setCurrentText(saved)
            combo.blockSignals(False)

        self.context_length_spin.setValue(ollama.get('context_length', 4096))
        self.gpu_layers_spin.setValue(ollama.get('gpu_layers', 0))
        self.keep_loaded_check.setChecked(ollama.get('keep_loaded', False))

        self.parallel_requests_spin.setValue(ollama.get('parallel_requests', 1))
        self.request_timeout_spin.setValue(ollama.get('request_timeout', 60))
        self.use_streaming_check.setChecked(ollama.get('use_streaming', True))

        # Check status on load: deferred so the dialog paints before the
        # (synchronous, up-to-5s) request runs, and with auto-start disabled
        # so merely opening Settings never spawns an 'ollama serve'
        # subprocess.
        QTimer.singleShot(0, lambda: self.check_server_status(allow_autostart=False))

    def get_settings(self):
        """Get settings from UI"""
        return {
            'ollama': {
                'server_url': self.server_url_edit.text(),
                'auto_start': self.auto_start_check.isChecked(),
                'default_text_model': self.default_text_model_combo.currentText(),
                'default_vision_model': self.default_vision_model_combo.currentText(),
                'context_length': self.context_length_spin.value(),
                'gpu_layers': self.gpu_layers_spin.value(),
                'keep_loaded': self.keep_loaded_check.isChecked(),
                'parallel_requests': self.parallel_requests_spin.value(),
                'request_timeout': self.request_timeout_spin.value(),
                'use_streaming': self.use_streaming_check.isChecked()
            }
        }

    def on_settings_saved(self):
        """Called when settings are saved"""
        pass

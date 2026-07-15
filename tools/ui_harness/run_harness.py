# Offscreen interactive test harness for the StoryboardTo3D plugin UI.
#
# Runs the plugin's REAL UI code outside Unreal (PySide6 offscreen platform,
# fake 'unreal' module) and exercises the interactions that were previously
# only testable by hand inside the editor: show/episode/panel creation,
# field auto-save, the Settings dialog round-trip, asset categorisation,
# and every menu/toolbar action and panel button.
#
# STUB gaps (missing fake-unreal surface) are harness work; PLUGIN
# exceptions are findings. Findings land in tools/ui_harness/findings.json.
#
# Run:  C:/Users/tyler/.storyboard_to_3d/harness_venv/Scripts/python.exe \
#           tools/ui_harness/run_harness.py

import json
import os
import shutil
import sys
import tempfile
import traceback

# Windows consoles default to cp1252; the plugin logs emoji freely
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HARNESS_DIR))
PLUGIN_PYTHON = os.path.join(REPO_ROOT, "Content", "Python")
FINDINGS_PATH = os.path.join(HARNESS_DIR, "findings.json")

# --- Environment: offscreen Qt + fresh sandbox, BEFORE any Qt/plugin import
SANDBOX = os.path.join(tempfile.gettempdir(), "storyboard_harness_sandbox")
if os.path.isdir(SANDBOX):
    shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["STORYBOARD_HARNESS_SANDBOX"] = SANDBOX

sys.path.insert(0, HARNESS_DIR)
sys.path.insert(0, PLUGIN_PYTHON)

import fake_unreal  # noqa: E402
sys.modules["unreal"] = fake_unreal

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QMessageBox, QInputDialog, QFileDialog, QDialog, QMenu,
    QComboBox, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QSlider,
    QTextEdit, QPlainTextEdit, QPushButton, QRadioButton,
)
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

# ---------------------------------------------------------------------------
# Findings collection
# ---------------------------------------------------------------------------

FINDINGS = []
CURRENT_STEP = ["startup"]


def record(kind, widget, message, tb=None):
    FINDINGS.append({
        "step": CURRENT_STEP[0],
        "kind": kind,
        "widget": widget,
        "exception": message,
        "traceback": tb or "",
    })
    print(f"[FINDING] ({kind}) {widget}: {message}")


def _excepthook(etype, value, tb):
    record("unhandled-exception", CURRENT_STEP[0], f"{etype.__name__}: {value}",
           "".join(traceback.format_exception(etype, value, tb)))


sys.excepthook = _excepthook

# ---------------------------------------------------------------------------
# Modal-dialog neutralisation (offscreen must never block)
# ---------------------------------------------------------------------------

DIALOG_LOG = []
INPUT_QUEUE = []       # queued (text, ok) responses for QInputDialog.getText
FILE_QUEUE = []        # queued responses for QFileDialog.getOpenFileNames


def _msgbox(kind, ret):
    def fn(parent, title, text, *args, **kwargs):
        DIALOG_LOG.append({"step": CURRENT_STEP[0], "type": f"QMessageBox.{kind}",
                           "title": str(title), "text": str(text)})
        print(f"[MSGBOX {kind}] {title}: {str(text).splitlines()[0][:120]}")
        return ret
    return staticmethod(fn)


QMessageBox.information = _msgbox("information", QMessageBox.StandardButton.Ok)
QMessageBox.warning = _msgbox("warning", QMessageBox.StandardButton.Ok)
QMessageBox.critical = _msgbox("critical", QMessageBox.StandardButton.Ok)
QMessageBox.question = _msgbox("question", QMessageBox.StandardButton.Yes)


def _input_get_text(parent, title, label, *args, **kwargs):
    resp = INPUT_QUEUE.pop(0) if INPUT_QUEUE else ("", False)
    DIALOG_LOG.append({"step": CURRENT_STEP[0], "type": "QInputDialog.getText",
                       "title": str(title), "response": list(resp)})
    return resp


QInputDialog.getText = staticmethod(_input_get_text)


def _file_get_open_names(parent=None, caption="", dir="", filter="", *a, **k):
    resp = FILE_QUEUE.pop(0) if FILE_QUEUE else ([], "")
    DIALOG_LOG.append({"step": CURRENT_STEP[0], "type": "QFileDialog.getOpenFileNames",
                       "caption": str(caption), "response": list(resp[0])})
    return resp


QFileDialog.getOpenFileNames = staticmethod(_file_get_open_names)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")


def _dialog_exec(self, *args, **kwargs):
    DIALOG_LOG.append({"step": CURRENT_STEP[0], "type": "QDialog.exec",
                       "class": type(self).__name__,
                       "title": self.windowTitle()})
    print(f"[DIALOG exec suppressed] {type(self).__name__}: {self.windowTitle()}")
    return 0  # reject


QDialog.exec = _dialog_exec
QDialog.exec_ = _dialog_exec
QMenu.exec = lambda self, *a, **k: None
QMenu.exec_ = lambda self, *a, **k: None
QDesktopServices.openUrl = staticmethod(lambda url: True)

import webbrowser  # noqa: E402
webbrowser.open = lambda *a, **k: True

# ---------------------------------------------------------------------------
# Harness steps
# ---------------------------------------------------------------------------


def step(name):
    CURRENT_STEP[0] = name
    print(f"\n===== STEP: {name} =====")


def guarded(label, fn):
    """Run fn; plugin exceptions become findings, never stop the run."""
    try:
        fn()
        return True
    except Exception as e:
        record("plugin-exception", label, f"{type(e).__name__}: {e}",
               traceback.format_exc())
        return False


def wait(app, ms=150):
    QTest.qWait(ms)
    app.processEvents()


def make_panel_png(path):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (320, 180), (40, 44, 52))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 40, 120, 160], outline=(220, 220, 220), width=3)
    d.ellipse([180, 30, 260, 110], outline=(220, 180, 80), width=3)
    d.text((10, 5), "harness panel", fill=(255, 255, 255))
    img.save(path)


# --- Settings round-trip helpers ------------------------------------------

INPUT_TYPES = (QComboBox, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
               QSlider, QTextEdit, QPlainTextEdit, QRadioButton)


def settings_widgets(dialog):
    """(tab_name, attr_name, widget) for every named input widget on every tab."""
    out = []
    for tab_attr in ("general_tab", "ai_tab", "features_tab", "ollama_tab",
                     "paths_tab", "advanced_tab"):
        tab = getattr(dialog, tab_attr, None)
        if tab is None:
            continue
        for attr, w in sorted(vars(tab).items()):
            if isinstance(w, INPUT_TYPES):
                out.append((tab_attr, attr, w))
    return out


def widget_value(w):
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, (QCheckBox, QRadioButton)):
        return w.isChecked()
    if isinstance(w, (QSpinBox, QDoubleSpinBox, QSlider)):
        return w.value()
    if isinstance(w, (QTextEdit, QPlainTextEdit)):
        return w.toPlainText()
    return None


def set_nondefault(attr, w):
    """Drive the widget to a non-default value; return the value set,
    or None when the widget cannot be meaningfully changed."""
    if isinstance(w, QComboBox):
        if "model" in attr:  # simulate a refreshed/out-of-list model choice
            custom = "zz-harness-model"
            if w.findText(custom) < 0:
                w.insertItem(0, custom)
            w.setCurrentText(custom)
            return w.currentText()
        if w.isEditable():
            w.setCurrentText(f"harness-{attr}")
            return w.currentText()
        if w.count() > 1:
            w.setCurrentIndex((w.currentIndex() + 1) % w.count())
            return w.currentText()
        return None
    if isinstance(w, QLineEdit):
        w.setText(f"harness_{attr}")
        return w.text()
    if isinstance(w, (QCheckBox, QRadioButton)):
        w.setChecked(not w.isChecked())
        return w.isChecked()
    if isinstance(w, (QSpinBox, QDoubleSpinBox)):
        lo, hi = w.minimum(), w.maximum()
        target = lo + (1 if isinstance(w, QSpinBox) else w.singleStep())
        if target == w.value():
            target = min(hi, target + (1 if isinstance(w, QSpinBox) else w.singleStep()))
        w.setValue(target)
        return w.value()
    if isinstance(w, QSlider):
        target = w.minimum() + 1
        if target == w.value():
            target = min(w.maximum(), target + 1)
        w.setValue(target)
        return w.value()
    if isinstance(w, (QTextEdit, QPlainTextEdit)):
        if w.isReadOnly():
            return None
        w.setPlainText(f"harness text for {attr}")
        return w.toPlainText()
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)

    step("construct-main-window")
    from ui.main_window import ModernStoryboardWindow
    window = ModernStoryboardWindow()
    window.show()
    wait(app, 300)

    # ---- Welcome panel: visible while no shows exist ----------------------
    step("welcome-panel-initial")
    if not window.welcome_panel.isVisible():
        record("assertion", "welcome_panel",
               "Welcome panel should be visible on first run (no shows exist)")

    # ---- Create a show through the real new_show flow ---------------------
    step("create-show")
    INPUT_QUEUE.append(("Harness Show", True))
    guarded("show_manager.new_show", window.show_manager.new_show)
    wait(app)
    shows = window.shows_manager.get_all_shows()
    if not any(s.get("safe_name") == "Harness_Show" for s in shows):
        record("assertion", "shows_manager",
               f"Show 'Harness_Show' not created; shows on disk: {shows}")
    if window.welcome_panel.isVisible():
        record("assertion", "welcome_panel",
               "Welcome panel still visible after the first show was created")

    step("select-show")
    show = next((s for s in shows if s.get("safe_name") == "Harness_Show"), None)
    if show:
        guarded("show_manager.on_show_selected",
                lambda: window.show_manager.on_show_selected(show))
        wait(app, 800)  # let the deferred update_active_panel_context timers fire

    # ---- Create + select an episode ---------------------------------------
    step("create-episode")
    INPUT_QUEUE.append(("Episode 01", True))
    guarded("episode_manager.new_episode", window.episode_manager.new_episode)
    wait(app)
    if window.current_episode is None:
        record("assertion", "episode_manager",
               "Creating an episode did not select it in the main window")

    # ---- Import a panel image through the real dialog flow ----------------
    step("import-panel")
    png = os.path.join(SANDBOX, "harness_panel_001.png")
    make_panel_png(png)
    FILE_QUEUE.append(([png], "Images (*.png *.jpg *.jpeg)"))
    guarded("import_panels_dialog", window.import_panels_dialog)
    wait(app)
    if len(window.panels) != 1:
        record("assertion", "import_panels_dialog",
               f"Expected 1 panel after import, found {len(window.panels)}")
    if len(window.panel_grid.panel_cards) != len(window.panels):
        record("assertion", "panel_grid",
               f"Grid shows {len(window.panel_grid.panel_cards)} cards for "
               f"{len(window.panels)} panels")

    # ---- Select the panel by clicking its card -----------------------------
    step("select-panel-card")
    if window.panel_grid.panel_cards:
        card = window.panel_grid.panel_cards[0]
        QTest.mouseClick(card, Qt.LeftButton)
        wait(app)
        if window.active_panel is None:
            record("assertion", "PanelCard",
                   "Clicking a panel card did not set the active panel "
                   "(falling back to direct selection)")
            window.on_panel_clicked(window.panels[0])
            wait(app)

    # ---- Type into fields and verify auto-save -----------------------------
    step("field-auto-save")
    apw = window.active_panel_widget
    if window.active_panel is not None:
        apw.shot_type_combo.setCurrentText("Wide")
        apw.location_combo.setCurrentText("Harness Barn")
        INPUT_QUEUE.append(("Farmer John", True))
        guarded("add_character", apw.add_character)
        INPUT_QUEUE.append(("Hay Bale", True))
        guarded("add_prop", apw.add_prop)
        wait(app)

        meta_file = window.current_episode_path / "panels_metadata.json"
        if not meta_file.exists():
            record("assertion", "panels_metadata.json",
                   f"Auto-save produced no metadata file at {meta_file}")
        else:
            meta = json.loads(meta_file.read_text())
            entry = meta.get(window.active_panel["name"], {})
            checks = {
                "shot_type": ("Wide", entry.get("shot_type")),
                "location": ("Harness Barn", entry.get("location")),
                "characters": (["Farmer John"], entry.get("characters")),
                "props": (["Hay Bale"], entry.get("props")),
            }
            for field, (expected, actual) in checks.items():
                if actual != expected:
                    record("assertion", f"auto-save:{field}",
                           f"Expected {expected!r} in panels_metadata.json, "
                           f"found {actual!r}")
    else:
        record("assertion", "active_panel",
               "No active panel selected; skipping field auto-save checks")

    # ---- SETTINGS ROUND-TRIP (the key test) --------------------------------
    step("settings-roundtrip")
    from ui.settings.dialog import SettingsDialog
    import core.settings_manager as sm

    dialog = SettingsDialog(window)
    expected = {}
    for tab, attr, w in settings_widgets(dialog):
        try:
            val = set_nondefault(attr, w)
        except Exception as e:
            record("plugin-exception", f"{tab}.{attr}",
                   f"setting a value raised {type(e).__name__}: {e}",
                   traceback.format_exc())
            continue
        if val is not None:
            expected[(tab, attr)] = val
    wait(app)
    guarded("SettingsDialog.apply_settings", dialog.apply_settings)
    wait(app)
    dialog.deleteLater()
    wait(app)

    # Force a genuine reload from the JSON on disk
    sm._settings_manager = None
    dialog2 = SettingsDialog(window)
    wait(app)
    reloaded = {(t, a): widget_value(w) for t, a, w in settings_widgets(dialog2)}
    for key, want in sorted(expected.items()):
        got = reloaded.get(key, "<widget missing on reopen>")
        if got != want:
            record("settings-roundtrip", f"{key[0]}.{key[1]}",
                   f"Set {want!r}, Apply, reopen -> got {got!r} "
                   "(value did not round-trip through saved settings)")
    print(f"[settings-roundtrip] checked {len(expected)} widgets across 6 tabs")
    dialog2.deleteLater()
    wait(app)
    sm._settings_manager = None  # later steps read fresh settings

    # ---- Asset library categorisation --------------------------------------
    step("build-entry-from-asset")
    from ui.widgets.asset_library_widget import build_entry_from_asset
    cases = [
        (fake_unreal.StaticMesh("SM_HayBale_01"), "props"),
        (fake_unreal.SkeletalMesh("SK_FarmerJohn"), "characters"),
        (fake_unreal.Blueprint("BP_Chicken"), "characters"),
        (fake_unreal.World("BarnLevel"), "locations"),
    ]
    for asset, want_cat in cases:
        entry = None
        try:
            entry = build_entry_from_asset(asset)
        except Exception as e:
            record("plugin-exception", f"build_entry_from_asset({asset.get_name()})",
                   f"{type(e).__name__}: {e}", traceback.format_exc())
            continue
        if entry is None:
            record("assertion", f"build_entry_from_asset({asset.get_name()})",
                   f"Returned None for a supported {type(asset).__name__}")
        elif entry.get("category") != want_cat:
            record("assertion", f"build_entry_from_asset({asset.get_name()})",
                   f"Expected category {want_cat!r}, got {entry.get('category')!r}")
    try:
        unsupported = build_entry_from_asset(fake_unreal.Texture2D("T_Dirt"))
        if unsupported is not None:
            record("assertion", "build_entry_from_asset(T_Dirt)",
                   f"Unsupported Texture2D should return None, got {unsupported!r}")
    except Exception as e:
        record("plugin-exception", "build_entry_from_asset(T_Dirt)",
               f"{type(e).__name__}: {e}", traceback.format_exc())

    # ---- Trigger every menu + toolbar QAction -------------------------------
    step("trigger-all-actions")
    INPUT_QUEUE.clear()   # unknown prompts during the walk get cancelled
    FILE_QUEUE.clear()

    def all_actions():
        acts = []
        for menu_action in window.menuBar().actions():
            menu = menu_action.menu()
            if menu:
                for a in menu.actions():
                    if not a.isSeparator():
                        acts.append((f"menu[{menu_action.text().strip()}]>{a.text().strip()}", a))
        return acts

    # menu actions
    for label, action in all_actions():
        CURRENT_STEP[0] = f"action:{label}"
        print(f"-- triggering {label}")
        guarded(label, action.trigger)
        wait(app, 200)

    # toolbar actions
    from PySide6.QtWidgets import QToolBar
    for tb in window.findChildren(QToolBar):
        for a in tb.actions():
            if a.isSeparator() or not a.text().strip():
                continue
            label = f"toolbar>{a.text().strip()}"
            CURRENT_STEP[0] = f"action:{label}"
            print(f"-- triggering {label}")
            guarded(label, a.trigger)
            wait(app, 200)

    # ---- Click every button on the active panel widget ----------------------
    step("click-active-panel-buttons")
    for btn in apw.findChildren(QPushButton):
        label = f"ActivePanelWidget button '{btn.text().strip() or btn.objectName()}'"
        CURRENT_STEP[0] = f"button:{label}"
        print(f"-- clicking {label}")
        guarded(label, btn.click)
        wait(app, 250)

    # let deferred timers drain, catching stragglers via the excepthook
    step("drain-timers")
    wait(app, 1500)
    fake_unreal.pump_slate_ticks(count=3)
    wait(app, 300)

    # ---- Report -------------------------------------------------------------
    step("report")
    summary = {
        "sandbox": SANDBOX,
        "findings_count": len(FINDINGS),
        "ue_log_errors": len(fake_unreal.ERRORS),
        "ue_log_warnings": len(fake_unreal.WARNINGS),
        "modal_dialogs_intercepted": len(DIALOG_LOG),
    }
    out = {"summary": summary, "findings": FINDINGS,
           "intercepted_dialogs": DIALOG_LOG,
           "ue_log_errors_tail": fake_unreal.ERRORS[-20:]}
    with open(FINDINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n===== DONE: {len(FINDINGS)} findings -> {FINDINGS_PATH} =====")
    for fnd in FINDINGS:
        print(f"  - [{fnd['kind']}] {fnd['widget']}: {fnd['exception']}")

    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.

"""
Calibration Dashboard

Answers the thesis question "do the models know how good they are?" by
plotting each model's self-reported match score against the objective
(externally validated) score for the same iteration.

Data sources (both written into the ThesisMetrics folder):
- analysis.metrics_tracker.MetricsTracker writes one
  "<scene_id>_<approach>_metrics.json" per run. Each file's
  'iteration_details' list carries the AI self-score ('match_score',
  0-100) and, when metric validation ran, a 'validation_result' dict with
  'composite_objective_score' (0-1, from analysis.metric_validation).
- analysis.multi_model_tracker.MultiModelTracker writes one
  "<Model-Name>_comparison.csv" per model with per-scene final accuracy.
  The metrics JSON does not record which model produced it, so this module
  attributes each JSON to a model by cross-referencing scene number and
  final accuracy against those CSVs (falling back to 'Unknown').

Output: a PIL-only PNG scatter chart (no matplotlib): self score on X,
objective score on Y, a diagonal perfect-calibration reference line, one
color per model, and per-model mean-error annotations. Points above the
diagonal are underconfident; points below are overconfident.

Usage:
    from analysis.calibration_dashboard import generate_dashboard
    path = generate_dashboard()  # default: ThesisMetrics/calibration_dashboard.png
"""

import csv
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Guard the unreal import so this module also works outside the editor
# (e.g. generating the chart from a plain Python shell over saved metrics).
try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    unreal = None
    UNREAL_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Chart geometry
CHART_WIDTH = 980
CHART_HEIGHT = 720
MARGIN_LEFT = 90
MARGIN_RIGHT = 300   # leaves room for the legend
MARGIN_TOP = 70
MARGIN_BOTTOM = 80

# Colors (RGB)
COLOR_BG = (250, 250, 250)
COLOR_PLOT_BG = (255, 255, 255)
COLOR_GRID = (225, 225, 225)
COLOR_AXIS = (60, 60, 60)
COLOR_DIAGONAL = (140, 140, 140)
COLOR_TEXT = (30, 30, 30)
COLOR_SUBTEXT = (110, 110, 110)

# Model color mapping by substring (checked in order), plus a fallback cycle
MODEL_COLOR_RULES = [
    ('gpt', (31, 119, 180)),      # blue
    ('claude', (255, 127, 14)),   # orange
    ('sonnet', (255, 127, 14)),   # orange
    ('llava', (44, 160, 44)),     # green
    ('ground', (148, 103, 189)),  # purple
    ('unknown', (127, 127, 127)), # gray
]
FALLBACK_COLORS = [
    (214, 39, 40),    # red
    (140, 86, 75),    # brown
    (23, 190, 207),   # cyan
    (188, 189, 34),   # olive
]


def _log(message):
    if UNREAL_AVAILABLE:
        unreal.log(f"[CalibrationDashboard] {message}")
    else:
        print(f"[CalibrationDashboard] {message}")


def _log_warning(message):
    if UNREAL_AVAILABLE:
        unreal.log_warning(f"[CalibrationDashboard] {message}")
    else:
        print(f"[CalibrationDashboard] WARNING: {message}")


def _resolve_metrics_dir(metrics_dir: Optional[Any] = None) -> Path:
    """
    Resolve the ThesisMetrics directory.

    Prefers an explicit argument, then the UE project's Saved dir (the same
    location active_panel_widget gives MetricsTracker/MultiModelTracker),
    then a Saved/ThesisMetrics folder relative to this plugin's root.
    """
    if metrics_dir:
        return Path(metrics_dir)

    if UNREAL_AVAILABLE:
        try:
            if hasattr(unreal, 'Paths') and hasattr(unreal.Paths, 'project_saved_dir'):
                return Path(unreal.Paths.project_saved_dir()) / "ThesisMetrics"
            _log_warning("unreal.Paths.project_saved_dir not available; using plugin-relative path")
        except Exception as e:
            _log_warning(f"Could not resolve project saved dir: {e}")

    # <plugin root>/Saved/ThesisMetrics  (module lives at Content/Python/analysis/)
    return Path(__file__).resolve().parents[3] / "Saved" / "ThesisMetrics"


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def _load_model_rows(metrics_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """
    Load the per-model comparison CSVs written by MultiModelTracker.

    Returns:
        {model_name: [row dicts]} where model_name comes from the filename
        "<Model-Name>_comparison.csv".
    """
    model_rows = {}
    try:
        csv_files = sorted(metrics_dir.glob("*_comparison.csv"))
    except Exception as e:
        _log_warning(f"Could not scan {metrics_dir} for comparison CSVs: {e}")
        return model_rows

    for csv_file in csv_files:
        stem = csv_file.stem  # "<Model-Name>_comparison"
        model_name = stem[:-len("_comparison")] if stem.lower().endswith("_comparison") else stem
        if model_name.lower().startswith("all_models"):
            continue  # combined export, not a single model
        try:
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                model_rows[model_name] = list(reader)
        except Exception as e:
            _log_warning(f"Failed to read {csv_file.name}: {e}")
    return model_rows


def _extract_pairs(summary: Dict[str, Any]) -> List[Tuple[float, float]]:
    """
    Extract (self_score, external_score) pairs from one metrics JSON.

    self_score is the per-iteration AI 'match_score' (0-100). external_score
    is 'validation_result.composite_objective_score' (0-1) rescaled to 0-100.
    Iterations without a validation result are skipped.
    """
    pairs = []
    for record in summary.get('iteration_details', []) or []:
        if not isinstance(record, dict):
            continue
        self_score = record.get('match_score')
        validation = record.get('validation_result')
        if not isinstance(validation, dict):
            continue
        external = validation.get('composite_objective_score')
        if self_score is None or external is None:
            continue
        try:
            pairs.append((float(self_score), float(external) * 100.0))
        except (TypeError, ValueError):
            continue
    return pairs


def _scene_number(scene_id: str) -> Optional[int]:
    """Pull the numeric part out of 'Panel_003' / 'Storyboard_03' style ids."""
    match = re.search(r'(\d+)', str(scene_id))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _attribute_model(summary: Dict[str, Any],
                     model_rows: Dict[str, List[Dict[str, str]]]) -> str:
    """
    Determine which model produced a metrics JSON.

    Order of preference:
    1. An explicit model/provider field, if a future writer adds one.
    2. Cross-reference against MultiModelTracker CSVs: a row whose scene
       number matches the JSON's scene number and whose final_accuracy
       matches the JSON's final_accuracy. Only a unique match is trusted.
    3. 'Unknown'.
    """
    for key in ('model', 'model_name', 'provider', 'ai_model'):
        value = summary.get(key)
        if value:
            return str(value)

    final_acc = summary.get('final_accuracy')
    if final_acc is None:
        return 'Unknown'
    try:
        final_acc = float(final_acc)
    except (TypeError, ValueError):
        return 'Unknown'

    panel_num = _scene_number(summary.get('scene_id', ''))

    candidates = set()
    for model_name, rows in model_rows.items():
        for row in rows:
            raw = (row.get('final_accuracy') or '').strip()
            if not raw:
                continue
            try:
                row_acc = float(raw)
            except ValueError:
                continue
            if abs(row_acc - final_acc) > 0.05:
                continue
            row_num = _scene_number(row.get('scene_id', ''))
            if panel_num is not None and row_num is not None and panel_num != row_num:
                continue
            candidates.add(model_name)

    if len(candidates) == 1:
        return candidates.pop()
    return 'Unknown'


def collect_calibration_data(metrics_dir: Optional[Any] = None) -> Dict[str, List[Tuple[float, float]]]:
    """
    Aggregate (self_score, external_score) pairs per model.

    Reads every "*_metrics.json" written by MetricsTracker in the metrics
    directory and attributes each to a model via the MultiModelTracker CSVs.

    Returns:
        {model_name: [(self_score, external_score), ...]} with scores 0-100.
    """
    metrics_path = _resolve_metrics_dir(metrics_dir)
    data = {}

    if not metrics_path.exists():
        _log_warning(f"Metrics directory does not exist yet: {metrics_path}")
        return data

    model_rows = _load_model_rows(metrics_path)

    try:
        json_files = sorted(metrics_path.glob("*_metrics.json"))
    except Exception as e:
        _log_warning(f"Could not scan {metrics_path} for metrics JSON: {e}")
        return data

    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                summary = json.load(f)
        except Exception as e:
            _log_warning(f"Failed to load {json_file.name}: {e}")
            continue
        if not isinstance(summary, dict):
            continue

        pairs = _extract_pairs(summary)
        if not pairs:
            continue

        model_name = _attribute_model(summary, model_rows)
        data.setdefault(model_name, []).extend(pairs)

    total = sum(len(v) for v in data.values())
    _log(f"Collected {total} calibration pair(s) across {len(data)} model(s) from {metrics_path}")
    return data


# ----------------------------------------------------------------------
# Drawing helpers (PIL only)
# ----------------------------------------------------------------------

def _load_font(size):
    """Load Arial when available, else PIL's default bitmap font."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default()
        except Exception:
            return None


def _text_size(draw, text, font):
    """Measure text with new or old PIL APIs."""
    try:
        if hasattr(draw, 'textbbox'):
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            return (right - left, bottom - top)
    except Exception:
        pass
    try:
        return draw.textsize(text, font=font)
    except Exception:
        return (len(text) * 6, 11)


def _model_color(model_name: str, assigned: Dict[str, Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """Pick a stable color for a model name."""
    if model_name in assigned:
        return assigned[model_name]
    lowered = model_name.lower()
    for needle, color in MODEL_COLOR_RULES:
        if needle in lowered:
            assigned[model_name] = color
            return color
    color = FALLBACK_COLORS[len(assigned) % len(FALLBACK_COLORS)]
    assigned[model_name] = color
    return color


def _draw_placeholder(output_path: Path, metrics_path: Path) -> None:
    """Write a friendly placeholder image when no metrics exist yet."""
    image = Image.new('RGB', (CHART_WIDTH, CHART_HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(image)
    title_font = _load_font(28)
    sub_font = _load_font(14)

    message = "No runs recorded yet"
    detail = "Run a storyboard positioning pass to populate the metrics, then regenerate."
    location = f"Looked in: {metrics_path}"

    w, h = _text_size(draw, message, title_font)
    draw.text(((CHART_WIDTH - w) / 2, CHART_HEIGHT / 2 - h - 20), message,
              fill=COLOR_TEXT, font=title_font)
    w2, _h2 = _text_size(draw, detail, sub_font)
    draw.text(((CHART_WIDTH - w2) / 2, CHART_HEIGHT / 2 + 4), detail,
              fill=COLOR_SUBTEXT, font=sub_font)
    w3, _h3 = _text_size(draw, location, sub_font)
    draw.text(((CHART_WIDTH - w3) / 2, CHART_HEIGHT / 2 + 28), location,
              fill=COLOR_SUBTEXT, font=sub_font)

    image.save(output_path, format='PNG')


def _draw_chart(output_path: Path, data: Dict[str, List[Tuple[float, float]]]) -> None:
    """Render the calibration scatter chart to output_path."""
    image = Image.new('RGB', (CHART_WIDTH, CHART_HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(20)
    label_font = _load_font(14)
    small_font = _load_font(12)

    plot_left = MARGIN_LEFT
    plot_top = MARGIN_TOP
    plot_right = CHART_WIDTH - MARGIN_RIGHT
    plot_bottom = CHART_HEIGHT - MARGIN_BOTTOM
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    def sx(value):
        clamped = max(0.0, min(100.0, value))
        return plot_left + (clamped / 100.0) * plot_w

    def sy(value):
        clamped = max(0.0, min(100.0, value))
        return plot_bottom - (clamped / 100.0) * plot_h

    # Plot background and grid
    draw.rectangle([plot_left, plot_top, plot_right, plot_bottom], fill=COLOR_PLOT_BG)
    for tick in range(0, 101, 20):
        x = sx(tick)
        y = sy(tick)
        draw.line([x, plot_top, x, plot_bottom], fill=COLOR_GRID, width=1)
        draw.line([plot_left, y, plot_right, y], fill=COLOR_GRID, width=1)
        # Tick labels
        tick_text = str(tick)
        tw, th = _text_size(draw, tick_text, small_font)
        draw.text((x - tw / 2, plot_bottom + 6), tick_text, fill=COLOR_AXIS, font=small_font)
        draw.text((plot_left - tw - 10, y - th / 2), tick_text, fill=COLOR_AXIS, font=small_font)

    # Axes
    draw.line([plot_left, plot_top, plot_left, plot_bottom], fill=COLOR_AXIS, width=2)
    draw.line([plot_left, plot_bottom, plot_right, plot_bottom], fill=COLOR_AXIS, width=2)

    # Diagonal perfect-calibration reference (dashed)
    step = 4.0
    tick = 0.0
    segment = True
    while tick < 100.0:
        end = min(tick + step, 100.0)
        if segment:
            draw.line([sx(tick), sy(tick), sx(end), sy(end)], fill=COLOR_DIAGONAL, width=2)
        segment = not segment
        tick = end
    diag_label = "perfect calibration"
    draw.text((sx(72) + 6, sy(72) + 8), diag_label, fill=COLOR_DIAGONAL, font=small_font)

    # Scatter points per model
    assigned_colors = {}
    radius = 4
    for model_name in sorted(data.keys()):
        color = _model_color(model_name, assigned_colors)
        for self_score, external_score in data[model_name]:
            x = sx(self_score)
            y = sy(external_score)
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=color, outline=COLOR_PLOT_BG)

    # Title and axis labels
    title = "Model Calibration: Self-Reported vs Objective Score"
    tw, _th = _text_size(draw, title, title_font)
    draw.text((plot_left + (plot_w - tw) / 2, 22), title, fill=COLOR_TEXT, font=title_font)

    x_label = "AI self-reported match score (%)"
    xw, _xh = _text_size(draw, x_label, label_font)
    draw.text((plot_left + (plot_w - xw) / 2, plot_bottom + 30), x_label,
              fill=COLOR_TEXT, font=label_font)

    # Vertical Y label (rotated), with a horizontal fallback
    y_label = "Objective composite score (%)"
    try:
        yw, yh = _text_size(draw, y_label, label_font)
        label_img = Image.new('RGB', (yw + 4, yh + 4), COLOR_BG)
        label_draw = ImageDraw.Draw(label_img)
        label_draw.text((2, 2), y_label, fill=COLOR_TEXT, font=label_font)
        rotated = label_img.rotate(90, expand=True)
        image.paste(rotated, (16, int(plot_top + (plot_h - rotated.height) / 2)))
    except Exception:
        draw.text((10, plot_top - 24), y_label, fill=COLOR_TEXT, font=label_font)

    # Legend with per-model mean error (self minus objective; positive means
    # the model rates itself higher than the objective metrics do)
    legend_x = plot_right + 24
    legend_y = plot_top
    draw.text((legend_x, legend_y), "Models", fill=COLOR_TEXT, font=label_font)
    legend_y += 26
    for model_name in sorted(data.keys()):
        pairs = data[model_name]
        color = _model_color(model_name, assigned_colors)
        errors = [self_s - ext_s for self_s, ext_s in pairs]
        mean_error = statistics.mean(errors) if errors else 0.0

        draw.rectangle([legend_x, legend_y + 2, legend_x + 12, legend_y + 14],
                       fill=color, outline=COLOR_AXIS)
        draw.text((legend_x + 20, legend_y), model_name, fill=COLOR_TEXT, font=small_font)
        legend_y += 18
        stats_text = f"n={len(pairs)}, mean err {mean_error:+.1f} pp"
        draw.text((legend_x + 20, legend_y), stats_text, fill=COLOR_SUBTEXT, font=small_font)
        legend_y += 28

    # Footer note
    total_pairs = sum(len(v) for v in data.values())
    footer = (
        f"{total_pairs} iteration pair(s). Positive mean error = overconfident. "
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    draw.text((plot_left, CHART_HEIGHT - 28), footer, fill=COLOR_SUBTEXT, font=small_font)

    image.save(output_path, format='PNG')


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def generate_dashboard(output_path: Optional[Any] = None,
                       metrics_dir: Optional[Any] = None) -> Optional[str]:
    """
    Generate the calibration dashboard PNG.

    Args:
        output_path: Where to write the PNG. Defaults to
            "<ThesisMetrics>/calibration_dashboard.png".
        metrics_dir: Override for the metrics directory (defaults to the
            same ThesisMetrics folder the trackers write into).

    Returns:
        The output path as a string on success, or None on failure (logged).
        When no metrics exist yet, a friendly placeholder image is written
        and its path returned.
    """
    if not PIL_AVAILABLE:
        _log_warning("PIL (pillow) is not installed; cannot render dashboard. pip install pillow")
        return None

    metrics_path = _resolve_metrics_dir(metrics_dir)

    if output_path is None:
        out_path = metrics_path / "calibration_dashboard.png"
    else:
        out_path = Path(output_path)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _log_warning(f"Could not create output directory {out_path.parent}: {e}")
        return None

    try:
        data = collect_calibration_data(metrics_path)
    except Exception as e:
        _log_warning(f"Failed to collect calibration data: {e}")
        data = {}

    try:
        if data:
            _draw_chart(out_path, data)
            _log(f"Calibration dashboard saved: {out_path}")
        else:
            _draw_placeholder(out_path, metrics_path)
            _log(f"No metrics found; placeholder dashboard saved: {out_path}")
        return str(out_path)
    except Exception as e:
        _log_warning(f"Failed to render dashboard: {e}")
        return None


if __name__ == "__main__":
    generate_dashboard()

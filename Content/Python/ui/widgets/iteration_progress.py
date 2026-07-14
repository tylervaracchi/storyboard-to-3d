# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# INTEGRATION (not wired up by this file - left to a supervised pass):
#   Instantiate IterationProgressWidget in ActivePanelWidget, next to
#   self.match_progress (ui/widgets/active_panel_widget.py, around line 807).
#   Feed it from the iteration loop's score-recording site - search that file
#   for `_record_iteration_metrics` - by calling:
#       iteration_progress_widget.add_score(self.current_iteration, self.last_match_score)
#       iteration_progress_widget.set_cost_text(<short string, e.g. from
#           utils/cost_estimator.format_estimate() or a running total of
#           self.iteration_costs>)
#   Connect iteration_progress_widget.cancelled to whatever currently stops
#   the refinement loop. This widget intentionally does not import anything
#   from active_panel_widget.py or panel_widgets.py, and does not import
#   `unreal`, so it can be built/tested outside the running plugin.
"""
Iteration Progress Widget for StoryboardTo3D
Self-contained live progress view for the AI refinement loop: a score
sparkline, a current-score readout, a cost readout, and a Cancel button.
"""

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


class _ScoreSparkline(QWidget):
    """
    Minimal internal plot widget: renders a horizontal line chart of recorded
    (iteration, score) pairs in paintEvent. Not intended for use outside
    IterationProgressWidget.
    """

    # Cap history so a very long-running batch doesn't grow this unbounded.
    MAX_POINTS = 200

    # Match scores in this codebase are on a 0-100 scale (see last_match_score
    # in active_panel_widget.py).
    SCORE_MIN = 0.0
    SCORE_MAX = 100.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []  # List[Tuple[int, float]]
        self.setMinimumHeight(48)
        self.setMaximumHeight(64)
        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            # SizePolicy constants are stable across PySide2/6, but guard
            # defensively rather than let a layout quirk crash construction.
            pass

    def add_score(self, iteration, score):
        """Append a new (iteration, score) point and repaint."""
        self._points.append((iteration, score))
        if len(self._points) > self.MAX_POINTS:
            self._points = self._points[-self.MAX_POINTS:]
        self.update()

    def clear_scores(self):
        """Drop all recorded points and repaint empty."""
        self._points = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.rect()

            # Background + border, matching this codebase's dark card style.
            painter.fillRect(rect, QColor("#1A1A1A"))
            painter.setPen(QPen(QColor("#2A2A2A"), 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

            if len(self._points) < 2:
                painter.setPen(QColor("#6B7280"))
                painter.drawText(rect, Qt.AlignCenter, "No iterations yet")
                return

            margin = 6
            plot_rect = rect.adjusted(margin, margin, -margin, -margin)
            width = max(1, plot_rect.width())
            height = max(1, plot_rect.height())

            count = len(self._points)
            step_x = width / float(max(1, count - 1))
            score_range = self.SCORE_MAX - self.SCORE_MIN

            def point_at(index, score):
                x = plot_rect.left() + (index * step_x)
                clamped = max(self.SCORE_MIN, min(self.SCORE_MAX, score))
                normalized = (clamped - self.SCORE_MIN) / score_range if score_range > 0 else 0.0
                y = plot_rect.bottom() - (normalized * height)
                return QPointF(x, y)

            latest_score = self._points[-1][1]
            if latest_score >= 80:
                line_color = QColor("#00CC00")
            elif latest_score >= 50:
                line_color = QColor("#F59E0B")
            else:
                line_color = QColor("#FF6B6B")

            painter.setPen(QPen(line_color, 2))
            prev_point = None
            for i, (_iteration, score) in enumerate(self._points):
                current_point = point_at(i, score)
                if prev_point is not None:
                    painter.drawLine(prev_point, current_point)
                prev_point = current_point

            if prev_point is not None:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(line_color))
                painter.drawEllipse(prev_point, 3, 3)
        finally:
            painter.end()


class IterationProgressWidget(QWidget):
    """
    Self-contained live progress view for an iterative AI refinement run.

    Shows a live sparkline of recorded match scores, a current-score readout,
    a free-form cost readout, and a Cancel button. Has no dependency on
    active_panel_widget.py or panel_widgets.py; the caller wires it up (see
    the INTEGRATION comment block at the top of this file).
    """

    # Emitted when the user clicks Cancel. The caller is responsible for
    # actually stopping the iteration loop.
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("iterationProgressWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_label = QLabel("Iteration Progress")
        title_label.setStyleSheet("color: #E5E7EB; font-size: 12px; font-weight: bold;")
        header_row.addWidget(title_label)
        header_row.addStretch()

        self.current_score_label = QLabel("Score: --")
        self.current_score_label.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
        header_row.addWidget(self.current_score_label)
        layout.addLayout(header_row)

        self.sparkline = _ScoreSparkline(self)
        layout.addWidget(self.sparkline)

        footer_row = QHBoxLayout()
        self.cost_label = QLabel("")
        self.cost_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        footer_row.addWidget(self.cost_label)
        footer_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("iterationCancelButton")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setStyleSheet("""
            QPushButton#iterationCancelButton {
                background-color: #7F1D1D;
                color: #FFFFFF;
                border: 1px solid #991B1B;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton#iterationCancelButton:hover {
                background-color: #991B1B;
            }
        """)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        footer_row.addWidget(self.cancel_button)
        layout.addLayout(footer_row)

    def add_score(self, iteration, score):
        """
        Record a new iteration's score, refreshing both the sparkline and the
        current-score readout label.

        Args:
            iteration: Iteration number (int).
            score: Match score, expected on a 0-100 scale.
        """
        try:
            score_value = float(score)
            iteration_value = int(iteration)
        except (TypeError, ValueError):
            return

        self.sparkline.add_score(iteration_value, score_value)
        self.current_score_label.setText(f"Score: {score_value:.0f}/100 (iter {iteration_value})")

    def set_cost_text(self, text):
        """
        Set the free-form cost readout text, e.g. the output of
        utils/cost_estimator.py's format_estimate().

        Args:
            text: Short human-readable cost string, or falsy to clear it.
        """
        self.cost_label.setText(text or "")

    def reset(self):
        """Clear recorded scores and readouts, e.g. when starting a new panel."""
        self.sparkline.clear_scores()
        self.current_score_label.setText("Score: --")
        self.cost_label.setText("")

    def _on_cancel_clicked(self):
        self.cancelled.emit()

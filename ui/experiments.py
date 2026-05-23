"""
experiments.py — Experiment management screen (Step 4).

Layout:
    ┌─── Header ───────────────────────────────────────────────────┐
    ├─── Left: New Experiment form ──┬─── Right: Experiment list ──┤
    │  Name                          │  Table: all experiments     │
    │  Start date                    │  with status badges and     │
    │  CECs being spiked             │  action buttons             │
    │  Spike concentration           │                             │
    │  Description                   │                             │
    │  [Create Experiment]           │                             │
    └────────────────────────────────┴─────────────────────────────┘

Rules:
  • Only ONE experiment can be "active" at a time.
  • Setting an experiment active clears the active flag on all others.
  • An experiment is "Complete" when its end_date is set.
  • All data entry screens (Daily Log, CEC Tracker, etc.) link to the
    single active experiment — so the researcher must set one before
    entering data.
"""

from datetime import date as dt_date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QDoubleSpinBox, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QSizePolicy, QSplitter, QScrollArea, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QDate, QSize, Signal
from PySide6.QtGui import QFont, QColor, QBrush

import statistics

from core.database import get_session
from ui.theme import confirm_discard
from core.models import Experiment, DailyReading, CECReading, MassBalanceResult


# ── Style constants ────────────────────────────────────────────────────────────
HDR_BG       = "#2c3e50"
ACTIVE_ROW   = "#d5f5e3"    # light green tint for active experiment row
RUNNING_ROW  = "#eaf4fb"    # light blue for running (not yet active)
COMPLETE_ROW = "#f2f3f4"    # light grey for completed experiments
BTN_PRIMARY  = "#2980b9"
BTN_SUCCESS  = "#27ae60"
BTN_NEUTRAL  = "#85929e"


class ExperimentsScreen(QWidget):
    """
    Full experiment management screen.
    Emits `experiment_changed` whenever the active experiment is updated
    so other screens can react (e.g. refresh status bars).
    """

    # Emitted when active experiment changes or a new one is created
    experiment_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # Splitter: form on the left, list on the right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #dde1e7; }")
        splitter.addWidget(self._build_form_panel())
        splitter.addWidget(self._build_list_panel())
        splitter.setSizes([380, 820])   # initial proportions
        root.addWidget(splitter, stretch=1)

        self._refresh_list()

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {HDR_BG};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)

        title = QLabel("Experiments")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        # Refresh button
        btn = QPushButton("  Refresh")
        btn.setIcon(qta.icon("fa6s.rotate-left", color="#ecf0f1"))
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(32)
        btn.setStyleSheet(self._secondary_btn_style())
        btn.clicked.connect(self._refresh_list)
        row.addWidget(btn)

        return bar

    # ── Form panel (left) ──────────────────────────────────────────────────────
    def _build_form_panel(self) -> QWidget:
        """
        Scrollable left panel containing the New Experiment form.
        """
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.NoFrame)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.setStyleSheet("background-color: #ffffff;")

        card = QWidget()
        card.setStyleSheet("background-color: #ffffff;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(6)

        # Panel title
        panel_title = QLabel("New Experiment")
        f = QFont(); f.setPointSize(12); f.setBold(True)
        panel_title.setFont(f)
        panel_title.setStyleSheet("color: #2c3e50; margin-bottom: 4px;")
        layout.addWidget(panel_title)

        divider = self._make_divider()
        layout.addWidget(divider)
        layout.addSpacing(8)

        # ── Form fields ────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)

        # Experiment name
        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("e.g. Run 1 — PFOS spike 50 µg/L")
        self._f_name.setFixedHeight(32)
        self._f_name.setStyleSheet(self._input_style())
        form.addRow(self._label("Experiment name *"), self._f_name)

        # Start date
        self._f_start = QDateEdit()
        self._f_start.setDate(QDate.currentDate())
        self._f_start.setCalendarPopup(True)
        self._f_start.setFixedHeight(32)
        self._f_start.setDisplayFormat("yyyy-MM-dd")
        self._f_start.setStyleSheet(self._input_style())
        form.addRow(self._label("Start date *"), self._f_start)

        # CECs being spiked
        self._f_cecs = QLineEdit()
        self._f_cecs.setPlaceholderText("e.g. PFOS, PFBA, PFBS")
        self._f_cecs.setFixedHeight(32)
        self._f_cecs.setStyleSheet(self._input_style())
        form.addRow(self._label("CECs spiked"), self._f_cecs)

        # Spike concentration
        conc_row = QHBoxLayout()
        conc_row.setSpacing(6)
        self._f_conc = QDoubleSpinBox()
        self._f_conc.setRange(0.0, 100000.0)
        self._f_conc.setDecimals(2)
        self._f_conc.setValue(0.0)
        self._f_conc.setFixedHeight(32)
        self._f_conc.setStyleSheet(self._input_style())
        self._f_conc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        unit = QLabel("µg/L")
        unit.setStyleSheet("color: #636e72; font-size: 11px;")
        conc_row.addWidget(self._f_conc)
        conc_row.addWidget(unit)
        conc_widget = QWidget()
        conc_widget.setLayout(conc_row)
        form.addRow(self._label("Spike concentration"), conc_widget)

        # Description
        self._f_desc = QTextEdit()
        self._f_desc.setPlaceholderText("Brief description of this experimental run…")
        self._f_desc.setFixedHeight(80)
        self._f_desc.setStyleSheet(self._input_style())
        form.addRow(self._label("Description"), self._f_desc)

        # Notes
        self._f_notes = QTextEdit()
        self._f_notes.setPlaceholderText("Any additional notes or observations…")
        self._f_notes.setFixedHeight(64)
        self._f_notes.setStyleSheet(self._input_style())
        form.addRow(self._label("Notes"), self._f_notes)

        layout.addLayout(form)
        layout.addSpacing(16)

        # ── Submit button ──────────────────────────────────────────────────────
        self._create_btn = QPushButton("  Create Experiment")
        self._create_btn.setIcon(qta.icon("fa6s.plus", color="#ffffff"))
        self._create_btn.setIconSize(QSize(13, 13))
        self._create_btn.setFixedHeight(40)
        self._create_btn.setCursor(Qt.PointingHandCursor)
        self._create_btn.setStyleSheet(self._primary_btn_style(BTN_PRIMARY))
        self._create_btn.clicked.connect(self._on_create)
        layout.addWidget(self._create_btn)

        # Error / success message label
        self._form_msg = QLabel("")
        self._form_msg.setWordWrap(True)
        self._form_msg.setStyleSheet("font-size: 11px; padding-top: 4px;")
        layout.addWidget(self._form_msg)

        layout.addStretch()
        outer.setWidget(card)
        return outer

    # ── List panel (right) ─────────────────────────────────────────────────────
    def _build_list_panel(self) -> QWidget:
        """
        Right panel with a QTableWidget listing all experiments.
        """
        panel = QWidget()
        panel.setStyleSheet("background-color: #f8f9fa;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Panel title
        title = QLabel("All Experiments")
        f = QFont(); f.setPointSize(12); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)
        layout.addWidget(self._make_divider())

        # Legend row
        legend = QHBoxLayout()
        for color, text in [
            (ACTIVE_ROW,   "Active (data links here)"),
            (RUNNING_ROW,  "Running (not selected)"),
            (COMPLETE_ROW, "Complete"),
        ]:
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {QColor(color).darker(120).name()}; font-size: 13px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #636e72; font-size: 10px;")
            legend.addWidget(dot)
            legend.addWidget(lbl)
            legend.addSpacing(12)
        legend.addStretch()
        layout.addLayout(legend)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Experiment Name", "CECs Spiked", "Start Date", "End Date", "Status", "Actions"]
        )
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._table.setColumnWidth(5, 200)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(False)   # we handle row colours manually
        self._table.setShowGrid(False)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #dde1e7;
                border-radius: 6px;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: #ecf0f1;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 10px;
                border: none;
            }
            QTableWidget::item {
                padding: 6px 10px;
            }
        """)
        layout.addWidget(self._table, stretch=1)

        return panel

    # ── Database operations ────────────────────────────────────────────────────
    def _on_create(self) -> None:
        """
        Validate the form, create a new Experiment record, then refresh the list.
        If the new experiment is the first one, automatically set it active.
        """
        name = self._f_name.text().strip()
        if not name:
            self._set_form_msg("Experiment name is required.", error=True)
            self._f_name.setFocus()
            return

        start_qdate = self._f_start.date()
        start = dt_date(start_qdate.year(), start_qdate.month(), start_qdate.day())

        cec_text = self._f_cecs.text().strip() or None
        conc     = self._f_conc.value() if self._f_conc.value() > 0 else None
        desc     = self._f_desc.toPlainText().strip() or None
        notes    = self._f_notes.toPlainText().strip() or None

        try:
            with get_session() as session:
                # Check if this will be the first experiment
                total = session.query(Experiment).count()
                new_exp = Experiment(
                    name        = name,
                    start_date  = start,
                    cec_spiked  = cec_text,
                    spike_conc  = conc,
                    description = desc,
                    notes       = notes,
                    is_active   = (total == 0),   # auto-activate if first
                )
                session.add(new_exp)

        except Exception as exc:
            self._set_form_msg(f"Could not save: {exc}", error=True)
            return

        self._set_form_msg(f'"{name}" created successfully.', error=False)
        self._clear_form()
        self._refresh_list()
        self.experiment_changed.emit()

    def _set_active(self, exp_id: int) -> None:
        """
        Make the chosen experiment active and deactivate all others.
        All daily logs, CEC entries, and mass balance results will now
        link to this experiment.
        """
        try:
            with get_session() as session:
                # Deactivate all
                session.query(Experiment).update({"is_active": False})
                # Activate chosen
                session.query(Experiment).filter_by(id=exp_id).update({"is_active": True})
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not set active experiment:\n{exc}")
            return

        self._refresh_list()
        self.experiment_changed.emit()

    def _mark_complete(self, exp_id: int) -> None:
        """Set end_date = today, then show a completion summary."""
        confirmed = confirm_discard(
            self, "Mark Complete",
            "Mark this experiment as complete?\n\n"
            "This sets the end date to today. You can still view its data afterwards.",
            yes_label="Mark Complete",
            no_label="Cancel",
        )
        if not confirmed:
            return

        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(id=exp_id).first()
                if exp:
                    exp.end_date = dt_date.today()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not update experiment:\n{exc}")
            return

        self._refresh_list()
        self.experiment_changed.emit()
        self._show_completion_summary(exp_id)

    def _show_completion_summary(self, exp_id: int) -> None:
        """Build and display a summary dialog for a completed experiment."""
        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(id=exp_id).first()
                if not exp:
                    return

                n_daily = (
                    session.query(DailyReading)
                    .filter_by(experiment_id=exp_id)
                    .count()
                )
                cec_dates = (
                    session.query(CECReading.reading_date)
                    .filter_by(experiment_id=exp_id)
                    .distinct()
                    .all()
                )
                n_cec_days = len(cec_dates)

                mb_rows = (
                    session.query(MassBalanceResult)
                    .filter_by(experiment_id=exp_id)
                    .all()
                )
                removals = [r.removal_pct for r in mb_rows if r.removal_pct is not None]

                duration = (
                    (exp.end_date - exp.start_date).days
                    if exp.start_date and exp.end_date else None
                )

        except Exception as exc:
            QMessageBox.warning(self, "Summary Error", str(exc))
            return

        # Build summary text
        lines = [
            f"Experiment:   {exp.name}",
            f"Duration:     {exp.start_date}  →  {exp.end_date}"
            + (f"  ({duration} days)" if duration else ""),
            "",
            f"Daily log entries:      {n_daily} zone-readings",
            f"CEC measurement days:   {n_cec_days}",
            f"Mass balance runs:      {len(mb_rows)}",
        ]

        if removals:
            mean_r = statistics.mean(removals)
            sd_r   = statistics.stdev(removals) if len(removals) > 1 else 0.0
            lines += [
                "",
                "─── Removal Efficiency (all CECs) ───",
                f"  Mean removal:   {mean_r:.1f}%",
                f"  Std dev:        {sd_r:.1f}%",
                f"  Best reading:   {max(removals):.1f}%",
                f"  Worst reading:  {min(removals):.1f}%",
            ]

        if exp.cec_spiked:
            lines += ["", f"CECs spiked:  {exp.cec_spiked}"]
        if exp.spike_conc:
            lines += [f"Spike conc:   {exp.spike_conc} µg/L"]

        lines += [
            "",
            "Data is archived. Export a full report from the Mass Balance screen.",
        ]

        msg = QMessageBox(self)
        msg.setWindowTitle("Experiment Complete — Summary")
        msg.setText(f"<b>{exp.name}</b> has been marked complete.")
        msg.setDetailedText("\n".join(lines))
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _refresh_list(self) -> None:
        """
        Reload all experiments from the database and rebuild the table.
        Called after any create / activate / complete action, and on showEvent.
        """
        try:
            with get_session() as session:
                experiments = (
                    session.query(Experiment)
                    .order_by(Experiment.start_date.desc())
                    .all()
                )
                # Detach so we can use after session closes
                data = [
                    {
                        "id":         e.id,
                        "name":       e.name,
                        "cec_spiked": e.cec_spiked or "—",
                        "start_date": str(e.start_date),
                        "end_date":   str(e.end_date) if e.end_date else "—",
                        "is_active":  e.is_active,
                        "complete":   e.end_date is not None,
                    }
                    for e in experiments
                ]
        except Exception as exc:
            QMessageBox.warning(self, "Database Error", str(exc))
            return

        self._table.setRowCount(0)

        if not data:
            self._table.setRowCount(1)
            msg = QTableWidgetItem("No experiments yet — create one using the form on the left.")
            msg.setTextAlignment(Qt.AlignCenter)
            msg.setForeground(QBrush(QColor("#95a5a6")))
            self._table.setItem(0, 0, msg)
            self._table.setSpan(0, 0, 1, 6)
            return

        self._table.setRowCount(len(data))
        self._table.setRowCount(len(data))

        for row, exp in enumerate(data):
            # Row background colour by status
            if exp["is_active"]:
                row_color = QColor(ACTIVE_ROW)
                status_text  = "Active"
                status_color = "#1e8449"
            elif exp["complete"]:
                row_color = QColor(COMPLETE_ROW)
                status_text  = "Complete"
                status_color = "#7f8c8d"
            else:
                row_color = QColor(RUNNING_ROW)
                status_text  = "Running"
                status_color = "#2471a3"

            cells = [
                exp["name"],
                exp["cec_spiked"],
                exp["start_date"],
                exp["end_date"],
                "",   # status — rendered as label below
            ]

            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(QBrush(row_color))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self._table.setItem(row, col, item)

            # Status badge (col 4)
            status_lbl = QLabel(f"  {status_text}  ")
            status_lbl.setAlignment(Qt.AlignCenter)
            status_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {row_color.name()};
                    color: {status_color};
                    font-weight: bold;
                    font-size: 11px;
                }}
            """)
            self._table.setCellWidget(row, 4, status_lbl)

            # Action buttons (col 5)
            self._table.setCellWidget(row, 5, self._make_action_widget(exp, row_color))
            self._table.setRowHeight(row, 44)

    def _make_action_widget(self, exp: dict, row_color: QColor) -> QWidget:
        """
        Build the action buttons for one table row.
        Shows 'Set Active' if not active, 'Mark Complete' if still running.
        """
        widget = QWidget()
        widget.setStyleSheet(f"background-color: {row_color.name()};")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        if not exp["is_active"]:
            btn_act = QPushButton("Set Active")
            btn_act.setIcon(qta.icon("fa6s.circle-check", color="#ffffff"))
            btn_act.setIconSize(QSize(12, 12))
            btn_act.setFixedHeight(28)
            btn_act.setCursor(Qt.PointingHandCursor)
            btn_act.setStyleSheet(self._primary_btn_style(BTN_SUCCESS, small=True))
            btn_act.clicked.connect(lambda _=False, eid=exp["id"]: self._set_active(eid))
            layout.addWidget(btn_act)

        if not exp["complete"]:
            btn_done = QPushButton("Mark Complete")
            btn_done.setIcon(qta.icon("fa6s.flag-checkered", color="#ffffff"))
            btn_done.setIconSize(QSize(12, 12))
            btn_done.setFixedHeight(28)
            btn_done.setCursor(Qt.PointingHandCursor)
            btn_done.setStyleSheet(self._primary_btn_style(BTN_NEUTRAL, small=True))
            btn_done.clicked.connect(lambda _=False, eid=exp["id"]: self._mark_complete(eid))
            layout.addWidget(btn_done)

        layout.addStretch()
        return widget

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        """Refresh the list whenever the user navigates to this screen."""
        super().showEvent(event)
        self._refresh_list()

    # ── Form helpers ───────────────────────────────────────────────────────────
    def _clear_form(self) -> None:
        """Reset all form fields to their defaults."""
        self._f_name.clear()
        self._f_start.setDate(QDate.currentDate())
        self._f_cecs.clear()
        self._f_conc.setValue(0.0)
        self._f_desc.clear()
        self._f_notes.clear()

    def _set_form_msg(self, text: str, error: bool) -> None:
        color = "#e74c3c" if error else "#27ae60"
        self._form_msg.setText(text)
        self._form_msg.setStyleSheet(f"font-size: 11px; color: {color}; padding-top: 4px;")

    # ── Style helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #2c3e50; font-size: 11px; font-weight: 600;")
        return lbl

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.HLine)
        d.setStyleSheet("color: #dde1e7; margin: 2px 0;")
        return d

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit, QTextEdit, QDoubleSpinBox, QDateEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 4px 8px;
                background: #ffffff;
                font-size: 11px;
                color: #2c3e50;
            }
            QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QDateEdit:focus {
                border-color: #2980b9;
            }
        """

    @staticmethod
    def _primary_btn_style(color: str, small: bool = False) -> str:
        fs   = "10px" if small else "11px"
        pad  = "0 10px" if small else "0 16px"
        return f"""
            QPushButton {{
                background-color: {color};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: {fs};
                font-weight: 600;
                padding: {pad};
            }}
            QPushButton:hover {{ background-color: {QColor(color).lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {QColor(color).darker(115).name()}; }}
        """

    @staticmethod
    def _secondary_btn_style() -> str:
        return """
            QPushButton {
                background: #3d5166;
                color: #ecf0f1;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
                font-size: 11px;
            }
            QPushButton:hover { background: #3498db; }
        """

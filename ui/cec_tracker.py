"""
cec_tracker.py — CEC (Contaminants of Emerging Concern) concentration
entry and tracking screen (Step 6).

Layout:
    ┌─── Header: title · date picker · Save button ───────────────────┐
    ├─── Active experiment info strip ────────────────────────────────┤
    ├─── Left: Entry form ────────────────┬─── Right: Results ────────┤
    │  CEC name / type / method           │  Removal efficiency table  │
    │  4 × sampling point rows            │  SP1→SP2→SP3→SP4 chart    │
    │  (conc / BDL checkbox / det limit)  │                           │
    └─────────────────────────────────────┴───────────────────────────┘
    ├─── Recent CEC readings history table ───────────────────────────┘

Sampling points:
    SP1_influent   — raw influent (before any treatment)
    SP2_primary    — after anaerobic zone
    SP3_clarifier  — clarifier output
    SP4_effluent   — final effluent

Removal efficiency is calculated automatically:
    removal % = (SP1 - SP4) / SP1 × 100  (overall)
    stage %   = (SPn - SPn+1) / SPn × 100 (per stage)
"""

from datetime import date as dt_date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QDateEdit, QFrame, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis, QCategoryAxis,
)

from core.database import get_session
from core.models import Experiment, CECReading
from core.validators import validate_cec_payload, summarize_issues
from ui.theme import dark_date_edit_style


# ── Sampling point definitions ─────────────────────────────────────────────────
SAMPLING_POINTS = [
    ("SP1_influent",  "SP1 — Influent",   "#e74c3c"),
    ("SP2_primary",   "SP2 — Anaerobic",  "#8e44ad"),
    ("SP3_clarifier", "SP3 — Clarifier",  "#2471a3"),
    ("SP4_effluent",  "SP4 — Effluent",   "#27ae60"),
]

SP_LABELS = {k: label for k, label, _ in SAMPLING_POINTS}

# Common CEC names for quick-select
COMMON_CECS = [
    "", "PFOS", "PFOA", "PFBA", "PFBS", "PFHxA", "PFHxS",
    "PFNA", "PFDA", "PFUnDA", "6:2 FTS", "8:2 FTS",
]

C_HDR = "#2c3e50"


class CECTrackerScreen(QWidget):
    """CEC concentration entry, removal efficiency display, and history."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._dirty = False
        self._loading_form = False
        self._loaded_date = QDate.currentDate()

        # sp_key → {spin, bdl_check, det_spin}
        self._sp_widgets: dict[str, dict] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_info_strip())

        # ── Layout: horizontal splitter for panels; fixed-height history below.
        # Vertical sizing is fixed (no vertical splitter) — QScrollArea provides
        # overflow scrolling if the window is too short.

        # Horizontal splitter: entry form | results panel (user drags left/right)
        top = QSplitter(Qt.Horizontal)
        top.setChildrenCollapsible(False)
        top.setHandleWidth(4)
        top.setStyleSheet("QSplitter::handle { background: #dfe6e9; }")
        top.addWidget(self._panel_card("CEC Entry Form",     self._build_entry_form()))
        top.addWidget(self._panel_card("Removal Efficiency", self._build_results_panel()))
        top.setSizes([480, 420])
        top.setMinimumHeight(420)

        # History table — fixed height, no vertical resizing
        history_card = self._panel_card("Reading History", self._build_history_section())
        history_card.setFixedHeight(240)

        # Stack them in a plain widget
        body = QWidget()
        body_vl = QVBoxLayout(body)
        body_vl.setContentsMargins(0, 0, 0, 0)
        body_vl.setSpacing(2)
        body_vl.addWidget(top, stretch=1)
        body_vl.addWidget(history_card)

        # Scroll area: vertical scroll if window too short, never horizontal
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)

        root.addWidget(scroll, stretch=1)
        self._wire_dirty_tracking()

    # ── Panel card wrapper ─────────────────────────────────────────────────────
    def _panel_card(self, title: str, widget: QWidget) -> QWidget:
        """Wrap a panel widget with a dark title bar — replaces QDockWidget header."""
        card = QWidget()
        card.setStyleSheet("background: #f5f6fa;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet(f"background: {C_HDR}; border-bottom: 1px solid #3d5166;")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #ecf0f1; font-size: 11px; font-weight: 600;")
        hrow.addWidget(lbl)
        hrow.addStretch()
        layout.addWidget(hdr)
        layout.addWidget(widget, stretch=1)
        return card

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        title = QLabel("CEC Tracker")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        date_lbl = QLabel("Reading date:")
        date_lbl.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        row.addWidget(date_lbl)

        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setFixedHeight(30)
        self._date_edit.setFixedWidth(130)
        self._date_edit.setStyleSheet(dark_date_edit_style())
        self._date_edit.dateChanged.connect(self._on_date_changed_request)
        row.addWidget(self._date_edit)

        self._save_btn = QPushButton("  Save CEC Readings")
        self._save_btn.setIcon(qta.icon("fa6s.floppy-disk", color="#ffffff"))
        self._save_btn.setIconSize(QSize(13, 13))
        self._save_btn.setFixedHeight(34)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet("""
            QPushButton { background:#2980b9; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }
            QPushButton:hover { background:#3498db; }
            QPushButton:pressed { background:#1a5276; }
        """)
        self._save_btn.clicked.connect(self._on_save)
        row.addWidget(self._save_btn)

        return bar

    # ── Info strip ─────────────────────────────────────────────────────────────
    def _build_info_strip(self) -> QWidget:
        strip = QWidget()
        strip.setFixedHeight(30)
        strip.setStyleSheet("background:#dfe6e9; border-bottom:1px solid #b2bec3;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 0, 14, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa6s.flask", color="#636e72").pixmap(QSize(13, 13)))
        row.addWidget(icon_lbl)
        row.addSpacing(5)
        self._info_label = QLabel("Loading…")
        self._info_label.setStyleSheet("color:#636e72; font-size:11px;")
        row.addWidget(self._info_label)
        row.addStretch()
        self._save_msg = QLabel("")
        self._save_msg.setStyleSheet("font-size:11px;")
        row.addWidget(self._save_msg)
        return strip

    # ── Entry form (left panel) ────────────────────────────────────────────────
    def _build_entry_form(self) -> QWidget:
        """
        Left panel: CEC identity fields + one row per sampling point.
        Each sampling point row has: concentration spinbox, BDL checkbox,
        detection limit spinbox.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        # Section title
        t = QLabel("Enter CEC Concentrations")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        # ── CEC identity ───────────────────────────────────────────────────────
        id_form = QFormLayout()
        id_form.setSpacing(10)
        id_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # CEC name (combo + free-type)
        self._cec_name = QComboBox()
        self._cec_name.setEditable(True)
        self._cec_name.addItems(COMMON_CECS)
        self._cec_name.setFixedHeight(30)
        self._cec_name.setStyleSheet(self._input_style())
        self._cec_name.lineEdit().setPlaceholderText("Select or type CEC name…")
        id_form.addRow(self._lbl("CEC name *"), self._cec_name)

        # CEC type
        self._cec_type = QComboBox()
        self._cec_type.addItems(["", "short-chain", "long-chain"])
        self._cec_type.setFixedHeight(30)
        self._cec_type.setStyleSheet(self._input_style())
        id_form.addRow(self._lbl("Chain type"), self._cec_type)

        # Analysis method
        self._method = QComboBox()
        self._method.addItems(["", "TOF-MS", "GC-MS", "LC-MS/MS", "HPLC"])
        self._method.setFixedHeight(30)
        self._method.setStyleSheet(self._input_style())
        id_form.addRow(self._lbl("Analysis method"), self._method)

        layout.addLayout(id_form)

        # ── Sampling point rows ────────────────────────────────────────────────
        sp_title = QLabel("Concentrations at Each Sampling Point (µg/L)")
        sp_title.setStyleSheet("color:#636e72; font-size:10px; font-weight:600;")
        layout.addWidget(sp_title)

        # Column headers
        hdr = QGridLayout()
        hdr.setSpacing(6)
        for col, text in enumerate(["Sampling Point", "Conc. (µg/L)", "Below\nDetection", "Det. Limit\n(µg/L)"]):
            h = QLabel(text)
            h.setAlignment(Qt.AlignCenter)
            h.setStyleSheet("color:#7f8c8d; font-size:10px; font-weight:600;")
            hdr.addWidget(h, 0, col)
        layout.addLayout(hdr)
        layout.addWidget(self._make_divider())

        for sp_key, sp_label, sp_color in SAMPLING_POINTS:
            row_w = self._build_sp_row(sp_key, sp_label, sp_color)
            layout.addWidget(row_w)

        layout.addStretch()
        return card

    def _build_sp_row(self, sp_key: str, label: str, color: str) -> QWidget:
        """One row per sampling point: label · conc spinbox · BDL check · det-limit spinbox."""
        row_w = QWidget()
        row_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(row_w)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(8)

        # Coloured label
        lbl = QLabel(label)
        lbl.setFixedWidth(150)
        lbl.setStyleSheet(f"color:{color}; font-size:11px; font-weight:600;")
        grid.addWidget(lbl, 0, 0)

        # Concentration
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100000.0)
        spin.setDecimals(4)
        spin.setValue(0.0)
        spin.setSpecialValueText("—")
        spin.setFixedHeight(28)
        spin.setStyleSheet(self._spin_style())
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid.addWidget(spin, 0, 1)

        # BDL checkbox — disables the concentration spinbox when checked
        bdl = QCheckBox("BDL")
        bdl.setStyleSheet("font-size:11px; color:#636e72;")
        bdl.setToolTip("Check if this reading is Below the Detection Limit")
        bdl.toggled.connect(lambda checked, s=spin: s.setEnabled(not checked))
        grid.addWidget(bdl, 0, 2, Qt.AlignCenter)

        # Detection limit
        det = QDoubleSpinBox()
        det.setRange(0.0, 10000.0)
        det.setDecimals(4)
        det.setValue(0.0)
        det.setSpecialValueText("—")
        det.setFixedHeight(28)
        det.setToolTip("Instrument detection limit for this measurement")
        det.setStyleSheet(self._spin_style())
        det.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid.addWidget(det, 0, 3)

        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(3, 1)

        self._sp_widgets[sp_key] = {"spin": spin, "bdl": bdl, "det": det}
        return row_w

    # ── Results panel (right panel) ────────────────────────────────────────────
    def _build_results_panel(self) -> QWidget:
        """
        Right panel: removal efficiency table + concentration profile chart.
        Both update whenever the form values change or the date changes.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        t = QLabel("Removal Efficiency")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        # Efficiency summary table (stages + overall)
        self._eff_table = QTableWidget(5, 2)
        self._eff_table.setHorizontalHeaderLabels(["Stage", "Removal %"])
        self._eff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._eff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._eff_table.verticalHeader().setVisible(False)
        self._eff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._eff_table.setFixedHeight(188)
        self._eff_table.setShowGrid(False)
        self._eff_table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:11px; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:5px 10px; }
        """)
        layout.addWidget(self._eff_table)
        self._populate_eff_table([])   # empty on init

        # Concentration profile chart (SP1 → SP4)
        chart_title = QLabel("Concentration Profile  SP1 → SP4")
        chart_title.setStyleSheet("color:#636e72; font-size:10px; font-weight:600;")
        layout.addWidget(chart_title)
        layout.addWidget(self._build_chart(), stretch=1)

        return card

    def _build_chart(self) -> QChartView:
        """
        QLineSeries chart showing concentration at each sampling point.
        Uses QtCharts — included with PySide6.
        """
        self._series = QLineSeries()
        self._series.setName("Concentration (µg/L)")

        # Style the line and points
        pen = self._series.pen()
        pen.setWidth(2)
        pen.setColor(QColor("#2980b9"))
        self._series.setPen(pen)
        self._series.setPointsVisible(True)

        self._chart = QChart()
        self._chart.addSeries(self._series)
        self._chart.setTitle("")
        self._chart.legend().hide()
        self._chart.setBackgroundRoundness(0)
        self._chart.setMargins(__import__('PySide6.QtCore', fromlist=['QMargins']).QMargins(8, 8, 8, 8))
        self._chart.setBackgroundBrush(QBrush(QColor("#ffffff")))

        # X axis — category labels SP1-SP4
        self._x_axis = QCategoryAxis()
        self._x_axis.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
        for i, (_, lbl, _) in enumerate(SAMPLING_POINTS):
            self._x_axis.append(lbl.split("—")[0].strip(), i)
        self._x_axis.setRange(-0.5, 3.5)
        self._x_axis.setGridLineVisible(False)

        self._y_axis = QValueAxis()
        self._y_axis.setTitleText("µg/L")
        self._y_axis.setRange(0, 1)
        self._y_axis.setTickCount(5)
        self._y_axis.setLabelFormat("%.3f")

        self._chart.addAxis(self._x_axis, Qt.AlignBottom)
        self._chart.addAxis(self._y_axis, Qt.AlignLeft)
        self._series.attachAxis(self._x_axis)
        self._series.attachAxis(self._y_axis)

        view = QChartView(self._chart)
        view.setRenderHint(__import__('PySide6.QtGui', fromlist=['QPainter']).QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(200)
        view.setStyleSheet("border:1px solid #dde1e7; border-radius:6px;")
        self._chart_view = view
        return view

    def _wire_dirty_tracking(self) -> None:
        """Connect all editable fields so we can warn before discarding unsaved values."""
        self._cec_name.currentTextChanged.connect(self._mark_dirty)
        self._cec_type.currentTextChanged.connect(self._mark_dirty)
        self._method.currentTextChanged.connect(self._mark_dirty)
        for sp_key, _, _ in SAMPLING_POINTS:
            w = self._sp_widgets[sp_key]
            w["spin"].valueChanged.connect(self._mark_dirty)
            w["bdl"].toggled.connect(self._mark_dirty)
            w["det"].valueChanged.connect(self._mark_dirty)

    # ── Save logic ─────────────────────────────────────────────────────────────
    def _on_save(self) -> None:
        """
        Validate and save one CECReading row per sampling point.
        Upserts: updates existing row for (experiment, date, cec, sp) if found.
        """
        active = self._get_active_experiment()
        if not active:
            QMessageBox.warning(self, "No Active Experiment",
                "Please go to Experiments and set one as active first.")
            return

        cec_name = self._cec_name.currentText().strip()
        if not cec_name:
            QMessageBox.warning(self, "Missing CEC Name", "Please enter a CEC name.")
            return

        qd = self._date_edit.date()
        reading_date = dt_date(qd.year(), qd.month(), qd.day())
        cec_type = self._cec_type.currentText() or None
        method   = self._method.currentText() or None

        sampling_values: dict[str, dict[str, float | bool | None]] = {}
        for sp_key, _, _ in SAMPLING_POINTS:
            w = self._sp_widgets[sp_key]
            sampling_values[sp_key] = {
                "concentration": w["spin"].value(),
                "below_detection": w["bdl"].isChecked(),
                "detection_limit": w["det"].value(),
            }

        issues = validate_cec_payload(sampling_values)
        ok_to_save, override_reason = self._confirm_validation_issues(issues)
        if not ok_to_save:
            return

        try:
            with get_session() as session:
                for sp_key, _, _ in SAMPLING_POINTS:
                    w = self._sp_widgets[sp_key]
                    bdl   = w["bdl"].isChecked()
                    conc  = None if bdl else (
                        w["spin"].value() if w["spin"].value() > 0 else None
                    )
                    det   = w["det"].value() if w["det"].value() > 0 else None

                    existing = (
                        session.query(CECReading)
                        .filter_by(
                            experiment_id  = active["id"],
                            reading_date   = reading_date,
                            cec_name       = cec_name,
                            sampling_point = sp_key,
                        )
                        .first()
                    )
                    row = existing or CECReading(
                        experiment_id  = active["id"],
                        reading_date   = reading_date,
                        cec_name       = cec_name,
                        sampling_point = sp_key,
                    )
                    if not existing:
                        session.add(row)

                    row.cec_type        = cec_type
                    row.concentration   = conc
                    row.below_detection = bdl
                    row.detection_limit = det
                    row.analysis_method = method
                    if override_reason:
                        row.notes = self._append_override_note(row.notes, override_reason, issues)

        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save:\n\n{exc}")
            return

        self._save_msg.setText("  Saved successfully.")
        self._save_msg.setStyleSheet("font-size:11px; color:#27ae60;")
        self._set_dirty(False)
        self._loaded_date = self._date_edit.date()
        self._refresh_history()
        self._update_results_from_form()

    # ── Date changes ──────────────────────────────────────────────────────────
    def _on_date_changed_request(self, qdate: QDate) -> None:
        """Prompt before changing dates when the CEC form has unsaved edits."""
        if self._loading_form:
            return
        if self._dirty:
            keep = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved CEC readings. Discard these changes and use a new date?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if keep != QMessageBox.Yes:
                self._loading_form = True
                self._date_edit.blockSignals(True)
                self._date_edit.setDate(self._loaded_date)
                self._date_edit.blockSignals(False)
                self._loading_form = False
                return
        self._loaded_date = qdate
        self._set_dirty(False)
        self._save_msg.setText("")

    # ── Results update ─────────────────────────────────────────────────────────
    def _update_results_from_form(self) -> None:
        """
        Read current form values and recalculate removal efficiencies
        and chart data without touching the database.
        """
        values: list[float | None] = []
        for sp_key, _, _ in SAMPLING_POINTS:
            w = self._sp_widgets[sp_key]
            if w["bdl"].isChecked():
                det = w["det"].value()
                values.append(det / 2 if det > 0 else 0.0)   # use half MDL convention
            else:
                v = w["spin"].value()
                values.append(v if v > 0 else None)

        self._populate_eff_table(values)
        self._update_chart(values)

    def _populate_eff_table(self, values: list) -> None:
        """Fill the 5-row efficiency table: 3 stage rows + separator + overall."""
        stage_defs = [
            ("Influent → Anaerobic (SP1→SP2)", 0, 1),
            ("Anaerobic → Clarifier (SP2→SP3)", 1, 2),
            ("Clarifier → Effluent (SP3→SP4)",  2, 3),
            (None, None, None),                              # separator row
            ("Overall Removal (SP1→SP4)",        0, 3),
        ]

        self._eff_table.setRowCount(len(stage_defs))
        for row_i, (label, a, b) in enumerate(stage_defs):
            if label is None:
                # Thin separator row
                sep = QTableWidgetItem("")
                sep.setBackground(QBrush(QColor("#f0f3f4")))
                self._eff_table.setItem(row_i, 0, sep)
                self._eff_table.setItem(row_i, 1, QTableWidgetItem(""))
                self._eff_table.setRowHeight(row_i, 6)
                continue

            stage_item = QTableWidgetItem(label)
            stage_item.setFlags(Qt.ItemIsEnabled)
            if row_i == 4:   # overall row — bold
                f = QFont(); f.setBold(True)
                stage_item.setFont(f)

            # Calculate removal %
            removal_text = "—"
            removal_color = QColor("#2c3e50")
            if values and len(values) > max(a, b):
                va, vb = values[a], values[b]
                if va is not None and vb is not None and va > 0:
                    pct = (va - vb) / va * 100
                    removal_text = f"{pct:.1f} %"
                    # Colour-code: green ≥ 60%, amber 30-60%, red < 30%
                    if pct >= 60:
                        removal_color = QColor("#1e8449")
                    elif pct >= 30:
                        removal_color = QColor("#d68910")
                    else:
                        removal_color = QColor("#c0392b")

            val_item = QTableWidgetItem(removal_text)
            val_item.setTextAlignment(Qt.AlignCenter)
            val_item.setForeground(QBrush(removal_color))
            val_item.setFlags(Qt.ItemIsEnabled)
            if row_i == 4:
                f = QFont(); f.setBold(True)
                val_item.setFont(f)

            self._eff_table.setItem(row_i, 0, stage_item)
            self._eff_table.setItem(row_i, 1, val_item)
            self._eff_table.setRowHeight(row_i, 34)

    def _update_chart(self, values: list) -> None:
        """Redraw the SP1→SP4 line chart with current concentration values."""
        self._series.clear()
        valid = [v for v in values if v is not None]
        if not valid:
            self._y_axis.setRange(0, 1)
            return

        max_val = max(valid) * 1.15 if max(valid) > 0 else 1.0
        self._y_axis.setRange(0, max_val)

        for i, v in enumerate(values):
            if v is not None:
                self._series.append(i, v)

    # ── History table ──────────────────────────────────────────────────────────
    def _build_history_section(self) -> QWidget:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)

        t = QLabel("Recent CEC Readings")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        cols = ["Date", "CEC", "Type", "Method",
                "SP1 Influent", "SP2 Anaerobic", "SP3 Clarifier", "SP4 Effluent",
                "Overall Removal %"]
        self._history_table = QTableWidget(0, len(cols))
        self._history_table.setHorizontalHeaderLabels(cols)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for c in range(4, len(cols)):
            self._history_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setShowGrid(False)
        self._history_table.setFixedHeight(220)
        self._history_table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:11px;
                alternate-background-color:#f8f9fa; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:4px 8px; }
        """)
        layout.addWidget(self._history_table)
        return card

    def _refresh_history(self) -> None:
        """
        Load the most recent 30 CEC reading sets (grouped by date+CEC name)
        from the active experiment and populate the history table.
        """
        active = self._get_active_experiment()
        self._history_table.setRowCount(0)
        if not active:
            return

        try:
            with get_session() as session:
                rows = (
                    session.query(CECReading)
                    .filter_by(experiment_id=active["id"])
                    .order_by(CECReading.reading_date.desc(), CECReading.cec_name)
                    .limit(200)   # SQL-level limit avoids loading entire experiment history
                    .all()
                )
                # Group by (date, cec_name) — produce one history row each
                from collections import defaultdict
                groups: dict[tuple, dict] = defaultdict(dict)
                for r in rows:
                    key = (str(r.reading_date), r.cec_name)
                    groups[key][r.sampling_point] = r

        except Exception:
            return

        self._history_table.setRowCount(min(len(groups), 30))
        for row_i, ((date_s, cec_n), sp_map) in enumerate(
            list(groups.items())[:30]
        ):
            def conc_text(sp_key: str) -> str:
                r = sp_map.get(sp_key)
                if r is None:
                    return "—"
                if r.below_detection:
                    dl = f"< {r.detection_limit:.3f}" if r.detection_limit else "BDL"
                    return dl
                return f"{r.concentration:.4f}" if r.concentration is not None else "—"

            # Overall removal
            r_sp1 = sp_map.get("SP1_influent")
            r_sp4 = sp_map.get("SP4_effluent")
            if (r_sp1 and r_sp4 and
                    r_sp1.concentration and r_sp4.concentration and
                    not r_sp1.below_detection and r_sp1.concentration > 0):
                pct = (r_sp1.concentration - r_sp4.concentration) / r_sp1.concentration * 100
                overall = f"{pct:.1f} %"
                ov_color = QColor("#1e8449" if pct >= 60 else "#d68910" if pct >= 30 else "#c0392b")
            else:
                overall = "—"
                ov_color = QColor("#7f8c8d")

            any_r = next(iter(sp_map.values()))
            cells = [
                date_s, cec_n,
                any_r.cec_type or "—",
                any_r.analysis_method or "—",
                conc_text("SP1_influent"),
                conc_text("SP2_primary"),
                conc_text("SP3_clarifier"),
                conc_text("SP4_effluent"),
                overall,
            ]
            for col_i, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col_i == 8:
                    item.setForeground(QBrush(ov_color))
                    f = QFont(); f.setBold(True); item.setFont(f)
                self._history_table.setItem(row_i, col_i, item)
            self._history_table.setRowHeight(row_i, 32)

    # ── Database helpers ───────────────────────────────────────────────────────
    def _get_active_experiment(self) -> dict | None:
        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(is_active=True).first()
                if exp:
                    self._info_label.setText(f"Active experiment:  {exp.name}")
                    self._info_label.setStyleSheet(
                        "color:#1e8449; font-size:11px; font-weight:600;")
                    return {"id": exp.id, "name": exp.name}
        except Exception:
            pass
        self._info_label.setText("No active experiment — go to Experiments to set one.")
        self._info_label.setStyleSheet("color:#e74c3c; font-size:11px;")
        return None

    def _mark_dirty(self, *_args) -> None:
        if not self._loading_form:
            self._set_dirty(True)

    def _confirm_validation_issues(
        self, issues: list
    ) -> tuple[bool, str | None]:
        """Ask user to confirm and document QA override when issues are present."""
        if not issues:
            return True, None

        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            QMessageBox.warning(
                self,
                "Validation Errors",
                "These CEC readings cannot be saved until the following errors are fixed:\n\n"
                f"{summarize_issues(errors)}",
            )
            return False, None

        summary = summarize_issues(issues)
        proceed = QMessageBox.warning(
            self,
            "Validation Checks",
            "CEC validation detected warnings:\n\n"
            f"{summary}\n\n"
            "Do you want to save anyway with a documented QA override reason?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if proceed != QMessageBox.Yes:
            return False, None

        reason, ok = QInputDialog.getText(
            self,
            "QA Override Reason",
            "Enter reason for overriding validation checks:",
        )
        if not ok or not reason.strip():
            QMessageBox.information(
                self,
                "Save Cancelled",
                "A non-empty override reason is required to proceed.",
            )
            return False, None
        return True, reason.strip()

    @staticmethod
    def _append_override_note(existing: str | None, reason: str, issues: list) -> str:
        """Append a timestamped QA override audit entry to per-reading notes."""
        from datetime import datetime

        stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        issue_txt = "; ".join([i.message for i in issues[:4]])
        line = f"[QA Override {stamp}] Reason: {reason}. Checks: {issue_txt}"
        if existing and existing.strip():
            return existing.strip() + "\n" + line
        return line

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty

    def confirm_discard_changes(self) -> bool:
        """Return False when the user cancels navigation with unsaved edits."""
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved CEC readings. Leave this screen and discard changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._save_msg.setText("")
        self._get_active_experiment()
        self._refresh_history()
        self._set_dirty(False)

    # ── Style helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color:#2c3e50; font-size:11px; font-weight:600;")
        return l

    @staticmethod
    def _make_card() -> QWidget:
        w = QWidget()
        w.setStyleSheet("""
            QWidget { background:#ffffff; border-radius:8px;
                      border:1px solid #dde1e7; }
        """)
        return w

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.HLine)
        d.setStyleSheet("color:#dde1e7; margin:2px 0;")
        return d

    @staticmethod
    def _input_style() -> str:
        return """
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:4px 8px; font-size:11px; background:#fff; color:#2c3e50; }
            QComboBox:focus { border-color:#2980b9; }
        """

    @staticmethod
    def _spin_style() -> str:
        return """
            QDoubleSpinBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:11px; background:#fff; color:#2c3e50; }
            QDoubleSpinBox:focus { border-color:#2980b9; }
        """

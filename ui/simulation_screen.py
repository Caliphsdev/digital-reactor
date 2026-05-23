"""
simulation_screen.py — Phase 1 What-If Simulation screen (Step 8).

Layout:
    ┌─── Header: title · Run Simulation button ───────────────────────┐
    ├─── Left panel: Sliders + inputs ─────┬─── Right panel: Results ─┤
    │  Operating parameters (sliders)      │  Removal % gauges        │
    │    Flow rate, DO, SRT, RAS,          │  Effluent concentration  │
    │    Temp, pH                          │  table                   │
    │  Influent concentrations             │  Warning flags           │
    │    COD, NH4, TP, PFAS                │  Bar chart               │
    │  PFAS type selector                  │                          │
    └──────────────────────────────────────┴──────────────────────────┘

All sliders are connected live — results update instantly without
needing to click Run (Run also saves the scenario to the database).
"""

from datetime import datetime, date as dt_date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QSlider, QDoubleSpinBox, QComboBox, QPushButton,
    QFrame, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
)

from simulation.generic_model import (
    SimInputs, SimOutputs, run_phase1,
    PFAS_COMPOUND_LIST, PFAS_COMPOUND_CHAIN_TYPE,
)
from simulation.data_model import (
    run_phase2, get_model_status, train_phase2,
    MAIN_MODEL_THRESHOLD,
)
import simulation.data_model as _dm
from core.database import get_session
from core.models import SimulationRun, Experiment, DailyReading, FlowReading
from core.calculations import calc_actual_srt

C_HDR = "#2c3e50"

# Recommended operating ranges for slider warning colours
PARAM_RANGES = {
    "flow_rate": (200, 450),
    "do":        (1.0, 4.0),
    "srt":       (20, 40),
    "ras":       (0.5, 2.0),
    "temp":      (18, 28),
    "ph":        (6.5, 8.0),
}


class SimulationScreen(QWidget):
    """Phase 1 what-if simulator with live-updating results."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Debounce timer — wait 150 ms after last slider move before recalculating
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._recalculate)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # Horizontal splitter: inputs (left) | results (right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._panel_card("Operating Parameters", self._build_inputs_panel()))
        splitter.addWidget(self._panel_card("Predicted Results",    self._build_results_panel()))
        splitter.setSizes([460, 580])

        root.addWidget(splitter, stretch=1)

        # Run initial calculation with default values
        QTimer.singleShot(0, self._recalculate)

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background:{C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        self._header_title = QLabel("Simulation  —  Phase 1 Generic Model")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        self._header_title.setFont(f)
        self._header_title.setStyleSheet("color:#ecf0f1;")
        row.addWidget(self._header_title)
        row.addStretch()

        # Model selector
        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet("color:#bdc3c7; font-size:11px;")
        self._model_selector = QComboBox()
        self._model_selector.addItems([
            "Phase 1 – Equations",
            "Phase 2 – Data-Driven",
        ])
        self._model_selector.setFixedHeight(30)
        self._model_selector.setFixedWidth(195)
        self._model_selector.setStyleSheet("""
            QComboBox { border:1px solid #566573; border-radius:4px;
                padding:4px 8px; font-size:11px;
                background:#34495e; color:#ecf0f1; }
            QComboBox::drop-down { border:none; }
            QComboBox QAbstractItemView { background:#34495e; color:#ecf0f1; }
        """)
        self._model_selector.currentIndexChanged.connect(self._on_model_changed)
        row.addWidget(model_lbl)
        row.addWidget(self._model_selector)

        load_btn = QPushButton("  Load Today")
        load_btn.setIcon(qta.icon("fa6s.database", color="#fff"))
        load_btn.setIconSize(QSize(13, 13))
        load_btn.setFixedHeight(34)
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.setToolTip("Pre-fill inputs from today's logged readings")
        load_btn.setStyleSheet("""
            QPushButton { background:#16a085; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 14px; }
            QPushButton:hover { background:#1abc9c; }
            QPushButton:pressed { background:#0e8070; }
        """)
        load_btn.clicked.connect(self._load_today_data)
        row.addWidget(load_btn)

        save_btn = QPushButton("  Save Scenario")
        save_btn.setIcon(qta.icon("fa6s.floppy-disk", color="#fff"))
        save_btn.setIconSize(QSize(13, 13))
        save_btn.setFixedHeight(34)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }
            QPushButton:hover { background:#9b59b6; }
            QPushButton:pressed { background:#6c3483; }
        """)
        save_btn.clicked.connect(self._save_scenario)
        row.addWidget(save_btn)

        vl.addWidget(bar)

        # ── Phase 2 status card (hidden until Phase 2 selected) ────────────────
        self._p2_status_card = self._build_p2_status_card()
        self._p2_status_card.setVisible(False)
        vl.addWidget(self._p2_status_card)

        return container

    def _build_p2_status_card(self) -> QWidget:
        """Info card shown below the header when Phase 2 is selected."""
        card = QWidget()
        card.setFixedHeight(76)
        card.setStyleSheet(
            "QWidget { background:#f0f3f4; border-bottom:1px solid #d5dbdb; }"
        )

        row = QHBoxLayout(card)
        row.setContentsMargins(18, 8, 18, 8)
        row.setSpacing(20)

        # Sample count
        self._p2_sample_lbl = QLabel("Samples: —")
        self._p2_sample_lbl.setStyleSheet(
            "color:#2c3e50; font-size:11px; font-weight:600; border:none; background:transparent;"
        )
        row.addWidget(self._p2_sample_lbl)

        # Vertical divider
        div1 = QFrame()
        div1.setFrameShape(QFrame.VLine)
        div1.setStyleSheet("color:#d5dbdb; border:none; background:#d5dbdb;")
        div1.setFixedWidth(1)
        row.addWidget(div1)

        # Last trained
        self._p2_trained_lbl = QLabel("Not trained yet")
        self._p2_trained_lbl.setStyleSheet(
            "color:#7f8c8d; font-size:10px; border:none; background:transparent;"
        )
        row.addWidget(self._p2_trained_lbl)

        # Vertical divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.VLine)
        div2.setStyleSheet("color:#d5dbdb; border:none; background:#d5dbdb;")
        div2.setFixedWidth(1)
        row.addWidget(div2)

        # R² scores
        self._p2_r2_lbl = QLabel("R²: —")
        self._p2_r2_lbl.setStyleSheet(
            "color:#2c3e50; font-size:11px; border:none; background:transparent;"
        )
        row.addWidget(self._p2_r2_lbl)

        row.addStretch()

        # Status / warning message
        self._p2_status_msg = QLabel("")
        self._p2_status_msg.setWordWrap(True)
        self._p2_status_msg.setStyleSheet(
            "color:#e67e22; font-size:10px; font-weight:600; border:none; background:transparent;"
        )
        row.addWidget(self._p2_status_msg, stretch=1)

        # Train button
        self._train_btn = QPushButton("  Train Model")
        self._train_btn.setIcon(qta.icon("fa6s.brain", color="#fff"))
        self._train_btn.setIconSize(QSize(12, 12))
        self._train_btn.setFixedHeight(32)
        self._train_btn.setFixedWidth(130)
        self._train_btn.setCursor(Qt.PointingHandCursor)
        self._train_btn.setStyleSheet("""
            QPushButton { background:#27ae60; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 12px; }
            QPushButton:hover { background:#2ecc71; }
            QPushButton:pressed { background:#1e8449; }
            QPushButton:disabled { background:#aab7b8; color:#ecf0f1; }
        """)
        self._train_btn.clicked.connect(self._on_train_clicked)
        row.addWidget(self._train_btn)

        return card

    def _on_model_changed(self, index: int) -> None:
        """Switch between Phase 1 and Phase 2 prediction modes."""
        titles = [
            "Simulation  —  Phase 1 Generic Model",
            "Simulation  —  Phase 2 Data-Driven Model",
        ]
        self._header_title.setText(titles[index])
        self._p2_status_card.setVisible(index == 1)
        if index == 1:
            self._refresh_p2_status()
        self._debounce.start()

    def _refresh_p2_status(self) -> None:
        """Populate the Phase 2 status card from metadata.json."""
        status = get_model_status()
        n         = status["n_samples_main"]
        threshold = MAIN_MODEL_THRESHOLD

        self._p2_sample_lbl.setText(f"Samples: {n} / {threshold} required")

        if status["main_trained"]:
            dt_raw = status.get("last_trained") or ""
            dt_str = dt_raw[:16].replace("T", " ") + " UTC" if dt_raw else "unknown"
            self._p2_trained_lbl.setText(f"Trained: {dt_str}")

            parts = []
            for key, label in [
                ("r2_cod", "COD"), ("r2_nh4", "NH₄"),
                ("r2_tp", "TP"),   ("r2_pfas", "PFAS"),
            ]:
                val = status.get(key)
                if val is not None:
                    parts.append(f"{label} {val:.2f}")
            self._p2_r2_lbl.setText("R²  " + "  |  ".join(parts) if parts else "R²: —")
            self._p2_status_msg.setText("")
            self._train_btn.setText("  Retrain")
            self._train_btn.setEnabled(True)
        else:
            self._p2_trained_lbl.setText("Not trained yet")
            self._p2_r2_lbl.setText("R²: —")
            self._train_btn.setText("  Train Model")
            if n < threshold:
                needed = threshold - n
                self._p2_status_msg.setText(
                    f"Need {needed} more complete daily readings to enable training."
                )
                self._train_btn.setEnabled(False)
            else:
                self._p2_status_msg.setText(
                    f"{n} samples available — ready to train."
                )
                self._train_btn.setEnabled(True)

    def _on_train_clicked(self) -> None:
        """Kick off model training in a background thread."""
        self._train_btn.setEnabled(False)
        self._train_btn.setText("  Training…")
        self._p2_status_msg.setText("Training in progress…")

        class _TrainWorker(QThread):
            finished = Signal(dict)

            def run(self_inner):
                try:
                    with get_session() as session:
                        result = train_phase2(session)
                    self_inner.finished.emit(result)
                except Exception as exc:
                    self_inner.finished.emit({"status": "error", "message": str(exc)})

        self._train_worker = _TrainWorker()
        self._train_worker.finished.connect(self._on_train_finished)
        self._train_worker.start()

    def _on_train_finished(self, result: dict) -> None:
        """Handle completion of the training worker thread."""
        if result.get("status") == "ok":
            # Invalidate caches so run_phase2 picks up the new model files
            _dm._main_model_cache = None
            _dm._pfas_model_cache = None
            self._refresh_p2_status()
            self._debounce.start()
            cv = result.get("cv_r2_mean")
            cv_str = f"{cv:.3f}" if cv is not None else "n/a"
            QMessageBox.information(
                self, "Training Complete",
                f"Phase 2 model trained on {result['n_samples_main']} samples.\n"
                f"Cross-validated R²: {cv_str}\n\n"
                f"COD R²: {result.get('r2_cod', 0):.3f}  "
                f"NH₄ R²: {result.get('r2_nh4', 0):.3f}  "
                f"TP R²: {result.get('r2_tp', 0):.3f}"
            )
        else:
            self._p2_status_msg.setText(
                f"Training failed: {result.get('message', 'unknown error')}"
            )
            self._train_btn.setEnabled(True)
            self._refresh_p2_status()

    # ── Inputs panel (left) ────────────────────────────────────────────────────
    def _build_inputs_panel(self) -> QWidget:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        t = QLabel("Operating Parameters")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        # ── Sliders ────────────────────────────────────────────────────────────
        self._sliders: dict[str, QSlider] = {}
        self._slider_labels: dict[str, QLabel] = {}

        slider_defs = [
            # (key, label, unit, min×10, max×10, default×10, decimals, scale)
            ("flow_rate", "Influent flow",      "mL/h",  1000, 5000, 3200, 0, 0.1),
            ("do",        "DO (aeration tank)", "mg/L",     0,   50,   15, 1, 0.1),
            ("srt",       "Sludge age",         "days",     5,   60,   30, 0, 1.0),
            ("ras",       "RAS ratio",          "",         1,   40,   10, 1, 0.1),
            ("temp",      "Temperature",        "°C",     150,  350,  220, 1, 0.1),
            ("ph",        "pH",                 "",        60,   90,   75, 1, 0.1),
            ("mlss",      "MLSS",               "mg/L",  1000,100000,35000,0, 1.0),
        ]

        for key, label, unit, mn, mx, default, dec, scale in slider_defs:
            row_w = self._build_slider_row(key, label, unit, mn, mx, default, dec, scale)
            layout.addWidget(row_w)

        layout.addWidget(self._make_divider())

        # ── Influent concentrations ────────────────────────────────────────────
        inf_title = QLabel("Influent Concentrations")
        f2 = QFont(); f2.setPointSize(10); f2.setBold(True)
        inf_title.setFont(f2); inf_title.setStyleSheet("color:#2c3e50;")
        layout.addWidget(inf_title)

        conc_grid = QGridLayout()
        conc_grid.setSpacing(8)
        self._inf_spins: dict[str, QDoubleSpinBox] = {}

        conc_defs = [
            ("inf_cod",  "COD",  "mg/L",  0, 2000, 300, 1),
            ("inf_nh4",  "NH₄-N","mg/L",  0,  200,  40, 2),
            ("inf_tp",   "TP",   "mg/L",  0,   50,   6, 2),
            ("inf_pfas", "PFAS", "µg/L",  0, 1000,  50, 3),
        ]
        for col, (key, label, unit, mn, mx, default, dec) in enumerate(conc_defs):
            lbl = QLabel(f"{label}\n({unit})")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#636e72; font-size:10px; font-weight:600;")
            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(default)
            spin.setFixedHeight(30)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setStyleSheet(self._spin_style())
            spin.valueChanged.connect(lambda _: self._debounce.start())
            self._inf_spins[key] = spin
            conc_grid.addWidget(lbl,  0, col)
            conc_grid.addWidget(spin, 1, col)
        layout.addLayout(conc_grid)

        # ── PFAS type ──────────────────────────────────────────────────────────
        # ── PFAS compound + chain type ─────────────────────────────────────────
        pfas_row = QHBoxLayout()
        pfas_lbl = QLabel("PFAS compound:")
        pfas_lbl.setStyleSheet("color:#2c3e50; font-size:11px; font-weight:600;")
        pfas_lbl.setFixedWidth(105)

        self._pfas_compound = QComboBox()
        for label, _ in PFAS_COMPOUND_LIST:
            self._pfas_compound.addItem(label)
        self._pfas_compound.setFixedHeight(30)
        self._pfas_compound.setStyleSheet("""
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:4px 8px; font-size:11px; background:#fff; }
        """)
        self._pfas_compound.currentIndexChanged.connect(self._on_pfas_compound_changed)
        pfas_row.addWidget(pfas_lbl)
        pfas_row.addWidget(self._pfas_compound, stretch=1)
        layout.addLayout(pfas_row)

        chain_row = QHBoxLayout()
        chain_lbl = QLabel("Chain type:")
        chain_lbl.setStyleSheet("color:#636e72; font-size:10px;")
        chain_lbl.setFixedWidth(105)
        self._pfas_type = QComboBox()
        self._pfas_type.addItems(["short-chain", "long-chain"])
        self._pfas_type.setFixedHeight(26)
        self._pfas_type.setStyleSheet("""
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 8px; font-size:10px; background:#f8f9fa; color:#636e72; }
        """)
        self._pfas_type.currentIndexChanged.connect(lambda _: self._debounce.start())
        chain_row.addWidget(chain_lbl)
        chain_row.addWidget(self._pfas_type, stretch=1)
        layout.addLayout(chain_row)

        layout.addWidget(self._make_divider())

        # ── Target Finder (collapsible) ────────────────────────────────────────
        self._target_toggle = QPushButton("▶  Target Finder — find conditions for a removal goal")
        self._target_toggle.setCheckable(True)
        self._target_toggle.setChecked(False)
        self._target_toggle.setCursor(Qt.PointingHandCursor)
        self._target_toggle.setFixedHeight(26)
        self._target_toggle.setStyleSheet("""
            QPushButton { background:#dfe6e9; color:#2c3e50; border:none;
                text-align:left; padding:0 10px; font-size:10px; font-weight:600; }
            QPushButton:checked { background:#d5eaf9; }
            QPushButton:hover   { background:#d5eaf9; }
        """)
        self._target_toggle.toggled.connect(self._on_target_toggle)
        layout.addWidget(self._target_toggle)

        self._target_panel = QWidget()
        self._target_panel.setVisible(False)
        self._target_panel.setStyleSheet("background:#f8f9fa; border:1px solid #dde1e7; border-radius:4px;")
        tp = QGridLayout(self._target_panel)
        tp.setContentsMargins(10, 8, 10, 8)
        tp.setSpacing(6)

        tp.addWidget(self._small_lbl("Target parameter:"), 0, 0)
        self._target_param = QComboBox()
        self._target_param.addItems(["PFAS removal %", "COD removal %", "NH₄ removal %", "TP removal %"])
        self._target_param.setFixedHeight(26)
        self._target_param.setStyleSheet(self._spin_style())
        tp.addWidget(self._target_param, 0, 1)

        tp.addWidget(self._small_lbl("Target value (%):"), 1, 0)
        self._target_pct = QDoubleSpinBox()
        self._target_pct.setRange(1.0, 99.0)
        self._target_pct.setValue(60.0)
        self._target_pct.setDecimals(1)
        self._target_pct.setFixedHeight(26)
        self._target_pct.setStyleSheet(self._spin_style())
        tp.addWidget(self._target_pct, 1, 1)

        tp.addWidget(self._small_lbl("Solve for:"), 2, 0)
        self._solve_for = QComboBox()
        self._solve_for.addItems(["SRT (days)", "MLSS (mg/L)", "DO (mg/L)", "Flow (mL/h)"])
        self._solve_for.setFixedHeight(26)
        self._solve_for.setStyleSheet(self._spin_style())
        tp.addWidget(self._solve_for, 2, 1)

        find_btn = QPushButton("Find Conditions")
        find_btn.setFixedHeight(28)
        find_btn.setCursor(Qt.PointingHandCursor)
        find_btn.setStyleSheet("""
            QPushButton { background:#2980b9; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 10px; }
            QPushButton:hover { background:#3498db; }
        """)
        find_btn.clicked.connect(self._find_target)
        tp.addWidget(find_btn, 3, 0)

        self._target_result = QLabel("—")
        self._target_result.setStyleSheet(
            "color:#2c3e50; font-size:11px; font-weight:600; padding:2px 6px;"
        )
        tp.addWidget(self._target_result, 3, 1)
        layout.addWidget(self._target_panel)

        layout.addStretch()
        return card

    def _build_slider_row(
        self, key, label, unit, mn, mx, default, dec, scale
    ) -> QWidget:
        """One labelled slider row with current-value display."""
        row_w = QWidget()
        row_w.setStyleSheet("background:transparent;")
        layout = QHBoxLayout(row_w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        name_lbl = QLabel(label)
        name_lbl.setFixedWidth(110)
        name_lbl.setStyleSheet("color:#2c3e50; font-size:11px;")

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(mn)
        slider.setMaximum(mx)
        slider.setValue(default)
        slider.setFixedHeight(22)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height:4px; background:#dde1e7; border-radius:2px;
            }
            QSlider::handle:horizontal {
                width:14px; height:14px; margin:-5px 0;
                background:#2980b9; border-radius:7px;
            }
            QSlider::sub-page:horizontal { background:#2980b9; border-radius:2px; }
        """)
        slider.valueChanged.connect(
            lambda v, k=key, s=scale, d=dec, u=unit: self._on_slider(k, v, s, d, u)
        )
        self._sliders[key] = slider

        actual = default * scale
        val_text = f"{actual:.{dec}f} {unit}".strip()
        val_lbl = QLabel(val_text)
        val_lbl.setFixedWidth(90)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet("color:#2980b9; font-size:11px; font-weight:600;")
        self._slider_labels[key] = val_lbl

        layout.addWidget(name_lbl)
        layout.addWidget(slider, stretch=1)
        layout.addWidget(val_lbl)
        return row_w

    def _on_slider(self, key, raw_val, scale, dec, unit) -> None:
        """Update the value label and trigger a debounced recalculation."""
        actual = raw_val * scale
        lbl = self._slider_labels[key]
        lbl.setText(f"{actual:.{dec}f} {unit}".strip())

        # Colour label red if outside recommended range
        rng = PARAM_RANGES.get(key)
        if rng and not (rng[0] <= actual <= rng[1]):
            lbl.setStyleSheet("color:#e74c3c; font-size:11px; font-weight:600;")
        else:
            lbl.setStyleSheet("color:#2980b9; font-size:11px; font-weight:600;")

        self._debounce.start()

    # ── Results panel (right) ──────────────────────────────────────────────────
    def _build_results_panel(self) -> QWidget:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        t = QLabel("Predicted Results")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        # ── Removal % gauges (4 big number displays) ───────────────────────────
        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(8)
        self._gauges: dict[str, QLabel] = {}
        for key, label, color in [
            ("cod",  "COD",  "#2471a3"),
            ("nh4",  "NH₄",  "#8e44ad"),
            ("tp",   "TP",   "#1e8449"),
            ("pfas", "PFAS", "#e74c3c"),
        ]:
            box = self._build_gauge(key, label, color)
            gauges_row.addWidget(box)
        layout.addLayout(gauges_row)

        # ── Effluent concentrations table ──────────────────────────────────────
        eff_title = QLabel("Predicted Effluent Concentrations")
        eff_title.setStyleSheet("color:#636e72; font-size:10px; font-weight:600;")
        layout.addWidget(eff_title)

        self._eff_table = QTableWidget(4, 4)
        self._eff_table.setHorizontalHeaderLabels(
            ["Parameter", "Influent", "Predicted Effluent", "Removal %"])
        self._eff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._eff_table.verticalHeader().setVisible(False)
        self._eff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._eff_table.setFixedHeight(156)
        self._eff_table.setShowGrid(False)
        self._eff_table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:11px; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:5px 8px; }
        """)
        layout.addWidget(self._eff_table)

        # ── Bar chart ──────────────────────────────────────────────────────────
        chart_title = QLabel("Removal Efficiency Comparison")
        chart_title.setStyleSheet("color:#636e72; font-size:10px; font-weight:600;")
        layout.addWidget(chart_title)
        layout.addWidget(self._build_bar_chart(), stretch=1)

        # ── Warning flags ──────────────────────────────────────────────────────
        self._warnings_label = QLabel("")
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setStyleSheet("""
            background:#fef9e7; border:1px solid #f9ca24;
            border-radius:6px; padding:8px 12px; font-size:11px; color:#7d6608;
        """)
        self._warnings_label.setVisible(False)
        layout.addWidget(self._warnings_label)

        # HRT info
        self._hrt_label = QLabel("")
        self._hrt_label.setStyleSheet("color:#7f8c8d; font-size:10px; padding:2px 0;")
        layout.addWidget(self._hrt_label)

        layout.addWidget(self._make_divider())

        # ── Saved Scenarios (collapsible) ─────────────────────────────────────
        self._scenarios_toggle = QPushButton("▶  Saved Scenarios")
        self._scenarios_toggle.setCheckable(True)
        self._scenarios_toggle.setChecked(False)
        self._scenarios_toggle.setCursor(Qt.PointingHandCursor)
        self._scenarios_toggle.setFixedHeight(26)
        self._scenarios_toggle.setStyleSheet("""
            QPushButton { background:#dfe6e9; color:#2c3e50; border:none;
                text-align:left; padding:0 10px; font-size:10px; font-weight:600; }
            QPushButton:checked { background:#d5eaf9; }
            QPushButton:hover   { background:#d5eaf9; }
        """)
        self._scenarios_toggle.toggled.connect(self._on_scenarios_toggle)
        layout.addWidget(self._scenarios_toggle)

        self._scenarios_panel = QWidget()
        self._scenarios_panel.setVisible(False)
        sp_layout = QVBoxLayout(self._scenarios_panel)
        sp_layout.setContentsMargins(0, 4, 0, 0)
        sp_layout.setSpacing(0)

        self._scenarios_table = QTableWidget(0, 7)
        self._scenarios_table.setHorizontalHeaderLabels(
            ["Date", "SRT\nd", "DO\nmg/L", "MLSS\nmg/L", "PFAS\n%", "COD\n%", "NH₄\n%"]
        )
        self._scenarios_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, 7):
            self._scenarios_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self._scenarios_table.verticalHeader().setVisible(False)
        self._scenarios_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._scenarios_table.setFixedHeight(180)
        self._scenarios_table.setShowGrid(False)
        self._scenarios_table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:4px; font-size:10px; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:9px; padding:4px 2px; border:none; }
            QTableWidget::item { padding:3px 4px; }
        """)
        sp_layout.addWidget(self._scenarios_table)
        layout.addWidget(self._scenarios_panel)

        return card

    def _build_gauge(self, key: str, label: str, color: str) -> QWidget:
        """A coloured box showing a big removal % number."""
        box = QWidget()
        box.setStyleSheet(f"""
            QWidget {{ background:{QColor(color).lighter(190).name()};
                border:2px solid {color}; border-radius:8px; }}
        """)
        box.setFixedHeight(90)
        vl = QVBoxLayout(box)
        vl.setContentsMargins(8, 6, 8, 6)
        vl.setSpacing(2)

        pct_lbl = QLabel("—")
        f = QFont(); f.setPointSize(22); f.setBold(True)
        pct_lbl.setFont(f)
        pct_lbl.setAlignment(Qt.AlignCenter)
        pct_lbl.setStyleSheet(f"color:{color}; border:none; background:transparent;")

        name_lbl = QLabel(label + " removal")
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(f"color:{color}; font-size:10px; border:none; background:transparent;")

        vl.addWidget(pct_lbl)
        vl.addWidget(name_lbl)
        self._gauges[key] = pct_lbl
        return box

    def _build_bar_chart(self) -> QChartView:
        self._bar_set = QBarSet("Removal %")
        self._bar_set.setColor(QColor("#2980b9"))
        self._bar_set.append([0, 0, 0, 0])

        series = QBarSeries()
        series.append(self._bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundBrush(QBrush(QColor("#ffffff")))
        chart.setBackgroundRoundness(0)
        chart.setMargins(__import__('PySide6.QtCore', fromlist=['QMargins']).QMargins(4, 4, 4, 4))
        chart.legend().hide()

        x_axis = QBarCategoryAxis()
        x_axis.append(["COD", "NH₄", "TP", "PFAS"])
        chart.addAxis(x_axis, Qt.AlignBottom)
        series.attachAxis(x_axis)

        y_axis = QValueAxis()
        y_axis.setRange(0, 100)
        y_axis.setTitleText("Removal %")
        y_axis.setTickCount(6)
        chart.addAxis(y_axis, Qt.AlignLeft)
        series.attachAxis(y_axis)

        self._bar_chart = chart
        self._bar_series = series

        view = QChartView(chart)
        from PySide6.QtGui import QPainter
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(180)
        view.setStyleSheet("border:1px solid #dde1e7; border-radius:6px;")
        return view

    # ── Calculation ────────────────────────────────────────────────────────────
    def _get_inputs(self) -> SimInputs:
        """Read all current slider and spinbox values into a SimInputs object."""
        s = self._sliders
        compound_key = PFAS_COMPOUND_LIST[self._pfas_compound.currentIndex()][1]
        return SimInputs(
            flow_rate_mlh = s["flow_rate"].value() * 0.1,
            do_mgl        = s["do"].value()         * 0.1,
            srt_days      = s["srt"].value()        * 1.0,
            ras_ratio     = s["ras"].value()        * 0.1,
            temp_c        = s["temp"].value()       * 0.1,
            ph            = s["ph"].value()         * 0.1,
            mlss_mgl      = s["mlss"].value()       * 1.0,
            inf_cod       = self._inf_spins["inf_cod"].value(),
            inf_nh4       = self._inf_spins["inf_nh4"].value(),
            inf_tp        = self._inf_spins["inf_tp"].value(),
            inf_pfas      = self._inf_spins["inf_pfas"].value(),
            pfas_type     = self._pfas_type.currentText(),
            pfas_compound = compound_key,
        )

    def _recalculate(self) -> None:
        """Run the active model and refresh all result widgets."""
        inputs = self._get_inputs()
        if (self._model_selector.currentIndex() == 1
                and get_model_status()["main_trained"]):
            outputs = run_phase2(inputs)
        else:
            outputs = run_phase1(inputs)
        self._update_results(inputs, outputs)

    def _update_results(self, inp: SimInputs, out: SimOutputs) -> None:
        """Push new outputs into every result widget."""
        # Gauges
        for key, pct in [("cod",  out.cod_removal_pct),
                          ("nh4",  out.nh4_removal_pct),
                          ("tp",   out.tp_removal_pct),
                          ("pfas", out.pfas_removal_pct)]:
            self._gauges[key].setText(f"{pct:.1f}%")

        # Effluent table
        rows = [
            ("COD",  f"{inp.inf_cod:.1f} mg/L",  f"{out.eff_cod:.2f} mg/L",  out.cod_removal_pct),
            ("NH₄",  f"{inp.inf_nh4:.2f} mg/L",  f"{out.eff_nh4:.2f} mg/L",  out.nh4_removal_pct),
            ("TP",   f"{inp.inf_tp:.2f} mg/L",   f"{out.eff_tp:.2f} mg/L",   out.tp_removal_pct),
            ("PFAS", f"{inp.inf_pfas:.3f} µg/L", f"{out.eff_pfas:.3f} µg/L", out.pfas_removal_pct),
        ]
        for row_i, (param, inf_txt, eff_txt, pct) in enumerate(rows):
            color = ("#1e8449" if pct >= 60 else "#d68910" if pct >= 30 else "#c0392b")
            for col_i, text in enumerate([param, inf_txt, eff_txt, f"{pct:.1f}%"]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled)
                if col_i == 3:
                    item.setForeground(QBrush(QColor(color)))
                    f = QFont(); f.setBold(True); item.setFont(f)
                self._eff_table.setItem(row_i, col_i, item)
            self._eff_table.setRowHeight(row_i, 34)

        # Bar chart
        self._bar_set.replace(0, out.cod_removal_pct)
        self._bar_set.replace(1, out.nh4_removal_pct)
        self._bar_set.replace(2, out.tp_removal_pct)
        self._bar_set.replace(3, out.pfas_removal_pct)

        # HRT info
        compound_tag = f" ({inp.pfas_compound})" if inp.pfas_compound else " (class avg)"
        self._hrt_label.setText(
            f"HRT: {out.hrt_days:.2f} days  |  "
            f"Kd: {out.kd_used} L/kg{compound_tag}  |  "
            f"{inp.pfas_type}"
        )

        # Warnings
        if out.warnings:
            icon = "⚠  "
            self._warnings_label.setText(icon + ("\n" + icon).join(out.warnings))
            self._warnings_label.setVisible(True)
        else:
            self._warnings_label.setVisible(False)

    # ── PFAS compound selector ─────────────────────────────────────────────────
    def _on_pfas_compound_changed(self, index: int) -> None:
        """Auto-set chain type when a specific compound is selected."""
        key = PFAS_COMPOUND_LIST[index][1]
        if key in PFAS_COMPOUND_CHAIN_TYPE:
            chain = PFAS_COMPOUND_CHAIN_TYPE[key]
            self._pfas_type.setCurrentText(chain)
        self._debounce.start()

    # ── Load today's data ──────────────────────────────────────────────────────
    def _set_slider_val(self, key: str, actual: float, scale: float) -> None:
        """Set a slider from a real-world value (reverse the scale factor)."""
        slider = self._sliders.get(key)
        if slider is None:
            return
        int_val = int(round(actual / scale))
        int_val = max(slider.minimum(), min(slider.maximum(), int_val))
        slider.setValue(int_val)

    def _load_today_data(self) -> None:
        """Pre-fill all inputs from today's logged readings for the active experiment."""
        try:
            with get_session() as session:
                active = session.query(Experiment).filter_by(is_active=True).first()
                if not active:
                    QMessageBox.information(
                        self, "No Active Experiment",
                        "No active experiment found.\nCreate one in the Experiments screen first."
                    )
                    return

                today = dt_date.today()
                flow = (session.query(FlowReading)
                        .filter_by(experiment_id=active.id, reading_date=today).first())
                aer = (session.query(DailyReading)
                       .filter_by(experiment_id=active.id, reading_date=today, zone="aeration").first())
                pst = (session.query(DailyReading)
                       .filter_by(experiment_id=active.id, reading_date=today, zone="primary_settling").first())

            filled = []

            if flow:
                if flow.q_in_mlh:
                    self._set_slider_val("flow_rate", flow.q_in_mlh, 0.1)
                    filled.append("flow rate")
                if flow.ras_ratio:
                    self._set_slider_val("ras", flow.ras_ratio, 0.1)
                    filled.append("RAS ratio")
                if aer and aer.mlss_mgl and flow.q_was_mlh:
                    srt = calc_actual_srt(aer.mlss_mgl, flow.q_was_mlh)
                    if srt > 0:
                        self._set_slider_val("srt", srt, 1.0)
                        filled.append("SRT")

            if aer:
                if aer.do_mgl is not None:
                    self._set_slider_val("do", aer.do_mgl, 0.1)
                    filled.append("DO")
                if aer.temperature_c is not None:
                    self._set_slider_val("temp", aer.temperature_c, 0.1)
                    filled.append("temperature")
                if aer.ph is not None:
                    self._set_slider_val("ph", aer.ph, 0.1)
                    filled.append("pH")
                if aer.mlss_mgl is not None:
                    self._set_slider_val("mlss", aer.mlss_mgl, 1.0)
                    filled.append("MLSS")

            if pst:
                if pst.cod_mgl is not None:
                    self._inf_spins["inf_cod"].setValue(pst.cod_mgl)
                    filled.append("influent COD")
                if pst.nh4_mgl is not None:
                    self._inf_spins["inf_nh4"].setValue(pst.nh4_mgl)
                    filled.append("influent NH₄")
                if pst.tp_mgl is not None:
                    self._inf_spins["inf_tp"].setValue(pst.tp_mgl)
                    filled.append("influent TP")

            if not filled:
                QMessageBox.information(
                    self, "No Data for Today",
                    "No readings found for today in the active experiment.\n"
                    "Log today's data in the Daily Log screen first."
                )
            else:
                self._debounce.start()

        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    # ── Target Finder ──────────────────────────────────────────────────────────
    def _on_target_toggle(self, checked: bool) -> None:
        self._target_panel.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self._target_toggle.setText(f"{arrow}  Target Finder — find conditions for a removal goal")

    def _find_target(self) -> None:
        """Use bisection to find the operating condition that meets a removal target."""
        param_map = {
            "PFAS removal %": "pfas_removal_pct",
            "COD removal %":  "cod_removal_pct",
            "NH₄ removal %":  "nh4_removal_pct",
            "TP removal %":   "tp_removal_pct",
        }
        solve_map = {
            "SRT (days)":  ("srt_days",      5.0,    60.0,   1.0,   "d"),
            "MLSS (mg/L)": ("mlss_mgl",      500.0,  10000.0, 1.0,  "mg/L"),
            "DO (mg/L)":   ("do_mgl",        0.1,    5.0,    0.1,   "mg/L"),
            "Flow (mL/h)": ("flow_rate_mlh", 100.0,  500.0,  0.1,   "mL/h"),
        }

        attr   = param_map[self._target_param.currentText()]
        goal   = self._target_pct.value()
        field, lo, hi, scale, unit = solve_map[self._solve_for.currentText()]
        slider_key = {"srt_days": "srt", "mlss_mgl": "mlss",
                      "do_mgl": "do", "flow_rate_mlh": "flow_rate"}.get(field)

        import dataclasses
        base = self._get_inputs()

        def _residual(x: float) -> float:
            inp = dataclasses.replace(base, **{field: x})
            out = run_phase1(inp)
            return getattr(out, attr) - goal

        # Check feasibility at the bounds
        r_lo = _residual(lo)
        r_hi = _residual(hi)
        if r_lo * r_hi > 0:
            if abs(r_hi) < abs(r_lo):
                self._target_result.setText(
                    f"Max achievable: {getattr(run_phase1(dataclasses.replace(base, **{field: hi})), attr):.1f}%"
                )
            else:
                self._target_result.setText("Not achievable in valid range")
            return

        # Bisection (50 iterations ≈ 32 billion-fold precision)
        for _ in range(50):
            mid = (lo + hi) / 2.0
            if (hi - lo) < (scale * 0.1):
                break
            if _residual(lo) * _residual(mid) <= 0:
                hi = mid
            else:
                lo = mid
        solution = (lo + hi) / 2.0

        self._target_result.setText(f"➜  {field.replace('_', ' ').title()}: {solution:.1f} {unit}")

        # Apply the solution to the slider so the user can see it live
        if slider_key:
            self._set_slider_val(slider_key, solution, scale)
            self._debounce.start()

    # ── Saved Scenarios ────────────────────────────────────────────────────────
    def _on_scenarios_toggle(self, checked: bool) -> None:
        self._scenarios_panel.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self._scenarios_toggle.setText(f"{arrow}  Saved Scenarios")
        if checked:
            self._refresh_scenarios()

    def _refresh_scenarios(self) -> None:
        """Load the 10 most recent saved scenarios from the database."""
        try:
            with get_session() as session:
                rows = (session.query(SimulationRun)
                        .order_by(SimulationRun.run_date.desc())
                        .limit(10).all())
            self._scenarios_table.setRowCount(len(rows))
            for r, run in enumerate(rows):
                dt_str = str(run.run_date)[:16] if run.run_date else "—"
                cells = [
                    dt_str,
                    f"{run.srt_days:.0f}" if run.srt_days else "—",
                    f"{run.do_mgl:.1f}"   if run.do_mgl   else "—",
                    f"{run.flow_rate_mlh:.0f}" if run.flow_rate_mlh else "—",
                    f"{run.pred_pfas_removal:.1f}" if run.pred_pfas_removal else "—",
                    f"{run.pred_cod_removal:.1f}"  if run.pred_cod_removal  else "—",
                    f"{run.pred_nh4_removal:.1f}"  if run.pred_nh4_removal  else "—",
                ]
                for c, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setFlags(Qt.ItemIsEnabled)
                    self._scenarios_table.setItem(r, c, item)
                self._scenarios_table.setRowHeight(r, 28)
        except Exception:
            pass

    # ── Save scenario ──────────────────────────────────────────────────────────
    def _save_scenario(self) -> None:
        """Save the current inputs and outputs to the simulation_runs table."""
        inp = self._get_inputs()
        is_p2 = (self._model_selector.currentIndex() == 1
                 and get_model_status()["main_trained"])
        out = run_phase2(inp) if is_p2 else run_phase1(inp)
        model_type_str = "data_driven" if is_p2 else "generic"
        try:
            with get_session() as session:
                run = SimulationRun(
                    run_date          = datetime.utcnow(),
                    model_type        = model_type_str,
                    flow_rate_mlh     = inp.flow_rate_mlh,
                    ras_ratio         = inp.ras_ratio,
                    do_mgl            = inp.do_mgl,
                    srt_days          = inp.srt_days,
                    temp_c            = inp.temp_c,
                    ph                = inp.ph,
                    inf_cod           = inp.inf_cod,
                    inf_nh4           = inp.inf_nh4,
                    inf_tp            = inp.inf_tp,
                    inf_pfas          = inp.inf_pfas,
                    pfas_type         = inp.pfas_type,
                    pred_cod_removal  = out.cod_removal_pct,
                    pred_nh4_removal  = out.nh4_removal_pct,
                    pred_tp_removal   = out.tp_removal_pct,
                    pred_pfas_removal = out.pfas_removal_pct,
                    pred_eff_cod      = out.eff_cod,
                    pred_eff_nh4      = out.eff_nh4,
                    pred_eff_tp       = out.eff_tp,
                    pred_eff_pfas     = out.eff_pfas,
                )
                session.add(run)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        QMessageBox.information(self, "Saved",
            "Scenario saved to the database.\n"
            "You can compare it with real data in the Comparison screen.")
        if self._scenarios_toggle.isChecked():
            self._refresh_scenarios()

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._model_selector.currentIndex() == 1:
            self._refresh_p2_status()

    # ── Style helpers ──────────────────────────────────────────────────────────
    def _panel_card(self, title: str, widget: QWidget) -> QWidget:
        """Wrap a widget in a titled panel with a dark header bar."""
        outer = QWidget()
        outer.setStyleSheet("background:#ffffff; border:1px solid #dde1e7;")
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet("background:#2c3e50; border:none;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            "color:#ecf0f1; font-size:10px; font-weight:600;"
            " border:none; background:transparent;"
        )
        hl.addWidget(lbl)
        vl.addWidget(hdr)
        vl.addWidget(widget, stretch=1)
        return outer

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
    def _small_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#2c3e50; font-size:10px; font-weight:600; background:transparent;")
        return lbl

    @staticmethod
    def _spin_style() -> str:
        return """
            QDoubleSpinBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:11px; background:#fff; color:#2c3e50; }
            QDoubleSpinBox:focus { border-color:#2980b9; }
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:10px; background:#fff; color:#2c3e50; }
        """

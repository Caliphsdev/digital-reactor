"""
simulation_screen.py — Phase 1 What-If Simulation screen (Step 8).

Layout:
    ┌─── Header: title · Run Simulation button ───────────────────────┐
    ├─── Left panel: Sliders + inputs ─────┬─── Right panel: Results ─┤
    │  Operating parameters (sliders)      │  Removal % gauges        │
    │    Flow rate, DO, SRT, RAS,          │  Effluent concentration  │
    │    a-recycle, Temp, pH               │  table                   │
    │  Influent concentrations             │  Warning flags           │
    │    COD, NH4, TP, PFAS                │  Bar chart               │
    │  PFAS type selector                  │                          │
    └──────────────────────────────────────┴──────────────────────────┘

All sliders are connected live — results update instantly without
needing to click Run (Run also saves the scenario to the database).
"""

from datetime import datetime

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QSlider, QDoubleSpinBox, QComboBox, QPushButton,
    QFrame, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
)
from ui.docking_utils import make_inner_window, make_dock, make_dock_toolbar
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
)

from simulation.generic_model import SimInputs, SimOutputs, run_phase1
from core.database import get_session
from core.models import SimulationRun

C_HDR = "#2c3e50"

# Recommended operating ranges for slider warning colours
PARAM_RANGES = {
    "flow_rate": (200, 450),
    "do":        (1.0, 2.0),
    "srt":       (20, 40),
    "ras":       (0.5, 2.0),
    "a_recycle": (2.0, 6.0),
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

        # Guard so resizeDocks() only runs once after the window is visible
        self._docks_sized = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # Inner QMainWindow manages the two dockable panels.
        # Qt.WindowType.Widget keeps it embedded — not a standalone OS window.
        self._inner_mw = make_inner_window()

        # Minimal central placeholder — docks fill the visible area
        central = QWidget()
        central.setStyleSheet("background:#f5f6fa;")
        self._inner_mw.setCentralWidget(central)

        # Build docks from the existing panel builder methods
        self._dock_inputs  = make_dock("Operating Parameters", self._build_inputs_panel())
        self._dock_results = make_dock("Predicted Results",    self._build_results_panel())

        self._inner_mw.addDockWidget(Qt.LeftDockWidgetArea,  self._dock_inputs)
        self._inner_mw.addDockWidget(Qt.RightDockWidgetArea, self._dock_results)

        # Compact toolbar with one toggle button per dock (hide / restore)
        make_dock_toolbar(self._inner_mw, [self._dock_inputs, self._dock_results])

        root.addWidget(self._inner_mw, stretch=1)

        # Run initial calculation with default values
        QTimer.singleShot(0, self._recalculate)

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background:{C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        t = QLabel("Simulation  —  Phase 1 Generic Model")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#ecf0f1;")
        row.addWidget(t)

        note = QLabel("Textbook estimates only — Phase 2 uses your real data")
        note.setStyleSheet("color:#7f8c8d; font-size:10px;")
        row.addWidget(note)
        row.addStretch()

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

        return bar

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
            ("flow_rate", "Influent flow",   "mL/h",  1000, 5000, 3200, 0, 0.1),
            ("do",        "DO (aerobic)",    "mg/L",     0,   50,   15, 1, 0.1),
            ("srt",       "Sludge age",      "days",     5,   60,   30, 0, 1.0),
            ("ras",       "RAS ratio",       "",         1,   40,   10, 1, 0.1),
            ("a_recycle", "a-recycle ratio", "",         5,   80,   40, 1, 0.1),
            ("temp",      "Temperature",     "°C",     150,  350,  220, 1, 0.1),
            ("ph",        "pH",              "",        60,   90,   75, 1, 0.1),
            ("mlss",      "MLSS",            "mg/L",  1000,100000,35000,0, 1.0),
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
        pfas_row = QHBoxLayout()
        pfas_lbl = QLabel("PFAS chain type:")
        pfas_lbl.setStyleSheet("color:#2c3e50; font-size:11px; font-weight:600;")
        self._pfas_type = QComboBox()
        self._pfas_type.addItems(["short-chain", "long-chain"])
        self._pfas_type.setFixedHeight(30)
        self._pfas_type.setStyleSheet("""
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:4px 8px; font-size:11px; background:#fff; }
        """)
        self._pfas_type.currentIndexChanged.connect(lambda _: self._debounce.start())
        pfas_row.addWidget(pfas_lbl)
        pfas_row.addWidget(self._pfas_type, stretch=1)
        layout.addLayout(pfas_row)

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
        return SimInputs(
            flow_rate_mlh = s["flow_rate"].value() * 0.1,
            do_mgl        = s["do"].value()         * 0.1,
            srt_days      = s["srt"].value()        * 1.0,
            ras_ratio     = s["ras"].value()        * 0.1,
            a_recycle     = s["a_recycle"].value()  * 0.1,
            temp_c        = s["temp"].value()       * 0.1,
            ph            = s["ph"].value()         * 0.1,
            mlss_mgl      = s["mlss"].value()       * 1.0,
            inf_cod       = self._inf_spins["inf_cod"].value(),
            inf_nh4       = self._inf_spins["inf_nh4"].value(),
            inf_tp        = self._inf_spins["inf_tp"].value(),
            inf_pfas      = self._inf_spins["inf_pfas"].value(),
            pfas_type     = self._pfas_type.currentText(),
        )

    def _recalculate(self) -> None:
        """Run the Phase 1 model and refresh all result widgets."""
        inputs  = self._get_inputs()
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
        self._hrt_label.setText(
            f"HRT: {out.hrt_days:.2f} days  |  "
            f"Kd used: {out.kd_used} L/kg  |  "
            f"PFAS type: {inp.pfas_type}"
        )

        # Warnings
        if out.warnings:
            icon = "⚠  "
            self._warnings_label.setText(icon + ("\n" + icon).join(out.warnings))
            self._warnings_label.setVisible(True)
        else:
            self._warnings_label.setVisible(False)

    # ── Save scenario ──────────────────────────────────────────────────────────
    def _save_scenario(self) -> None:
        """Save the current inputs and outputs to the simulation_runs table."""
        inp = self._get_inputs()
        out = run_phase1(inp)
        try:
            with get_session() as session:
                run = SimulationRun(
                    run_date          = datetime.utcnow(),
                    model_type        = "generic",
                    flow_rate_mlh     = inp.flow_rate_mlh,
                    ras_ratio         = inp.ras_ratio,
                    a_recycle         = inp.a_recycle,
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

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Set initial dock widths once the window has been laid out.
        # Calling resizeDocks() before the widget is visible has no effect.
        if not self._docks_sized:
            self._inner_mw.resizeDocks(
                [self._dock_inputs, self._dock_results], [460, 580], Qt.Horizontal,
            )
            self._docks_sized = True

    # ── Style helpers ──────────────────────────────────────────────────────────
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
    def _spin_style() -> str:
        return """
            QDoubleSpinBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:11px; background:#fff; color:#2c3e50; }
            QDoubleSpinBox:focus { border-color:#2980b9; }
        """

"""
dashboard.py — Step 9: Comparison Dashboard screen.

Four chart tabs for analysing and comparing reactor performance:
  Tab 1  Lab vs Daspoort  — lab removal % vs full-scale WWTP removal % over time
  Tab 2  Model vs Actual  — Phase 1 simulation predictions vs measured values
  Tab 3  CEC Trends       — CEC concentration at each sampling point over time
  Tab 4  Parameter Trends — daily DO / pH / COD / NH4 etc. per zone over time

Export button saves all four charts as PNG images to a chosen folder.
"""

import os
from datetime import date, datetime
from collections import defaultdict

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox, QFileDialog, QMessageBox, QSizePolicy,
    QFrame,
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries,
    QValueAxis, QDateTimeAxis,
)
from PySide6.QtCore import Qt, QDateTime, QDate, QTime, QMargins, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QFont

from core.database import get_session
from core.models import (
    MassBalanceResult, DailyReading, CECReading,
    SimulationRun, DaspoortMonitoring,
)


# ── Colour palette — matches the rest of the app ─────────────────────────────
C_HDR      = "#2c3e50"    # dark navy — used for header bar
C_BG       = "#f5f6fa"    # light grey page background
C_CARD     = "#ffffff"    # white card / chart background
C_BORDER   = "#dde1e7"    # subtle border
C_TEXT     = "#2c3e50"    # primary text
C_MUTED    = "#636e72"    # secondary / label text
C_HINT     = "#7f8c8d"    # hint / axis text

# Series colours — distinct enough to tell apart on a white background
SERIES_COLORS = [
    "#2471a3",   # blue
    "#1e8449",   # green
    "#d68910",   # amber
    "#c0392b",   # red
    "#8e44ad",   # purple
    "#138d75",   # teal
    "#ba4a00",   # orange
    "#1a5276",   # navy
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _date_to_ms(d) -> float:
    """Convert a Python date or datetime to milliseconds since epoch for QDateTimeAxis."""
    if isinstance(d, datetime):
        return QDateTime(
            QDate(d.year, d.month, d.day),
            QTime(d.hour, d.minute, d.second),
        ).toMSecsSinceEpoch()
    return QDateTime(QDate(d.year, d.month, d.day), QTime(0, 0, 0)).toMSecsSinceEpoch()


def _make_chart(title: str) -> QChart:
    """Create a light-themed QChart matching the app's visual style."""
    chart = QChart()
    chart.setTitle(title)
    chart.setTitleBrush(QColor(C_TEXT))
    chart.setBackgroundBrush(QBrush(QColor(C_CARD)))
    chart.legend().setLabelColor(QColor(C_TEXT))
    chart.legend().setBrush(QBrush(QColor(C_CARD)))
    chart.setMargins(QMargins(8, 8, 8, 8))
    return chart


def _make_chart_view(chart: QChart) -> QChartView:
    """Wrap a QChart in an antialiased QChartView that fills available space."""
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setBackgroundBrush(QBrush(QColor(C_CARD)))
    view.setStyleSheet(f"border:1px solid {C_BORDER}; border-radius:6px;")
    view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return view


def _style_axis(axis, title: str = ""):
    """Apply consistent light-theme styling to a chart axis."""
    if title:
        axis.setTitleText(title)
    f = QFont()
    f.setPointSize(9)
    axis.setTitleBrush(QColor(C_TEXT))
    axis.setLabelsBrush(QColor(C_HINT))
    axis.setGridLineColor(QColor("#ecf0f1"))
    axis.setLinePen(QColor(C_BORDER))


def _attach_axes(chart: QChart, axis_x, axis_y):
    """Attach both axes to every series already added to the chart."""
    for series in chart.series():
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)


# ── Main screen ───────────────────────────────────────────────────────────────

class DashboardScreen(QWidget):
    """
    Step 9 — Comparison Dashboard.

    Provides four chart tabs for analysing reactor performance and
    comparing it against the Daspoort WWTP benchmark and Phase 1
    model predictions.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setStyleSheet(f"background:{C_BG};")

        # ── Header bar ─────────────────────────────────────────────────────────
        hdr_bar = QWidget()
        hdr_bar.setFixedHeight(52)
        hdr_bar.setStyleSheet(f"background:{C_HDR};")
        hdr_layout = QHBoxLayout(hdr_bar)
        hdr_layout.setContentsMargins(16, 0, 16, 0)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("fa6s.chart-line", color="#ecf0f1").pixmap(QSize(18, 18))
        )
        hdr_layout.addWidget(icon_lbl)

        title = QLabel("  Comparison Dashboard")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#ecf0f1;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        btn_refresh = QPushButton("  Refresh")
        btn_refresh.setIcon(qta.icon("fa6s.rotate-left", color="#ecf0f1"))
        btn_refresh.setFixedHeight(30)
        btn_refresh.setStyleSheet(self._hdr_btn_style())
        btn_refresh.clicked.connect(self.refresh)
        hdr_layout.addWidget(btn_refresh)

        btn_export = QPushButton("  Export Charts as PNG")
        btn_export.setIcon(qta.icon("fa6s.file-image", color="#ecf0f1"))
        btn_export.setFixedHeight(30)
        btn_export.setStyleSheet(self._hdr_btn_style(accent=True))
        btn_export.clicked.connect(self._export_charts)
        hdr_layout.addWidget(btn_export)

        root.addWidget(hdr_bar)

        # ── Content area ───────────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background:{C_BG};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(10)

        # ── Tab widget ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C_BORDER};
                background: {C_CARD};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background: #ecf0f1;
                color: {C_MUTED};
                padding: 8px 18px;
                border: 1px solid {C_BORDER};
                border-bottom: none;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {C_CARD};
                color: {C_TEXT};
                font-weight: 600;
            }}
            QTabBar::tab:hover {{
                background: #dfe6e9;
                color: {C_TEXT};
            }}
        """)
        content_layout.addWidget(self._tabs)
        root.addWidget(content)

        # Build tabs and keep references for PNG export
        self._tab_ld = self._build_tab_lab_daspoort()
        self._tab_mv = self._build_tab_model_vs_actual()
        self._tab_ct = self._build_tab_cec_trends()
        self._tab_pt = self._build_tab_param_trends()

        self._tabs.addTab(self._tab_ld, "  Lab vs Daspoort  ")
        self._tabs.addTab(self._tab_mv, "  Model vs Actual  ")
        self._tabs.addTab(self._tab_ct, "  CEC Trends  ")
        self._tabs.addTab(self._tab_pt, "  Parameter Trends  ")

    # ── Tab 1: Lab vs Daspoort ─────────────────────────────────────────────────

    def _build_tab_lab_daspoort(self) -> QWidget:
        """
        Tab 1: Lab reactor removal % (MassBalanceResult) vs
        Daspoort WWTP removal % (DaspoortMonitoring SP1→SP4),
        filtered by CEC compound name.
        """
        w = QWidget()
        w.setStyleSheet(f"background:{C_CARD};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        lbl = QLabel("CEC:")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl)
        self._ld_cec_combo = QComboBox()
        self._ld_cec_combo.setFixedWidth(190)
        self._ld_cec_combo.setStyleSheet(self._combo_style())
        self._ld_cec_combo.currentIndexChanged.connect(self._refresh_lab_daspoort)
        row.addWidget(self._ld_cec_combo)
        row.addStretch()
        layout.addLayout(row)

        self._ld_view = _make_chart_view(
            _make_chart("Lab Reactor vs Daspoort WWTP — Removal %")
        )
        layout.addWidget(self._ld_view)
        return w

    def _refresh_lab_daspoort(self):
        """Load data and rebuild the Lab vs Daspoort chart."""
        cec = self._ld_cec_combo.currentText()
        chart = _make_chart("Lab Reactor vs Daspoort WWTP — Removal %")

        with get_session() as s:
            # Lab removal % from the mass balance screen
            lab_rows = (
                s.query(MassBalanceResult.calculation_date, MassBalanceResult.removal_pct)
                .filter(MassBalanceResult.cec_name == cec)
                .filter(MassBalanceResult.removal_pct.isnot(None))
                .order_by(MassBalanceResult.calculation_date)
                .all()
            )
            # Daspoort data — one row per sampling point per date
            dasp_rows = (
                s.query(
                    DaspoortMonitoring.sampling_date,
                    DaspoortMonitoring.sampling_point,
                    DaspoortMonitoring.concentration,
                )
                .filter(DaspoortMonitoring.cec_name == cec)
                .filter(DaspoortMonitoring.concentration.isnot(None))
                .order_by(DaspoortMonitoring.sampling_date)
                .all()
            )

        if not lab_rows and not dasp_rows:
            chart.setTitle(
                f"No data yet for '{cec}' — log CEC readings and run a mass balance first."
            )
            self._ld_view.setChart(chart)
            return

        # Lab series
        lab_series = QLineSeries()
        lab_series.setName("Lab Reactor")
        lab_series.setColor(QColor(SERIES_COLORS[0]))
        for row_date, pct in lab_rows:
            lab_series.append(_date_to_ms(row_date), pct or 0.0)

        # Daspoort series — derive removal % from SP1 (influent) → SP4 (effluent)
        dasp_by_date: dict = defaultdict(dict)
        for d, sp, conc in dasp_rows:
            dasp_by_date[d][sp or ""] = conc or 0.0

        dasp_series = QLineSeries()
        dasp_series.setName("Daspoort WWTP")
        dasp_series.setColor(QColor(SERIES_COLORS[1]))
        for d in sorted(dasp_by_date.keys()):
            pts = dasp_by_date[d]
            inf_conc = pts.get("SP1_influent") or pts.get("SP1") or 0.0
            eff_conc = pts.get("SP4_effluent") or pts.get("SP4") or 0.0
            if inf_conc > 0:
                removal = max(0.0, (inf_conc - eff_conc) / inf_conc * 100)
                dasp_series.append(_date_to_ms(d), removal)

        chart.addSeries(lab_series)
        if dasp_series.count() > 0:
            chart.addSeries(dasp_series)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd MMM yy")
        _style_axis(axis_x, "Date")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        _style_axis(axis_y, "Removal (%)")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        _attach_axes(chart, axis_x, axis_y)
        self._ld_view.setChart(chart)

    # ── Tab 2: Model vs Actual ─────────────────────────────────────────────────

    def _build_tab_model_vs_actual(self) -> QWidget:
        """
        Tab 2: Phase 1 predicted removal % (SimulationRun) vs
        actual measured removal % derived from daily readings.
        """
        w = QWidget()
        w.setStyleSheet(f"background:{C_CARD};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        lbl = QLabel("Parameter:")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl)
        self._mv_param_combo = QComboBox()
        self._mv_param_combo.addItems(["COD", "NH4", "TP", "PFAS"])
        self._mv_param_combo.setFixedWidth(150)
        self._mv_param_combo.setStyleSheet(self._combo_style())
        self._mv_param_combo.currentIndexChanged.connect(self._refresh_model_vs_actual)
        row.addWidget(self._mv_param_combo)
        row.addStretch()
        layout.addLayout(row)

        self._mv_view = _make_chart_view(
            _make_chart("Phase 1 Model Prediction vs Actual Removal %")
        )
        layout.addWidget(self._mv_view)
        return w

    def _refresh_model_vs_actual(self):
        """Load data and rebuild the Model vs Actual chart."""
        param = self._mv_param_combo.currentText()
        chart = _make_chart(f"Phase 1 Model Prediction vs Actual — {param} Removal %")

        # Map parameter → predicted column on SimulationRun
        pred_col_map = {
            "COD":  SimulationRun.pred_cod_removal,
            "NH4":  SimulationRun.pred_nh4_removal,
            "TP":   SimulationRun.pred_tp_removal,
            "PFAS": SimulationRun.pred_pfas_removal,
        }
        pred_col = pred_col_map[param]

        # Map parameter → DailyReading column for computing actual removal
        actual_col_map = {
            "COD": "cod_mgl",
            "NH4": "nh4_mgl",
            "TP":  "po4_mgl",   # phosphate as TP proxy
            # PFAS has no DailyReading column — handled via absence below
        }
        actual_col_name = actual_col_map.get(param)

        with get_session() as s:
            # Phase 1 simulation runs over time
            sim_rows = (
                s.query(SimulationRun.run_date, pred_col)
                .filter(pred_col.isnot(None))
                .order_by(SimulationRun.run_date)
                .all()
            )

            # Actual removal: (anaerobic zone value − effluent zone value) / anaerobic * 100
            actual_rows = []
            if actual_col_name:
                col_attr = getattr(DailyReading, actual_col_name)
                inf_data = {
                    r.reading_date: getattr(r, actual_col_name)
                    for r in s.query(DailyReading)
                    .filter(DailyReading.zone == "anaerobic")
                    .filter(col_attr.isnot(None))
                    .all()
                }
                eff_data = {
                    r.reading_date: getattr(r, actual_col_name)
                    for r in s.query(DailyReading)
                    .filter(DailyReading.zone == "effluent")
                    .filter(col_attr.isnot(None))
                    .all()
                }
                for d in sorted(set(inf_data) & set(eff_data)):
                    inf_v = inf_data[d] or 0.0
                    eff_v = eff_data[d] or 0.0
                    if inf_v > 0:
                        actual_rows.append((d, max(0.0, (inf_v - eff_v) / inf_v * 100)))

        if not sim_rows and not actual_rows:
            chart.setTitle(
                "No simulation runs yet — go to the Simulation tab and run a scenario."
            )
            self._mv_view.setChart(chart)
            return

        pred_series = QLineSeries()
        pred_series.setName("Model Prediction (Phase 1)")
        pred_series.setColor(QColor(SERIES_COLORS[4]))   # purple
        for run_dt, pct in sim_rows:
            pred_series.append(_date_to_ms(run_dt), pct or 0.0)

        actual_series = QLineSeries()
        actual_series.setName("Actual Measured")
        actual_series.setColor(QColor(SERIES_COLORS[2]))  # amber
        for row_date, pct in actual_rows:
            actual_series.append(_date_to_ms(row_date), pct)

        chart.addSeries(pred_series)
        if actual_series.count() > 0:
            chart.addSeries(actual_series)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd MMM yy")
        _style_axis(axis_x, "Date / Run Time")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        _style_axis(axis_y, "Removal (%)")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        _attach_axes(chart, axis_x, axis_y)
        self._mv_view.setChart(chart)

    # ── Tab 3: CEC Trends ──────────────────────────────────────────────────────

    def _build_tab_cec_trends(self) -> QWidget:
        """
        Tab 3: CEC concentration at each sampling point over time.
        Each series is one sampling point (SP1→SP4), showing how
        concentration falls across the treatment train over the experiment.
        """
        w = QWidget()
        w.setStyleSheet(f"background:{C_CARD};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        lbl1 = QLabel("CEC:")
        lbl1.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl1)
        self._ct_cec_combo = QComboBox()
        self._ct_cec_combo.setFixedWidth(190)
        self._ct_cec_combo.setStyleSheet(self._combo_style())
        self._ct_cec_combo.currentIndexChanged.connect(self._refresh_cec_trends)
        row.addWidget(self._ct_cec_combo)

        lbl2 = QLabel("   Sampling Point:")
        lbl2.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl2)
        self._ct_sp_combo = QComboBox()
        self._ct_sp_combo.addItems([
            "All", "SP1_influent", "SP2_primary", "SP3_clarifier", "SP4_effluent",
        ])
        self._ct_sp_combo.setFixedWidth(170)
        self._ct_sp_combo.setStyleSheet(self._combo_style())
        self._ct_sp_combo.currentIndexChanged.connect(self._refresh_cec_trends)
        row.addWidget(self._ct_sp_combo)
        row.addStretch()
        layout.addLayout(row)

        self._ct_view = _make_chart_view(
            _make_chart("CEC Concentration Trends (µg/L)")
        )
        layout.addWidget(self._ct_view)
        return w

    def _refresh_cec_trends(self):
        """Load data and rebuild the CEC concentration trends chart."""
        cec = self._ct_cec_combo.currentText()
        sp  = self._ct_sp_combo.currentText()
        chart = _make_chart(f"{cec or 'CEC'} — Concentration Over Time (µg/L)")

        with get_session() as s:
            q = (
                s.query(
                    CECReading.reading_date,
                    CECReading.sampling_point,
                    CECReading.concentration,
                )
                .filter(CECReading.cec_name == cec)
                .filter(CECReading.concentration.isnot(None))
            )
            if sp != "All":
                q = q.filter(CECReading.sampling_point == sp)
            rows = q.order_by(CECReading.reading_date, CECReading.sampling_point).all()

        if not rows:
            chart.setTitle(f"No concentration data logged yet for '{cec}'.")
            self._ct_view.setChart(chart)
            return

        # Group readings by sampling point
        by_sp: dict = defaultdict(list)
        for d, sampling_pt, conc in rows:
            by_sp[sampling_pt or "Unknown"].append((d, conc or 0.0))

        # Render in treatment order: SP1 → SP2 → SP3 → SP4
        sp_order = ["SP1_influent", "SP2_primary", "SP3_clarifier", "SP4_effluent"]
        ordered_sps = [p for p in sp_order if p in by_sp] + \
                      [p for p in by_sp  if p not in sp_order]

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd MMM yy")
        _style_axis(axis_x, "Date")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        _style_axis(axis_y, "Concentration (µg/L)")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        max_conc = 0.0
        for i, sp_name in enumerate(ordered_sps):
            series = QLineSeries()
            series.setName(sp_name.replace("_", " "))
            series.setColor(QColor(SERIES_COLORS[i % len(SERIES_COLORS)]))
            for d, conc in by_sp[sp_name]:
                series.append(_date_to_ms(d), conc)
                max_conc = max(max_conc, conc)
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        axis_y.setRange(0, max_conc * 1.15 if max_conc > 0 else 10.0)
        self._ct_view.setChart(chart)

    # ── Tab 4: Parameter Trends ────────────────────────────────────────────────

    def _build_tab_param_trends(self) -> QWidget:
        """
        Tab 4: Daily water quality parameter trends per reactor zone.
        Each series is one zone (anaerobic → anoxic → aerobic → effluent).
        """
        w = QWidget()
        w.setStyleSheet(f"background:{C_CARD};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        lbl1 = QLabel("Parameter:")
        lbl1.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl1)
        self._pt_param_combo = QComboBox()
        self._pt_param_combo.addItems([
            "DO (mg/L)", "pH", "Temperature (°C)", "COD (mg/L)",
            "NH4 (mg/L)", "NO3 (mg/L)", "PO4 (mg/L)", "MLSS (mg/L)",
        ])
        self._pt_param_combo.setFixedWidth(175)
        self._pt_param_combo.setStyleSheet(self._combo_style())
        self._pt_param_combo.currentIndexChanged.connect(self._refresh_param_trends)
        row.addWidget(self._pt_param_combo)

        lbl2 = QLabel("   Zone:")
        lbl2.setStyleSheet(f"color:{C_TEXT}; font-size:11px; font-weight:600;")
        row.addWidget(lbl2)
        self._pt_zone_combo = QComboBox()
        self._pt_zone_combo.addItems([
            "All zones", "anaerobic", "anoxic", "aerobic", "effluent",
        ])
        self._pt_zone_combo.setFixedWidth(140)
        self._pt_zone_combo.setStyleSheet(self._combo_style())
        self._pt_zone_combo.currentIndexChanged.connect(self._refresh_param_trends)
        row.addWidget(self._pt_zone_combo)
        row.addStretch()
        layout.addLayout(row)

        self._pt_view = _make_chart_view(_make_chart("Daily Parameter Trends"))
        layout.addWidget(self._pt_view)
        return w

    def _refresh_param_trends(self):
        """Load data and rebuild the daily parameter trends chart."""
        param_label = self._pt_param_combo.currentText()
        zone_filter = self._pt_zone_combo.currentText()

        # Map display name → DailyReading column
        param_col_map = {
            "DO (mg/L)":        "do_mgl",
            "pH":               "ph",
            "Temperature (°C)": "temperature_c",
            "COD (mg/L)":       "cod_mgl",
            "NH4 (mg/L)":       "nh4_mgl",
            "NO3 (mg/L)":       "no3_mgl",
            "PO4 (mg/L)":       "po4_mgl",
            "MLSS (mg/L)":      "mlss_mgl",
        }
        col_name = param_col_map.get(param_label, "do_mgl")
        col_attr = getattr(DailyReading, col_name)
        chart = _make_chart(f"{param_label} — Trend by Zone")

        with get_session() as s:
            q = (
                s.query(DailyReading.reading_date, DailyReading.zone, col_attr)
                .filter(col_attr.isnot(None))
            )
            if zone_filter != "All zones":
                q = q.filter(DailyReading.zone == zone_filter)
            rows = q.order_by(DailyReading.reading_date).all()

        if not rows:
            chart.setTitle(f"No {param_label} readings logged yet.")
            self._pt_view.setChart(chart)
            return

        # Group readings by zone
        by_zone: dict = defaultdict(list)
        for d, zone, val in rows:
            by_zone[zone].append((d, val or 0.0))

        zone_order = ["anaerobic", "anoxic", "aerobic", "effluent"]
        ordered_zones = [z for z in zone_order if z in by_zone] + \
                        [z for z in by_zone if z not in zone_order]

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd MMM yy")
        _style_axis(axis_x, "Date")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        _style_axis(axis_y, param_label)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        max_val = 0.0
        for i, zone in enumerate(ordered_zones):
            series = QLineSeries()
            series.setName(zone.capitalize())
            series.setColor(QColor(SERIES_COLORS[i % len(SERIES_COLORS)]))
            for d, val in by_zone[zone]:
                series.append(_date_to_ms(d), val)
                max_val = max(max_val, val)
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        axis_y.setRange(0, max_val * 1.15 if max_val > 0 else 10.0)
        self._pt_view.setChart(chart)

    # ── Refresh entry point ────────────────────────────────────────────────────

    def refresh(self):
        """Reload all data and rebuild all four charts."""
        self._populate_cec_dropdowns()
        self._refresh_lab_daspoort()
        self._refresh_model_vs_actual()
        self._refresh_cec_trends()
        self._refresh_param_trends()

    def _populate_cec_dropdowns(self):
        """
        Fill CEC selector combos with distinct names from the database.
        Preserves the currently selected item when the list is refreshed.
        """
        with get_session() as s:
            names = sorted({
                r[0] for r in s.query(CECReading.cec_name).distinct().all()
                if r[0]
            })

        for combo in (self._ld_cec_combo, self._ct_cec_combo):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            if names:
                combo.addItems(names)
                idx = combo.findText(current)
                combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    # ── PNG export ────────────────────────────────────────────────────────────

    def _export_charts(self):
        """
        Grab each QChartView as a QPixmap and save to a user-chosen folder.
        Filenames are numbered to sort in tab order.
        """
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Export Folder", os.path.expanduser("~")
        )
        if not folder:
            return

        chart_views = {
            "01_lab_vs_daspoort":  self._ld_view,
            "02_model_vs_actual":  self._mv_view,
            "03_cec_trends":       self._ct_view,
            "04_parameter_trends": self._pt_view,
        }

        saved = []
        for name, view in chart_views.items():
            pixmap = view.grab()
            path = os.path.join(folder, f"{name}.png")
            if pixmap.save(path, "PNG"):
                saved.append(path)

        if saved:
            QMessageBox.information(
                self, "Export Complete",
                f"Saved {len(saved)} chart(s) to:\n{folder}",
            )
        else:
            QMessageBox.warning(
                self, "Export Failed",
                "No charts could be saved. Check that the folder is writable.",
            )

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _hdr_btn_style(self, accent: bool = False) -> str:
        """Button style for header bar (dark background context)."""
        if accent:
            return (
                "QPushButton { background:#8e44ad; color:#fff; border:none; "
                "border-radius:4px; padding:4px 12px; font-size:11px; }"
                "QPushButton:hover { background:#9b59b6; }"
            )
        return (
            "QPushButton { background:rgba(255,255,255,0.12); color:#ecf0f1; border:none; "
            "border-radius:4px; padding:4px 12px; font-size:11px; }"
            "QPushButton:hover { background:rgba(255,255,255,0.22); }"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ border:1px solid {C_BORDER}; border-radius:4px; "
            f"background:#fff; color:{C_TEXT}; padding:3px 8px; font-size:11px; }}"
            f"QComboBox QAbstractItemView {{ background:#fff; color:{C_TEXT}; "
            f"selection-background-color:#d6eaf8; }}"
        )

"""
mass_balance.py — Mass Balance Calculator screen (Step 7).

Auto-populates from the logged flow and CEC readings for the active
experiment, then shows the full worked calculation and fate breakdown.

Equations (from PhD proposal):
    Eq 2:  Q_eff  = Q_in − Q_psludge − Q_WAS          (mL/h)
    Eq 1:  mass_eff = C_eff × Q_eff × 24 / 1000       (µg/day)
    mass_in      = C_inf × Q_in  × 24 / 1000          (µg/day)
    mass_sludge  = C_sludge × Q_WAS × 24 / 1000       (µg/day)
    mass_transformed = mass_in − mass_eff − mass_sludge
    removal %    = (C_inf − C_eff) / C_inf × 100

Layout:
    ┌─── Header: title · date picker · Calculate button ─────────────┐
    ├─── Info strip ──────────────────────────────────────────────────┤
    ├─── Left: Equation workings ─────┬─── Right: Fate pie/breakdown ┤
    ├─── Results table (all CECs) ────────────────────────────────────┤
    └─── Export CSV button ───────────────────────────────────────────┘
"""

import csv
import os
from datetime import date as dt_date

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDateEdit, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy, QMessageBox, QFileDialog,
)
from ui.docking_utils import make_inner_window, make_dock, make_dock_toolbar
from PySide6.QtCore import Qt, QDate, QSize, QMargins
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QPieSlice,
)

from core.database import get_session
from core.models import Experiment, CECReading, FlowReading, MassBalanceResult
from core.calculations import full_mass_balance

C_HDR = "#2c3e50"


class MassBalanceScreen(QWidget):
    """
    Mass balance calculator that auto-populates from logged data and
    displays a worked equation, fate breakdown chart, and results table.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[dict] = []   # last calculated results
        # Guard so resizeDocks() only runs once after the window is visible
        self._docks_sized = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_info_strip())

        # Inner QMainWindow manages the three dockable panels.
        # Qt.WindowType.Widget keeps it embedded — not a standalone OS window.
        self._inner_mw = make_inner_window()

        # Minimal central placeholder — docks fill all visible space
        central = QWidget()
        central.setStyleSheet("background:#f5f6fa;")
        self._inner_mw.setCentralWidget(central)

        # Build docks from the existing panel builder methods
        self._dock_eq      = make_dock("Equation Workings", self._build_equation_panel())
        self._dock_fate    = make_dock("Fate Breakdown",    self._build_fate_panel())
        self._dock_results = make_dock("All CEC Results",   self._build_results_table())

        self._inner_mw.addDockWidget(Qt.LeftDockWidgetArea,   self._dock_eq)
        self._inner_mw.addDockWidget(Qt.RightDockWidgetArea,  self._dock_fate)
        self._inner_mw.addDockWidget(Qt.BottomDockWidgetArea, self._dock_results)

        # Results table spans the full width of the bottom area
        self._inner_mw.setCorner(Qt.BottomLeftCorner,  Qt.BottomDockWidgetArea)
        self._inner_mw.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        # Compact toolbar with one toggle button per dock (hide / restore)
        make_dock_toolbar(
            self._inner_mw,
            [self._dock_eq, self._dock_fate, self._dock_results],
        )

        root.addWidget(self._inner_mw, stretch=1)
        # Export bar stays outside the dock system — always accessible
        root.addWidget(self._build_export_bar())

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background:{C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        t = QLabel("Mass Balance")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#ecf0f1;")
        row.addWidget(t)
        row.addStretch()

        dl = QLabel("Date:")
        dl.setStyleSheet("color:#bdc3c7; font-size:11px;")
        row.addWidget(dl)

        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setFixedHeight(30)
        self._date_edit.setFixedWidth(130)
        self._date_edit.setStyleSheet("""
            QDateEdit { background:#3d5166; color:#ecf0f1;
                border:1px solid #566573; border-radius:4px;
                padding:2px 6px; font-size:11px; }
        """)
        row.addWidget(self._date_edit)

        calc_btn = QPushButton("  Calculate")
        calc_btn.setIcon(qta.icon("fa6s.calculator", color="#fff"))
        calc_btn.setIconSize(QSize(13, 13))
        calc_btn.setFixedHeight(34)
        calc_btn.setCursor(Qt.PointingHandCursor)
        calc_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }
            QPushButton:hover { background:#9b59b6; }
            QPushButton:pressed { background:#6c3483; }
        """)
        calc_btn.clicked.connect(self._on_calculate)
        row.addWidget(calc_btn)

        return bar

    # ── Info strip ─────────────────────────────────────────────────────────────
    def _build_info_strip(self) -> QWidget:
        strip = QWidget()
        strip.setFixedHeight(30)
        strip.setStyleSheet("background:#dfe6e9; border-bottom:1px solid #b2bec3;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 0, 14, 0)
        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.scale-balanced", color="#636e72").pixmap(QSize(13, 13)))
        row.addWidget(icon)
        row.addSpacing(5)
        self._info_label = QLabel("Select a date and click Calculate.")
        self._info_label.setStyleSheet("color:#636e72; font-size:11px;")
        row.addWidget(self._info_label)
        row.addStretch()
        return strip

    # ── Equation panel ─────────────────────────────────────────────────────────
    def _build_equation_panel(self) -> QWidget:
        """
        Shows the equation workings for the first CEC calculated.
        Displays each step with its substituted numeric values.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        t = QLabel("Equation Workings")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        # Flow equations section
        flow_title = QLabel("Step 1 — Equation 2: Calculate Q_eff")
        flow_title.setStyleSheet("color:#8e44ad; font-size:10px; font-weight:600;")
        layout.addWidget(flow_title)

        self._eq2_label = QLabel("Q_eff = Q_in − Q_psludge − Q_WAS\n\n  Waiting for data…")
        self._eq2_label.setStyleSheet("""
            background:#f8f4ff; border:1px solid #d7bde2; border-radius:6px;
            padding:10px 14px; font-size:11px; color:#4a235a;
            font-family: Consolas, monospace;
        """)
        self._eq2_label.setWordWrap(True)
        layout.addWidget(self._eq2_label)

        mass_title = QLabel("Step 2 — Equation 1: Calculate Mass Loads")
        mass_title.setStyleSheet("color:#2471a3; font-size:10px; font-weight:600;")
        layout.addWidget(mass_title)

        self._eq1_label = QLabel("mass = C × Q × 24 ÷ 1000\n\n  Waiting for data…")
        self._eq1_label.setStyleSheet("""
            background:#eaf4fb; border:1px solid #aed6f1; border-radius:6px;
            padding:10px 14px; font-size:11px; color:#1a5276;
            font-family: Consolas, monospace;
        """)
        self._eq1_label.setWordWrap(True)
        layout.addWidget(self._eq1_label)

        removal_title = QLabel("Step 3 — Removal Efficiency")
        removal_title.setStyleSheet("color:#1e8449; font-size:10px; font-weight:600;")
        layout.addWidget(removal_title)

        self._removal_label = QLabel("removal % = (C_inf − C_eff) / C_inf × 100\n\n  Waiting for data…")
        self._removal_label.setStyleSheet("""
            background:#eafaf1; border:1px solid #a9dfbf; border-radius:6px;
            padding:10px 14px; font-size:11px; color:#1e8449;
            font-family: Consolas, monospace;
        """)
        self._removal_label.setWordWrap(True)
        layout.addWidget(self._removal_label)

        layout.addStretch()
        return card

    # ── Fate breakdown panel ───────────────────────────────────────────────────
    def _build_fate_panel(self) -> QWidget:
        """
        Right panel: pie chart showing fate breakdown (effluent / sludge /
        transformed) for the first CEC, plus a summary label.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)

        t = QLabel("Fate Breakdown")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        self._pie_series = QPieSeries()
        self._pie_series.setHoleSize(0.38)   # donut style

        self._pie_chart = QChart()
        self._pie_chart.addSeries(self._pie_series)
        self._pie_chart.setTitle("No data yet")
        self._pie_chart.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self._pie_chart.setBackgroundRoundness(0)
        self._pie_chart.setMargins(QMargins(4, 4, 4, 4))
        self._pie_chart.legend().setAlignment(Qt.AlignBottom)

        view = QChartView(self._pie_chart)
        from PySide6.QtGui import QPainter
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(260)
        view.setStyleSheet("border:1px solid #dde1e7; border-radius:6px;")
        layout.addWidget(view, stretch=1)

        # Fate summary text
        self._fate_label = QLabel("Run a calculation to see the fate breakdown.")
        self._fate_label.setWordWrap(True)
        self._fate_label.setAlignment(Qt.AlignCenter)
        self._fate_label.setStyleSheet("color:#7f8c8d; font-size:11px; padding:6px;")
        layout.addWidget(self._fate_label)

        return card

    # ── Results table ──────────────────────────────────────────────────────────
    def _build_results_table(self) -> QWidget:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)

        t = QLabel("Results — All CECs for Selected Date")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        t.setFont(f); t.setStyleSheet("color:#2c3e50;")
        layout.addWidget(t)
        layout.addWidget(self._make_divider())

        cols = ["CEC", "C_inf\n(µg/L)", "C_eff\n(µg/L)",
                "Q_eff\n(mL/h)", "Mass In\n(µg/day)",
                "Mass Eff\n(µg/day)", "Mass Sludge\n(µg/day)",
                "Transformed\n(µg/day)", "Removal\n%"]
        self._results_table = QTableWidget(0, len(cols))
        self._results_table.setHorizontalHeaderLabels(cols)
        self._results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, len(cols)):
            self._results_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self._results_table.verticalHeader().setVisible(False)
        self._results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setShowGrid(False)
        self._results_table.setFixedHeight(200)
        self._results_table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:11px;
                alternate-background-color:#f8f9fa; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:4px 8px; }
        """)
        layout.addWidget(self._results_table)
        return card

    # ── Export bar ─────────────────────────────────────────────────────────────
    def _build_export_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background:transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 4, 0, 4)
        row.addStretch()

        export_btn = QPushButton("  Export to CSV")
        export_btn.setIcon(qta.icon("fa6s.file-csv", color="#fff"))
        export_btn.setIconSize(QSize(13, 13))
        export_btn.setFixedHeight(34)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setStyleSheet("""
            QPushButton { background:#27ae60; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }
            QPushButton:hover { background:#2ecc71; }
        """)
        export_btn.clicked.connect(self._on_export)
        row.addWidget(export_btn)
        return bar

    # ── Calculate ──────────────────────────────────────────────────────────────
    def _on_calculate(self) -> None:
        """
        1. Find active experiment.
        2. Load flow reading for selected date.
        3. Load all CEC readings for selected date (SP1 + SP4 needed).
        4. Run full_mass_balance() for each CEC.
        5. Save results to mass_balance_results table.
        6. Update equation panel, chart, and results table.
        """
        active = self._get_active_experiment()
        if not active:
            QMessageBox.warning(self, "No Active Experiment",
                "Please set an active experiment first.")
            return

        qd = self._date_edit.date()
        calc_date = dt_date(qd.year(), qd.month(), qd.day())

        try:
            with get_session() as session:
                # Load flow reading
                flow = (
                    session.query(FlowReading)
                    .filter_by(experiment_id=active["id"], reading_date=calc_date)
                    .first()
                )
                if flow is None:
                    QMessageBox.warning(self, "No Flow Data",
                        f"No flow readings found for {calc_date}.\n\n"
                        "Please enter flow data in the Daily Log first.")
                    return

                q_in  = flow.q_in_mlh       or 0.0
                q_was = flow.q_was_mlh      or 0.0
                q_ps  = flow.q_psludge_mlh  or 0.0

                # Load CEC readings — group by CEC name
                cec_rows = (
                    session.query(CECReading)
                    .filter_by(experiment_id=active["id"], reading_date=calc_date)
                    .all()
                )
                from collections import defaultdict
                cec_map: dict[str, dict] = defaultdict(dict)
                for r in cec_rows:
                    conc = r.concentration if not r.below_detection else (
                        (r.detection_limit / 2) if r.detection_limit else 0.0
                    )
                    cec_map[r.cec_name][r.sampling_point] = conc or 0.0

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", str(exc))
            return

        if not cec_map:
            QMessageBox.information(self, "No CEC Data",
                f"No CEC readings found for {calc_date}.\n\n"
                "Please enter CEC concentrations in the CEC Tracker first.")
            return

        # ── Run calculations ───────────────────────────────────────────────────
        self._results = []
        try:
            with get_session() as session:
                for cec_name, sp_concs in cec_map.items():
                    c_inf    = sp_concs.get("SP1_influent",   0.0)
                    c_eff    = sp_concs.get("SP4_effluent",   0.0)
                    c_sludge = 0.0   # sludge concentration not separately tracked

                    mb = full_mass_balance(c_inf, c_eff, c_sludge, q_in, q_was, q_ps)

                    result = {
                        "cec_name":    cec_name,
                        "c_inf":       c_inf,
                        "c_eff":       c_eff,
                        "q_in":        q_in,
                        "q_was":       q_was,
                        "q_ps":        q_ps,
                        **mb,
                    }
                    self._results.append(result)

                    # Persist to mass_balance_results table
                    existing = (
                        session.query(MassBalanceResult)
                        .filter_by(
                            experiment_id=active["id"],
                            calculation_date=calc_date,
                            cec_name=cec_name,
                        )
                        .first()
                    )
                    row = existing or MassBalanceResult(
                        experiment_id    = active["id"],
                        calculation_date = calc_date,
                        cec_name         = cec_name,
                    )
                    if not existing:
                        session.add(row)

                    row.mass_in_mgday     = mb["mass_in_ugday"]
                    row.mass_eff_mgday    = mb["mass_eff_ugday"]
                    row.mass_sludge_mgday = mb["mass_sludge_ugday"]
                    row.mass_transformed  = mb["mass_transformed_ugday"]
                    row.removal_pct       = mb["removal_pct"]
                    row.q_eff_mlday       = mb["q_eff_mlh"] * 24

        except Exception as exc:
            QMessageBox.critical(self, "Calculation Error", str(exc))
            return

        # ── Update UI ──────────────────────────────────────────────────────────
        self._info_label.setText(
            f"Calculated {len(self._results)} CEC(s) for {calc_date} — results saved.")
        self._info_label.setStyleSheet("color:#1e8449; font-size:11px; font-weight:600;")

        self._update_equation_panel(self._results[0] if self._results else None)
        self._update_fate_chart(self._results[0] if self._results else None)
        self._update_results_table()

    # ── UI update helpers ──────────────────────────────────────────────────────
    def _update_equation_panel(self, r: dict | None) -> None:
        """Fill the equation workings panel with substituted values."""
        if r is None:
            return

        q_eff = r["q_eff_mlh"]
        self._eq2_label.setText(
            f"Q_eff  =  Q_in  −  Q_psludge  −  Q_WAS\n"
            f"       =  {r['q_in']:.1f}  −  {r['q_ps']:.1f}  −  {r['q_was']:.1f}\n"
            f"       =  {q_eff:.1f}  mL/h"
        )

        self._eq1_label.setText(
            f"CEC: {r['cec_name']}\n\n"
            f"mass_in   =  C_inf  ×  Q_in  ×  24 ÷ 1000\n"
            f"          =  {r['c_inf']:.4f}  ×  {r['q_in']:.1f}  ×  24 ÷ 1000\n"
            f"          =  {r['mass_in_ugday']:.4f}  µg/day\n\n"
            f"mass_eff  =  C_eff  ×  Q_eff  ×  24 ÷ 1000\n"
            f"          =  {r['c_eff']:.4f}  ×  {q_eff:.1f}  ×  24 ÷ 1000\n"
            f"          =  {r['mass_eff_ugday']:.4f}  µg/day"
        )

        self._removal_label.setText(
            f"removal % =  (C_inf − C_eff) / C_inf  ×  100\n"
            f"          =  ({r['c_inf']:.4f} − {r['c_eff']:.4f}) / {r['c_inf']:.4f}  ×  100\n"
            f"          =  {r['removal_pct']:.2f} %\n\n"
            f"mass_transformed = {r['mass_transformed_ugday']:.4f}  µg/day"
        )

    def _update_fate_chart(self, r: dict | None) -> None:
        """Redraw the donut pie chart with fate percentages."""
        self._pie_series.clear()
        if r is None or r["mass_in_ugday"] <= 0:
            self._pie_chart.setTitle("No data")
            return

        mass_in = r["mass_in_ugday"]
        slices = [
            ("To Effluent",    r["mass_eff_ugday"],         QColor("#e74c3c")),
            ("To Sludge",      r["mass_sludge_ugday"],      QColor("#e67e22")),
            ("Transformed",    r["mass_transformed_ugday"], QColor("#27ae60")),
        ]
        for label, value, color in slices:
            if value > 0:
                sl = self._pie_series.append(label, value)
                sl.setBrush(QBrush(color))
                sl.setLabelVisible(True)
                pct = value / mass_in * 100
                sl.setLabel(f"{label}\n{pct:.1f}%")

        self._pie_chart.setTitle(f"{r['cec_name']} — Fate Breakdown")
        self._fate_label.setText(
            f"Mass in: {mass_in:.3f} µg/day  |  "
            f"Removal: {r['removal_pct']:.1f}%"
        )
        self._fate_label.setStyleSheet("color:#2c3e50; font-size:11px; font-weight:600; padding:6px;")

    def _update_results_table(self) -> None:
        """Populate the results table with all calculated CECs."""
        self._results_table.setRowCount(len(self._results))
        for row_i, r in enumerate(self._results):
            vals = [
                r["cec_name"],
                f"{r['c_inf']:.4f}",
                f"{r['c_eff']:.4f}",
                f"{r['q_eff_mlh']:.1f}",
                f"{r['mass_in_ugday']:.4f}",
                f"{r['mass_eff_ugday']:.4f}",
                f"{r['mass_sludge_ugday']:.4f}",
                f"{r['mass_transformed_ugday']:.4f}",
                f"{r['removal_pct']:.2f}",
            ]
            for col_i, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                # Colour removal % cell
                if col_i == 8:
                    pct = r["removal_pct"]
                    color = QColor(
                        "#1e8449" if pct >= 60 else
                        "#d68910" if pct >= 30 else
                        "#c0392b"
                    )
                    item.setForeground(QBrush(color))
                    f = QFont(); f.setBold(True); item.setFont(f)
                self._results_table.setItem(row_i, col_i, item)
            self._results_table.setRowHeight(row_i, 34)

    # ── Export ─────────────────────────────────────────────────────────────────
    def _on_export(self) -> None:
        """Save the current results to a CSV file chosen by the user."""
        if not self._results:
            QMessageBox.information(self, "No Results",
                "Run a calculation first before exporting.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Mass Balance Results", "", "CSV files (*.csv)"
        )
        if not path:
            return

        headers = ["CEC", "C_inf_ugl", "C_eff_ugl", "Q_eff_mlh",
                   "mass_in_ugday", "mass_eff_ugday", "mass_sludge_ugday",
                   "mass_transformed_ugday", "removal_pct"]
        try:
            with open(path, "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers)
                writer.writeheader()
                for r in self._results:
                    writer.writerow({
                        "CEC":                   r["cec_name"],
                        "C_inf_ugl":             r["c_inf"],
                        "C_eff_ugl":             r["c_eff"],
                        "Q_eff_mlh":             r["q_eff_mlh"],
                        "mass_in_ugday":         r["mass_in_ugday"],
                        "mass_eff_ugday":        r["mass_eff_ugday"],
                        "mass_sludge_ugday":     r["mass_sludge_ugday"],
                        "mass_transformed_ugday":r["mass_transformed_ugday"],
                        "removal_pct":           r["removal_pct"],
                    })
            QMessageBox.information(self, "Export Complete",
                f"Results saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Database helpers ───────────────────────────────────────────────────────
    def _get_active_experiment(self) -> dict | None:
        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(is_active=True).first()
                if exp:
                    return {"id": exp.id, "name": exp.name}
        except Exception:
            pass
        return None

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        super().showEvent(event)
        active = self._get_active_experiment()
        if active:
            self._info_label.setText(
                f"Active experiment: {active['name']}  — Select a date and click Calculate.")
            self._info_label.setStyleSheet("color:#636e72; font-size:11px;")
        else:
            self._info_label.setText("No active experiment — go to Experiments first.")
            self._info_label.setStyleSheet("color:#e74c3c; font-size:11px;")
        # Set initial dock proportions once the window has been laid out.
        # resizeDocks() has no effect before the widget is visible.
        if not self._docks_sized:
            self._inner_mw.resizeDocks(
                [self._dock_results], [200], Qt.Vertical,
            )
            self._inner_mw.resizeDocks(
                [self._dock_eq, self._dock_fate], [540, 480], Qt.Horizontal,
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

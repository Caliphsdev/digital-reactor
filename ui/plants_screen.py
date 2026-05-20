"""
plants_screen.py — Real-Plant Scientific Twin screen.

V1 includes only three South African plants:
  * Daspoort WWTW
  * Zeekoegat WWTW
  * Phola WWTP

The screen is intentionally labelled as a Scientific Twin: process-realistic
and mass-balance based, but not a live operational replica until field data is
connected and calibration is performed.
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QDoubleSpinBox, QComboBox, QScrollArea,
    QSizePolicy, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from core.database import get_session
from core.models import Plant, PlantMonitoringReading
from core.plant_calibration import (
    CALIBRATION_TARGETS,
    calibrate_plant,
    get_calibration_factors,
    get_calibration_summary,
    import_monitoring_file,
)
from simulation.plant_model import (
    BNR_MODES, PlantTwinInputs, PlantTwinOutputs, run_plant_twin,
)


C_HDR = "#2c3e50"
C_BG = "#f5f6fa"
C_CARD = "#ffffff"
C_BORDER = "#dde1e7"
C_TEXT = "#2c3e50"
C_MUTED = "#636e72"


def _item(text: str, align=Qt.AlignCenter) -> QTableWidgetItem:
    cell = QTableWidgetItem(text)
    cell.setTextAlignment(align)
    cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return cell


def _default(value, fallback: float = 0.0) -> float:
    return float(value) if value is not None else fallback


class PlantImportWorker(QThread):
    """Background worker for potentially large CSV/Excel monitoring imports."""
    result_ready = Signal(dict)

    def __init__(self, plant_slug: str, path: str, parent=None):
        super().__init__(parent)
        self.plant_slug = plant_slug
        self.path = path

    def run(self) -> None:
        try:
            with get_session() as session:
                result = import_monitoring_file(session, self.plant_slug, self.path)
            self.result_ready.emit({"status": "ok", "result": result})
        except Exception as exc:
            self.result_ready.emit({"status": "error", "message": str(exc)})


class PlantCalibrationWorker(QThread):
    """Background worker for recalculating Daspoort calibration coefficients."""
    result_ready = Signal(dict)

    def __init__(self, plant_slug: str, parent=None):
        super().__init__(parent)
        self.plant_slug = plant_slug

    def run(self) -> None:
        try:
            with get_session() as session:
                result = calibrate_plant(session, self.plant_slug)
            self.result_ready.emit({"status": "ok", "result": result})
        except Exception as exc:
            self.result_ready.emit({"status": "error", "message": str(exc)})


class PlantsScreen(QWidget):
    """Container with one tab/page for each real South African plant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setStyleSheet(f"background:{C_BG};")

        root.addWidget(self._build_header())
        root.addWidget(self._build_info_strip())

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C_BORDER};
                background: {C_CARD};
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
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.addWidget(self._tabs)
        root.addWidget(content, stretch=1)

        self._load_tabs()

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background:{C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.industry", color="#ecf0f1").pixmap(QSize(18, 18)))
        row.addWidget(icon)

        title = QLabel("Real Plant Scientific Twins")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        refresh_btn = QPushButton("  Refresh")
        refresh_btn.setIcon(qta.icon("fa6s.rotate-left", color="#ecf0f1"))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton { background:#3d5166; color:#ecf0f1; border:none;
                border-radius:4px; padding:0 14px; font-size:11px; }
            QPushButton:hover { background:#3498db; }
        """)
        refresh_btn.clicked.connect(self._load_tabs)
        row.addWidget(refresh_btn)
        return bar

    def _build_info_strip(self) -> QWidget:
        strip = QWidget()
        strip.setFixedHeight(34)
        strip.setStyleSheet("background:#eaf2f8; border-bottom:1px solid #c5d8ea;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.circle-info", color="#2c6fa6").pixmap(QSize(13, 13)))
        row.addWidget(icon)

        label = QLabel(
            "Scientific Twin mode: process-realistic and mass-balance based; "
            "not a live plant replica until field data is connected."
        )
        label.setStyleSheet("color:#1f3a5f; font-size:11px; font-weight:600;")
        row.addWidget(label)
        row.addStretch()
        return strip

    def _load_tabs(self) -> None:
        """Reload plant profiles from the database and rebuild tabs."""
        if self._tabs is None:
            return
        self._tabs.clear()

        with get_session() as session:
            plants = (
                session.query(Plant)
                .filter(Plant.slug.in_(["daspoort", "zeekoegat", "phola"]))
                .order_by(Plant.name)
                .all()
            )
            # Force relationship loading before the session closes.
            plant_payloads = []
            for plant in plants:
                plant_payloads.append({
                    "plant": plant,
                    "units": list(plant.units),
                    "sampling_points": list(plant.sampling_points),
                })

        order = {"daspoort": 0, "zeekoegat": 1, "phola": 2}
        plant_payloads.sort(key=lambda p: order.get(p["plant"].slug, 99))

        if not plant_payloads:
            self._tabs.addTab(_EmptyPlantsMessage(), "No plants")
            return

        for payload in plant_payloads:
            self._tabs.addTab(
                PlantDetailPanel(payload["plant"], payload["units"], payload["sampling_points"]),
                payload["plant"].name.split(" Wastewater")[0].split(" Waste ")[0],
            )


class _EmptyPlantsMessage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel("No plant profiles found. Restart the app to run database seeding.")
        label.setStyleSheet(f"color:{C_MUTED}; font-size:13px;")
        layout.addWidget(label)


class PlantDetailPanel(QWidget):
    """One plant page: profile, process train, inputs, and simulation output."""

    def __init__(self, plant: Plant, units: list, sampling_points: list, parent=None):
        super().__init__(parent)
        self.plant = plant
        self.units = units
        self.sampling_points = sampling_points
        self._inputs: dict[str, QDoubleSpinBox] = {}
        self._result_labels: dict[str, QLabel] = {}
        self._calibration_factors: dict[str, float] = {}
        self._calibration_table = None
        self._calibration_status = None
        self._import_btn = None
        self._calibrate_btn = None
        self._import_worker = None
        self._calibration_worker = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._run)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet(f"background:{C_CARD};")
        root = QVBoxLayout(body)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        root.addLayout(self._build_profile_row())
        if self.plant.slug == "daspoort":
            root.addWidget(self._panel("Daspoort Data Import & Calibration", self._build_calibration_tools()))

        tables_row = QHBoxLayout()
        tables_row.setSpacing(10)
        tables_row.addWidget(self._panel("Process Train", self._build_units_table()), stretch=2)
        tables_row.addWidget(self._panel("Sampling Map", self._build_sampling_table()), stretch=1)
        root.addLayout(tables_row)

        sim_row = QHBoxLayout()
        sim_row.setSpacing(10)
        sim_row.addWidget(self._panel("Scientific Twin Inputs", self._build_inputs()), stretch=1)
        sim_row.addWidget(self._panel("Predicted Fate", self._build_outputs()), stretch=1)
        root.addLayout(sim_row)

        root.addWidget(self._panel("Unit-by-Unit Prediction", self._build_unit_results_table()))

        scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._refresh_calibration_state()
        QTimer.singleShot(0, self._run)

    def _build_profile_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._profile_card(
            "Plant",
            self.plant.name,
            f"{self.plant.municipality or 'Unknown municipality'} · {self.plant.province or 'Unknown province'}",
            "#2471a3",
        ))
        row.addWidget(self._profile_card(
            "Process",
            self.plant.process_family,
            f"Capacity: {_default(self.plant.capacity_mld):.1f} ML/d",
            "#1e8449",
        ))
        row.addWidget(self._profile_card(
            "Confidence",
            "Scientific Twin",
            "Literature/default assumptions until calibrated",
            "#8e44ad",
        ))
        return row

    def _build_calibration_tools(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._calibration_status = QLabel("Loading calibration status...")
        self._calibration_status.setWordWrap(True)
        self._calibration_status.setStyleSheet(
            f"color:{C_TEXT}; font-size:10px; font-weight:600;"
        )
        top.addWidget(self._calibration_status, stretch=1)

        self._import_btn = QPushButton("  Import CSV/Excel")
        self._import_btn.setIcon(qta.icon("fa6s.file-import", color="#ffffff"))
        self._import_btn.setFixedHeight(32)
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setStyleSheet("""
            QPushButton { background:#2471a3; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 12px; }
            QPushButton:hover { background:#2980b9; }
            QPushButton:disabled { background:#aab7b8; color:#ecf0f1; }
        """)
        self._import_btn.clicked.connect(self._on_import_monitoring)
        top.addWidget(self._import_btn)

        self._calibrate_btn = QPushButton("  Calibrate")
        self._calibrate_btn.setIcon(qta.icon("fa6s.sliders", color="#ffffff"))
        self._calibrate_btn.setFixedHeight(32)
        self._calibrate_btn.setCursor(Qt.PointingHandCursor)
        self._calibrate_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 12px; }
            QPushButton:hover { background:#9b59b6; }
            QPushButton:disabled { background:#aab7b8; color:#ecf0f1; }
        """)
        self._calibrate_btn.clicked.connect(self._on_calibrate)
        top.addWidget(self._calibrate_btn)
        layout.addLayout(top)

        hint = QLabel(
            "Expected columns: date, sampling_point, flow_mld, COD, NH4, TN, TP, "
            "pH, temperature, DO, MLSS, SRT, HRT, cec_name, concentration_ugl, "
            "detection_limit, below_detection. SP1/influent and SP4/effluent pairs drive calibration."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_MUTED}; font-size:10px;")
        layout.addWidget(hint)

        self._calibration_table = QTableWidget(len(CALIBRATION_TARGETS), 6)
        self._calibration_table.setHorizontalHeaderLabels([
            "Target", "Multiplier", "Samples", "RMSE", "MAE", "R2",
        ])
        self._style_table(self._calibration_table)
        self._calibration_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._calibration_table.setFixedHeight(190)
        layout.addWidget(self._calibration_table)
        return w

    def _refresh_calibration_state(self) -> None:
        if self.plant.slug != "daspoort":
            return
        try:
            with get_session() as session:
                rows_count = (
                    session.query(PlantMonitoringReading)
                    .filter_by(plant_id=self.plant.id)
                    .count()
                )
                summary = get_calibration_summary(session, self.plant.id)
                self._calibration_factors = get_calibration_factors(session, self.plant.id)
        except Exception as exc:
            if self._calibration_status:
                self._calibration_status.setText(f"Calibration unavailable: {exc}")
            self._calibration_factors = {}
            return

        calibrated = len(self._calibration_factors)
        if self._calibration_status:
            self._calibration_status.setText(
                f"Imported monitoring rows: {rows_count}  |  "
                f"Calibrated targets: {calibrated}/5"
            )

        if not self._calibration_table:
            return
        by_target = {row.target: row for row in summary}
        for row_i, target in enumerate(CALIBRATION_TARGETS):
            cal = by_target.get(target)
            values = [
                target.upper(),
                f"{cal.multiplier:.3f}" if cal else "—",
                str(cal.n_samples) if cal else "0",
                f"{cal.rmse_pct:.2f}%" if cal and cal.rmse_pct is not None else "—",
                f"{cal.mean_abs_error_pct:.2f}%" if cal and cal.mean_abs_error_pct is not None else "—",
                f"{cal.r2:.3f}" if cal and cal.r2 is not None else "—",
            ]
            for col, text in enumerate(values):
                self._calibration_table.setItem(row_i, col, _item(text))
            self._calibration_table.setRowHeight(row_i, 28)

    def _on_import_monitoring(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Daspoort Monitoring Data",
            "",
            "Data files (*.csv *.xlsx *.xls);;CSV files (*.csv);;Excel files (*.xlsx *.xls)",
        )
        if not path:
            return
        self._set_calibration_busy(True, "Importing Daspoort monitoring data...")
        self._import_worker = PlantImportWorker(self.plant.slug, path, self)
        self._import_worker.result_ready.connect(self._on_import_finished)
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        self._import_worker.start()

    def _on_import_finished(self, payload: dict) -> None:
        self._import_worker = None
        self._set_calibration_busy(False)
        if payload.get("status") != "ok":
            QMessageBox.critical(self, "Import Failed", payload.get("message", "Unknown error"))
            self._refresh_calibration_state()
            return

        result = payload["result"]
        self._refresh_calibration_state()
        self._run()
        warning_text = ""
        if result["warnings"]:
            warning_text = "\n\nWarnings:\n" + "\n".join(result["warnings"])
        QMessageBox.information(
            self,
            "Import Complete",
            f"Imported {result['imported']} new row(s).\n"
            f"Updated {result['updated']} existing row(s).\n"
            f"Skipped {result['skipped']} row(s)."
            f"{warning_text}",
        )

    def _on_calibrate(self) -> None:
        self._set_calibration_busy(True, "Calibrating Daspoort coefficients...")
        self._calibration_worker = PlantCalibrationWorker(self.plant.slug, self)
        self._calibration_worker.result_ready.connect(self._on_calibration_finished)
        self._calibration_worker.finished.connect(self._calibration_worker.deleteLater)
        self._calibration_worker.start()

    def _on_calibration_finished(self, payload: dict) -> None:
        self._calibration_worker = None
        self._set_calibration_busy(False)
        if payload.get("status") != "ok":
            QMessageBox.critical(self, "Calibration Failed", payload.get("message", "Unknown error"))
            self._refresh_calibration_state()
            return

        result = payload["result"]
        self._refresh_calibration_state()
        self._run()
        targets = result.get("targets", {})
        if targets:
            detail = ", ".join(f"{target.upper()} n={data['n_samples']}" for target, data in targets.items())
        else:
            detail = "No complete SP1-to-SP4 pairs were available yet."
        QMessageBox.information(
            self,
            "Calibration Complete",
            f"Daspoort calibration updated.\n\n{detail}",
        )

    def _set_calibration_busy(self, busy: bool, message: str | None = None) -> None:
        if self._import_btn:
            self._import_btn.setEnabled(not busy)
            self._import_btn.setText("  Importing..." if busy and message and "Import" in message else "  Import CSV/Excel")
        if self._calibrate_btn:
            self._calibrate_btn.setEnabled(not busy)
            self._calibrate_btn.setText("  Calibrating..." if busy and message and "Calibrat" in message else "  Calibrate")
        if busy and self._calibration_status and message:
            self._calibration_status.setText(message)

    def _profile_card(self, title: str, value: str, sub: str, color: str) -> QWidget:
        card = QWidget()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumHeight(88)
        card.setStyleSheet(f"""
            QWidget {{ background:#ffffff; border:1px solid {C_BORDER}; border-radius:6px; }}
            QLabel {{ border:none; background:transparent; }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet(f"color:{C_MUTED}; font-size:10px; font-weight:600;")
        v = QLabel(value)
        v.setWordWrap(True)
        v.setStyleSheet(f"color:{color}; font-size:13px; font-weight:700;")
        s = QLabel(sub)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{C_MUTED}; font-size:10px;")
        layout.addWidget(t)
        layout.addWidget(v)
        layout.addWidget(s)
        layout.addStretch()
        return card

    def _build_units_table(self) -> QTableWidget:
        table = QTableWidget(len(self.units), 5)
        table.setHorizontalHeaderLabels(["#", "Unit", "Type", "HRT", "Scientific role"])
        self._style_table(table)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.setMinimumHeight(240)

        for row, unit in enumerate(self.units):
            table.setItem(row, 0, _item(str(unit.unit_order)))
            table.setItem(row, 1, _item(unit.name, Qt.AlignLeft | Qt.AlignVCenter))
            table.setItem(row, 2, _item(unit.unit_type))
            hrt = f"{unit.hrt_hours:.1f} h" if unit.hrt_hours else "—"
            table.setItem(row, 3, _item(hrt))
            table.setItem(row, 4, _item(unit.hydraulic_role or unit.notes or "", Qt.AlignLeft | Qt.AlignVCenter))
            table.setRowHeight(row, 30)
        return table

    def _build_sampling_table(self) -> QTableWidget:
        table = QTableWidget(len(self.sampling_points), 4)
        table.setHorizontalHeaderLabels(["Code", "Location", "After", "Purpose"])
        self._style_table(table)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setMinimumHeight(240)

        for row, point in enumerate(self.sampling_points):
            table.setItem(row, 0, _item(point.code))
            table.setItem(row, 1, _item(point.name, Qt.AlignLeft | Qt.AlignVCenter))
            table.setItem(row, 2, _item(str(point.after_unit_order or "—")))
            table.setItem(row, 3, _item(point.description or "", Qt.AlignLeft | Qt.AlignVCenter))
            table.setRowHeight(row, 36)
        return table

    def _build_inputs(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)

        defs = [
            ("flow_mld", "Flow", "ML/d", 0.1, 120.0, _default(self.plant.default_flow_mld, _default(self.plant.capacity_mld, 1.0)), 2),
            ("hrt_hours", "HRT", "h", 1.0, 120.0, _default(self.plant.default_hrt_hours, 12.0), 1),
            ("srt_days", "SRT", "d", 0.0, 80.0, _default(self.plant.default_srt_days, 0.0), 1),
            ("mlss_mgl", "MLSS", "mg/L", 100.0, 10000.0, _default(self.plant.default_mlss_mgl, 3000.0), 0),
            ("do_mgl", "DO", "mg/L", 0.0, 6.0, _default(self.plant.default_do_mgl, 1.5), 2),
            ("temp_c", "Temp", "deg C", 5.0, 35.0, _default(self.plant.default_temp_c, 22.0), 1),
            ("ph", "pH", "", 5.0, 9.5, _default(self.plant.default_ph, 7.5), 2),
            ("recycle_ratio", "Recycle", "", 0.0, 8.0, _default(self.plant.default_recycle_ratio, 0.0), 2),
            ("organic_loading", "Org. load", "kg BOD/m3/d", 0.0, 2.0, _default(self.plant.default_organic_loading, 0.0), 3),
            ("nitrogen_loading", "N load", "g TKN/m2/d", 0.0, 5.0, _default(self.plant.default_nitrogen_loading, 0.0), 2),
            ("inf_cod_mgl", "Influent COD", "mg/L", 1.0, 2000.0, 450.0 if self.plant.slug == "phola" else 350.0, 1),
            ("inf_nh4_mgl", "Influent NH4", "mg/L", 0.1, 200.0, 45.0, 2),
            ("inf_tn_mgl", "Influent TN", "mg/L", 0.1, 250.0, 70.0, 2),
            ("inf_tp_mgl", "Influent TP", "mg/L", 0.1, 60.0, 8.0, 2),
            ("inf_pfas_ugl", "Influent PFAS", "ug/L", 0.0, 1000.0, 50.0, 3),
        ]

        for i, (key, label, unit, mn, mx, val, dec) in enumerate(defs):
            r = i // 2
            c = (i % 2) * 2
            lbl = QLabel(f"{label} {f'({unit})' if unit else ''}")
            lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:600;")
            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(val)
            spin.setFixedHeight(28)
            spin.setStyleSheet(self._spin_style())
            spin.valueChanged.connect(lambda _: self._debounce.start())
            self._inputs[key] = spin
            grid.addWidget(lbl, r, c)
            grid.addWidget(spin, r, c + 1)

        layout.addLayout(grid)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        pfas_lbl = QLabel("PFAS type")
        pfas_lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:600;")
        self._pfas_type = QComboBox()
        self._pfas_type.addItems(["short-chain", "long-chain"])
        self._pfas_type.setStyleSheet(self._combo_style())
        self._pfas_type.currentIndexChanged.connect(lambda _: self._debounce.start())
        controls.addWidget(pfas_lbl)
        controls.addWidget(self._pfas_type)

        self._bnr_mode = QComboBox()
        self._bnr_mode.addItems(BNR_MODES)
        self._bnr_mode.setStyleSheet(self._combo_style())
        self._bnr_mode.currentIndexChanged.connect(lambda _: self._debounce.start())
        if self.plant.slug != "zeekoegat":
            self._bnr_mode.setEnabled(False)
        controls.addWidget(QLabel("BNR mode"))
        controls.addWidget(self._bnr_mode, stretch=1)
        layout.addLayout(controls)

        run_btn = QPushButton("  Run Scientific Twin")
        run_btn.setIcon(qta.icon("fa6s.play", color="#ffffff"))
        run_btn.setFixedHeight(34)
        run_btn.setCursor(Qt.PointingHandCursor)
        run_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:11px; font-weight:600; padding:0 14px; }
            QPushButton:hover { background:#9b59b6; }
        """)
        run_btn.clicked.connect(self._run)
        layout.addWidget(run_btn)
        return w

    def _build_outputs(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        for i, (key, title, color) in enumerate([
            ("cod", "COD", "#2471a3"),
            ("nh4", "NH4", "#8e44ad"),
            ("tn", "TN", "#138d75"),
            ("tp", "TP", "#1e8449"),
            ("pfas", "PFAS", "#c0392b"),
            ("fm", "F:M", "#d68910"),
        ]):
            kpi_grid.addWidget(self._kpi(key, title, color), i // 3, i % 3)
        layout.addLayout(kpi_grid)

        self._eff_table = QTableWidget(5, 4)
        self._eff_table.setHorizontalHeaderLabels(["Parameter", "Influent", "Effluent", "Removal"])
        self._style_table(self._eff_table)
        self._eff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._eff_table.setFixedHeight(190)
        layout.addWidget(self._eff_table)

        self._mass_table = QTableWidget(4, 2)
        self._mass_table.setHorizontalHeaderLabels(["PFAS fate", "g/day"])
        self._style_table(self._mass_table)
        self._mass_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._mass_table.setFixedHeight(150)
        layout.addWidget(self._mass_table)

        self._confidence = QLabel("Scientific Twin")
        self._confidence.setWordWrap(True)
        self._confidence.setStyleSheet("""
            background:#f8f9fa; border:1px solid #dde1e7; border-radius:6px;
            padding:8px 10px; color:#2c3e50; font-size:10px; font-weight:600;
        """)
        layout.addWidget(self._confidence)

        self._warnings = QLabel("")
        self._warnings.setWordWrap(True)
        self._warnings.setVisible(False)
        self._warnings.setStyleSheet("""
            background:#fef9e7; border:1px solid #f9ca24; border-radius:6px;
            padding:8px 10px; color:#7d6608; font-size:10px; font-weight:600;
        """)
        layout.addWidget(self._warnings)
        return w

    def _kpi(self, key: str, title: str, color: str) -> QWidget:
        box = QWidget()
        box.setMinimumHeight(68)
        box.setStyleSheet(f"""
            QWidget {{ background:{QColor(color).lighter(190).name()};
                border:1px solid {color}; border-radius:6px; }}
            QLabel {{ border:none; background:transparent; }}
        """)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{color}; font-size:10px; font-weight:600;")
        val = QLabel("—")
        val.setAlignment(Qt.AlignCenter)
        val.setStyleSheet(f"color:{color}; font-size:17px; font-weight:800;")
        v.addWidget(t)
        v.addWidget(val)
        self._result_labels[key] = val
        return box

    def _build_unit_results_table(self) -> QTableWidget:
        self._unit_results = QTableWidget(0, 7)
        self._unit_results.setHorizontalHeaderLabels([
            "Unit", "Type", "COD", "NH4", "TN", "TP", "PFAS / note",
        ])
        self._style_table(self._unit_results)
        self._unit_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._unit_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, 6):
            self._unit_results.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._unit_results.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._unit_results.setMinimumHeight(210)
        return self._unit_results

    def _run(self) -> None:
        inputs = PlantTwinInputs(
            plant_slug=self.plant.slug,
            flow_mld=self._inputs["flow_mld"].value(),
            hrt_hours=self._inputs["hrt_hours"].value(),
            srt_days=self._inputs["srt_days"].value(),
            mlss_mgl=self._inputs["mlss_mgl"].value(),
            do_mgl=self._inputs["do_mgl"].value(),
            temp_c=self._inputs["temp_c"].value(),
            ph=self._inputs["ph"].value(),
            recycle_ratio=self._inputs["recycle_ratio"].value(),
            organic_loading=self._inputs["organic_loading"].value(),
            nitrogen_loading=self._inputs["nitrogen_loading"].value(),
            inf_cod_mgl=self._inputs["inf_cod_mgl"].value(),
            inf_nh4_mgl=self._inputs["inf_nh4_mgl"].value(),
            inf_tn_mgl=self._inputs["inf_tn_mgl"].value(),
            inf_tp_mgl=self._inputs["inf_tp_mgl"].value(),
            inf_pfas_ugl=self._inputs["inf_pfas_ugl"].value(),
            pfas_type=self._pfas_type.currentText(),
            bnr_mode=self._bnr_mode.currentText(),
            calibration_factors=self._calibration_factors,
        )
        self._update_results(inputs, run_plant_twin(inputs))

    def _update_results(self, inputs: PlantTwinInputs, outputs: PlantTwinOutputs) -> None:
        self._result_labels["cod"].setText(f"{outputs.cod_removal_pct:.1f}%")
        self._result_labels["nh4"].setText(f"{outputs.nh4_removal_pct:.1f}%")
        self._result_labels["tn"].setText(f"{outputs.tn_removal_pct:.1f}%")
        self._result_labels["tp"].setText(f"{outputs.tp_removal_pct:.1f}%")
        self._result_labels["pfas"].setText(f"{outputs.pfas_removal_pct:.2f}%")
        self._result_labels["fm"].setText(f"{outputs.fm_ratio:.3f}")

        eff_rows = [
            ("COD", f"{inputs.inf_cod_mgl:.1f} mg/L", f"{outputs.eff_cod_mgl:.2f} mg/L", f"{outputs.cod_removal_pct:.1f}%"),
            ("NH4", f"{inputs.inf_nh4_mgl:.2f} mg/L", f"{outputs.eff_nh4_mgl:.2f} mg/L", f"{outputs.nh4_removal_pct:.1f}%"),
            ("TN", f"{inputs.inf_tn_mgl:.2f} mg/L", f"{outputs.eff_tn_mgl:.2f} mg/L", f"{outputs.tn_removal_pct:.1f}%"),
            ("TP", f"{inputs.inf_tp_mgl:.2f} mg/L", f"{outputs.eff_tp_mgl:.2f} mg/L", f"{outputs.tp_removal_pct:.1f}%"),
            ("PFAS", f"{inputs.inf_pfas_ugl:.3f} ug/L", f"{outputs.eff_pfas_ugl:.3f} ug/L", f"{outputs.pfas_removal_pct:.2f}%"),
        ]
        for r, row in enumerate(eff_rows):
            for c, text in enumerate(row):
                cell = _item(text)
                if c == 3:
                    cell.setForeground(QBrush(QColor("#1e8449" if row[0] != "PFAS" and float(text.rstrip("%")) >= 60 else "#c0392b" if row[0] == "PFAS" else "#d68910")))
                self._eff_table.setItem(r, c, cell)
            self._eff_table.setRowHeight(r, 30)

        mass_rows = [
            ("PFAS in", outputs.pfas_in_g_day),
            ("To effluent", outputs.pfas_effluent_g_day),
            ("To sludge/solids", outputs.pfas_sludge_g_day),
            ("Unresolved", outputs.pfas_unresolved_g_day),
        ]
        for r, (label, value) in enumerate(mass_rows):
            self._mass_table.setItem(r, 0, _item(label, Qt.AlignLeft | Qt.AlignVCenter))
            self._mass_table.setItem(r, 1, _item(f"{value:.4f}"))
            self._mass_table.setRowHeight(r, 28)

        self._confidence.setText(
            f"{outputs.confidence_label}  |  COD load: {outputs.cod_load_kg_day:.1f} kg/day  |  "
            f"PFAS Kd: {outputs.kd_used:.3g} L/kg. PFAS removal is adsorption/solids capture, not biodegradation."
        )

        if outputs.warnings:
            self._warnings.setText("  ".join(outputs.warnings))
            self._warnings.setVisible(True)
        else:
            self._warnings.setVisible(False)

        self._unit_results.setRowCount(len(outputs.unit_results))
        for r, unit in enumerate(outputs.unit_results):
            values = [
                unit.unit_name,
                unit.unit_type,
                f"{unit.cod_mgl:.2f}",
                f"{unit.nh4_mgl:.2f}",
                f"{unit.tn_mgl:.2f}",
                f"{unit.tp_mgl:.2f}",
                f"{unit.pfas_ugl:.3f} ug/L  ·  {unit.note}",
            ]
            for c, text in enumerate(values):
                align = Qt.AlignLeft | Qt.AlignVCenter if c in (0, 6) else Qt.AlignCenter
                self._unit_results.setItem(r, c, _item(text, align))
            self._unit_results.setRowHeight(r, 32)

    def _panel(self, title: str, widget: QWidget) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background:#ffffff; border:1px solid {C_BORDER};")
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet(f"background:{C_HDR}; border:none;")
        row = QHBoxLayout(hdr)
        row.setContentsMargins(12, 0, 12, 0)
        label = QLabel(title)
        label.setStyleSheet("color:#ecf0f1; font-size:10px; font-weight:600; border:none;")
        row.addWidget(label)
        layout.addWidget(hdr)
        layout.addWidget(widget)
        return outer

    @staticmethod
    def _style_table(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:10px; alternate-background-color:#f8f9fa; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:4px 7px; }
        """)

    @staticmethod
    def _spin_style() -> str:
        return """
            QDoubleSpinBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:10px; background:#fff; color:#2c3e50; }
            QDoubleSpinBox:focus { border-color:#2980b9; }
        """

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:3px 8px; font-size:10px; background:#fff; color:#2c3e50; }
            QComboBox:disabled { color:#95a5a6; background:#f8f9fa; }
        """

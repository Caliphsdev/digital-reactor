"""
settings.py — Settings screen (index 7) for Digital Reactor.

Tabs:
  1. Data Management  — Backup / Restore / Export database
  2. Defaults         — Pre-fill values for simulation sliders (QSettings)
  3. About            — Version info and researcher details

Data Preservation Strategy
---------------------------
The database (reactor.db) lives in the project folder.
When a new version of the app is installed:
  • Schema migrations run automatically (core/migrations.py)
  • All existing rows are preserved — new columns get NULL defaults
  • This screen lets the user create a timestamped backup before any
    update, and restore a backup if anything goes wrong.
"""

import os
import shutil
import glob as pyglob
from datetime import datetime
from pathlib import Path

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QGroupBox, QFormLayout,
    QDoubleSpinBox, QCheckBox, QFileDialog, QScrollArea,
    QFrame, QSizePolicy, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSpinBox,
)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QFont, QColor

from core.database import DB_PATH, engine

# ── Styling constants ──────────────────────────────────────────────────────────
C_HDR      = "#2c3e50"
C_TEXT     = "#ecf0f1"
C_CARD_BG  = "#ffffff"
C_BG       = "#f0f3f4"
C_MUTED    = "#7f8c8d"
C_GREEN    = "#27ae60"
C_RED      = "#e74c3c"
C_BLUE     = "#2980b9"

# Maximum total backups to keep (auto + manual combined)
MAX_BACKUPS = 7


def _backup_dir() -> Path:
    """Return the folder where database backups are stored."""
    return DB_PATH.parent / "backups"


def _format_size(path: Path) -> str:
    """Return human-readable file size for a path."""
    try:
        size = path.stat().st_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 ** 2:.1f} MB"
    except OSError:
        return "?"


class SettingsScreen(QWidget):
    """Settings screen with 3 tabs: Data Management, Defaults, About."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        # ── QSettings must be created BEFORE building tabs that read from it ──
        self._qsettings = QSettings("TUT", "DigitalReactor")

        body = QWidget()
        body.setStyleSheet(f"background-color: {C_BG};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_data_tab(),     "  Data Management  ")
        self._tabs.addTab(self._build_defaults_tab(), "  Sim Defaults  ")
        self._tabs.addTab(self._build_about_tab(),    "  About  ")
        self._tabs.setStyleSheet("""
            QTabBar::tab {
                background: #dfe6e9;
                color: #2c3e50;
                padding: 8px 18px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #2c3e50;
                font-weight: bold;
            }
            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #dfe6e9;
                border-radius: 0 4px 4px 4px;
            }
        """)

        body_layout.addWidget(self._tabs)
        layout.addWidget(body, stretch=1)

        self._load_defaults()

        # Run auto-backup silently on screen load if enabled
        if self._qsettings.value("auto_backup", True, type=bool):
            self._auto_backup()

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        title = QLabel("Settings")
        font = QFont(); font.setPointSize(13); font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {C_TEXT};")
        row.addWidget(title)
        row.addStretch()
        return bar

    # ── Tab 1: Data Management ─────────────────────────────────────────────────
    def _build_data_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ── Database location card ─────────────────────────────────────────────
        loc_box = self._card("Database Location")
        loc_layout = QVBoxLayout(loc_box)

        self._db_path_label = QLabel(str(DB_PATH))
        self._db_path_label.setWordWrap(True)
        self._db_path_label.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
        loc_layout.addWidget(self._db_path_label)

        self._db_size_label = QLabel()
        self._db_size_label.setStyleSheet(f"color: {C_MUTED}; font-size: 10px;")
        loc_layout.addWidget(self._db_size_label)
        self._refresh_db_info()

        layout.addWidget(loc_box)

        # ── Backup card ────────────────────────────────────────────────────────
        backup_box = self._card("Backup Database")
        bk_layout = QVBoxLayout(backup_box)

        desc = QLabel(
            "Create a timestamped copy of reactor.db in a backups/ folder "
            "next to the database. Do this before installing a new app update."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
        bk_layout.addWidget(desc)
        bk_layout.addSpacing(8)

        btn_row = QHBoxLayout()
        self._backup_btn = QPushButton("  Backup Now")
        self._backup_btn.setIcon(qta.icon("fa6s.database", color="#ffffff"))
        self._backup_btn.setIconSize(QSize(14, 14))
        self._backup_btn.setFixedHeight(34)
        self._backup_btn.setCursor(Qt.PointingHandCursor)
        self._backup_btn.setStyleSheet(self._btn_style(C_BLUE))
        self._backup_btn.clicked.connect(self._on_backup)
        btn_row.addWidget(self._backup_btn)

        self._open_backup_folder_btn = QPushButton("  Open Backup Folder")
        self._open_backup_folder_btn.setIcon(qta.icon("fa6s.folder-open", color="#2c3e50"))
        self._open_backup_folder_btn.setIconSize(QSize(14, 14))
        self._open_backup_folder_btn.setFixedHeight(34)
        self._open_backup_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_backup_folder_btn.setStyleSheet(self._btn_style_outline())
        self._open_backup_folder_btn.clicked.connect(self._open_backup_folder)
        btn_row.addWidget(self._open_backup_folder_btn)
        btn_row.addStretch()
        bk_layout.addLayout(btn_row)
        bk_layout.addSpacing(8)

        # Auto-backup toggle
        auto_row = QHBoxLayout()
        self._auto_backup_chk = QCheckBox("Auto-backup when opening this screen")
        self._auto_backup_chk.setStyleSheet("font-size: 11px;")
        self._auto_backup_chk.toggled.connect(
            lambda v: self._qsettings.setValue("auto_backup", v)
        )
        auto_row.addWidget(self._auto_backup_chk)
        auto_row.addStretch()
        bk_layout.addLayout(auto_row)

        self._backup_status_label = QLabel("")
        self._backup_status_label.setStyleSheet("font-size: 10px;")
        bk_layout.addWidget(self._backup_status_label)

        layout.addWidget(backup_box)

        # ── Backup history ─────────────────────────────────────────────────────
        hist_box = self._card("Backup History")
        hist_layout = QVBoxLayout(hist_box)

        self._backup_table = QTableWidget(0, 3)
        self._backup_table.setHorizontalHeaderLabels(["File", "Date", "Size"])
        self._backup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._backup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._backup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._backup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._backup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._backup_table.setFixedHeight(160)
        self._backup_table.verticalHeader().setVisible(False)
        self._backup_table.setAlternatingRowColors(True)
        self._backup_table.setStyleSheet("font-size: 11px;")
        hist_layout.addWidget(self._backup_table)

        restore_row = QHBoxLayout()
        self._restore_btn = QPushButton("  Restore Selected Backup")
        self._restore_btn.setIcon(qta.icon("fa6s.rotate-left", color="#ffffff"))
        self._restore_btn.setIconSize(QSize(14, 14))
        self._restore_btn.setFixedHeight(34)
        self._restore_btn.setCursor(Qt.PointingHandCursor)
        self._restore_btn.setStyleSheet(self._btn_style("#e67e22"))
        self._restore_btn.clicked.connect(self._on_restore)
        restore_row.addWidget(self._restore_btn)
        restore_row.addStretch()
        hist_layout.addLayout(restore_row)
        layout.addWidget(hist_box)

        # ── Export card ────────────────────────────────────────────────────────
        export_box = self._card("Export All Data to Excel")
        ex_layout = QVBoxLayout(export_box)

        ex_desc = QLabel(
            "Export every table from the database into a single Excel workbook "
            "(.xlsx) — one sheet per table. Useful for thesis analysis in Excel or R."
        )
        ex_desc.setWordWrap(True)
        ex_desc.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
        ex_layout.addWidget(ex_desc)
        ex_layout.addSpacing(8)

        self._export_btn = QPushButton("  Export to Excel")
        self._export_btn.setIcon(qta.icon("fa6s.file-excel", color="#ffffff"))
        self._export_btn.setIconSize(QSize(14, 14))
        self._export_btn.setFixedHeight(34)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setStyleSheet(self._btn_style(C_GREEN))
        self._export_btn.clicked.connect(self._on_export_excel)
        ex_layout.addWidget(self._export_btn)
        layout.addWidget(export_box)

        layout.addStretch()
        scroll.setWidget(page)
        self._refresh_backup_list()
        return scroll

    # ── Tab 2: Simulation Defaults ─────────────────────────────────────────────
    def _build_defaults_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        desc_box = self._card("Simulation Pre-fill Defaults")
        desc_layout = QVBoxLayout(desc_box)
        desc = QLabel(
            "These values pre-fill the Simulation screen sliders when the app starts. "
            "Set them to your reactor's typical operating conditions."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
        desc_layout.addWidget(desc)
        desc_layout.addSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        # Default fields: (QSettings key, label, min, max, decimals, default)
        self._default_spins: dict[str, QDoubleSpinBox] = {}
        defaults_spec = [
            ("def_flow",     "Flow rate (mL/h)",      200.0, 450.0, 0, 320.0),
            ("def_do",       "DO (mg/L)",              0.0,   5.0,  1, 1.5),
            ("def_srt",      "SRT (days)",             5.0,  60.0,  0, 30.0),
            ("def_ras",      "RAS ratio",              0.5,   3.0,  1, 1.0),
            ("def_arecycle", "a-recycle ratio",        1.0,   8.0,  1, 4.0),
            ("def_temp",     "Temperature (°C)",      15.0,  35.0,  1, 22.0),
            ("def_ph",       "pH",                    5.0,   10.0,  1, 7.5),
            ("def_mlss",     "MLSS (mg/L)",          500.0,8000.0,  0,3000.0),
            ("def_cod",      "Influent COD (mg/L)",    0.0,2000.0,  0, 300.0),
            ("def_nh4",      "Influent NH4 (mg/L)",    0.0, 200.0,  1, 40.0),
            ("def_tp",       "Influent TP (mg/L)",     0.0,  50.0,  1, 6.0),
            ("def_pfas",     "Influent PFAS (µg/L)",   0.0,1000.0,  1, 50.0),
        ]
        for key, label, mn, mx, dec, default_val in defaults_spec:
            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(self._qsettings.value(key, default_val, type=float))
            spin.setFixedHeight(28)
            spin.setFixedWidth(120)
            spin.valueChanged.connect(lambda v, k=key: self._qsettings.setValue(k, v))
            self._default_spins[key] = spin
            form.addRow(QLabel(label), spin)

        desc_layout.addLayout(form)
        desc_layout.addSpacing(12)

        reset_btn = QPushButton("Reset to Factory Defaults")
        reset_btn.setFixedHeight(30)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(self._btn_style_outline())
        reset_btn.clicked.connect(self._reset_defaults)
        desc_layout.addWidget(reset_btn)
        layout.addWidget(desc_box)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ── Tab 3: About ───────────────────────────────────────────────────────────
    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: #ffffff;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("Digital Reactor")
        f = QFont(); f.setPointSize(18); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {C_HDR};")
        layout.addWidget(title)

        version = QLabel("Version 1.0")
        version.setStyleSheet(f"color: {C_MUTED}; font-size: 12px;")
        layout.addWidget(version)

        layout.addSpacing(16)
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: #dfe6e9;")
        layout.addWidget(line)
        layout.addSpacing(16)

        for label, value in [
            ("Researcher",  "Mahlatse Mapula Sekhula-Mojela"),
            ("Study period","2026 – 2028"),
            ("Focus",       "PFAS / Contaminants of Emerging Concern (CECs)"),
            ("Reactor type","Lab-scale Activated Sludge (OECD 303A)"),
            ("Developer",   "Caliphs Zvinowanda"),
            ("Contact",     "+27 65 235 7607"),
            ("Database",    str(DB_PATH)),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(120)
            lbl.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val = QLabel(value)
            val.setWordWrap(True)
            val.setStyleSheet("color: #2c3e50; font-size: 11px;")
            row.addWidget(lbl)
            row.addSpacing(10)
            row.addWidget(val, stretch=1)
            layout.addLayout(row)

        layout.addStretch()
        return page

    # ── Backup / Restore logic ─────────────────────────────────────────────────
    def _on_backup(self) -> None:
        """Create a timestamped backup of reactor.db."""
        try:
            dest = self._do_backup()
            self._backup_status_label.setText(
                f"✓ Backed up to: {dest.name}"
            )
            self._backup_status_label.setStyleSheet(f"color: {C_GREEN}; font-size: 10px;")
            self._refresh_backup_list()
            self._refresh_db_info()
        except Exception as exc:
            self._backup_status_label.setText(f"✗ Backup failed: {exc}")
            self._backup_status_label.setStyleSheet(f"color: {C_RED}; font-size: 10px;")

    def _do_backup(self) -> Path:
        """Internal: copy reactor.db to backups/ with timestamp filename."""
        bdir = _backup_dir()
        bdir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest = bdir / f"reactor_backup_{ts}.db"
        shutil.copy2(str(DB_PATH), str(dest))
        # Prune oldest backups — keep only the most recent MAX_BACKUPS total
        existing = sorted(bdir.glob("reactor_backup_*.db"))
        while len(existing) > MAX_BACKUPS:
            existing.pop(0).unlink()
            existing = sorted(bdir.glob("reactor_backup_*.db"))
        return dest

    def _auto_backup(self) -> None:
        """
        Silent auto-backup — at most once per calendar day.

        Checks whether any backup already exists for today before creating
        a new one.  This prevents accumulation when the user visits Settings
        multiple times in the same session.
        """
        try:
            bdir = _backup_dir()
            today = datetime.now().strftime("%Y-%m-%d")
            if bdir.exists():
                # Already backed up today — skip silently
                if any(bdir.glob(f"reactor_backup_{today}_*.db")):
                    return
            self._do_backup()
        except Exception:
            pass   # silent — never alarm the user for an auto-backup failure

    def _on_restore(self) -> None:
        """Restore the selected backup over the current reactor.db."""
        row = self._backup_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a Backup", "Select a backup file from the list first.")
            return

        backup_name = self._backup_table.item(row, 0).text()
        backup_path = _backup_dir() / backup_name

        confirm = QMessageBox.warning(
            self,
            "Restore Backup",
            f"This will OVERWRITE the current database with:\n\n  {backup_name}\n\n"
            "All data entered after this backup was created will be lost.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            # Close all SQLAlchemy connections before file copy
            engine.dispose()
            shutil.copy2(str(backup_path), str(DB_PATH))
            QMessageBox.information(
                self, "Restored",
                f"Database restored from {backup_name}.\n\nPlease restart the application."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))

    def _open_backup_folder(self) -> None:
        """Open the backups folder in Windows Explorer."""
        bdir = _backup_dir()
        bdir.mkdir(exist_ok=True)
        import subprocess
        subprocess.Popen(f'explorer "{bdir}"')

    def _refresh_backup_list(self) -> None:
        """Reload the backup history table from the backups/ folder."""
        self._backup_table.setRowCount(0)
        bdir = _backup_dir()
        if not bdir.exists():
            return
        files = sorted(bdir.glob("reactor_backup_*.db"), reverse=True)
        for f in files:
            row = self._backup_table.rowCount()
            self._backup_table.insertRow(row)
            self._backup_table.setItem(row, 0, QTableWidgetItem(f.name))
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self._backup_table.setItem(row, 1, QTableWidgetItem(mtime))
            self._backup_table.setItem(row, 2, QTableWidgetItem(_format_size(f)))

    def _refresh_db_info(self) -> None:
        if DB_PATH.exists():
            self._db_size_label.setText(f"Size: {_format_size(DB_PATH)}")

    # ── Excel export ───────────────────────────────────────────────────────────
    def _on_export_excel(self) -> None:
        """Export all database tables to a single Excel workbook."""
        try:
            import pandas as pd
            import openpyxl  # noqa — ensure installed
        except ImportError:
            QMessageBox.critical(self, "Missing Library",
                "pandas and openpyxl are required for Excel export.\n"
                "Run: pip install pandas openpyxl")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", "reactor_data_export.xlsx",
            "Excel Workbook (*.xlsx)"
        )
        if not path:
            return

        try:
            tables = [
                "experiments", "daily_readings", "flow_readings",
                "cec_readings", "mass_balance_results", "simulation_runs",
                "daspoort_monitoring", "sludge_characterization",
            ]
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for table in tables:
                    try:
                        df = pd.read_sql_table(table, engine)
                        df.to_excel(writer, sheet_name=table[:31], index=False)
                    except Exception:
                        pass  # table may not exist yet

            QMessageBox.information(self, "Export Complete",
                f"Data exported successfully to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    # ── Defaults helpers ───────────────────────────────────────────────────────
    def _load_defaults(self) -> None:
        """Sync auto-backup checkbox from QSettings."""
        auto = self._qsettings.value("auto_backup", True, type=bool)
        self._auto_backup_chk.setChecked(auto)

    def _reset_defaults(self) -> None:
        """Reset all simulation defaults back to factory values."""
        factory = {
            "def_flow": 320.0, "def_do": 1.5, "def_srt": 30.0,
            "def_ras": 1.0, "def_arecycle": 4.0, "def_temp": 22.0,
            "def_ph": 7.5, "def_mlss": 3000.0, "def_cod": 300.0,
            "def_nh4": 40.0, "def_tp": 6.0, "def_pfas": 50.0,
        }
        for key, val in factory.items():
            self._default_spins[key].setValue(val)
            self._qsettings.setValue(key, val)

    # ── UI helpers ─────────────────────────────────────────────────────────────
    def _card(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet("""
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                margin-top: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 11px;
                color: #2c3e50;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        return box

    def _btn_style(self, color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 16px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {color}cc; }}
        """

    def _btn_style_outline(self) -> str:
        return """
            QPushButton {
                background-color: transparent;
                color: #2c3e50;
                border: 1px solid #b2bec3;
                border-radius: 4px;
                padding: 0 14px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #dfe6e9; }
        """

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_backup_list()
        self._refresh_db_info()

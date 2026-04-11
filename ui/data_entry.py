"""
data_entry.py — Daily measurement input screen (Step 5).

Layout:
    ┌─── Header: title · date picker · Save button ───────────────────┐
    ├─── Active experiment info strip ────────────────────────────────┤
    ├─── Zone tabs (Anaerobic | Anoxic | Aerobic | Effluent) ─────────┤
    │    9 fields per zone — highlighted red if outside normal range  │
    ├─── Flow readings section ───────────────────────────────────────┤
    ├─── Last 7 days history table ───────────────────────────────────┘

Rules:
  • Requires an active experiment — shows a warning if none is set.
  • Loading a date that already has readings pre-fills the form (edit mode).
  • Values outside the normal operating range show a red border + tooltip.
  • Save writes DailyReading rows (one per zone) + one FlowReading row.
  • History table cell backgrounds mirror the range-flag colours.
"""

from datetime import date as dt_date, timedelta

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QTextEdit, QLineEdit,
    QPushButton, QDateEdit, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QSizePolicy, QScrollArea, QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QFont, QColor, QBrush

from core.database import get_session
from core.models import Experiment, DailyReading, FlowReading
from ui.theme import dark_date_edit_style


# ── Zone and field definitions ─────────────────────────────────────────────────
ZONES = ["primary_settling", "aeration", "clarifier", "effluent"]

ZONE_LABELS = {
    "primary_settling": "Primary Settling",
    "aeration":         "Aeration Tank",
    "clarifier":        "Clarifier",
    "effluent":         "Effluent",
}

ZONE_COLORS = {
    "primary_settling": "#795548",   # earthy brown — settling
    "aeration":         "#1e8449",   # green — biological
    "clarifier":        "#717d7e",   # grey — clarification
    "effluent":         "#2e86c1",   # blue — treated water
}

# (db_field, display_label, unit, min, max, decimals)
ZONE_FIELDS = [
    ("do_mgl",        "Dissolved Oxygen",  "mg/L",    0.0,   20.0,  2),
    ("ph",            "pH",                "",         0.0,   14.0,  2),
    ("temperature_c", "Temperature",       "°C",       0.0,   50.0,  1),
    ("cod_mgl",       "COD",               "mg/L",    0.0, 5000.0,   1),
    ("nh4_mgl",       "NH₄-N",             "mg/L",    0.0,  500.0,   2),
    ("no3_mgl",       "NO₃-N",             "mg/L",    0.0,  500.0,   2),
    ("so4_mgl",       "SO₄",               "mg/L",    0.0, 2000.0,   1),
    ("po4_mgl",       "PO₄-P",             "mg/L",    0.0,  200.0,   2),
    ("mlss_mgl",      "MLSS",              "mg/L",    0.0,20000.0,    0),
]

# Normal operating ranges per zone — values outside trigger a red highlight
RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "primary_settling": {
        "do_mgl":        (0.0,    1.0),   # low/near-zero O₂ in settling tank
        "ph":            (6.5,    8.5),
        "temperature_c": (15.0,  30.0),
        "cod_mgl":       (50.0, 3000.0),
        "nh4_mgl":       (0.0,  200.0),
        "no3_mgl":       (0.0,   50.0),
        "so4_mgl":       (0.0,  800.0),
        "po4_mgl":       (0.0,   50.0),
        "mlss_mgl":      (50.0,  500.0),  # low — settling not biological
    },
    "aeration": {
        "do_mgl":        (1.0,    4.0),   # critical — target 1–3 mg/L
        "ph":            (6.5,    8.0),
        "temperature_c": (18.0,  28.0),
        "cod_mgl":       (5.0,  500.0),
        "nh4_mgl":       (0.0,   50.0),
        "no3_mgl":       (0.0,  100.0),
        "so4_mgl":       (0.0,  800.0),
        "po4_mgl":       (0.0,   30.0),
        "mlss_mgl":    (1000.0, 5000.0),
    },
    "clarifier": {
        "do_mgl":        (0.0,    2.0),
        "ph":            (6.5,    8.5),
        "temperature_c": (15.0,  30.0),
        "cod_mgl":       (5.0,  200.0),
        "nh4_mgl":       (0.0,   30.0),
        "no3_mgl":       (0.0,   50.0),
        "so4_mgl":       (0.0,  800.0),
        "po4_mgl":       (0.0,   20.0),
        "mlss_mgl":      (50.0, 1000.0),  # low — post-settling supernatant
    },
    "effluent": {
        "do_mgl":        (0.0,   10.0),
        "ph":            (6.0,    9.0),
        "temperature_c": (15.0,  30.0),
        "cod_mgl":       (0.0,  250.0),
        "nh4_mgl":       (0.0,   50.0),
        "no3_mgl":       (0.0,   50.0),
        "so4_mgl":       (0.0,  800.0),
        "po4_mgl":       (0.0,   20.0),
        "mlss_mgl":      (0.0,  100.0),
    },
}

# ── Advanced (Tier-1) measurement fields  ─────────────────────────────────────
# These appear in a collapsible "Advanced Measurements" section per zone tab.
# Fields match the new columns added to daily_readings via migration v1.
# (db_field, display_label, unit, min, max, decimals)
ADVANCED_ZONE_FIELDS = [
    ("vss_mgl",        "VSS",             "mg/L",    0.0, 20000.0, 0),
    ("tss_mgl",        "TSS",             "mg/L",    0.0, 20000.0, 0),
    ("orp_mv",         "ORP",             "mV",   -500.0,   500.0, 0),
    ("alkalinity_mgl", "Alkalinity",      "mg/L",    0.0,  2000.0, 1),
    ("turbidity_ntu",  "Turbidity",       "NTU",     0.0,  1000.0, 1),
    ("our_mgl_h",      "OUR",             "mg/L/h",  0.0,   100.0, 2),
    ("bod_mgl",        "BOD₅",            "mg/L",    0.0,  5000.0, 1),
    ("tn_mgl",         "Total-N",         "mg/L",    0.0,   500.0, 1),
    ("tp_mgl",         "Total-P",         "mg/L",    0.0,   200.0, 2),
]

# Typical operating ranges for advanced parameters per zone.
# ORP ranges guide redox interpretation:
#   primary_settling: variable  |  aeration: +50 to +200 mV (aerobic)
ADVANCED_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "primary_settling": {
        "orp_mv":         (-200.0,  50.0),
        "alkalinity_mgl": (50.0,   500.0),
        "vss_mgl":        (10.0,   500.0),
        "tss_mgl":        (20.0,   600.0),
    },
    "aeration": {
        "orp_mv":         (50.0,   250.0),  # aerobic conditions
        "our_mgl_h":      (5.0,    60.0),
        "alkalinity_mgl": (50.0,   300.0),
        "vss_mgl":        (500.0, 6000.0),
        "tss_mgl":        (500.0, 7000.0),
    },
    "clarifier": {
        "orp_mv":         (-50.0,  100.0),
        "alkalinity_mgl": (50.0,   400.0),
        "vss_mgl":        (10.0,  1000.0),
        "tss_mgl":        (10.0,  1200.0),
    },
    "effluent": {
        "turbidity_ntu":  (0.0,    10.0),
        "tss_mgl":        (0.0,    30.0),
        "tp_mgl":         (0.0,    10.0),
        "tn_mgl":         (0.0,    20.0),
    },
}

# Colour tokens
C_OK      = "#ffffff"
C_ERR_BG  = "#fdecea"
C_ERR_BD  = "#e74c3c"
C_HDR     = "#2c3e50"
HISTORY_ERR = QColor("#fadbd8")


class DataEntryScreen(QWidget):
    """Daily measurement input screen with zone tabs, flow section, and history."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # zone → field → QDoubleSpinBox  (core measurements)
        self._zone_spins: dict[str, dict[str, QDoubleSpinBox]] = {}
        # zone → field → QDoubleSpinBox  (advanced measurements)
        self._adv_zone_spins: dict[str, dict[str, QDoubleSpinBox]] = {}
        # zone → notes QTextEdit
        self._zone_notes: dict[str, QTextEdit] = {}
        # flow field → QDoubleSpinBox
        self._flow_spins: dict[str, QDoubleSpinBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_info_strip())

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: #f5f6fa;")

        form_body = QWidget()
        form_body.setStyleSheet("background: #f5f6fa;")
        body_layout = QVBoxLayout(form_body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(12)

        body_layout.addWidget(self._build_zone_tabs())
        body_layout.addWidget(self._build_flow_section())
        body_layout.addWidget(self._build_history_section())

        scroll.setWidget(form_body)
        root.addWidget(scroll, stretch=1)

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        title = QLabel("Daily Log")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        # Date picker
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
        self._date_edit.dateChanged.connect(self._on_date_changed)
        row.addWidget(self._date_edit)

        # Save button
        self._save_btn = QPushButton("  Save Readings")
        self._save_btn.setIcon(qta.icon("fa6s.floppy-disk", color="#ffffff"))
        self._save_btn.setIconSize(QSize(13, 13))
        self._save_btn.setFixedHeight(34)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: #fff; border: none;
                border-radius: 4px; font-size: 11px; font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #1e8449; }
        """)
        self._save_btn.clicked.connect(self._on_save)
        row.addWidget(self._save_btn)

        return bar

    # ── Info strip ─────────────────────────────────────────────────────────────
    def _build_info_strip(self) -> QWidget:
        """Shows active experiment name, or a warning if none is set."""
        strip = QWidget()
        strip.setFixedHeight(30)
        strip.setStyleSheet("background: #dfe6e9; border-bottom: 1px solid #b2bec3;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 0, 14, 0)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa6s.flask", color="#636e72").pixmap(QSize(13, 13)))
        row.addWidget(icon_lbl)
        row.addSpacing(5)

        self._info_label = QLabel("Loading…")
        self._info_label.setStyleSheet("color: #636e72; font-size: 11px;")
        row.addWidget(self._info_label)
        row.addStretch()

        # Message shown after save
        self._save_msg = QLabel("")
        self._save_msg.setStyleSheet("font-size: 11px;")
        row.addWidget(self._save_msg)

        return strip

    # ── Zone tabs ──────────────────────────────────────────────────────────────
    def _build_zone_tabs(self) -> QWidget:
        """
        Card containing a QTabWidget with one tab per reactor zone.
        Each tab has a 2-column grid of parameter inputs.
        """
        card = self._make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 16)
        card_layout.setSpacing(8)

        section_title = QLabel("Zone Measurements")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        section_title.setFont(f)
        section_title.setStyleSheet("color: #2c3e50;")
        card_layout.addWidget(section_title)
        card_layout.addWidget(self._make_divider())

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dde1e7; border-radius: 4px;
                background: #ffffff; margin-top: -1px;
            }
            QTabBar::tab {
                background: #ecf0f1; color: #636e72;
                padding: 8px 20px; border: 1px solid #dde1e7;
                border-bottom: none; border-radius: 4px 4px 0 0;
                font-size: 11px; font-weight: 600; margin-right: 2px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #2c3e50; }
            QTabBar::tab:hover    { background: #d5eaf9; }
        """)

        for zone in ZONES:
            tab = self._build_zone_tab(zone)
            color = ZONE_COLORS[zone]
            self._tabs.addTab(tab, ZONE_LABELS[zone])
            # Colour the tab text by zone
            idx = self._tabs.count() - 1
            self._tabs.tabBar().setTabTextColor(idx, QColor(color))

        card_layout.addWidget(self._tabs)
        return card

    def _build_zone_tab(self, zone: str) -> QWidget:
        """
        One zone tab: 2-column grid of QDoubleSpinBox inputs + a notes field.
        Inputs are validated live against RANGES[zone] — red border if out of range.
        """
        widget = QWidget()
        widget.setStyleSheet("background: #ffffff;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self._zone_spins[zone] = {}
        grid = QGridLayout()
        grid.setSpacing(10)

        for i, (field, label, unit, mn, mx, dec) in enumerate(ZONE_FIELDS):
            row_g, col_g = divmod(i, 2)     # 2 columns

            # Label
            lbl = QLabel(label + (":" if unit else ":"))
            lbl.setStyleSheet("color: #2c3e50; font-size: 11px; font-weight: 600;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Spinbox
            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(0.0)
            spin.setSpecialValueText("—")      # 0 shows as "—" meaning not entered
            spin.setFixedHeight(30)
            spin.setSuffix(f"  {unit}" if unit else "")
            spin.setStyleSheet(self._spin_style_ok())
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Live range validation
            rng = RANGES[zone].get(field)
            if rng:
                spin.valueChanged.connect(
                    lambda val, s=spin, r=rng, f=field, z=zone: self._validate_spin(s, val, r)
                )
                lo, hi = rng
                spin.setToolTip(f"Normal range: {lo} – {hi}")

            self._zone_spins[zone][field] = spin

            # Unit label (right of spinbox)
            col_offset = col_g * 3
            grid.addWidget(lbl,  row_g, col_offset,     1, 1)
            grid.addWidget(spin, row_g, col_offset + 1, 1, 1)

        # Make columns expand equally
        for c in (0, 1, 3, 4):
            grid.setColumnStretch(c, 0 if c in (0, 3) else 1)
        grid.setColumnMinimumWidth(2, 20)   # gap between the two columns

        layout.addLayout(grid)

        # Notes for this zone
        notes_lbl = QLabel("Notes for this zone:")
        notes_lbl.setStyleSheet("color: #636e72; font-size: 10px;")
        layout.addWidget(notes_lbl)

        notes = QTextEdit()
        notes.setFixedHeight(48)
        notes.setPlaceholderText("Optional observations for this zone…")
        notes.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ced4da; border-radius: 4px;
                padding: 4px 8px; font-size: 11px; background: #fff;
            }
            QTextEdit:focus { border-color: #2980b9; }
        """)
        self._zone_notes[zone] = notes
        layout.addWidget(notes)

        # ── Collapsible Advanced Measurements section ──────────────────────────
        layout.addSpacing(4)
        adv_toggle = QPushButton("▶  Advanced Measurements  (VSS · TSS · ORP · Alkalinity · OUR · BOD · TN · TP · Turbidity)")
        adv_toggle.setCheckable(True)
        adv_toggle.setChecked(False)
        adv_toggle.setCursor(Qt.PointingHandCursor)
        adv_toggle.setStyleSheet("""
            QPushButton {
                background: #f0f3f4; color: #2c3e50; border: 1px solid #dde1e7;
                border-radius: 4px; text-align: left; padding: 6px 10px;
                font-size: 10px; font-weight: 600;
            }
            QPushButton:checked { background: #d5eaf9; border-color: #2980b9; }
            QPushButton:hover { background: #d5eaf9; }
        """)

        adv_widget = QWidget()
        adv_widget.setVisible(False)
        adv_widget.setStyleSheet("background: #fafbfc;")
        adv_layout = QVBoxLayout(adv_widget)
        adv_layout.setContentsMargins(0, 8, 0, 4)
        adv_layout.setSpacing(8)

        adv_info = QLabel(
            "These parameters are optional — enter only when lab analysis is available. "
            "ORP verifies redox zone conditions; OUR (aerobic only) indicates biological activity."
        )
        adv_info.setWordWrap(True)
        adv_info.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 0 2px;")
        adv_layout.addWidget(adv_info)

        self._adv_zone_spins[zone] = {}
        adv_grid = QGridLayout()
        adv_grid.setSpacing(8)

        for i, (field, label, unit, mn, mx, dec) in enumerate(ADVANCED_ZONE_FIELDS):
            row_g, col_g = divmod(i, 3)    # 3 columns for compact layout
            col_offset = col_g * 2

            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: #2c3e50; font-size: 10px; font-weight: 600;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(mn)
            spin.setSpecialValueText("—")
            spin.setFixedHeight(28)
            spin.setSuffix(f"  {unit}" if unit else "")
            spin.setStyleSheet(self._spin_style_ok())
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setStyleSheet("""
                QDoubleSpinBox {
                    border: 1px solid #ced4da; border-radius: 4px;
                    padding: 2px 6px; font-size: 10px;
                    background: #ffffff; color: #2c3e50;
                }
                QDoubleSpinBox:focus { border-color: #2980b9; }
            """)

            rng = ADVANCED_RANGES.get(zone, {}).get(field)
            if rng:
                spin.valueChanged.connect(
                    lambda val, s=spin, r=rng: self._validate_spin(s, val, r)
                )
                lo, hi = rng
                spin.setToolTip(f"Normal range: {lo} – {hi}")
            else:
                spin.setToolTip(f"{label} — no fixed range for this zone")

            self._adv_zone_spins[zone][field] = spin
            adv_grid.addWidget(lbl,  row_g, col_offset,     1, 1)
            adv_grid.addWidget(spin, row_g, col_offset + 1, 1, 1)

        for c in range(6):
            adv_grid.setColumnStretch(c, 0 if c % 2 == 0 else 1)

        adv_layout.addLayout(adv_grid)
        layout.addWidget(adv_toggle)
        layout.addWidget(adv_widget)

        def _toggle_adv(checked: bool, w=adv_widget, btn=adv_toggle) -> None:
            w.setVisible(checked)
            btn.setText(
                ("▼" if checked else "▶") +
                "  Advanced Measurements  (VSS · TSS · ORP · Alkalinity · OUR · BOD · TN · TP · Turbidity)"
            )
        adv_toggle.toggled.connect(_toggle_adv)

        return widget

    # ── Flow section ───────────────────────────────────────────────────────────
    def _build_flow_section(self) -> QWidget:
        """
        Card with flow and recycle ratio inputs.
        Default values pre-filled from OECD 303A operating conditions.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Flow Readings")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)
        layout.addWidget(self._make_divider())

        # (db_field, label, unit, default, min, max, decimals)
        flow_fields = [
            ("q_in_mlh",      "Influent flow (Q_in)",       "mL/h",  320.0, 0.0, 2000.0, 1),
            ("q_was_mlh",     "Waste sludge (Q_WAS)",       "mL/h",    0.0, 0.0, 1000.0, 1),
            ("q_psludge_mlh", "Primary sludge (Q_Psludge)", "mL/h",    0.0, 0.0, 1000.0, 1),
            ("ras_ratio",     "RAS ratio",                  "",        1.0, 0.0,   10.0, 2),
        ]

        grid = QGridLayout()
        grid.setSpacing(10)

        for col, (field, label, unit, default, mn, mx, dec) in enumerate(flow_fields):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: #2c3e50; font-size: 11px; font-weight: 600;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(default)
            spin.setFixedHeight(30)
            spin.setSuffix(f"  {unit}" if unit else "")
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setStyleSheet(self._spin_style_ok())
            self._flow_spins[field] = spin

            grid.addWidget(lbl,  0, col * 2)
            grid.addWidget(spin, 1, col * 2)

        for c in range(len(flow_fields) * 2):
            grid.setColumnStretch(c, 0 if c % 2 == 0 else 1)

        layout.addLayout(grid)

        # Flow notes
        fn_lbl = QLabel("Notes:")
        fn_lbl.setStyleSheet("color: #636e72; font-size: 10px;")
        layout.addWidget(fn_lbl)
        self._flow_notes = QTextEdit()
        self._flow_notes.setFixedHeight(44)
        self._flow_notes.setPlaceholderText("Optional flow observations…")
        self._flow_notes.setStyleSheet("""
            QTextEdit { border: 1px solid #ced4da; border-radius: 4px;
                        padding: 4px 8px; font-size: 11px; background: #fff; }
            QTextEdit:focus { border-color: #2980b9; }
        """)
        layout.addWidget(self._flow_notes)

        return card

    # ── History table ──────────────────────────────────────────────────────────
    def _build_history_section(self) -> QWidget:
        """
        Card with a table showing the last 7 days of zone readings.
        Out-of-range cells are highlighted in light red.
        """
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)

        row_hdr = QHBoxLayout()
        title = QLabel("Last 7 Days")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #2c3e50;")
        row_hdr.addWidget(title)
        row_hdr.addStretch()

        legend = QLabel("  ■  Outside normal range")
        legend.setStyleSheet(f"color: {C_ERR_BD}; font-size: 10px;")
        row_hdr.addWidget(legend)
        layout.addLayout(row_hdr)
        layout.addWidget(self._make_divider())

        cols = ["Date", "Zone", "DO\nmg/L", "pH", "Temp\n°C",
                "COD\nmg/L", "NH₄\nmg/L", "NO₃\nmg/L",
                "SO₄\nmg/L", "PO₄\nmg/L", "MLSS\nmg/L"]

        self._history_table = QTableWidget(0, len(cols))
        self._history_table.setHorizontalHeaderLabels(cols)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, len(cols)):
            self._history_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setShowGrid(False)
        self._history_table.setFixedHeight(240)
        self._history_table.setStyleSheet("""
            QTableWidget {
                background: #ffffff; border: 1px solid #dde1e7;
                border-radius: 6px; font-size: 11px;
                alternate-background-color: #f8f9fa;
            }
            QHeaderView::section {
                background: #2c3e50; color: #ecf0f1;
                font-weight: bold; font-size: 10px;
                padding: 6px 6px; border: none;
            }
            QTableWidget::item { padding: 4px 8px; }
        """)
        layout.addWidget(self._history_table)

        return card

    # ── Save logic ─────────────────────────────────────────────────────────────
    def _on_save(self) -> None:
        """
        Validate that an active experiment exists, then upsert DailyReading
        rows for all four zones and one FlowReading for the selected date.
        Upsert = update existing row if found, else insert new one.
        """
        active_exp = self._get_active_experiment()
        if active_exp is None:
            QMessageBox.warning(
                self, "No Active Experiment",
                "Please go to Experiments and set one as active before entering data.",
            )
            return

        qd = self._date_edit.date()
        reading_date = dt_date(qd.year(), qd.month(), qd.day())

        try:
            with get_session() as session:
                # ── Zone readings ──────────────────────────────────────────────
                for zone in ZONES:
                    spins = self._zone_spins[zone]
                    notes = self._zone_notes[zone].toPlainText().strip() or None

                    # Skip zone if all values are at their minimum (0 / special)
                    # — user did not enter anything for this zone today
                    values = {f: (spins[f].value() if spins[f].value() > spins[f].minimum()
                                  else None)
                              for f, *_ in ZONE_FIELDS}
                    if all(v is None for v in values.values()) and notes is None:
                        continue

                    # Check for existing record (upsert)
                    existing = (
                        session.query(DailyReading)
                        .filter_by(
                            experiment_id=active_exp["id"],
                            reading_date=reading_date,
                            zone=zone,
                        )
                        .first()
                    )
                    if existing:
                        row = existing
                    else:
                        row = DailyReading(
                            experiment_id=active_exp["id"],
                            reading_date=reading_date,
                            zone=zone,
                        )
                        session.add(row)

                    row.do_mgl        = values["do_mgl"]
                    row.ph            = values["ph"]
                    row.temperature_c = values["temperature_c"]
                    row.cod_mgl       = values["cod_mgl"]
                    row.nh4_mgl       = values["nh4_mgl"]
                    row.no3_mgl       = values["no3_mgl"]
                    row.so4_mgl       = values["so4_mgl"]
                    row.po4_mgl       = values["po4_mgl"]
                    row.mlss_mgl      = values["mlss_mgl"]
                    row.notes         = notes

                    # Advanced parameters (save only if the user opened the section)
                    adv_spins = self._adv_zone_spins.get(zone, {})
                    for field, *_ in ADVANCED_ZONE_FIELDS:
                        spin = adv_spins.get(field)
                        if spin:
                            val = spin.value() if spin.value() > spin.minimum() else None
                            setattr(row, field, val)

                # ── Flow reading ───────────────────────────────────────────────
                existing_flow = (
                    session.query(FlowReading)
                    .filter_by(
                        experiment_id=active_exp["id"],
                        reading_date=reading_date,
                    )
                    .first()
                )
                flow = existing_flow or FlowReading(
                    experiment_id=active_exp["id"],
                    reading_date=reading_date,
                )
                if not existing_flow:
                    session.add(flow)

                flow.q_in_mlh      = self._flow_spins["q_in_mlh"].value()
                flow.q_was_mlh     = self._flow_spins["q_was_mlh"].value()
                flow.q_psludge_mlh = self._flow_spins["q_psludge_mlh"].value()
                flow.ras_ratio     = self._flow_spins["ras_ratio"].value()
                flow.notes         = self._flow_notes.toPlainText().strip() or None

        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save readings:\n\n{exc}")
            return

        self._save_msg.setText("  Saved successfully.")
        self._save_msg.setStyleSheet("font-size: 11px; color: #27ae60;")
        self._refresh_history()

    # ── Date change — pre-fill form with existing data ────────────────────────
    def _on_date_changed(self, qdate: QDate) -> None:
        """When the user picks a different date, load existing readings into the form."""
        self._save_msg.setText("")
        active_exp = self._get_active_experiment()
        if active_exp is None:
            return

        reading_date = dt_date(qdate.year(), qdate.month(), qdate.day())

        try:
            with get_session() as session:
                rows = (
                    session.query(DailyReading)
                    .filter_by(experiment_id=active_exp["id"], reading_date=reading_date)
                    .all()
                )
                zone_data = {r.zone: r for r in rows}

                flow_row = (
                    session.query(FlowReading)
                    .filter_by(experiment_id=active_exp["id"], reading_date=reading_date)
                    .first()
                )

            # Fill zone tabs
            for zone in ZONES:
                spins = self._zone_spins[zone]
                r = zone_data.get(zone)
                for field, *_ in ZONE_FIELDS:
                    val = getattr(r, field, None) if r else None
                    spin = spins[field]
                    spin.blockSignals(True)
                    spin.setValue(val if val is not None else spin.minimum())
                    spin.blockSignals(False)
                    # Re-run validation after loading
                    rng = RANGES[zone].get(field)
                    if rng:
                        self._validate_spin(spin, spin.value(), rng)
                self._zone_notes[zone].setPlainText(r.notes or "" if r else "")

                # Load advanced fields (silently — columns may be None on old rows)
                adv_spins = self._adv_zone_spins.get(zone, {})
                for field, *_ in ADVANCED_ZONE_FIELDS:
                    spin = adv_spins.get(field)
                    if spin and r:
                        val = getattr(r, field, None)
                        spin.blockSignals(True)
                        spin.setValue(val if val is not None else spin.minimum())
                        spin.blockSignals(False)

            # Fill flow section
            for field in self._flow_spins:
                val = getattr(flow_row, field, None) if flow_row else None
                self._flow_spins[field].setValue(
                    val if val is not None else self._flow_spins[field].minimum()
                )
            self._flow_notes.setPlainText(flow_row.notes or "" if flow_row else "")

        except Exception:
            pass   # silently skip pre-fill errors

    # ── History table ──────────────────────────────────────────────────────────
    def _refresh_history(self) -> None:
        """
        Load zone readings for the last 7 days from the active experiment
        and populate the history table. Out-of-range cells get a red background.
        """
        active_exp = self._get_active_experiment()
        self._history_table.setRowCount(0)
        if active_exp is None:
            return

        today = dt_date.today()
        cutoff = today - timedelta(days=6)

        try:
            with get_session() as session:
                rows = (
                    session.query(DailyReading)
                    .filter(
                        DailyReading.experiment_id == active_exp["id"],
                        DailyReading.reading_date  >= cutoff,
                    )
                    .order_by(DailyReading.reading_date.desc(), DailyReading.zone)
                    .all()
                )
                records = [
                    {
                        "date":  str(r.reading_date),
                        "zone":  r.zone,
                        "do":    r.do_mgl,
                        "ph":    r.ph,
                        "temp":  r.temperature_c,
                        "cod":   r.cod_mgl,
                        "nh4":   r.nh4_mgl,
                        "no3":   r.no3_mgl,
                        "so4":   r.so4_mgl,
                        "po4":   r.po4_mgl,
                        "mlss":  r.mlss_mgl,
                    }
                    for r in rows
                ]
        except Exception:
            return

        field_keys = ["do", "ph", "temp", "cod", "nh4", "no3", "so4", "po4", "mlss"]
        db_fields  = ["do_mgl", "ph", "temperature_c", "cod_mgl", "nh4_mgl",
                      "no3_mgl", "so4_mgl", "po4_mgl", "mlss_mgl"]

        self._history_table.setRowCount(len(records))
        for row_i, rec in enumerate(records):
            zone = rec["zone"]
            zone_color = QColor(ZONE_COLORS.get(zone, "#95a5a6"))
            zone_color.setAlpha(30)

            # Date
            self._set_cell(row_i, 0, rec["date"], zone_color)
            # Zone (coloured text)
            z_item = QTableWidgetItem(ZONE_LABELS.get(zone, zone))
            z_item.setForeground(QBrush(QColor(ZONE_COLORS.get(zone, "#2c3e50"))))
            z_item.setFont(QFont("", -1, QFont.Bold))
            z_item.setBackground(QBrush(zone_color))
            self._history_table.setItem(row_i, 1, z_item)

            # Parameter values
            for col_i, (key, db_f) in enumerate(zip(field_keys, db_fields), start=2):
                val = rec[key]
                text = f"{val:.2f}" if val is not None else "—"
                rng  = RANGES.get(zone, {}).get(db_f)
                out_of_range = (
                    rng is not None and val is not None and
                    not (rng[0] <= val <= rng[1])
                )
                bg = HISTORY_ERR if out_of_range else zone_color
                item = self._set_cell(row_i, col_i, text, bg)
                if out_of_range:
                    item.setForeground(QBrush(QColor("#922b21")))
                    item.setToolTip(f"Outside normal range ({rng[0]}–{rng[1]})")

            self._history_table.setRowHeight(row_i, 32)

    def _set_cell(self, row: int, col: int, text: str, bg: QColor) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setBackground(QBrush(bg))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self._history_table.setItem(row, col, item)
        return item

    # ── Range validation ───────────────────────────────────────────────────────
    def _validate_spin(
        self, spin: QDoubleSpinBox, val: float, rng: tuple[float, float]
    ) -> None:
        """
        Color the spinbox border red if val is outside rng, normal otherwise.
        A value at the spinbox minimum (the "—" state) is never flagged.
        """
        at_min = val <= spin.minimum()
        out    = not at_min and not (rng[0] <= val <= rng[1])
        spin.setStyleSheet(self._spin_style_err() if out else self._spin_style_ok())

    # ── Database helpers ───────────────────────────────────────────────────────
    def _get_active_experiment(self) -> dict | None:
        """
        Return {id, name} of the active experiment, or None.
        Also updates the info strip label.
        """
        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(is_active=True).first()
                if exp:
                    result = {"id": exp.id, "name": exp.name}
                    self._info_label.setText(f"Active experiment:  {exp.name}")
                    self._info_label.setStyleSheet("color: #1e8449; font-size: 11px; font-weight: 600;")
                    return result
        except Exception:
            pass
        self._info_label.setText("No active experiment — go to Experiments to set one.")
        self._info_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        return None

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        """Refresh info strip and history whenever the user navigates here."""
        super().showEvent(event)
        self._save_msg.setText("")
        self._get_active_experiment()
        self._on_date_changed(self._date_edit.date())
        self._refresh_history()

    # ── Style helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _spin_style_ok() -> str:
        return """
            QDoubleSpinBox {
                border: 1px solid #ced4da; border-radius: 4px;
                padding: 2px 6px; font-size: 11px;
                background: #ffffff; color: #2c3e50;
            }
            QDoubleSpinBox:focus { border-color: #2980b9; }
        """

    @staticmethod
    def _spin_style_err() -> str:
        return """
            QDoubleSpinBox {
                border: 2px solid #e74c3c; border-radius: 4px;
                padding: 2px 6px; font-size: 11px;
                background: #fdecea; color: #922b21;
            }
        """

    @staticmethod
    def _make_card() -> QWidget:
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: #ffffff; border-radius: 8px;
                border: 1px solid #dde1e7;
            }
        """)
        return card

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.HLine)
        d.setStyleSheet("color: #dde1e7; margin: 2px 0;")
        return d

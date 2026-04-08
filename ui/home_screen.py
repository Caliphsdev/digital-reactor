"""
home_screen.py — Home screen (index 0) for the Digital Reactor app.

Contains:
  • A header bar with the screen title and a Refresh button
  • The ReactorDiagram widget (fills remaining space)
  • A status strip showing active experiment name, or a prompt to create one

The Refresh button reloads today's readings from the database without
restarting the app.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from datetime import date as dt_date

from core.database import get_session
from core.models import Experiment, DailyReading, FlowReading
from core.calculations import (
    calc_fm_ratio, calc_actual_srt, calc_hrt,
    check_nitrifier_washout_risk, REACTOR_VOLUME_L,
)
from ui.reactor_diagram import ReactorDiagram


class HomeScreen(QWidget):
    """
    Home screen that hosts the live reactor diagram plus a header and
    a status bar showing the active experiment.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_diagram(), stretch=1)
        layout.addWidget(self._build_kinetics_card())
        layout.addWidget(self._build_status_bar())

        self._refresh_status()

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        """
        Top bar: screen title on the left, Refresh button on the right.
        """
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet("background-color: #2c3e50;")

        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)

        # Screen title
        title = QLabel("Reactor Overview")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("color: #ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        # Refresh button — reloads today's data without restarting
        self._refresh_btn = QPushButton("  Refresh")
        self._refresh_btn.setIcon(qta.icon("fa6s.rotate-left", color="#ecf0f1"))
        self._refresh_btn.setIconSize(QSize(14, 14))
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background: #3d5166;
                color: #ecf0f1;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
                font-size: 11px;
            }
            QPushButton:hover { background: #3498db; }
        """)
        self._refresh_btn.clicked.connect(self._on_refresh)
        row.addWidget(self._refresh_btn)

        return bar

    # ── Kinetics summary card ──────────────────────────────────────────────────
    def _build_kinetics_card(self) -> QWidget:
        """
        Collapsible strip showing key derived process metrics for today:
        HRT, actual SRT, F:M ratio, and a nitrifier washout warning if triggered.

        Collapsed by default (one-line header). Expands to show metric chips.
        """
        container = QWidget()
        container.setStyleSheet("background: #ecf0f1; border-top: 1px solid #d5d8dc;")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle header
        self._kinetics_toggle = QPushButton()
        self._kinetics_toggle.setCheckable(True)
        self._kinetics_toggle.setChecked(False)
        self._kinetics_toggle.setCursor(Qt.PointingHandCursor)
        self._kinetics_toggle.setFixedHeight(28)
        self._kinetics_toggle.setStyleSheet("""
            QPushButton {
                background: #dfe6e9; color: #2c3e50; border: none;
                text-align: left; padding: 0 14px; font-size: 10px; font-weight: 600;
            }
            QPushButton:checked { background: #d5eaf9; }
            QPushButton:hover   { background: #d5eaf9; }
        """)
        self._kinetics_toggle.toggled.connect(self._on_kinetics_toggle)
        outer.addWidget(self._kinetics_toggle)

        # Expandable metrics panel
        self._kinetics_panel = QWidget()
        self._kinetics_panel.setVisible(False)
        self._kinetics_panel.setStyleSheet("background: #ecf0f1;")
        panel_layout = QHBoxLayout(self._kinetics_panel)
        panel_layout.setContentsMargins(14, 8, 14, 8)
        panel_layout.setSpacing(12)

        # Metric labels stored for refresh
        self._km_hrt   = self._metric_chip(panel_layout, "HRT", "—")
        self._km_srt   = self._metric_chip(panel_layout, "Actual SRT", "—")
        self._km_fm    = self._metric_chip(panel_layout, "F:M Ratio", "—")
        panel_layout.addStretch()
        self._km_warn  = QLabel("")
        self._km_warn.setStyleSheet("color: #e67e22; font-size: 10px; font-weight: 600;")
        self._km_warn.setWordWrap(True)
        panel_layout.addWidget(self._km_warn)

        outer.addWidget(self._kinetics_panel)
        self._update_kinetics_header(loading=True)
        return container

    def _metric_chip(self, layout: QHBoxLayout, label: str, value: str) -> QLabel:
        """Add a small label+value chip to the panel and return the value QLabel."""
        chip = QWidget()
        chip.setStyleSheet(
            "background: #ffffff; border-radius: 4px; border: 1px solid #d5d8dc;"
        )
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(10, 4, 10, 4)
        chip_layout.setSpacing(6)

        lbl = QLabel(label + ":")
        lbl.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("color: #2c3e50; font-size: 10px; font-weight: 600;")
        chip_layout.addWidget(lbl)
        chip_layout.addWidget(val_lbl)
        layout.addWidget(chip)
        return val_lbl

    def _on_kinetics_toggle(self, checked: bool) -> None:
        self._kinetics_panel.setVisible(checked)
        arrow = "▼" if checked else "▶"
        # Preserve whatever text was already set (just update arrow)
        text = self._kinetics_toggle.text()
        if text and len(text) > 2:
            self._kinetics_toggle.setText(f"{arrow}  {text[3:]}")

    def _refresh_kinetics(self) -> None:
        """Compute today's HRT, SRT, F:M from the database and update chips."""
        try:
            with get_session() as session:
                active = session.query(Experiment).filter_by(is_active=True).first()
                if not active:
                    self._update_kinetics_header(no_exp=True)
                    return

                today = dt_date.today()
                flow = (
                    session.query(FlowReading)
                    .filter_by(experiment_id=active.id, reading_date=today)
                    .first()
                )
                aerobic_r = (
                    session.query(DailyReading)
                    .filter_by(experiment_id=active.id, reading_date=today, zone="aerobic")
                    .first()
                )

            if not flow:
                self._update_kinetics_header(no_data=True)
                return

            hrt_h  = calc_hrt(flow.q_in_mlh or 0.0)
            srt_d  = calc_actual_srt(
                aerobic_r.mlss_mgl if aerobic_r else 3000.0,
                flow.q_was_mlh or 0.0
            )
            fm = 0.0
            if aerobic_r and aerobic_r.mlss_mgl:
                # Use influent COD from aerobic zone's COD reading (approximation)
                # A more accurate F:M would use the influent zone COD
                fm = calc_fm_ratio(
                    cod_inf_mgl=aerobic_r.cod_mgl or 0.0,
                    q_in_mlh=flow.q_in_mlh or 0.0,
                    mlss_mgl=aerobic_r.mlss_mgl or 0.0,
                    vss_mgl=aerobic_r.vss_mgl if hasattr(aerobic_r, "vss_mgl") else None,
                )

            temp = aerobic_r.temperature_c if aerobic_r else 22.0
            warn = check_nitrifier_washout_risk(srt_d, temp or 22.0) if srt_d > 0 else None

            # Format values
            hrt_txt = f"{hrt_h:.1f} h" if hrt_h > 0 else "—"
            srt_txt = f"{srt_d:.1f} d" if srt_d > 0 else "—"
            fm_txt  = f"{fm:.3f} kg/kg/d" if fm > 0 else "—"

            # Colour F:M: green (0.05–0.15), amber (otherwise)
            fm_color = "#27ae60" if 0.05 <= fm <= 0.15 else ("#e67e22" if fm > 0 else "#7f8c8d")
            srt_color = "#27ae60" if 15 <= srt_d <= 45 else "#e67e22"

            self._km_hrt.setText(hrt_txt)
            self._km_hrt.setStyleSheet(f"color: #2c3e50; font-size: 10px; font-weight: 600;")
            self._km_srt.setText(srt_txt)
            self._km_srt.setStyleSheet(f"color: {srt_color}; font-size: 10px; font-weight: 600;")
            self._km_fm.setText(fm_txt)
            self._km_fm.setStyleSheet(f"color: {fm_color}; font-size: 10px; font-weight: 600;")
            self._km_warn.setText(f"⚠ {warn}" if warn else "")

            self._update_kinetics_header(hrt_h=hrt_h, srt_d=srt_d, fm=fm)

        except Exception:
            self._update_kinetics_header(no_data=True)

    def _update_kinetics_header(
        self, loading=False, no_exp=False, no_data=False,
        hrt_h=None, srt_d=None, fm=None
    ) -> None:
        arrow = "▼" if self._kinetics_toggle.isChecked() else "▶"
        if loading or no_exp:
            text = f"{arrow}  Process Metrics (today)  — no active experiment" if no_exp else f"{arrow}  Process Metrics (today)"
        elif no_data:
            text = f"{arrow}  Process Metrics (today)  — enter flow readings to calculate"
        else:
            parts = []
            if hrt_h: parts.append(f"HRT {hrt_h:.1f}h")
            if srt_d: parts.append(f"SRT {srt_d:.1f}d")
            if fm:    parts.append(f"F:M {fm:.3f}")
            text = f"{arrow}  Process Metrics (today)   " + "  ·  ".join(parts)
        self._kinetics_toggle.setText(text)

    # ── Reactor diagram ────────────────────────────────────────────────────────
    def _build_diagram(self) -> ReactorDiagram:
        """Create the QPainter diagram widget."""
        self._diagram = ReactorDiagram()
        return self._diagram

    # ── Status bar ─────────────────────────────────────────────────────────────
    def _build_status_bar(self) -> QWidget:
        """
        Thin strip at the bottom showing the active experiment name,
        or a message prompting the user to create one.
        """
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet("background-color: #dfe6e9; border-top: 1px solid #b2bec3;")

        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 0, 14, 0)

        # Experiment icon
        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon("fa6s.flask", color="#636e72").pixmap(QSize(13, 13))
        )
        row.addWidget(icon_label)
        row.addSpacing(5)

        self._status_label = QLabel("Loading…")
        self._status_label.setStyleSheet("color: #636e72; font-size: 11px;")
        row.addWidget(self._status_label)
        row.addStretch()

        return bar

    # ── Refresh logic ──────────────────────────────────────────────────────────
    def _on_refresh(self) -> None:
        """Called when the Refresh button is clicked."""
        self._diagram._load_today_data()
        self._diagram.update()
        self._refresh_status()
        self._refresh_kinetics()

    def _refresh_status(self) -> None:
        """
        Query the database for the active experiment and update the status bar.
        Shows the experiment name if one is active, otherwise a hint message.
        """
        try:
            with get_session() as session:
                active = (
                    session.query(Experiment)
                    .filter_by(is_active=True)
                    .first()
                )
            if active:
                self._status_label.setText(
                    f"Active experiment:  {active.name}   "
                    f"(started {active.start_date})"
                )
            else:
                self._status_label.setText(
                    "No active experiment — go to Experiments to create one."
                )
        except Exception:
            self._status_label.setText("Database unavailable.")

    def showEvent(self, event) -> None:
        """Refresh status and kinetics whenever this screen becomes visible."""
        super().showEvent(event)
        self._refresh_status()
        self._refresh_kinetics()

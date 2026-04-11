"""
reactor_diagram.py — Digital Reactor process flow diagram (QPainter).

Physical layout matches the CAS lab reactor:

         [STIRRER]      [STIRRER] [STIRRER]
              ↓               ↓     ↓
[DO METER] ╱PST╲  SP2  ╱AERATION TANK╲  SP3  │CLARIFIER│  SP4  [RAS CTRL]
[panel]   ╲    ╱ ───── ╲             ╱ ─────  │  TUBE   │ ────  [panel]
           ╲──╱         ╲───────────╱         │         │
SP1↑                         DO probe↑                  ↓ WAS
[INFLUENT STORAGE]               ←── RAS ───── [EFFLUENT STORAGE]

Animation:
  • Flow particles on each pipe segment
  • RAS return particles following curved path
  • Aeration bubbles rising inside the Aeration Tank
  • Stirrer cross-blades drawn above PST and Aeration Tank
  • DO probe icon inserted from above into Aeration Tank

Geometry cached on first paint, invalidated on resize.
Timer paused when widget hidden.
"""

import math
import random
from pathlib import Path
from datetime import date

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath,
    QFont, QPolygonF, QRadialGradient, QLinearGradient,
)
from PySide6.QtSvg import QSvgRenderer

from core.database import get_session
from core.models import DailyReading, FlowReading, Experiment


# ── Palette ────────────────────────────────────────────────────────────────────
C_PST        = QColor("#795548")   # earthy brown — primary settling tank
C_AERATION   = QColor("#1e8449")   # green — biological aeration
C_CLARIFIER  = QColor("#717d7e")   # grey — clarifier
C_PIPE_RAIL  = QColor("#2c3e50")
C_PIPE_SPEC  = QColor("#8ea8ba")
C_PIPE_SHAD  = QColor("#1a252f")
C_FLOW       = QColor("#5dade2")
C_RAS        = QColor("#e74c3c")
C_WAS        = QColor("#c0392b")
C_SP         = QColor("#e74c3c")
C_TEXT       = QColor("#1c2833")
C_TEXT_ZONE  = QColor("#ffffff")
C_OVERLAY_BG = QColor(255, 255, 255, 195)
C_PANEL_BG   = QColor("#1a2a3a")
C_PANEL_BORD = QColor("#4a6fa5")
C_JUG_BORD   = QColor("#7f8c8d")
C_JUG_FILL   = QColor(240, 248, 255, 220)

# Clarifier sedimentation band colours
C_CLA_CLEAR  = QColor(220, 233, 240, 204)
C_CLA_MIXED  = QColor(181, 200, 212, 230)
C_CLA_SLUDGE = QColor(141, 159, 168, 255)

# ── Animation constants ────────────────────────────────────────────────────────
TIMER_MS       = 66          # ~15 fps
PARTICLE_SPEED = 0.025
N_PARTICLES    = 2
TAIL = [(0.0, 1.00, 4.5), (PARTICLE_SPEED, 0.45, 3.2), (PARTICLE_SPEED * 2, 0.18, 2.0)]
FLOW_DASH_SPEED = 0.12
ASSET_REACTOR_OVERVIEW = "reactor_overview_scada.svg"
SVG_VIEW_W = 1000.0
SVG_VIEW_H = 600.0

LABELS = {
    "pst": "PRIMARY\nSETTLING",
    "aeration": "AERATION\nTANK",
    "clarifier": "CLARIFIER",
    "do_meter": "DO\nMETER",
    "pump_title": "SEDIMENT\nRETURN",
}


class ReactorDiagram(QWidget):
    """
    Scalable QPainter widget — CAS reactor process flow diagram.
    Matches the physical lab reactor: PST → Aeration Tank → Clarifier.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        # Particle t-values per segment — evenly spaced [0, 1/N, 2/N ...]
        self._pts: dict[str, list[float]] = {
            seg: [i / N_PARTICLES for i in range(N_PARTICLES)]
            for seg in ("feed", "pst_aer", "aer_cla", "effluent", "ras", "was")
        }

        # Geometry cache — rebuilt on resize
        self._geo: dict | None = None
        self._ras_path: QPainterPath | None = None

        self._today_data: dict = {}
        self._ras_ratio: float | None = None
        self._load_today_data()
        self._flow_phase: float = 0.0
        self._svg_renderer = self._load_svg_renderer()

        self._init_bubbles()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TIMER_MS)

    # ── Bubble initialisation ──────────────────────────────────────────────────
    def _init_bubbles(self) -> None:
        self._bubbles: list[dict] = []
        for _ in range(14):
            self._bubbles.append({
                "x_off":   random.uniform(-0.70, 0.70),
                "y_frac":  random.uniform(-0.70, 0.70),
                "r_px":    random.uniform(2.5, 5.5),
                "opacity": random.uniform(0.50, 0.85),
                "speed":   random.uniform(0.008, 0.016),
            })

    # ── Timer ──────────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        for seg in self._pts:
            self._pts[seg] = [(t + PARTICLE_SPEED) % 1.0 for t in self._pts[seg]]
        for b in self._bubbles:
            b["y_frac"] -= b["speed"]
        self._flow_phase = (self._flow_phase + FLOW_DASH_SPEED) % 1000.0
        self.update()

    # ── Resize ─────────────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._geo = None
        self._ras_path = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_today_data()
        if not self._timer.isActive():
            self._timer.start(TIMER_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    # ── Database ───────────────────────────────────────────────────────────────
    def _load_today_data(self) -> None:
        """Load today's zone readings + RAS ratio from the active experiment."""
        today = date.today()
        self._today_data = {}
        self._ras_ratio = None
        try:
            with get_session() as session:
                active = session.query(Experiment).filter_by(is_active=True).first()
                if not active:
                    return
                for row in (
                    session.query(DailyReading)
                    .filter_by(experiment_id=active.id, reading_date=today)
                    .all()
                ):
                    self._today_data[row.zone] = {
                        "do_mgl": row.do_mgl,
                        "ph":     row.ph,
                        "mlss_mgl": row.mlss_mgl,
                    }
                flow = (
                    session.query(FlowReading)
                    .filter_by(experiment_id=active.id, reading_date=today)
                    .first()
                )
                if flow and flow.ras_ratio is not None:
                    self._ras_ratio = flow.ras_ratio
        except Exception:
            pass

    # ── Paint ──────────────────────────────────────────────────────────────────
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()

        self._draw_background(painter, w, h)

        if self._geo is None:
            self._geo = self._build_geometry(w, h)
            self._ras_path = self._make_ras_path(self._geo)

        g = self._geo

        if self._svg_renderer and self._svg_renderer.isValid():
            # Professional base illustration from layered vector artwork.
            self._draw_svg_base(painter, w, h)
            self._draw_flow_velocity_overlay(painter, g)
            self._draw_particles(painter, g)
            self._draw_aeration_bubbles(painter, g)
            self._draw_svg_live_overlays(painter, w, h)
            self._draw_loop_labels(painter, g)
            self._draw_was_label(painter, g)
        else:
            # Fallback to the fully programmatic renderer when SVG is unavailable.
            self._draw_storage_jugs(painter, g)
            self._draw_loop_rails(painter, g)
            self._draw_pipe_rails(painter, g)
            self._draw_flow_velocity_overlay(painter, g)
            self._draw_particles(painter, g)
            self._draw_vessels(painter, g)
            self._draw_aeration_bubbles(painter, g)
            self._draw_stirrers(painter, g)
            self._draw_do_probe(painter, g)
            self._draw_sampling_points(painter, g)
            self._draw_do_meter_panel(painter, g)
            self._draw_ras_controller_panel(painter, g)
            self._draw_loop_labels(painter, g)
            self._draw_was_label(painter, g)

        self._draw_data_overlays(painter, g)

        painter.end()

    # ── Geometry ───────────────────────────────────────────────────────────────
    def _build_geometry(self, w: int, h: int) -> dict:
        y_mid = h * 0.46

        # PST — inverted trapezoid (funnel)
        pst_x  = w * 0.29
        pst_tw = w * 0.075   # top half-width (wide)
        pst_bw = w * 0.030   # bottom half-width (narrow)
        pst_ht = h * 0.18    # half-height

        # Aeration Tank — large rounded vessel
        aer_x  = w * 0.54
        aer_hw = w * 0.105   # half-width
        aer_hh = h * 0.21    # half-height

        # Clarifier — tall narrow cylinder
        cla_x  = w * 0.78
        cla_hw = w * 0.022   # half-width (narrow)
        cla_hh = h * 0.27    # half-height (tall)

        # Process pipe endpoints
        x_feed = w * 0.04
        x_effl = w * 0.96

        # RAS and WAS y-levels — proportions derived from SVG coords (488/600, 556/600)
        # so particle paths and labels align with the SVG artwork.
        y_ras     = h * 0.813
        y_was_end = h * 0.927

        # DO Meter panel (left wall)
        do_px = w * 0.018
        do_py = h * 0.10
        do_pw = w * 0.075
        do_ph = h * 0.26

        # RAS Controller panel (right wall)
        ras_px = w * 0.905
        ras_py = h * 0.10
        ras_pw = w * 0.080
        ras_ph = h * 0.26

        # Influent/Effluent storage jugs (bottom)
        jug_w = w * 0.12
        jug_h = h * 0.22
        jug_y = h * 0.73
        infl_jug_x = w * 0.06
        effl_jug_x = w * 0.83

        # Stirrer anchor y-positions (above vessels)
        pst_stirrer_y = y_mid - pst_ht - h * 0.055
        aer_stirrer_y = y_mid - aer_hh - h * 0.055

        return dict(
            w=w, h=h, y_mid=y_mid,
            pst_x=pst_x, pst_tw=pst_tw, pst_bw=pst_bw, pst_ht=pst_ht,
            aer_x=aer_x, aer_hw=aer_hw, aer_hh=aer_hh,
            cla_x=cla_x, cla_hw=cla_hw, cla_hh=cla_hh,
            x_feed=x_feed, x_effl=x_effl,
            y_ras=y_ras, y_was_end=y_was_end,
            do_px=do_px, do_py=do_py, do_pw=do_pw, do_ph=do_ph,
            ras_px=ras_px, ras_py=ras_py, ras_pw=ras_pw, ras_ph=ras_ph,
            jug_w=jug_w, jug_h=jug_h, jug_y=jug_y,
            infl_jug_x=infl_jug_x, effl_jug_x=effl_jug_x,
            pst_stirrer_y=pst_stirrer_y,
            aer_stirrer_y=aer_stirrer_y,
        )

    # ── RAS path ───────────────────────────────────────────────────────────────
    def _make_ras_path(self, g: dict) -> QPainterPath:
        """RAS: clarifier bottom → under diagram → aeration tank left inlet."""
        x_s = g["cla_x"]
        y_s = g["y_mid"] + g["cla_hh"]
        x_e = g["aer_x"] - g["aer_hw"]
        y_e = g["y_mid"]
        y_b = g["y_ras"]
        cr  = 14
        p = QPainterPath()
        p.moveTo(x_s, y_s)
        p.lineTo(x_s, y_b - cr)
        p.quadTo(x_s, y_b, x_s - cr, y_b)
        p.lineTo(x_e + cr, y_b)
        p.quadTo(x_e, y_b, x_e, y_b - cr)
        p.lineTo(x_e, y_e)
        return p

    # ── Background ─────────────────────────────────────────────────────────────
    def _load_svg_renderer(self) -> QSvgRenderer | None:
        """Load SCADA SVG art if present; fallback painter mode remains available."""
        asset_path = Path(__file__).resolve().parent.parent / "assets" / ASSET_REACTOR_OVERVIEW
        if not asset_path.exists():
            return None
        renderer = QSvgRenderer(str(asset_path))
        return renderer if renderer.isValid() else None

    def _draw_svg_base(self, painter: QPainter, w: int, h: int) -> None:
        painter.save()
        self._svg_renderer.render(painter, QRectF(0, 0, w, h))
        painter.restore()

    def _draw_svg_live_overlays(self, painter: QPainter, w: int, h: int) -> None:
        """Draw live values and process-state animation above static SVG artwork."""
        sx = w / SVG_VIEW_W
        sy = h / SVG_VIEW_H
        self._draw_svg_clarifier_settling(painter, sx, sy)
        self._draw_svg_live_instruments(painter, sx, sy)

    def _draw_svg_clarifier_settling(self, painter: QPainter, sx: float, sy: float) -> None:
        """Animate clarifier sludge blanket height using daily MLSS readings."""
        # Base dimensions mirror the clarifier in assets/reactor_overview_scada.svg.
        x = 751.0 * sx
        y = 96.0 * sy
        w = 58.0 * sx
        h = 342.0 * sy

        cla = self._today_data.get("clarifier", {})
        aer = self._today_data.get("aeration", {})

        mlss = cla.get("mlss_mgl")
        if mlss is None:
            mlss = aer.get("mlss_mgl")

        if mlss is None:
            blanket_ratio = 0.34
        else:
            norm = max(0.0, min(1.0, (mlss - 80.0) / 1400.0))
            blanket_ratio = 0.22 + norm * 0.40

        # Subtle breathing motion keeps the layer visually alive.
        blanket_ratio += 0.015 * math.sin(self._flow_phase * 0.11)
        blanket_ratio = max(0.18, min(0.64, blanket_ratio))

        blanket_h = h * blanket_ratio
        blanket_top = y + h - blanket_h

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, w, h), 6.0 * sx, 6.0 * sy)

        painter.save()
        painter.setClipPath(clip)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(124, 140, 151, 170)))
        painter.drawRect(QRectF(x, blanket_top, w, blanket_h))

        # Interface haze between mixed and sludge layers.
        haze_h = max(3.0 * sy, h * 0.02)
        painter.setBrush(QBrush(QColor(196, 210, 219, 95)))
        painter.drawRect(QRectF(x, blanket_top - haze_h, w, haze_h))
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(214, 227, 235, 175), max(1.1, 1.6 * sy), Qt.DashLine))
        painter.drawLine(
            QPointF(x + 1.5 * sx, blanket_top),
            QPointF(x + w - 1.5 * sx, blanket_top),
        )
        painter.restore()

    def _draw_svg_live_instruments(self, painter: QPainter, sx: float, sy: float) -> None:
        """Overwrite static panel text with live DO and RAS values."""
        aer = self._today_data.get("aeration", {})
        do_val = aer.get("do_mgl")
        ratio = self._ras_ratio if self._ras_ratio is not None else 1.0

        # DO display area.
        do_screen = QRectF(24.0 * sx, 55.0 * sy, 67.0 * sx, 62.0 * sy)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0d261c")))
        painter.drawRoundedRect(do_screen, 3.0 * sx, 3.0 * sy)

        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(12, int(24 * sy)))
        painter.setFont(f)
        painter.setPen(QPen(QColor("#39ff14")))
        do_text = f"{do_val:.1f}" if do_val is not None else "-"
        painter.drawText(QRectF(24.0 * sx, 66.0 * sy, 67.0 * sx, 24.0 * sy), Qt.AlignCenter, do_text)

        f2 = QFont()
        f2.setBold(True)
        f2.setPixelSize(max(8, int(12 * sy)))
        painter.setFont(f2)
        painter.drawText(QRectF(24.0 * sx, 91.0 * sy, 67.0 * sx, 18.0 * sy), Qt.AlignCenter, "mg/L")
        painter.restore()

        # RAS value area — matches panel at x=897, width=88 in SVG.
        ras_value_rect = QRectF(900.0 * sx, 101.0 * sy, 82.0 * sx, 28.0 * sy)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#152433")))
        painter.drawRect(ras_value_rect)

        f3 = QFont()
        f3.setBold(True)
        f3.setPixelSize(max(10, int(16 * sy)))
        painter.setFont(f3)
        painter.setPen(QPen(QColor("#e8f4f8")))
        painter.drawText(ras_value_rect, Qt.AlignCenter, f"RAS {ratio:.1f}:1")

        # Running indicator pulse — centred on panel at x=941.
        glow = 130 + int(50 * (0.5 + 0.5 * math.sin(self._flow_phase * 0.08)))
        painter.setBrush(QBrush(QColor(46, 204, 113, glow)))
        painter.setPen(QPen(QColor("#14683a"), max(0.8, 1.0 * sy)))
        painter.drawEllipse(QPointF(941.0 * sx, 160.0 * sy), 8.0 * sx, 8.0 * sy)
        painter.restore()

    def _draw_background(self, painter: QPainter, w: int, h: int) -> None:
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#f4f7f9"))
        bg.setColorAt(1.0, QColor("#edf1f5"))
        painter.fillRect(0, 0, w, h, QBrush(bg))
        painter.setPen(QPen(QColor(220, 228, 234, 178), 0.5))
        for x in range(0, w, 48):
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        for y in range(0, h, 48):
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        painter.setOpacity(1.0)

    # ── Storage jugs ───────────────────────────────────────────────────────────
    def _draw_storage_jugs(self, painter: QPainter, g: dict) -> None:
        """Influent and effluent storage containers at the bottom."""
        jw, jh, jy = g["jug_w"], g["jug_h"], g["jug_y"]

        for jx, label, liq_color in [
            (g["infl_jug_x"], "Influent\nStorage", QColor("#aed6f1")),
            (g["effl_jug_x"], "Effluent\nStorage", QColor("#a9dfbf")),
        ]:
            rect = QRectF(jx, jy, jw, jh)

            # Shadow
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
            painter.drawRoundedRect(rect.adjusted(3, 4, 3, 4), 6, 6)

            # Body
            painter.setPen(QPen(C_JUG_BORD, 1.8))
            painter.setBrush(QBrush(C_JUG_FILL))
            painter.drawRoundedRect(rect, 6, 6)

            # Liquid fill (bottom 58%)
            fill_rect = QRectF(jx + 2, jy + jh * 0.40, jw - 4, jh * 0.58)
            liq_grad = QLinearGradient(jx, fill_rect.top(), jx, fill_rect.bottom())
            liq_grad.setColorAt(0.0, liq_color.lighter(115))
            liq_grad.setColorAt(1.0, liq_color.darker(120))
            clip = QPainterPath()
            clip.addRoundedRect(rect, 6, 6)
            painter.save()
            painter.setClipPath(clip)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(liq_grad))
            painter.drawRect(fill_rect)
            painter.restore()

            # Border on top
            painter.setPen(QPen(C_JUG_BORD, 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)

            # Label
            font = QFont()
            font.setPointSize(max(6, int(jw * 0.09)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(C_TEXT))
            painter.drawText(rect, Qt.AlignCenter, label)

        # Feed pipe: influent jug top → main pipe level
        ijcx = g["infl_jug_x"] + jw / 2
        painter.setPen(QPen(C_PIPE_SHAD, 4.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(ijcx, jy), QPointF(g["x_feed"], g["y_mid"]))
        painter.setPen(QPen(C_PIPE_RAIL, 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(ijcx, jy), QPointF(g["x_feed"], g["y_mid"]))

        # Effluent pipe: main pipe level → effluent jug top
        ejcx = g["effl_jug_x"] + jw / 2
        painter.setPen(QPen(C_PIPE_SHAD, 4.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(g["x_effl"], g["y_mid"]), QPointF(ejcx, jy))
        painter.setPen(QPen(C_PIPE_RAIL, 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(g["x_effl"], g["y_mid"]), QPointF(ejcx, jy))

    # ── Loop rails (RAS + WAS) ─────────────────────────────────────────────────
    def _draw_loop_rails(self, painter: QPainter, g: dict) -> None:
        # RAS return
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_RAS.darker(130), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._ras_path)
        self._arrowhead(painter, QPointF(g["aer_x"] - g["aer_hw"], g["y_mid"]),
                        "up", C_RAS, 9)

        # WAS drop
        x   = g["cla_x"]
        y_s = g["y_mid"] + g["cla_hh"]
        y_e = g["y_was_end"]
        painter.setPen(QPen(C_WAS.darker(120), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(x, y_s), QPointF(x, y_e))
        self._arrowhead(painter, QPointF(x, y_e), "down", C_WAS, 8)

    # ── Pipe rails (3-layer cylindrical) ───────────────────────────────────────
    def _draw_pipe_rails(self, painter: QPainter, g: dict) -> None:
        y = g["y_mid"]
        segs = [
            (g["x_feed"],                      g["pst_x"] - g["pst_tw"]),
            (g["pst_x"] + g["pst_tw"],         g["aer_x"] - g["aer_hw"]),
            (g["aer_x"] + g["aer_hw"],         g["cla_x"] - g["cla_hw"]),
            (g["cla_x"] + g["cla_hw"],         g["x_effl"]),
        ]
        for x1, x2 in segs:
            if x2 <= x1 + 2:
                continue
            painter.setPen(QPen(C_PIPE_SHAD, 6.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y + 1.2), QPointF(x2, y + 1.2))
            painter.setPen(QPen(C_PIPE_RAIL, 4.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
            painter.setPen(QPen(C_PIPE_SPEC, 1.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y - 1.0), QPointF(x2, y - 1.0))
            self._arrowhead(painter, QPointF(x2, y), "right", C_PIPE_RAIL, 9)

    # ── Particles ──────────────────────────────────────────────────────────────
    def _draw_particles(self, painter: QPainter, g: dict) -> None:
        y = g["y_mid"]
        straight = [
            (QPointF(g["x_feed"],              y),
             QPointF(g["pst_x"] - g["pst_tw"], y), "feed",    C_FLOW),
            (QPointF(g["pst_x"] + g["pst_tw"], y),
             QPointF(g["aer_x"] - g["aer_hw"], y), "pst_aer", C_FLOW),
            (QPointF(g["aer_x"] + g["aer_hw"], y),
             QPointF(g["cla_x"] - g["cla_hw"], y), "aer_cla", C_FLOW),
            (QPointF(g["cla_x"] + g["cla_hw"], y),
             QPointF(g["x_effl"],              y), "effluent", C_FLOW),
            (QPointF(g["cla_x"], g["y_mid"] + g["cla_hh"]),
             QPointF(g["cla_x"], g["y_was_end"]),  "was",     C_WAS),
        ]
        painter.setPen(Qt.NoPen)
        for p1, p2, key, color in straight:
            dx = abs(p2.x() - p1.x())
            dy = abs(p2.y() - p1.y())
            if dx > 4 or dy > 4:
                self._draw_seg_particles(painter, self._pts[key], p1, p2, color)
        self._draw_path_particles(painter, self._pts["ras"], self._ras_path, C_RAS)
        painter.setOpacity(1.0)

    def _draw_flow_velocity_overlay(self, painter: QPainter, g: dict) -> None:
        """Animated dashed overlays reinforce flow direction on main process lines."""
        y = g["y_mid"]
        dash = 22.0

        flow_pen = QPen(QColor(130, 197, 255, 150), 1.6, Qt.DashLine, Qt.RoundCap)
        flow_pen.setDashPattern([6.0, 8.0])
        flow_pen.setDashOffset(-self._flow_phase)

        ras_pen = QPen(QColor(231, 76, 60, 180), 1.8, Qt.DashLine, Qt.RoundCap)
        ras_pen.setDashPattern([8.0, 7.0])
        ras_pen.setDashOffset(-self._flow_phase * 0.85)

        was_pen = QPen(QColor(192, 57, 43, 170), 1.5, Qt.DashLine, Qt.RoundCap)
        was_pen.setDashPattern([6.0, 8.0])
        was_pen.setDashOffset(-self._flow_phase * 0.72)

        segments = [
            (QPointF(g["x_feed"], y), QPointF(g["pst_x"] - g["pst_tw"], y)),
            (QPointF(g["pst_x"] + g["pst_tw"], y), QPointF(g["aer_x"] - g["aer_hw"], y)),
            (QPointF(g["aer_x"] + g["aer_hw"], y), QPointF(g["cla_x"] - g["cla_hw"], y)),
            (QPointF(g["cla_x"] + g["cla_hw"], y), QPointF(g["x_effl"], y)),
        ]

        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(flow_pen)
        for p1, p2 in segments:
            if abs(p2.x() - p1.x()) > dash:
                painter.drawLine(p1, p2)

        if self._ras_path is not None:
            painter.setPen(ras_pen)
            painter.drawPath(self._ras_path)

        painter.setPen(was_pen)
        painter.drawLine(
            QPointF(g["cla_x"], g["y_mid"] + g["cla_hh"]),
            QPointF(g["cla_x"], g["y_was_end"]),
        )
        painter.restore()

    def _draw_seg_particles(self, painter, ts, p1, p2, color) -> None:
        for t in ts:
            for dt, opacity, radius in TAIL:
                t_g = (t - dt) % 1.0
                pos = QPointF(p1.x() + t_g * (p2.x() - p1.x()),
                              p1.y() + t_g * (p2.y() - p1.y()))
                painter.setOpacity(opacity)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pos, radius, radius)

    def _draw_path_particles(self, painter, ts, path, color) -> None:
        for t in ts:
            for dt, opacity, radius in TAIL:
                t_g = (t - dt) % 1.0
                pos = path.pointAtPercent(t_g)
                painter.setOpacity(opacity)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pos, radius, radius)

    # ── Vessels ─────────────────────────────────────────────────────────────────
    def _draw_vessels(self, painter: QPainter, g: dict) -> None:
        self._draw_pst(painter, g)
        self._draw_aeration_tank(painter, g)
        self._draw_clarifier(painter, g)

    def _draw_pst(self, painter: QPainter, g: dict) -> None:
        """Primary Settling Tank — inverted trapezoid (funnel shape), earthy brown."""
        cx, y   = g["pst_x"], g["y_mid"]
        tw, bw  = g["pst_tw"], g["pst_bw"]
        ht      = g["pst_ht"]
        ty, by  = y - ht, y + ht

        pts = QPolygonF([
            QPointF(cx - tw, ty),
            QPointF(cx + tw, ty),
            QPointF(cx + bw, by),
            QPointF(cx - bw, by),
        ])

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawPolygon(QPolygonF([QPointF(p.x() + 4, p.y() + 5) for p in pts]))

        # Gradient fill
        grad = QLinearGradient(cx - tw, ty, cx + tw, ty)
        grad.setColorAt(0.0, C_PST.lighter(165))
        grad.setColorAt(0.5, C_PST.lighter(120))
        grad.setColorAt(1.0, C_PST.darker(130))
        painter.setPen(QPen(C_PST.darker(140), 1.8))
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(pts)

        # Settled solids layer at bottom 35% (clipped to vessel shape)
        clip = QPainterPath()
        clip.addPolygon(pts)
        clip.closeSubpath()
        total_h = by - ty
        painter.save()
        painter.setClipPath(clip)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(180, 158, 130, 140)))
        painter.drawRect(QRectF(cx - tw, ty + total_h * 0.65, tw * 2, total_h * 0.35))
        painter.restore()

        # Outline on top
        painter.setPen(QPen(C_PST.darker(140), 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(pts)

        # Label
        font = QFont()
        font.setPointSize(max(5, int(tw * 0.155)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT_ZONE))
        painter.drawText(
            QRectF(cx - tw * 0.88, ty + 5, tw * 1.76, ht * 0.72),
            Qt.AlignCenter, LABELS["pst"],
        )

    def _draw_aeration_tank(self, painter: QPainter, g: dict) -> None:
        """Aeration Tank — large rounded rectangle, green, dominant vessel."""
        cx, y   = g["aer_x"], g["y_mid"]
        hw, hh  = g["aer_hw"], g["aer_hh"]
        rect    = QRectF(cx - hw, y - hh, hw * 2, hh * 2)

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 55)))
        painter.drawRoundedRect(rect.adjusted(4, 5, 4, 5), 12, 12)

        # Radial gradient fill
        grad = QRadialGradient(cx, y, hw * 1.25)
        grad.setFocalPoint(QPointF(cx - hw * 0.35, y - hh * 0.38))
        grad.setColorAt(0.0, C_AERATION.lighter(190))
        grad.setColorAt(0.38, C_AERATION.lighter(118))
        grad.setColorAt(1.0, C_AERATION.darker(160))
        painter.setPen(QPen(C_AERATION.darker(140), 2.0))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, 12, 12)

        # Liquid surface reflection sheen
        refl = QRectF(cx - hw * 0.58, y - hh * 0.76, hw * 1.16, hh * 0.13)
        rg   = QLinearGradient(cx - hw, y, cx + hw, y)
        rg.setColorAt(0.0, QColor(255, 255, 255, 0))
        rg.setColorAt(0.5, QColor(255, 255, 255, 80))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(rg))
        painter.drawEllipse(refl)

        # Label
        font = QFont()
        font.setPointSize(max(6, int(hw * 0.13)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT_ZONE))
        painter.drawText(rect, Qt.AlignCenter, LABELS["aeration"])

    def _draw_clarifier(self, painter: QPainter, g: dict) -> None:
        """Clarifier — tall narrow cylinder with sedimentation layers."""
        cx, y   = g["cla_x"], g["y_mid"]
        hw, hh  = g["cla_hw"], g["cla_hh"]
        ty = y - hh
        rect    = QRectF(cx - hw, ty, hw * 2, hh * 2)
        total_h = hh * 2

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawRoundedRect(rect.adjusted(3, 4, 3, 4), 5, 5)

        # Base fill
        grad = QLinearGradient(cx - hw, ty, cx + hw, ty)
        grad.setColorAt(0.0, C_CLARIFIER.lighter(140))
        grad.setColorAt(1.0, C_CLARIFIER.darker(130))
        painter.setPen(QPen(C_CLARIFIER.darker(130), 2.0))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, 5, 5)

        # Sedimentation layers clipped to cylinder
        clip = QPainterPath()
        clip.addRoundedRect(rect, 5, 5)
        painter.save()
        painter.setClipPath(clip)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(C_CLA_CLEAR))
        painter.drawRect(QRectF(cx - hw, ty, hw * 2, total_h * 0.38))
        painter.setBrush(QBrush(C_CLA_MIXED))
        painter.drawRect(QRectF(cx - hw, ty + total_h * 0.38, hw * 2, total_h * 0.25))
        painter.setBrush(QBrush(C_CLA_SLUDGE))
        painter.drawRect(QRectF(cx - hw, ty + total_h * 0.63, hw * 2, total_h * 0.37))
        painter.restore()

        # Outline
        painter.setPen(QPen(C_CLARIFIER.darker(130), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)

        # Vertical label avoids awkward split text inside narrow clarifier body.
        font = QFont()
        font.setPointSize(max(6, int(hw * 0.82)))
        font.setBold(True)
        painter.save()
        painter.translate(cx, y)
        painter.rotate(-90)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT_ZONE))
        painter.drawText(QRectF(-hh, -hw, hh * 2, hw * 2), Qt.AlignCenter, LABELS["clarifier"])
        painter.restore()

    # ── Aeration bubbles ───────────────────────────────────────────────────────
    def _draw_aeration_bubbles(self, painter: QPainter, g: dict) -> None:
        """Animated rising bubbles inside the Aeration Tank."""
        cx, cy = g["aer_x"], g["y_mid"]
        hw, hh = g["aer_hw"], g["aer_hh"]

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(cx - hw, cy - hh, hw * 2, hh * 2), 12, 12)
        painter.save()
        painter.setClipPath(clip)
        painter.setClipping(True)

        painter.setPen(QPen(QColor(150, 220, 235, 220), 1.2))
        for b in self._bubbles:
            if b["y_frac"] < -0.88:
                b["y_frac"]  = 0.78
                b["x_off"]   = random.uniform(-0.65, 0.65)
                b["r_px"]    = random.uniform(1.2, 2.5)
                b["opacity"] = random.uniform(0.40, 0.80)
            bx = cx + b["x_off"] * hw
            by = cy + b["y_frac"] * hh
            painter.setOpacity(b["opacity"])
            painter.setBrush(QBrush(QColor(255, 255, 255, 160)))
            painter.drawEllipse(QPointF(bx, by), b["r_px"], b["r_px"])

        painter.restore()
        painter.setClipping(False)
        painter.setOpacity(1.0)

    # ── Stirrers ───────────────────────────────────────────────────────────────
    def _draw_stirrers(self, painter: QPainter, g: dict) -> None:
        """Draw stirrer motor + blades above PST (×1) and Aeration Tank (×2)."""
        painter.setOpacity(1.0)
        # PST — single stirrer centred
        self._draw_one_stirrer(painter, g["pst_x"], g["pst_stirrer_y"],
                               g["y_mid"] - g["pst_ht"])
        # Aeration — two stirrers side-by-side
        aer_offset = g["aer_hw"] * 0.36
        self._draw_one_stirrer(painter, g["aer_x"] - aer_offset, g["aer_stirrer_y"],
                               g["y_mid"] - g["aer_hh"])
        self._draw_one_stirrer(painter, g["aer_x"] + aer_offset, g["aer_stirrer_y"],
                               g["y_mid"] - g["aer_hh"])

    def _draw_one_stirrer(self, painter: QPainter, cx: float,
                          sy: float, vessel_top: float) -> None:
        """Shaft → motor box → 3-blade propeller cross."""
        # Shaft
        painter.setPen(QPen(QColor("#34495e"), 2.0, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(cx, sy + 10), QPointF(cx, vessel_top))

        # Motor box
        mw, mh = 18, 11
        motor = QRectF(cx - mw / 2, sy - mh / 2, mw, mh)
        painter.setPen(QPen(QColor("#2c3e50"), 1.5))
        painter.setBrush(QBrush(QColor("#7f8c8d")))
        painter.drawRoundedRect(motor, 3, 3)

        # 3-blade propeller (60° apart)
        blade_len = 9
        painter.setPen(QPen(QColor("#1a252f"), 2.5, Qt.SolidLine, Qt.RoundCap))
        blade_y = sy + 16
        for angle_deg in (0, 60, 120):
            rad = math.radians(angle_deg)
            dx = math.cos(rad) * blade_len
            dy = math.sin(rad) * blade_len
            painter.drawLine(
                QPointF(cx - dx, blade_y - dy),
                QPointF(cx + dx, blade_y + dy),
            )

    # ── DO probe on aeration tank ──────────────────────────────────────────────
    def _draw_do_probe(self, painter: QPainter, g: dict) -> None:
        """Thin DO probe inserted from above into the Aeration Tank."""
        cx    = g["aer_x"] + g["aer_hw"] * 0.54
        y_top = g["y_mid"] - g["aer_hh"]
        y_tip = g["y_mid"] - g["aer_hh"] * 0.32

        painter.setPen(QPen(QColor("#1a5276"), 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(cx, y_top - 6), QPointF(cx, y_tip))

        painter.setPen(QPen(QColor("#1a5276"), 1.5))
        painter.setBrush(QBrush(QColor("#5dade2")))
        painter.drawEllipse(QPointF(cx, y_tip), 3.5, 3.5)

        font = QFont()
        font.setPointSize(6)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#1a5276")))
        painter.drawText(QRectF(cx - 12, y_top - 20, 24, 14), Qt.AlignCenter, "DO")

    # ── Sampling points ────────────────────────────────────────────────────────
    def _draw_sampling_points(self, painter: QPainter, g: dict) -> None:
        y   = g["y_mid"]
        rsp = max(5.0, g["aer_hw"] * 0.10)

        sp1 = g["x_feed"] + (g["pst_x"] - g["pst_tw"] - g["x_feed"]) * 0.50
        sp2 = (g["pst_x"] + g["pst_tw"] + g["aer_x"] - g["aer_hw"]) * 0.50
        sp3 = (g["aer_x"] + g["aer_hw"] + g["cla_x"] - g["cla_hw"]) * 0.50
        sp4 = g["cla_x"] + g["cla_hw"] + (g["x_effl"] - g["cla_x"] - g["cla_hw"]) * 0.45

        font = QFont()
        font.setPointSize(max(7, int(rsp * 1.25)))
        font.setBold(True)
        painter.setFont(font)
        painter.setOpacity(1.0)

        for px, label in [(sp1, "SP1"), (sp2, "SP2"), (sp3, "SP3"), (sp4, "SP4")]:
            painter.setPen(QPen(C_SP, 2.0))
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(QPointF(px, y), rsp, rsp)
            painter.setPen(QPen(C_SP))
            painter.drawText(QRectF(px - 22, y - rsp - 18, 44, 16),
                             Qt.AlignCenter, label)

    # ── DO Meter panel (left wall instrument) ─────────────────────────────────
    def _draw_do_meter_panel(self, painter: QPainter, g: dict) -> None:
        px, py, pw, ph = g["do_px"], g["do_py"], g["do_pw"], g["do_ph"]
        rect = QRectF(px, py, pw, ph)

        painter.setPen(QPen(C_PANEL_BORD, 1.5))
        painter.setBrush(QBrush(C_PANEL_BG))
        painter.drawRoundedRect(rect, 4, 4)

        # LED screen (top 42%)
        screen = QRectF(px + 3, py + 4, pw - 6, ph * 0.42)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0d2a1e")))
        painter.drawRoundedRect(screen, 3, 3)

        do_val = None
        aer = self._today_data.get("aeration")
        if aer and aer.get("do_mgl") is not None:
            do_val = aer["do_mgl"]

        font = QFont()
        font.setPointSize(max(5, int(pw * 0.14)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#39ff14")))  # green LED text
        txt = f"{do_val:.1f}\nmg/L" if do_val is not None else "─\nmg/L"
        painter.drawText(screen, Qt.AlignCenter, txt)

        # Panel label
        font2 = QFont()
        font2.setPointSize(max(5, int(pw * 0.12)))
        font2.setBold(True)
        painter.setFont(font2)
        painter.setPen(QPen(QColor("#aab8c2")))
        painter.drawText(QRectF(px, py + ph * 0.47, pw, ph * 0.28),
                         Qt.AlignCenter, LABELS["do_meter"])

        # Dashed cable from panel to aeration tank DO probe
        probe_x = g["aer_x"] + g["aer_hw"] * 0.54
        probe_y = g["y_mid"] - g["aer_hh"] - 6
        painter.setPen(QPen(QColor("#4a6fa5"), 1.0, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(px + pw / 2, py + ph), QPointF(probe_x, probe_y))

    # ── RAS Controller panel (right wall) ─────────────────────────────────────
    def _draw_ras_controller_panel(self, painter: QPainter, g: dict) -> None:
        """Sediment return pump controller — shows RAS ratio and running status."""
        px, py, pw, ph = g["ras_px"], g["ras_py"], g["ras_pw"], g["ras_ph"]
        rect = QRectF(px, py, pw, ph)

        painter.setPen(QPen(C_PANEL_BORD, 1.5))
        painter.setBrush(QBrush(C_PANEL_BG))
        painter.drawRoundedRect(rect, 4, 4)

        # Title strip
        title = QRectF(px + 2, py + 3, pw - 4, ph * 0.22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#1a3a5c")))
        painter.drawRoundedRect(title, 3, 3)
        ft = QFont()
        ft.setPointSize(max(4, int(pw * 0.105)))
        ft.setBold(True)
        painter.setFont(ft)
        painter.setPen(QPen(QColor("#aab8c2")))
        painter.drawText(title, Qt.AlignCenter, LABELS["pump_title"])

        # RAS ratio value
        ratio = self._ras_ratio if self._ras_ratio is not None else 1.0
        fv = QFont()
        fv.setPointSize(max(5, int(pw * 0.115)))
        fv.setBold(True)
        painter.setFont(fv)
        painter.setPen(QPen(QColor("#e8f4f8")))
        painter.drawText(QRectF(px, py + ph * 0.27, pw, ph * 0.28),
                         Qt.AlignCenter, f"RAS {ratio:.1f}:1")

        # Status indicator dot (green = running)
        dot_cx = px + pw * 0.50
        dot_cy = py + ph * 0.69
        dot_r  = max(3.0, pw * 0.095)
        painter.setPen(QPen(QColor("#145a32"), 1.0))
        painter.setBrush(QBrush(QColor("#2ecc71")))
        painter.drawEllipse(QPointF(dot_cx, dot_cy), dot_r, dot_r)

        fs = QFont()
        fs.setPointSize(max(4, int(pw * 0.09)))
        painter.setFont(fs)
        painter.setPen(QPen(QColor("#aab8c2")))
        painter.drawText(QRectF(px, py + ph * 0.80, pw, ph * 0.18),
                         Qt.AlignCenter, "RUNNING")

    # ── Loop labels ────────────────────────────────────────────────────────────
    def _draw_loop_labels(self, painter: QPainter, g: dict) -> None:
        font = QFont()
        font.setPointSize(max(7, int(g["aer_hw"] * 0.12)))
        font.setBold(True)
        painter.setFont(font)
        painter.setOpacity(1.0)

        # Centre the label on the horizontal RAS segment, just above the pipe.
        lx = (g["cla_x"] + g["aer_x"] - g["aer_hw"]) / 2
        painter.setPen(QPen(C_RAS))
        painter.drawText(QRectF(lx - 28, g["y_ras"] - 18, 56, 16),
                         Qt.AlignCenter, "RAS")

    def _draw_was_label(self, painter: QPainter, g: dict) -> None:
        font = QFont()
        font.setPointSize(max(7, int(g["aer_hw"] * 0.12)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_WAS))
        painter.setOpacity(1.0)
        # Place label to the right of the vertical WAS line, at its midpoint.
        was_mid_y = (g["y_mid"] + g["cla_hh"] + g["y_was_end"]) / 2
        painter.drawText(
            QRectF(g["cla_x"] + 6, was_mid_y - 9, 46, 18),
            Qt.AlignLeft | Qt.AlignVCenter, "WAS",
        )

    # ── Data overlays (DO / pH badges under vessels) ───────────────────────────
    def _draw_data_overlays(self, painter: QPainter, g: dict) -> None:
        if not self._today_data:
            return
        painter.setOpacity(1.0)
        font = QFont()
        font.setPointSize(max(6, int(g["aer_hw"] * 0.13)))
        painter.setFont(font)

        zones_geo = [
            ("primary_settling", g["pst_x"],  g["y_mid"] + g["pst_ht"],  g["pst_tw"] * 1.8),
            ("aeration",         g["aer_x"],  g["y_mid"] + g["aer_hh"],  g["aer_hw"] * 1.7),
            ("clarifier",        g["cla_x"],  g["y_mid"] + g["cla_hh"],  g["cla_hw"] * 5.5),
        ]
        for zone, cx, y_bot, badge_w in zones_geo:
            data = self._today_data.get(zone)
            if not data:
                continue
            lines = []
            if data.get("do_mgl") is not None:
                lines.append(f"DO {data['do_mgl']:.1f}")
            if data.get("ph") is not None:
                lines.append(f"pH {data['ph']:.1f}")
            if not lines:
                continue
            bh = g["aer_hh"] * 0.52
            badge = QRectF(cx - badge_w / 2, y_bot + 5, badge_w, bh)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(C_OVERLAY_BG))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QPen(C_TEXT))
            painter.drawText(badge, Qt.AlignCenter, "\n".join(lines))

    # ── Arrowhead helper ───────────────────────────────────────────────────────
    def _arrowhead(self, painter, tip, direction, color, size=9) -> None:
        s, h = size, size * 0.52
        match direction:
            case "right": pts = [tip, QPointF(tip.x()-s, tip.y()-h), QPointF(tip.x()-s, tip.y()+h)]
            case "left":  pts = [tip, QPointF(tip.x()+s, tip.y()-h), QPointF(tip.x()+s, tip.y()+h)]
            case "down":  pts = [tip, QPointF(tip.x()-h, tip.y()-s), QPointF(tip.x()+h, tip.y()-s)]
            case "up":    pts = [tip, QPointF(tip.x()-h, tip.y()+s), QPointF(tip.x()+h, tip.y()+s)]
            case _:       return
        painter.setOpacity(1.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF(pts))
        painter.setBrush(Qt.NoBrush)

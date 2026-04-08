"""
reactor_diagram.py — Digital Reactor process flow diagram (QPainter).

Scientific aesthetic improvements:
  • Engineering grid background (P&ID / chart-paper feel)
  • 3-layer cylindrical pipe rendering (shadow + barrel + specular highlight)
  • Animated aeration bubbles inside the aerobic zone (scientifically accurate)
  • Clarifier sedimentation layers (clear zone / mixed zone / sludge blanket)
  • Zone liquid surface reflection ellipses (tanks containing liquid)
  • All geometry cached on first paint and invalidated on resize.
  • Timer paused when widget is hidden (avoids unnecessary CPU use).

Layout:
        [FEED]──SP1──●ANAEROBIC●──SP2──●ANOXIC●──SP3──●AEROBIC●──◀──▽CLARIFIER▽──SP4──[EFFLUENT]
                                  ↑ a-recycle (above) ↑
         ←──────────────────── RAS (below) ─────────────────────────────┘
                                                              ↓ WAS
"""

import random
from datetime import date

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath,
    QFont, QPolygonF, QRadialGradient, QLinearGradient, QRegion,
)

from core.database import get_session
from core.models import DailyReading, Experiment


# ── Palette ────────────────────────────────────────────────────────────────────
C_ANAEROBIC  = QColor("#8e44ad")
C_ANOXIC     = QColor("#2471a3")
C_AEROBIC    = QColor("#1e8449")
C_CLARIFIER  = QColor("#717d7e")
C_PIPE_RAIL  = QColor("#2c3e50")   # outer pipe colour
C_PIPE_HIGH  = QColor("#566573")   # inner pipe highlight
C_PIPE_SPEC  = QColor("#8ea8ba")   # specular highlight (new 3-layer pipe)
C_PIPE_SHAD  = QColor("#1a252f")   # shadow underside (new 3-layer pipe)
C_FLOW       = QColor("#5dade2")   # main flow particles
C_RAS        = QColor("#e74c3c")   # RAS particles
C_ARECYCLE   = QColor("#e67e22")   # a-recycle particles
C_WAS        = QColor("#c0392b")   # WAS particles
C_SP         = QColor("#e74c3c")   # sampling point marker
C_TEXT       = QColor("#1c2833")
C_TEXT_ZONE  = QColor("#ffffff")
C_OVERLAY_BG = QColor(255, 255, 255, 195)

# ── Animation constants ────────────────────────────────────────────────────────
TIMER_MS       = 66        # ~15 fps
PARTICLE_SPEED = 0.025
N_PARTICLES    = 2         # particles per pipe segment

# Tail: list of (t_offset_behind, opacity, radius_px)
TAIL = [(0.0, 1.00, 4.5), (PARTICLE_SPEED, 0.45, 3.2), (PARTICLE_SPEED * 2, 0.18, 2.0)]

# Clarifier sedimentation band colours (alpha pre-set)
C_CLA_CLEAR  = QColor(220, 233, 240, 204)   # top 40% — clarified water
C_CLA_MIXED  = QColor(181, 200, 212, 230)   # middle 25% — transition
C_CLA_SLUDGE = QColor(141, 159, 168, 255)   # bottom 35% — sludge blanket


class ReactorDiagram(QWidget):
    """
    Scalable QPainter widget for the reactor process flow diagram.
    Animation runs via a QTimer; geometry is cached after first paint.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        # Particle t-values per segment — evenly spaced [0, 1/N, 2/N ...]
        self._pts: dict[str, list[float]] = {
            seg: [i / N_PARTICLES for i in range(N_PARTICLES)]
            for seg in ("feed", "ana_anx", "anx_aer", "aer_cla",
                        "effluent", "ras", "arecycle", "was")
        }

        # Geometry cache — rebuilt on resize
        self._geo: dict | None = None
        self._ras_path:      QPainterPath | None = None
        self._arecycle_path: QPainterPath | None = None

        self._today_data: dict[str, dict] = {}
        self._load_today_data()

        # Aeration bubbles (aerobic zone only)
        self._init_bubbles()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TIMER_MS)

    # ── Bubble initialisation ──────────────────────────────────────────────────
    def _init_bubbles(self) -> None:
        """Create the bubble state list for the aerobic zone animation."""
        self._bubbles: list[dict] = []
        for _ in range(12):
            self._bubbles.append({
                "x_off":   random.uniform(-0.60, 0.60),   # fraction of r
                "y_frac":  random.uniform(-0.70, 0.70),   # fraction of r from zone centre
                "r_px":    random.uniform(2.5, 5.5),      # pixel radius — larger for visibility
                "opacity": random.uniform(0.50, 0.85),
                "speed":   random.uniform(0.008, 0.016),  # fraction-of-r per tick
            })

    # ── Timer ──────────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        for seg in self._pts:
            self._pts[seg] = [(t + PARTICLE_SPEED) % 1.0 for t in self._pts[seg]]
        # Advance bubbles (reset handled in draw — keeps _tick geometry-free)
        for b in self._bubbles:
            b["y_frac"] -= b["speed"]
        self.update()

    # ── Resize — invalidate geometry cache ────────────────────────────────────
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._geo = None
        self._ras_path = None
        self._arecycle_path = None

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
        """Load today's DO and pH from the active experiment."""
        today = date.today()
        self._today_data = {}
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
                    }
        except Exception:
            self._today_data = {}

    # ── Paint ──────────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()

        # 1. Scientific grid background
        self._draw_background(painter, w, h)

        # Build/reuse geometry cache
        if self._geo is None:
            self._geo = self._build_geometry(w, h)
            self._ras_path      = self._make_ras_path(self._geo)
            self._arecycle_path = self._make_arecycle_path(self._geo)

        g = self._geo

        # Draw order: loops → pipes → particles → zones → bubbles → SP → labels → data
        self._draw_loop_rails(painter, g)
        self._draw_pipe_rails(painter, g)
        self._draw_particles(painter, g)
        self._draw_zones(painter, g)
        self._draw_aerobic_bubbles(painter, g)
        self._draw_sampling_points(painter, g)
        self._draw_feed_effluent_labels(painter, g)
        self._draw_loop_labels(painter, g)
        self._draw_was_label(painter, g)
        self._draw_data_overlays(painter, g)

        painter.end()

    # ── Geometry ───────────────────────────────────────────────────────────────
    def _build_geometry(self, w: int, h: int) -> dict:
        r = min(w, h) * 0.092
        ana_x = w * 0.190
        anx_x = w * 0.390
        aer_x = w * 0.595
        cla_x = w * 0.788
        y_mid = h * 0.475
        cla_hw = r * 1.20   # wider — sedimentation bands more visible
        cla_hh = r * 1.50   # taller — more depth to show settling zones
        y_ras      = h * 0.800
        y_arecycle = h * 0.115
        y_was_end  = h * 0.912
        x_right = w - 88
        return dict(
            w=w, h=h, r=r,
            ana_x=ana_x, anx_x=anx_x, aer_x=aer_x, cla_x=cla_x,
            y_mid=y_mid, cla_hw=cla_hw, cla_hh=cla_hh,
            y_ras=y_ras, y_arecycle=y_arecycle,
            y_was_end=y_was_end, x_right=x_right,
        )

    # ── Pipe path builders ─────────────────────────────────────────────────────
    def _make_ras_path(self, g: dict) -> QPainterPath:
        x_s = g["cla_x"];  y_s = g["y_mid"] + g["cla_hh"] * 0.60
        x_e = g["ana_x"];  y_e = g["y_mid"] + g["r"]
        y_b = g["y_ras"];  cr  = 14
        p = QPainterPath()
        p.moveTo(x_s, y_s)
        p.lineTo(x_s, y_b - cr);  p.quadTo(x_s, y_b, x_s - cr, y_b)
        p.lineTo(x_e + cr, y_b);  p.quadTo(x_e, y_b, x_e, y_b - cr)
        p.lineTo(x_e, y_e)
        return p

    def _make_arecycle_path(self, g: dict) -> QPainterPath:
        x_s = g["aer_x"];  y_s = g["y_mid"] - g["r"]
        x_e = g["anx_x"];  y_e = g["y_mid"] - g["r"]
        y_t = g["y_arecycle"];  cr = 14
        p = QPainterPath()
        p.moveTo(x_s, y_s)
        p.lineTo(x_s, y_t + cr);  p.quadTo(x_s, y_t, x_s - cr, y_t)
        p.lineTo(x_e + cr, y_t);  p.quadTo(x_e, y_t, x_e, y_t + cr)
        p.lineTo(x_e, y_e)
        return p

    # ── NEW: Draw 1 — Scientific grid background ───────────────────────────────
    def _draw_background(self, painter: QPainter, w: int, h: int) -> None:
        """
        Subtle engineering-style background:
        vertical gradient fill + fine grid lines (P&ID / lab chart-paper feel).
        """
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor("#f4f7f9"))
        bg_grad.setColorAt(1.0, QColor("#edf1f5"))
        painter.fillRect(0, 0, w, h, QBrush(bg_grad))

        grid_pen = QPen(QColor(220, 228, 234, 178), 0.5, Qt.SolidLine)
        painter.setPen(grid_pen)
        step = 48
        for x in range(0, w, step):
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        for y in range(0, h, step):
            painter.drawLine(QPointF(0, y), QPointF(w, y))

        painter.setOpacity(1.0)

    # ── Draw: loop rails ───────────────────────────────────────────────────────
    def _draw_loop_rails(self, painter: QPainter, g: dict) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_RAS.darker(130), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._ras_path)
        self._arrowhead(painter, QPointF(g["ana_x"], g["y_mid"] + g["r"]), "up", C_RAS, 9)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_ARECYCLE.darker(120), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._arecycle_path)
        self._arrowhead(painter, QPointF(g["anx_x"], g["y_mid"] - g["r"]), "down", C_ARECYCLE, 9)

        x   = g["cla_x"]
        y_s = g["y_mid"] + g["cla_hh"] * 0.60
        y_e = g["y_was_end"]
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_WAS.darker(120), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(x, y_s), QPointF(x, y_e))
        self._arrowhead(painter, QPointF(x, y_e), "down", C_WAS, 8)

    # ── IMPROVED: Draw 2 — 3-layer cylindrical pipe rails ─────────────────────
    def _draw_pipe_rails(self, painter: QPainter, g: dict) -> None:
        """
        Straight pipe segments rendered as 3 layers back-to-front:
          1. Shadow underside  (6px, +1.2px y, very dark)
          2. Main barrel       (4px, centre, dark navy)
          3. Specular highlight(1.2px, -1.0px y, steel blue)
        Creates a cylindrical tube illusion from a single painted line.
        """
        y  = g["y_mid"]
        r  = g["r"]
        cw = g["cla_hw"]
        xr = g["x_right"]

        segs = [
            (g["w"] * 0.046,  g["ana_x"] - r),
            (g["ana_x"] + r,  g["anx_x"] - r),
            (g["anx_x"] + r,  g["aer_x"] - r),
            (g["aer_x"] + r,  g["cla_x"] - cw - 2),
            (g["cla_x"] + cw + 2, xr - 6),
        ]

        for x1, x2 in segs:
            # Layer 1 — shadow / underside (drawn first, visually deepest)
            painter.setPen(QPen(C_PIPE_SHAD, 6.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y + 1.2), QPointF(x2, y + 1.2))
            # Layer 2 — main barrel
            painter.setPen(QPen(C_PIPE_RAIL, 4.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
            # Layer 3 — specular top-lit reflection
            painter.setPen(QPen(C_PIPE_SPEC, 1.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y - 1.0), QPointF(x2, y - 1.0))
            # Arrowhead
            self._arrowhead(painter, QPointF(x2, y), "right", C_PIPE_RAIL, 9)

    # ── Draw: particles (unchanged) ────────────────────────────────────────────
    def _draw_particles(self, painter: QPainter, g: dict) -> None:
        y  = g["y_mid"]
        r  = g["r"]
        cw = g["cla_hw"]
        xr = g["x_right"]
        straight = [
            (QPointF(g["w"] * 0.046, y),  QPointF(g["ana_x"] - r, y),     "feed",     C_FLOW),
            (QPointF(g["ana_x"] + r, y),  QPointF(g["anx_x"] - r, y),     "ana_anx",  C_FLOW),
            (QPointF(g["anx_x"] + r, y),  QPointF(g["aer_x"] - r, y),     "anx_aer",  C_FLOW),
            (QPointF(g["aer_x"] + r, y),  QPointF(g["cla_x"] - cw - 2,y), "aer_cla",  C_FLOW),
            (QPointF(g["cla_x"]+cw+2, y), QPointF(xr - 6, y),             "effluent",  C_FLOW),
            (QPointF(g["cla_x"], g["y_mid"] + g["cla_hh"] * 0.60),
             QPointF(g["cla_x"], g["y_was_end"]),                          "was",      C_WAS),
        ]
        painter.setPen(Qt.NoPen)
        for p1, p2, key, color in straight:
            self._draw_seg_particles(painter, self._pts[key], p1, p2, color)
        self._draw_path_particles(painter, self._pts["ras"],      self._ras_path,      C_RAS)
        self._draw_path_particles(painter, self._pts["arecycle"], self._arecycle_path, C_ARECYCLE)
        painter.setOpacity(1.0)

    def _draw_seg_particles(self, painter, ts, p1, p2, color) -> None:
        for t in ts:
            for dt, opacity, radius in TAIL:
                t_g = (t - dt) % 1.0
                pos = QPointF(p1.x() + t_g*(p2.x()-p1.x()), p1.y() + t_g*(p2.y()-p1.y()))
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

    # ── IMPROVED: Draw 3 — Zone shapes with reflection + clarifier layers ──────
    def _draw_zones(self, painter: QPainter, g: dict) -> None:
        """
        Three gradient sphere circles + clarifier triangle.
        New: liquid surface reflection ellipse on each zone circle.
        New: sedimentation layers inside the clarifier triangle.
        """
        r    = g["r"]
        y    = g["y_mid"]
        font = QFont()
        font.setPointSize(max(7, int(r * 0.20)))
        font.setBold(True)
        painter.setFont(font)
        painter.setOpacity(1.0)

        for cx, base_color, label in [
            (g["ana_x"], C_ANAEROBIC, "ANAEROBIC"),
            (g["anx_x"], C_ANOXIC,   "ANOXIC"),
            (g["aer_x"], C_AEROBIC,  "AEROBIC"),
        ]:
            # Drop shadow
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 55)))
            painter.drawEllipse(QPointF(cx + 4, y + 5), r, r)

            # Sphere gradient — focal point upper-left
            grad = QRadialGradient(cx, y, r * 1.05)
            grad.setFocalPoint(QPointF(cx - r * 0.38, y - r * 0.38))
            grad.setColorAt(0.0,  base_color.lighter(185))
            grad.setColorAt(0.35, base_color.lighter(115))
            grad.setColorAt(1.0,  base_color.darker(155))
            painter.setPen(QPen(base_color.darker(140), 1.5))
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(cx, y), r, r)

            # NEW: Liquid surface reflection — horizontal white sheen near top
            refl_cy = y - r * 0.52
            refl_rw = r * 0.55           # half-width
            refl_rh = r * 0.09           # half-height
            refl_grad = QLinearGradient(cx - refl_rw, refl_cy, cx + refl_rw, refl_cy)
            refl_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            refl_grad.setColorAt(0.5, QColor(255, 255, 255, 89))
            refl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(refl_grad))
            painter.drawEllipse(QPointF(cx, refl_cy), refl_rw, refl_rh)

            # Zone label (on top of reflection)
            painter.setPen(QPen(C_TEXT_ZONE))
            painter.drawText(QRectF(cx - r, y - r, r * 2, r * 2), Qt.AlignCenter, label)

        # ── Clarifier triangle ─────────────────────────────────────────────────
        cx  = g["cla_x"]
        chw = g["cla_hw"]
        chh = g["cla_hh"]
        ty  = y - chh * 0.58
        by  = y + chh * 0.58
        pts = [QPointF(cx - chw, ty), QPointF(cx + chw, ty), QPointF(cx, by)]
        total_h = by - ty

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawPolygon(QPolygonF([QPointF(p.x() + 4, p.y() + 5) for p in pts]))

        # Base gradient fill
        grad2 = QRadialGradient(cx, ty + chh * 0.3, chh * 1.1)
        grad2.setColorAt(0.0, C_CLARIFIER.lighter(145))
        grad2.setColorAt(1.0, C_CLARIFIER.darker(150))
        painter.setPen(QPen(C_CLARIFIER.darker(130), 1.5))
        painter.setBrush(QBrush(grad2))
        painter.drawPolygon(QPolygonF(pts))

        # NEW: Sedimentation layers clipped to triangle shape
        cla_path = QPainterPath()
        cla_path.addPolygon(QPolygonF(pts))
        cla_path.closeSubpath()

        painter.save()
        painter.setClipPath(cla_path)
        painter.setPen(Qt.NoPen)

        # Clear zone — top 40%: clarified water
        painter.setBrush(QBrush(C_CLA_CLEAR))
        painter.drawRect(QRectF(cx - chw, ty, chw * 2, total_h * 0.40))

        # Mixed zone — next 25%: transition layer
        painter.setBrush(QBrush(C_CLA_MIXED))
        painter.drawRect(QRectF(cx - chw, ty + total_h * 0.40, chw * 2, total_h * 0.25))

        # Sludge blanket — bottom 35%
        painter.setBrush(QBrush(C_CLA_SLUDGE))
        painter.drawRect(QRectF(cx - chw, ty + total_h * 0.65, chw * 2, total_h * 0.35))

        # Depth gradient overlay: slight white tint at top → dark tint at bottom
        depth_grad = QLinearGradient(0, ty, 0, by)
        depth_grad.setColorAt(0.0, QColor(255, 255, 255, 35))
        depth_grad.setColorAt(1.0, QColor(0,   0,   0,   45))
        painter.setBrush(QBrush(depth_grad))
        painter.drawRect(QRectF(cx - chw, ty, chw * 2, total_h))

        painter.restore()   # restores clip, pen, brush, opacity

        # Redraw outline on top of sedimentation bands
        painter.setPen(QPen(C_CLARIFIER.darker(130), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF(pts))

        # Label — font capped so text always fits inside the triangle top area.
        # The triangle is widest at ty; usable width there is chw*2 minus ~20% margins.
        clf = QFont()
        clf.setPointSize(max(5, int(chw * 0.14)))   # smaller coefficient keeps it inside
        clf.setBold(True)
        painter.setFont(clf)
        painter.setPen(QPen(C_TEXT_ZONE))
        painter.drawText(
            QRectF(cx - chw * 0.78, ty + chh * 0.08, chw * 1.56, chh * 0.40),
            Qt.AlignCenter, "CLARIFIER",
        )

    # ── NEW: Draw 4 — Aeration bubbles in aerobic zone ────────────────────────
    def _draw_aerobic_bubbles(self, painter: QPainter, g: dict) -> None:
        """
        Animated rising bubbles inside the aerobic zone circle only.
        Communicates active aeration — scientifically accurate.
        Bubbles are clipped to the circle boundary via QRegion.
        Bubble reset (y escape check) happens here, keeping _tick geometry-free.
        """
        r  = g["r"]
        cx = g["aer_x"]
        cy = g["y_mid"]

        # Clip drawing to the aerobic circle bounding rect (elliptical region)
        clip_rect = QRect(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        clip_region = QRegion(clip_rect, QRegion.RegionType.Ellipse)
        painter.setClipRegion(clip_region)
        painter.setClipping(True)

        bubble_fill   = QColor(255, 255, 255, 160)   # white, ~63% opacity
        bubble_border = QColor(150, 220, 235, 220)   # light cyan border

        painter.setPen(QPen(bubble_border, 1.2))

        for b in self._bubbles:
            # Reset if bubble escaped the top of the zone
            if b["y_frac"] < -0.82:
                b["y_frac"]  = 0.70
                b["x_off"]   = random.uniform(-0.55, 0.55)
                b["r_px"]    = random.uniform(1.2, 2.5)
                b["opacity"] = random.uniform(0.40, 0.80)

            bx = cx + b["x_off"] * r
            by = cy + b["y_frac"] * r
            br = b["r_px"]

            painter.setOpacity(b["opacity"])
            painter.setBrush(QBrush(bubble_fill))
            painter.drawEllipse(QPointF(bx, by), br, br)

        painter.setClipping(False)
        painter.setOpacity(1.0)
        painter.setBrush(Qt.NoBrush)

    # ── Draw: sampling points (unchanged) ─────────────────────────────────────
    def _draw_sampling_points(self, painter: QPainter, g: dict) -> None:
        y   = g["y_mid"]
        r   = g["r"]
        cw  = g["cla_hw"]
        xr  = g["x_right"]
        rsp = max(5.0, r * 0.13)

        sp1 = g["w"] * 0.046 + (g["ana_x"] - r - g["w"] * 0.046) * 0.40
        sp2 = (g["ana_x"] + r + g["anx_x"] - r) / 2
        sp3 = (g["aer_x"] + r + g["cla_x"] - cw) / 2
        sp4 = g["cla_x"] + cw + (xr - 6 - g["cla_x"] - cw) * 0.45

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
            painter.drawText(QRectF(px - 22, y - rsp - 18, 44, 16), Qt.AlignCenter, label)

    # ── Draw: FEED / EFFLUENT labels (unchanged) ───────────────────────────────
    def _draw_feed_effluent_labels(self, painter: QPainter, g: dict) -> None:
        y = g["y_mid"]
        font = QFont()
        font.setPointSize(max(7, int(g["r"] * 0.18)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT))
        painter.setOpacity(1.0)
        painter.drawText(QRectF(2, y - 18, 56, 36), Qt.AlignLeft | Qt.AlignVCenter, "FEED")
        painter.drawText(QRectF(g["x_right"] + 2, y - 18, 84, 36), Qt.AlignLeft | Qt.AlignVCenter, "EFFLUENT")

    # ── Draw: loop labels (unchanged) ─────────────────────────────────────────
    def _draw_loop_labels(self, painter: QPainter, g: dict) -> None:
        font = QFont()
        font.setPointSize(max(7, int(g["r"] * 0.16)))
        font.setBold(True)
        painter.setFont(font)
        painter.setOpacity(1.0)

        lx_ras = (g["cla_x"] + g["ana_x"]) / 2
        painter.setPen(QPen(C_RAS))
        painter.drawText(QRectF(lx_ras - 28, g["y_ras"] + 4, 56, 16), Qt.AlignCenter, "RAS")

        lx_arc = (g["aer_x"] + g["anx_x"]) / 2
        painter.setPen(QPen(C_ARECYCLE))
        painter.drawText(QRectF(lx_arc - 38, g["y_arecycle"] - 18, 76, 16), Qt.AlignCenter, "a-recycle")

    def _draw_was_label(self, painter: QPainter, g: dict) -> None:
        font = QFont()
        font.setPointSize(max(7, int(g["r"] * 0.16)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_WAS))
        painter.setOpacity(1.0)
        painter.drawText(
            QRectF(g["cla_x"] + 7, g["y_was_end"] - 10, 46, 18),
            Qt.AlignLeft | Qt.AlignVCenter, "WAS",
        )

    # ── Draw: today's DO / pH overlays (unchanged) ────────────────────────────
    def _draw_data_overlays(self, painter: QPainter, g: dict) -> None:
        if not self._today_data:
            return
        r     = g["r"]
        y_mid = g["y_mid"]
        bh    = r * 0.58
        font = QFont()
        font.setPointSize(max(6, int(r * 0.17)))
        painter.setFont(font)
        painter.setOpacity(1.0)
        for zone, cx in [("anaerobic", g["ana_x"]), ("anoxic", g["anx_x"]), ("aerobic", g["aer_x"])]:
            data = self._today_data.get(zone)
            if not data:
                continue
            lines = []
            if data.get("do_mgl") is not None:
                lines.append(f"DO {data['do_mgl']:.1f} mg/L")
            if data.get("ph") is not None:
                lines.append(f"pH {data['ph']:.1f}")
            if not lines:
                continue
            badge = QRectF(cx - r * 0.82, y_mid + r + 5, r * 1.64, bh)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(C_OVERLAY_BG))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QPen(C_TEXT))
            painter.drawText(badge, Qt.AlignCenter, "\n".join(lines))

    # ── Arrowhead helper (unchanged) ───────────────────────────────────────────
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

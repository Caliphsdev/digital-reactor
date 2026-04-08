"""
reactor_diagram.py — Digital Reactor process flow diagram (QPainter).

Visual improvements over the initial version:
  • Zone circles rendered with QRadialGradient (off-centre focal point) for a
    sphere/3D look — no flat discs.
  • Pipes drawn as a two-tone rail (dark outer + lighter inner highlight)
    so they read as physical tubes, not just lines.
  • Flow animated with moving particles (3 per pipe with a comet tail) using
    QPainterPath.pointAtPercent() for the loop paths and linear interpolation
    for straight segments.  Particles replace the old dash-offset trick which
    looked mechanical.
  • Particle opacity fades back (1.0 → 0.45 → 0.18) to show direction.
  • painter.setOpacity() used for fade effects (PySide6 QPainter API).
  • All geometry cached on first paint and invalidated on resize — no
    redundant recomputation every tick.
  • Clarifier made narrower and shifted left so the label always fits.
  • setRenderHint uses the PySide6 6.6 enum form: QPainter.RenderHint.*

Layout:
        [FEED]──SP1──●ANAEROBIC●──SP2──●ANOXIC●──SP3──●AEROBIC●──◀──▽CLARIFIER▽──SP4──[EFFLUENT]
                                  ↑ a-recycle (above) ↑
         ←──────────────────── RAS (below) ─────────────────────────────┘
                                                              ↓ WAS
"""

from datetime import date

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath,
    QFont, QPolygonF, QRadialGradient,
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
C_FLOW       = QColor("#5dade2")   # main flow particles
C_RAS        = QColor("#e74c3c")   # RAS particles
C_ARECYCLE   = QColor("#e67e22")   # a-recycle particles
C_WAS        = QColor("#c0392b")   # WAS particles
C_SP         = QColor("#e74c3c")   # sampling point marker
C_TEXT       = QColor("#1c2833")
C_TEXT_ZONE  = QColor("#ffffff")
C_OVERLAY_BG = QColor(255, 255, 255, 195)

# ── Animation constants ────────────────────────────────────────────────────────
TIMER_MS       = 66        # ~15 fps — imperceptibly different, 25% fewer callbacks
PARTICLE_SPEED = 0.025     # slightly faster step to compensate for lower fps
N_PARTICLES    = 2         # particles per pipe segment (was 3 — reduce CPU load)

# Tail: list of (t_offset_behind, opacity, radius_px)
TAIL = [(0.0, 1.00, 4.5), (PARTICLE_SPEED, 0.45, 3.2), (PARTICLE_SPEED * 2, 0.18, 2.0)]


class ReactorDiagram(QWidget):
    """
    Scalable QPainter widget for the reactor process flow.
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

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TIMER_MS)

    # ── Timer ──────────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        for seg in self._pts:
            self._pts[seg] = [(t + PARTICLE_SPEED) % 1.0 for t in self._pts[seg]]
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
        # Restart timer only when the diagram is actually on screen.
        # When hidden (other screens active) the timer is stopped so it doesn't
        # fire paintEvent callbacks 15x/sec while the user is elsewhere.
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
        painter.fillRect(0, 0, w, h, QColor("#f0f3f6"))

        # Build/reuse geometry cache
        if self._geo is None:
            self._geo = self._build_geometry(w, h)
            self._ras_path      = self._make_ras_path(self._geo)
            self._arecycle_path = self._make_arecycle_path(self._geo)

        g = self._geo

        # Draw order: loops → pipes → particles → zones → SP markers → labels → data
        self._draw_loop_rails(painter, g)
        self._draw_pipe_rails(painter, g)
        self._draw_particles(painter, g)
        self._draw_zones(painter, g)
        self._draw_sampling_points(painter, g)
        self._draw_feed_effluent_labels(painter, g)
        self._draw_loop_labels(painter, g)
        self._draw_was_label(painter, g)
        self._draw_data_overlays(painter, g)

        painter.end()

    # ── Geometry ───────────────────────────────────────────────────────────────
    def _build_geometry(self, w: int, h: int) -> dict:
        """
        Compute all pixel positions from widget dimensions.
        Called once per size; cached in self._geo.
        """
        r = min(w, h) * 0.092           # zone circle radius

        ana_x = w * 0.190
        anx_x = w * 0.390
        aer_x = w * 0.595
        cla_x = w * 0.788               # shifted left vs previous version

        y_mid = h * 0.475

        cla_hw = r * 0.86               # narrower clarifier — label fits
        cla_hh = r * 1.35

        y_ras      = h * 0.800
        y_arecycle = h * 0.115
        y_was_end  = h * 0.912

        x_right = w - 88               # reserved space for EFFLUENT label

        return dict(
            w=w, h=h, r=r,
            ana_x=ana_x, anx_x=anx_x, aer_x=aer_x, cla_x=cla_x,
            y_mid=y_mid,
            cla_hw=cla_hw, cla_hh=cla_hh,
            y_ras=y_ras, y_arecycle=y_arecycle,
            y_was_end=y_was_end,
            x_right=x_right,
        )

    # ── Pipe path builders ─────────────────────────────────────────────────────
    def _make_ras_path(self, g: dict) -> QPainterPath:
        """QPainterPath for the RAS loop (used for both rail and particles)."""
        x_s = g["cla_x"]
        y_s = g["y_mid"] + g["cla_hh"] * 0.60
        x_e = g["ana_x"]
        y_e = g["y_mid"] + g["r"]
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

    def _make_arecycle_path(self, g: dict) -> QPainterPath:
        """QPainterPath for the a-recycle loop."""
        x_s = g["aer_x"]
        y_s = g["y_mid"] - g["r"]
        x_e = g["anx_x"]
        y_e = g["y_mid"] - g["r"]
        y_t = g["y_arecycle"]
        cr  = 14
        p = QPainterPath()
        p.moveTo(x_s, y_s)
        p.lineTo(x_s, y_t + cr)
        p.quadTo(x_s, y_t, x_s - cr, y_t)
        p.lineTo(x_e + cr, y_t)
        p.quadTo(x_e, y_t, x_e, y_t + cr)
        p.lineTo(x_e, y_e)
        return p

    # ── Draw: pipe rails (non-animated structure) ──────────────────────────────
    def _draw_pipe_rails(self, painter: QPainter, g: dict) -> None:
        """
        Draw all straight pipe segments as two-tone rails:
        a wider dark outer line + a thinner lighter inner highlight.
        Arrowheads show direction.
        """
        y   = g["y_mid"]
        r   = g["r"]
        cw  = g["cla_hw"]
        xr  = g["x_right"]

        segs = [
            (g["w"] * 0.046,  g["ana_x"] - r),      # Feed → Anaerobic
            (g["ana_x"] + r,  g["anx_x"] - r),      # Ana → Anx
            (g["anx_x"] + r,  g["aer_x"] - r),      # Anx → Aer
            (g["aer_x"] + r,  g["cla_x"] - cw - 2), # Aer → Clarifier
            (g["cla_x"] + cw + 2, xr - 6),          # Clarifier → Effluent
        ]

        for x1, x2 in segs:
            # Outer dark rail
            painter.setPen(QPen(C_PIPE_RAIL, 4.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
            # Inner lighter highlight
            painter.setPen(QPen(C_PIPE_HIGH, 1.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y - 0.8), QPointF(x2, y - 0.8))
            # Arrowhead at the destination end
            self._arrowhead(painter, QPointF(x2, y), "right", C_PIPE_RAIL, 9)

    def _draw_loop_rails(self, painter: QPainter, g: dict) -> None:
        """
        Draw the RAS and a-recycle loop paths as solid dark rails
        with arrowheads, and the WAS vertical drop.
        """
        # RAS
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_RAS.darker(130), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._ras_path)
        self._arrowhead(painter, QPointF(g["ana_x"], g["y_mid"] + g["r"]), "up", C_RAS, 9)

        # a-recycle — reset brush after RAS arrowhead before drawing path
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_ARECYCLE.darker(120), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._arecycle_path)
        self._arrowhead(painter, QPointF(g["anx_x"], g["y_mid"] - g["r"]), "down", C_ARECYCLE, 9)

        # WAS — reset brush after a-recycle arrowhead before drawing line
        x     = g["cla_x"]
        y_s   = g["y_mid"] + g["cla_hh"] * 0.60
        y_e   = g["y_was_end"]
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(C_WAS.darker(120), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(x, y_s), QPointF(x, y_e))
        self._arrowhead(painter, QPointF(x, y_e), "down", C_WAS, 8)

    # ── Draw: particles ────────────────────────────────────────────────────────
    def _draw_particles(self, painter: QPainter, g: dict) -> None:
        """
        Draw all flow particles for every pipe segment.
        Each particle has a comet tail rendered with decreasing opacity.
        """
        y  = g["y_mid"]
        r  = g["r"]
        cw = g["cla_hw"]
        xr = g["x_right"]

        # Straight segment endpoints (P1, P2, segment_key, colour)
        straight = [
            (QPointF(g["w"] * 0.046, y),  QPointF(g["ana_x"] - r, y),     "feed",     C_FLOW),
            (QPointF(g["ana_x"] + r, y),  QPointF(g["anx_x"] - r, y),     "ana_anx",  C_FLOW),
            (QPointF(g["anx_x"] + r, y),  QPointF(g["aer_x"] - r, y),     "anx_aer",  C_FLOW),
            (QPointF(g["aer_x"] + r, y),  QPointF(g["cla_x"] - cw - 2,y), "aer_cla",  C_FLOW),
            (QPointF(g["cla_x"]+cw+2, y), QPointF(xr - 6, y),             "effluent",  C_FLOW),
            # WAS is vertical — treat as straight with rotated endpoints
            (QPointF(g["cla_x"], g["y_mid"] + g["cla_hh"] * 0.60),
             QPointF(g["cla_x"], g["y_was_end"]),                          "was",      C_WAS),
        ]

        painter.setPen(Qt.NoPen)
        for p1, p2, key, color in straight:
            self._draw_seg_particles(painter, self._pts[key], p1, p2, color)

        # Curved loop particles via QPainterPath.pointAtPercent
        self._draw_path_particles(painter, self._pts["ras"],      self._ras_path,      C_RAS)
        self._draw_path_particles(painter, self._pts["arecycle"], self._arecycle_path, C_ARECYCLE)

        painter.setOpacity(1.0)   # restore after particle draws

    def _draw_seg_particles(
        self,
        painter: QPainter,
        ts: list[float],
        p1: QPointF,
        p2: QPointF,
        color: QColor,
    ) -> None:
        """Render particles with comet tail for one straight segment."""
        for t in ts:
            for dt, opacity, radius in TAIL:
                t_g = (t - dt) % 1.0
                pos = QPointF(
                    p1.x() + t_g * (p2.x() - p1.x()),
                    p1.y() + t_g * (p2.y() - p1.y()),
                )
                painter.setOpacity(opacity)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pos, radius, radius)

    def _draw_path_particles(
        self,
        painter: QPainter,
        ts: list[float],
        path: QPainterPath,
        color: QColor,
    ) -> None:
        """Render particles with comet tail along a QPainterPath."""
        for t in ts:
            for dt, opacity, radius in TAIL:
                t_g = (t - dt) % 1.0
                pos  = path.pointAtPercent(t_g)
                painter.setOpacity(opacity)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pos, radius, radius)

    # ── Draw: zone shapes ──────────────────────────────────────────────────────
    def _draw_zones(self, painter: QPainter, g: dict) -> None:
        """
        Three gradient-filled circles and one clarifier triangle.
        QRadialGradient with an off-centre focal point gives each circle
        a sphere/3D appearance — the highlight sits at the upper-left.
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
            grad.setColorAt(0.0, base_color.lighter(185))
            grad.setColorAt(0.35, base_color.lighter(115))
            grad.setColorAt(1.0, base_color.darker(155))

            painter.setPen(QPen(base_color.darker(140), 1.5))
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(cx, y), r, r)

            # Label
            painter.setPen(QPen(C_TEXT_ZONE))
            painter.drawText(QRectF(cx - r, y - r, r * 2, r * 2), Qt.AlignCenter, label)

        # ── Clarifier triangle (gradient fill) ─────────────────────────────────
        cx  = g["cla_x"]
        chw = g["cla_hw"]
        chh = g["cla_hh"]
        ty  = y - chh * 0.58
        by  = y + chh * 0.58
        pts = [QPointF(cx - chw, ty), QPointF(cx + chw, ty), QPointF(cx, by)]

        # Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawPolygon(QPolygonF([QPointF(p.x() + 4, p.y() + 5) for p in pts]))

        # Gradient fill (top lighter, bottom darker)
        grad2 = QRadialGradient(cx, ty + chh * 0.3, chh * 1.1)
        grad2.setColorAt(0.0, C_CLARIFIER.lighter(145))
        grad2.setColorAt(1.0, C_CLARIFIER.darker(150))
        painter.setPen(QPen(C_CLARIFIER.darker(130), 1.5))
        painter.setBrush(QBrush(grad2))
        painter.drawPolygon(QPolygonF(pts))

        # Label — font sized to fit inside triangle
        clf = QFont()
        clf.setPointSize(max(6, int(chw * 0.22)))
        clf.setBold(True)
        painter.setFont(clf)
        painter.setPen(QPen(C_TEXT_ZONE))
        painter.drawText(
            QRectF(cx - chw * 0.88, ty + chh * 0.12, chw * 1.76, chh * 0.60),
            Qt.AlignCenter, "CLARIFIER",
        )

    # ── Draw: sampling points ──────────────────────────────────────────────────
    def _draw_sampling_points(self, painter: QPainter, g: dict) -> None:
        """SP1–SP4 markers: white circles with red border, label above."""
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

    # ── Draw: FEED / EFFLUENT labels ───────────────────────────────────────────
    def _draw_feed_effluent_labels(self, painter: QPainter, g: dict) -> None:
        """End-of-pipe labels. EFFLUENT starts at x_right with room to spare."""
        y = g["y_mid"]
        font = QFont()
        font.setPointSize(max(7, int(g["r"] * 0.18)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT))
        painter.setOpacity(1.0)
        painter.drawText(QRectF(2, y - 18, 56, 36), Qt.AlignLeft | Qt.AlignVCenter, "FEED")
        painter.drawText(QRectF(g["x_right"] + 2, y - 18, 84, 36), Qt.AlignLeft | Qt.AlignVCenter, "EFFLUENT")

    # ── Draw: loop labels ──────────────────────────────────────────────────────
    def _draw_loop_labels(self, painter: QPainter, g: dict) -> None:
        """'RAS' below the bottom run, 'a-recycle' above the top run."""
        font = QFont()
        font.setPointSize(max(7, int(g["r"] * 0.16)))
        font.setBold(True)
        painter.setFont(font)
        painter.setOpacity(1.0)

        # RAS label — centred between clarifier and anaerobic at y_ras
        lx_ras = (g["cla_x"] + g["ana_x"]) / 2
        painter.setPen(QPen(C_RAS))
        painter.drawText(QRectF(lx_ras - 28, g["y_ras"] + 4, 56, 16), Qt.AlignCenter, "RAS")

        # a-recycle — centred between aerobic and anoxic at y_arecycle
        lx_arc = (g["aer_x"] + g["anx_x"]) / 2
        painter.setPen(QPen(C_ARECYCLE))
        painter.drawText(QRectF(lx_arc - 38, g["y_arecycle"] - 18, 76, 16), Qt.AlignCenter, "a-recycle")

    def _draw_was_label(self, painter: QPainter, g: dict) -> None:
        """'WAS' label beside the WAS outlet arrow."""
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

    # ── Draw: today's DO / pH overlays ────────────────────────────────────────
    def _draw_data_overlays(self, painter: QPainter, g: dict) -> None:
        """
        Semi-transparent badge below each zone circle showing today's
        DO and pH if readings exist for the active experiment.
        """
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

    # ── Arrowhead helper ───────────────────────────────────────────────────────
    def _arrowhead(
        self,
        painter: QPainter,
        tip: QPointF,
        direction: str,
        color: QColor,
        size: float = 9,
    ) -> None:
        """Filled triangular arrowhead at `tip` pointing in `direction`."""
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
        painter.setBrush(Qt.NoBrush)   # always restore — prevents path fill bleed

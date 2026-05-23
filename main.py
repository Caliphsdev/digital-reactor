"""
main.py — Digital Reactor application entry point.

Run with:
    python main.py

On first run, reactor.db is created in %APPDATA%\\DigitalReactor\\ with all
tables.  On subsequent runs, pending schema migrations are applied automatically.
"""

import sys
import math
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QBrush, QPen,
    QLinearGradient, QRadialGradient, QPainterPath,
)

from core.database import init_db
from ui.theme import apply_theme

# ── Splash geometry ────────────────────────────────────────────────────────────
_SW, _SH  = 740, 460    # canvas size
_PROG_H   = 56          # bottom progress strip
_DIV_X    = 244         # left panel width

# CAS reactor zone palette — Primary Settling / Aeration / Clarifier / Effluent
_ZONE_COLS = ["#7b2d8b", "#0077b6", "#2d8b6f", "#e07b39"]


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _dot_grid(p: QPainter, x: int, y: int, w: int, h: int) -> None:
    """Very subtle dot matrix for an engineering-blueprint texture."""
    spacing = 16
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 12))
    for gy in range(y, y + h, spacing):
        for gx in range(x, x + w, spacing):
            p.drawEllipse(QPointF(gx, gy), 0.8, 0.8)


def _glow_text(p: QPainter, font: QFont, text: str,
               rect_args: tuple, align: Qt.AlignmentFlag,
               glow_col: QColor, main_col: QColor, layers: int = 3) -> None:
    """Draw text with a soft ambient glow: multiple translucent layers then solid."""
    p.setFont(font)
    x, y, w, h = rect_args
    for i in range(layers, 0, -1):
        alpha = int(50 / i)
        off   = i
        p.setPen(QColor(glow_col.red(), glow_col.green(), glow_col.blue(), alpha))
        p.drawText(x - off, y + off, w, h, align, text)
    p.setPen(main_col)
    p.drawText(x, y, w, h, align, text)


# ──────────────────────────────────────────────────────────────────────────────
#  Static base pixmap (drawn once at startup)
# ──────────────────────────────────────────────────────────────────────────────

def _make_base_pixmap() -> QPixmap:
    """
    Render the static portion of the splash and return it as a QPixmap.

    Layout
    ──────
    ┌── 5px accent bar (4 CAS zone colours) ──────────────────────────────┐
    │  LEFT PANEL (0–244)       │  RIGHT PANEL (244–740)                  │
    │  Dot-grid texture         │  [TUT badge]                            │
    │  "PROCESS  FLOW" header   │  DIGITAL  (tracked cyan)                │
    │  ──────────────────────   │  REACTOR  (hero — white + glow)         │
    │  ● PRIMARY SETTLING       │  ─────────────────────                  │
    │  ▼ connector              │  PFAS & CEC subtitle                    │
    │  ● AERATION TANK (glows)  │  Researcher name / institution          │
    │  ▼ connector              │  v1.0  OECD 303A  Phase ML  badges      │
    │  ● CLARIFIER              │  Developer credit                       │
    │  ▼ connector              │                                         │
    │  ● EFFLUENT STORAGE       │                                         │
    │  RAS dashed loop (left)   │                                         │
    ├── 56px progress strip ───────────────────────────────────────────── ┤
    │  ● ● ● ●  status text                               [pct%]          │
    │  ══════════════════ progress bar ══════════════════                 │
    └─────────────────────────────────────────────────────────────────────┘
    """
    W, H = _SW, _SH
    PH, DX = _PROG_H, _DIV_X

    pix = QPixmap(W, H)
    p   = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    # ── Full background ────────────────────────────────────────────────────────
    bg = QLinearGradient(0, 0, W, H)
    bg.setColorAt(0.0, QColor("#071923"))
    bg.setColorAt(0.6, QColor("#0b2535"))
    bg.setColorAt(1.0, QColor("#071623"))
    p.fillRect(0, 0, W, H, QBrush(bg))

    # ── Right-panel atmospheric radial glow ────────────────────────────────────
    glow = QRadialGradient(QPointF(W * 0.74, H * 0.38), 300)
    glow.setColorAt(0.0, QColor(0, 180, 216, 35))
    glow.setColorAt(0.5, QColor(0, 119, 182, 12))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(DX, 0, W - DX, H - PH, QBrush(glow))

    # ── Left panel solid overlay ───────────────────────────────────────────────
    lp = QLinearGradient(0, 0, DX, H - PH)
    lp.setColorAt(0.0, QColor("#0a1e2e"))
    lp.setColorAt(1.0, QColor("#071520"))
    p.fillRect(0, 0, DX, H - PH, QBrush(lp))

    _dot_grid(p, 0, 0, DX, H - PH)

    # Left panel divider line (gradient fade top/bottom)
    div = QLinearGradient(0, 0, 0, H - PH)
    div.setColorAt(0.0,  QColor(0, 212, 255, 0))
    div.setColorAt(0.15, QColor(0, 212, 255, 80))
    div.setColorAt(0.85, QColor(0, 212, 255, 60))
    div.setColorAt(1.0,  QColor(0, 212, 255, 0))
    p.fillRect(DX - 1, 0, 1, H - PH, QBrush(div))

    # ── Top accent bar — 4 zone segments ──────────────────────────────────────
    BAR_H = 5
    seg   = W // 4
    for i, col in enumerate(_ZONE_COLS):
        extra = (W % 4) if i == 3 else 0
        g = QLinearGradient(i * seg, 0, (i + 1) * seg, 0)
        g.setColorAt(0.0, QColor(col).lighter(140))
        g.setColorAt(1.0, QColor(col))
        p.fillRect(i * seg, 0, seg + extra, BAR_H, QBrush(g))

    # ── "PROCESS  FLOW" header ────────────────────────────────────────────────
    f_hdr = QFont("Segoe UI", 7, QFont.Bold)
    f_hdr.setLetterSpacing(QFont.AbsoluteSpacing, 3)
    p.setFont(f_hdr)
    p.setPen(QColor(0, 212, 255, 110))
    p.drawText(0, BAR_H, DX, 26, Qt.AlignCenter, "PROCESS  FLOW")

    p.setPen(QPen(QColor(0, 212, 255, 30), 1))
    p.drawLine(14, BAR_H + 26, DX - 14, BAR_H + 26)

    # ── CAS zone boxes ─────────────────────────────────────────────────────────
    bw, bh = 168, 36
    bcx = DX // 2
    bx  = bcx - bw // 2

    zones = [
        ("PRIMARY SETTLING", "#7b2d8b",  46),
        ("AERATION TANK",    "#0077b6", 118),
        ("CLARIFIER",        "#2d8b6f", 190),
        ("EFFLUENT STORAGE", "#e07b39", 262),
    ]

    for name, col, by in zones:
        c      = QColor(col)
        bright = c.lighter(145)

        # Aeration glow halo
        if "AERATION" in name:
            for r_off, alpha in [(9, 25), (6, 40), (3, 60)]:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(0, 180, 216, alpha), 1))
                p.drawRoundedRect(bx - r_off, by - r_off,
                                  bw + r_off * 2, bh + r_off * 2, 8, 8)

        # Box fill
        box_bg = QLinearGradient(bx, by, bx + bw, by + bh)
        box_bg.setColorAt(0.0, c.darker(170))
        box_bg.setColorAt(1.0, c.darker(230))
        p.setBrush(QBrush(box_bg))
        p.setPen(QPen(bright, 0.8))
        p.drawRoundedRect(bx, by, bw, bh, 5, 5)

        # Left accent strip
        acc = QLinearGradient(bx, by, bx, by + bh)
        acc.setColorAt(0.0, bright.lighter(115))
        acc.setColorAt(1.0, bright)
        p.setBrush(QBrush(acc))
        p.setPen(Qt.NoPen)
        path_acc = QPainterPath()
        path_acc.addRoundedRect(QRectF(bx, by, 5, bh), 2.5, 2.5)
        p.drawPath(path_acc)

        # Zone label
        f_z = QFont("Segoe UI", 7, QFont.Bold)
        f_z.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        p.setFont(f_z)
        p.setPen(bright.lighter(135))
        p.drawText(bx + 12, by, bw - 12, bh, Qt.AlignLeft | Qt.AlignVCenter, name)

        # Aeration bubbles (static visual hint)
        if "AERATION" in name:
            for bub_x, bub_y, bub_r in [
                (bx + bw - 14, by + 9,  3.0),
                (bx + bw - 25, by + 24, 2.0),
                (bx + bw - 9,  by + 26, 2.5),
                (bx + bw - 19, by + 17, 1.5),
            ]:
                p.setBrush(QColor(0, 180, 216, 100))
                p.setPen(QPen(QColor(0, 210, 240, 140), 0.8))
                p.drawEllipse(QPointF(bub_x, bub_y), bub_r, bub_r)

    # ── Flow connectors ────────────────────────────────────────────────────────
    for i in range(len(zones) - 1):
        _, col_top, y_top = zones[i]
        _, col_bot, y_bot = zones[i + 1]
        cx = bcx
        y1, y2 = y_top + bh, y_bot
        mid_y  = (y1 + y2) // 2

        conn = QLinearGradient(0, y1, 0, y2)
        conn.setColorAt(0.0, QColor(col_top).lighter(130))
        conn.setColorAt(1.0, QColor(col_bot).lighter(130))
        p.setPen(QPen(QBrush(conn), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawLine(cx, y1, cx, y2)

        # Flow pulse dot at midpoint
        p.setBrush(QColor(0, 212, 255, 130))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, mid_y), 2.5, 2.5)

        # Arrowhead
        p.setBrush(QColor(col_bot).lighter(140))
        arr = QPainterPath()
        arr.moveTo(cx,      y2)
        arr.lineTo(cx - 4.5, y2 - 9)
        arr.lineTo(cx + 4.5, y2 - 9)
        arr.closeSubpath()
        p.drawPath(arr)

    # ── Influent / Effluent labels ─────────────────────────────────────────────
    p.setFont(QFont("Segoe UI", 7))
    p.setPen(QColor(0, 212, 255, 120))
    p.drawText(bx, BAR_H + 2, bw, 36, Qt.AlignCenter, "▼  Influent")
    _, _, last_by = zones[-1]
    p.drawText(bx, last_by + bh + 4, bw, 22, Qt.AlignCenter, "▲  Effluent")

    # ── RAS recycle (Clarifier → Aeration, left side) ─────────────────────────
    _, _, clar_by = zones[2]
    _, _, aer_by  = zones[1]
    ras_x    = bx - 22
    ras_cy_c = clar_by + bh // 2
    ras_cy_a = aer_by  + bh // 2

    ras = QPainterPath()
    ras.moveTo(bx, ras_cy_c)
    ras.lineTo(ras_x, ras_cy_c)
    ras.lineTo(ras_x, ras_cy_a)
    ras.lineTo(bx, ras_cy_a)

    rpen = QPen(QColor("#7b2d8b").lighter(150), 1.2)
    rpen.setStyle(Qt.DashLine)
    rpen.setDashPattern([4, 3])
    p.setBrush(Qt.NoBrush)
    p.setPen(rpen)
    p.drawPath(ras)

    p.setBrush(QColor("#7b2d8b").lighter(160))
    p.setPen(Qt.NoPen)
    ras_arr = QPainterPath()
    ras_arr.moveTo(bx,     ras_cy_a)
    ras_arr.lineTo(bx - 5, ras_cy_a - 4)
    ras_arr.lineTo(bx - 5, ras_cy_a + 4)
    ras_arr.closeSubpath()
    p.drawPath(ras_arr)

    f_tiny = QFont("Segoe UI", 6, QFont.Bold)
    f_tiny.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
    p.setFont(f_tiny)
    p.setPen(QColor("#7b2d8b").lighter(190))
    mid_y_ras = (ras_cy_c + ras_cy_a) // 2
    p.drawText(0, mid_y_ras - 8, ras_x - 2, 16, Qt.AlignCenter, "RAS")

    # ── RIGHT PANEL ────────────────────────────────────────────────────────────
    rx = DX + 30
    rw = W - rx - 22
    cy = BAR_H   # current y cursor

    # Institution badge
    f_inst = QFont("Segoe UI", 7, QFont.Bold)
    f_inst.setLetterSpacing(QFont.AbsoluteSpacing, 1.8)
    p.setFont(f_inst)
    inst_text = "TSHWANE UNIVERSITY OF TECHNOLOGY"
    fm   = p.fontMetrics()
    inst_w = fm.horizontalAdvance(inst_text) + 18
    inst_y = cy + 14
    p.setBrush(QColor(0, 119, 182, 35))
    p.setPen(QPen(QColor(0, 180, 216, 75), 1))
    p.drawRoundedRect(rx, inst_y, inst_w, 20, 3, 3)
    p.setPen(QColor(0, 200, 230, 190))
    p.drawText(rx, inst_y, inst_w, 20, Qt.AlignCenter, inst_text)

    cy = inst_y + 20

    # "DIGITAL" tracked label
    f_digi = QFont("Segoe UI", 12, QFont.Bold)
    f_digi.setLetterSpacing(QFont.AbsoluteSpacing, 8)
    p.setFont(f_digi)
    p.setPen(QColor("#00d4ff"))
    digi_y = cy + 16
    p.drawText(rx, digi_y, rw, 32, Qt.AlignLeft | Qt.AlignVCenter, "DIGITAL")

    cy = digi_y + 28

    # "REACTOR" hero with triple-layer glow
    f_hero = QFont("Segoe UI", 56, QFont.Bold)
    hero_y = cy
    _glow_text(
        p, f_hero, "REACTOR",
        (rx, hero_y, rw, 72), Qt.AlignLeft | Qt.AlignBottom,
        QColor(0, 180, 216), QColor("#ffffff"), layers=3,
    )

    cy = hero_y + 74

    # Gradient accent rule under hero text
    rule = QLinearGradient(rx, 0, rx + rw - 10, 0)
    rule.setColorAt(0.0,  QColor("#00d4ff"))
    rule.setColorAt(0.35, QColor("#0077b6"))
    rule.setColorAt(1.0,  QColor(0, 0, 0, 0))
    p.fillRect(rx, cy, rw - 10, 2, QBrush(rule))
    rule2 = QLinearGradient(rx, 0, rx + int(rw * 0.5), 0)
    rule2.setColorAt(0.0, QColor(0, 212, 255, 70))
    rule2.setColorAt(1.0, QColor(0, 212, 255, 0))
    p.fillRect(rx, cy + 5, int(rw * 0.5), 1, QBrush(rule2))

    cy += 14

    # Subtitle 1
    f_sub1 = QFont("Segoe UI", 11)
    p.setFont(f_sub1)
    p.setPen(QColor("#a8d8ea"))
    p.drawText(rx, cy, rw, 28, Qt.AlignLeft | Qt.AlignVCenter,
               "PFAS & CEC Wastewater Research Platform")

    cy += 26

    # Subtitle 2
    f_sub2 = QFont("Segoe UI", 9)
    p.setFont(f_sub2)
    p.setPen(QColor(255, 255, 255, 75))
    p.drawText(rx, cy, rw, 22, Qt.AlignLeft | Qt.AlignVCenter,
               "Lab-scale activated sludge  ·  OECD Guideline 303A")

    cy += 30

    # Thin separator
    p.fillRect(rx, cy, rw - 8, 1, QColor(255, 255, 255, 18))
    cy += 10

    # Badges
    p.setFont(QFont("Segoe UI", 8, QFont.Bold))

    def _badge(bx_s: int, label: str, bg: str, fg: str, border: str) -> int:
        fm2  = p.fontMetrics()
        bw_  = fm2.horizontalAdvance(label) + 22
        bh_  = 22
        p.setBrush(QColor(bg))
        p.setPen(QPen(QColor(border), 1))
        p.drawRoundedRect(bx_s, cy, bw_, bh_, 11, 11)
        p.setPen(QColor(fg))
        p.drawText(bx_s, cy, bw_, bh_, Qt.AlignCenter, label)
        return bx_s + bw_ + 8

    nx = rx
    nx = _badge(nx, "v1.0",         "#051525", "#00d4ff", "#0077b6")
    nx = _badge(nx, "OECD 303A",    "#051a10", "#48cae4", "#2d8b6f")
    nx = _badge(nx, "Phase 1+2 ML", "#1a0e00", "#e07b39", "#c45a20")

    cy += 32

    # Researcher name
    f_name = QFont("Segoe UI", 10, QFont.Bold)
    p.setFont(f_name)
    p.setPen(QColor("#ecf0f1"))
    p.drawText(rx, cy, rw, 24, Qt.AlignLeft | Qt.AlignVCenter, "M.M. Sekhula-Mojela")
    cy += 22

    f_role = QFont("Segoe UI", 8)
    p.setFont(f_role)
    p.setPen(QColor(255, 255, 255, 95))
    p.drawText(rx, cy, rw, 18, Qt.AlignLeft | Qt.AlignVCenter,
               "PhD Candidate  ·  Environmental Sciences  ·  2026–2028")

    # Developer credit (bottom-right, faint)
    f_dev = QFont("Segoe UI", 8)
    p.setFont(f_dev)
    p.setPen(QColor(255, 255, 255, 40))
    p.drawText(rx, H - PH - 22, rw, 16, Qt.AlignRight | Qt.AlignVCenter,
               "Developed by Caliphs Zvinowanda")

    # ── Progress strip background ──────────────────────────────────────────────
    pg = QLinearGradient(0, H - PH, 0, H)
    pg.setColorAt(0.0, QColor("#071520"))
    pg.setColorAt(1.0, QColor("#040d12"))
    p.fillRect(0, H - PH, W, PH, QBrush(pg))

    # Top edge of progress strip — cyan fade
    top_edge = QLinearGradient(0, 0, W, 0)
    top_edge.setColorAt(0.0,  QColor(0, 212, 255, 0))
    top_edge.setColorAt(0.25, QColor(0, 212, 255, 100))
    top_edge.setColorAt(0.75, QColor(0, 180, 216, 80))
    top_edge.setColorAt(1.0,  QColor(0, 212, 255, 0))
    p.fillRect(0, H - PH, W, 1, QBrush(top_edge))

    p.end()
    return pix


# ──────────────────────────────────────────────────────────────────────────────
#  Animated progress overlay (stamped fresh each loading step)
# ──────────────────────────────────────────────────────────────────────────────

def _set_progress(splash: QSplashScreen, base: QPixmap,
                  pct: int, msg: str) -> None:
    """
    Stamp the progress bar and status text onto a copy of *base* then push
    the result to the splash screen.  Called before every loading step.
    """
    W, H = _SW, _SH
    PH   = _PROG_H
    PY   = H - PH

    new_pix = QPixmap(base)
    p       = QPainter(new_pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Clear the strip
    pg = QLinearGradient(0, PY, 0, H)
    pg.setColorAt(0.0, QColor("#071520"))
    pg.setColorAt(1.0, QColor("#040d12"))
    p.fillRect(0, PY, W, PH, QBrush(pg))

    # Top edge
    top_edge = QLinearGradient(0, 0, W, 0)
    top_edge.setColorAt(0.0,  QColor(0, 212, 255, 0))
    top_edge.setColorAt(0.25, QColor(0, 212, 255, 100))
    top_edge.setColorAt(0.75, QColor(0, 180, 216, 80))
    top_edge.setColorAt(1.0,  QColor(0, 212, 255, 0))
    p.fillRect(0, PY, W, 1, QBrush(top_edge))

    # ── Zone indicator dots ────────────────────────────────────────────────────
    dot_x_start = 18
    dot_spacing = 20
    for i, col in enumerate(_ZONE_COLS):
        cx = dot_x_start + i * dot_spacing
        cy = PY + 17
        active = pct >= (i + 1) * 25
        if active:
            # Glow ring
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(col), 1.0))
            p.drawEllipse(QPointF(cx, cy), 8, 8)
            # Filled dot
            p.setBrush(QColor(col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), 5.5, 5.5)
        else:
            p.setBrush(QColor(QColor(col).red(), QColor(col).green(),
                               QColor(col).blue(), 55))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), 4, 4)

    # ── Status message ─────────────────────────────────────────────────────────
    msg_x = dot_x_start + 4 * dot_spacing + 14
    f_msg = QFont("Segoe UI", 9)
    p.setFont(f_msg)
    p.setPen(QColor(255, 255, 255, 145))
    p.drawText(msg_x, PY + 5, W - msg_x - 68, 24,
               Qt.AlignLeft | Qt.AlignVCenter, msg)

    # ── Percentage label ───────────────────────────────────────────────────────
    f_pct = QFont("Segoe UI", 9, QFont.Bold)
    p.setFont(f_pct)
    p.setPen(QColor("#00d4ff"))
    p.drawText(W - 58, PY + 5, 48, 24, Qt.AlignRight | Qt.AlignVCenter, f"{pct}%")

    # ── Progress bar ───────────────────────────────────────────────────────────
    tx, ty, tw, th = 18, PY + 34, W - 36, 10

    # Track
    p.setBrush(QColor(0, 0, 0, 70))
    p.setPen(QPen(QColor(255, 255, 255, 18), 1))
    p.drawRoundedRect(tx, ty, tw, th, 5, 5)

    # Fill
    if pct > 0:
        fw = max(th, int(tw * pct / 100))

        bar = QLinearGradient(tx, 0, tx + fw, 0)
        bar.setColorAt(0.0,  QColor("#005f96"))
        bar.setColorAt(0.45, QColor("#00b4d8"))
        bar.setColorAt(1.0,  QColor("#00d4ff"))
        p.setBrush(QBrush(bar))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(tx, ty, fw, th, 5, 5)

        # Top-half gloss sheen
        gloss = QLinearGradient(0, ty, 0, ty + th // 2)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 55))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gloss))
        p.drawRoundedRect(tx, ty, fw, th // 2 + 2, 5, 5)

        # Shimmer spot — position advances with pct (static per frame)
        sh_center = tx + max(10, int(tw * pct / 100) - 20)
        sh_grad = QLinearGradient(sh_center - 24, 0, sh_center + 24, 0)
        sh_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        sh_grad.setColorAt(0.5, QColor(255, 255, 255, 85))
        sh_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(sh_grad))
        p.drawRoundedRect(
            max(tx, sh_center - 24), ty,
            min(48, fw - (sh_center - 24 - tx)), th, 5, 5,
        )

        # Leading-edge glow orb
        p.setBrush(QColor(0, 212, 255, 170))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(tx + fw, ty + th / 2.0), th / 2.0 + 1, th / 2.0 + 1)

    p.end()
    splash.setPixmap(new_pix)
    splash.repaint()


# ──────────────────────────────────────────────────────────────────────────────
#  Application entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Initialise the database, build all screens, then show the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName("Digital Reactor")
    app.setOrganizationName("TUT Environmental Sciences")

    apply_theme(app)

    # ── Splash ────────────────────────────────────────────────────────────────
    base_pix = _make_base_pixmap()
    splash   = QSplashScreen(base_pix, Qt.WindowStaysOnTopHint)
    _set_progress(splash, base_pix, 0, "Starting up…")
    splash.show()
    app.processEvents()

    # ── Database ──────────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 10, "Initialising database…")
    app.processEvents()
    try:
        init_db()
    except Exception as exc:
        splash.hide()
        QMessageBox.critical(
            None, "Database Error",
            f"Could not initialise the database:\n\n{exc}\n\n"
            "Please check that the application data folder is writable.\n"
            f"Expected location: %APPDATA%\\DigitalReactor\\"
        )
        sys.exit(1)

    # ── Main window shell ─────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 22, "Building interface…")
    app.processEvents()
    from ui.main_window import MainWindow
    window = MainWindow()

    # ── Home ──────────────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 36, "Loading Home…")
    app.processEvents()
    from ui.home_screen import HomeScreen
    home = HomeScreen()
    window.replace_screen(0, home)

    # ── Experiments ───────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 48, "Loading Experiments…")
    app.processEvents()
    from ui.experiments import ExperimentsScreen
    experiments = ExperimentsScreen()
    experiments.experiment_changed.connect(home._refresh_status)
    experiments.experiment_changed.connect(window.refresh_active_experiment)
    window.replace_screen(1, experiments)

    # ── Data-entry screens ────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 62, "Loading data entry screens…")
    app.processEvents()
    from ui.data_entry import DataEntryScreen
    window.replace_screen(2, DataEntryScreen())
    from ui.cec_tracker import CECTrackerScreen
    window.replace_screen(3, CECTrackerScreen())
    from ui.mass_balance import MassBalanceScreen
    window.replace_screen(4, MassBalanceScreen())

    # ── Simulation & Plants ───────────────────────────────────────────────────
    _set_progress(splash, base_pix, 76, "Loading Simulation & Plants…")
    app.processEvents()
    from ui.simulation_screen import SimulationScreen
    window.replace_screen(5, SimulationScreen())
    from ui.plants_screen import PlantsScreen
    window.replace_screen(6, PlantsScreen())

    # ── Dashboard ─────────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 84, "Loading Comparison Dashboard…")
    app.processEvents()
    from ui.dashboard import DashboardScreen
    window.replace_screen(7, DashboardScreen())

    # ── Settings & Manual ─────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 91, "Loading Settings & Manual…")
    app.processEvents()
    from ui.settings import SettingsScreen
    window.replace_screen(8, SettingsScreen())
    from ui.help_screen import HelpScreen
    window.replace_screen(9, HelpScreen())

    # ── Ready ─────────────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 100, "Ready.")
    app.processEvents()

    window._go_to(0)
    window.showMaximized()
    app.processEvents()

    QTimer.singleShot(750, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

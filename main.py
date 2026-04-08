"""
main.py — Digital Reactor application entry point.

Run with:
    python main.py

On first run, reactor.db is created in %APPDATA%\\DigitalReactor\\ with all
tables.  On subsequent runs, pending schema migrations are applied automatically.
"""

import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QBrush, QPen,
    QLinearGradient, QRadialGradient, QPainterPath,
)

from core.database import init_db
from ui.theme import apply_theme

# ── Splash geometry ────────────────────────────────────────────────────────────
_SW, _SH = 640, 380   # splash canvas size
_BAR_H   = 8          # top zone-colour accent bar
_PROG_H  = 44         # bottom progress area
_DIV_X   = 220        # x where left process-flow panel ends

# Zone colours match the 4 biological zones throughout the app
_ZONE_COLS = ["#8e44ad", "#2471a3", "#1e8449", "#636e72"]


# ──────────────────────────────────────────────────────────────────────────────
#  Splash drawing
# ──────────────────────────────────────────────────────────────────────────────

def _make_base_pixmap() -> QPixmap:
    """
    Draw the static portion of the splash screen and return the base QPixmap.

    Layout
    ──────
    ┌── 8 px accent bar (zone colours) ──────────────────────────────────┐
    │ LEFT PANEL (0–220 px)        │  RIGHT PANEL (220–640 px)           │
    │  "PROCESS FLOW" header       │  "DIGITAL"                          │
    │  Reactor zones (5 boxes):    │  "REACTOR"  (large)                 │
    │    ANAEROBIC ─purple         │  PFAS & CEC Research Platform        │
    │    ANOXIC    ─blue           │  ─────────────────────               │
    │    AEROBIC   ─green          │  Researcher name + institution       │
    │    CLARIFIER ─grey           │  Version / OECD / ML badges          │
    │    EFFLUENT  ─teal           │  Developer credit                    │
    │  RAS & a-recycle arrows      │                                      │
    ├── 44 px progress area ─────────────────────────────────────────────┤
    │  ● ● ● ●  status text                               [pct%]         │
    │  ═══════════════════════════════════════════════════               │
    └────────────────────────────────────────────────────────────────────┘
    """
    W, H = _SW, _SH
    BH, PH, DX = _BAR_H, _PROG_H, _DIV_X

    pix = QPixmap(W, H)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    # ── Full background ────────────────────────────────────────────────────
    bg = QLinearGradient(0, 0, W, H)
    bg.setColorAt(0.0, QColor("#0d1b2a"))
    bg.setColorAt(1.0, QColor("#0a1520"))
    p.fillRect(0, 0, W, H, QBrush(bg))

    # ── Left panel background ──────────────────────────────────────────────
    lp = QLinearGradient(0, BH, 0, H - PH)
    lp.setColorAt(0.0, QColor("#0f2030"))
    lp.setColorAt(1.0, QColor("#0a1a28"))
    p.fillRect(0, BH, DX, H - BH - PH, QBrush(lp))
    # Thin right edge
    p.fillRect(DX, BH, 1, H - BH - PH, QColor("#0d2236"))

    # ── Top accent bar (4 zone colours, equal segments) ───────────────────
    seg = W // 4
    for i, col in enumerate(_ZONE_COLS):
        extra = (W % 4) if i == 3 else 0
        p.fillRect(i * seg, 0, seg + extra, BH, QColor(col))

    # ── "PROCESS FLOW" header in left panel ───────────────────────────────
    f = QFont("Segoe UI", 7, QFont.Bold)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
    p.setFont(f)
    p.setPen(QColor("#1e3a52"))
    p.drawText(0, BH, DX, 22, Qt.AlignCenter, "PROCESS FLOW")

    # ── Zone boxes ────────────────────────────────────────────────────────
    #   5 zones, each 30 px tall, spaced 50 px apart (20 px connector gap)
    bw, bh = 148, 30
    bcx = DX // 2          # center x of left panel  = 110
    bx  = bcx - bw // 2   # left edge of boxes       =  36

    zones = [
        ("ANAEROBIC",  "#8e44ad",  60),
        ("ANOXIC",     "#2471a3", 110),
        ("AEROBIC",    "#1e8449", 160),
        ("CLARIFIER",  "#636e72", 210),
        ("EFFLUENT",   "#16a085", 260),
    ]

    for name, col, by in zones:
        c = QColor(col)
        # drop shadow
        p.setBrush(QColor(0, 0, 0, 50))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(bx + 2, by + 2, bw, bh, 4, 4)
        # box fill
        box_bg = QLinearGradient(bx, by, bx, by + bh)
        box_bg.setColorAt(0.0, c.darker(230))
        box_bg.setColorAt(1.0, c.darker(290))
        p.setBrush(QBrush(box_bg))
        p.setPen(QPen(c, 1.5))
        p.drawRoundedRect(bx, by, bw, bh, 4, 4)
        # label
        f_z = QFont("Segoe UI", 7, QFont.Bold)
        f_z.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(f_z)
        p.setPen(c.lighter(175))
        p.drawText(bx, by, bw, bh, Qt.AlignCenter, name)

    # ── Flow connectors (dotted lines + arrowheads) ───────────────────────
    for i in range(len(zones) - 1):
        _, _, y_top = zones[i]
        _, _, y_bot = zones[i + 1]
        cx = bcx
        y1, y2 = y_top + bh, y_bot

        p.setPen(QPen(QColor("#1a3a5c"), 1.5))
        p.drawLine(cx, y1, cx, y2)

        p.setBrush(QColor("#1a3a5c"))
        p.setPen(Qt.NoPen)
        arr = QPainterPath()
        arr.moveTo(cx,     y2)
        arr.lineTo(cx - 4, y2 - 7)
        arr.lineTo(cx + 4, y2 - 7)
        arr.closeSubpath()
        p.drawPath(arr)

    # ── Influent label (SP1) ───────────────────────────────────────────────
    f_sp = QFont("Segoe UI", 7)
    p.setFont(f_sp)
    p.setPen(QColor("#2d4a62"))
    p.drawText(bx, BH + 30, bw, 20, Qt.AlignCenter, "↓  Influent  (SP1)")

    # ── Effluent label (SP4) ──────────────────────────────────────────────
    _, _, last_by = zones[-1]
    p.drawText(bx, last_by + bh + 4, bw, 20, Qt.AlignCenter, "↑  Effluent  (SP4)")

    # ── RAS recycle arrow (left side, CLARIFIER → ANAEROBIC) ─────────────
    _, _, clar_by = zones[3]
    _, _, ana_by  = zones[0]
    ras_x    = bx - 14
    ras_cy_c = clar_by + bh // 2   # 225
    ras_cy_a = ana_by  + bh // 2   #  75

    ras = QPainterPath()
    ras.moveTo(bx, ras_cy_c)
    ras.lineTo(ras_x, ras_cy_c)
    ras.lineTo(ras_x, ras_cy_a)
    ras.lineTo(bx, ras_cy_a)

    rpen = QPen(QColor("#4d6370"), 1.2)
    rpen.setStyle(Qt.DashLine)
    p.setBrush(Qt.NoBrush)
    p.setPen(rpen)
    p.drawPath(ras)

    p.setBrush(QColor("#4d6370"))
    p.setPen(Qt.NoPen)
    ras_arr = QPainterPath()
    ras_arr.moveTo(bx, ras_cy_a)
    ras_arr.lineTo(bx - 5, ras_cy_a - 4)
    ras_arr.lineTo(bx - 5, ras_cy_a + 4)
    ras_arr.closeSubpath()
    p.drawPath(ras_arr)

    f_tiny = QFont("Segoe UI", 6)
    p.setFont(f_tiny)
    p.setPen(QColor("#1e3a52"))
    p.drawText(0, (ras_cy_c + ras_cy_a) // 2 - 8, ras_x, 16, Qt.AlignCenter, "RAS")

    # ── a-recycle arrow (right side, AEROBIC → ANOXIC) ───────────────────
    _, _, aer_by = zones[2]
    _, _, anx_by = zones[1]
    rec_x    = bx + bw + 14
    rec_cy_a = aer_by + bh // 2   # 175
    rec_cy_n = anx_by + bh // 2   # 125

    rec = QPainterPath()
    rec.moveTo(bx + bw, rec_cy_a)
    rec.lineTo(rec_x,   rec_cy_a)
    rec.lineTo(rec_x,   rec_cy_n)
    rec.lineTo(bx + bw, rec_cy_n)

    apen = QPen(QColor("#1a3a5c"), 1.2)
    apen.setStyle(Qt.DashLine)
    p.setBrush(Qt.NoBrush)
    p.setPen(apen)
    p.drawPath(rec)

    p.setBrush(QColor("#1a3a5c"))
    p.setPen(Qt.NoPen)
    rec_arr = QPainterPath()
    rec_arr.moveTo(bx + bw,     rec_cy_n)
    rec_arr.lineTo(bx + bw + 5, rec_cy_n - 4)
    rec_arr.lineTo(bx + bw + 5, rec_cy_n + 4)
    rec_arr.closeSubpath()
    p.drawPath(rec_arr)

    p.setFont(f_tiny)
    p.setPen(QColor("#1a3a5c"))
    mid_y = (rec_cy_a + rec_cy_n) // 2
    p.drawText(rec_x + 1, mid_y - 8, DX - rec_x - 2, 16, Qt.AlignLeft, "a")

    # ──────────────────────────────────────────────────────────────────────
    # RIGHT PANEL
    # ──────────────────────────────────────────────────────────────────────
    rx = DX + 22          # content left edge
    rw = W - rx - 18      # content width

    # Subtle blue radial glow (atmospheric)
    glow = QRadialGradient(QPointF(W * 0.72, H * 0.3), 220)
    glow.setColorAt(0.0, QColor(36, 113, 163, 22))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(DX, BH, W - DX, H - BH, QBrush(glow))

    # "DIGITAL" — small tracked label
    f_digi = QFont("Segoe UI", 10, QFont.Bold)
    f_digi.setLetterSpacing(QFont.AbsoluteSpacing, 6)
    p.setFont(f_digi)
    p.setPen(QColor("#2471a3"))
    p.drawText(rx, BH + 18, rw, 26, Qt.AlignLeft | Qt.AlignVCenter, "DIGITAL")

    # "REACTOR" — large hero text
    f_hero = QFont("Segoe UI", 46, QFont.Bold)
    p.setFont(f_hero)
    p.setPen(QColor("#ecf0f1"))
    p.drawText(rx - 4, BH + 44, rw, 60, Qt.AlignLeft | Qt.AlignBottom, "REACTOR")

    # Blue underline accent (two-layer for depth)
    p.fillRect(rx, BH + 108, 292, 3, QColor("#1a5276"))
    p.fillRect(rx, BH + 108, 130, 3, QColor("#2980b9"))

    # Subtitle lines
    f_sub1 = QFont("Segoe UI", 11)
    p.setFont(f_sub1)
    p.setPen(QColor("#7f8c8d"))
    p.drawText(rx, BH + 116, rw, 26,
               Qt.AlignLeft | Qt.AlignVCenter,
               "PFAS & CEC Wastewater Research Platform")

    f_sub2 = QFont("Segoe UI", 9)
    p.setFont(f_sub2)
    p.setPen(QColor("#4d6370"))
    p.drawText(rx, BH + 140, rw, 20,
               Qt.AlignLeft | Qt.AlignVCenter,
               "Lab-scale activated sludge  ·  OECD Guideline 303A")

    # Separator above badges
    p.fillRect(rx, BH + 170, rw - 8, 1, QColor("#0f2236"))

    # Badge drawing helper
    p.setFont(QFont("Segoe UI", 8, QFont.Bold))

    def _badge(bx_start: int, label: str, bg: str, fg: str) -> int:
        fm = p.fontMetrics()
        bw_px = fm.horizontalAdvance(label) + 20
        badge_y = BH + 182
        badge_h = 22
        p.setBrush(QColor(bg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(bx_start, badge_y, bw_px, badge_h, 11, 11)
        p.setPen(QColor(fg))
        p.drawText(bx_start, badge_y, bw_px, badge_h, Qt.AlignCenter, label)
        return bx_start + bw_px + 8

    nx = rx
    nx = _badge(nx, "v1.0",         "#0f2236", "#2980b9")
    nx = _badge(nx, "OECD 303A",    "#0a2218", "#27ae60")
    nx = _badge(nx, "Phase 1+2 ML", "#200e05", "#e67e22")

    # Developer credit
    f_dev = QFont("Segoe UI", 8)
    p.setFont(f_dev)
    p.setPen(QColor("#1e3a52"))
    p.drawText(rx, H - PH - 22, rw, 18,
               Qt.AlignRight | Qt.AlignVCenter, "Developed by Caliphs Zvinowanda")

    # ── Bottom progress area (background only; content drawn by _set_progress)
    p.fillRect(0, H - PH, W, PH, QColor("#050d18"))
    p.fillRect(0, H - PH, W, 1, QColor("#0d2030"))

    p.end()
    return pix


def _set_progress(splash: QSplashScreen, base: QPixmap,
                  pct: int, msg: str) -> None:
    """
    Stamp the progress bar and status text onto a fresh copy of *base*,
    then push the result to *splash*.

    Called before every loading step so the bar advances visibly.
    """
    W, H = _SW, _SH
    PH   = _PROG_H
    PY   = H - PH          # y-coordinate where progress area starts

    new_pix = QPixmap(base)
    p = QPainter(new_pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Clear the progress area
    p.fillRect(0, PY, W, PH, QColor("#050d18"))
    p.fillRect(0, PY, W, 1, QColor("#0d2030"))

    # Zone-colour dots (left side)
    for i, col in enumerate(_ZONE_COLS):
        p.setBrush(QColor(col))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(14 + i * 16, PY + 14), 4, 4)

    # Status message
    f_msg = QFont("Segoe UI", 9)
    p.setFont(f_msg)
    p.setPen(QColor("#4d6370"))
    msg_x = 14 + len(_ZONE_COLS) * 16 + 10
    p.drawText(msg_x, PY + 4, W - msg_x - 56, 20,
               Qt.AlignLeft | Qt.AlignVCenter, msg)

    # Percentage label (right)
    f_pct = QFont("Segoe UI", 8, QFont.Bold)
    p.setFont(f_pct)
    p.setPen(QColor("#2471a3"))
    p.drawText(W - 50, PY + 4, 40, 20, Qt.AlignRight | Qt.AlignVCenter, f"{pct}%")

    # Progress bar track
    tx, ty, tw, th = 14, PY + 28, W - 28, 6
    p.setBrush(QColor("#0a1e2e"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(tx, ty, tw, th, 3, 3)

    # Progress bar fill
    if pct > 0:
        fw = max(th, int(tw * pct / 100))
        grad = QLinearGradient(tx, 0, tx + fw, 0)
        grad.setColorAt(0.0, QColor("#1a5276"))
        grad.setColorAt(0.6, QColor("#2471a3"))
        grad.setColorAt(1.0, QColor("#2980b9"))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(tx, ty, fw, th, 3, 3)

        # Gloss sheen on upper half
        gloss = QLinearGradient(0, ty, 0, ty + th // 2)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 28))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gloss))
        p.drawRoundedRect(tx, ty, fw, th // 2, 3, 3)

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

    # ── Splash (shown before any heavy work starts) ───────────────────────────
    base_pix = _make_base_pixmap()
    splash   = QSplashScreen(base_pix, Qt.WindowStaysOnTopHint)
    _set_progress(splash, base_pix, 0, "Starting up…")
    splash.show()
    app.processEvents()   # ensure splash is visible before blocking work begins

    # ── Database init ─────────────────────────────────────────────────────────
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

    # ── Home (loaded eagerly — diagram animation starts on first paint) ────────
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
    window.replace_screen(1, experiments)

    # ── Data-entry screens (Daily Log / CEC / Mass Balance) ───────────────────
    _set_progress(splash, base_pix, 62, "Loading data entry screens…")
    app.processEvents()
    from ui.data_entry import DataEntryScreen
    window.replace_screen(2, DataEntryScreen())
    from ui.cec_tracker import CECTrackerScreen
    window.replace_screen(3, CECTrackerScreen())
    from ui.mass_balance import MassBalanceScreen
    window.replace_screen(4, MassBalanceScreen())

    # ── Simulation & Comparison ───────────────────────────────────────────────
    _set_progress(splash, base_pix, 76, "Loading Simulation & Dashboard…")
    app.processEvents()
    from ui.simulation_screen import SimulationScreen
    window.replace_screen(5, SimulationScreen())
    from ui.dashboard import DashboardScreen
    window.replace_screen(6, DashboardScreen())

    # ── Settings & Manual ─────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 91, "Loading Settings & Manual…")
    app.processEvents()
    from ui.settings import SettingsScreen
    window.replace_screen(7, SettingsScreen())
    from ui.help_screen import HelpScreen
    window.replace_screen(8, HelpScreen())

    # ── Ready ─────────────────────────────────────────────────────────────────
    _set_progress(splash, base_pix, 100, "Ready.")
    app.processEvents()

    # Show window (it paints underneath the splash which stays on top)
    window._go_to(0)
    window.showMaximized()
    app.processEvents()   # let the window fully render before splash steps aside

    # Close splash after a short pause — gives the user a moment to see 100%
    # and ensures the window beneath is fully painted when the splash disappears
    QTimer.singleShot(650, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

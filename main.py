"""
main.py — Digital Reactor application entry point.

Run with:
    python main.py

On first run this creates reactor.db in the project folder with all tables.
On subsequent runs it applies any pending schema migrations (data preserved).
"""

import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

from core.database import init_db
from ui.theme import apply_theme


def _make_splash(app: QApplication) -> QSplashScreen:
    """
    Splash screen drawn entirely with QPainter — no image files needed.
    Design: dark gradient background, zone-color accent bar, clean typography.
    """
    from PySide6.QtGui import QLinearGradient, QBrush, QPen, QRadialGradient
    from PySide6.QtCore import QRectF, QPointF

    W, H = 580, 320
    pix = QPixmap(W, H)
    pix.fill(QColor("#1a2533"))

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    # ── Background gradient (dark navy → slightly lighter) ─────────────────
    bg_grad = QLinearGradient(0, 0, 0, H)
    bg_grad.setColorAt(0.0, QColor("#1e2d3d"))
    bg_grad.setColorAt(1.0, QColor("#141e2b"))
    p.fillRect(0, 0, W, H, QBrush(bg_grad))

    # ── Subtle radial glow in the centre ───────────────────────────────────
    glow = QRadialGradient(QPointF(W / 2, H / 2 - 20), 220)
    glow.setColorAt(0.0, QColor(41, 128, 185, 35))   # #2980b9 at low opacity
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(0, 0, W, H, QBrush(glow))

    # ── Zone color accent bar (top) ────────────────────────────────────────
    bar_h = 5
    zone_colors = ["#8e44ad", "#2471a3", "#1e8449", "#7f8c8d"]
    seg_w = W // len(zone_colors)
    for i, color in enumerate(zone_colors):
        p.fillRect(i * seg_w, 0, seg_w, bar_h, QColor(color))

    # ── Thin horizontal rule below accent bar ──────────────────────────────
    p.setPen(QPen(QColor("#2c3e50"), 1))
    p.drawLine(0, bar_h, W, bar_h)

    # ── Left blue accent stripe ────────────────────────────────────────────
    stripe_grad = QLinearGradient(0, 0, 6, 0)
    stripe_grad.setColorAt(0.0, QColor("#2980b9"))
    stripe_grad.setColorAt(1.0, QColor("#2980b9", ))
    p.fillRect(0, bar_h, 4, H - bar_h, QColor("#2980b9"))

    # ── "DR" monogram circle ───────────────────────────────────────────────
    cx, cy, r = 74, 148, 38
    circle_grad = QRadialGradient(QPointF(cx - 8, cy - 8), r * 1.4)
    circle_grad.setColorAt(0.0, QColor("#3498db"))
    circle_grad.setColorAt(1.0, QColor("#1a6da3"))
    p.setBrush(QBrush(circle_grad))
    p.setPen(QPen(QColor("#2980b9"), 1.5))
    p.drawEllipse(QPointF(cx, cy), r, r)

    f_mono = QFont("Segoe UI", 18, QFont.Bold)
    p.setFont(f_mono)
    p.setPen(QColor("#ffffff"))
    p.drawText(cx - r, cy - r, r * 2, r * 2, Qt.AlignCenter, "DR")

    # ── App title ──────────────────────────────────────────────────────────
    f_title = QFont("Segoe UI", 28, QFont.Bold)
    p.setFont(f_title)
    p.setPen(QColor("#ecf0f1"))
    p.drawText(128, 95, W - 140, 50, Qt.AlignLeft | Qt.AlignVCenter,
               "Digital Reactor")

    # ── Version badge ──────────────────────────────────────────────────────
    badge_x, badge_y, badge_w, badge_h = 128, 148, 46, 20
    p.setBrush(QColor("#2980b9"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 10, 10)
    f_badge = QFont("Segoe UI", 8, QFont.Bold)
    p.setFont(f_badge)
    p.setPen(QColor("#ffffff"))
    p.drawText(badge_x, badge_y, badge_w, badge_h, Qt.AlignCenter, "v1.0")

    # ── Subtitle ───────────────────────────────────────────────────────────
    f_sub = QFont("Segoe UI", 10)
    p.setFont(f_sub)
    p.setPen(QColor("#7f8c8d"))
    p.drawText(128, 148, W - 140, 26, Qt.AlignLeft | Qt.AlignVCenter,
               "       PFAS / CEC Wastewater Research Platform")

    # ── Divider line ───────────────────────────────────────────────────────
    p.setPen(QPen(QColor("#2c3e50"), 1))
    p.drawLine(128, 188, W - 20, 188)

    # ── Developer info ─────────────────────────────────────────────────────
    f_dev = QFont("Segoe UI", 9)
    p.setFont(f_dev)
    p.setPen(QColor("#566573"))
    p.drawText(128, 194, W - 148, 22, Qt.AlignLeft | Qt.AlignVCenter,
               "Developed by  Caliphs Zvinowanda  ·  +27 65 235 7607")

    # ── Bottom status bar background ───────────────────────────────────────
    p.fillRect(0, H - 36, W, 36, QColor("#111922"))
    p.setPen(QPen(QColor("#1e2d3d"), 1))
    p.drawLine(0, H - 36, W, H - 36)

    p.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.showMessage("  Initialising…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    return splash


def main():
    """Initialise the database, apply theme, show splash, then launch UI."""
    app = QApplication(sys.argv)
    app.setApplicationName("Digital Reactor")
    app.setOrganizationName("TUT Environmental Sciences")

    # ── Apply global theme (fonts + QSS) ──────────────────────────────────────
    apply_theme(app)

    # ── Splash screen ─────────────────────────────────────────────────────────
    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    # ── Initialise database + run schema migrations ───────────────────────────
    try:
        splash.showMessage("Initialising database…",
                           Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
        app.processEvents()
        init_db()
    except Exception as exc:
        splash.hide()
        QMessageBox.critical(
            None,
            "Database Error",
            f"Could not initialise the database:\n\n{exc}\n\n"
            "Please check that the application folder is writable."
        )
        sys.exit(1)

    # ── Build main window ─────────────────────────────────────────────────────
    splash.showMessage("Loading interface…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    app.processEvents()

    from ui.main_window import MainWindow
    window = MainWindow()

    # ── Load screens (lazy-friendly: only Home loads eagerly; rest on first visit) ──
    # Home — must be loaded immediately (diagram starts animation)
    splash.showMessage("Loading Home screen…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    app.processEvents()
    from ui.home_screen import HomeScreen
    home = HomeScreen()
    window.replace_screen(0, home)

    splash.showMessage("Loading Experiments screen…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    app.processEvents()
    from ui.experiments import ExperimentsScreen
    experiments = ExperimentsScreen()
    experiments.experiment_changed.connect(home._refresh_status)
    window.replace_screen(1, experiments)

    splash.showMessage("Loading data entry screens…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    app.processEvents()
    from ui.data_entry import DataEntryScreen
    window.replace_screen(2, DataEntryScreen())

    from ui.cec_tracker import CECTrackerScreen
    window.replace_screen(3, CECTrackerScreen())

    from ui.mass_balance import MassBalanceScreen
    window.replace_screen(4, MassBalanceScreen())

    splash.showMessage("Loading simulation & dashboard…",
                       Qt.AlignBottom | Qt.AlignLeft, QColor("#7f8c8d"))
    app.processEvents()
    from ui.simulation_screen import SimulationScreen
    window.replace_screen(5, SimulationScreen())

    from ui.dashboard import DashboardScreen
    window.replace_screen(6, DashboardScreen())

    from ui.settings import SettingsScreen
    window.replace_screen(7, SettingsScreen())

    from ui.help_screen import HelpScreen
    window.replace_screen(8, HelpScreen())

    # ── Navigate to Home and show window (maximized — standard for Windows apps)
    window._go_to(0)
    window.showMaximized()

    # Close splash after 1.2 s (gives the window time to paint)
    QTimer.singleShot(1200, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

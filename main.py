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
    Create a simple programmatic splash screen.
    No image file needed — drawn entirely with QPainter.
    """
    width, height = 480, 240
    pix = QPixmap(width, height)
    pix.fill(QColor("#2c3e50"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Title
    f_title = QFont("Segoe UI", 26, QFont.Bold)
    painter.setFont(f_title)
    painter.setPen(QColor("#ecf0f1"))
    painter.drawText(0, 50, width, 50, Qt.AlignHCenter | Qt.AlignVCenter, "Digital Reactor")

    # Subtitle
    f_sub = QFont("Segoe UI", 11)
    painter.setFont(f_sub)
    painter.setPen(QColor("#7f8c8d"))
    painter.drawText(0, 100, width, 35, Qt.AlignHCenter | Qt.AlignVCenter,
                     "PFAS / CEC Wastewater Research Platform")

    # Developer info
    f_dev = QFont("Segoe UI", 9)
    painter.setFont(f_dev)
    painter.setPen(QColor("#566573"))
    painter.drawText(0, 175, width, 22, Qt.AlignHCenter | Qt.AlignVCenter,
                     "Developed by Caliphs Zvinowanda  ·  +27 65 235 7607")
    painter.setPen(QColor("#3d5166"))
    painter.drawText(0, 197, width, 22, Qt.AlignHCenter | Qt.AlignVCenter,
                     "v1.0")

    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.showMessage("Initialising database…",
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
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
                           Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
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
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
    app.processEvents()

    from ui.main_window import MainWindow
    window = MainWindow()

    # ── Load screens (lazy-friendly: only Home loads eagerly; rest on first visit) ──
    # Home — must be loaded immediately (diagram starts animation)
    splash.showMessage("Loading Home screen…",
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
    app.processEvents()
    from ui.home_screen import HomeScreen
    home = HomeScreen()
    window.replace_screen(0, home)

    splash.showMessage("Loading Experiments screen…",
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
    app.processEvents()
    from ui.experiments import ExperimentsScreen
    experiments = ExperimentsScreen()
    experiments.experiment_changed.connect(home._refresh_status)
    window.replace_screen(1, experiments)

    splash.showMessage("Loading data entry screens…",
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
    app.processEvents()
    from ui.data_entry import DataEntryScreen
    window.replace_screen(2, DataEntryScreen())

    from ui.cec_tracker import CECTrackerScreen
    window.replace_screen(3, CECTrackerScreen())

    from ui.mass_balance import MassBalanceScreen
    window.replace_screen(4, MassBalanceScreen())

    splash.showMessage("Loading simulation & dashboard…",
                       Qt.AlignBottom | Qt.AlignHCenter, QColor("#b2bec3"))
    app.processEvents()
    from ui.simulation_screen import SimulationScreen
    window.replace_screen(5, SimulationScreen())

    from ui.dashboard import DashboardScreen
    window.replace_screen(6, DashboardScreen())

    from ui.settings import SettingsScreen
    window.replace_screen(7, SettingsScreen())

    from ui.help_screen import HelpScreen
    window.replace_screen(8, HelpScreen())

    # ── Navigate to Home and show window ──────────────────────────────────────
    window._go_to(0)
    window.show()

    # Close splash after 1.2 s (gives the window time to paint)
    QTimer.singleShot(1200, splash.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

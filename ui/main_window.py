"""
main_window.py — Digital Reactor main application window.

Layout (expanded sidebar):
    ┌──────────────┬───────────────────────────────────┐
    │ [≡] Digital  │                                   │
    │    Reactor   │   Content area (QStackedWidget)   │
    │  ──────────  │                                   │
    │  [icon] Home │                                   │
    │  [icon] ...  │                                   │
    └──────────────┴───────────────────────────────────┘

Layout (collapsed sidebar — icon-only):
    ┌────┬──────────────────────────────────────────────┐
    │[≡] │                                              │
    │[🏠]│   Content area                               │
    │[📋]│                                              │
    └────┴──────────────────────────────────────────────┘

The sidebar can be toggled between expanded (210 px, icon + label)
and collapsed (52 px, icon only) by clicking the hamburger button.
Window is resizable with a minimum of 1024×680 px (works on most laptops).
Icons come from qtawesome (Font Awesome 6 Solid).
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

from core.database import get_session
from core.models import Experiment


# ── Window dimensions ─────────────────────────────────────────────────────────
WINDOW_WIDTH  = 1280   # default startup size
WINDOW_HEIGHT = 760
WINDOW_MIN_W  = 1024   # minimum — works on 1366×768 laptops common in Southern Africa
WINDOW_MIN_H  = 680

# ── Sidebar dimensions ─────────────────────────────────────────────────────────
SIDEBAR_EXPANDED  = 210   # px — icon + label visible
SIDEBAR_COLLAPSED = 52    # px — icon only

# ── Colour palette ─────────────────────────────────────────────────────────────
COLOR_SIDEBAR_BG   = "#2c3e50"
COLOR_ACTIVE_BTN   = "#2980b9"
COLOR_HOVER_BTN    = "#3498db"
COLOR_TEXT         = "#ecf0f1"
COLOR_MUTED        = "#7f8c8d"
COLOR_DIVIDER      = "#3d5166"
COLOR_CONTENT_BG   = "#f0f3f4"
COLOR_ICON         = "#ecf0f1"   # icon colour in normal state
COLOR_ICON_ACTIVE  = "#ffffff"   # icon colour when button is active
COLOR_EXP_BAR_BG   = "#eaf2f8"
COLOR_EXP_BAR_TEXT = "#1f3a5f"


# ── Placeholder screen ─────────────────────────────────────────────────────────
class PlaceholderScreen(QWidget):
    """
    Temporary centred placeholder shown for screens not yet built.
    Each build step replaces this via MainWindow.replace_screen().
    """
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(f"color: {COLOR_MUTED};")

        sub = QLabel("This screen is coming soon.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #bdc3c7; font-size: 13px;")

        layout.addWidget(label)
        layout.addWidget(sub)


# ── Sidebar navigation button ──────────────────────────────────────────────────
class NavButton(QPushButton):
    """
    One navigation entry in the sidebar.

    Shows a qtawesome icon on the left and a text label to its right.
    When the sidebar is collapsed the label is hidden; only the icon shows.

    Args:
        icon_name:  qtawesome icon key, e.g. "fa6s.house"
        label:      Text shown beside the icon in expanded mode.
    """
    BTN_HEIGHT = 46

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self._icon_name  = icon_name

        self.setCheckable(True)
        self.setFixedHeight(self.BTN_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setIconSize(QSize(18, 18))

        font = QFont()
        font.setPointSize(10)
        self.setFont(font)

        self._set_icon(active=False)
        self._apply_style(active=False, expanded=True)

    # ── Icon ───────────────────────────────────────────────────────────────────
    def _set_icon(self, active: bool) -> None:
        """Swap icon colour based on active state."""
        colour = COLOR_ICON_ACTIVE if active else COLOR_ICON
        self.setIcon(qta.icon(self._icon_name, color=colour))

    # ── Style ──────────────────────────────────────────────────────────────────
    def _apply_style(self, active: bool, expanded: bool) -> None:
        """Rebuild the stylesheet for current active/expanded combination."""
        bg      = COLOR_ACTIVE_BTN if active else "transparent"
        align   = "left" if expanded else "center"
        padding = "padding-left: 14px;" if expanded else "padding: 0;"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {COLOR_TEXT};
                border: none;
                text-align: {align};
                {padding}
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_HOVER_BTN};
            }}
        """)

    # ── Public API ─────────────────────────────────────────────────────────────
    def set_active(self, active: bool, expanded: bool) -> None:
        """
        Update visual state when navigation changes or sidebar is toggled.

        Args:
            active:   True if this is the currently selected screen.
            expanded: True if the sidebar is in expanded (wide) mode.
        """
        self.setChecked(active)
        self._set_icon(active)
        self._apply_style(active, expanded)
        # Show or hide the text label based on sidebar state
        self.setText(self._label_text if expanded else "")


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    """
    Top-level application window.

    - Fixed size (cannot be resized by the user).
    - Collapsible sidebar toggled by the hamburger button.
    - QStackedWidget content area swapped by nav button clicks.
    """

    # (qtawesome icon key, display label, placeholder title)
    NAV_ITEMS = [
        ("fa6s.house",           "Home",          "Home — Reactor Overview"),
        ("fa6s.flask",           "Experiments",   "Experiments"),
        ("fa6s.chart-bar",       "Daily Log",     "Daily Log"),
        ("fa6s.vial",            "CEC Tracker",   "CEC Tracker"),
        ("fa6s.scale-balanced",  "Mass Balance",  "Mass Balance Calculator"),
        ("fa6s.microscope",      "Simulation",    "Simulation"),
        ("fa6s.industry",        "Plants",        "Real Plant Scientific Twins"),
        ("fa6s.chart-line",      "Comparison",    "Comparison Dashboard"),
        ("fa6s.gear",            "Settings",      "Settings"),
        ("fa6s.book-open",       "Manual",        "User Manual"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Digital Reactor")

        # ── Resizable window with minimum size ─────────────────────────────────
        # Removed setFixedSize — window is now resizable so it works on any laptop.
        # Minimum size prevents layout from becoming unusable on very small screens.
        self.setMinimumSize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self._sidebar_expanded = True   # tracks current sidebar state
        self._anim = None
        self._anim2 = None
        self._exp_context_label = None

        # ── Root layout ────────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        content       = self._build_content()

        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(content, stretch=1)

        self._go_to(0)

    # ── Sidebar ────────────────────────────────────────────────────────────────
    def _build_sidebar(self) -> QWidget:
        """
        Build the collapsible left-hand sidebar.
        Contains: hamburger toggle, app title, divider, nav buttons, version.
        """
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_EXPANDED)
        sidebar.setStyleSheet(f"background-color: {COLOR_SIDEBAR_BG};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(6, 10, 6, 12)
        layout.setSpacing(2)

        # ── Top row: hamburger + app title ─────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        # Hamburger / collapse toggle button
        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedSize(36, 36)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setIcon(qta.icon("fa6s.bars", color=COLOR_TEXT))
        self._toggle_btn.setIconSize(QSize(16, 16))
        self._toggle_btn.setToolTip("Collapse / expand sidebar")
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {COLOR_HOVER_BTN};
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_sidebar)
        top_row.addWidget(self._toggle_btn, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # App title label (hidden when collapsed)
        self._title_label = QLabel("Digital Reactor")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setStyleSheet(f"color: {COLOR_TEXT};")
        top_row.addWidget(self._title_label, stretch=1)

        layout.addLayout(top_row)
        layout.addSpacing(8)

        # ── Divider ────────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"color: {COLOR_DIVIDER};")
        layout.addWidget(divider)
        layout.addSpacing(6)

        # ── Navigation buttons ─────────────────────────────────────────────────
        self._nav_buttons: list[NavButton] = []
        for i, (icon_name, label, _) in enumerate(self.NAV_ITEMS):
            btn = NavButton(icon_name, label)
            btn.clicked.connect(lambda checked, idx=i: self._go_to(idx))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()

        # ── Version label ──────────────────────────────────────────────────────
        self._version_label = QLabel("v1.0  Digital Reactor")
        self._version_label.setAlignment(Qt.AlignCenter)
        self._version_label.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 10px;")
        layout.addWidget(self._version_label)

        return sidebar

    # ── Content area ───────────────────────────────────────────────────────────
    def _build_content(self) -> QWidget:
        """
        Build the QStackedWidget that holds all screens.
        Index matches NAV_ITEMS order — _go_to(i) shows screen i.
        """
        content = QWidget()
        content.setStyleSheet(f"background-color: {COLOR_CONTENT_BG};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._exp_context_bar = self._build_experiment_context_bar()
        layout.addWidget(self._exp_context_bar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {COLOR_CONTENT_BG};")
        for _, _, title in self.NAV_ITEMS:
            self._stack.addWidget(PlaceholderScreen(title))
        layout.addWidget(self._stack, stretch=1)

        self.refresh_active_experiment()
        return content

    def _build_experiment_context_bar(self) -> QWidget:
        """Create the global active-experiment context bar above the content stack."""
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(
            f"background:{COLOR_EXP_BAR_BG}; border-bottom:1px solid #c5d8ea;"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.flask", color="#2c6fa6").pixmap(QSize(13, 13)))
        row.addWidget(icon)

        self._exp_context_label = QLabel("Active experiment: loading…")
        self._exp_context_label.setStyleSheet(
            f"color:{COLOR_EXP_BAR_TEXT}; font-size:11px; font-weight:600;"
        )
        row.addWidget(self._exp_context_label)
        row.addStretch()

        switch_btn = QPushButton("Switch")
        switch_btn.setCursor(Qt.PointingHandCursor)
        switch_btn.setFixedHeight(24)
        switch_btn.setStyleSheet(
            "QPushButton {"
            "  background:#2c6fa6; color:#ffffff; border:none;"
            "  border-radius:4px; padding:0 10px; font-size:10px; font-weight:600;"
            "}"
            "QPushButton:hover { background:#3b82bd; }"
            "QPushButton:pressed { background:#245b88; }"
        )
        switch_btn.clicked.connect(lambda: self._go_to(1))
        row.addWidget(switch_btn)

        return bar

    # ── Sidebar toggle ─────────────────────────────────────────────────────────
    def _toggle_sidebar(self) -> None:
        """
        Animate the sidebar between expanded (210 px) and collapsed (52 px).
        Hides text labels and the title when collapsed so only icons remain.
        """
        self._sidebar_expanded = not self._sidebar_expanded
        target_width = SIDEBAR_EXPANDED if self._sidebar_expanded else SIDEBAR_COLLAPSED

        # Animate width change
        anim = QPropertyAnimation(self._sidebar, b"minimumWidth", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setStartValue(self._sidebar.width())
        anim.setEndValue(target_width)
        anim.start()
        self._anim = anim   # keep a reference so it isn't garbage-collected

        # Also fix the maximum so the sidebar doesn't stretch
        anim2 = QPropertyAnimation(self._sidebar, b"maximumWidth", self)
        anim2.setDuration(180)
        anim2.setEasingCurve(QEasingCurve.InOutQuad)
        anim2.setStartValue(self._sidebar.width())
        anim2.setEndValue(target_width)
        anim2.start()
        self._anim2 = anim2

        # Show/hide text elements
        self._title_label.setVisible(self._sidebar_expanded)
        self._version_label.setVisible(self._sidebar_expanded)

        # Refresh all nav button labels and alignment
        current_index = self._stack.currentIndex()
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == current_index, self._sidebar_expanded)

    # ── Navigation ─────────────────────────────────────────────────────────────
    def _go_to(self, index: int) -> None:
        """
        Switch the content area to screen `index` and update nav highlights.

        Args:
            index: 0=Home … 9=Manual (matches NAV_ITEMS order).
        """
        current_widget = self._stack.currentWidget()
        if current_widget and index != self._stack.currentIndex():
            confirm = getattr(current_widget, "confirm_discard_changes", None)
            if callable(confirm) and not confirm():
                return

        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index, self._sidebar_expanded)
        self._stack.setCurrentIndex(index)
        self.refresh_active_experiment()

    def refresh_active_experiment(self) -> None:
        """Refresh the global active-experiment context text from the database."""
        try:
            with get_session() as session:
                exp = session.query(Experiment).filter_by(is_active=True).first()
            if exp:
                self._exp_context_label.setText(f"Active experiment: {exp.name}")
                self._exp_context_label.setStyleSheet(
                    f"color:{COLOR_EXP_BAR_TEXT}; font-size:11px; font-weight:600;"
                )
            else:
                self._exp_context_label.setText("No active experiment selected")
                self._exp_context_label.setStyleSheet(
                    "color:#b03a2e; font-size:11px; font-weight:600;"
                )
        except Exception:
            self._exp_context_label.setText("Active experiment unavailable")
            self._exp_context_label.setStyleSheet(
                "color:#b03a2e; font-size:11px; font-weight:600;"
            )

    # ── Public API for future build steps ──────────────────────────────────────
    def replace_screen(self, index: int, widget: QWidget) -> None:
        """
        Swap placeholder at `index` with a finished screen widget.
        Called by each build step once its screen is complete.

        Args:
            index:  Position in NAV_ITEMS (0=Home … 9=Manual).
            widget: The real screen widget to insert.
        """
        old = self._stack.widget(index)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._stack.insertWidget(index, widget)
        self._go_to(index)

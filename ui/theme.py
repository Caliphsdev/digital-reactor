"""
theme.py — Centralized dark-refined theme for Digital Reactor.

Single source of truth for:
  • Color palette
  • Font sizes
  • Global QSS stylesheet (applied at QApplication level)
  • Helper style-string generators for common widgets

Usage:
    from ui.theme import apply_theme, COLORS
    apply_theme(app)   # call once in main.py after QApplication created

Design intent: Professional scientific look.
  Dark navy sidebar (#2c3e50) + white card content area.
  Rounded corners (8px), subtle shadows, clean 8px grid spacing.
  Works at any window size ≥ 1024×680 px.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont


# ── Color palette ─────────────────────────────────────────────────────────────
COLORS = {
    # Sidebar / header
    "sidebar_bg":       "#2c3e50",
    "sidebar_hover":    "#3498db",
    "sidebar_active":   "#2980b9",
    "sidebar_divider":  "#3d5166",
    "sidebar_text":     "#ecf0f1",
    "sidebar_muted":    "#7f8c8d",

    # Content area
    "content_bg":       "#f0f3f4",
    "card_bg":          "#ffffff",
    "card_border":      "#dfe6e9",

    # Typography
    "text_primary":     "#2c3e50",
    "text_secondary":   "#636e72",
    "text_muted":       "#b2bec3",

    # Status / alert
    "green":            "#27ae60",
    "green_light":      "#d5f5e3",
    "amber":            "#e67e22",
    "amber_light":      "#fef9e7",
    "red":              "#e74c3c",
    "red_light":        "#fdecea",
    "blue":             "#2980b9",
    "blue_light":       "#d5eaf9",

    # Zone colors (reactor zones)
    "zone_anaerobic":   "#8e44ad",
    "zone_anoxic":      "#2471a3",
    "zone_aerobic":     "#1e8449",
    "zone_effluent":    "#7f8c8d",
}


# ── Font config ───────────────────────────────────────────────────────────────
BASE_FONT_FAMILY = "Segoe UI"   # Available on all Windows machines
BASE_FONT_SIZE   = 10           # pt — base for body text


def _global_qss() -> str:
    """
    Generate the global application QSS stylesheet.

    Applied once to QApplication — cascades to all widgets.
    Overrides can still be applied per-widget using setStyleSheet().
    """
    from core.resources import resource_path
    _check = resource_path("ui/icons/check_white.svg").replace("\\", "/")
    c = COLORS
    return f"""
    /* ── Global base ──────────────────────────────────────────────────── */
    QWidget {{
        font-family: "{BASE_FONT_FAMILY}", "Arial", sans-serif;
        font-size: {BASE_FONT_SIZE}pt;
        color: {c['text_primary']};
    }}

    QMainWindow, QDialog {{
        background-color: {c['content_bg']};
    }}

    /* ── Scroll bars — slim modern style ─────────────────────────────── */
    QScrollBar:vertical {{
        background: {c['content_bg']};
        width: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['card_border']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['text_secondary']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: {c['content_bg']};
        height: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['card_border']};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c['text_secondary']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── Tab widget ───────────────────────────────────────────────────── */
    QTabWidget::pane {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 0 6px 6px 6px;
    }}
    QTabBar::tab {{
        background: #dfe6e9;
        color: {c['text_secondary']};
        padding: 8px 18px;
        border: 1px solid {c['card_border']};
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        margin-right: 2px;
        font-size: 10pt;
    }}
    QTabBar::tab:selected {{
        background: {c['card_bg']};
        color: {c['text_primary']};
        font-weight: bold;
    }}
    QTabBar::tab:hover {{
        background: {c['blue_light']};
    }}

    /* ── Push buttons (default style) ────────────────────────────────── */
    QPushButton {{
        background-color: {c['blue']};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-size: 10pt;
    }}
    QPushButton:hover  {{ background-color: #3498db; }}
    QPushButton:pressed {{ background-color: #1a6da3; }}
    QPushButton:disabled {{ background-color: #b2bec3; color: #ffffff; }}

    /* ── Line edit / spin box ─────────────────────────────────────────── */
    QLineEdit, QDoubleSpinBox, QSpinBox, QDateEdit, QComboBox {{
        border: 1px solid {c['card_border']};
        border-radius: 4px;
        padding: 4px 8px;
        background: {c['card_bg']};
        color: {c['text_primary']};
        selection-background-color: {c['blue']};
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus,
    QDateEdit:focus, QComboBox:focus {{
        border-color: {c['blue']};
        outline: none;
    }}

    /* ── Combo box dropdown ───────────────────────────────────────────── */
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        selection-background-color: {c['blue_light']};
        color: {c['text_primary']};
    }}

    /* ── Table widget ─────────────────────────────────────────────────── */
    QTableWidget {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 6px;
        gridline-color: {c['card_border']};
        font-size: 10pt;
        alternate-background-color: #f8f9fa;
    }}
    QHeaderView::section {{
        background: {c['sidebar_bg']};
        color: {c['sidebar_text']};
        font-weight: bold;
        font-size: 9pt;
        padding: 6px 8px;
        border: none;
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QTableWidget::item:selected {{
        background: {c['blue_light']};
        color: {c['text_primary']};
    }}

    /* ── Group box ────────────────────────────────────────────────────── */
    QGroupBox {{
        background: {c['card_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 6px;
        margin-top: 8px;
        padding: 12px 12px 12px 12px;
        font-weight: bold;
        font-size: 10pt;
        color: {c['text_primary']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        background: {c['card_bg']};
    }}

    /* ── Message box ──────────────────────────────────────────────────── */
    QMessageBox {{
        background: {c['card_bg']};
    }}
    /* Explicitly style dialog buttons — QMessageBox's white background
       cascades and can override the global QPushButton rule. */
    QMessageBox QPushButton {{
        background-color: {c['blue']};
        color: #ffffff;
        border: none;
        border-radius: 4px;
        padding: 6px 20px;
        font-size: 10pt;
        min-width: 70px;
    }}
    QMessageBox QPushButton:hover  {{ background-color: #3498db; }}
    QMessageBox QPushButton:pressed {{ background-color: #1a6da3; }}
    /* Destructive / default button gets a more prominent colour */
    QMessageBox QPushButton[text="Yes"],
    QMessageBox QPushButton[text="OK"] {{
        background-color: {c['blue']};
    }}
    QMessageBox QPushButton[text="Cancel"],
    QMessageBox QPushButton[text="No"] {{
        background-color: {c['text_secondary']};
    }}

    /* ── Calendar widget — always light background for readability ───── */
    QCalendarWidget {{
        background-color: #ffffff;
        color: #2c3e50;
        border: 1px solid {c['card_border']};
        border-radius: 6px;
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: #ffffff;
        color: #2c3e50;
        selection-background-color: {c['blue']};
        selection-color: #ffffff;
        alternate-background-color: #f8f9fa;
        font-size: 10pt;
        outline: none;
    }}
    QCalendarWidget QAbstractItemView:disabled {{
        color: #b2bec3;
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background-color: {c['sidebar_bg']};
        border-radius: 6px 6px 0 0;
    }}
    QCalendarWidget QToolButton {{
        background-color: transparent;
        color: #ecf0f1;
        border: none;
        border-radius: 3px;
        padding: 4px 8px;
        font-size: 10pt;
        font-weight: bold;
    }}
    QCalendarWidget QToolButton:hover {{
        background-color: {c['sidebar_hover']};
    }}
    QCalendarWidget QSpinBox {{
        background-color: {c['sidebar_bg']};
        color: #ecf0f1;
        border: none;
        font-size: 10pt;
    }}
    QCalendarWidget QMenu {{
        background-color: #ffffff;
        color: #2c3e50;
    }}

    /* ── Tool tip ─────────────────────────────────────────────────────── */
    QToolTip {{
        background: {c['sidebar_bg']};
        color: {c['sidebar_text']};
        border: 1px solid {c['sidebar_divider']};
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 9pt;
    }}

    /* ── Check box ────────────────────────────────────────────────────── */
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {c['card_border']};
        border-radius: 3px;
        background: {c['card_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {c['blue']};
        border-color: {c['blue']};
        image: url({_check});
    }}
    """


def apply_theme(app: QApplication) -> None:
    """
    Apply the global theme to a QApplication instance.
    Call this once in main.py after creating QApplication.

    Sets:
      • Global QSS stylesheet
      • Default application font (Segoe UI 10pt)
    """
    font = QFont(BASE_FONT_FAMILY, BASE_FONT_SIZE)
    app.setFont(font)
    app.setStyleSheet(_global_qss())


# ── Convenience style strings ─────────────────────────────────────────────────
# These are used by individual screen files that need per-widget overrides.

def header_bar_style() -> str:
    """Dark header bar (54px) used at top of each screen."""
    return f"background-color: {COLORS['sidebar_bg']};"


def dark_date_edit_style() -> str:
    """
    Style for a QDateEdit sitting in a dark header bar.

    Includes explicit calendar popup resets so that weekday numbers stay
    readable.  Without these resets, Qt cascades the header's color:#ecf0f1
    into the calendar popup, making weekday cells invisible (white-on-white).
    """
    c = COLORS
    return f"""
        QDateEdit {{
            background: #3d5166; color: #ecf0f1;
            border: 1px solid #566573; border-radius: 4px;
            padding: 2px 6px; font-size: 11px;
        }}
        /* ── Calendar popup resets ─────────────────────────────────────── */
        QCalendarWidget {{
            background-color: #ffffff; color: #2c3e50;
        }}
        QCalendarWidget QAbstractItemView {{
            background-color: #ffffff;
            color: #2c3e50;
            selection-background-color: {c['blue']};
            selection-color: #ffffff;
            alternate-background-color: #f8f9fa;
            font-size: 10pt;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: #b2bec3;
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {c['sidebar_bg']};
            border-radius: 6px 6px 0 0;
        }}
        QCalendarWidget QToolButton {{
            color: #ecf0f1; background: transparent; border: none;
            border-radius: 3px; padding: 4px 8px; font-weight: bold;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {c['sidebar_hover']};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {c['sidebar_bg']}; color: #ecf0f1; border: none;
        }}
        QCalendarWidget QMenu {{
            background-color: #ffffff; color: #2c3e50;
        }}
    """


def card_style(border_radius: int = 8) -> str:
    """White card with subtle border and rounded corners."""
    return (
        f"background-color: {COLORS['card_bg']};"
        f"border: 1px solid {COLORS['card_border']};"
        f"border-radius: {border_radius}px;"
    )


def btn_primary(color: str = None) -> str:
    """Primary action button style."""
    bg = color or COLORS["blue"]
    return f"""
        QPushButton {{
            background-color: {bg}; color: white; border: none;
            border-radius: 4px; padding: 0 16px; font-size: 10pt;
        }}
        QPushButton:hover {{ background-color: {bg}cc; }}
        QPushButton:pressed {{ background-color: {bg}99; }}
    """


def btn_outline() -> str:
    """Outline (ghost) button style."""
    return f"""
        QPushButton {{
            background-color: transparent; color: {COLORS['text_primary']};
            border: 1px solid {COLORS['card_border']};
            border-radius: 4px; padding: 0 14px; font-size: 10pt;
        }}
        QPushButton:hover {{ background-color: {COLORS['blue_light']}; }}
    """

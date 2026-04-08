"""
docking_utils.py — Shared helpers for embedded QDockWidget layouts.

Three functions used by CEC Tracker, Simulation Screen, and Mass Balance
to create an inner QMainWindow that manages dockable panels within the
fixed outer window. The outer navigation (sidebar, QStackedWidget) is
completely unaffected.

Pattern:
    inner_mw = make_inner_window()          # embed as widget
    dock_a   = make_dock("Title A", panel_a)
    dock_b   = make_dock("Title B", panel_b)
    inner_mw.addDockWidget(Qt.LeftDockWidgetArea,  dock_a)
    inner_mw.addDockWidget(Qt.RightDockWidgetArea, dock_b)
    make_dock_toolbar(inner_mw, [dock_a, dock_b])  # hide/show toggles
"""

from PySide6.QtWidgets import QMainWindow, QDockWidget, QToolBar, QSizePolicy
from PySide6.QtCore import Qt


# Title-bar colours — match the dark header bar used by all screens
_C_HDR  = "#2c3e50"
_C_TEXT = "#ecf0f1"


def make_inner_window() -> QMainWindow:
    """
    Create a QMainWindow that embeds as a plain widget inside a QVBoxLayout.

    Qt.WindowType.Widget prevents it from becoming a standalone OS window.
    The menubar and statusbar are hidden immediately so they don't consume
    any vertical space inside the 1280×760 fixed outer window.
    """
    mw = QMainWindow()
    # Embed as a widget — prevents a separate OS window from appearing
    mw.setWindowFlags(Qt.WindowType.Widget)
    # Suppress the menubar and statusbar that QMainWindow creates by default
    mw.menuBar().setVisible(False)
    mw.statusBar().hide()
    mw.setStyleSheet("QMainWindow { background: #f5f6fa; }")
    mw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return mw


def make_dock(title: str, widget, object_name: str = "") -> QDockWidget:
    """
    Wrap a panel widget in a styled QDockWidget.

    All three features (float, move, close) are enabled so the researcher can:
      - Drag the title bar to rearrange or float the panel
      - Click the float button to detach it as a standalone OS window
      - Close the panel (hide it) and restore it via the toolbar toggle button
    """
    dock = QDockWidget(title)
    dock.setWidget(widget)
    if object_name:
        dock.setObjectName(object_name)
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetMovable   |
        QDockWidget.DockWidgetFeature.DockWidgetClosable,
    )
    # Dark title bar matching the screen header bars
    dock.setStyleSheet(f"""
        QDockWidget::title {{
            background: {_C_HDR};
            color: {_C_TEXT};
            padding: 5px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QDockWidget {{
            border: 1px solid #dde1e7;
        }}
    """)
    return dock


def make_dock_toolbar(inner_mw: QMainWindow, docks: list) -> QToolBar:
    """
    Add a compact toggle toolbar above the dock area of the inner QMainWindow.

    Each dock contributes one toggle button via dock.toggleViewAction().
    The action stays automatically in sync with the dock's visible state —
    no manual signal wiring is needed. A closed dock can be re-opened by
    clicking its button in this toolbar.
    """
    toolbar = QToolBar("Panels")
    toolbar.setMovable(False)   # prevent the researcher from accidentally dragging it away
    toolbar.setFloatable(False)
    toolbar.setStyleSheet("""
        QToolBar {
            background: #f0f3f4;
            border: none;
            border-bottom: 1px solid #dde1e7;
            spacing: 4px;
            padding: 3px 8px;
        }
        QToolBar QToolButton {
            background: transparent;
            color: #636e72;
            border: 1px solid #ced4da;
            border-radius: 3px;
            padding: 3px 10px;
            font-size: 10px;
        }
        QToolBar QToolButton:checked {
            background: #2c3e50;
            color: #ecf0f1;
            border-color: #2c3e50;
        }
        QToolBar QToolButton:hover {
            background: #d5dbdb;
            color: #2c3e50;
        }
    """)
    # Text-only buttons — icon-only would be ambiguous for dock toggle buttons
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

    for dock in docks:
        action = dock.toggleViewAction()
        toolbar.addAction(action)

    inner_mw.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
    return toolbar

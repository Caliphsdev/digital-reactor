"""
resources.py — Resolve bundled data file paths across environments.

Works correctly in:
  Development       — returns path relative to project root
  PyInstaller dist  — returns path relative to sys._MEIPASS (_internal/)
  Nuitka standalone — returns path relative to the compiled executable directory

Usage:
    from core.resources import resource_path
    svg_path = resource_path("ui/icons/check_white.svg")
"""

import os
import sys


def _get_base() -> str:
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller: extracted files live under sys._MEIPASS
        return sys._MEIPASS

    exe_name = os.path.basename(sys.executable).lower()
    if exe_name.startswith('python') or exe_name.startswith('pythonw'):
        # Development: running under a Python interpreter.
        # Project root is the parent of the core/ package directory.
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Nuitka standalone (or any other compiled executable):
    # data files are placed next to the .exe by --include-data-dir flags.
    return os.path.dirname(os.path.abspath(sys.executable))


_BUNDLE_BASE = _get_base()


def resource_path(relative: str) -> str:
    """Return the absolute path to a bundled data file.

    Pass a forward-slash relative path from the project root, e.g.:
        resource_path("ui/icons/check_white.svg")
        resource_path("assets/styles.qss")
    """
    return os.path.join(_BUNDLE_BASE, relative)

"""
paths.py — Single source of truth for all user-data directory paths.

All persistent user data (database, backups, ML models) lives under
APP_DATA_DIR, which resolves to:

    Windows:  C:\\Users\\<name>\\AppData\\Roaming\\DigitalReactor\\
    Fallback: <user home>\\DigitalReactor\\

This directory is completely separate from the application installation
folder, so updating or reinstalling the .exe never touches the researcher's
data.

Import pattern:
    from core.paths import APP_DATA_DIR, DB_PATH, MODELS_DIR
"""

import os
from pathlib import Path

# ── Root user-data folder ─────────────────────────────────────────────────────
# %APPDATA% is set on every modern Windows install.
# The fallback (home dir) handles Linux/macOS development environments.
_appdata_root = Path(os.environ.get("APPDATA") or Path.home())
APP_DATA_DIR  = _appdata_root / "DigitalReactor"

# Ensure the directory exists the moment this module is imported
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Derived paths ─────────────────────────────────────────────────────────────
DB_PATH    = APP_DATA_DIR / "reactor.db"
MODELS_DIR = APP_DATA_DIR / "models"

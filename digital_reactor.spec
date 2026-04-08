# -*- mode: python ; coding: utf-8 -*-
#
# digital_reactor.spec — PyInstaller build definition for Digital Reactor v1.0
#
# Build command (from project root, venv active):
#   pyinstaller digital_reactor.spec --noconfirm
#
# Or use build.bat which handles venv activation and Inno Setup automatically.
#
# Output: dist/DigitalReactor/   ← copy this entire folder to deploy, or
#         run the Inno Setup installer to create a proper setup .exe.

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    collect_all,
)

# ── Non-Python data files the app reads at runtime ────────────────────────────
#    Format: (source_glob_or_dir, destination_inside_bundle)
datas = []

# qtawesome — Font Awesome icon fonts (referenced by name at runtime)
datas += collect_data_files('qtawesome')

# matplotlib — mpl-data: bundled fonts, style sheets, sample data
datas += collect_data_files('matplotlib')

# scikit-learn — includes compiled .pyx/.so extensions and data files
datas += collect_data_files('sklearn')

# App assets: SVG check icon used in QSS; .ico for window chrome
datas += [('ui/icons', 'ui/icons')]

# ── Hidden imports ─────────────────────────────────────────────────────────────
#    Modules that PyInstaller's static analysis misses because they are loaded
#    via string (e.g. SQLAlchemy connection-string dialect, joblib-loaded models)
hiddenimports = []

# SQLAlchemy — sqlite dialect is resolved at runtime from the connection string
hiddenimports += [
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.sqlite.pysqlite',
    'sqlalchemy.pool',
    'sqlalchemy.pool.impl',
    'sqlalchemy.event',
    'sqlalchemy.sql.visitors',
]

# scikit-learn — estimators are referenced by class name when joblib loads a model
hiddenimports += collect_submodules('sklearn')

# pandas optional dependencies
hiddenimports += [
    'pandas._libs.tslibs.np_datetime',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.tslibs.offsets',
    'pandas._libs.tslibs.timedeltas',
    'pandas._libs.tslibs.timestamps',
]

# pyqtgraph — uses dynamic backend selection
hiddenimports += collect_submodules('pyqtgraph')

# matplotlib — Qt backend for any inline rendering
hiddenimports += [
    'matplotlib.backends.backend_agg',
    'matplotlib.backends.backend_qtagg',
]

# openpyxl — cell styles loaded dynamically
hiddenimports += [
    'openpyxl.cell._writer',
    'openpyxl.styles.numbers',
]

# ── Packages that need full collect (data + submodules) ───────────────────────
# pyqtgraph ships compiled extensions that PyInstaller needs help finding
_pg_datas, _pg_bins, _pg_hidden = collect_all('pyqtgraph')
datas        += _pg_datas
hiddenimports += _pg_hidden
# Note: _pg_bins added to binaries below

# ── Analysis ───────────────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=_pg_bins,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Only exclude modules that are provably unused AND have no hidden dependents.
    # Be conservative — importlib.metadata pulls in email/html/http transitively.
    excludes=[
        'tkinter', '_tkinter',  # Qt app — no Tk needed
        'turtle',               # Python toy module
        'antigravity',          # Easter egg
        'this',                 # Easter egg
        'curses',               # Terminal UI — not needed on Windows
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
    optimize=1,   # compile to .pyc with basic optimisation (removes assert/docstrings)
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir mode: binaries go into COLLECT below
    name='DigitalReactor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,             # do not strip debug symbols from DLLs on Windows
    upx=False,               # UPX disabled — can break PySide6/Qt DLLs on Windows
    console=False,           # no console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ui/icons/favicon.ico',
    version='version_info.txt',  # embeds Windows VERSIONINFO into the .exe
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DigitalReactor',   # output folder: dist/DigitalReactor/
)

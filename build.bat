@echo off
setlocal EnableDelayedExpansion
title Digital Reactor — Build

:: ============================================================================
::  build.bat — One-click build script for Digital Reactor
::
::  Produces:
::    dist\DigitalReactor\           Nuitka standalone app folder
::    installer\Output\DigitalReactor_Setup_v1.0.exe   (if Inno Setup found)
::
::  Usage:
::    build.bat           full build (Nuitka + Inno Setup if available)
::    build.bat /apponly  Nuitka only (skip Inno Setup)
::    build.bat /clean    clean build artifacts then exit
::
::  Prerequisites:
::    - Python virtual environment at .venv\
::    - Visual Studio Build Tools 2022 (MSVC) — for Nuitka C compilation
::    - Inno Setup 6 — for installer creation (optional)
:: ============================================================================

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "ISS=%ROOT%installer\digital_reactor.iss"
set "APP_NAME=DigitalReactor"
set "APP_VERSION=1.0"
set "APP_ONLY=0"

:: Change to the project root so all relative paths work correctly
cd /d "%ROOT%"

:: Parse arguments
for %%A in (%*) do (
    if /I "%%A"=="/apponly" set "APP_ONLY=1"
    if /I "%%A"=="/clean"   goto :clean
)

echo.
echo ============================================================
echo  Digital Reactor v%APP_VERSION% ^| Nuitka Build Script
echo ============================================================
echo.

:: ── Virtual environment ───────────────────────────────────────────────────────
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at: %VENV%
    echo         Run:  python -m venv .venv   then   pip install -r requirements.txt
    exit /b 1
)

echo [Setup]  Activating virtual environment...
call "%VENV%\Scripts\activate.bat"

:: ── Nuitka and build dependencies ────────────────────────────────────────────
echo [Setup]  Checking Nuitka...
python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo [Setup]  Installing Nuitka and build helpers...
    pip install --quiet nuitka ordered-set zstandard
)

:: ── Visual C++ Redistributable ───────────────────────────────────────────────
if not exist "%ROOT%installer\vc_redist.x64.exe" (
    echo [Setup]  vc_redist.x64.exe not found in installer\.
    echo          Downloading Visual C++ 2022 Redistributable from Microsoft...
    powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%ROOT%installer\vc_redist.x64.exe' -UseBasicParsing"
    if not exist "%ROOT%installer\vc_redist.x64.exe" (
        echo [ERROR] Download failed. Place vc_redist.x64.exe in installer\ manually.
        exit /b 1
    )
    echo [OK]    vc_redist.x64.exe downloaded.
)

:: ── Clean previous build ──────────────────────────────────────────────────────
echo [1/3]   Cleaning previous build artifacts...
if exist "%ROOT%build"  rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist"   rmdir /s /q "%ROOT%dist"
mkdir "%ROOT%dist"

:: ── Nuitka compilation ────────────────────────────────────────────────────────
echo [2/3]   Compiling with Nuitka (first build: 5-15 minutes)...
echo          Subsequent builds are faster due to incremental C caching.
echo.

python -m nuitka ^
  --standalone ^
  --windows-icon-from-ico=ui\icons\favicon.ico ^
  --windows-product-name="Digital Reactor" ^
  --windows-product-version=1.0.0.0 ^
  --windows-file-version=1.0.0.0 ^
  --windows-company-name="Caliphs Zvinowanda" ^
  --windows-file-description="PFAS & CEC Wastewater Research Platform" ^
  --windows-copyright="(c) 2026 Caliphs Zvinowanda. All rights reserved." ^
  --windows-console-mode=disable ^
  --enable-plugin=pyside6 ^
  --include-package=sqlalchemy ^
  --include-package=sqlalchemy.dialects ^
  --include-package=sqlalchemy.dialects.sqlite ^
  --include-package=sqlalchemy.pool ^
  --include-package=sklearn ^
  --include-package=joblib ^
  --include-package=threadpoolctl ^
  --include-package=openpyxl ^
  --include-package=pyqtgraph ^
  --include-package=pandas ^
  --include-package=numpy ^
  --include-package=matplotlib ^
  --include-package=qtawesome ^
  --include-package-data=qtawesome ^
  --include-package-data=matplotlib ^
  --include-package-data=sklearn ^
  --include-package-data=pyqtgraph ^
  --include-package-data=openpyxl ^
  --include-data-dir=ui\icons=ui/icons ^
  --include-data-dir=assets=assets ^
  --nofollow-import-to=tkinter ^
  --nofollow-import-to=_tkinter ^
  --nofollow-import-to=turtle ^
  --nofollow-import-to=antigravity ^
  --nofollow-import-to=curses ^
  --output-dir=build ^
  --output-filename=%APP_NAME%.exe ^
  main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Nuitka compilation failed. See output above for details.
    exit /b 1
)

:: ── Move Nuitka output to dist\DigitalReactor ─────────────────────────────────
:: Nuitka names the output folder after the entry script: build\main.dist\
:: We rename it to dist\DigitalReactor\ to match the Inno Setup source path.
move "%ROOT%build\main.dist" "%ROOT%dist\%APP_NAME%"
if errorlevel 1 (
    echo [ERROR] Could not move build\main.dist to dist\%APP_NAME%
    exit /b 1
)

:: Verify the executable was produced
if not exist "%ROOT%dist\%APP_NAME%\%APP_NAME%.exe" (
    echo [ERROR] Expected output not found: dist\%APP_NAME%\%APP_NAME%.exe
    exit /b 1
)

echo.
echo [OK]    App bundle: dist\%APP_NAME%\%APP_NAME%.exe

:: ── Inno Setup ───────────────────────────────────────────────────────────────
if "%APP_ONLY%"=="1" (
    echo.
    echo [Skip]  Inno Setup skipped ^(/apponly flag set^).
    goto :done
)

echo [3/3]   Looking for Inno Setup 6 compiler...

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo.
    echo [WARN]  Inno Setup 6 not found. Installer was not created.
    echo         Download from: https://jrsoftware.org/isinfo.php
    echo         Then run manually:
    echo           "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\digital_reactor.iss
    goto :done
)

if not exist "%ROOT%installer\Output" mkdir "%ROOT%installer\Output"

echo [3/3]   Compiling installer with Inno Setup...
"!ISCC!" "%ISS%"

if errorlevel 1 (
    echo.
    echo [ERROR] Inno Setup compilation failed.
    exit /b 1
)

echo.
echo [OK]    Installer: installer\Output\%APP_NAME%_Setup_v%APP_VERSION%.exe

:done
echo.
echo ============================================================
echo  BUILD COMPLETE
echo.
echo  App folder : dist\%APP_NAME%\
if exist "%ROOT%installer\Output\%APP_NAME%_Setup_v%APP_VERSION%.exe" (
    echo  Installer  : installer\Output\%APP_NAME%_Setup_v%APP_VERSION%.exe
)
echo ============================================================
echo.
exit /b 0

:: ── Clean target ─────────────────────────────────────────────────────────────
:clean
echo [Clean] Removing build\, dist\, installer\Output\...
if exist "%ROOT%build"             rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist"              rmdir /s /q "%ROOT%dist"
if exist "%ROOT%installer\Output"  rmdir /s /q "%ROOT%installer\Output"
echo [Clean] Done.
exit /b 0

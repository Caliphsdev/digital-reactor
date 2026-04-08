@echo off
setlocal EnableDelayedExpansion
title Digital Reactor — Build

:: ============================================================================
::  build.bat — One-click build script for Digital Reactor
::
::  Produces:
::    dist\DigitalReactor\           PyInstaller app folder
::    installer\Output\DigitalReactor_Setup_v1.0.exe   (if Inno Setup found)
::
::  Usage:
::    build.bat           full build (PyInstaller + Inno Setup if available)
::    build.bat /apponly  PyInstaller only (skip Inno Setup)
::    build.bat /clean    clean build artifacts then exit
:: ============================================================================

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "SPEC=%ROOT%digital_reactor.spec"
set "ISS=%ROOT%installer\digital_reactor.iss"
set "APP_VERSION=1.0"
set "APP_ONLY=0"

:: Parse arguments
for %%A in (%*) do (
    if /I "%%A"=="/apponly" set "APP_ONLY=1"
    if /I "%%A"=="/clean"   goto :clean
)

echo.
echo ============================================================
echo  Digital Reactor v%APP_VERSION% ^| Build Script
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

:: ── PyInstaller ───────────────────────────────────────────────────────────────
echo [Setup]  Checking PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [Setup]  Installing PyInstaller...
    pip install --quiet pyinstaller
)

:: ── Visual C++ Redistributable ───────────────────────────────────────────────
if not exist "%ROOT%installer\vc_redist.x64.exe" (
    echo [Setup]  vc_redist.x64.exe not found in installer\.
    echo          Downloading Visual C++ 2022 Redistributable from Microsoft...
    powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%ROOT%installer\vc_redist.x64.exe' -UseBasicParsing"
    if not exist "%ROOT%installer\vc_redist.x64.exe" (
        echo [ERROR] Download failed. Place vc_redist.x64.exe in the installer\ folder manually.
        exit /b 1
    )
    echo [OK]    vc_redist.x64.exe downloaded.
)

:: ── Clean previous build ──────────────────────────────────────────────────────
echo [1/3]   Cleaning previous build artifacts...
if exist "%ROOT%build" (
    rmdir /s /q "%ROOT%build"
)
if exist "%ROOT%dist" (
    rmdir /s /q "%ROOT%dist"
)

:: ── PyInstaller ───────────────────────────────────────────────────────────────
echo [2/3]   Running PyInstaller (this takes 1–3 minutes)...
echo.
pyinstaller "%SPEC%" --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. See output above for details.
    exit /b 1
)

:: Verify the exe was created
if not exist "%ROOT%dist\DigitalReactor\DigitalReactor.exe" (
    echo [ERROR] Expected output not found: dist\DigitalReactor\DigitalReactor.exe
    exit /b 1
)

echo.
echo [OK]    App bundle: dist\DigitalReactor\DigitalReactor.exe

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
echo [OK]    Installer: installer\Output\DigitalReactor_Setup_v%APP_VERSION%.exe

:done
echo.
echo ============================================================
echo  BUILD COMPLETE
echo.
echo  App folder : dist\DigitalReactor\
if exist "%ROOT%installer\Output\DigitalReactor_Setup_v%APP_VERSION%.exe" (
    echo  Installer  : installer\Output\DigitalReactor_Setup_v%APP_VERSION%.exe
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

@echo off
title ow-vision
color 0b
cd /d "%~dp0"

:: ── Check required files exist ─────────────────────────
if not exist "app.py" (
    echo.
    echo   ERROR: app.py not found!
    echo.
    echo   You need to download the ENTIRE ow-vision folder,
    echo   not just this .bat file.
    echo.
    echo   Go to the GitHub repo, click the green "Code" button,
    echo   then "Download ZIP". Extract the ZIP, then double-click
    echo   ow-vision.bat INSIDE the extracted folder.
    echo.
    pause
    exit /b 1
)

:: ── Check Python is installed ──────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python is not installed!
    echo.
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Download and install Python
    echo   3. IMPORTANT: Check "Add Python to PATH" during install
    echo   4. Then double-click this file again
    echo.
    pause
    exit /b 1
)

echo.
echo   ow-vision is starting...
echo.

:: ── First-time setup ───────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo   [1/2] Setting up environment (first time only)...
    python -m venv .venv
)

.venv\Scripts\python.exe -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo   [2/2] Installing dependencies (first time only, please wait)...
    .venv\Scripts\pip.exe install -q -r requirements.txt
)

:: ── Launch the app (browser opens automatically) ───────
echo   Launching... your browser will open now.
echo   (You can close this window)
echo.
start "" .venv\Scripts\pythonw.exe app.py
exit /b

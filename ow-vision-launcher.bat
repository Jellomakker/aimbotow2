@echo off
setlocal enabledelayedexpansion
title OW Vision - Setup ^& Launch
color 0A

echo.
echo  ============================================
echo   OW VISION - Overwatch 2 AI Triggerbot
echo  ============================================
echo.

:: ── Check for Python ──
where python >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Go to https://www.python.org/downloads/
    echo  Download Python 3.10 or newer.
    echo  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

:: ── Check Python version is 3.10+ ──
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Found Python %PYVER%

:: ── Set install folder ──
set "INSTALL_DIR=%USERPROFILE%\ow-vision"
echo  Install folder: %INSTALL_DIR%
echo.

:: ── Download or update from GitHub ──
if exist "%INSTALL_DIR%\app.py" (
    echo  [OK] OW Vision is already downloaded.
    echo  Checking for updates...
    where git >nul 2>&1
    if !errorlevel! equ 0 (
        pushd "%INSTALL_DIR%"
        git pull --ff-only >nul 2>&1
        popd
        echo  Updated.
    ) else (
        echo  Git not found, skipping update.
    )
) else (
    echo  Downloading OW Vision...
    echo.

    :: Try git clone first
    where git >nul 2>&1
    if !errorlevel! equ 0 (
        git clone https://github.com/Jellomakker/aimbotow2.git "%INSTALL_DIR%_tmp" >nul 2>&1
        if exist "%INSTALL_DIR%_tmp\ow-vision\app.py" (
            robocopy "%INSTALL_DIR%_tmp\ow-vision" "%INSTALL_DIR%" /E /NFL /NDL /NJH /NJS >nul
            rd /s /q "%INSTALL_DIR%_tmp" >nul 2>&1
        ) else (
            echo  [ERROR] Clone failed.
            rd /s /q "%INSTALL_DIR%_tmp" >nul 2>&1
            goto :download_zip
        )
    ) else (
        goto :download_zip
    )
    goto :downloaded
)
goto :downloaded

:download_zip
echo  Downloading ZIP from GitHub...
powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/Jellomakker/aimbotow2/archive/refs/heads/main.zip' -OutFile '%TEMP%\ow-vision.zip' -UseBasicParsing } catch { exit 1 }"
if %errorlevel% neq 0 (
    color 0C
    echo  [ERROR] Download failed. Check your internet connection.
    pause
    exit /b 1
)
echo  Extracting...
powershell -Command "Expand-Archive -Path '%TEMP%\ow-vision.zip' -DestinationPath '%TEMP%\ow-vision-extract' -Force"
if exist "%TEMP%\ow-vision-extract\aimbotow2-main\ow-vision\app.py" (
    robocopy "%TEMP%\ow-vision-extract\aimbotow2-main\ow-vision" "%INSTALL_DIR%" /E /NFL /NDL /NJH /NJS >nul
) else (
    color 0C
    echo  [ERROR] Extraction failed.
    pause
    exit /b 1
)
rd /s /q "%TEMP%\ow-vision-extract" >nul 2>&1
del "%TEMP%\ow-vision.zip" >nul 2>&1

:downloaded
echo.

:: ── Verify files exist ──
if not exist "%INSTALL_DIR%\app.py" (
    color 0C
    echo  [ERROR] app.py not found. Download may have failed.
    pause
    exit /b 1
)

:: ── Create virtual environment ──
if not exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv "%INSTALL_DIR%\.venv"
    if %errorlevel% neq 0 (
        color 0C
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)

:: ── Install dependencies ──
"%INSTALL_DIR%\.venv\Scripts\pip.exe" show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Installing dependencies (this may take a few minutes)...
    echo  Please wait...
    echo.
    "%INSTALL_DIR%\.venv\Scripts\pip.exe" install -r "%INSTALL_DIR%\requirements.txt" -q
    if %errorlevel% neq 0 (
        color 0C
        echo.
        echo  [ERROR] Failed to install dependencies.
        echo  Try running this again. If it keeps failing, you may need
        echo  to install Visual C++ Build Tools from:
        echo  https://visualstudio.microsoft.com/visual-cpp-build-tools/
        pause
        exit /b 1
    )
    echo  [OK] Dependencies installed.
)

:: ── Launch ──
echo.
echo  ============================================
echo   Starting OW Vision...
echo   A browser window will open automatically.
echo   Keep this window open while using the app.
echo  ============================================
echo.

cd /d "%INSTALL_DIR%"
start "" "%INSTALL_DIR%\.venv\Scripts\pythonw.exe" app.py

:: Wait a moment then open browser as backup
timeout /t 3 /nobreak >nul
echo  If the browser didn't open, go to:
echo  http://127.0.0.1:18729
echo.
echo  Press any key to close the app and exit.
pause >nul

:: Kill the app when user presses a key
taskkill /f /im pythonw.exe >nul 2>&1
echo  OW Vision closed.
timeout /t 2 >nul

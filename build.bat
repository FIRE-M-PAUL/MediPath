@echo off
title MediPath — Build Desktop EXE
color 0A
echo.
echo ============================================
echo   MediPath Desktop Application Builder
echo ============================================
echo.

:: ── Check Python is available ────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.x and try again.
    pause
    exit /b 1
)

:: ── Install / upgrade dependencies ───────────
echo [1/4] Installing required packages...
pip install pyinstaller flask flask_sqlalchemy flask_bcrypt flask_login flask_cors flask-wtf --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Clean previous build artifacts ───────────
echo [2/4] Cleaning old build files...
if exist build    rmdir /s /q build
if exist dist     rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
echo       Done.
echo.

:: ── Run PyInstaller ───────────────────────────
echo [3/4] Building MediPath.exe (this may take 2-5 minutes)...
pyinstaller medipath.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above for details.
    echo         Also check medipath_errors.log after running the app.
    pause
    exit /b 1
)
echo       Build complete!
echo.

:: ── Show result ───────────────────────────────
echo [4/4] Opening output folder...
echo.
echo ============================================
echo   SUCCESS! Your .exe is ready:
echo   dist\MediPath.exe
echo ============================================
echo.
echo You can now:
echo   1. Double-click dist\MediPath.exe to run
echo   2. Copy dist\MediPath.exe to any Windows PC
echo      (Python NOT required on target machine)
echo.

:: Open the dist folder in Explorer
explorer dist

pause

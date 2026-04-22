@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0frontend"

echo ============================================================
echo  PlotPilot Frontend Launcher
echo ============================================================

set "NODE_DIR=%~dp0tools\nodejs22\node-v22.14.0-win-x64"
set "PATH=%NODE_DIR%;%PATH%"

if not exist "%NODE_DIR%\node.exe" (
    echo [ERROR] Node.js not found at %NODE_DIR%
    pause
    exit /b 1
)

echo Starting frontend on port 3000...
"%NODE_DIR%\npm.cmd" run dev

pause

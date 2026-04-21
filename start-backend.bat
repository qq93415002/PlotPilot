@echo off
chcp 65001 >nul 2>&1
cd /d "d:\WORKSPACE\PlotPilot"

echo ============================================================
echo  PlotPilot Backend Launcher
echo ============================================================

set "PYTHON_EXE=tools\python_embed\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at %PYTHON_EXE%
    pause
    exit /b 1
)

echo Starting backend on port 8006...
set "PYTHONPATH=d:\WORKSPACE\PlotPilot;%%PYTHONPATH%%"
"%PYTHON_EXE%" -m uvicorn interfaces.main:app --host 0.0.0.0 --port 8006

pause

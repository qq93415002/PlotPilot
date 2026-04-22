@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."

:: ============================================================
::  PlotPilot - AI Novel Platform Launcher
::  ============================================================
::  Double-click to run:
::    [1] Auto-extract Python (no install needed)
::    [2] Auto-install pip / venv / dependencies
::    [3] Start backend + open browser
::
::  Usage:
::    Double-click          -> auto mode
::    aitext.bat pack       -> pack for sharing
::    aitext.bat force      -> force restart
::  ============================================================

set "MODE=auto"
if not "%~1"=="" (
    if /i "%~1"=="pack"     set "MODE=pack"
    if /i "%~1"=="p"        set "MODE=pack"
    if /i "%~1"=="force"    set "MODE=force"
    if /i "%~1"=="f"        set "MODE=force"
)

:: ----------------------------------------------------------
:: Step 0: Ensure embedded Python is extracted
:: ----------------------------------------------------------
if not exist "tools\python_embed\python.exe" (
    if exist "tools\python-3.11.9-embed-amd64.zip" (
        echo.
        echo   +--------------------------------------------+
        echo   |  First run: Preparing Python environment... |
        echo   +--------------------------------------------+
        echo.

        powershell -NoProfile -Command "Expand-Archive -Path 'tools\python-3.11.9-embed-amd64.zip' -DestinationPath 'tools\python_embed' -Force"
        if errorlevel 1 (
            echo   [ERROR] Extract failed! Please manually extract tools\python-3.11.9-embed-amd64.zip to tools\python_embed\
            pause
            exit /b 1
        )
        echo   Python ready [OK]
    ) else (
        echo   [WARN] No embedded Python package found, will use system Python
    )
)

:: ----------------------------------------------------------
:: Step 0.5: Install pip for embedded Python
:: ----------------------------------------------------------
if exist "tools\python_embed\python.exe" (
    "tools\python_embed\python.exe" -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   +--------------------------------------------+
        echo   |  First run: Installing pip...               |
        echo   +--------------------------------------------+
        echo.

        if not exist "tools\python_embed\get-pip.py" (
            echo   Downloading get-pip.py...
            "tools\python_embed\python.exe" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', r'tools\python_embed\get-pip.py'); print('OK')" >nul 2>&1
        )

        if exist "tools\python_embed\get-pip.py" (
            "tools\python_embed\python.exe" "tools\python_embed\get-pip.py" --no-warn-script-location -q
            if errorlevel 1 (
                echo   [WARN] pip install failed, continuing anyway...
            ) else (
                echo   pip installed [OK]
                del /f "tools\python_embed\get-pip.py" 2>nul
            )
        ) else (
            echo   [WARN] get-pip.py download failed, check network
        )
    )
)

:: ----------------------------------------------------------
:: Step 1: Find Python (priority: full > venv > embed > system)
:: ----------------------------------------------------------
set "PYTHON_EXE="
set "PYTHON_DIR="

:: A) Full Python with tkinter (for GUI launcher)
if exist "tools\python_full\python.exe" (
    set "PYTHON_EXE=tools\python_full\python.exe"
    set "PYTHON_DIR=tools\python_full\"
    set "TCL_LIBRARY=%CD%\tools\python_full\tcl\tcl8.6"
    set "TK_LIBRARY=%CD%\tools\python_full\tcl\tk8.6"
    set "PATH=%CD%\tools\python_full\DLLs;%PATH%"
    goto :python_found
)

:: B) Virtual env
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "PYTHON_DIR=.venv\Scripts\"
    goto :python_found
)

:: C) Embedded Python
if exist "tools\python_embed\python.exe" (
    set "PYTHON_EXE=tools\python_embed\python.exe"
    set "PYTHON_DIR=tools\python_embed\"
    set "TCL_LIBRARY=%CD%\tools\python_embed\tcl\tcl8.6"
    set "TK_LIBRARY=%CD%\tools\python_embed\tcl\tk8.6"
    goto :python_found
)

:: D) System PATH
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%i"
    goto :python_found
)

:: E) Not found -> guide user
:python_not_found
echo.
echo   +======================================================+
echo   |                                                      |
echo   |     [X]  Python NOT found                             |
echo   |                                                      |
echo   +------------------------------------------------------+
echo   |  Choose one of the following:                         |
echo   |                                                      |
echo   |  Option A (recommended): Put python-3.11.9-embed-     |
echo   |           amd64.zip in tools/ folder, then double-    |
echo   |           click this file again                       |
echo   |                                                      |
echo   |  Option B: Install Python 3.10+ (check Add to PATH)   |
echo   |           https://www.python.org/downloads/            |
echo   |                                                      |
echo   +======================================================+
echo.
pause
exit /b 1

:python_found

:: ----------------------------------------------------------
:: Step 2: Verify Python works
:: ----------------------------------------------------------
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python exists but cannot run: %PYTHON_EXE%
    pause
    exit /b 1
)

:: ----------------------------------------------------------
:: Step 3: Ensure directories exist
:: ----------------------------------------------------------
if not exist "logs"          mkdir logs
if not exist "data\chromadb"  mkdir data\chromadb
if not exist "data\logs"     mkdir data\logs

:: ----------------------------------------------------------
:: Step 3.5: Kill leftover processes on ports
:: ----------------------------------------------------------
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8005 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8006 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: ----------------------------------------------------------
:: Step 4: Launch GUI window (detached process)
:: ----------------------------------------------------------
::  [1] Use pythonw.exe (no console) to launch Tkinter GUI
::  [2] Use start "" to detach the process so bat exits immediately
::  [3] bat exits, black window disappears, GUI lives on its own

set "PYTHONW_EXE=%PYTHON_DIR%pythonw.exe"

if not exist "%PYTHONW_EXE%" (
    echo   [WARN] pythonw.exe not found, using python.exe (may show terminal)
    set "PYTHONW_EXE=%PYTHON_EXE%"
)

echo.
echo   +--------------------------------------------+
echo   |  Starting PlotPilot...                      |
echo   +--------------------------------------------+
echo.

:: Core magic: start "" detaches the process
:: The first "" is the window title for start (must be empty!)
start "" "%PYTHONW_EXE%" -u scripts\install\hub.py %MODE% 2>logs\hub_error.log

exit /b 0

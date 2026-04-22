@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."

:: ============================================================
::  PlotPilot（墨枢）- AI 小说创作平台 启动器
::  ============================================================
::  双击即用，全自动流程：
::    ① 自动解压 Python（无需安装）
::    ② 自动安装 pip / 创建虚拟环境 / 安装依赖
::    ③ 启动后端服务 + 打开浏览器
::
::  用法:
::    双击本文件          → 自动模式
::    aitext.bat pack     → 打包分享
::    aitext.bat force    → 强制重启
::  ============================================================

set "MODE=auto"
if not "%~1"=="" (
    if /i "%~1"=="pack"     set "MODE=pack"
    if /i "%~1"=="p"        set "MODE=pack"
    if /i "%~1"=="force"    set "MODE=force"
    if /i "%~1"=="f"        set "MODE=force"
)

:: ════════════════════════════════════
:: Step 0: 确保内嵌 Python 已解压（零配置核心！）
:: ════════════════════════════════════
if not exist "tools\python_embed\python.exe" (
    if not exist "tools\python-3.11.9-embed-amd64.zip" (
        echo.
        echo   ┌────────────────────────────────────┐
        echo   │  首次启动：正在下载 Python 环境...   │
        echo   └────────────────────────────────────┘
        echo.
        powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile 'tools\python-3.11.9-embed-amd64.zip'"
        if errorlevel 1 (
            echo   [ERROR] Python 下载失败！请检查网络连接
            pause
            exit /b 1
        )
        echo   Python 下载完成 ✓
    )
    
    echo.
    echo   ┌────────────────────────────────────┐
    echo   │  首次启动：正在解压 Python 环境...   │
    echo   └────────────────────────────────────┘
    echo.

    powershell -NoProfile -Command "Expand-Archive -Path 'tools\python-3.11.9-embed-amd64.zip' -DestinationPath 'tools\python_embed' -Force"
    if errorlevel 1 (
        echo   [ERROR] 解压失败！请手动解压 tools\python-3.11.9-embed-amd64.zip 到 tools\python_embed\
        pause
        exit /b 1
    )
    echo   Python 环境就绪 ✓
)

:: ════════════════════════════════════
:: Step 0.5: 为内嵌 Python 自动安装 pip（embeddable 版默认无 pip）
:: ════════════════════════════════════
if exist "tools\python_embed\python.exe" (
    "tools\python_embed\python.exe" -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   ┌────────────────────────────────────┐
        echo   │  首次启动：正在为内嵌 Python 安装 pip... │
        echo   └────────────────────────────────────┘
        echo.

        :: 下载 get-pip.py（如果不存在）
        if not exist "tools\python_embed\get-pip.py" (
            echo   正在下载 get-pip.py...
            "tools\python_embed\python.exe" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', r'tools\python_embed\get-pip.py'); print('OK')" >nul 2>&1
        )

        :: 安装 pip
        if exist "tools\python_embed\get-pip.py" (
            "tools\python_embed\python.exe" "tools\python_embed\get-pip.py" --no-warn-script-location -q
            if errorlevel 1 (
                echo   [WARN] pip 自动安装失败，将尝试继续...
            ) else (
                echo   pip 安装完成 ✓
                :: 清理临时文件
                del /f "tools\python_embed\get-pip.py" 2>nul
            )
        ) else (
            echo   [WARN] get-pip.py 下载失败，请检查网络连接
        )
    )
)

:: ════════════════════════════════════
:: Step 1: 强制使用内置 Python 环境
:: ════════════════════════════════════
if not exist "tools\python_embed\python.exe" (
    echo.
    echo   ╔═══════════════════════════════════════════════════════════╗
    echo   ║  [ERROR] 内置 Python 环境不存在！                           ║
    echo   ║                                                           ║
    echo   ║  请确保 tools\python-3.11.9-embed-amd64.zip 已解压         ║
    echo   ║  到 tools\python_embed\ 目录                               ║
    echo   ╚═══════════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

set "PYTHON_EXE=tools\python_embed\python.exe"
set "TCL_LIBRARY=%CD%\tools\python_embed\tcl\tcl8.6"
set "TK_LIBRARY=%CD%\tools\python_embed\tcl\tk8.6"

:python_found

:: ════════════════════════════════════
:: Step 2: 验证 Python 可用
:: ════════════════════════════════════
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python 存在但无法运行: %PYTHON_EXE%
    pause
    exit /b 1
)

:: ════════════════════════════════════
:: Step 3: 确保目录存在
:: ════════════════════════════════════
if not exist "logs"          mkdir logs
if not exist "data\chromadb"  mkdir data\chromadb
if not exist "data\logs"     mkdir data\logs

:: ════════════════════════════════════
:: Step 3.5: 清理残留进程（防止端口占用）
:: ════════════════════════════════════
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8005 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8006 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: ════════════════════════════════════
:: Step 4: 启动独立的 GUI 窗口（核心魔法！）
:: ════════════════════════════════════
::  ① 用 pythonw.exe（无控制台版）启动 Tkinter
::  ② 用 start "" 把 GUI 进程彻底分离，bat 不等待
::  ③ bat 立即 exit，黑框消失，GUI 独立存活

:: 安全提取目录（使用字符串操作避免 PowerShell 兼容性问题）
set "PYTHON_DIR=%PYTHON_EXE%"
set "PYTHON_DIR=%PYTHON_DIR:~0,-10%"
set "PYTHONW_EXE=%PYTHON_DIR%pythonw.exe"

:: 检查 pythonw 是否存在，不存在则回退 python.exe
if not exist "%PYTHONW_EXE%" (
    echo   [WARN] 未找到 pythonw.exe，将使用 python.exe（可能附带终端窗口）
    set "PYTHONW_EXE=%PYTHON_EXE%"
)

echo.
echo   ┌────────────────────────────────────┐
echo   │  正在启动 PlotPilot（墨枢）...      │
echo   └────────────────────────────────────┘
echo.

:: ★ 核心魔法：start "" 分离进程 ★
:: 第一个 "" 是 start 的窗口标题（必须留空！否则路径会被误解析为标题）
:: start 之后 bat 立即 exit，不再等待 GUI 关闭
start "" "%PYTHONW_EXE%" -u scripts\install\hub.py %MODE% 2>logs\hub_error.log

:: bat 在这里就结束了，用户只会看到独立的 Tkinter 窗口
exit /b 0

@echo off
title FastAPI Backend Service (Port 8008)
cd /d "%~dp0backend"

set PY_EXE=python
if exist "D:\miniconda\envs\excel_report_env\python.exe" (
    set PY_EXE=D:\miniconda\envs\excel_report_env\python.exe
) else if exist "%CONDA_PREFIX%\python.exe" (
    set PY_EXE=%CONDA_PREFIX%\python.exe
)

echo =======================================================
echo [INFO] 正在启动 FastAPI 后端服务 (端口 8008)...
echo [INFO] 使用 Python: %PY_EXE%
echo =======================================================
%PY_EXE% -m uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 后端服务异常退出，请检查端口或运行环境。
)
pause

@echo off
title 启动高校发展检验报告系统
echo =======================================================
echo 正在一键启动前后端服务...
echo =======================================================

start "FastAPI Backend (Port 8000)" cmd /k "cd /d "%~dp0backend" && D:\miniconda\envs\excel_report_env\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 /nobreak >nul

start "Vue 3 Frontend (Port 5173)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo 前后端服务已在独立窗口中启动！
echo 请在浏览器中打开访问: http://localhost:5173
echo =======================================================
pause

@echo off
title 高校发展检验报告系统一键启动
cd /d "%~dp0"

echo =======================================================
echo   高校发展检验报告系统 (前后端联调启动)
echo =======================================================
echo.
echo [1/2] 正在启动后端服务 (端口 8008)...
start "FastAPI Backend (Port 8008)" "%~dp0run_backend.bat"

timeout /t 2 /nobreak >nul

echo [2/2] 正在启动前端服务 (端口 5173)...
start "Vue 3 Frontend (Port 5173)" "%~dp0run_frontend.bat"

echo.
echo =======================================================
echo [OK] 服务已启动，请在浏览器访问: http://localhost:5173
echo =======================================================
echo.
pause

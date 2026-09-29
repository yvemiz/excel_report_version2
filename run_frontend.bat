@echo off
title Vue 3 Frontend Service (Port 5173)
cd /d "%~dp0frontend"

echo =======================================================
echo [INFO] 正在启动 Vue 3 前端开发服务 (端口 5173)...
echo =======================================================
call npm run dev
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 前端服务启动失败，请检查 Node.js/npm 环境。
)
pause

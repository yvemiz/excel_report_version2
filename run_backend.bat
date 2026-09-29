@echo off
title FastAPI Backend Service (Port 8000)
cd /d "%~dp0backend"
D:\miniconda\envs\excel_report_env\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause

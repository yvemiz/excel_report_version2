[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "正在一键启动高校发展检验报告系统 (前后端联调)..." -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Cyan

$backendPath = Join-Path $PSScriptRoot "backend"
$frontendPath = Join-Path $PSScriptRoot "frontend"
$runBackendBat = Join-Path $PSScriptRoot "run_backend.bat"

Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "call `"$runBackendBat`""
Start-Sleep -Seconds 2
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$frontendPath`" && npm run dev"

Write-Host ""
Write-Host "前后端服务已在独立窗口中启动！" -ForegroundColor Green
Write-Host "请在浏览器访问: http://localhost:5173" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Cyan

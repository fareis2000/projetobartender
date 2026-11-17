@echo off
chcp 65001 >nul
title Encerrar Servidor Bartender
echo Encerrando servidores Bartender (portas 8000 e 8010)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,8010 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host ('Processo encerrado (PID ' + $_ + ')') }"
echo.
echo Servidor encerrado com sucesso!
timeout /t 3

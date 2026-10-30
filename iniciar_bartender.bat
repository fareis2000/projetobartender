@echo off
chcp 65001 >nul
title Bartender Automatico v2.0 - Servidor
cd /d "%~dp0"

:: 1. Verifica ou cria o ambiente virtual Python (.venv)
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Criando ambiente virtual Python (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Python nao encontrado no PATH. Instale o Python 3.10+.
        pause
        exit /b 1
    )
    echo [1/2] Instalando dependencias do backend...
    .venv\Scripts\pip install -r backend\requirements.txt
)

:: 2. Verifica se o build do frontend (frontend/dist) existe
if not exist "frontend\dist\index.html" (
    echo [2/2] Compilando interface web React pela primeira vez...
    pushd frontend
    call npm install
    call npm run build
    popd
)

:: 3. Abre o navegador automaticamente e inicia o servidor
start "" "http://localhost:8000"
.venv\Scripts\python.exe server.py

echo.
echo Servidor encerrado.
pause

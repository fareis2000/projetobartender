@echo off
chcp 65001 >nul
title Bartender.OS v3.0 Comercial - Multi-Bares e Pix (Porta 8010)
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
    echo [1/2] Instalando dependencias do backend v3...
    .venv\Scripts\pip install -r backend\requirements.txt
)

:: 2. Verifica se o build do frontend (frontend/dist) existe
if not exist "frontend\dist\index.html" (
    echo [2/2] Compilando interface web React v3 pela primeira vez...
    pushd frontend
    call npm install
    call npm run build
    popd
)

:: 3. Abre a visao da Maquina #01 automaticamente e inicia na porta 8010 (sem conflitar com a v2 na 8000)
start "" "http://localhost:8010/m/maq-01"
.venv\Scripts\python.exe server.py

echo.
echo Servidor encerrado.
pause

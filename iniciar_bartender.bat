@echo off
chcp 65001 >nul
title Bartender.OS v3.0 Comercial - Multi-Bares e Pix (Porta 8010)
cd /d "%~dp0"

:: ============================================================================
:: SCRIPT DE INICIALIZACAO AUTOMATICA ONE-CLICK — BARTENDER.OS v3.0 (SAAS)
:: ============================================================================
:: Funcao Arquitetural e Comercial:
:: Permite que apresentacoes comerciais B2B, testes de bancada ou homologacoes
:: de campo subam toda a pilha (Python .venv + Build React SPA + API FastAPI
:: + Banco SQLite Multi-Tenant) com apenas um duplo clique no Windows.
:: Opera isolado na porta 8010 para coexistir sem conflito com a versao v2.
:: ============================================================================

:: 1. Verifica ou cria o ambiente virtual Python (.venv)
:: Se for a primeira execucao na maquina, provisiona o ambiente isolado e instala o requirements.txt
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
:: Caso o bundle de producao ainda nao tenha sido gerado pelo Vite, instala os pacotes Node e compila a SPA
if not exist "frontend\dist\index.html" (
    echo [2/2] Compilando interface web React v3 pela primeira vez...
    pushd frontend
    call npm install
    call npm run build
    popd
)

:: 3. Abre a visao da Maquina #01 automaticamente assim que a porta 8010 responder
echo [3/3] Iniciando servidor na porta 8010 e abrindo o navegador...
start /b cmd /c "powershell -NoProfile -WindowStyle Hidden -Command ""for ($i=0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 500; if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 8010 -WarningAction SilentlyContinue).TcpTestSucceeded) { Start-Process 'http://localhost:8010/m/maq-01'; break } }"""
.venv\Scripts\python.exe server.py

echo.
echo Servidor encerrado.
pause

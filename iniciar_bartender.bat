@echo off
REM ============================================================================
REM BARTENDER AUTOMATICO v2.0 - SCRIPT DE INICIALIZACAO ONE-CLICK (WINDOWS)
REM ============================================================================
REM Papel na Arquitetura:
REM   Automatiza todo o ciclo de provisionamento e execucao local para operadores
REM   de eventos, totens touch e demonstracoes comerciais, sem exigir comandos
REM   manuais no terminal.
REM
REM Fluxo de Execucao:
REM   1. Ajusta codificacao do console para UTF-8 (chcp 65001) e posiciona na raiz.
REM   2. Provisiona automaticamente o ambiente virtual Python (.venv) e instala os
REM      pacotes de backend\requirements.txt no primeiro uso.
REM   3. Compila automaticamente o frontend React/Vite (frontend\dist) caso o build
REM      de producao ainda nao exista no disco.
REM   4. Abre o navegador padrao em http://localhost:8000 e inicia o server.py.
REM ============================================================================

REM Define pagina de codigo UTF-8 silenciosamente para evitar caracteres quebrados
chcp 65001 >nul
title Bartender Automatico v2.0 - Servidor

REM Garante que o diretorio de trabalho seja sempre a pasta onde este .bat reside
cd /d "%~dp0"

REM 1. Verifica ou cria o ambiente virtual Python (.venv)
REM Se o executavel do Python isolado nao existir, cria a venv e instala o FastAPI/dependencias
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Criando ambiente virtual Python ^(.venv^)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Python nao encontrado no PATH. Instale o Python 3.10+.
        pause
        exit /b 1
    )
    echo [1/2] Instalando dependencias do backend...
    ".venv\Scripts\pip.exe" install -r backend\requirements.txt
)

REM 2. Verifica se o build do frontend (frontend/dist) existe
REM Compila os estaticos otimizados do React apenas se o index.html de producao nao existir
if not exist "frontend\dist\index.html" (
    echo [2/2] Compilando interface web React pela primeira vez...
    pushd frontend
    call npm install
    call npm run build
    popd
)

REM 3. Aguarda o servidor subir na porta 8000 em background e abre o navegador automaticamente
REM Dispara a aba do painel web assim que o Uvicorn estiver escutando conexoes
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for ($i=0; $i -lt 40; $i++) { try { $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 8000); $c.Close(); break } catch { Start-Sleep -Milliseconds 300 } }; Start-Process 'http://localhost:8000'"
".venv\Scripts\python.exe" server.py

echo.
echo Servidor encerrado.
pause

"""Configurações globais, diretórios base e carregamento de variáveis de ambiente.

Papel na Arquitetura:
---------------------
Centraliza todos os caminhos absolutos do projeto (`BASE_DIR`, `PROJECT_ROOT`, `DATA_DIR`,
`FRONTEND_DIST_DIR`) usando `pathlib.Path` (compatível com Windows, Linux e macOS) e expõe
a instância `settings` com os parâmetros operacionais lidos de arquivos `.env`.

Valor Comercial / Segurança:
----------------------------
Separa completamente o código-fonte das credenciais de instalação (`ESP32_API_TOKEN`) e dos
endereços locais de hardware, permitindo implantar o mesmo pacote de software em múltiplos
quiosques/eventos mudando apenas o arquivo `.env` local.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Diretório `projetobartender/backend`
BASE_DIR = Path(__file__).resolve().parent.parent

# Diretório raiz `projetobartender/`
PROJECT_ROOT = BASE_DIR.parent

# Pasta onde ficam salvos os JSONs leves de estado (`pumps.json` e `connection.json`)
DATA_DIR = BASE_DIR / "data"

# Pasta gerada pelo `npm run build` com os arquivos estáticos de produção do React
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# Carrega .env se existir em backend/.env ou na raiz
# Observação: `load_dotenv` por padrão não sobrescreve variáveis já definidas no sistema operacional,
# permitindo tanto configuração por arquivo local quanto injeção via ambiente de execução.
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """Contêiner de configurações iniciais carregadas das variáveis de ambiente.

    Atributos:
        esp32_mode (str): Modo inicial de transporte (`'auto'`, `'wifi'`, `'serial'` ou `'simulator'`).
        esp32_host (str): Hostname mDNS (`'bartender.local'`) ou IP fixo do ESP32 na rede Wi-Fi.
        esp32_port (int): Porta HTTP do servidor embarcado no ESP32 (padrão `80`).
        esp32_api_token (str): Token compartilhado opcional enviado no header `X-Bartender-Token`.
        serial_port (str): Porta serial padrão para comunicação via cabo USB (ex.: `'COM3'`).
        serial_baud (int): Taxa de transmissão serial em bps (padrão `115200` no ESP32/ESP8266).
        max_cup_ml (int): Limite volumétrico de segurança do copo em mililitros (padrão `450`).
    """

    esp32_mode: str = os.getenv("ESP32_MODE", "auto").lower()
    esp32_host: str = os.getenv("ESP32_HOST", "bartender.local")
    esp32_port: int = int(os.getenv("ESP32_PORT", "80"))
    esp32_api_token: str = os.getenv("ESP32_API_TOKEN", "").strip()
    serial_port: str = os.getenv("SERIAL_PORT", "COM3")
    serial_baud: int = int(os.getenv("SERIAL_BAUD", "115200"))
    max_cup_ml: int = int(os.getenv("MAX_CUP_ML", "450"))


# Singleton global de configuração importado pelos demais módulos do backend
settings = Settings()

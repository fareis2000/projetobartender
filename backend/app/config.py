"""Configurações centralizadas e gerenciamento de segredos do Bartender.OS v3.0.

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Centraliza a resolução de caminhos de diretórios (`data/`, `frontend/dist/`), leitura de
variáveis de ambiente (`.env`) e provisionamento automático de chave criptográfica JWT.

Em implantações comerciais B2B ou on-premise enxutas, o sistema é **Zero-Config**: se o
administrador não definir um `JWT_SECRET` manual, o módulo gera automaticamente um token
criptograficamente seguro de 384 bits (`token_urlsafe(48)`) e o persiste em disco
(`backend/data/.jwt_secret`), mantendo todas as sessões de donos de bares válidas mesmo
após reinicializações do servidor.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Resolução absoluta de diretórios independente do diretório de trabalho (CWD) do processo
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# Carrega .env se existir em backend/.env ou na raiz
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


def _load_or_create_jwt_secret() -> str:
    """Obtém a chave secreta de assinatura JWT do ambiente ou de arquivo persistente local.

    Ordem de precedência:
    1. Variável de ambiente `JWT_SECRET` (ideal para containers em nuvem stateless).
    2. Arquivo local `backend/data/.jwt_secret` já existente.
    3. Geração automática via `secrets.token_urlsafe(48)` salva em `backend/data/.jwt_secret`.
    """
    env_val = os.getenv("JWT_SECRET", "").strip()
    if env_val:
        return env_val
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = DATA_DIR / ".jwt_secret"
    if secret_file.exists():
        stored = secret_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    # Gera segredo aleatório de alta entropia no primeiro boot da instalação
    generated = secrets.token_urlsafe(48)
    secret_file.write_text(generated, encoding="utf-8")
    return generated


class Settings:
    """Contêiner tipado das configurações globais de execução da plataforma SaaS.

    Reúne parâmetros de rede, caminho do banco SQLite Multi-Tenant, credenciais de seed
    para o Super-Admin e o Bar Demo inicial, parâmetros padrão de conectividade IoT e
    janelas temporais críticas de negócio (expiração de Pix e janela de confirmação de copo).
    """

    # Porta HTTP/WS padrão 8010 (isolada da porta 8000 utilizada pela versão v2)
    server_port: int = int(os.getenv("PORT", "8010"))

    # Caminho do banco SQLite transacional (permite sobrescrita em testes automatizados via env)
    db_path: Path = Path(os.getenv("BARTENDER_DB_PATH", str(DATA_DIR / "bartender_v3.db")))

    # Segredo HMAC-SHA256 e validade padrão da sessão autenticada (7 dias = 604.800s)
    jwt_secret: str = _load_or_create_jwt_secret()
    jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", str(60 * 60 * 24 * 7)))

    # Credenciais de bootstrap do Super-Admin dono da plataforma SaaS
    superadmin_email: str = os.getenv("SUPERADMIN_EMAIL", "superadmin@bartender.os").strip().lower()
    superadmin_password: str = os.getenv("SUPERADMIN_PASSWORD", "admin123")

    # Credenciais de bootstrap do estabelecimento demonstrativo criado no primeiro boot
    default_bar_email: str = os.getenv("DEFAULT_BAR_EMAIL", "dono@bartropical.com").strip().lower()
    default_bar_password: str = os.getenv("DEFAULT_BAR_PASSWORD", "bar123")

    # Domínio público HTTPS da plataforma (usado na geração de QR Codes SVG e Webhooks Pix)
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

    # Defaults p/ primeira máquina criada
    esp32_mode: str = os.getenv("ESP32_MODE", "auto").lower()
    esp32_host: str = os.getenv("ESP32_HOST", "bartender.local")
    esp32_port: int = int(os.getenv("ESP32_PORT", "80"))
    esp32_api_token: str = os.getenv("ESP32_API_TOKEN", "").strip()
    serial_port: str = os.getenv("SERIAL_PORT", "COM3")
    serial_baud: int = int(os.getenv("SERIAL_BAUD", "115200"))
    # Limite físico anti-transbordo padrão por copo em mililitros
    max_cup_ml: int = int(os.getenv("MAX_CUP_ML", "450"))

    # Janelas de tempo de pagamento e fila
    # Tempo máximo visual no celular para o cliente pagar o Pix (600s = 10 min)
    pix_expiration_seconds: int = int(os.getenv("PIX_EXPIRATION_SECONDS", "600"))
    # Tempo máximo para o cliente da vez confirmar o copo na plataforma antes de pausar seu turno (75s)
    turn_window_seconds: int = int(os.getenv("TURN_WINDOW_SECONDS", "75"))


# Instância singleton importada por todos os módulos do backend
settings = Settings()

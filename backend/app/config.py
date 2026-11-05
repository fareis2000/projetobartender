from __future__ import annotations

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# Carrega .env se existir em backend/.env ou na raiz
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


def _load_or_create_jwt_secret() -> str:
    env_val = os.getenv("JWT_SECRET", "").strip()
    if env_val:
        return env_val
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = DATA_DIR / ".jwt_secret"
    if secret_file.exists():
        stored = secret_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    generated = secrets.token_urlsafe(48)
    secret_file.write_text(generated, encoding="utf-8")
    return generated


class Settings:
    server_port: int = int(os.getenv("PORT", "8010"))
    db_path: Path = Path(os.getenv("BARTENDER_DB_PATH", str(DATA_DIR / "bartender_v3.db")))
    jwt_secret: str = _load_or_create_jwt_secret()
    jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", str(60 * 60 * 24 * 7)))

    superadmin_email: str = os.getenv("SUPERADMIN_EMAIL", "superadmin@bartender.os").strip().lower()
    superadmin_password: str = os.getenv("SUPERADMIN_PASSWORD", "admin123")

    default_bar_email: str = os.getenv("DEFAULT_BAR_EMAIL", "dono@bartropical.com").strip().lower()
    default_bar_password: str = os.getenv("DEFAULT_BAR_PASSWORD", "bar123")

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

    # Defaults p/ primeira máquina criada
    esp32_mode: str = os.getenv("ESP32_MODE", "auto").lower()
    esp32_host: str = os.getenv("ESP32_HOST", "bartender.local")
    esp32_port: int = int(os.getenv("ESP32_PORT", "80"))
    esp32_api_token: str = os.getenv("ESP32_API_TOKEN", "").strip()
    serial_port: str = os.getenv("SERIAL_PORT", "COM3")
    serial_baud: int = int(os.getenv("SERIAL_BAUD", "115200"))
    max_cup_ml: int = int(os.getenv("MAX_CUP_ML", "450"))

    # Janelas de tempo de pagamento e fila
    pix_expiration_seconds: int = int(os.getenv("PIX_EXPIRATION_SECONDS", "300"))
    turn_window_seconds: int = int(os.getenv("TURN_WINDOW_SECONDS", "75"))


settings = Settings()

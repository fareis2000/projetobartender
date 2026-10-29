from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# Carrega .env se existir em backend/.env ou na raiz
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    esp32_mode: str = os.getenv("ESP32_MODE", "auto").lower()
    esp32_host: str = os.getenv("ESP32_HOST", "bartender.local")
    esp32_port: int = int(os.getenv("ESP32_PORT", "80"))
    esp32_api_token: str = os.getenv("ESP32_API_TOKEN", "").strip()
    serial_port: str = os.getenv("SERIAL_PORT", "COM3")
    serial_baud: int = int(os.getenv("SERIAL_BAUD", "115200"))
    max_cup_ml: int = int(os.getenv("MAX_CUP_ML", "450"))


settings = Settings()


"""Ponto de entrada unificado para iniciar o servidor FastAPI (Bartender Automático)."""
import socket
import sys
import uvicorn


def _get_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lan_ip = _get_lan_ip()
    print("=" * 60)
    print("[Bartender v2.0] Servidor FastAPI + ESP8266 / ESP32")
    print("[Acesso neste PC]   http://localhost:8000")
    if lan_ip:
        print(f"[Acesso no Celular] http://{lan_ip}:8000  (mesmo Wi-Fi)")
    print("[Documentacao API]  http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)

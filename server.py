"""Ponto de entrada unificado do Bartender.OS v3.0 (SaaS Multi-Bares + Pix + CRUD)."""
import socket
import sys
import uvicorn

from backend.app.config import settings


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
    port = settings.server_port
    lan_ip = _get_lan_ip()
    print("=" * 68)
    print(f"[Bartender.OS v3.0] Plataforma Comercial Multi-Bares + Pix (Porta {port})")
    print(f"[QR Code Máquina #01] http://localhost:{port}/m/maq-01")
    print(f"[Painel Dono do Bar]  http://localhost:{port}/painel  (dono@bartropical.com / bar123)")
    print(f"[Painel Super-Admin]  http://localhost:{port}/superadmin  (superadmin@bartender.os / admin123)")
    if lan_ip:
        print(f"[Teste no Celular]    http://{lan_ip}:{port}/m/maq-01")
    print(f"[Documentacao API]    http://localhost:{port}/docs")
    print("=" * 68)
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=True)

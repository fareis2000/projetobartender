"""Ponto de entrada unificado do Bartender.OS v3.0 (SaaS Multi-Bares + Pix + CRUD).

Função Arquitetural:
--------------------
Este script inicializa o servidor HTTP/WebSocket ASGI (`Uvicorn`) que hospeda de forma
unificada:
1. A API REST Multi-Tenant (`/api/auth`, `/api/public`, `/api/bar`, `/api/superadmin`).
2. O endpoint de Sincronização Cloud IoT (`/api/iot/{machine_slug}/sync`) para placas
   ESP8266/ESP32 conectadas diretamente no Wi-Fi 2.4 GHz de cada bar.
3. Os Webhooks de confirmação instantânea Pix do Mercado Pago (`/api/webhooks/...`).
4. O canal WebSocket de telemetria em tempo real por máquina (`/api/ws/machines/...`).
5. Os arquivos estáticos pré-compilados da SPA React (`frontend/dist`), eliminando a
   necessidade de servidor web secundário em deploys enxutos ou demonstrações locais.

Diferenciais Comerciais e Operacionais:
---------------------------------------
- Opera por padrão na porta `8010`, garantindo isolamento total em relação à versão
  legada de eventos (`v2`, porta `8000`).
- Detecta automaticamente o IP da interface de rede local (LAN) via socket UDP sem
  enviar tráfego real, exibindo no console o link pronto para teste imediato pelo
  celular (4G/Wi-Fi) simulando a leitura física do QR Code da máquina.
"""
from pathlib import Path
import sys
import uvicorn

from backend.app.config import settings
from backend.app.network_discovery import (
    get_current_network_info,
    sync_secrets_h_with_current_network,
)


if __name__ == "__main__":
    # Garante saída UTF-8 limpa no terminal do Windows (PowerShell / CMD) para acentos e símbolos
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Carrega a porta configurada via variável de ambiente PORT (padrão 8010)
    port = settings.server_port
    net_info = get_current_network_info(force_refresh=True)
    connected_ssid = net_info.get("connected_ssid")
    target_ssid = net_info.get("esp_target_ssid")
    lan_ips = net_info.get("lan_ips") or []
    primary_ip = net_info.get("primary_ip") or "127.0.0.1"

    secrets_path = Path(__file__).resolve().parent / "bombas" / "secrets.h"
    sync_res = sync_secrets_h_with_current_network(
        secrets_path,
        cloud_sync_url=f"http://{primary_ip}:{port}/api/iot/maq-01/sync",
    )

    # Banner de inicialização com URLs diretas das 3 jornadas da plataforma SaaS + Swagger
    print("=" * 72)
    print(f"[Bartender.OS v3.0] Plataforma Comercial Multi-Bares + Pix (Porta {port})")
    if connected_ssid:
        print(f"[Rede Wi-Fi Atual]    {connected_ssid}  -->  Alvo 2.4GHz ESP: {target_ssid}")
        print(f"[Firmware Sync]       bombas/secrets.h sincronizado ({sync_res.get('known_networks_count', 0)} redes salvas)")
    print(f"[QR Code Máquina #01] http://localhost:{port}/m/maq-01")
    print(f"[Painel Dono do Bar]  http://localhost:{port}/painel  (dono@bartropical.com / bar123)")
    print(f"[Painel Super-Admin]  http://localhost:{port}/superadmin  (superadmin@bartender.os / admin123)")
    for ip in (lan_ips or [primary_ip]):
        if ip and not ip.startswith("127."):
            print(f"[Acesso na Rede LAN]  http://{ip}:{port}/m/maq-01  (QR Code / Celular / Tablet)")
    print(f"[Documentacao API]    http://localhost:{port}/docs")
    print("=" * 72)

    # Inicia o servidor ASGI escutando em todas as interfaces (0.0.0.0)
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        timeout_graceful_shutdown=2,
    )

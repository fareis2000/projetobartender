"""Ponto de entrada unificado para iniciar o servidor FastAPI (Bartender Automático).

Papel na Arquitetura:
---------------------
Este script atua como o bootstrapper (inicializador único) da plataforma Bartender.OS v2.0
em modo de operação local, totem interativo ou servidor de eventos (LAN). Ele:
  1. Configura a saída padrão (stdout) em UTF-8 para evitar falhas de codificação em terminais
     Windows (PowerShell / CMD) ao imprimir emojis ou caracteres acentuados.
  2. Descobre automaticamente o endereço IPv4 da máquina na rede Wi-Fi/LAN local para exibi-lo
     no console, facilitando o acesso imediato por tablets, totens e smartphones de convidados.
  3. Inicia o servidor ASGI Uvicorn escutando em `0.0.0.0:8000`, servindo simultaneamente:
     - A API REST (`/api/*`) e a documentação interativa Swagger (`/docs`);
     - O canal de telemetria em tempo real via WebSocket (`/api/ws`);
     - O bundle estático de produção do frontend React (`frontend/dist`), eliminando a
       necessidade de servidores web externos (Nginx/Apache) em eventos.

Valor Comercial / Operacional:
------------------------------
Permite colocar o bar automatizado em operação com um único comando (`python server.py` ou
duplo-clique em `iniciar_bartender.bat`), reduzindo o tempo de setup técnico em feiras,
casamentos e ativações de marca para menos de 1 minuto.
"""
from pathlib import Path
import sys
import uvicorn

from backend.app.network_discovery import (
    get_current_network_info,
    sync_secrets_h_with_current_network,
)


if __name__ == "__main__":
    # Garante saída UTF-8 segura em terminais Windows (evita UnicodeEncodeError no console)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Puxa automaticamente a rede Wi-Fi conectada e sincroniza bombas/secrets.h
    net_info = get_current_network_info(force_refresh=True)
    secrets_path = Path(__file__).resolve().parent / "bombas" / "secrets.h"
    sync_res = sync_secrets_h_with_current_network(secrets_path)

    connected_ssid = net_info.get("connected_ssid")
    target_ssid = net_info.get("esp_target_ssid")
    lan_ips = net_info.get("lan_ips") or []
    primary_ip = net_info.get("primary_ip") or "127.0.0.1"

    print("=" * 68)
    print("[Bartender v2.0] Servidor FastAPI + Auto-Descoberta ESP8266 / ESP32")
    if connected_ssid:
        print(f"[Rede Wi-Fi Atual]  {connected_ssid}  -->  Alvo 2.4GHz ESP: {target_ssid}")
        print(f"[Firmware Sync]     bombas/secrets.h atualizado ({sync_res.get('known_networks_count', 0)} redes salvas)")
    print("[Acesso neste PC]   http://localhost:8000")
    for ip in (lan_ips or [primary_ip]):
        if ip and not ip.startswith("127."):
            print(f"[Acesso na Rede]    http://{ip}:8000  (Celular / Tablet / Totem)")
    print("[Documentacao API]  http://localhost:8000/docs")
    print("=" * 68)

    # Inicia o Uvicorn em 0.0.0.0 para aceitar conexões tanto locais (totem) quanto da LAN (convidados)
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        timeout_graceful_shutdown=2,
    )

"""Orquestrador assíncrono de hardware ESP32/ESP8266 com fallback triplo e telemetria Pub/Sub.

Papel na Arquitetura:
---------------------
Este módulo é o coração operacional do backend (`ESP32Controller`). Ele abstrai completamente
a camada física de comunicação com a placa controladora das bombas, expondo uma interface
assíncrona unificada para o FastAPI e transmitindo atualizações em tempo real (`SystemSnapshot`)
para todos os clientes WebSocket inscritos.

Diferenciais Técnicos e Comerciais (Alta Disponibilidade em Eventos):
---------------------------------------------------------------------
  1. Fallback Triplo Inteligente (`mode="auto"`):
     - Prioridade 1 — **Wi-Fi HTTP JSON (`bartender.local` / IP fixo):** Ideal para bancadas limpas
       onde o totem/notebook fica afastado da estrutura hidráulica.
     - Prioridade 2 — **Cabo USB Serial (`115200 baud`):** Se o Wi-Fi do evento sofrer interferência
       intensa de RF (centenas de celulares próximos), basta plugar um cabo USB que o sistema
       assume automaticamente sem alterar código.
     - Prioridade 3 — **Simulador Volumétrico Fiel:** Se nenhum hardware estiver conectado, simula
       o tempo exato de cada bomba e pausa usando as vazões reais calibradas, viabilizando
       demonstrações comerciais de pré-venda em qualquer reunião ou tablet sem levar a máquina física.
  2. Exclusão Mútua Estrita (`asyncio.Lock`):
     - Impede condições de corrida caso dois convidados cliquem em "Preparar" no mesmo milissegundo
       em celulares diferentes na mesma rede LAN.
  3. Parada de Emergência Prioritária (`emergency_stop`):
     - Corta imediatamente os relés no hardware (via `POST /stop` ou comando serial `STOP\\n`) e
       cancela a task assíncrona em andamento em fração de segundo.
"""
from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path
from typing import Callable, Awaitable

import httpx
import serial
import serial.tools.list_ports
from serial.serialutil import SerialException

from .catalog import load_pumps
from .config import DATA_DIR, PROJECT_ROOT, settings
from .models import (
    ConnectionConfig,
    DoseStep,
    HardwareHealth,
    NetworkSyncResult,
    PreparationStatus,
    PumpConfig,
    PumpId,
    SystemSnapshot,
)
from .network_discovery import (
    auto_provision_esp_via_softap_bridge,
    discover_esp_on_network,
    find_best_serial_port,
    get_current_network_info,
    list_all_serial_ports,
    provision_esp_via_serial_sync,
    push_wifi_config_to_esp_http,
    sync_secrets_h_with_current_network,
)

# Arquivo JSON local onde a preferência de conexão escolhida no painel ⚙️ é persistida
CONNECTION_FILE: Path = DATA_DIR / "connection.json"
BOMBAS_SECRETS_FILE: Path = PROJECT_ROOT / "bombas" / "secrets.h"


class ESP32Controller:
    """Gerencia comunicação assíncrona com o ESP32 via Wi-Fi (HTTP), USB Serial ou Simulador.

    Implementa o padrão Singleton (`esp32_controller`) compartilhado por todas as rotas HTTP e
    conexões WebSocket do processo FastAPI, mantendo estado único de preparo, lock de concorrência
    e lista de assinantes (`_subscribers`) para broadcast reativo.
    """

    def __init__(self) -> None:
        """Inicializa estado interno, lock de exclusão mútua e carrega `connection.json`."""
        self._config = self._load_config()
        self._status = PreparationStatus()
        # Lock assíncrono que garante no máximo 1 bebida sendo preparada fisicamente por vez
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None
        self._cancel_requested = False
        self._serial: serial.Serial | None = None
        # Conjunto de callbacks assíncronos registrados pelas conexões WebSocket ativas
        self._subscribers: set[Callable[[SystemSnapshot], Awaitable[None]]] = set()
        self._last_synced_ssid: str | None = None
        self._last_subnet_scan_ts: float = 0.0
        self._last_softap_bridge_ts: float = 0.0
        self._last_health = HardwareHealth(
            mode=self._config.mode,
            active_transport="disconnected",
            esp32_host=self._config.esp32_host,
            esp32_port=self._config.esp32_port,
            serial_port=self._config.serial_port,
            serial_baud=self._config.serial_baud,
        )

    def _load_config(self) -> ConnectionConfig:
        """Carrega os parâmetros de conexão de `backend/data/connection.json` com fallback para `.env`.

        Returns:
            ConnectionConfig: Configuração validada pronta para uso.
        """
        default = ConnectionConfig(
            mode=settings.esp32_mode if settings.esp32_mode in ("auto", "wifi", "serial", "simulator") else "auto",
            esp32_host=settings.esp32_host,
            esp32_port=settings.esp32_port,
            serial_port=settings.serial_port,
            serial_baud=settings.serial_baud,
        )
        if CONNECTION_FILE.exists():
            try:
                raw = json.loads(CONNECTION_FILE.read_text(encoding="utf-8"))
                return ConnectionConfig(**raw)
            except Exception:
                # Se o JSON estiver inválido, restaura silenciosamente o padrão seguro do .env
                pass
        return default

    def save_config(self, cfg: ConnectionConfig) -> ConnectionConfig:
        """Atualiza a configuração de transporte em memória e persiste em `connection.json`.

        Args:
            cfg (ConnectionConfig): Nova configuração enviada pelo painel administrativo.

        Returns:
            ConnectionConfig: A própria configuração persistida.
        """
        self._config = cfg
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONNECTION_FILE.write_text(
            json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self._config

    @property
    def config(self) -> ConnectionConfig:
        """Retorna a configuração de conexão atualmente ativa."""
        return self._config

    @property
    def status(self) -> PreparationStatus:
        """Retorna o status instantâneo do preparo atual."""
        return self._status

    def subscribe(self, callback: Callable[[SystemSnapshot], Awaitable[None]]) -> None:
        """Registra um listener assíncrono (ex.: cliente WebSocket) para receber snapshots ao vivo."""
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[SystemSnapshot], Awaitable[None]]) -> None:
        """Remove um listener assíncrono previamente registrado quando o WebSocket desconecta."""
        self._subscribers.discard(callback)

    async def _broadcast(self) -> None:
        """Envia o snapshot atual (`status` + `hardware`) para todos os clientes WebSocket ativos.

        Callbacks que lançarem exceção (conexões órfãs) são coletados e removidos automaticamente
        para evitar vazamento de memória durante eventos de longa duração (8h+ de operação contínua).
        """
        snapshot = SystemSnapshot(status=self._status, hardware=self._last_health)
        stale: list[Callable[[SystemSnapshot], Awaitable[None]]] = []
        for cb in list(self._subscribers):
            try:
                await cb(snapshot)
            except Exception:
                stale.append(cb)
        for cb in stale:
            self._subscribers.discard(cb)

    def _wifi_base_url(self, use_cached_ip: bool = False) -> str:
        """Constrói a URL base HTTP do ESP32 priorizando o IP já resolvido quando solicitado.

        Usar `use_cached_ip=True` durante o polling de preparo e na parada de emergência evita
        repetir resoluções mDNS (`bartender.local`) no Windows, que podem adicionar ~300-1000ms
        de latência por requisição.
        """
        host = (
            self._last_health.wifi_ip
            if (use_cached_ip and self._last_health.wifi_ip)
            else self._config.esp32_host
        )
        return f"http://{host}:{self._config.esp32_port}"

    async def _resolve_wifi_host(self) -> str:
        """Resolve hostnames mDNS (`.local`) em thread separada para não bloquear o event loop."""
        host = self._config.esp32_host.strip()
        if host.lower().endswith(".local"):
            try:
                return await asyncio.to_thread(socket.gethostbyname, host)
            except OSError:
                pass
        return host

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        """Monta o cabeçalho de autenticação opcional `X-Bartender-Token` se definido no `.env`."""
        if settings.esp32_api_token:
            return {"X-Bartender-Token": settings.esp32_api_token}
        return {}

    @staticmethod
    def list_serial_ports() -> list[str]:
        """Enumera todas as portas seriais (`COM*` / `/dev/tty*`) visíveis no sistema operacional."""
        return list_all_serial_ports()

    def _ensure_secrets_synced(self) -> dict[str, object]:
        """Sincroniza automaticamente `bombas/secrets.h` sempre que a rede Wi-Fi do PC mudar."""
        net_info = get_current_network_info()
        target_ssid = net_info.get("esp_target_ssid") or net_info.get("connected_ssid")
        if target_ssid != self._last_synced_ssid or not BOMBAS_SECRETS_FILE.exists():
            sync_secrets_h_with_current_network(
                BOMBAS_SECRETS_FILE,
                api_token=settings.esp32_api_token or "",
            )
            self._last_synced_ssid = str(target_ssid)
        return net_info

    async def probe_hardware(self, force_deep_scan: bool = False) -> HardwareHealth:
        """Executa diagnóstico ativo do hardware e decide o transporte efetivo de operação.

        Fluxo de decisão dinâmico multi-rede:
          1. Detecta automaticamente a rede atual conectada no PC (SSID, equivalente 2.4GHz, IP LAN)
             e sincroniza `bombas/secrets.h`.
          2. Descobre o ESP na rede atual via 4 camadas (Broadcast UDP 4210, Host/IP/mDNS/SoftAP,
             Tabela ARP e Varredura de Sub-rede `/24`), sem depender de IP ou rede fixa.
          3. Detecta automaticamente qualquer porta USB Serial (`COM*`) caso o cabo USB esteja conectado.
          4. Se nenhum hardware físico estiver presente, seleciona `'simulator'` no modo `'auto'`.

        Returns:
            HardwareHealth: Relatório completo de conectividade atualizado em `self._last_health`.
        """
        net_info = await asyncio.to_thread(self._ensure_secrets_synced)
        connected_ssid = net_info.get("connected_ssid")
        esp_target_ssid = net_info.get("esp_target_ssid")
        server_lan_ip = str(net_info.get("primary_ip") or "127.0.0.1")

        ports = self.list_serial_ports()
        best_serial = find_best_serial_port(self._config.serial_port)
        if best_serial and best_serial != self._config.serial_port:
            self._config.serial_port = best_serial

        wifi_ok = False
        wifi_ip: str | None = None
        wifi_rssi: int | None = None
        discovered_via: str | None = None
        serial_ok = False
        detail = ""

        # Etapa 1: Descoberta inteligente Wi-Fi HTTP (executada nos modos 'auto' e 'wifi')
        if self._config.mode in ("auto", "wifi"):
            now_mono = time.monotonic()
            should_deep_scan = (
                force_deep_scan
                or not self._last_health.wifi_reachable
                or (now_mono - self._last_subnet_scan_ts > 15.0)
            )
            if should_deep_scan:
                self._last_subnet_scan_ts = now_mono

            disc = await discover_esp_on_network(
                configured_host=self._config.esp32_host,
                port=self._config.esp32_port,
                cached_ip=self._last_health.wifi_ip,
                api_token=settings.esp32_api_token or "",
                allow_subnet_scan=should_deep_scan,
            )

            if disc and disc.get("ip"):
                wifi_ok = True
                wifi_ip = str(disc["ip"])
                wifi_rssi = disc.get("rssi")
                discovered_via = str(disc.get("discovered_via") or "lan")

        # Etapa 2: Sondagem USB Serial automática (qualquer porta COM conectada ao ESP)
        if self._serial and self._serial.is_open:
            serial_ok = True
        elif best_serial and best_serial in ports:
            serial_ok = True

        # Se o ESP ainda não está na LAN nem no USB, mas está com o AP 'Bartender-ESP32' visível no ar,
        # faz a ponte automática Wi-Fi p/ provisionar o SSID/Senha da rede atual sem precisar de cabo!
        if (
            not wifi_ok
            and not serial_ok
            and self._config.mode in ("auto", "wifi")
            and connected_ssid
            and esp_target_ssid
            and not net_info.get("is_5ghz_only")
            and net_info.get("wifi_password")
            and (force_deep_scan or (time.monotonic() - self._last_softap_bridge_ts > 45.0))
        ):
            self._last_softap_bridge_ts = time.monotonic()
            bridged = await auto_provision_esp_via_softap_bridge(
                current_pc_ssid=str(connected_ssid),
                target_24g_ssid=str(esp_target_ssid),
                target_password=str(net_info.get("wifi_password") or ""),
                esp_port=self._config.esp32_port,
                api_token=settings.esp32_api_token or "",
            )
            if bridged:
                disc = await discover_esp_on_network(
                    configured_host=self._config.esp32_host,
                    port=self._config.esp32_port,
                    cached_ip=self._last_health.wifi_ip,
                    api_token=settings.esp32_api_token or "",
                    allow_subnet_scan=True,
                )
                if disc and disc.get("ip"):
                    wifi_ok = True
                    wifi_ip = str(disc["ip"])
                    wifi_rssi = disc.get("rssi")
                    discovered_via = "softap_bridge"

        # Se o ESP está conectado no USB Serial mas ainda não entrou no Wi-Fi da rede atual,
        # provisiona automaticamente o SSID/Senha da rede atual via USB Serial!
        if (
            serial_ok
            and not wifi_ok
            and self._config.mode in ("auto", "wifi")
            and esp_target_ssid
            and net_info.get("wifi_password")
            and (force_deep_scan or self._last_health.active_transport == "disconnected")
        ):
            prov = await asyncio.to_thread(
                provision_esp_via_serial_sync,
                self._config.serial_port,
                self._config.serial_baud,
                str(esp_target_ssid),
                str(net_info.get("wifi_password") or ""),
            )
            prov_ip = prov.get("ip")
            if prov_ip and prov_ip not in ("0.0.0.0", "192.168.4.1"):
                wifi_ok = True
                wifi_ip = str(prov_ip)
                discovered_via = "serial_provisioned"

        # Etapa 3: Consolidação do transporte ativo e mensagem amigável para o operador
        if self._config.mode == "simulator":
            active = "simulator"
            detail = "Modo Simulador ativo — dosagem em tempo real simulada"
        elif self._config.mode == "wifi":
            if wifi_ok:
                active = "wifi"
                via_lbl = f" [{discovered_via}]" if discovered_via else ""
                detail = f"ESP conectado via Wi-Fi ({wifi_ip}){via_lbl}"
            elif serial_ok:
                # Mesmo se o usuário deixou 'wifi' selecionado, se o cabo USB estiver plugado usamos Serial como salva-vidas!
                active = "serial"
                detail = f"Wi-Fi indisponível — usando cabo USB Serial ({self._config.serial_port}) automaticamente"
            else:
                active = "disconnected"
                net_lbl = f" na rede '{connected_ssid}'" if connected_ssid else ""
                detail = f"ESP não localizado{net_lbl} ({self._config.esp32_host})"
        elif self._config.mode == "serial":
            active = "serial" if serial_ok else ("wifi" if wifi_ok else "disconnected")
            detail = (
                f"Porta USB Serial {self._config.serial_port} pronta"
                if serial_ok
                else (
                    f"USB desconectado — usando Wi-Fi ({wifi_ip})"
                    if wifi_ok
                    else f"Porta {self._config.serial_port} não encontrada"
                )
            )
        else:  # auto
            if wifi_ok:
                active = "wifi"
                detail = f"ESP online na rede atual ({wifi_ip})"
            elif serial_ok:
                active = "serial"
                detail = f"ESP detectado na USB Serial ({self._config.serial_port})"
            else:
                active = "simulator"
                if net_info.get("is_5ghz_only"):
                    detail = (
                        f"Rede '{connected_ssid}' apenas em 5 GHz (Canal {net_info.get('channel')}). "
                        "Mude o Roteador Wi-Fi/Hotspot para 2.4 GHz para o ESP8266 conectar!"
                    )
                else:
                    detail = "ESP não detectado em Wi-Fi/USB — Simulador inteligente pronto"

        self._last_health = HardwareHealth(
            mode=self._config.mode,
            active_transport=active,
            wifi_reachable=wifi_ok,
            wifi_ip=wifi_ip,
            wifi_rssi=wifi_rssi,
            serial_connected=serial_ok,
            available_serial_ports=ports,
            esp32_host=self._config.esp32_host,
            esp32_port=self._config.esp32_port,
            serial_port=self._config.serial_port,
            serial_baud=self._config.serial_baud,
            detail=detail,
            connected_ssid=str(connected_ssid) if connected_ssid else None,
            esp_target_ssid=str(esp_target_ssid) if esp_target_ssid else None,
            server_lan_ip=server_lan_ip,
            discovered_via=discovered_via,
        )
        return self._last_health

    async def sync_and_discover_network(self) -> NetworkSyncResult:
        """Puxa os dados da rede Wi-Fi conectada no PC, atualiza `secrets.h`, provisiona o ESP e localiza seu IP."""
        net_info = await asyncio.to_thread(get_current_network_info, True)
        connected_ssid = net_info.get("connected_ssid")
        esp_target_ssid = net_info.get("esp_target_ssid") or connected_ssid
        wifi_password = net_info.get("wifi_password") or ""
        server_lan_ip = str(net_info.get("primary_ip") or "127.0.0.1")
        lan_ips = list(net_info.get("lan_ips") or [server_lan_ip])

        sync_res = await asyncio.to_thread(
            sync_secrets_h_with_current_network,
            BOMBAS_SECRETS_FILE,
            api_token=settings.esp32_api_token or "",
        )
        secrets_updated = bool(sync_res.get("updated"))

        serial_provisioned = False
        best_serial = find_best_serial_port(self._config.serial_port)
        if best_serial and esp_target_ssid:
            self._config.serial_port = best_serial
            prov = await asyncio.to_thread(
                provision_esp_via_serial_sync,
                best_serial,
                self._config.serial_baud,
                str(esp_target_ssid),
                str(wifi_password),
            )
            if prov.get("ok"):
                serial_provisioned = True
                if prov.get("ip") and prov["ip"] not in ("0.0.0.0", "192.168.4.1"):
                    self._last_health.wifi_ip = str(prov["ip"])

        # Se o PC já estiver conectado diretamente ao SoftAP (192.168.4.x), envia credenciais via HTTP
        if esp_target_ssid and wifi_password and any(ip.startswith("192.168.4.") for ip in lan_ips):
            await push_wifi_config_to_esp_http(
                "192.168.4.1",
                str(esp_target_ssid),
                str(wifi_password),
                port=self._config.esp32_port,
                api_token=settings.esp32_api_token or "",
            )

        health = await self.probe_hardware(force_deep_scan=True)
        # Se não encontrou na rede atual nem no USB, mas o ESP está com o AP 'Bartender-ESP32' aberto,
        # faz a ponte automática via Wi-Fi para enviar a senha da rede nova ao ESP!
        if not health.wifi_reachable and not health.serial_connected and connected_ssid and esp_target_ssid:
            bridged = await auto_provision_esp_via_softap_bridge(
                current_pc_ssid=str(connected_ssid),
                target_24g_ssid=str(esp_target_ssid),
                target_password=str(wifi_password),
                esp_port=self._config.esp32_port,
                api_token=settings.esp32_api_token or "",
            )
            if bridged:
                health = await self.probe_hardware(force_deep_scan=True)

        if health.wifi_ip and health.wifi_ip != "192.168.4.1":
            # Persiste o IP descoberto caso o host anterior fosse um IP antigo de outra rede
            if self._config.esp32_host != "bartender.local":
                self._config.esp32_host = health.wifi_ip
                self.save_config(self._config)

        await self._broadcast()

        msg_parts: list[str] = []
        if connected_ssid:
            msg_parts.append(f"Rede detectada: '{connected_ssid}' (2.4GHz: '{esp_target_ssid}')")
        else:
            msg_parts.append(f"Servidor ativo em {server_lan_ip}")
        if health.wifi_reachable and health.wifi_ip:
            msg_parts.append(f"ESP localizado em {health.wifi_ip} via {health.discovered_via or 'Wi-Fi'}")
        elif health.serial_connected:
            msg_parts.append(f"ESP pronto na porta USB {health.serial_port}")
        else:
            msg_parts.append("secrets.h atualizado com todas as redes salvas do PC")

        return NetworkSyncResult(
            ok=True,
            connected_ssid=str(connected_ssid) if connected_ssid else None,
            esp_target_ssid=str(esp_target_ssid) if esp_target_ssid else None,
            wifi_password_found=bool(wifi_password),
            server_lan_ip=server_lan_ip,
            lan_ips=lan_ips,
            secrets_updated=secrets_updated,
            serial_provisioned=serial_provisioned,
            esp_discovered=health.wifi_reachable,
            esp_ip=health.wifi_ip,
            discovered_via=health.discovered_via,
            hardware=health,
            message=" · ".join(msg_parts),
        )

    async def get_snapshot(self, refresh_hardware: bool = False) -> SystemSnapshot:
        """Retorna o retrato consolidado do sistema, opcionalmente forçando nova sondagem física."""
        if refresh_hardware:
            await self.probe_hardware()
        return SystemSnapshot(status=self._status, hardware=self._last_health)

    async def sync_pump_rates_to_esp32(self, pumps: dict[PumpId, PumpConfig]) -> bool:
        """Sincroniza vazões calibradas (ml/s) com a memória NVS do ESP32 quando online via Wi-Fi.

        Isso garante que o cálculo físico de milissegundos no microcontrolador reflita imediatamente
        qualquer ajuste de calibração salvo pelo operador na interface web.
        """
        try:
            host = self._last_health.wifi_ip or await self._resolve_wifi_host()
            async with httpx.AsyncClient(timeout=2.5, headers=self._auth_headers(), trust_env=False) as client:
                payload = {pid: cfg.flow_rate_ml_s for pid, cfg in pumps.items()}
                resp = await client.post(f"http://{host}:{self._config.esp32_port}/config/pumps", json=payload)
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def encode_plan(steps: list[DoseStep]) -> str:
        """Serializa a lista de etapas no protocolo compacto `bomba:ml:pausa_ms` aceito pelo firmware.

        Exemplo de saída: `'vermelho:70.0:1500,azul:220.0:0'`
        """
        return ",".join(f"{s.pump}:{round(s.ml, 1)}:{s.pause_ms}" for s in steps if s.ml > 0)

    async def start_dispense(self, drink_id: str, drink_name: str, steps: list[DoseStep]) -> PreparationStatus:
        """Valida disponibilidade, inicializa a telemetria e dispara a task assíncrona de preparo.

        Args:
            drink_id (str): Identificador da receita ou `'custom'`.
            drink_name (str): Nome de exibição da bebida para o modal de acompanhamento.
            steps (list[DoseStep]): Sequência ordenada de bombas, volumes (`ml`) e pausas (`ms`).

        Raises:
            RuntimeError: Caso já exista um preparo em andamento (convertido em HTTP 409 pela rota).
            ConnectionError: Caso o modo exija hardware (`wifi`/`serial`) e ele esteja inacessível (HTTP 503).

        Returns:
            PreparationStatus: Estado inicial (`dispensing`, `progress=2`) retornado imediatamente (HTTP 202).
        """
        # Barreira rápida contra duplo clique ou pedidos simultâneos na rede local
        if self._lock.locked() or self._status.state == "dispensing":
            raise RuntimeError("Já existe um drink sendo preparado no momento.")

        health = await self.probe_hardware()
        if health.active_transport == "disconnected":
            raise ConnectionError(health.detail or "ESP32 desconectado.")

        pumps = load_pumps()
        # Calcula duração total estimada somando tempo de bombeamento (ml / ml_s) + pausas (ms / 1000)
        total_sec = sum((s.ml / pumps[s.pump].flow_rate_ml_s) + (s.pause_ms / 1000.0) for s in steps)

        self._cancel_requested = False
        self._status = PreparationStatus(
            state="dispensing",
            drink_id=drink_id,
            drink_name=drink_name,
            progress=2,
            current_pump=steps[0].pump if steps else None,
            current_step_index=1 if steps else 0,
            total_steps=len(steps),
            message=f"Iniciando preparo de {drink_name}...",
            transport=health.active_transport,  # wifi | serial | simulator
            elapsed_seconds=0.0,
            total_seconds=round(total_sec, 1),
        )
        await self._broadcast()

        # Executa o ciclo completo em background para liberar a resposta HTTP 202 imediatamente
        self._active_task = asyncio.create_task(
            self._run_dispense_job(drink_id, drink_name, steps, health.active_transport, pumps, total_sec)
        )
        return self._status

    async def emergency_stop(self) -> PreparationStatus:
        """Aciona parada de emergência imediata: desliga relés físicos e cancela a task ativa.

        Projetado para resposta de baixíssima latência quando o usuário retira o copo antes da
        hora ou pressiona o botão vermelho no modal.
        """
        self._cancel_requested = True

        # Envia parada imediata ao hardware caso esteja em Wi-Fi ou Serial
        if self._status.transport == "wifi":
            try:
                async with httpx.AsyncClient(timeout=1.5, headers=self._auth_headers(), trust_env=False) as client:
                    await client.post(f"{self._wifi_base_url(use_cached_ip=True)}/stop")
            except Exception:
                pass
        elif self._status.transport == "serial":
            await asyncio.to_thread(self._serial_write_stop)

        # Cancela a task de acompanhamento em background de forma limpa
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

        self._status = self._status.model_copy(
            update={
                "state": "stopped",
                "current_pump": None,
                "message": "Preparo interrompido com segurança (bombas desligadas).",
            }
        )
        await self._broadcast()
        return self._status

    def _serial_write_stop(self) -> None:
        """Envia o comando textual `STOP\\n` diretamente no buffer de saída da porta USB Serial."""
        try:
            if self._serial and self._serial.is_open:
                self._serial.write(b"STOP\n")
                self._serial.flush()
        except Exception:
            pass

    async def _run_dispense_job(
        self,
        drink_id: str,
        drink_name: str,
        steps: list[DoseStep],
        transport: str,
        pumps: dict[PumpId, PumpConfig],
        total_sec: float,
    ) -> None:
        """Worker em background protegido por `self._lock` que delega para o driver de transporte ativo."""
        async with self._lock:
            try:
                if transport == "wifi":
                    await self._execute_wifi(drink_name, steps, pumps, total_sec)
                elif transport == "serial":
                    await self._execute_serial(drink_name, steps, pumps, total_sec)
                else:
                    await self._execute_simulator(drink_name, steps, pumps, total_sec)
            except asyncio.CancelledError:
                # Repropaga cancelamento intencional disparado por `emergency_stop`
                raise
            except Exception as exc:
                # Captura erros inesperados de rede/serial e notifica todos os clientes WebSocket
                self._status = self._status.model_copy(
                    update={
                        "state": "error",
                        "current_pump": None,
                        "message": f"Falha durante o preparo: {exc}",
                    }
                )
                await self._broadcast()

    async def _execute_wifi(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpConfig],
        total_sec: float,
    ) -> None:
        """Executa o plano via API HTTP JSON do ESP32 (`POST /dispense`) e monitora `GET /status` a cada 300ms."""
        plan_str = self.encode_plan(steps)
        start_ts = time.monotonic()

        base_url = self._wifi_base_url(use_cached_ip=True)
        async with httpx.AsyncClient(timeout=4.0, headers=self._auth_headers(), trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/dispense",
                json={"name": drink_name, "plan": plan_str},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"ESP32 recusou comando ({resp.status_code}): {resp.text}")

            # Margem generosa de segurança além do tempo estimado para acomodar melodia e latência Wi-Fi
            timeout_at = start_ts + max(total_sec + 20.0, 45.0)
            while time.monotonic() < timeout_at:
                if self._cancel_requested:
                    return
                await asyncio.sleep(0.3)
                st_resp = await client.get(f"{base_url}/status")
                data = st_resp.json()
                esp_state = data.get("state", "idle")
                progress = int(data.get("progress", 0))
                cur_pump = data.get("current_pump") or None
                step_idx = int(data.get("step_index", 1))
                elapsed = round(time.monotonic() - start_ts, 1)

                if esp_state in ("done", "idle") and progress >= 100:
                    break
                if esp_state == "stopped":
                    self._status = self._status.model_copy(
                        update={
                            "state": "stopped",
                            "current_pump": None,
                            "message": "Preparo interrompido no ESP32.",
                        }
                    )
                    await self._broadcast()
                    return

                pump_label = pumps[cur_pump].ingredient if cur_pump in pumps else "Finalizando com melodia..."
                msg = (
                    f"Dosando {pump_label}..."
                    if esp_state == "dispensing" and cur_pump
                    else "Finalizando seu drink..."
                )
                self._status = self._status.model_copy(
                    update={
                        "progress": max(5, min(99, progress)),
                        "current_pump": cur_pump if cur_pump in pumps else None,
                        "current_step_index": step_idx,
                        "elapsed_seconds": elapsed,
                        "message": msg,
                    }
                )
                await self._broadcast()

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} finalizado! Pode retirar seu copo.",
            }
        )
        await self._broadcast()

    def _open_serial_sync(self) -> serial.Serial:
        """Abre ou reutiliza a porta USB Serial de forma síncrona (invocada via `asyncio.to_thread`).

        Aguarda `1.2s` na abertura inicial pois placas ESP32/Arduino podem sofrer auto-reset pelo
        sinal DTR/RTS da conversora USB-Serial (CP2102/CH340) ao abrir a porta COM.
        """
        if self._serial and self._serial.is_open:
            return self._serial
        ser = serial.Serial(self._config.serial_port, self._config.serial_baud, timeout=0.2)
        time.sleep(1.2)
        ser.reset_input_buffer()
        self._serial = ser
        return ser

    async def _execute_serial(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpConfig],
        total_sec: float,
    ) -> None:
        """Executa o plano via protocolo textual USB Serial (`PLAN:...`) lendo telemetria linha a linha."""
        plan_str = self.encode_plan(steps)
        start_ts = time.monotonic()

        try:
            ser = await asyncio.to_thread(self._open_serial_sync)
        except SerialException as exc:
            raise RuntimeError(f"Não foi possível abrir {self._config.serial_port}: {exc}") from exc

        cmd = f"PLAN:{plan_str}\n".encode("utf-8")
        await asyncio.to_thread(ser.write, cmd)
        await asyncio.to_thread(ser.flush)

        timeout_at = start_ts + max(total_sec + 20.0, 45.0)
        done = False

        while time.monotonic() < timeout_at and not done:
            if self._cancel_requested:
                return
            line_bytes = await asyncio.to_thread(ser.readline)
            elapsed = round(time.monotonic() - start_ts, 1)

            if line_bytes:
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if line == "DONE":
                    done = True
                    break
                if line == "STOPPED":
                    self._status = self._status.model_copy(
                        update={"state": "stopped", "current_pump": None, "message": "Interrompido via USB Serial."}
                    )
                    await self._broadcast()
                    return
                if line.startswith("PROGRESS:"):
                    # Formato emitido pelo firmware a cada 400ms: PROGRESS:<pct>:<pump_key>
                    parts = line.split(":")
                    prog = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else self._status.progress
                    cur_pump = parts[2] if len(parts) > 2 and parts[2] in pumps else None
                    label = pumps[cur_pump].ingredient if cur_pump else "Preparando..."
                    self._status = self._status.model_copy(
                        update={
                            "progress": max(5, min(99, prog)),
                            "current_pump": cur_pump,
                            "elapsed_seconds": elapsed,
                            "message": f"Dosando {label}...",
                        }
                    )
                    await self._broadcast()
            else:
                # Estimativa suave caso o firmware envie apenas DONE ao final
                est_prog = int(min(95, (elapsed / max(total_sec, 1.0)) * 95))
                if est_prog != self._status.progress:
                    self._status = self._status.model_copy(
                        update={"progress": est_prog, "elapsed_seconds": elapsed}
                    )
                    await self._broadcast()
                await asyncio.sleep(0.1)

        if not done:
            raise TimeoutError("Tempo limite de resposta do ESP32 via Serial excedido.")

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} finalizado! Pode retirar seu copo.",
            }
        )
        await self._broadcast()

    async def _execute_simulator(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpConfig],
        total_sec: float,
    ) -> None:
        """Simulador volumétrico de alta fidelidade para demonstrações comerciais e desenvolvimento sem hardware.

        Reproduz com exatidão matemática o tempo de escoamento (`step.ml / flow_rate_ml_s`),
        as pausas inter-ingredientes (`step.pause_ms`) e a etapa final de melodia, emitindo
        eventos WebSocket a cada `150 ms` idênticos aos de uma máquina física real.
        """
        start_ts = time.monotonic()

        for idx, step in enumerate(steps, start=1):
            if self._cancel_requested:
                return
            pump_cfg = pumps[step.pump]
            # Conversão volumétrica física: tempo em segundos = volume (ml) / vazão calibrada (ml/s)
            pour_duration = step.ml / pump_cfg.flow_rate_ml_s
            step_end = time.monotonic() + pour_duration

            while time.monotonic() < step_end:
                if self._cancel_requested:
                    return
                elapsed = time.monotonic() - start_ts
                progress = int(min(96, max(4, (elapsed / max(total_sec, 0.5)) * 96)))
                self._status = self._status.model_copy(
                    update={
                        "progress": progress,
                        "current_pump": step.pump,
                        "current_step_index": idx,
                        "elapsed_seconds": round(elapsed, 1),
                        "message": f"Dosando {round(step.ml)} ml de {pump_cfg.ingredient} ({pump_cfg.label})...",
                    }
                )
                await self._broadcast()
                await asyncio.sleep(0.15)

            # Simula a pausa de estabilização hidráulica entre bombas
            if step.pause_ms > 0:
                pause_end = time.monotonic() + (step.pause_ms / 1000.0)
                while time.monotonic() < pause_end:
                    if self._cancel_requested:
                        return
                    elapsed = time.monotonic() - start_ts
                    progress = int(min(98, (elapsed / max(total_sec, 0.5)) * 96))
                    self._status = self._status.model_copy(
                        update={
                            "progress": progress,
                            "current_pump": None,
                            "current_step_index": idx,
                            "elapsed_seconds": round(elapsed, 1),
                            "message": "Estabilizando fluxo entre ingredientes...",
                        }
                    )
                    await self._broadcast()
                    await asyncio.sleep(0.15)

        # Breve toque final representando a melodia de conclusão do buzzer
        self._status = self._status.model_copy(
            update={
                "progress": 99,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": "Tocando melodia de finalização...",
            }
        )
        await self._broadcast()
        await asyncio.sleep(0.6)

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} pronto! Aproveite seu drink.",
            }
        )
        await self._broadcast()


# Instância global única do controlador compartilhada por toda a aplicação FastAPI
esp32_controller = ESP32Controller()

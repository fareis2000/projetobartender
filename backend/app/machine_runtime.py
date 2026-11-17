"""Motor Assíncrono de Execução de Hardware, Cloud Sync IoT e Broadcast WebSocket.

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Gerencia o estado em tempo real, a comunicação física/virtual de cada máquina da rede e o
worker global de manutenção de filas e conciliação Pix (`MachineRuntimeManager`):

1. **Arquitetura Cloud Sync Outbound (`_execute_cloud_iot` + `handle_iot_sync`):**
   - Diferencial comercial decisivo para escalar bares e franquias: a placa `ESP8266` ou
     `ESP32` conectada apenas no Wi-Fi 2.4 GHz comum do bar faz chamadas HTTP/HTTPS de saída
     a cada `450ms–800ms` para `/api/iot/{machine_slug}/sync`.
   - **Zero TI no Bar:** Não exige computador ligado no balcão, não exige IP fixo, não exige
     abertura de portas (`Port Forwarding` / `NAT`) no roteador da operadora, e permite que o
     cliente peça pelo **próprio 4G/5G** sem pedir a senha do Wi-Fi do estabelecimento!
2. **Quatro Transportes Unificados (`auto`, `cloud_iot`, `wifi`, `serial`, `simulator`):**
   - Opera de forma transparente via nuvem IoT, API HTTP LAN (`bartender.local`), cabo USB
     Serial (`115200 bps`) ou Simulador Volumétrico fiel para demonstrações comerciais B2B.
3. **Pub/Sub WebSocket por Máquina + Worker de Conciliação (`_maintenance_loop`):**
   - Transmite frames `MachineRealtimeSnapshot` instantâneos para os celulares na fila e para
     o painel do bar, enquanto avança turnos expirados (`75s`) e consulta pagamentos Mercado
     Pago pendentes mesmo em ambientes sem Webhook HTTPS público.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import socket
import time
from typing import Awaitable, Callable

import httpx
import serial
import serial.tools.list_ports
from serial.serialutil import SerialException

from .config import PROJECT_ROOT
from .database import (
    confirm_order_payment,
    expire_and_advance_queue,
    finalize_order_after_dispense,
    get_conn,
    get_machine_pumps_with_bottles,
    get_machine_queue_stats,
    list_pending_mp_orders,
    record_iot_heartbeat,
    utcnow,
)
from .models import (
    ConnectionMode,
    DoseStep,
    HardwareHealth,
    IotSyncRequest,
    IotSyncResponse,
    MachineRealtimeSnapshot,
    PreparationStatus,
    PumpId,
    PumpSlotOut,
)
from .network_discovery import (
    auto_provision_esp_via_softap_bridge,
    discover_esp_on_network,
    find_best_serial_port,
    get_current_network_info,
    list_all_serial_ports,
    provision_esp_via_serial_sync,
    push_cloud_config_to_esp,
    push_wifi_config_to_esp_http,
    sync_secrets_h_with_current_network,
)
from .payments import check_mercadopago_payment_status

BOMBAS_SECRETS_FILE = PROJECT_ROOT / "bombas" / "secrets.h"


class MachineExecutor:
    """Controla o preparo físico/simulado, telemetria IoT e WebSockets de uma máquina específica.

    Cada estação física do sistema possui sua própria instância isolada de `MachineExecutor` em
    memória, garantindo que múltiplas máquinas do mesmo bar (ou de dezenas de bares distintos)
    sirvam drinks simultaneamente sem bloqueio cruzado (`asyncio.Lock` individual por máquina).
    """

    def __init__(self, machine_id: str, machine_slug: str) -> None:
        """Inicializa locks, fila de comandos Cloud IoT e registro de inscritos WebSocket da máquina."""
        self.machine_id = machine_id
        self.machine_slug = machine_slug
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None
        self._cancel_requested = False
        self._serial: serial.Serial | None = None
        self._status = PreparationStatus()
        self._subscribers: set[Callable[[MachineRealtimeSnapshot], Awaitable[None]]] = set()

        # Fila de comandos IoT pendentes p/ ESP8266/ESP32 no Wi-Fi local do bar
        self._iot_pending_cmd: IotSyncResponse | None = None
        self._iot_job_started = False
        self._iot_done_event = asyncio.Event()
        self._last_health: HardwareHealth | None = None
        self._last_subnet_scan_ts: float = 0.0
        self._last_softap_bridge_ts: float = 0.0

    @property
    def status(self) -> PreparationStatus:
        """Retorna o estado instantâneo atual do preparo da máquina."""
        return self._status

    def subscribe(self, cb: Callable[[MachineRealtimeSnapshot], Awaitable[None]]) -> None:
        """Inscreve um callback assíncrono (conexão WebSocket ativa) para receber snapshots em tempo real."""
        self._subscribers.add(cb)

    def unsubscribe(self, cb: Callable[[MachineRealtimeSnapshot], Awaitable[None]]) -> None:
        """Remove o callback WebSocket encerrado da lista de ouvintes da máquina."""
        self._subscribers.discard(cb)

    @staticmethod
    def encode_plan(steps: list[DoseStep]) -> str:
        """Serializa os passos da receita no protocolo compacto esperado pelo firmware ESP.

        Exemplo de saída: `"vermelho:70.0:1500,azul:220.0:0"` (`<bomba>:<ml>:<pausa_ms>`).
        """
        return ",".join(f"{s.pump}:{round(s.ml, 1)}:{s.pause_ms}" for s in steps if s.ml > 0)

    @staticmethod
    def list_serial_ports() -> list[str]:
        """Enumera as portas seriais USB (`COMx` / `/dev/ttyUSBx`) disponíveis no host."""
        return list_all_serial_ports()

    def _load_machine_db_row(self):
        """Busca a linha atualizada de configuração da máquina na tabela `machines`."""
        with get_conn() as conn:
            return conn.execute("SELECT * FROM machines WHERE id = ?", (self.machine_id,)).fetchone()

    def _load_pumps(self) -> list[PumpSlotOut]:
        """Carrega as 4 bombas da máquina já enriquecidas com garrafas e estoque disponível."""
        with get_conn() as conn:
            return get_machine_pumps_with_bottles(conn, self.machine_id)

    async def probe_hardware(self, quick: bool = False, force_deep_scan: bool = False) -> HardwareHealth:
        """Inspeciona a saúde de conectividade da máquina e seleciona o transporte ativo ideal.

        Ordem de prioridade multi-rede:
        1. `cloud_iot`: Batimento HTTP recente do ESP (`last_seen_at <= 12.0s`).
        2. `wifi`: Descoberta automática em 4 camadas na rede atual (UDP 4210 c/ auto-config de Cloud URL,
           IP em cache/mDNS/SoftAP `192.168.4.1`, Tabela ARP e Sub-rede `/24`).
        3. `serial`: Detecção automática de qualquer porta USB Serial conectada (`COMx`).
        4. `simulator`: Fallback gracioso para o simulador volumétrico sem travar demonstrações.
        """
        row = self._load_machine_db_row()
        if not row:
            raise RuntimeError(f"Máquina {self.machine_id} não encontrada.")

        mode: ConnectionMode = row["connection_mode"]
        esp_host: str = row["esp32_host"]
        esp_port: int = int(row["esp32_port"])
        ser_port: str = row["serial_port"]
        ser_baud: int = int(row["serial_baud"])
        api_tok: str = row["api_token"] or ""

        net_info = get_current_network_info()
        connected_ssid = net_info.get("connected_ssid")
        esp_target_ssid = net_info.get("esp_target_ssid")
        server_lan_ip = str(net_info.get("primary_ip") or "127.0.0.1")
        sync_url = f"http://{server_lan_ip}:8010/api/iot/{self.machine_slug}/sync"

        # Verifica batimento IoT recente (últimos 12 segundos)
        iot_online = False
        seen_ago: float | None = None
        if row["last_seen_at"]:
            try:
                seen_dt = dt.datetime.fromisoformat(row["last_seen_at"])
                if seen_dt.tzinfo is None:
                    seen_dt = seen_dt.replace(tzinfo=dt.timezone.utc)
                seen_ago = round(max(0.0, (utcnow() - seen_dt).total_seconds()), 1)
                iot_online = seen_ago <= 12.0
            except Exception:
                pass

        ports = self.list_serial_ports() if not quick else []
        if not quick and ports:
            best_ser = find_best_serial_port(ser_port)
            if best_ser:
                ser_port = best_ser

        wifi_ok = False
        wifi_ip: str | None = row["last_ip"] if iot_online else (self._last_health.wifi_ip if self._last_health else None)
        wifi_rssi: int | None = row["last_rssi"] if iot_online else None
        discovered_via: str | None = "cloud_iot" if iot_online else None
        serial_ok = False

        # Descoberta automática na rede atual (executada se não estiver com batimento IoT recente)
        if not quick and mode in ("auto", "wifi", "cloud_iot") and not iot_online:
            now_mono = time.monotonic()
            should_deep_scan = (
                force_deep_scan
                or self._last_health is None
                or not self._last_health.wifi_reachable
                or (now_mono - self._last_subnet_scan_ts > 15.0)
            )
            if should_deep_scan:
                self._last_subnet_scan_ts = now_mono

            disc = await discover_esp_on_network(
                configured_host=esp_host,
                port=esp_port,
                cached_ip=wifi_ip or row["last_ip"],
                api_token=api_tok,
                sync_url=sync_url,
                allow_subnet_scan=should_deep_scan,
            )

            if disc and disc.get("ip"):
                wifi_ok = True
                wifi_ip = str(disc["ip"])
                wifi_rssi = disc.get("rssi")
                discovered_via = str(disc.get("discovered_via") or "lan")
                # Atualiza a URL de Cloud Sync no ESP descoberto e registra o novo IP no SQLite!
                if server_lan_ip != "127.0.0.1":
                    await push_cloud_config_to_esp(wifi_ip, sync_url, api_tok, port=esp_port)
                if wifi_ip != "192.168.4.1":
                    record_iot_heartbeat(self.machine_slug, api_tok, wifi_ip, wifi_rssi or -50)

        if not quick and not iot_online:
            if (self._serial and self._serial.is_open) or (ser_port in ports):
                serial_ok = True

        # Se não encontrou na LAN nem no USB, mas o AP do ESP está no ar, provisiona automaticamente via SoftAP Bridge!
        if (
            not quick
            and not iot_online
            and not wifi_ok
            and not serial_ok
            and mode in ("auto", "wifi", "cloud_iot")
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
                esp_port=esp_port,
                api_token=api_tok,
                cloud_sync_url=sync_url,
            )
            if bridged:
                disc = await discover_esp_on_network(
                    configured_host=esp_host,
                    port=esp_port,
                    cached_ip=wifi_ip or row["last_ip"],
                    api_token=api_tok,
                    sync_url=sync_url,
                    allow_subnet_scan=True,
                )
                if disc and disc.get("ip"):
                    wifi_ok = True
                    wifi_ip = str(disc["ip"])
                    wifi_rssi = disc.get("rssi")
                    discovered_via = "softap_bridge"
                    if wifi_ip != "192.168.4.1":
                        record_iot_heartbeat(self.machine_slug, api_tok, wifi_ip, wifi_rssi or -50)

        # Determina transporte efetivo com fallback resiliente entre Cloud IoT, Wi-Fi LAN e USB Serial
        if mode == "simulator":
            active = "simulator"
            detail = "Simulador volumétrico ativo"
        elif mode == "cloud_iot":
            if iot_online:
                active = "cloud_iot"
                detail = f"ESP conectado via Wi-Fi ({wifi_ip})"
            elif wifi_ok:
                active = "wifi"
                detail = f"ESP localizado na rede atual ({wifi_ip}) e sincronizado"
            elif serial_ok:
                active = "serial"
                detail = f"Wi-Fi ausente — ESP pronto via cabo USB ({ser_port})"
            else:
                active = "disconnected"
                detail = f"Aguardando ESP na rede '{connected_ssid or 'atual'}' (/api/iot/{self.machine_slug}/sync)"
        elif mode == "wifi":
            if wifi_ok:
                active = "wifi"
                detail = f"ESP conectado na rede atual ({wifi_ip})"
            elif iot_online:
                active = "cloud_iot"
                detail = f"ESP conectado via Cloud Sync ({wifi_ip})"
            elif serial_ok:
                active = "serial"
                detail = f"Wi-Fi ausente — usando cabo USB ({ser_port})"
            else:
                active = "disconnected"
                detail = f"ESP não localizado na rede '{connected_ssid or esp_host}'"
        elif mode == "serial":
            if serial_ok:
                active = "serial"
                detail = f"USB Serial {ser_port} pronta"
            elif wifi_ok:
                active = "wifi"
                detail = f"USB desconectado — ESP ativo no Wi-Fi ({wifi_ip})"
            else:
                active = "disconnected"
                detail = f"Porta {ser_port} indisponível"
        else:  # auto
            if iot_online:
                active = "cloud_iot"
                detail = f"ESP sincronizado na rede atual ({wifi_ip})"
            elif wifi_ok:
                active = "wifi"
                detail = f"ESP online via LAN ({wifi_ip})"
            elif serial_ok:
                active = "serial"
                detail = f"ESP conectado via USB ({ser_port})"
            else:
                active = "simulator"
                if net_info.get("is_5ghz_only"):
                    detail = (
                        f"Rede '{connected_ssid}' apenas em 5 GHz (Canal {net_info.get('channel')}). "
                        "Mude o Roteador Wi-Fi/Hotspot para 2.4 GHz para o ESP8266 conectar!"
                    )
                else:
                    detail = "Simulador inteligente pronto (sem ESP físico detectado)"

        self._last_health = HardwareHealth(
            mode=mode,
            active_transport=active,  # type: ignore[arg-type]
            wifi_reachable=wifi_ok or iot_online,
            wifi_ip=wifi_ip,
            wifi_rssi=wifi_rssi,
            serial_connected=serial_ok,
            available_serial_ports=ports,
            esp32_host=esp_host,
            esp32_port=esp_port,
            serial_port=ser_port,
            serial_baud=ser_baud,
            iot_online=iot_online,
            last_seen_seconds_ago=seen_ago,
            detail=detail,
            connected_ssid=str(connected_ssid) if connected_ssid else None,
            esp_target_ssid=str(esp_target_ssid) if esp_target_ssid else None,
            server_lan_ip=server_lan_ip,
            discovered_via=discovered_via,
        )
        return self._last_health

    async def sync_and_discover_network(self, base_url: str) -> HardwareHealth:
        """Puxa a rede Wi-Fi conectada no servidor, atualiza `secrets.h`, provisiona o ESP (USB/SoftAP/LAN) e localiza o IP."""
        row = self._load_machine_db_row()
        if not row:
            raise RuntimeError(f"Máquina {self.machine_id} não encontrada.")

        api_tok = str(row["api_token"] or "")
        esp_port = int(row["esp32_port"])
        ser_baud = int(row["serial_baud"])
        net_info = await asyncio.to_thread(get_current_network_info, True)
        esp_target_ssid = net_info.get("esp_target_ssid") or net_info.get("connected_ssid")
        wifi_pass = str(net_info.get("wifi_password") or "")
        sync_url = f"{base_url.rstrip('/')}/api/iot/{self.machine_slug}/sync"

        await asyncio.to_thread(
            sync_secrets_h_with_current_network,
            BOMBAS_SECRETS_FILE,
            api_token=api_tok,
            cloud_sync_url=sync_url,
        )

        best_ser = find_best_serial_port(row["serial_port"])
        if best_ser and esp_target_ssid:
            prov = await asyncio.to_thread(
                provision_esp_via_serial_sync,
                best_ser,
                ser_baud,
                str(esp_target_ssid),
                wifi_pass,
                sync_url,
            )
            if prov.get("ip") and prov["ip"] not in ("0.0.0.0", "192.168.4.1"):
                record_iot_heartbeat(self.machine_slug, api_tok, str(prov["ip"]), -55)

        lan_ips = list(net_info.get("lan_ips") or [])
        if esp_target_ssid and wifi_pass and any(str(ip).startswith("192.168.4.") for ip in lan_ips):
            await push_wifi_config_to_esp_http(
                "192.168.4.1",
                str(esp_target_ssid),
                wifi_pass,
                port=esp_port,
                api_token=api_tok,
                cloud_sync_url=sync_url,
            )

        health = await self.probe_hardware(quick=False, force_deep_scan=True)
        connected_ssid = net_info.get("connected_ssid")
        if not health.wifi_reachable and not health.serial_connected and connected_ssid and esp_target_ssid:
            bridged = await auto_provision_esp_via_softap_bridge(
                current_pc_ssid=str(connected_ssid),
                target_24g_ssid=str(esp_target_ssid),
                target_password=wifi_pass,
                esp_port=esp_port,
                api_token=api_tok,
                cloud_sync_url=sync_url,
            )
            if bridged:
                health = await self.probe_hardware(quick=False, force_deep_scan=True)
        await self.broadcast()
        return health

    async def build_snapshot(self, refresh_hardware: bool = False) -> MachineRealtimeSnapshot:
        """Monta o snapshot completo de estado, fila e bombas da máquina para HTTP/WebSocket."""
        if refresh_hardware or self._last_health is None:
            await self.probe_hardware(quick=not refresh_hardware)
        assert self._last_health is not None
        q_len, ready_id, ready_num = get_machine_queue_stats(self.machine_id)
        pumps = self._load_pumps()
        return MachineRealtimeSnapshot(
            machine_slug=self.machine_slug,
            status=self._status,
            hardware=self._last_health,
            queue_length=q_len,
            ready_order_id=ready_id,
            ready_order_number=ready_num,
            pumps=pumps,
        )

    async def broadcast(self) -> None:
        """Envia o snapshot atualizado para todos os clientes WebSocket conectados nesta máquina.

        Remove silenciosamente conexões órfãs ou desconectadas (`stale`) sem interromper o loop.
        """
        if not self._subscribers:
            return
        snap = await self.build_snapshot(refresh_hardware=False)
        stale: list[Callable[[MachineRealtimeSnapshot], Awaitable[None]]] = []
        for cb in list(self._subscribers):
            try:
                await cb(snap)
            except Exception:
                stale.append(cb)
        for cb in stale:
            self._subscribers.discard(cb)

    def queue_pump_rates_sync(self, pumps: list[PumpSlotOut]) -> None:
        """Agenda comando OTA (`update_pumps`) para gravar novas vazões calibradas (`ml/s`) na Flash do ESP."""
        rates = {p.pump_id: p.flow_rate_ml_s for p in pumps}
        if self._iot_pending_cmd is None or self._iot_pending_cmd.command == "none":
            self._iot_pending_cmd = IotSyncResponse(command="update_pumps", pumps_rates=rates)

    async def handle_iot_sync(self, api_token: str, payload: IotSyncRequest) -> IotSyncResponse:
        """Endpoint chamado a cada ~500ms pelo ESP8266/ESP32 conectado no Wi-Fi local do bar.

        Fluxo Bidirecional em Uma Única Requisição Outbound:
        1. Valida `X-Machine-Token` em tempo constante e grava IP local + RSSI Wi-Fi no SQLite.
        2. Se houver preparo Cloud IoT em curso, espelha o progresso real reportado pela placa
           para o celular do cliente via WebSocket e detecta conclusão (`done`/`idle`) ou `stopped`.
        3. Despacha na resposta qualquer comando enfileirado (`dispense`, `stop` ou `update_pumps`).
        """
        record_iot_heartbeat(self.machine_slug, api_token, payload.ip, payload.rssi)
        await self.probe_hardware(quick=True)

        if self._status.state == "dispensing" and self._status.transport == "cloud_iot":
            esp_st = payload.state.lower()
            pumps_map = {p.pump_id: p for p in self._load_pumps()}
            if esp_st in ("dispensing", "dosing", "pausing", "melody"):
                self._iot_job_started = True
                cur_p: PumpId | None = payload.current_pump if payload.current_pump in pumps_map else None  # type: ignore[assignment]
                ing_name = pumps_map[cur_p].ingredient if cur_p else "Finalizando camadas..."
                self._status = self._status.model_copy(
                    update={
                        "progress": max(5, min(99, int(payload.progress))),
                        "current_pump": cur_p,
                        "current_step_index": payload.step,
                        "message": f"Servindo {ing_name}...",
                    }
                )
                await self.broadcast()
            elif self._iot_job_started and esp_st in ("done", "idle"):
                # Placa concluiu todas as bombas + melodia de conclusão; acorda a coroutine _execute_cloud_iot
                self._iot_done_event.set()
            elif esp_st == "stopped":
                self._cancel_requested = True
                self._iot_done_event.set()

        if self._iot_pending_cmd is not None:
            cmd = self._iot_pending_cmd
            self._iot_pending_cmd = None
            return cmd

        return IotSyncResponse(command="none")

    async def start_order_dispense(
        self,
        *,
        order_id: str | None,
        order_number: int | None,
        drink_id: str | None,
        drink_name: str,
        steps: list[DoseStep],
    ) -> PreparationStatus:
        """Valida disponibilidade de hardware e dispara a task assíncrona de dosagem do pedido.

        Só é invocada após confirmação explícita do cliente de que o copo está posicionado na
        plataforma (`confirm_cup_and_start_dispense`).
        """
        if self._lock.locked() or self._status.state == "dispensing":
            raise RuntimeError("A máquina já está servindo um drink neste instante.")

        health = await self.probe_hardware(quick=False)
        if health.active_transport == "disconnected":
            raise ConnectionError(health.detail or "Máquina desconectada.")

        pumps = {p.pump_id: p for p in self._load_pumps()}
        total_sec = sum((s.ml / max(pumps[s.pump].flow_rate_ml_s, 1.0)) + (s.pause_ms / 1000.0) for s in steps)

        self._cancel_requested = False
        self._status = PreparationStatus(
            state="dispensing",
            order_id=order_id,
            order_number=order_number,
            drink_id=drink_id,
            drink_name=drink_name,
            progress=3,
            current_pump=steps[0].pump if steps else None,
            current_step_index=1 if steps else 0,
            total_steps=len(steps),
            message=f"Iniciando preparo de {drink_name}...",
            transport=health.active_transport,  # type: ignore[arg-type]
            elapsed_seconds=0.0,
            total_seconds=round(total_sec, 1),
        )
        await self.broadcast()

        self._active_task = asyncio.create_task(
            self._run_dispense_job(order_id, drink_name, steps, health.active_transport, pumps, total_sec)
        )
        return self._status

    async def emergency_stop(self) -> PreparationStatus:
        """Aciona parada de emergência imediata das bombas em qualquer transporte ativo.

        Desliga relés fisicamente (`stop` via Cloud IoT, `/stop` via LAN ou `STOP\\n` via Serial),
        cancela a tarefa em execução e marca o pedido como `FAILED_DISPENSE` sem abater estoque,
        permitindo reenvio à fila ou estorno pelo painel do dono do bar.
        """
        self._cancel_requested = True
        if self._status.transport == "cloud_iot":
            self._iot_pending_cmd = IotSyncResponse(command="stop")
            self._iot_done_event.set()
        elif self._status.transport == "wifi" and self._last_health:
            row = self._load_machine_db_row()
            host = self._last_health.wifi_ip or self._last_health.esp32_host
            headers = {"X-Bartender-Token": row["api_token"]} if row and row["api_token"] else {}
            try:
                async with httpx.AsyncClient(timeout=1.5, headers=headers, trust_env=False) as client:
                    await client.post(f"http://{host}:{self._last_health.esp32_port}/stop")
            except Exception:
                pass
        elif self._status.transport == "serial":
            try:
                if self._serial and self._serial.is_open:
                    await asyncio.to_thread(self._serial.write, b"STOP\n")
            except Exception:
                pass

        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

        if self._status.order_id:
            finalize_order_after_dispense(self._status.order_id, success=False)

        self._status = self._status.model_copy(
            update={
                "state": "stopped",
                "current_pump": None,
                "message": "Preparo interrompido com segurança (bombas desligadas).",
            }
        )
        await self.broadcast()
        return self._status

    async def _run_dispense_job(
        self,
        order_id: str | None,
        drink_name: str,
        steps: list[DoseStep],
        transport: str,
        pumps: dict[PumpId, PumpSlotOut],
        total_sec: float,
    ) -> None:
        """Gerencia o ciclo completo da dosagem sob lock exclusivo e finaliza estoque + fila ao término."""
        async with self._lock:
            success = False
            try:
                if transport == "cloud_iot":
                    await self._execute_cloud_iot(order_id, drink_name, steps, total_sec)
                elif transport == "wifi":
                    await self._execute_wifi(drink_name, steps, pumps, total_sec)
                elif transport == "serial":
                    await self._execute_serial(drink_name, steps, pumps, total_sec)
                else:
                    await self._execute_simulator(drink_name, steps, pumps, total_sec)
                success = not self._cancel_requested and self._status.state == "completed"
            except asyncio.CancelledError:
                success = False
                raise
            except Exception as exc:
                success = False
                self._status = self._status.model_copy(
                    update={
                        "state": "error",
                        "current_pump": None,
                        "message": f"Falha no hardware durante o preparo: {exc}",
                    }
                )
            finally:
                # Registra sucesso (abatendo ml das garrafas e promovendo próximo da fila) ou falha
                if order_id:
                    finalize_order_after_dispense(order_id, success=success)
                await self.broadcast()
                # Após 3.5s concluído, volta estado visual da máquina p/ idle liberando próximo da fila
                if success:
                    await asyncio.sleep(3.5)
                    if self._status.state == "completed":
                        self._status = PreparationStatus()
                        await self.broadcast()

    async def _execute_cloud_iot(
        self,
        order_id: str | None,
        drink_name: str,
        steps: list[DoseStep],
        total_sec: float,
    ) -> None:
        """Enfileira o plano de dosagem para ser coletado pelo próximo POST `/sync` do ESP no Wi-Fi do bar."""
        start_ts = time.monotonic()
        self._iot_job_started = False
        self._iot_done_event.clear()
        self._iot_pending_cmd = IotSyncResponse(
            command="dispense",
            order_id=order_id,
            drink_name=drink_name,
            plan=self.encode_plan(steps),
        )
        timeout = max(total_sec + 25.0, 45.0)
        try:
            await asyncio.wait_for(self._iot_done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("ESP não confirmou conclusão dentro do tempo esperado.") from exc

        if self._cancel_requested:
            return

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} pronto! Retire seu copo e aproveite!",
            }
        )

    async def _execute_wifi(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpSlotOut],
        total_sec: float,
    ) -> None:
        """Executa o preparo comandando diretamente a API HTTP local da placa ESP na rede LAN."""
        row = self._load_machine_db_row()
        host = (self._last_health.wifi_ip if self._last_health else None) or row["esp32_host"]
        port = int(row["esp32_port"])
        headers = {"X-Bartender-Token": row["api_token"]} if row["api_token"] else {}
        base_url = f"http://{host}:{port}"
        start_ts = time.monotonic()

        async with httpx.AsyncClient(timeout=4.0, headers=headers, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/dispense",
                json={"name": drink_name, "plan": self.encode_plan(steps)},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"ESP recusou comando ({resp.status_code}): {resp.text}")

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
                elapsed = round(time.monotonic() - start_ts, 1)

                if esp_state in ("done", "idle") and progress >= 100:
                    break
                if esp_state == "stopped":
                    self._cancel_requested = True
                    return

                ing = pumps[cur_pump].ingredient if cur_pump in pumps else "Finalizando..."
                self._status = self._status.model_copy(
                    update={
                        "progress": max(5, min(99, progress)),
                        "current_pump": cur_pump if cur_pump in pumps else None,
                        "elapsed_seconds": elapsed,
                        "message": f"Servindo {ing}...",
                    }
                )
                await self.broadcast()

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} finalizado! Pode retirar seu copo.",
            }
        )

    async def _execute_serial(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpSlotOut],
        total_sec: float,
    ) -> None:
        """Executa o preparo via cabo USB Serial (`PLAN:<plano>\\n`) lendo frames `PROGRESS:` e `DONE`."""
        row = self._load_machine_db_row()
        start_ts = time.monotonic()
        ser_port = find_best_serial_port(row["serial_port"]) or row["serial_port"]
        try:
            if not self._serial or not self._serial.is_open:
                ser = await asyncio.to_thread(serial.Serial, ser_port, int(row["serial_baud"]), timeout=0.2)
                await asyncio.sleep(1.0)
                self._serial = ser
            assert self._serial is not None
        except SerialException as exc:
            raise RuntimeError(f"Erro na porta {ser_port}: {exc}") from exc

        cmd = f"PLAN:{self.encode_plan(steps)}\n".encode("utf-8")
        await asyncio.to_thread(self._serial.write, cmd)
        await asyncio.to_thread(self._serial.flush)

        timeout_at = start_ts + max(total_sec + 20.0, 45.0)
        done = False
        while time.monotonic() < timeout_at and not done:
            if self._cancel_requested:
                return
            line_bytes = await asyncio.to_thread(self._serial.readline)
            elapsed = round(time.monotonic() - start_ts, 1)
            if line_bytes:
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if line == "DONE":
                    done = True
                    break
                if line == "STOPPED":
                    self._cancel_requested = True
                    return
                if line.startswith("PROGRESS:"):
                    parts = line.split(":")
                    prog = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else self._status.progress
                    cur_p: PumpId | None = parts[2] if len(parts) > 2 and parts[2] in pumps else None  # type: ignore[assignment]
                    ing = pumps[cur_p].ingredient if cur_p else "Preparando..."
                    self._status = self._status.model_copy(
                        update={"progress": max(5, min(99, prog)), "current_pump": cur_p, "elapsed_seconds": elapsed, "message": f"Servindo {ing}..."}
                    )
                    await self.broadcast()
            else:
                await asyncio.sleep(0.1)

        if not done:
            raise TimeoutError("Timeout aguardando resposta Serial do ESP.")

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} pronto! Retire seu copo.",
            }
        )

    async def _execute_simulator(
        self,
        drink_name: str,
        steps: list[DoseStep],
        pumps: dict[PumpId, PumpSlotOut],
        total_sec: float,
    ) -> None:
        """Simula com fidelidade cronométrica a vazão (`ml/s`), pausas de camada e sinal sonoro final."""
        start_ts = time.monotonic()
        for idx, step in enumerate(steps, start=1):
            if self._cancel_requested:
                return
            slot = pumps[step.pump]
            pour_duration = step.ml / max(slot.flow_rate_ml_s, 1.0)
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
                        "message": f"Dosando {round(step.ml)} ml de {slot.ingredient}...",
                    }
                )
                await self.broadcast()
                await asyncio.sleep(0.15)

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
                            "message": "Estabilizando camadas no copo...",
                        }
                    )
                    await self.broadcast()
                    await asyncio.sleep(0.15)

        self._status = self._status.model_copy(
            update={
                "progress": 99,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": "Sinal sonoro de conclusão...",
            }
        )
        await self.broadcast()
        await asyncio.sleep(0.45)

        self._status = self._status.model_copy(
            update={
                "state": "completed",
                "progress": 100,
                "current_pump": None,
                "elapsed_seconds": round(time.monotonic() - start_ts, 1),
                "message": f"{drink_name} servido! Saúde!",
            }
        )


class MachineRuntimeManager:
    """Orquestrador global de todas as máquinas de todos os bares.

    Mantém o registro de instâncias `MachineExecutor` sob demanda e executa em background o
    loop contínuo de manutenção (`_maintenance_loop`) a cada `2.5s`.
    """

    def __init__(self) -> None:
        """Inicializa o dicionário de executores por `machine_id` e ponteiro da task de manutenção."""
        self._executors: dict[str, MachineExecutor] = {}
        self._bg_task: asyncio.Task[None] | None = None

    def get_executor(self, machine_id: str, machine_slug: str) -> MachineExecutor:
        """Obtém ou instancia de forma preguiçosa (*lazy*) o executor dedicado de uma máquina."""
        ex = self._executors.get(machine_id)
        if ex is None:
            ex = MachineExecutor(machine_id=machine_id, machine_slug=machine_slug)
            self._executors[machine_id] = ex
        else:
            ex.machine_slug = machine_slug
        return ex

    def start_background_workers(self) -> None:
        """Inicia o worker assíncrono global durante o evento `startup` do lifespan FastAPI."""
        if self._bg_task is None or self._bg_task.done():
            self._bg_task = asyncio.create_task(self._maintenance_loop())

    async def stop_background_workers(self) -> None:
        """Encerra graciosamente o worker assíncrono global durante o `shutdown` da aplicação."""
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass

    async def _maintenance_loop(self) -> None:
        """Loop periódico (a cada 2.5s) de conciliação Pix Mercado Pago e avanço automático de filas.

        Garante duas propriedades críticas de confiabilidade comercial:
        1. Se o bar estiver rodando sem domínio HTTPS público (logo sem receber Webhook externo),
           consulta proativamente a API do Mercado Pago e aprova o pedido assim que pago.
        2. Se o cliente da vez (`READY_FOR_CUP`) se afastar por mais de `75s` sem confirmar o copo,
           move-o para espera protegida (`PAUSED_TURN`), promove o próximo cliente pago da fila e
           notifica todos os celulares via WebSocket instantaneamente!
        """
        while True:
            try:
                await asyncio.sleep(2.5)
                # 1. Verifica pagamentos Mercado Pago pendentes (fallback caso sem Webhook HTTPS)
                pending_mp = list_pending_mp_orders()
                for ord_id, ext_id, mp_tok in pending_mp:
                    st = await check_mercadopago_payment_status(mp_tok, ext_id)
                    if st == "approved":
                        ord_out, changed = confirm_order_payment(ord_id)
                        if changed:
                            ex = self.get_executor(ord_out.machine_id, ord_out.machine_slug)
                            await ex.broadcast()

                # 2. Avança timers de expiração de fila nas máquinas ativas
                for m_id, ex in list(self._executors.items()):
                    if expire_and_advance_queue(m_id):
                        await ex.broadcast()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass


# Singleton global compartilhado pelas rotas HTTP e WebSockets da API
runtime_manager = MachineRuntimeManager()

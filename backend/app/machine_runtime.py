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
from .payments import check_mercadopago_payment_status


class MachineExecutor:
    """Controla o preparo físico/simulado, telemetria IoT e WebSockets de uma máquina específica."""

    def __init__(self, machine_id: str, machine_slug: str) -> None:
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

    @property
    def status(self) -> PreparationStatus:
        return self._status

    def subscribe(self, cb: Callable[[MachineRealtimeSnapshot], Awaitable[None]]) -> None:
        self._subscribers.add(cb)

    def unsubscribe(self, cb: Callable[[MachineRealtimeSnapshot], Awaitable[None]]) -> None:
        self._subscribers.discard(cb)

    @staticmethod
    def encode_plan(steps: list[DoseStep]) -> str:
        return ",".join(f"{s.pump}:{round(s.ml, 1)}:{s.pause_ms}" for s in steps if s.ml > 0)

    @staticmethod
    def list_serial_ports() -> list[str]:
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def _load_machine_db_row(self):
        with get_conn() as conn:
            return conn.execute("SELECT * FROM machines WHERE id = ?", (self.machine_id,)).fetchone()

    def _load_pumps(self) -> list[PumpSlotOut]:
        with get_conn() as conn:
            return get_machine_pumps_with_bottles(conn, self.machine_id)

    async def probe_hardware(self, quick: bool = False) -> HardwareHealth:
        row = self._load_machine_db_row()
        if not row:
            raise RuntimeError(f"Máquina {self.machine_id} não encontrada.")

        mode: ConnectionMode = row["connection_mode"]
        esp_host: str = row["esp32_host"]
        esp_port: int = int(row["esp32_port"])
        ser_port: str = row["serial_port"]
        ser_baud: int = int(row["serial_baud"])
        api_tok: str = row["api_token"] or ""

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
        wifi_ok = False
        wifi_ip: str | None = row["last_ip"] if iot_online else None
        wifi_rssi: int | None = row["last_rssi"] if iot_online else None
        serial_ok = False

        if not quick and mode in ("auto", "wifi") and not iot_online:
            resolved = esp_host.strip()
            if resolved.lower().endswith(".local"):
                try:
                    resolved = await asyncio.to_thread(socket.gethostbyname, resolved)
                except OSError:
                    pass
            try:
                headers = {"X-Bartender-Token": api_tok} if api_tok else {}
                async with httpx.AsyncClient(timeout=1.8, headers=headers, trust_env=False) as client:
                    resp = await client.get(f"http://{resolved}:{esp_port}/status")
                    if resp.status_code == 200:
                        data = resp.json()
                        wifi_ok = True
                        wifi_ip = data.get("ip") or resolved
                        wifi_rssi = data.get("rssi")
            except Exception:
                pass

        if not quick and mode in ("auto", "serial") and not wifi_ok and not iot_online:
            if (self._serial and self._serial.is_open) or (ser_port in ports):
                serial_ok = True

        if mode == "simulator":
            active = "simulator"
            detail = "Simulador volumétrico ativo"
        elif mode == "cloud_iot":
            active = "cloud_iot" if iot_online else "disconnected"
            detail = (
                f"ESP conectado via Wi-Fi do Bar (IP {wifi_ip})"
                if iot_online
                else "Aguardando ESP conectar via Wi-Fi do Bar (/api/iot/...)"
            )
        elif mode == "wifi":
            active = "wifi" if wifi_ok else "disconnected"
            detail = f"ESP conectado na LAN ({wifi_ip})" if wifi_ok else f"Sem resposta em {esp_host}:{esp_port}"
        elif mode == "serial":
            active = "serial" if serial_ok else "disconnected"
            detail = f"USB Serial {ser_port} pronta" if serial_ok else f"Porta {ser_port} indisponível"
        else:  # auto
            if iot_online:
                active = "cloud_iot"
                detail = f"ESP sincronizado pelo Wi-Fi do Bar ({wifi_ip})"
            elif wifi_ok:
                active = "wifi"
                detail = f"ESP conectado via LAN ({wifi_ip})"
            elif serial_ok:
                active = "serial"
                detail = f"ESP conectado via USB ({ser_port})"
            else:
                active = "simulator"
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
        )
        return self._last_health

    async def build_snapshot(self, refresh_hardware: bool = False) -> MachineRealtimeSnapshot:
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
        rates = {p.pump_id: p.flow_rate_ml_s for p in pumps}
        if self._iot_pending_cmd is None or self._iot_pending_cmd.command == "none":
            self._iot_pending_cmd = IotSyncResponse(command="update_pumps", pumps_rates=rates)

    async def handle_iot_sync(self, api_token: str, payload: IotSyncRequest) -> IotSyncResponse:
        """Endpoint chamado a cada ~500ms pelo ESP8266/ESP32 conectado no Wi-Fi local do bar."""
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
        row = self._load_machine_db_row()
        start_ts = time.monotonic()
        try:
            if not self._serial or not self._serial.is_open:
                ser = await asyncio.to_thread(serial.Serial, row["serial_port"], int(row["serial_baud"]), timeout=0.2)
                await asyncio.sleep(1.0)
                self._serial = ser
            assert self._serial is not None
        except SerialException as exc:
            raise RuntimeError(f"Erro na porta {row['serial_port']}: {exc}") from exc

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
    """Orquestrador global de todas as máquinas de todos os bares."""

    def __init__(self) -> None:
        self._executors: dict[str, MachineExecutor] = {}
        self._bg_task: asyncio.Task[None] | None = None

    def get_executor(self, machine_id: str, machine_slug: str) -> MachineExecutor:
        ex = self._executors.get(machine_id)
        if ex is None:
            ex = MachineExecutor(machine_id=machine_id, machine_slug=machine_slug)
            self._executors[machine_id] = ex
        else:
            ex.machine_slug = machine_slug
        return ex

    def start_background_workers(self) -> None:
        if self._bg_task is None or self._bg_task.done():
            self._bg_task = asyncio.create_task(self._maintenance_loop())

    async def stop_background_workers(self) -> None:
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass

    async def _maintenance_loop(self) -> None:
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


runtime_manager = MachineRuntimeManager()

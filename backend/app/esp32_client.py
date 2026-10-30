from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Callable, Awaitable

import httpx
import serial
import serial.tools.list_ports
from serial.serialutil import SerialException

from .catalog import load_pumps
from .config import DATA_DIR, settings
from .models import (
    ConnectionConfig,
    DoseStep,
    HardwareHealth,
    PreparationStatus,
    PumpConfig,
    PumpId,
    SystemSnapshot,
)

CONNECTION_FILE: Path = DATA_DIR / "connection.json"


class ESP32Controller:
    """Gerencia comunicação assíncrona com o ESP32 via Wi-Fi (HTTP), USB Serial ou Simulador."""

    def __init__(self) -> None:
        self._config = self._load_config()
        self._status = PreparationStatus()
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None
        self._cancel_requested = False
        self._serial: serial.Serial | None = None
        self._subscribers: set[Callable[[SystemSnapshot], Awaitable[None]]] = set()
        self._last_health = HardwareHealth(
            mode=self._config.mode,
            active_transport="disconnected",
            esp32_host=self._config.esp32_host,
            esp32_port=self._config.esp32_port,
            serial_port=self._config.serial_port,
            serial_baud=self._config.serial_baud,
        )

    def _load_config(self) -> ConnectionConfig:
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
                pass
        return default

    def save_config(self, cfg: ConnectionConfig) -> ConnectionConfig:
        self._config = cfg
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONNECTION_FILE.write_text(
            json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self._config

    @property
    def config(self) -> ConnectionConfig:
        return self._config

    @property
    def status(self) -> PreparationStatus:
        return self._status

    def subscribe(self, callback: Callable[[SystemSnapshot], Awaitable[None]]) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[SystemSnapshot], Awaitable[None]]) -> None:
        self._subscribers.discard(callback)

    async def _broadcast(self) -> None:
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
        host = (
            self._last_health.wifi_ip
            if (use_cached_ip and self._last_health.wifi_ip)
            else self._config.esp32_host
        )
        return f"http://{host}:{self._config.esp32_port}"

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        if settings.esp32_api_token:
            return {"X-Bartender-Token": settings.esp32_api_token}
        return {}

    @staticmethod
    def list_serial_ports() -> list[str]:
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    async def probe_hardware(self) -> HardwareHealth:
        ports = self.list_serial_ports()
        wifi_ok = False
        wifi_ip: str | None = None
        wifi_rssi: int | None = None
        serial_ok = False
        detail = ""

        if self._config.mode in ("auto", "wifi"):
            try:
                async with httpx.AsyncClient(timeout=3.5) as client:
                    resp = await client.get(f"{self._wifi_base_url()}/status")
                    if resp.status_code == 200:
                        data = resp.json()
                        wifi_ok = True
                        wifi_ip = data.get("ip") or self._config.esp32_host
                        wifi_rssi = data.get("rssi")
            except Exception:
                wifi_ok = False

        if self._config.mode in ("auto", "serial") and not wifi_ok:
            if self._serial and self._serial.is_open:
                serial_ok = True
            elif self._config.serial_port in ports:
                serial_ok = True

        if self._config.mode == "simulator":
            active = "simulator"
            detail = "Modo Simulador ativo — dosagem em tempo real simulada"
        elif self._config.mode == "wifi":
            active = "wifi" if wifi_ok else "disconnected"
            detail = (
                f"ESP32 conectado via Wi-Fi ({wifi_ip})"
                if wifi_ok
                else f"ESP32 não respondeu em {self._wifi_base_url()}"
            )
        elif self._config.mode == "serial":
            active = "serial" if serial_ok else "disconnected"
            detail = (
                f"Porta USB Serial {self._config.serial_port} disponível"
                if serial_ok
                else f"Porta {self._config.serial_port} não encontrada"
            )
        else:  # auto
            if wifi_ok:
                active = "wifi"
                detail = f"ESP32 online via Wi-Fi ({wifi_ip})"
            elif serial_ok:
                active = "serial"
                detail = f"ESP32 detectado na USB Serial ({self._config.serial_port})"
            else:
                active = "simulator"
                detail = "ESP32 não detectado em Wi-Fi/USB — Simulador inteligente pronto"

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
        )
        return self._last_health

    async def get_snapshot(self, refresh_hardware: bool = False) -> SystemSnapshot:
        if refresh_hardware:
            await self.probe_hardware()
        return SystemSnapshot(status=self._status, hardware=self._last_health)

    async def sync_pump_rates_to_esp32(self, pumps: dict[PumpId, PumpConfig]) -> bool:
        """Sincroniza vazões calibradas (ml/s) com a memória NVS do ESP32 quando online via Wi-Fi."""
        try:
            async with httpx.AsyncClient(timeout=2.0, headers=self._auth_headers()) as client:
                payload = {pid: cfg.flow_rate_ml_s for pid, cfg in pumps.items()}
                resp = await client.post(f"{self._wifi_base_url(use_cached_ip=True)}/config/pumps", json=payload)
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def encode_plan(steps: list[DoseStep]) -> str:
        return ",".join(f"{s.pump}:{round(s.ml, 1)}:{s.pause_ms}" for s in steps if s.ml > 0)

    async def start_dispense(self, drink_id: str, drink_name: str, steps: list[DoseStep]) -> PreparationStatus:
        if self._lock.locked() or self._status.state == "dispensing":
            raise RuntimeError("Já existe um drink sendo preparado no momento.")

        health = await self.probe_hardware()
        if health.active_transport == "disconnected":
            raise ConnectionError(health.detail or "ESP32 desconectado.")

        pumps = load_pumps()
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

        self._active_task = asyncio.create_task(
            self._run_dispense_job(drink_id, drink_name, steps, health.active_transport, pumps, total_sec)
        )
        return self._status

    async def emergency_stop(self) -> PreparationStatus:
        self._cancel_requested = True

        # Envia parada imediata ao hardware caso esteja em Wi-Fi ou Serial
        if self._status.transport == "wifi":
            try:
                async with httpx.AsyncClient(timeout=1.5, headers=self._auth_headers()) as client:
                    await client.post(f"{self._wifi_base_url(use_cached_ip=True)}/stop")
            except Exception:
                pass
        elif self._status.transport == "serial":
            await asyncio.to_thread(self._serial_write_stop)

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
        async with self._lock:
            try:
                if transport == "wifi":
                    await self._execute_wifi(drink_name, steps, pumps, total_sec)
                elif transport == "serial":
                    await self._execute_serial(drink_name, steps, pumps, total_sec)
                else:
                    await self._execute_simulator(drink_name, steps, pumps, total_sec)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
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
        plan_str = self.encode_plan(steps)
        start_ts = time.monotonic()

        base_url = self._wifi_base_url(use_cached_ip=True)
        async with httpx.AsyncClient(timeout=4.0, headers=self._auth_headers()) as client:
            resp = await client.post(
                f"{base_url}/dispense",
                json={"name": drink_name, "plan": plan_str},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"ESP32 recusou comando ({resp.status_code}): {resp.text}")

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
        start_ts = time.monotonic()

        for idx, step in enumerate(steps, start=1):
            if self._cancel_requested:
                return
            pump_cfg = pumps[step.pump]
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


esp32_controller = ESP32Controller()


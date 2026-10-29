from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalog import (
    get_catalog,
    get_drink_by_id,
    load_pumps,
    update_pump_config,
)
from .config import FRONTEND_DIST_DIR
from .esp32_client import esp32_controller
from .models import (
    ConnectionConfig,
    CustomDrinkRequest,
    DoseStep,
    DrinkRecipe,
    HardwareHealth,
    PreparationStatus,
    PumpConfig,
    PumpId,
    PumpUpdateRequest,
    SystemSnapshot,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await esp32_controller.probe_hardware()
    yield


app = FastAPI(
    title="Bartender Automático · ESP32 API",
    description="API assíncrona para controle de coquetelaria automatizada via ESP32 (Wi-Fi HTTP + USB Serial).",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/drinks", response_model=list[DrinkRecipe])
async def list_drinks() -> list[DrinkRecipe]:
    return get_catalog()


@app.get("/api/pumps", response_model=list[PumpConfig])
async def list_pumps() -> list[PumpConfig]:
    pumps = load_pumps()
    return [pumps["amarelo"], pumps["vermelho"], pumps["verde"], pumps["azul"]]


@app.put("/api/pumps/{pump_id}", response_model=PumpConfig)
async def edit_pump(pump_id: PumpId, payload: PumpUpdateRequest) -> PumpConfig:
    updated = update_pump_config(pump_id, payload)
    await esp32_controller.sync_pump_rates_to_esp32(load_pumps())
    return updated


@app.get("/api/status", response_model=SystemSnapshot)
async def get_system_status(probe: bool = False) -> SystemSnapshot:
    return await esp32_controller.get_snapshot(refresh_hardware=probe)


@app.get("/api/connection", response_model=HardwareHealth)
async def get_connection_health() -> HardwareHealth:
    return await esp32_controller.probe_hardware()


@app.put("/api/connection", response_model=HardwareHealth)
async def update_connection(cfg: ConnectionConfig) -> HardwareHealth:
    esp32_controller.save_config(cfg)
    return await esp32_controller.probe_hardware()


@app.post("/api/dispense/custom", response_model=PreparationStatus, status_code=202)
async def dispense_custom_drink(req: CustomDrinkRequest) -> PreparationStatus:
    raw_order: list[tuple[PumpId, float]] = [
        ("amarelo", req.amarelo),
        ("vermelho", req.vermelho),
        ("verde", req.verde),
        ("azul", req.azul),
    ]
    non_zero = [(pid, ml) for pid, ml in raw_order if ml > 0]
    steps: list[DoseStep] = []
    for i, (pid, ml) in enumerate(non_zero):
        is_last = i == len(non_zero) - 1
        steps.append(DoseStep(pump=pid, ml=ml, pause_ms=0 if is_last else 1200))

    try:
        return await esp32_controller.start_dispense(
            drink_id="custom",
            drink_name=req.name.strip() or "Mix Personalizado",
            steps=steps,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/dispense/{drink_id}", response_model=PreparationStatus, status_code=202)
async def dispense_preset_drink(drink_id: str) -> PreparationStatus:
    drink = get_drink_by_id(drink_id)
    if not drink:
        raise HTTPException(status_code=404, detail=f"Drink '{drink_id}' não encontrado.")
    try:
        return await esp32_controller.start_dispense(
            drink_id=drink.id,
            drink_name=drink.name,
            steps=drink.steps,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/stop", response_model=PreparationStatus)
async def stop_dispense() -> PreparationStatus:
    return await esp32_controller.emergency_stop()


@app.websocket("/api/ws")
async def websocket_status(ws: WebSocket) -> None:
    await ws.accept()
    queue: asyncio.Queue[SystemSnapshot] = asyncio.Queue(maxsize=32)

    async def on_snapshot(snap: SystemSnapshot) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(snap)

    esp32_controller.subscribe(on_snapshot)
    try:
        initial = await esp32_controller.get_snapshot(refresh_hardware=True)
        await ws.send_json(initial.model_dump())
        while True:
            snap = await queue.get()
            await ws.send_json(snap.model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        esp32_controller.unsubscribe(on_snapshot)


# Serve o build de produção do React (frontend/dist) automaticamente quando compilado
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Endpoint da API não encontrado.")
    if FRONTEND_DIST_DIR.exists():
        dist_root = FRONTEND_DIST_DIR.resolve()
        target = (dist_root / full_path).resolve()
        if full_path and target.is_relative_to(dist_root) and target.is_file():
            return FileResponse(target)
        index_file = dist_root / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
    return {
        "service": "Bartender Automático API",
        "docs": "/docs",
        "frontend_hint": "Execute 'npm run dev' ou 'npm run build' dentro de frontend/.",
    }

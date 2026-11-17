"""Aplicação principal FastAPI: Rotas REST, Streaming WebSocket e Servidor Estático SPA.

Papel na Arquitetura:
---------------------
Expõe todos os endpoints de controle do Bartender.OS v2.0 consumidos pelo painel React
(totem local, celulares na LAN ou navegador de demonstração):
  - Consulta de cardápio e calibração dinâmica das 4 bombas (`/api/drinks`, `/api/pumps`);
  - Diagnóstico e alternância quente de modo de conexão (`/api/connection`, `/api/status`);
  - Disparo assíncrono (`HTTP 202 Accepted`) de bebidas prontas ou personalizadas (`/api/dispense/*`);
  - Parada de emergência imediata (`/api/stop`);
  - Canal WebSocket (`/api/ws`) com fila limitada (`maxsize=32`, controle de backpressure)
    para sincronizar múltiplos displays ao vivo sem polling HTTP;
  - Entrega integrada dos artefatos estáticos do React (`frontend/dist`) com proteção contra
    ataques de Path Traversal (`target.is_relative_to(dist_root)`).
"""
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
    NetworkSyncResult,
    PreparationStatus,
    PumpConfig,
    PumpId,
    PumpUpdateRequest,
    SystemSnapshot,
)
from .network_discovery import get_current_network_info


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gerencia o ciclo de vida do servidor FastAPI.

    Na inicialização (startup), executa uma sondagem proativa do ESP32 (`probe_hardware`)
    para que o primeiro cliente a abrir o painel já receba imediatamente o estado real do
    transporte (Wi-Fi, USB Serial ou Simulador).
    """
    await esp32_controller.probe_hardware()
    yield


app = FastAPI(
    title="Bartender Automático · ESP32 API",
    description="API assíncrona para controle de coquetelaria automatizada via ESP32 (Wi-Fi HTTP + USB Serial).",
    version="2.0.0",
    lifespan=lifespan,
)

# Habilita CORS aberto para permitir acesso fluido tanto do Vite Dev Server (:5173)
# quanto de tablets e celulares conectados via IP da rede local em eventos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/drinks", response_model=list[DrinkRecipe])
async def list_drinks() -> list[DrinkRecipe]:
    """Lista todas as receitas do cardápio com volume total e tempo estimado recalculados."""
    return get_catalog()


@app.get("/api/pumps", response_model=list[PumpConfig])
async def list_pumps() -> list[PumpConfig]:
    """Retorna as 4 bombas na ordem canônica da bancada física (Amarela, Vermelha, Verde e Azul)."""
    pumps = load_pumps()
    return [pumps["amarelo"], pumps["vermelho"], pumps["verde"], pumps["azul"]]


@app.put("/api/pumps/{pump_id}", response_model=PumpConfig)
async def edit_pump(pump_id: PumpId, payload: PumpUpdateRequest) -> PumpConfig:
    """Atualiza o ingrediente ou a vazão (`ml/s`) de uma bomba e sincroniza com a Flash NVS do ESP32."""
    updated = update_pump_config(pump_id, payload)
    # Se o ESP32 estiver acessível via Wi-Fi, grava imediatamente as novas vazões na NVS da placa
    await esp32_controller.sync_pump_rates_to_esp32(load_pumps())
    return updated


@app.get("/api/status", response_model=SystemSnapshot)
async def get_system_status(probe: bool = False) -> SystemSnapshot:
    """Retorna o snapshot instantâneo de preparo e conectividade (`?probe=true` refaz o teste físico)."""
    return await esp32_controller.get_snapshot(refresh_hardware=probe)


@app.get("/api/connection", response_model=HardwareHealth)
async def get_connection_health() -> HardwareHealth:
    """Executa uma sondagem ativa de conectividade no ESP32 e retorna o diagnóstico detalhado."""
    return await esp32_controller.probe_hardware()


@app.put("/api/connection", response_model=HardwareHealth)
async def update_connection(cfg: ConnectionConfig) -> HardwareHealth:
    """Salva novas preferências de transporte (`connection.json`) e testa a comunicação imediatamente."""
    esp32_controller.save_config(cfg)
    return await esp32_controller.probe_hardware()


@app.get("/api/network")
async def get_network_status() -> dict[str, object]:
    """Retorna os dados da rede Wi-Fi/LAN atualmente conectada no servidor (sem exigir rede fixa)."""
    info = await asyncio.to_thread(get_current_network_info, True)
    # Remove senhas em texto claro da resposta pública por segurança
    return {
        "connected_ssid": info.get("connected_ssid"),
        "esp_target_ssid": info.get("esp_target_ssid"),
        "wifi_password_available": bool(info.get("wifi_password")),
        "primary_ip": info.get("primary_ip"),
        "lan_ips": info.get("lan_ips", []),
        "subnets": info.get("subnets", []),
        "saved_profiles_count": len(info.get("saved_profiles", [])),
    }


@app.post("/api/network/sync", response_model=NetworkSyncResult)
async def sync_current_network() -> NetworkSyncResult:
    """Puxa automaticamente a rede Wi-Fi conectada, sincroniza `secrets.h`, provisiona o ESP e varre a LAN."""
    return await esp32_controller.sync_and_discover_network()


@app.post("/api/dispense/custom", response_model=PreparationStatus, status_code=202)
async def dispense_custom_drink(req: CustomDrinkRequest) -> PreparationStatus:
    """Converte volumes personalizados das 4 bombas em um plano sequencial e inicia a dosagem.

    Mantém a ordem clássica de densidade (xaropes concentrados primeiro e base gaseificada `azul`
    por último para misturar o drink), inserindo `1200 ms` de estabilização entre bombas e `0 ms`
    após o último ingrediente.
    """
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
        # HTTP 409 Conflict: protege quando outro drink já está em preparo
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConnectionError as exc:
        # HTTP 503 Service Unavailable: hardware exigido offline nos modos estritos 'wifi'/'serial'
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/dispense/{drink_id}", response_model=PreparationStatus, status_code=202)
async def dispense_preset_drink(drink_id: str) -> PreparationStatus:
    """Inicia o preparo assíncrono de uma receita pronta do cardápio identificada por `drink_id`."""
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
    """Endpoint de Parada de Emergência: corta os relés físicos e interrompe o ciclo atual."""
    return await esp32_controller.emergency_stop()


@app.websocket("/api/ws")
async def websocket_status(ws: WebSocket) -> None:
    """Canal WebSocket em tempo real para sincronização instantânea de progresso e saúde do bar.

    Utiliza uma `asyncio.Queue(maxsize=32)` por cliente com descarte do item mais antigo caso a
    conexão Wi-Fi de um celular fique lenta (drop-oldest backpressure), garantindo que um cliente
    lento nunca atrase o loop de controle das bombas nem consuma memória ilimitada.
    """
    await ws.accept()
    queue: asyncio.Queue[SystemSnapshot] = asyncio.Queue(maxsize=32)

    async def on_snapshot(snap: SystemSnapshot) -> None:
        """Enfileira o novo estado descartando o frame mais antigo se o buffer estiver cheio."""
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(snap)

    esp32_controller.subscribe(on_snapshot)
    try:
        # Envia um snapshot completo assim que o navegador conecta
        initial = await esp32_controller.get_snapshot(refresh_hardware=True)
        await ws.send_json(initial.model_dump())
        while True:
            snap = await queue.get()
            await ws.send_json(snap.model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        # Garante remoção limpa do listener ao fechar a aba ou perder sinal Wi-Fi
        esp32_controller.unsubscribe(on_snapshot)


# Serve o build de produção do React (frontend/dist) automaticamente quando compilado
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """Serve arquivos estáticos compilados da SPA React (`frontend/dist`) e faz fallback para `index.html`.

    Segurança:
        Resolve caminhos canônicos (`resolve()`) e valida `target.is_relative_to(dist_root)`
        para bloquear tentativas de leitura de arquivos fora de `frontend/dist` (Path Traversal).
    """
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

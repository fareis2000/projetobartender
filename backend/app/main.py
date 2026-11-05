from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import (
    Principal,
    create_access_token,
    get_current_principal,
    require_superadmin,
    resolve_target_bar_id,
)
from .config import FRONTEND_DIST_DIR, settings
from .database import (
    authenticate_user,
    cancel_pending_order,
    confirm_order_payment,
    confirm_order_payment_by_external_id,
    create_bar_tenant,
    create_bottle,
    create_drink,
    create_machine,
    delete_bar_tenant,
    delete_bottle,
    delete_drink,
    get_active_customer_order,
    get_bar_analytics,
    get_bar_settings,
    get_conn,
    get_machine_pumps_with_bottles,
    get_machine_queue_stats,
    get_machine_row_by_id,
    get_machine_row_by_slug,
    get_order_by_id,
    get_platform_overview,
    init_db,
    insert_pending_order,
    list_bar_drinks,
    list_bar_machine_rows,
    list_bar_orders,
    list_bottles,
    list_drinks_for_machine,
    list_public_machines,
    mark_order_dispensing,
    mark_order_refunded,
    prepare_validated_order_draft,
    refill_pump_bottle,
    resume_or_extend_customer_turn,
    retry_failed_order,
    update_bar_settings,
    update_bar_superadmin,
    update_bottle,
    update_drink,
    update_machine,
    update_pump_slot,
)
from .machine_runtime import runtime_manager
from .models import (
    AuthTokenResponse,
    BarAnalyticsOut,
    BarCreateRequest,
    BarSettingsOut,
    BarSettingsUpdateRequest,
    BarSummaryOut,
    BarSuperAdminUpdateRequest,
    BottleCreateRequest,
    BottleOut,
    BottleUpdateRequest,
    CupConfirmationRequest,
    DrinkCreateRequest,
    DrinkOut,
    DrinkUpdateRequest,
    IotSyncRequest,
    IotSyncResponse,
    LoginRequest,
    MachineCreateRequest,
    MachineOut,
    MachinePublicContext,
    MachineRealtimeSnapshot,
    MachineUpdateRequest,
    OrderCustomCreateRequest,
    OrderOut,
    OrderPresetCreateRequest,
    PlatformOverviewOut,
    PreparationStatus,
    PrincipalOut,
    PublicMachineSummary,
    PumpId,
    PumpRefillRequest,
    PumpSlotOut,
    PumpSlotUpdateRequest,
)
from .payments import (
    check_mercadopago_payment_status,
    create_pix_charge,
    generate_qr_svg_bytes,
    refund_pix_payment,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    runtime_manager.start_background_workers()
    yield
    await runtime_manager.stop_background_workers()


app = FastAPI(
    title="Bartender.OS v3.0 · SaaS Multi-Bares & Pix",
    description="Plataforma comercial multi-bares com QR Code por máquina, Pix Dinâmico (Mercado Pago + Simulador), fila inteligente com confirmação de copo e CRUD completo de garrafas (R$/ml) e drinks.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _infer_base_url(request: Request) -> str:
    if settings.public_base_url:
        return settings.public_base_url
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8010"
    return f"{proto}://{host}"


async def _build_machine_out(m_row, base_url: str, probe: bool = False) -> MachineOut:
    machine_id = m_row["id"]
    slug = m_row["slug"]
    ex = runtime_manager.get_executor(machine_id, slug)
    snap = await ex.build_snapshot(refresh_hardware=probe)
    return MachineOut(
        id=machine_id,
        bar_id=m_row["bar_id"],
        slug=slug,
        name=m_row["name"],
        api_token=m_row["api_token"],
        qr_url=f"{base_url}/m/{slug}",
        cup_fee_cents=int(m_row["cup_fee_cents"]),
        min_order_cents=int(m_row["min_order_cents"]),
        max_cup_ml=int(m_row["max_cup_ml"]),
        allow_custom_builder=bool(m_row["allow_custom_builder"]),
        connection_mode=m_row["connection_mode"],
        esp32_host=m_row["esp32_host"],
        esp32_port=int(m_row["esp32_port"]),
        serial_port=m_row["serial_port"],
        serial_baud=int(m_row["serial_baud"]),
        pumps=snap.pumps,
        hardware=snap.hardware,
        status=snap.status,
        queue_length=snap.queue_length,
    )


# ======================== AUTHENTICATION ========================

@app.post("/api/auth/login", response_model=AuthTokenResponse)
async def login(payload: LoginRequest) -> AuthTokenResponse:
    principal = authenticate_user(payload.email, payload.password)
    token = create_access_token(principal)
    return AuthTokenResponse(
        access_token=token,
        user=PrincipalOut(
            sub=principal.sub,
            email=principal.email,
            role=principal.role,
            bar_id=principal.bar_id,
            bar_name=principal.bar_name,
        ),
    )


@app.get("/api/auth/me", response_model=PrincipalOut)
async def me(principal: Principal = Depends(get_current_principal)) -> PrincipalOut:
    return PrincipalOut(
        sub=principal.sub,
        email=principal.email,
        role=principal.role,
        bar_id=principal.bar_id,
        bar_name=principal.bar_name,
    )


# ======================== PUBLIC CUSTOMER QR & PIX FLOW ========================

@app.get("/api/public/machines", response_model=list[PublicMachineSummary])
async def get_public_machines_directory() -> list[PublicMachineSummary]:
    return list_public_machines()


@app.get("/api/public/m/{machine_slug}", response_model=MachinePublicContext)
async def get_public_machine_context(
    machine_slug: str,
    session_id: str | None = Query(default=None),
) -> MachinePublicContext:
    m_row = get_machine_row_by_slug(machine_slug)
    machine_id = m_row["id"]
    bar_id = m_row["bar_id"]

    ex = runtime_manager.get_executor(machine_id, machine_slug)
    snap = await ex.build_snapshot(refresh_hardware=False)
    drinks = list_drinks_for_machine(bar_id, machine_id, only_active=True)
    active_order = get_active_customer_order(machine_id, session_id)

    effective_provider = (
        "mercadopago"
        if m_row["payment_provider"] == "mercadopago" and str(m_row["mp_access_token"] or "").strip()
        else "simulated"
    )

    return MachinePublicContext(
        bar_name=m_row["bar_name"],
        bar_slug=m_row["bar_slug"],
        payment_provider=effective_provider,
        machine_id=machine_id,
        machine_slug=machine_slug,
        machine_name=m_row["name"],
        cup_fee_cents=int(m_row["cup_fee_cents"]),
        min_order_cents=int(m_row["min_order_cents"]),
        max_cup_ml=int(m_row["max_cup_ml"]),
        allow_custom_builder=bool(m_row["allow_custom_builder"]),
        pumps=snap.pumps,
        drinks=drinks,
        status=snap.status,
        hardware=snap.hardware,
        queue_length=snap.queue_length,
        ready_order_number=snap.ready_order_number,
        active_customer_order=active_order,
    )


@app.get("/api/public/m/{machine_slug}/qr.svg")
async def download_machine_qr_svg(machine_slug: str, request: Request) -> Response:
    get_machine_row_by_slug(machine_slug)
    target_url = f"{_infer_base_url(request)}/m/{machine_slug}"
    svg_bytes = generate_qr_svg_bytes(target_url, scale=10)
    return Response(content=svg_bytes, media_type="image/svg+xml")


@app.post("/api/public/m/{machine_slug}/orders/preset", response_model=OrderOut, status_code=201)
async def create_preset_drink_order(
    machine_slug: str,
    req: OrderPresetCreateRequest,
    request: Request,
) -> OrderOut:
    m_row, draft = prepare_validated_order_draft(
        machine_slug=machine_slug,
        customer_session_id=req.customer_session_id,
        customer_name=req.customer_name,
        drink_id=req.drink_id,
        custom_name=None,
        custom_volumes=None,
    )
    try:
        pix = await create_pix_charge(
            provider=m_row["payment_provider"],
            mp_access_token=m_row["mp_access_token"],
            order_id=str(draft["id"]),
            order_number=int(draft["order_number"]),  # type: ignore[arg-type]
            bar_id=str(draft["bar_id"]),
            bar_name=m_row["bar_name"],
            drink_name=str(draft["drink_name"]),
            amount_cents=int(draft["total_cents"]),  # type: ignore[arg-type]
            platform_fee_cents=int(draft["platform_fee_cents"]),  # type: ignore[arg-type]
            expiration_seconds=settings.pix_expiration_seconds,
            public_base_url=_infer_base_url(request),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return insert_pending_order(
        draft,
        pix.provider,
        pix.external_id,
        pix.qr_code_text,
        pix.qr_code_data_uri,
        pix.expires_at_iso,
    )


@app.post("/api/public/m/{machine_slug}/orders/custom", response_model=OrderOut, status_code=201)
async def create_custom_drink_order(
    machine_slug: str,
    req: OrderCustomCreateRequest,
    request: Request,
) -> OrderOut:
    m_row, draft = prepare_validated_order_draft(
        machine_slug=machine_slug,
        customer_session_id=req.customer_session_id,
        customer_name=req.customer_name,
        drink_id=None,
        custom_name=req.name,
        custom_volumes={
            "amarelo": req.amarelo,
            "vermelho": req.vermelho,
            "verde": req.verde,
            "azul": req.azul,
        },
    )
    try:
        pix = await create_pix_charge(
            provider=m_row["payment_provider"],
            mp_access_token=m_row["mp_access_token"],
            order_id=str(draft["id"]),
            order_number=int(draft["order_number"]),  # type: ignore[arg-type]
            bar_id=str(draft["bar_id"]),
            bar_name=m_row["bar_name"],
            drink_name=str(draft["drink_name"]),
            amount_cents=int(draft["total_cents"]),  # type: ignore[arg-type]
            platform_fee_cents=int(draft["platform_fee_cents"]),  # type: ignore[arg-type]
            expiration_seconds=settings.pix_expiration_seconds,
            public_base_url=_infer_base_url(request),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return insert_pending_order(
        draft,
        pix.provider,
        pix.external_id,
        pix.qr_code_text,
        pix.qr_code_data_uri,
        pix.expires_at_iso,
    )


@app.get("/api/public/orders/{order_id}", response_model=OrderOut)
async def get_public_order_status(order_id: str) -> OrderOut:
    ord_out = get_order_by_id(order_id)
    # Se for Mercado Pago pendente, aproveita a consulta ao voltar do app do banco p/ checar imediatamente
    if ord_out.status == "PENDING_PAYMENT" and ord_out.payment_provider == "mercadopago" and ord_out.payment_external_id:
        with get_conn() as conn:
            b_row = conn.execute("SELECT mp_access_token FROM bars WHERE id = ?", (ord_out.bar_id,)).fetchone()
        if b_row and b_row["mp_access_token"]:
            st = await check_mercadopago_payment_status(b_row["mp_access_token"], ord_out.payment_external_id)
            if st == "approved":
                ord_out, changed = confirm_order_payment(order_id)
                if changed:
                    ex = runtime_manager.get_executor(ord_out.machine_id, ord_out.machine_slug)
                    await ex.broadcast()
    return ord_out


@app.post("/api/public/orders/{order_id}/simulate-pay", response_model=OrderOut)
async def simulate_pix_approval(order_id: str) -> OrderOut:
    ord_out = get_order_by_id(order_id)
    if ord_out.payment_provider != "simulated":
        raise HTTPException(
            status_code=403,
            detail="Aprovação simulada só é permitida quando o bar está em Modo Pix Simulado.",
        )
    confirmed, _ = confirm_order_payment(order_id)
    ex = runtime_manager.get_executor(confirmed.machine_id, confirmed.machine_slug)
    await ex.broadcast()
    return confirmed


@app.post("/api/public/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order_endpoint(
    order_id: str,
    customer_session_id: str = Query(...),
) -> OrderOut:
    return cancel_pending_order(order_id, customer_session_id)


@app.post("/api/public/orders/{order_id}/resume-turn", response_model=OrderOut)
async def resume_order_turn_endpoint(
    order_id: str,
    customer_session_id: str = Query(...),
) -> OrderOut:
    updated = resume_or_extend_customer_turn(order_id, customer_session_id)
    ex = runtime_manager.get_executor(updated.machine_id, updated.machine_slug)
    await ex.broadcast()
    return updated


@app.post("/api/public/orders/{order_id}/confirm-cup-and-dispense", response_model=OrderOut)
async def confirm_cup_and_start_dispense(order_id: str, req: CupConfirmationRequest) -> OrderOut:
    if not req.cup_on_platform_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme que o copo já está posicionado na plataforma antes de iniciar o preparo.",
        )

    ord_info = get_order_by_id(order_id)
    ex = runtime_manager.get_executor(ord_info.machine_id, ord_info.machine_slug)

    if ex.status.state == "dispensing":
        raise HTTPException(status_code=409, detail="Aguarde o preparo atual finalizar na máquina.")

    dispensing_ord = mark_order_dispensing(order_id, req.customer_session_id)
    try:
        await ex.start_order_dispense(
            order_id=dispensing_ord.id,
            order_number=dispensing_ord.order_number,
            drink_id=dispensing_ord.drink_id,
            drink_name=dispensing_ord.drink_name,
            steps=dispensing_ord.steps,
        )
    except (RuntimeError, ConnectionError) as exc:
        # Se a máquina falhar ao iniciar, devolve para a fila sem perder o pagamento do cliente!
        with get_conn() as conn:
            conn.execute("UPDATE orders SET status = 'READY_FOR_CUP' WHERE id = ?", (order_id,))
        await ex.broadcast()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return get_order_by_id(order_id)


# ======================== WEBHOOK MERCADO PAGO ========================

@app.post("/api/webhooks/mercadopago/{bar_id}")
async def mercadopago_webhook(bar_id: str, request: Request) -> dict[str, object]:
    body: dict[str, object] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    data_obj = body.get("data") if isinstance(body.get("data"), dict) else {}
    payment_id = str(
        (data_obj or {}).get("id")
        or request.query_params.get("data.id")
        or request.query_params.get("id")
        or ""
    ).strip()

    if not payment_id:
        return {"received": True, "action": "ignored"}

    with get_conn() as conn:
        b_row = conn.execute("SELECT mp_access_token FROM bars WHERE id = ?", (bar_id,)).fetchone()
    if not b_row or not b_row["mp_access_token"]:
        return {"received": True, "action": "bar_without_token"}

    # Confirma autenticidade consultando diretamente a API oficial do Mercado Pago
    mp_status = await check_mercadopago_payment_status(b_row["mp_access_token"], payment_id)
    if mp_status == "approved":
        ord_out, changed = confirm_order_payment_by_external_id(bar_id, payment_id)
        if ord_out and changed:
            ex = runtime_manager.get_executor(ord_out.machine_id, ord_out.machine_slug)
            await ex.broadcast()
        return {"received": True, "action": "approved"}

    return {"received": True, "mp_status": mp_status}


# ======================== IOT MACHINE SYNC (ESP8266 / ESP32 NO WI-FI DO BAR) ========================

@app.post("/api/iot/{machine_slug}/sync", response_model=IotSyncResponse)
async def iot_machine_sync(
    machine_slug: str,
    payload: IotSyncRequest,
    x_machine_token: str = Header(default=""),
) -> IotSyncResponse:
    m_row = get_machine_row_by_slug(machine_slug)
    ex = runtime_manager.get_executor(m_row["id"], machine_slug)
    return await ex.handle_iot_sync(x_machine_token, payload)


# ======================== BAR OWNER ADMIN CRUD ========================

@app.get("/api/bar/settings", response_model=BarSettingsOut)
async def bar_get_settings(
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BarSettingsOut:
    return get_bar_settings(bar_id, _infer_base_url(request))


@app.put("/api/bar/settings", response_model=BarSettingsOut)
async def bar_put_settings(
    req: BarSettingsUpdateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BarSettingsOut:
    return update_bar_settings(bar_id, req, _infer_base_url(request))


# --- Bottles CRUD ---

@app.get("/api/bar/bottles", response_model=list[BottleOut])
async def bar_list_bottles(bar_id: str = Depends(resolve_target_bar_id)) -> list[BottleOut]:
    return list_bottles(bar_id)


@app.post("/api/bar/bottles", response_model=BottleOut, status_code=201)
async def bar_create_bottle(
    req: BottleCreateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BottleOut:
    return create_bottle(bar_id, req)


@app.put("/api/bar/bottles/{bottle_id}", response_model=BottleOut)
async def bar_update_bottle(
    bottle_id: str,
    req: BottleUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BottleOut:
    updated = update_bottle(bar_id, bottle_id, req)
    for m_row in list_bar_machine_rows(bar_id):
        await runtime_manager.get_executor(m_row["id"], m_row["slug"]).broadcast()
    return updated


@app.delete("/api/bar/bottles/{bottle_id}", status_code=204)
async def bar_delete_bottle(
    bottle_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> Response:
    delete_bottle(bar_id, bottle_id)
    for m_row in list_bar_machine_rows(bar_id):
        await runtime_manager.get_executor(m_row["id"], m_row["slug"]).broadcast()
    return Response(status_code=204)


# --- Drinks Full CRUD ---

@app.get("/api/bar/drinks", response_model=list[DrinkOut])
async def bar_get_drinks(bar_id: str = Depends(resolve_target_bar_id)) -> list[DrinkOut]:
    return list_bar_drinks(bar_id)


@app.post("/api/bar/drinks", response_model=DrinkOut, status_code=201)
async def bar_post_drink(
    req: DrinkCreateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> DrinkOut:
    return create_drink(bar_id, req)


@app.put("/api/bar/drinks/{drink_id}", response_model=DrinkOut)
async def bar_put_drink(
    drink_id: str,
    req: DrinkUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> DrinkOut:
    return update_drink(bar_id, drink_id, req)


@app.delete("/api/bar/drinks/{drink_id}", status_code=204)
async def bar_remove_drink(
    drink_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> Response:
    delete_drink(bar_id, drink_id)
    return Response(status_code=204)


# --- Machines & 4 Pumps ---

@app.get("/api/bar/machines", response_model=list[MachineOut])
async def bar_get_machines(
    request: Request,
    probe: bool = False,
    bar_id: str = Depends(resolve_target_bar_id),
) -> list[MachineOut]:
    base = _infer_base_url(request)
    rows = list_bar_machine_rows(bar_id)
    return [await _build_machine_out(r, base, probe=probe) for r in rows]


@app.post("/api/bar/machines", response_model=MachineOut, status_code=201)
async def bar_post_machine(
    req: MachineCreateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MachineOut:
    row = create_machine(bar_id, req)
    return await _build_machine_out(row, _infer_base_url(request), probe=False)


@app.put("/api/bar/machines/{machine_id}", response_model=MachineOut)
async def bar_put_machine(
    machine_id: str,
    req: MachineUpdateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MachineOut:
    row = update_machine(bar_id, machine_id, req)
    return await _build_machine_out(row, _infer_base_url(request), probe=True)


@app.put("/api/bar/machines/{machine_id}/pumps/{pump_id}", response_model=list[PumpSlotOut])
async def bar_put_pump_slot(
    machine_id: str,
    pump_id: PumpId,
    req: PumpSlotUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> list[PumpSlotOut]:
    m_row = get_machine_row_by_id(bar_id, machine_id)
    pumps = update_pump_slot(bar_id, machine_id, pump_id, req)
    ex = runtime_manager.get_executor(machine_id, m_row["slug"])
    ex.queue_pump_rates_sync(pumps)
    await ex.broadcast()
    return pumps


@app.post("/api/bar/machines/{machine_id}/pumps/{pump_id}/refill", response_model=list[PumpSlotOut])
async def bar_post_pump_refill(
    machine_id: str,
    pump_id: PumpId,
    req: PumpRefillRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> list[PumpSlotOut]:
    m_row = get_machine_row_by_id(bar_id, machine_id)
    pumps = refill_pump_bottle(bar_id, machine_id, pump_id, req.remaining_ml)
    ex = runtime_manager.get_executor(machine_id, m_row["slug"])
    await ex.broadcast()
    return pumps


@app.post("/api/bar/machines/{machine_id}/stop", response_model=PreparationStatus)
async def bar_emergency_stop_machine(
    machine_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> PreparationStatus:
    m_row = get_machine_row_by_id(bar_id, machine_id)
    ex = runtime_manager.get_executor(machine_id, m_row["slug"])
    return await ex.emergency_stop()


# --- Orders & Analytics ---

@app.get("/api/bar/orders", response_model=list[OrderOut])
async def bar_get_orders(bar_id: str = Depends(resolve_target_bar_id)) -> list[OrderOut]:
    return list_bar_orders(bar_id)


@app.get("/api/bar/analytics", response_model=BarAnalyticsOut)
async def bar_get_analytics_summary(bar_id: str = Depends(resolve_target_bar_id)) -> BarAnalyticsOut:
    return get_bar_analytics(bar_id)


@app.post("/api/bar/orders/{order_id}/refund", response_model=OrderOut)
async def bar_refund_order(
    order_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> OrderOut:
    ord_out, provider, mp_tok, ext_id = mark_order_refunded(bar_id, order_id)
    try:
        await refund_pix_payment(provider, mp_tok, ext_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    ex = runtime_manager.get_executor(ord_out.machine_id, ord_out.machine_slug)
    await ex.broadcast()
    return ord_out


@app.post("/api/bar/orders/{order_id}/retry", response_model=OrderOut)
async def bar_retry_failed_order_endpoint(
    order_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> OrderOut:
    ord_out = retry_failed_order(bar_id, order_id)
    ex = runtime_manager.get_executor(ord_out.machine_id, ord_out.machine_slug)
    await ex.broadcast()
    return ord_out


# ======================== SUPER-ADMIN MULTI-BAR ENDPOINTS ========================

@app.get("/api/superadmin/overview", response_model=PlatformOverviewOut)
async def superadmin_overview(_: Principal = Depends(require_superadmin)) -> PlatformOverviewOut:
    return get_platform_overview()


@app.post("/api/superadmin/bars", response_model=BarSummaryOut, status_code=201)
async def superadmin_create_bar(
    req: BarCreateRequest,
    _: Principal = Depends(require_superadmin),
) -> BarSummaryOut:
    return create_bar_tenant(req)


@app.put("/api/superadmin/bars/{bar_id}", response_model=BarSummaryOut)
async def superadmin_update_bar(
    bar_id: str,
    req: BarSuperAdminUpdateRequest,
    _: Principal = Depends(require_superadmin),
) -> BarSummaryOut:
    return update_bar_superadmin(bar_id, req)


@app.delete("/api/superadmin/bars/{bar_id}", status_code=204)
async def superadmin_delete_bar(
    bar_id: str,
    _: Principal = Depends(require_superadmin),
) -> Response:
    delete_bar_tenant(bar_id)
    return Response(status_code=204)


# ======================== REALTIME WEBSOCKET POR MÁQUINA ========================

@app.websocket("/api/ws/machines/{machine_slug}")
async def websocket_machine_status(ws: WebSocket, machine_slug: str) -> None:
    try:
        m_row = get_machine_row_by_slug(machine_slug)
    except HTTPException:
        await ws.close(code=1008)
        return

    await ws.accept()
    ex = runtime_manager.get_executor(m_row["id"], machine_slug)
    queue: asyncio.Queue[MachineRealtimeSnapshot] = asyncio.Queue(maxsize=32)

    async def on_snap(snap: MachineRealtimeSnapshot) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(snap)

    ex.subscribe(on_snap)
    try:
        initial = await ex.build_snapshot(refresh_hardware=False)
        await ws.send_json(initial.model_dump())
        while True:
            snap = await queue.get()
            await ws.send_json(snap.model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        ex.unsubscribe(on_snap)


# ======================== SERVE REACT SPA ========================

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
        "service": "Bartender.OS v3.0 · SaaS Multi-Bares & Pix",
        "docs": "/docs",
        "default_machine_qr": "/m/maq-01",
        "bar_owner_panel": "/painel",
        "superadmin_panel": "/superadmin",
    }

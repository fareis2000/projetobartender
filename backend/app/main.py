""" Controlador Principal da API FastAPI e Servidor SPA — Bartender.OS v3.0 SaaS.

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Expõe todos os contratos HTTP REST, Webhooks financeiros, sincronização Cloud IoT e canais
WebSocket em tempo real da plataforma Multi-Bares, organizados em 6 camadas claras:

1. **Autenticação Unificada (`/api/auth/*`):**
   - Login único que identifica automaticamente `superadmin` ou `bar_owner` e emite JWT.
2. **Jornada Pública Mobile do Cliente (`/api/public/*`):**
   - Acesso instantâneo via QR Code (`/m/{machine_slug}`) sem login e sem instalar aplicativo,
     criação de pedidos de cardápio ou personalizados (`R$/ml`), Pix Copia e Cola, fila virtual,
     retomada de turno pausado (`resume-turn`) e trava obrigatória de confirmação de copo.
3. **Webhook Oficial Mercado Pago (`/api/webhooks/mercadopago/{bar_id}`):**
   - Recebe notificações assíncronas de pagamento Pix por bar e valida autenticidade na fonte.
4. **Cloud Sync IoT Outbound (`/api/iot/{machine_slug}/sync`):**
   - Canal leve para placas `ESP8266`/`ESP32` operarem apenas com o Wi-Fi 2.4 GHz do bar.
5. **Painel do Dono do Bar (`/api/bar/*`) & Painel Super-Admin (`/api/superadmin/*`):**
   - CRUD completo e isolado por `bar_id` para garrafas, receitas, máquinas, bombas, estornos
     Pix em 1 clique, parada de emergência e gestão multi-tenant com `%` de Split SaaS.
6. **WebSocket Tempo Real (`/api/ws/machines/{machine_slug}`) & Entrega SPA React:**
   - Atualizações push sub-segundo e roteamento `history fallback` seguro contra *Path Traversal*.
"""
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
from .config import FRONTEND_DIST_DIR, PROJECT_ROOT, settings
from .network_discovery import (
    get_current_network_info,
    get_primary_lan_ip,
    sync_secrets_h_with_current_network,
)
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
    get_bar_mp_access_token,
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
    MpTokenTestOut,
    MpTokenTestRequest,
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
    cancel_mercadopago_payment,
    check_mercadopago_payment_status,
    create_pix_charge,
    generate_qr_svg_bytes,
    refund_pix_payment,
    validate_mp_access_token_format,
    verify_mercadopago_token,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gerencia inicialização do banco SQLite (DDL + seeds) e workers assíncronos de manutenção."""
    init_db()
    try:
        lan_ip = get_primary_lan_ip()
        with get_conn() as conn:
            m_row = conn.execute("SELECT slug, api_token FROM machines ORDER BY created_at ASC LIMIT 1").fetchone()
        if m_row:
            sync_url = f"http://{lan_ip}:8010/api/iot/{m_row['slug']}/sync"
            sync_secrets_h_with_current_network(
                PROJECT_ROOT / "bombas" / "secrets.h",
                api_token=str(m_row["api_token"] or ""),
                cloud_sync_url=sync_url,
            )
    except Exception:
        pass
    runtime_manager.start_background_workers()
    yield
    await runtime_manager.stop_background_workers()


app = FastAPI(
    title="Bartender.OS v3.0 · SaaS Multi-Bares & Pix",
    description="Plataforma comercial multi-bares com QR Code por máquina, Pix Dinâmico (Mercado Pago + Simulador), fila inteligente com confirmação de copo e CRUD completo de garrafas (R$/ml) e drinks.",
    version="3.0.0",
    lifespan=lifespan,
)

# Habilita CORS para desenvolvimento local (Vite dev server) e integrações externas autorizadas
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _infer_base_url(request: Request) -> str:
    """Resolve a URL pública base respeitando `PUBLIC_BASE_URL` ou cabeçalhos de proxy reverso (`X-Forwarded-*`).

    Se o painel for aberto via `localhost` ou `127.0.0.1`, substitui automaticamente o hostname pelo IP
    IPv4 real da rede Wi-Fi/LAN atualmente conectada (`get_primary_lan_ip()`), garantindo que os QR Codes
    de balcão e a URL de Cloud Sync do ESP32/ESP8266 funcionem imediatamente em qualquer celular ou rede!
    """
    if settings.public_base_url:
        return settings.public_base_url
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8010"
    host_only, _, port_part = host.partition(":")
    if host_only.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
        lan_ip = get_primary_lan_ip()
        if lan_ip and not lan_ip.startswith("127."):
            host = f"{lan_ip}:{port_part}" if port_part else lan_ip
    return f"{proto}://{host}"


async def _build_machine_out(m_row, base_url: str, probe: bool = False) -> MachineOut:
    """Combina o registro SQLite da máquina com seu snapshot de runtime (bombas, fila e saúde IoT)."""
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
    """Autentica um Super-Admin da plataforma ou Dono de Bar e retorna o token JWT `HS256`."""
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
    """Valida o token Bearer atual e devolve os dados do perfil logado para restauração de sessão."""
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
    """Lista todas as máquinas públicas de estabelecimentos ativos na plataforma."""
    return list_public_machines()


@app.get("/api/public/m/{machine_slug}", response_model=MachinePublicContext)
async def get_public_machine_context(
    machine_slug: str,
    session_id: str | None = Query(default=None),
) -> MachinePublicContext:
    """Retorna o cardápio vivo, preços `R$/ml`, estoque das 4 bombas e pedido ativo do celular do cliente.

    Chamada automaticamente quando o cliente escaneia o QR Code da máquina (`/m/{machine_slug}`)
    e também quando retorna do aplicativo do banco (`visibilitychange`), restaurando sua posição
    na fila através do `session_id` persistido no `localStorage` do navegador!
    """
    m_row = get_machine_row_by_slug(machine_slug)
    machine_id = m_row["id"]
    bar_id = m_row["bar_id"]

    ex = runtime_manager.get_executor(machine_id, machine_slug)
    snap = await ex.build_snapshot(refresh_hardware=False)
    drinks = list_drinks_for_machine(bar_id, machine_id, only_active=True)
    active_order = get_active_customer_order(machine_id, session_id)

    effective_provider = (
        "mercadopago"
        if m_row["payment_provider"] == "mercadopago"
        and validate_mp_access_token_format(str(m_row["mp_access_token"] or ""))[0]
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
    """Gera e disponibiliza para download a arte vetorial `.svg` do QR Code exclusivo da máquina."""
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
    """Cria pedido a partir de um drink pronto do cardápio, validando estoque e gerando cobrança Pix."""
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
    """Cria pedido personalizado por mililitro ('Monte seu Drink'), precificando cada bomba em tempo real."""
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
    """Consulta o status atualizado de um pedido e força conciliação imediata se for Mercado Pago pendente."""
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
    """Simula a aprovação instantânea do pagamento Pix (disponível exclusivamente em `simulated`)."""
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
    """Permite ao próprio cliente cancelar uma cobrança Pix ainda não paga (`PENDING_PAYMENT`)."""
    cancelled = cancel_pending_order(order_id, customer_session_id)
    if cancelled.payment_provider == "mercadopago" and cancelled.payment_external_id:
        mp_tok = get_bar_mp_access_token(cancelled.bar_id)
        await cancel_mercadopago_payment(mp_tok, cancelled.payment_external_id)
    return cancelled


@app.post("/api/public/orders/{order_id}/resume-turn", response_model=OrderOut)
async def resume_order_turn_endpoint(
    order_id: str,
    customer_session_id: str = Query(...),
) -> OrderOut:
    """Reativa prioritariamente no topo da fila um pedido pago que entrou em espera protegida (`PAUSED_TURN`)."""
    updated = resume_or_extend_customer_turn(order_id, customer_session_id)
    ex = runtime_manager.get_executor(updated.machine_id, updated.machine_slug)
    await ex.broadcast()
    return updated


@app.post("/api/public/orders/{order_id}/confirm-cup-and-dispense", response_model=OrderOut)
async def confirm_cup_and_start_dispense(order_id: str, req: CupConfirmationRequest) -> OrderOut:
    """Trava Crítica Anti-Desperdício: exige confirmação do copo na plataforma e aciona as bombas da máquina.

    Proteções de Negócio e Segurança:
    1. Recusa imediatamente (`400`) se `cup_on_platform_confirmed` não for `True`.
    2. Impede furar fila (`409`): apenas o pedido na posição #1 (`READY_FOR_CUP`) e pertencente
       ao mesmo `customer_session_id` consegue iniciar a dosagem.
    3. Proteção Financeira: se o hardware estiver momentaneamente desconectado ao tentar partir,
       restaura o pedido para `READY_FOR_CUP` sem jamais perder o crédito já pago pelo cliente!
    """
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
    """Recebe notificações Webhook do Mercado Pago, valida autenticidade na API oficial e libera a fila."""
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
    """Endpoint de sincronização contínua outbound acionado pelo microcontrolador ESP no Wi-Fi do bar."""
    m_row = get_machine_row_by_slug(machine_slug)
    ex = runtime_manager.get_executor(m_row["id"], machine_slug)
    return await ex.handle_iot_sync(x_machine_token, payload)


# ======================== BAR OWNER ADMIN CRUD ========================

@app.get("/api/bar/settings", response_model=BarSettingsOut)
async def bar_get_settings(
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BarSettingsOut:
    """Obtém as configurações de recebimento Pix e dados cadastrais do bar autenticado."""
    return get_bar_settings(bar_id, _infer_base_url(request))


@app.put("/api/bar/settings", response_model=BarSettingsOut)
async def bar_put_settings(
    req: BarSettingsUpdateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BarSettingsOut:
    """Atualiza modo Pix (`simulated` vs `mercadopago`), Access Token, segredo Webhook ou senha do bar."""
    return update_bar_settings(bar_id, req, _infer_base_url(request))


@app.post("/api/bar/settings/test-mercadopago", response_model=MpTokenTestOut)
async def bar_test_mercadopago(
    req: MpTokenTestRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MpTokenTestOut:
    """Valida ao vivo um Access Token rascunho ou já salvo consultando a API oficial do Mercado Pago."""
    candidate = (req.mp_access_token or "").strip() or get_bar_mp_access_token(bar_id)
    try:
        info = await verify_mercadopago_token(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    env_label = "Modo Teste (TEST-)" if info["is_test"] else "Produção Real (APP_USR-)"
    return MpTokenTestOut(
        ok=True,
        account_id=str(info["account_id"]),
        nickname=str(info["nickname"]),
        email=str(info["email"]),
        first_name=str(info["first_name"]),
        is_test=bool(info["is_test"]),
        message=f"Conectado com sucesso à conta Mercado Pago de {info['first_name']} ({env_label})!",
    )


# --- Bottles CRUD ---

@app.get("/api/bar/bottles", response_model=list[BottleOut])
async def bar_list_bottles(bar_id: str = Depends(resolve_target_bar_id)) -> list[BottleOut]:
    """Lista todas as garrafas cadastradas no estoque do bar com métricas de lucro e `R$/ml`."""
    return list_bottles(bar_id)


@app.post("/api/bar/bottles", response_model=BottleOut, status_code=201)
async def bar_create_bottle(
    req: BottleCreateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BottleOut:
    """Cadastra uma nova garrafa/insumo no catálogo do estabelecimento."""
    return create_bottle(bar_id, req)


@app.put("/api/bar/bottles/{bottle_id}", response_model=BottleOut)
async def bar_update_bottle(
    bottle_id: str,
    req: BottleUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> BottleOut:
    """Edita preço `R$/ml`, custo, volume ou cor de uma garrafa e atualiza vitrines via WebSocket."""
    updated = update_bottle(bar_id, bottle_id, req)
    for m_row in list_bar_machine_rows(bar_id):
        await runtime_manager.get_executor(m_row["id"], m_row["slug"]).broadcast()
    return updated


@app.delete("/api/bar/bottles/{bottle_id}", status_code=204)
async def bar_delete_bottle(
    bottle_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> Response:
    """Remove uma garrafa do catálogo (desvinculando-a automaticamente de bombas via `ON DELETE SET NULL`)."""
    delete_bottle(bar_id, bottle_id)
    for m_row in list_bar_machine_rows(bar_id):
        await runtime_manager.get_executor(m_row["id"], m_row["slug"]).broadcast()
    return Response(status_code=204)


# --- Drinks Full CRUD ---

@app.get("/api/bar/drinks", response_model=list[DrinkOut])
async def bar_get_drinks(bar_id: str = Depends(resolve_target_bar_id)) -> list[DrinkOut]:
    """Lista todas as receitas do cardápio do bar (ativas e pausadas) com cálculo de margem."""
    return list_bar_drinks(bar_id)


@app.post("/api/bar/drinks", response_model=DrinkOut, status_code=201)
async def bar_post_drink(
    req: DrinkCreateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> DrinkOut:
    """Cria uma nova receita de drink no cardápio do bar."""
    return create_drink(bar_id, req)


@app.put("/api/bar/drinks/{drink_id}", response_model=DrinkOut)
async def bar_put_drink(
    drink_id: str,
    req: DrinkUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> DrinkOut:
    """Atualiza etapas em `ml`, precificação (`auto_ml` ou `fixed`), desconto ou status ativo do drink."""
    return update_drink(bar_id, drink_id, req)


@app.delete("/api/bar/drinks/{drink_id}", status_code=204)
async def bar_remove_drink(
    drink_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> Response:
    """Exclui permanentemente uma receita do cardápio do bar (inclusive drinks iniciais de demonstração)."""
    delete_drink(bar_id, drink_id)
    return Response(status_code=204)


# --- Machines & 4 Pumps ---

@app.get("/api/bar/machines", response_model=list[MachineOut])
async def bar_get_machines(
    request: Request,
    probe: bool = False,
    bar_id: str = Depends(resolve_target_bar_id),
) -> list[MachineOut]:
    """Lista todas as máquinas do bar, suas 4 bombas, QR Code e credenciais de sincronização IoT."""
    base = _infer_base_url(request)
    rows = list_bar_machine_rows(bar_id)
    return [await _build_machine_out(r, base, probe=probe) for r in rows]


@app.post("/api/bar/machines", response_model=MachineOut, status_code=201)
async def bar_post_machine(
    req: MachineCreateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MachineOut:
    """Adiciona uma nova máquina de autosserviço ao bar gerando token IoT exclusivo e 4 bombas."""
    row = create_machine(bar_id, req)
    return await _build_machine_out(row, _infer_base_url(request), probe=False)


@app.put("/api/bar/machines/{machine_id}", response_model=MachineOut)
async def bar_put_machine(
    machine_id: str,
    req: MachineUpdateRequest,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MachineOut:
    """Atualiza taxa de copo, pedido mínimo, volume máximo de segurança ou modo de conexão da máquina."""
    row = update_machine(bar_id, machine_id, req)
    return await _build_machine_out(row, _infer_base_url(request), probe=True)


@app.post("/api/bar/machines/{machine_id}/discover", response_model=MachineOut)
async def bar_discover_machine_network(
    machine_id: str,
    request: Request,
    bar_id: str = Depends(resolve_target_bar_id),
) -> MachineOut:
    """Puxa automaticamente a rede Wi-Fi conectada, atualiza `secrets.h`, provisiona o ESP e varre a LAN."""
    m_row = get_machine_row_by_id(bar_id, machine_id)
    base_url = _infer_base_url(request)
    ex = runtime_manager.get_executor(machine_id, m_row["slug"])
    await ex.sync_and_discover_network(base_url)
    fresh_row = get_machine_row_by_id(bar_id, machine_id)
    return await _build_machine_out(fresh_row, base_url, probe=False)


@app.get("/api/network")
async def get_network_status() -> dict[str, object]:
    """Retorna os metadados da rede Wi-Fi/LAN atualmente conectada no servidor."""
    info = await asyncio.to_thread(get_current_network_info, True)
    return {
        "connected_ssid": info.get("connected_ssid"),
        "esp_target_ssid": info.get("esp_target_ssid"),
        "wifi_password_available": bool(info.get("wifi_password")),
        "primary_ip": info.get("primary_ip"),
        "lan_ips": info.get("lan_ips", []),
        "subnets": info.get("subnets", []),
        "saved_profiles_count": len(info.get("saved_profiles", [])),
    }


@app.put("/api/bar/machines/{machine_id}/pumps/{pump_id}", response_model=list[PumpSlotOut])
async def bar_put_pump_slot(
    machine_id: str,
    pump_id: PumpId,
    req: PumpSlotUpdateRequest,
    bar_id: str = Depends(resolve_target_bar_id),
) -> list[PumpSlotOut]:
    """Troca a garrafa espetada na bomba ou calibra sua vazão (`ml/s`), sincronizando OTA com o ESP."""
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
    """Restaura em 1 clique o volume cheio da garrafa instalada na bomba após reposição física."""
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
    """Corta imediatamente o acionamento das 4 bombas da máquina (Parada de Emergência Remota)."""
    m_row = get_machine_row_by_id(bar_id, machine_id)
    ex = runtime_manager.get_executor(machine_id, m_row["slug"])
    return await ex.emergency_stop()


# --- Orders & Analytics ---

@app.get("/api/bar/orders", response_model=list[OrderOut])
async def bar_get_orders(bar_id: str = Depends(resolve_target_bar_id)) -> list[OrderOut]:
    """Retorna o histórico recente de pedidos, fila e status Pix do estabelecimento."""
    return list_bar_orders(bar_id)


@app.get("/api/bar/analytics", response_model=BarAnalyticsOut)
async def bar_get_analytics_summary(bar_id: str = Depends(resolve_target_bar_id)) -> BarAnalyticsOut:
    """Retorna faturamento bruto, custo de insumos consumidos, split da plataforma e lucro líquido real."""
    return get_bar_analytics(bar_id)


@app.post("/api/bar/orders/{order_id}/refund", response_model=OrderOut)
async def bar_refund_order(
    order_id: str,
    bar_id: str = Depends(resolve_target_bar_id),
) -> OrderOut:
    """Executa o estorno Pix automático (Mercado Pago ou Simulado) e retira o pedido da fila."""
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
    """Reinsere na fila (`PAID_QUEUED`) um pedido interrompido por falha de hardware (`FAILED_DISPENSE`)."""
    ord_out = retry_failed_order(bar_id, order_id)
    ex = runtime_manager.get_executor(ord_out.machine_id, ord_out.machine_slug)
    await ex.broadcast()
    return ord_out


# ======================== SUPER-ADMIN MULTI-BAR ENDPOINTS ========================

@app.get("/api/superadmin/overview", response_model=PlatformOverviewOut)
async def superadmin_overview(_: Principal = Depends(require_superadmin)) -> PlatformOverviewOut:
    """Painel executivo da rede SaaS com métricas consolidadas de todos os bares clientes."""
    return get_platform_overview()


@app.post("/api/superadmin/bars", response_model=BarSummaryOut, status_code=201)
async def superadmin_create_bar(
    req: BarCreateRequest,
    _: Principal = Depends(require_superadmin),
) -> BarSummaryOut:
    """Provisiona um novo bar cliente (tenant isolado) já com sua primeira máquina e token IoT."""
    return create_bar_tenant(req)


@app.put("/api/superadmin/bars/{bar_id}", response_model=BarSummaryOut)
async def superadmin_update_bar(
    bar_id: str,
    req: BarSuperAdminUpdateRequest,
    _: Principal = Depends(require_superadmin),
) -> BarSummaryOut:
    """Altera taxa `%` de split da plataforma, credenciais do proprietário ou suspende/reativa um bar."""
    return update_bar_superadmin(bar_id, req)


@app.delete("/api/superadmin/bars/{bar_id}", status_code=204)
async def superadmin_delete_bar(
    bar_id: str,
    _: Principal = Depends(require_superadmin),
) -> Response:
    """Remove um tenant da plataforma com limpeza referencial completa em cascata (`ON DELETE CASCADE`)."""
    delete_bar_tenant(bar_id)
    return Response(status_code=204)


# ======================== REALTIME WEBSOCKET POR MÁQUINA ========================

@app.websocket("/api/ws/machines/{machine_slug}")
async def websocket_machine_status(ws: WebSocket, machine_slug: str) -> None:
    """Canal WebSocket pub/sub por máquina com fila limitada (`maxsize=32`, *drop-oldest* anti-backpressure)."""
    try:
        m_row = get_machine_row_by_slug(machine_slug)
    except HTTPException:
        await ws.close(code=1008)
        return

    await ws.accept()
    ex = runtime_manager.get_executor(m_row["id"], machine_slug)
    queue: asyncio.Queue[MachineRealtimeSnapshot] = asyncio.Queue(maxsize=32)

    async def on_snap(snap: MachineRealtimeSnapshot) -> None:
        # Se a internet móvel do cliente oscilar e a fila encher, descarta o frame antigo priorizando o mais recente
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
    """Serve os assets estáticos da SPA React (`frontend/dist`) com proteção contra *Path Traversal*.

    Qualquer rota visual do cliente (`/m/maq-01`, `/painel`, `/superadmin`) faz fallback para
    `index.html`, enquanto rotas inexistentes sob `api/` retornam `404 JSON` explícito.
    """
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Endpoint da API não encontrado.")
    if FRONTEND_DIST_DIR.exists():
        dist_root = FRONTEND_DIST_DIR.resolve()
        target = (dist_root / full_path).resolve()
        # Garante que `target` permaneça estritamente dentro de `frontend/dist`
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

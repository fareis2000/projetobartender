"""Modelos de Domínio e Contratos de API (Pydantic v2) — Bartender.OS v3.0 SaaS.

Função Arquitetural e Diferenciais Comerciais:
----------------------------------------------
Define todos os esquemas tipados de entrada (`Request`) e saída (`Out`/`Response`) da API
FastAPI, garantindo validação rigorosa em tempo de execução, documentação OpenAPI/Swagger
automática (`/docs`) e integridade financeira/física:

1. **Precisão Monetária em Centavos Inteiros (`*_cents`):**
   - Todos os valores financeiros (preço por litro, custo da garrafa, taxa de copo/gelo,
     subtotal, comissão SaaS da plataforma e líquido do bar) trafegam em centavos inteiros,
     eliminando discrepâncias de arredondamento IEEE 754 em transações Pix.
2. **Ciclo de Vida Completo da Fila Virtual (`OrderStatus`):**
   - Modela os 10 estados operacionais do pedido, incluindo a trava anti-desperdício
     `READY_FOR_CUP` (confirmação obrigatória de copo na plataforma) e `PAUSED_TURN`
     (espera protegida quando o cliente demora >75s, sem perder o pagamento nem travar a fila).
3. **Validação Física Anti-Transbordo e Anti-Fraude:**
   - Restringe volumes mínimos (`>= 10 ml`), limites por etapa (`<= 500 ml`), vazões de
     calibração (`1.0` a `200.0 ml/s`) e padrões de slugs para QR Codes imprimíveis.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

# Identificadores canônicos das 4 bombas peristálticas/diafragma por máquina
PumpId = Literal["amarelo", "vermelho", "verde", "azul"]

# Modos de transporte suportados entre o Backend SaaS e o controlador físico da máquina:
# - "cloud_iot": ESP8266/ESP32 conecta no Wi-Fi 2.4 GHz do bar e faz polling outbound HTTPS/HTTP
# - "auto": Detecta automaticamente Cloud IoT -> Wi-Fi LAN -> USB Serial -> Simulador
# - "wifi": Servidor backend faz requisições HTTP diretas na LAN local da placa ESP
# - "serial": Comunicação direta via cabo USB (115200 bps)
# - "simulator": Simulador volumétrico virtual em tempo real para demonstrações comerciais sem hardware
ConnectionMode = Literal["cloud_iot", "auto", "wifi", "serial", "simulator"]

# Estado físico instantâneo do executor de preparo da máquina
PrepState = Literal["idle", "dispensing", "completed", "stopped", "error"]

# Provedor de liquidação Pix configurado pelo estabelecimento
PaymentProvider = Literal["simulated", "mercadopago"]

# Estratégia comercial de precificação de cada receita do cardápio:
# - "auto_ml": Soma automática dos ml de cada garrafa + taxa de copo - desconto percentual
# - "fixed": Preço fechado promocional ou psicológico definido manualmente pelo dono do bar
DrinkPricingMode = Literal["auto_ml", "fixed"]

# Máquina de estados completa de um pedido comercial com pagamento Pix e fila inteligente:
# - PENDING_PAYMENT: QR Code Pix gerado, aguardando pagamento do cliente (estoque ainda não reservado)
# - PAID_QUEUED: Pix aprovado! Pedido garantido aguardando vez na fila da máquina (estoque reservado)
# - READY_FOR_CUP: Vez do cliente! Janela de 75s aberta exigindo confirmação de copo na plataforma
# - PAUSED_TURN: Cliente não confirmou o copo em 75s; pedido fica salvo em espera protegida liberando a fila
# - DISPENSING: Copo confirmado e bombas físicas/simuladas servindo a bebida neste instante
# - COMPLETED: Bebida entregue com sucesso e volume abatido definitivamente das garrafas
# - FAILED_DISPENSE: Interrupção/erro de hardware durante o preparo (permite reenvio ou estorno no painel)
# - EXPIRED: Tempo de pagamento Pix esgotado sem confirmação bancária
# - CANCELED: Cancelado voluntariamente pelo cliente antes de pagar
# - REFUNDED: Valor devolvido integralmente ao cliente via API de estorno Pix
OrderStatus = Literal[
    "PENDING_PAYMENT",
    "PAID_QUEUED",
    "READY_FOR_CUP",
    "PAUSED_TURN",
    "DISPENSING",
    "COMPLETED",
    "FAILED_DISPENSE",
    "EXPIRED",
    "CANCELED",
    "REFUNDED",
]

# Ordem determinística de apresentação e montagem das bombas (insumos concentrados -> base/mixer no final)
PUMP_IDS_ORDERED: list[PumpId] = ["amarelo", "vermelho", "verde", "azul"]


# ======================== AUTH ========================

class LoginRequest(BaseModel):
    """Credenciais enviadas pelos painéis `/painel` (Dono do Bar) e `/superadmin`."""

    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=3, max_length=120)


class PrincipalOut(BaseModel):
    """Dados públicos da sessão autenticada retornados ao frontend."""

    sub: str
    email: str
    role: Literal["superadmin", "bar_owner"]
    bar_id: str | None = None
    bar_name: str | None = None


class AuthTokenResponse(BaseModel):
    """Resposta de autenticação bem-sucedida contendo o Bearer Token JWT e perfil do usuário."""

    access_token: str
    token_type: str = "bearer"
    user: PrincipalOut


# ======================== SUPERADMIN / MULTI-BAR ========================

class BarCreateRequest(BaseModel):
    """Payload de onboarding B2B para provisionar um novo bar cliente e sua primeira máquina IoT."""

    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    owner_name: str = Field(min_length=2, max_length=80)
    owner_email: str = Field(min_length=5, max_length=120)
    owner_password: str = Field(min_length=4, max_length=120)
    # Percentual de Split/Comissão da plataforma SaaS sobre cada venda aprovada (0% a 50%)
    platform_fee_percent: float = Field(default=0.0, ge=0.0, le=50.0)
    initial_machine_name: str = Field(default="Máquina Principal #01", min_length=2, max_length=60)
    initial_machine_slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")


class BarSuperAdminUpdateRequest(BaseModel):
    """Atualização administrativa de cadastro, status ativo/suspenso ou taxa de split de um bar."""

    name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_email: str | None = Field(default=None, min_length=5, max_length=120)
    owner_password: str | None = Field(default=None, min_length=4, max_length=120)
    active: bool | None = None
    platform_fee_percent: float | None = Field(default=None, ge=0.0, le=50.0)


class BarSummaryOut(BaseModel):
    """Resumo gerencial e financeiro de um tenant (bar) listado no painel Super-Admin."""

    id: str
    name: str
    slug: str
    owner_name: str
    owner_email: str
    active: bool
    payment_provider: PaymentProvider
    has_mp_token: bool
    platform_fee_percent: float
    machines_count: int = 0
    paid_orders_count: int = 0
    gross_revenue_cents: int = 0
    platform_fees_cents: int = 0
    created_at: str


class PlatformOverviewOut(BaseModel):
    """Visão consolidada de toda a rede SaaS (GMV total, comissões da plataforma e lista de bares)."""

    total_bars: int
    active_bars: int
    total_machines: int
    total_paid_orders: int
    total_gross_cents: int
    total_platform_fees_cents: int
    bars: list[BarSummaryOut]


# ======================== BAR SETTINGS & PAYMENT ========================

class BarSettingsOut(BaseModel):
    """Configurações operacionais e status seguro (mascarado) das chaves Pix do estabelecimento."""

    id: str
    name: str
    slug: str
    owner_name: str
    owner_email: str
    payment_provider: PaymentProvider
    has_mp_token: bool
    # Token exibido parcialmente mascarado (ex: APP_USR-••••••••1234) para nunca vazar segredo na UI
    mp_token_masked: str
    mp_webhook_secret_configured: bool
    platform_fee_percent: float
    public_base_url: str


class BarSettingsUpdateRequest(BaseModel):
    """Requisição do dono do bar para configurar Mercado Pago Oficial, Simulador ou trocar senha."""

    name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_name: str | None = Field(default=None, min_length=2, max_length=80)
    payment_provider: PaymentProvider | None = None
    mp_access_token: str | None = None
    mp_webhook_secret: str | None = None
    new_password: str | None = Field(default=None, min_length=4, max_length=120)


class MpTokenTestRequest(BaseModel):
    """Payload opcional para testar um Access Token Mercado Pago antes ou depois de salvar no banco."""

    mp_access_token: str | None = None


class MpTokenTestOut(BaseModel):
    """Resultado do diagnóstico ao vivo da conta Mercado Pago conectada ao estabelecimento."""

    ok: bool
    account_id: str
    nickname: str
    email: str
    first_name: str
    is_test: bool
    message: str


# ======================== BOTTLES CRUD (R$/ml) ========================

class BottleCreateRequest(BaseModel):
    """Criação de insumo/garrafa no estoque do bar com engenharia de custo, perda e preço por litro.

    Nota Comercial:
    Armazenar `price_per_liter_cents` (centavos por 1.000 ml) permite representar frações sub-centavo
    por mililitro com precisão inteira (ex: Água com Gás a `R$ 18,00/L` = `1800` centavos/L = `R$ 0,018/ml`).
    """

    name: str = Field(min_length=2, max_length=70)
    description: str = Field(default="", max_length=160)
    color_hex: str = Field(default="#f97316", pattern=r"^#[0-9a-fA-F]{6}$")
    is_alcoholic: bool = False
    is_mixer: bool = False
    bottle_volume_ml: float = Field(gt=50, le=20000)
    cost_cents: int = Field(default=0, ge=0, le=10_000_000)
    # Percentual técnico de perda por purga de mangueira/fundo de garrafa (0% a 35%)
    loss_pct: float = Field(default=3.0, ge=0.0, le=35.0)
    price_per_liter_cents: int = Field(gt=0, le=50_000_000)


class BottleUpdateRequest(BaseModel):
    """Atualização parcial dos atributos comerciais, visuais ou de custo/preço de uma garrafa."""

    name: str | None = Field(default=None, min_length=2, max_length=70)
    description: str | None = Field(default=None, max_length=160)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_alcoholic: bool | None = None
    is_mixer: bool | None = None
    bottle_volume_ml: float | None = Field(default=None, gt=50, le=20000)
    cost_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    loss_pct: float | None = Field(default=None, ge=0.0, le=35.0)
    price_per_liter_cents: int | None = Field(default=None, gt=0, le=50_000_000)


class BottleOut(BaseModel):
    """Representação enriquecida da garrafa com indicadores automáticos de rentabilidade e lucro."""

    id: str
    bar_id: str
    name: str
    description: str
    color_hex: str
    is_alcoholic: bool
    is_mixer: bool
    bottle_volume_ml: float
    usable_volume_ml: float
    cost_cents: int
    loss_pct: float
    price_per_liter_cents: int
    price_per_ml_cents_float: float
    dose_50ml_cents: int
    estimated_bottle_revenue_cents: int
    estimated_bottle_profit_cents: int
    installed_in_pumps: int = 0
    created_at: str


# ======================== MACHINES & PUMPS ========================

class PumpSlotOut(BaseModel):
    """Estado detalhado de uma das 4 bombas da máquina, unindo calibração física, garrafa e estoque vivo."""

    pump_id: PumpId
    label: str
    gpio: int
    flow_rate_ml_s: float
    remaining_ml: float
    min_reserve_ml: float
    # Volume efetivamente vendável neste instante (remaining_ml - min_reserve_ml - pedidos pagos na fila)
    available_ml: float
    bottle_id: str | None = None
    ingredient: str
    description: str
    color_hex: str
    is_alcoholic: bool = False
    is_mixer: bool = False
    bottle_volume_ml: float = 1000.0
    price_per_liter_cents: int = 0
    price_per_10ml_cents: float = 0.0


class PumpSlotUpdateRequest(BaseModel):
    """Vinculação de garrafa do estoque a uma bomba, ajuste fino de vazão (`ml/s`) ou reserva mínima."""

    bottle_id: str | None = None
    flow_rate_ml_s: float | None = Field(default=None, gt=1.0, le=200.0)
    remaining_ml: float | None = Field(default=None, ge=0.0, le=20000.0)
    min_reserve_ml: float | None = Field(default=None, ge=0.0, le=1000.0)


class PumpRefillRequest(BaseModel):
    """Comando rápido de troca/reabastecimento de garrafa cheia na bomba (1 clique no painel)."""

    remaining_ml: float | None = Field(default=None, gt=0.0, le=20000.0)


class HardwareHealth(BaseModel):
    """Diagnóstico em tempo real da conectividade física/IoT da placa controladora ESP8266/ESP32."""

    mode: ConnectionMode
    active_transport: Literal["cloud_iot", "wifi", "serial", "simulator", "disconnected"]
    wifi_reachable: bool = False
    wifi_ip: str | None = None
    wifi_rssi: int | None = None
    serial_connected: bool = False
    available_serial_ports: list[str] = []
    esp32_host: str
    esp32_port: int
    serial_port: str
    serial_baud: int
    iot_online: bool = False
    last_seen_seconds_ago: float | None = None
    detail: str = ""


class PreparationStatus(BaseModel):
    """Telemetria instantânea do preparo em andamento transmitida via WebSocket para celular e painel."""

    state: PrepState = "idle"
    order_id: str | None = None
    order_number: int | None = None
    drink_id: str | None = None
    drink_name: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    current_pump: PumpId | None = None
    current_step_index: int = 0
    total_steps: int = 0
    message: str = "Pronto para preparar seu próximo drink"
    transport: Literal["cloud_iot", "wifi", "serial", "simulator"] | None = None
    elapsed_seconds: float = 0.0
    total_seconds: float = 0.0


class MachineCreateRequest(BaseModel):
    """Cadastro de uma nova estação/máquina de autosserviço vinculada ao bar."""

    name: str = Field(min_length=2, max_length=60)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    cup_fee_cents: int = Field(default=0, ge=0, le=10000)
    min_order_cents: int = Field(default=300, ge=100, le=50000)
    max_cup_ml: int = Field(default=450, ge=100, le=1000)
    allow_custom_builder: bool = True
    connection_mode: ConnectionMode = "auto"


class MachineUpdateRequest(BaseModel):
    """Atualização de regras comerciais da máquina (taxa de copo, pedido mínimo, limite ml) e transporte."""

    name: str | None = Field(default=None, min_length=2, max_length=60)
    cup_fee_cents: int | None = Field(default=None, ge=0, le=10000)
    min_order_cents: int | None = Field(default=None, ge=100, le=50000)
    max_cup_ml: int | None = Field(default=None, ge=100, le=1000)
    allow_custom_builder: bool | None = None
    connection_mode: ConnectionMode | None = None
    esp32_host: str | None = None
    esp32_port: int | None = Field(default=None, ge=1, le=65535)
    serial_port: str | None = None
    serial_baud: int | None = None


class MachineOut(BaseModel):
    """Visão administrativa completa de uma máquina, incluindo credencial `api_token` IoT e URL do QR Code."""

    id: str
    bar_id: str
    slug: str
    name: str
    api_token: str
    qr_url: str
    cup_fee_cents: int
    min_order_cents: int
    max_cup_ml: int
    allow_custom_builder: bool
    connection_mode: ConnectionMode
    esp32_host: str
    esp32_port: int
    serial_port: str
    serial_baud: int
    pumps: list[PumpSlotOut]
    hardware: HardwareHealth
    status: PreparationStatus
    queue_length: int = 0


# ======================== DRINKS CRUD ========================

class DoseStep(BaseModel):
    """Etapa atômica de uma receita: qual bomba acionar, quantos `ml` dosar e pausa de estabilização."""

    pump: PumpId
    ml: float = Field(gt=0, le=500)
    pause_ms: int = Field(default=1000, ge=0, le=10000)


class DrinkCreateRequest(BaseModel):
    """Criação de drink autoral ou clássico no cardápio do bar, com suporte a preço automático por `ml` ou fixo."""

    name: str = Field(min_length=2, max_length=60)
    subtitle: str = Field(default="Receita Exclusiva da Casa", max_length=90)
    description: str = Field(default="", max_length=280)
    category: str = Field(default="Clássicos da Casa", min_length=2, max_length=50)
    badge: str = Field(default="Especial", max_length=35)
    accent_from: str = Field(default="#ea580c", pattern=r"^#[0-9a-fA-F]{6}$")
    accent_to: str = Field(default="#f97316", pattern=r"^#[0-9a-fA-F]{6}$")
    glass_color: str = Field(default="#f97316", pattern=r"^#[0-9a-fA-F]{6}$")
    pricing_mode: DrinkPricingMode = "auto_ml"
    fixed_price_cents: int = Field(default=1500, ge=100, le=500_000)
    discount_pct: float = Field(default=0.0, ge=0.0, le=90.0)
    active: bool = True
    steps: list[DoseStep] = Field(min_length=1, max_length=8)


class DrinkUpdateRequest(BaseModel):
    """Edição flexível de drink existente no cardápio (nome, cores, etapas, modo de preço ou pausa de venda)."""

    name: str | None = Field(default=None, min_length=2, max_length=60)
    subtitle: str | None = Field(default=None, max_length=90)
    description: str | None = Field(default=None, max_length=280)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    badge: str | None = Field(default=None, max_length=35)
    accent_from: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    accent_to: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    glass_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    pricing_mode: DrinkPricingMode | None = None
    fixed_price_cents: int | None = Field(default=None, ge=100, le=500_000)
    discount_pct: float | None = Field(default=None, ge=0.0, le=90.0)
    active: bool | None = None
    steps: list[DoseStep] | None = Field(default=None, min_length=1, max_length=8)


class DrinkOut(BaseModel):
    """Drink calculado dinamicamente para uma máquina específica (preço em tempo real, lucro e disponibilidade)."""

    id: str
    bar_id: str
    name: str
    subtitle: str
    description: str
    category: str
    badge: str
    accent_from: str
    accent_to: str
    glass_color: str
    pricing_mode: DrinkPricingMode
    fixed_price_cents: int
    discount_pct: float
    active: bool
    steps: list[DoseStep]
    total_ml: float = 0.0
    estimated_seconds: float = 0.0
    raw_ml_price_cents: int = 0
    final_price_cents: int = 0
    estimated_cost_cents: int = 0
    estimated_profit_cents: int = 0
    is_alcoholic: bool = False
    # Bloqueia compra automaticamente no cardápio se faltar garrafa ou ml suficiente em qualquer bomba!
    available: bool = True
    unavailable_reason: str | None = None


# ======================== CUSTOMER QR & ORDERS ========================

class OrderItemBreakdown(BaseModel):
    """Detalhamento contábil e volumétrico congelado por ingrediente no momento da criação do pedido."""

    pump: PumpId
    bottle_id: str | None = None
    ingredient: str
    color_hex: str
    ml: float
    price_cents: int
    cost_cents: int


class OrderPresetCreateRequest(BaseModel):
    """Criação de pedido pelo celular do cliente a partir de uma receita pronta do cardápio."""

    drink_id: str
    customer_session_id: str = Field(min_length=6, max_length=80)
    customer_name: str = Field(default="", max_length=40)


class OrderCustomCreateRequest(BaseModel):
    """Criação de pedido no construtor livre ('Monte seu Drink por ml') no celular do cliente."""

    name: str = Field(default="Meu Drink Personalizado", min_length=1, max_length=45)
    customer_session_id: str = Field(min_length=6, max_length=80)
    customer_name: str = Field(default="", max_length=40)
    amarelo: float = Field(default=0, ge=0, le=500)
    vermelho: float = Field(default=0, ge=0, le=500)
    verde: float = Field(default=0, ge=0, le=500)
    azul: float = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def validate_minimum(self) -> "OrderCustomCreateRequest":
        """Garante volume mínimo de 10 ml somando todas as bombas para evitar acionamentos irrelevantes."""
        total = self.amarelo + self.vermelho + self.verde + self.azul
        if total < 10:
            raise ValueError("Selecione pelo menos 10 ml no total para preparar o drink.")
        return self


class CupConfirmationRequest(BaseModel):
    """Confirmação explícita obrigatória de que o cliente posicionou o copo físico sob os bicos."""

    customer_session_id: str = Field(min_length=6, max_length=80)
    cup_on_platform_confirmed: bool


class OrderOut(BaseModel):
    """Estado completo do pedido, cobrança Pix, posição na fila virtual e decomposição financeira."""

    id: str
    order_number: int
    bar_id: str
    machine_id: str
    machine_slug: str
    machine_name: str
    customer_session_id: str
    customer_name: str
    drink_id: str | None = None
    drink_name: str
    is_custom: bool
    is_alcoholic: bool
    steps: list[DoseStep]
    items: list[OrderItemBreakdown]
    total_ml: float
    subtotal_cents: int
    cup_fee_cents: int
    total_cents: int
    cost_total_cents: int = 0
    platform_fee_cents: int = 0
    bar_net_cents: int = 0
    status: OrderStatus
    queue_position: int = 0
    seconds_until_pix_expiry: int = 0
    seconds_until_turn_expiry: int = 0
    payment_provider: PaymentProvider
    payment_external_id: str | None = None
    pix_qr_code: str = ""
    pix_qr_base64: str = ""
    created_at: str
    paid_at: str | None = None
    completed_at: str | None = None


class PublicMachineSummary(BaseModel):
    """Resumo público enxuto para listagem/diretório de máquinas ativas."""

    slug: str
    name: str
    bar_name: str


class MachinePublicContext(BaseModel):
    """Payload completo carregado quando o cliente escaneia o QR Code `/m/{machine_slug}` no 4G/5G."""

    bar_name: str
    bar_slug: str
    payment_provider: PaymentProvider
    machine_id: str
    machine_slug: str
    machine_name: str
    cup_fee_cents: int
    min_order_cents: int
    max_cup_ml: int
    allow_custom_builder: bool
    pumps: list[PumpSlotOut]
    drinks: list[DrinkOut]
    status: PreparationStatus
    hardware: HardwareHealth
    queue_length: int
    ready_order_number: int | None = None
    active_customer_order: OrderOut | None = None


class MachineRealtimeSnapshot(BaseModel):
    """Frame leve enviado em tempo real pelo WebSocket `/api/ws/machines/{machine_slug}`."""

    machine_slug: str
    status: PreparationStatus
    hardware: HardwareHealth
    queue_length: int
    ready_order_id: str | None = None
    ready_order_number: int | None = None
    pumps: list[PumpSlotOut]


# ======================== ANALYTICS & IOT ========================

class BarAnalyticsOut(BaseModel):
    """Indicadores financeiros consolidados (DRE operacional em tempo real) do painel do dono do bar."""

    paid_orders_count: int
    completed_orders_count: int
    pending_orders_count: int
    refunded_orders_count: int
    gross_revenue_cents: int
    total_cost_cents: int
    platform_fees_cents: int
    net_profit_cents: int
    total_ml_dispensed: float


class IotSyncRequest(BaseModel):
    """Batimento de telemetria enviado a cada `450ms–800ms` pelo firmware ESP8266/ESP32 via HTTP POST."""

    state: str = "idle"
    progress: int = 0
    current_pump: str = ""
    step: int = 0
    total_steps: int = 0
    ip: str = ""
    rssi: int = 0
    device: str = "ESP"


class IotSyncResponse(BaseModel):
    """Comando descendente retornado pela nuvem ao ESP8266/ESP32 na resposta do batimento `/sync`."""

    ok: bool = True
    command: Literal["none", "dispense", "stop", "update_pumps"] = "none"
    order_id: str | None = None
    drink_name: str | None = None
    plan: str | None = None
    pumps_rates: dict[str, float] | None = None

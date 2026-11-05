from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

PumpId = Literal["amarelo", "vermelho", "verde", "azul"]
ConnectionMode = Literal["cloud_iot", "auto", "wifi", "serial", "simulator"]
PrepState = Literal["idle", "dispensing", "completed", "stopped", "error"]
PaymentProvider = Literal["simulated", "mercadopago"]
DrinkPricingMode = Literal["auto_ml", "fixed"]
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

PUMP_IDS_ORDERED: list[PumpId] = ["amarelo", "vermelho", "verde", "azul"]


# ======================== AUTH ========================

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=3, max_length=120)


class PrincipalOut(BaseModel):
    sub: str
    email: str
    role: Literal["superadmin", "bar_owner"]
    bar_id: str | None = None
    bar_name: str | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: PrincipalOut


# ======================== SUPERADMIN / MULTI-BAR ========================

class BarCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    owner_name: str = Field(min_length=2, max_length=80)
    owner_email: str = Field(min_length=5, max_length=120)
    owner_password: str = Field(min_length=4, max_length=120)
    platform_fee_percent: float = Field(default=0.0, ge=0.0, le=50.0)
    initial_machine_name: str = Field(default="Máquina Principal #01", min_length=2, max_length=60)
    initial_machine_slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")


class BarSuperAdminUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_email: str | None = Field(default=None, min_length=5, max_length=120)
    owner_password: str | None = Field(default=None, min_length=4, max_length=120)
    active: bool | None = None
    platform_fee_percent: float | None = Field(default=None, ge=0.0, le=50.0)


class BarSummaryOut(BaseModel):
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
    total_bars: int
    active_bars: int
    total_machines: int
    total_paid_orders: int
    total_gross_cents: int
    total_platform_fees_cents: int
    bars: list[BarSummaryOut]


# ======================== BAR SETTINGS & PAYMENT ========================

class BarSettingsOut(BaseModel):
    id: str
    name: str
    slug: str
    owner_name: str
    owner_email: str
    payment_provider: PaymentProvider
    has_mp_token: bool
    mp_token_masked: str
    mp_webhook_secret_configured: bool
    platform_fee_percent: float
    public_base_url: str


class BarSettingsUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    owner_name: str | None = Field(default=None, min_length=2, max_length=80)
    payment_provider: PaymentProvider | None = None
    mp_access_token: str | None = None
    mp_webhook_secret: str | None = None
    new_password: str | None = Field(default=None, min_length=4, max_length=120)


# ======================== BOTTLES CRUD (R$/ml) ========================

class BottleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=70)
    description: str = Field(default="", max_length=160)
    color_hex: str = Field(default="#f97316", pattern=r"^#[0-9a-fA-F]{6}$")
    is_alcoholic: bool = False
    is_mixer: bool = False
    bottle_volume_ml: float = Field(gt=50, le=20000)
    cost_cents: int = Field(default=0, ge=0, le=10_000_000)
    loss_pct: float = Field(default=3.0, ge=0.0, le=35.0)
    price_per_liter_cents: int = Field(gt=0, le=50_000_000)


class BottleUpdateRequest(BaseModel):
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
    pump_id: PumpId
    label: str
    gpio: int
    flow_rate_ml_s: float
    remaining_ml: float
    min_reserve_ml: float
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
    bottle_id: str | None = None
    flow_rate_ml_s: float | None = Field(default=None, gt=1.0, le=200.0)
    remaining_ml: float | None = Field(default=None, ge=0.0, le=20000.0)
    min_reserve_ml: float | None = Field(default=None, ge=0.0, le=1000.0)


class PumpRefillRequest(BaseModel):
    remaining_ml: float | None = Field(default=None, gt=0.0, le=20000.0)


class HardwareHealth(BaseModel):
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
    name: str = Field(min_length=2, max_length=60)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    cup_fee_cents: int = Field(default=0, ge=0, le=10000)
    min_order_cents: int = Field(default=300, ge=100, le=50000)
    max_cup_ml: int = Field(default=450, ge=100, le=1000)
    allow_custom_builder: bool = True
    connection_mode: ConnectionMode = "auto"


class MachineUpdateRequest(BaseModel):
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
    pump: PumpId
    ml: float = Field(gt=0, le=500)
    pause_ms: int = Field(default=1000, ge=0, le=10000)


class DrinkCreateRequest(BaseModel):
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
    available: bool = True
    unavailable_reason: str | None = None


# ======================== CUSTOMER QR & ORDERS ========================

class OrderItemBreakdown(BaseModel):
    pump: PumpId
    bottle_id: str | None = None
    ingredient: str
    color_hex: str
    ml: float
    price_cents: int
    cost_cents: int


class OrderPresetCreateRequest(BaseModel):
    drink_id: str
    customer_session_id: str = Field(min_length=6, max_length=80)
    customer_name: str = Field(default="", max_length=40)


class OrderCustomCreateRequest(BaseModel):
    name: str = Field(default="Meu Drink Personalizado", min_length=1, max_length=45)
    customer_session_id: str = Field(min_length=6, max_length=80)
    customer_name: str = Field(default="", max_length=40)
    amarelo: float = Field(default=0, ge=0, le=500)
    vermelho: float = Field(default=0, ge=0, le=500)
    verde: float = Field(default=0, ge=0, le=500)
    azul: float = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def validate_minimum(self) -> "OrderCustomCreateRequest":
        total = self.amarelo + self.vermelho + self.verde + self.azul
        if total < 10:
            raise ValueError("Selecione pelo menos 10 ml no total para preparar o drink.")
        return self


class CupConfirmationRequest(BaseModel):
    customer_session_id: str = Field(min_length=6, max_length=80)
    cup_on_platform_confirmed: bool


class OrderOut(BaseModel):
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
    slug: str
    name: str
    bar_name: str


class MachinePublicContext(BaseModel):
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
    machine_slug: str
    status: PreparationStatus
    hardware: HardwareHealth
    queue_length: int
    ready_order_id: str | None = None
    ready_order_number: int | None = None
    pumps: list[PumpSlotOut]


# ======================== ANALYTICS & IOT ========================

class BarAnalyticsOut(BaseModel):
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
    state: str = "idle"
    progress: int = 0
    current_pump: str = ""
    step: int = 0
    total_steps: int = 0
    ip: str = ""
    rssi: int = 0
    device: str = "ESP"


class IotSyncResponse(BaseModel):
    ok: bool = True
    command: Literal["none", "dispense", "stop", "update_pumps"] = "none"
    order_id: str | None = None
    drink_name: str | None = None
    plan: str | None = None
    pumps_rates: dict[str, float] | None = None

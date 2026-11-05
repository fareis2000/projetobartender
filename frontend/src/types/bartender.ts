export type PumpId = 'amarelo' | 'vermelho' | 'verde' | 'azul';
export type ConnectionMode = 'cloud_iot' | 'auto' | 'wifi' | 'serial' | 'simulator';
export type PrepState = 'idle' | 'dispensing' | 'completed' | 'stopped' | 'error';
export type PaymentProvider = 'simulated' | 'mercadopago';
export type DrinkPricingMode = 'auto_ml' | 'fixed';

export type OrderStatus =
  | 'PENDING_PAYMENT'
  | 'PAID_QUEUED'
  | 'READY_FOR_CUP'
  | 'PAUSED_TURN'
  | 'DISPENSING'
  | 'COMPLETED'
  | 'FAILED_DISPENSE'
  | 'EXPIRED'
  | 'CANCELED'
  | 'REFUNDED';

export interface PrincipalUser {
  sub: string;
  email: string;
  role: 'superadmin' | 'bar_owner';
  bar_id: string | null;
  bar_name: string | null;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: PrincipalUser;
}

export interface Bottle {
  id: string;
  bar_id: string;
  name: string;
  description: string;
  color_hex: string;
  is_alcoholic: boolean;
  is_mixer: boolean;
  bottle_volume_ml: number;
  usable_volume_ml: number;
  cost_cents: number;
  loss_pct: number;
  price_per_liter_cents: number;
  price_per_ml_cents_float: number;
  dose_50ml_cents: number;
  estimated_bottle_revenue_cents: number;
  estimated_bottle_profit_cents: number;
  installed_in_pumps: number;
  created_at: string;
}

export interface BottlePayload {
  name: string;
  description: string;
  color_hex: string;
  is_alcoholic: boolean;
  is_mixer: boolean;
  bottle_volume_ml: number;
  cost_cents: number;
  loss_pct: number;
  price_per_liter_cents: number;
}

export interface PumpSlot {
  pump_id: PumpId;
  label: string;
  gpio: number;
  flow_rate_ml_s: number;
  remaining_ml: number;
  min_reserve_ml: number;
  available_ml: number;
  bottle_id: string | null;
  ingredient: string;
  description: string;
  color_hex: string;
  is_alcoholic: boolean;
  is_mixer: boolean;
  bottle_volume_ml: number;
  price_per_liter_cents: number;
  price_per_10ml_cents: number;
}

export interface DoseStep {
  pump: PumpId;
  ml: number;
  pause_ms: number;
}

export interface DrinkRecipe {
  id: string;
  bar_id: string;
  name: string;
  subtitle: string;
  description: string;
  category: string;
  badge: string;
  accent_from: string;
  accent_to: string;
  glass_color: string;
  pricing_mode: DrinkPricingMode;
  fixed_price_cents: number;
  discount_pct: number;
  active: boolean;
  steps: DoseStep[];
  total_ml: number;
  estimated_seconds: number;
  raw_ml_price_cents: number;
  final_price_cents: number;
  estimated_cost_cents: number;
  estimated_profit_cents: number;
  is_alcoholic: boolean;
  available: boolean;
  unavailable_reason: string | null;
}

export interface DrinkPayload {
  name: string;
  subtitle: string;
  description: string;
  category: string;
  badge: string;
  accent_from: string;
  accent_to: string;
  glass_color: string;
  pricing_mode: DrinkPricingMode;
  fixed_price_cents: number;
  discount_pct: number;
  active: boolean;
  steps: DoseStep[];
}

export interface PreparationStatus {
  state: PrepState;
  order_id: string | null;
  order_number: number | null;
  drink_id: string | null;
  drink_name: string | null;
  progress: number;
  current_pump: PumpId | null;
  current_step_index: number;
  total_steps: number;
  message: string;
  transport: 'cloud_iot' | 'wifi' | 'serial' | 'simulator' | null;
  elapsed_seconds: number;
  total_seconds: number;
}

export interface HardwareHealth {
  mode: ConnectionMode;
  active_transport: 'cloud_iot' | 'wifi' | 'serial' | 'simulator' | 'disconnected';
  wifi_reachable: boolean;
  wifi_ip: string | null;
  wifi_rssi: number | null;
  serial_connected: boolean;
  available_serial_ports: string[];
  esp32_host: string;
  esp32_port: number;
  serial_port: string;
  serial_baud: number;
  iot_online: boolean;
  last_seen_seconds_ago: number | null;
  detail: string;
}

export interface Machine {
  id: string;
  bar_id: string;
  slug: string;
  name: string;
  api_token: string;
  qr_url: string;
  cup_fee_cents: number;
  min_order_cents: number;
  max_cup_ml: number;
  allow_custom_builder: boolean;
  connection_mode: ConnectionMode;
  esp32_host: string;
  esp32_port: number;
  serial_port: string;
  serial_baud: number;
  pumps: PumpSlot[];
  hardware: HardwareHealth;
  status: PreparationStatus;
  queue_length: number;
}

export interface OrderItemBreakdown {
  pump: PumpId;
  bottle_id: string | null;
  ingredient: string;
  color_hex: string;
  ml: number;
  price_cents: number;
  cost_cents: number;
}

export interface Order {
  id: string;
  order_number: number;
  bar_id: string;
  machine_id: string;
  machine_slug: string;
  machine_name: string;
  customer_session_id: string;
  customer_name: string;
  drink_id: string | null;
  drink_name: string;
  is_custom: boolean;
  is_alcoholic: boolean;
  steps: DoseStep[];
  items: OrderItemBreakdown[];
  total_ml: number;
  subtotal_cents: number;
  cup_fee_cents: number;
  total_cents: number;
  cost_total_cents: number;
  platform_fee_cents: number;
  bar_net_cents: number;
  status: OrderStatus;
  queue_position: number;
  seconds_until_pix_expiry: number;
  seconds_until_turn_expiry: number;
  payment_provider: PaymentProvider;
  payment_external_id: string | null;
  pix_qr_code: string;
  pix_qr_base64: string;
  created_at: string;
  paid_at: string | null;
  completed_at: string | null;
}

export interface MachinePublicContext {
  bar_name: string;
  bar_slug: string;
  payment_provider: PaymentProvider;
  machine_id: string;
  machine_slug: string;
  machine_name: string;
  cup_fee_cents: number;
  min_order_cents: number;
  max_cup_ml: number;
  allow_custom_builder: boolean;
  pumps: PumpSlot[];
  drinks: DrinkRecipe[];
  status: PreparationStatus;
  hardware: HardwareHealth;
  queue_length: number;
  ready_order_number: number | null;
  active_customer_order: Order | null;
}

export interface MachineRealtimeSnapshot {
  machine_slug: string;
  status: PreparationStatus;
  hardware: HardwareHealth;
  queue_length: number;
  ready_order_id: string | null;
  ready_order_number: number | null;
  pumps: PumpSlot[];
}

export interface BarSettings {
  id: string;
  name: string;
  slug: string;
  owner_name: string;
  owner_email: string;
  payment_provider: PaymentProvider;
  has_mp_token: boolean;
  mp_token_masked: string;
  mp_webhook_secret_configured: boolean;
  platform_fee_percent: number;
  public_base_url: string;
}

export interface BarAnalytics {
  paid_orders_count: number;
  completed_orders_count: number;
  pending_orders_count: number;
  refunded_orders_count: number;
  gross_revenue_cents: number;
  total_cost_cents: number;
  platform_fees_cents: number;
  net_profit_cents: number;
  total_ml_dispensed: number;
}

export interface BarSummary {
  id: string;
  name: string;
  slug: string;
  owner_name: string;
  owner_email: string;
  active: boolean;
  payment_provider: PaymentProvider;
  has_mp_token: boolean;
  platform_fee_percent: number;
  machines_count: number;
  paid_orders_count: number;
  gross_revenue_cents: number;
  platform_fees_cents: number;
  created_at: string;
}

export interface PlatformOverview {
  total_bars: number;
  active_bars: number;
  total_machines: number;
  total_paid_orders: number;
  total_gross_cents: number;
  total_platform_fees_cents: number;
  bars: BarSummary[];
}

export interface PublicMachineSummary {
  slug: string;
  name: string;
  bar_name: string;
}

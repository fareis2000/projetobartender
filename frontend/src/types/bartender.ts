export type PumpId = 'amarelo' | 'vermelho' | 'verde' | 'azul';
export type ConnectionMode = 'auto' | 'wifi' | 'serial' | 'simulator';
export type PrepState = 'idle' | 'dispensing' | 'completed' | 'stopped' | 'error';

export interface PumpConfig {
  id: PumpId;
  label: string;
  ingredient: string;
  description: string;
  gpio: number;
  flow_rate_ml_s: number;
  color_hex: string;
  is_mixer: boolean;
}

export interface DoseStep {
  pump: PumpId;
  ml: number;
  pause_ms: number;
}

export interface DrinkRecipe {
  id: string;
  code: string;
  name: string;
  subtitle: string;
  description: string;
  category: string;
  badge: string;
  accent_from: string;
  accent_to: string;
  glass_color: string;
  steps: DoseStep[];
  total_ml: number;
  estimated_seconds: number;
}

export interface CustomDrinkPayload {
  name: string;
  amarelo: number;
  vermelho: number;
  verde: number;
  azul: number;
}

export interface PreparationStatus {
  state: PrepState;
  drink_id: string | null;
  drink_name: string | null;
  progress: number;
  current_pump: PumpId | null;
  current_step_index: number;
  total_steps: number;
  message: string;
  transport: 'wifi' | 'serial' | 'simulator' | null;
  elapsed_seconds: number;
  total_seconds: number;
}

export interface HardwareHealth {
  mode: ConnectionMode;
  active_transport: 'wifi' | 'serial' | 'simulator' | 'disconnected';
  wifi_reachable: boolean;
  wifi_ip: string | null;
  wifi_rssi: number | null;
  serial_connected: boolean;
  available_serial_ports: string[];
  esp32_host: string;
  esp32_port: number;
  serial_port: string;
  serial_baud: number;
  detail: string;
}

export interface SystemSnapshot {
  status: PreparationStatus;
  hardware: HardwareHealth;
}

export interface ConnectionConfigPayload {
  mode: ConnectionMode;
  esp32_host: string;
  esp32_port: number;
  serial_port: string;
  serial_baud: number;
}


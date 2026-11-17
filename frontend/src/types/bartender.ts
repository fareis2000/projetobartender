/**
 * @file bartender.ts
 * @description Contratos TypeScript espelhados 1:1 com os modelos Pydantic do backend (`backend/app/models.py`).
 *
 * Papel na Arquitetura:
 * ---------------------
 * Garante segurança estática em tempo de compilação (`tsc -b`) em toda a comunicação REST e
 * nos frames JSON recebidos pelo canal WebSocket (`/api/ws`), eliminando divergências de nomes
 * de propriedades entre o controle físico em Python/C++ e os componentes visuais React.
 */

/** Identificadores canônicos das 4 bombas dosadoras da bancada. */
export type PumpId = 'amarelo' | 'vermelho' | 'verde' | 'azul';

/** Modos de operação selecionáveis no painel administrativo de hardware. */
export type ConnectionMode = 'auto' | 'wifi' | 'serial' | 'simulator';

/** Estados possíveis do ciclo de preparo de um drink exibidos na interface. */
export type PrepState = 'idle' | 'dispensing' | 'completed' | 'stopped' | 'error';

/**
 * Configuração completa de uma bomba física, incluindo metadados visuais e calibração hidráulica.
 */
export interface PumpConfig {
  /** Chave única da bomba (`amarelo`, `vermelho`, `verde` ou `azul`). */
  id: PumpId;
  /** Nome técnico da posição física (ex.: `'Bomba 1 · Amarela'`). */
  label: string;
  /** Bebida ou xarope atualmente instalado na garrafa correspondente. */
  ingredient: string;
  /** Descrição sensorial exibida nos controles do estúdio interativo. */
  description: string;
  /** Pino GPIO correspondente no ESP32-WROOM-32 (`16`, `17`, `18` ou `19`). */
  gpio: number;
  /** Vazão calibrada em mililitros por segundo (`ml/s`). */
  flow_rate_ml_s: number;
  /** Cor hexadecimal representativa usada no copo vetorial e barras de proporção. */
  color_hex: string;
  /** Define se é uma bebida base/diluidora (habilita faixa maior de volume no slider). */
  is_mixer: boolean;
}

/**
 * Etapa individual de dosagem sequencial dentro de uma receita do cardápio.
 */
export interface DoseStep {
  /** Bomba acionada nesta etapa. */
  pump: PumpId;
  /** Volume em mililitros a ser dispensado. */
  ml: number;
  /** Tempo de espera em milissegundos após o término desta bomba. */
  pause_ms: number;
}

/**
 * Receita completa do catálogo com identidade cromática e métricas calculadas dinamicamente.
 */
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
  /** Soma total em mililitros de todas as etapas da receita. */
  total_ml: number;
  /** Tempo total estimado em segundos considerando as vazões atuais calibradas. */
  estimated_seconds: number;
}

/**
 * Payload enviado ao endpoint `POST /api/dispense/custom` pelo estúdio "Monte seu Drink".
 */
export interface CustomDrinkPayload {
  name: string;
  amarelo: number;
  vermelho: number;
  verde: number;
  azul: number;
}

/**
 * Estado em tempo real da preparação ativa recebido via REST ou streaming WebSocket.
 */
export interface PreparationStatus {
  state: PrepState;
  drink_id: string | null;
  drink_name: string | null;
  /** Porcentagem concluída do preparo (`0` a `100`). */
  progress: number;
  /** Bomba energizada neste exato instante (define a cor do jato animado no copo). */
  current_pump: PumpId | null;
  current_step_index: number;
  total_steps: number;
  message: string;
  transport: 'wifi' | 'serial' | 'simulator' | null;
  elapsed_seconds: number;
  total_seconds: number;
}

/**
 * Diagnóstico detalhado da camada de conectividade física com o ESP32.
 */
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
  connected_ssid?: string | null;
  esp_target_ssid?: string | null;
  server_lan_ip?: string | null;
  discovered_via?: string | null;
}

export interface NetworkSyncResult {
  ok: boolean;
  connected_ssid: string | null;
  esp_target_ssid: string | null;
  wifi_password_found: boolean;
  server_lan_ip: string;
  lan_ips: string[];
  secrets_updated: boolean;
  serial_provisioned: boolean;
  esp_discovered: boolean;
  esp_ip: string | null;
  discovered_via: string | null;
  hardware: HardwareHealth;
  message: string;
}

/**
 * Pacote consolidado transmitido pelo WebSocket (`/api/ws`) a cada mudança de estado.
 */
export interface SystemSnapshot {
  status: PreparationStatus;
  hardware: HardwareHealth;
}

/**
 * Payload enviado em `PUT /api/connection` ao salvar ajustes de rede/porta COM.
 */
export interface ConnectionConfigPayload {
  mode: ConnectionMode;
  esp32_host: string;
  esp32_port: number;
  serial_port: string;
  serial_baud: number;
}

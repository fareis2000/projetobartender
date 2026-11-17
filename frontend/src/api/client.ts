/**
 * @file client.ts
 * @description Cliente HTTP REST fortemente tipado para comunicação com o backend FastAPI.
 *
 * Papel na Arquitetura:
 * ---------------------
 * Encapsula todas as chamadas `fetch` da interface React em funções assíncronas limpas e
 * tipadas (`bartenderApi`), padronizando cabeçalhos JSON e extraindo mensagens amigáveis do
 * campo `detail` retornado pelas validações Pydantic / `HTTPException` do FastAPI (como
 * erros `409 Conflict` quando já há bebida em preparo ou `422` por excesso de volume).
 *
 * Nota sobre URLs Relativas:
 * --------------------------
 * Todas as rotas usam caminhos relativos (`/api/...`), funcionando sem reconfiguração tanto
 * no Vite Dev Server (`localhost:5173` via proxy) quanto em produção na porta `8000` acessada
 * por qualquer IP na rede Wi-Fi do evento (`http://192.168.x.x:8000`).
 */
import type {
  ConnectionConfigPayload,
  CustomDrinkPayload,
  DrinkRecipe,
  HardwareHealth,
  NetworkSyncResult,
  PreparationStatus,
  PumpConfig,
  PumpId,
  SystemSnapshot,
} from '../types/bartender';

/**
 * Helper genérico para requisições HTTP JSON com tratamento unificado de erros da API.
 *
 * @template T Tipo esperado no corpo JSON de resposta em caso de sucesso (`2xx`).
 * @param url Caminho relativo do endpoint (ex.: `'/api/drinks'`).
 * @param init Opções adicionais do `fetch` (método HTTP, body serializado, headers extras).
 * @throws {Error} Mensagem amigável extraída de `data.detail` do FastAPI ou código HTTP.
 */
async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!res.ok) {
    let errMsg = `Erro HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // ignora erro de parse
    }
    throw new Error(errMsg);
  }

  return res.json() as Promise<T>;
}

/**
 * Fachada de serviços REST do Bartender Automático consumida pelos componentes React.
 */
export const bartenderApi = {
  /** Lista o catálogo completo de drinks com volumes (`ml`) e durações (`s`) calculados. */
  getDrinks: () => requestJson<DrinkRecipe[]>('/api/drinks'),

  /** Lista a configuração atual e a vazão calibrada (`ml/s`) das 4 bombas físicas. */
  getPumps: () => requestJson<PumpConfig[]>('/api/pumps'),

  /** Atualiza o ingrediente instalado ou a vazão (`ml/s`) de uma bomba e sincroniza com o ESP32. */
  updatePump: (
    pumpId: PumpId,
    payload: { ingredient?: string; description?: string; flow_rate_ml_s?: number },
  ) =>
    requestJson<PumpConfig>(`/api/pumps/${pumpId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Obtém o snapshot atual de preparo e hardware (`probe=true` força nova sondagem no ESP32). */
  getStatus: (probe = false) =>
    requestJson<SystemSnapshot>(`/api/status${probe ? '?probe=true' : ''}`),

  /** Executa diagnóstico imediato de conectividade Wi-Fi / USB Serial / Simulador. */
  getConnection: () => requestJson<HardwareHealth>('/api/connection'),

  /** Salva e aplica uma nova configuração de modo/endereço de comunicação com o ESP32. */
  updateConnection: (payload: ConnectionConfigPayload) =>
    requestJson<HardwareHealth>('/api/connection', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Solicita o preparo imediato de uma receita pré-definida do cardápio (`POST /api/dispense/{id}`). */
  dispensePreset: (drinkId: string) =>
    requestJson<PreparationStatus>(`/api/dispense/${encodeURIComponent(drinkId)}`, {
      method: 'POST',
    }),

  /** Solicita o preparo de uma bebida personalizada montada pelo usuário (`POST /api/dispense/custom`). */
  dispenseCustom: (payload: CustomDrinkPayload) =>
    requestJson<PreparationStatus>('/api/dispense/custom', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Aciona a Parada de Emergência desligando imediatamente todas as bombas (`POST /api/stop`). */
  emergencyStop: () =>
    requestJson<PreparationStatus>('/api/stop', {
      method: 'POST',
    }),

  /** Puxa a rede Wi-Fi conectada, sincroniza secrets.h, provisiona o ESP e varre a LAN (`POST /api/network/sync`). */
  syncNetwork: () =>
    requestJson<NetworkSyncResult>('/api/network/sync', {
      method: 'POST',
    }),
};

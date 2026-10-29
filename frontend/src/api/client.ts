import type {
  ConnectionConfigPayload,
  CustomDrinkPayload,
  DrinkRecipe,
  HardwareHealth,
  PreparationStatus,
  PumpConfig,
  PumpId,
  SystemSnapshot,
} from '../types/bartender';

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

export const bartenderApi = {
  getDrinks: () => requestJson<DrinkRecipe[]>('/api/drinks'),

  getPumps: () => requestJson<PumpConfig[]>('/api/pumps'),

  updatePump: (
    pumpId: PumpId,
    payload: { ingredient?: string; description?: string; flow_rate_ml_s?: number },
  ) =>
    requestJson<PumpConfig>(`/api/pumps/${pumpId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getStatus: (probe = false) =>
    requestJson<SystemSnapshot>(`/api/status${probe ? '?probe=true' : ''}`),

  getConnection: () => requestJson<HardwareHealth>('/api/connection'),

  updateConnection: (payload: ConnectionConfigPayload) =>
    requestJson<HardwareHealth>('/api/connection', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  dispensePreset: (drinkId: string) =>
    requestJson<PreparationStatus>(`/api/dispense/${encodeURIComponent(drinkId)}`, {
      method: 'POST',
    }),

  dispenseCustom: (payload: CustomDrinkPayload) =>
    requestJson<PreparationStatus>('/api/dispense/custom', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  emergencyStop: () =>
    requestJson<PreparationStatus>('/api/stop', {
      method: 'POST',
    }),
};


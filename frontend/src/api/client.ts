import type {
  AuthTokenResponse,
  BarAnalytics,
  BarSettings,
  BarSummary,
  Bottle,
  BottlePayload,
  DrinkPayload,
  DrinkRecipe,
  Machine,
  MachinePublicContext,
  Order,
  PlatformOverview,
  PreparationStatus,
  PrincipalUser,
  PublicMachineSummary,
  PumpId,
  PumpSlot,
} from '../types/bartender';
import { getInspectBarId, getStoredAuthToken } from '../utils/format';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getStoredAuthToken();
  const inspectBar = getInspectBarId();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(inspectBar ? { 'X-Bar-Id': inspectBar } : {}),
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };

  const res = await fetch(url, {
    ...init,
    headers,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let errMsg = `Erro HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        errMsg =
          typeof data.detail === 'string'
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
              : JSON.stringify(data.detail);
      }
    } catch {
      // ignora erro de parse
    }
    throw new Error(errMsg);
  }

  return res.json() as Promise<T>;
}

export const bartenderApi = {
  // Autenticação
  login: (email: string, password: string) =>
    requestJson<AuthTokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  getMe: () => requestJson<PrincipalUser>('/api/auth/me'),

  // Público Cliente (QR Code na Máquina + Pix + Fila + Confirmação de Copo)
  listPublicMachines: () => requestJson<PublicMachineSummary[]>('/api/public/machines'),

  getPublicMachine: (slug: string, sessionId: string) =>
    requestJson<MachinePublicContext>(
      `/api/public/m/${encodeURIComponent(slug)}?session_id=${encodeURIComponent(sessionId)}`,
    ),

  createPresetOrder: (
    machineSlug: string,
    payload: { drink_id: string; customer_session_id: string; customer_name?: string },
  ) =>
    requestJson<Order>(`/api/public/m/${encodeURIComponent(machineSlug)}/orders/preset`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  createCustomOrder: (
    machineSlug: string,
    payload: {
      name: string;
      customer_session_id: string;
      customer_name?: string;
      amarelo: number;
      vermelho: number;
      verde: number;
      azul: number;
    },
  ) =>
    requestJson<Order>(`/api/public/m/${encodeURIComponent(machineSlug)}/orders/custom`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getOrder: (orderId: string) =>
    requestJson<Order>(`/api/public/orders/${encodeURIComponent(orderId)}`),

  simulatePayOrder: (orderId: string) =>
    requestJson<Order>(`/api/public/orders/${encodeURIComponent(orderId)}/simulate-pay`, {
      method: 'POST',
    }),

  cancelOrder: (orderId: string, sessionId: string) =>
    requestJson<Order>(
      `/api/public/orders/${encodeURIComponent(orderId)}/cancel?customer_session_id=${encodeURIComponent(sessionId)}`,
      { method: 'POST' },
    ),

  resumeOrderTurn: (orderId: string, sessionId: string) =>
    requestJson<Order>(
      `/api/public/orders/${encodeURIComponent(orderId)}/resume-turn?customer_session_id=${encodeURIComponent(sessionId)}`,
      { method: 'POST' },
    ),

  confirmCupAndDispense: (orderId: string, sessionId: string, confirmed: boolean) =>
    requestJson<Order>(
      `/api/public/orders/${encodeURIComponent(orderId)}/confirm-cup-and-dispense`,
      {
        method: 'POST',
        body: JSON.stringify({
          customer_session_id: sessionId,
          cup_on_platform_confirmed: confirmed,
        }),
      },
    ),

  // Painel Dono do Bar — Configurações & Mercado Pago
  getBarSettings: () => requestJson<BarSettings>('/api/bar/settings'),

  updateBarSettings: (payload: {
    name?: string;
    owner_name?: string;
    payment_provider?: 'simulated' | 'mercadopago';
    mp_access_token?: string;
    mp_webhook_secret?: string;
    new_password?: string;
  }) =>
    requestJson<BarSettings>('/api/bar/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // CRUD de Garrafas (R$/ml)
  listBottles: () => requestJson<Bottle[]>('/api/bar/bottles'),

  createBottle: (payload: BottlePayload) =>
    requestJson<Bottle>('/api/bar/bottles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateBottle: (id: string, payload: Partial<BottlePayload>) =>
    requestJson<Bottle>(`/api/bar/bottles/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteBottle: (id: string) =>
    requestJson<void>(`/api/bar/bottles/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  // CRUD Completo de Drinks
  listBarDrinks: () => requestJson<DrinkRecipe[]>('/api/bar/drinks'),

  createDrink: (payload: DrinkPayload) =>
    requestJson<DrinkRecipe>('/api/bar/drinks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateDrink: (id: string, payload: Partial<DrinkPayload>) =>
    requestJson<DrinkRecipe>(`/api/bar/drinks/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteDrink: (id: string) =>
    requestJson<void>(`/api/bar/drinks/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  // Máquinas & 4 Bombas
  listMachines: (probe = false) =>
    requestJson<Machine[]>(`/api/bar/machines${probe ? '?probe=true' : ''}`),

  createMachine: (payload: {
    name: string;
    slug: string;
    cup_fee_cents: number;
    min_order_cents: number;
    max_cup_ml: number;
    allow_custom_builder: boolean;
    connection_mode: string;
  }) =>
    requestJson<Machine>('/api/bar/machines', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateMachine: (id: string, payload: Record<string, unknown>) =>
    requestJson<Machine>(`/api/bar/machines/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  updatePumpSlot: (
    machineId: string,
    pumpId: PumpId,
    payload: {
      bottle_id?: string | null;
      flow_rate_ml_s?: number;
      remaining_ml?: number;
      min_reserve_ml?: number;
    },
  ) =>
    requestJson<PumpSlot[]>(
      `/api/bar/machines/${encodeURIComponent(machineId)}/pumps/${pumpId}`,
      {
        method: 'PUT',
        body: JSON.stringify(payload),
      },
    ),

  refillPump: (machineId: string, pumpId: PumpId, remainingMl?: number) =>
    requestJson<PumpSlot[]>(
      `/api/bar/machines/${encodeURIComponent(machineId)}/pumps/${pumpId}/refill`,
      {
        method: 'POST',
        body: JSON.stringify(remainingMl !== undefined ? { remaining_ml: remainingMl } : {}),
      },
    ),

  emergencyStopMachine: (machineId: string) =>
    requestJson<PreparationStatus>(`/api/bar/machines/${encodeURIComponent(machineId)}/stop`, {
      method: 'POST',
    }),

  // Pedidos & Financeiro
  listBarOrders: () => requestJson<Order[]>('/api/bar/orders'),

  getBarAnalytics: () => requestJson<BarAnalytics>('/api/bar/analytics'),

  refundOrder: (orderId: string) =>
    requestJson<Order>(`/api/bar/orders/${encodeURIComponent(orderId)}/refund`, {
      method: 'POST',
    }),

  retryOrder: (orderId: string) =>
    requestJson<Order>(`/api/bar/orders/${encodeURIComponent(orderId)}/retry`, {
      method: 'POST',
    }),

  // Super-Admin Multi-Bares
  getPlatformOverview: () => requestJson<PlatformOverview>('/api/superadmin/overview'),

  createBarTenant: (payload: {
    name: string;
    slug: string;
    owner_name: string;
    owner_email: string;
    owner_password: string;
    platform_fee_percent: number;
    initial_machine_name: string;
    initial_machine_slug: string;
  }) =>
    requestJson<BarSummary>('/api/superadmin/bars', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateBarTenant: (
    barId: string,
    payload: {
      name?: string;
      owner_name?: string;
      owner_email?: string;
      owner_password?: string;
      active?: boolean;
      platform_fee_percent?: number;
    },
  ) =>
    requestJson<BarSummary>(`/api/superadmin/bars/${encodeURIComponent(barId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteBarTenant: (barId: string) =>
    requestJson<void>(`/api/superadmin/bars/${encodeURIComponent(barId)}`, {
      method: 'DELETE',
    }),
};

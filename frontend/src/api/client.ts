/**
 * @file src/api/client.ts
 * @description Cliente HTTP tipado e centralizado (`bartenderApi`) para comunicação REST com o backend FastAPI.
 *
 * Papel na Arquitetura Multi-Tenant & Segurança Operacional:
 * - Centraliza 100% das chamadas de rede das três frentes do produto (Autoatendimento Mobile Público,
 *   ERP do Dono do Bar e Console Super-Admin SaaS) usando `fetch` nativo sem bibliotecas pesadas.
 * - Injeta automaticamente o token JWT (`Authorization: Bearer ...`) quando autenticado e o cabeçalho
 *   de governança multi-tenant (`X-Bar-Id`) quando o Super-Admin está prestando suporte remoto a um bar.
 * - Traduz erros estruturados de validação do FastAPI/Pydantic (`detail` string ou lista de objetos)
 *   em mensagens claras em português prontas para exibição imediata nos banners de UI.
 */
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
  MpTokenTestResult,
  Order,
  PlatformOverview,
  PreparationStatus,
  PrincipalUser,
  PublicMachineSummary,
  PumpId,
  PumpSlot,
} from '../types/bartender';
import { getInspectBarId, getStoredAuthToken } from '../utils/format';

/**
 * Executor HTTP genérico com serialização JSON, injeção automática de credenciais/tenant
 * e normalização de exceções vindas da API FastAPI.
 *
 * @template T Tipo esperado do corpo JSON de resposta.
 * @param url Endpoint relativo da API (ex.: `"/api/bar/bottles"`).
 * @param init Opções adicionais do `fetch` (método HTTP, body serializado, cabeçalhos extras).
 * @returns Promise resolvida com o payload tipado `T` (ou `undefined` em respostas `204 No Content`).
 * @throws {Error} Mensagem amigável extraída de `data.detail` ou código HTTP correspondente.
 */
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

/**
 * Fachada completa da API do Bartender.OS v3.0 organizada por domínio de negócio.
 */
export const bartenderApi = {
  // Autenticação
  /** Autentica Dono do Bar ou Super-Admin e retorna o JWT + perfil (`PrincipalUser`). */
  login: (email: string, password: string) =>
    requestJson<AuthTokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  /** Valida o token JWT salvo no navegador e recupera os dados atualizados do operador logado. */
  getMe: () => requestJson<PrincipalUser>('/api/auth/me'),

  // Público Cliente (QR Code na Máquina + Pix + Fila + Confirmação de Copo)
  /** Lista todas as máquinas públicas ativas disponíveis para acesso rápido. */
  listPublicMachines: () => requestJson<PublicMachineSummary[]>('/api/public/machines'),

  /**
   * Sincroniza o celular do cliente com uma máquina específica via slug do QR Code,
   * retornando cardápio ao vivo, bombas instaladas, fila e eventual pedido ativo daquela sessão.
   */
  getPublicMachine: (slug: string, sessionId: string) =>
    requestJson<MachinePublicContext>(
      `/api/public/m/${encodeURIComponent(slug)}?session_id=${encodeURIComponent(sessionId)}`,
    ),

  /** Gera cobrança Pix imediata para um drink pronto do cardápio da máquina. */
  createPresetOrder: (
    machineSlug: string,
    payload: { drink_id: string; customer_session_id: string; customer_name?: string },
  ) =>
    requestJson<Order>(`/api/public/m/${encodeURIComponent(machineSlug)}/orders/preset`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Gera cobrança Pix sob medida para uma combinação personalizada de mililitros nas 4 bombas. */
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

  /** Consulta o estado atualizado, contadores de expiração e posição na fila de um pedido específico. */
  getOrder: (orderId: string) =>
    requestJson<Order>(`/api/public/orders/${encodeURIComponent(orderId)}`),

  /** Aprova instantaneamente um pedido em modo Sandbox (`payment_provider === 'simulated'`) para demos comerciais. */
  simulatePayOrder: (orderId: string) =>
    requestJson<Order>(`/api/public/orders/${encodeURIComponent(orderId)}/simulate-pay`, {
      method: 'POST',
    }),

  /** Cancela um pedido ainda pendente de pagamento pertencente à sessão do cliente. */
  cancelOrder: (orderId: string, sessionId: string) =>
    requestJson<Order>(
      `/api/public/orders/${encodeURIComponent(orderId)}/cancel?customer_session_id=${encodeURIComponent(sessionId)}`,
      { method: 'POST' },
    ),

  /** Retoma a vez na fila (ou estende +60s para pegar gelo/copo) sem perder o crédito Pix já pago. */
  resumeOrderTurn: (orderId: string, sessionId: string) =>
    requestJson<Order>(
      `/api/public/orders/${encodeURIComponent(orderId)}/resume-turn?customer_session_id=${encodeURIComponent(sessionId)}`,
      { method: 'POST' },
    ),

  /**
   * Envia o aceite obrigatório de segurança confirmando que o copo está posicionado na base física
   * e dispara imediatamente o acionamento das bombas na controladora IoT/ESP.
   */
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
  /** Obtém dados cadastrais, provedor Pix ativo, webhook dedicado e token mascarado do bar. */
  getBarSettings: () => requestJson<BarSettings>('/api/bar/settings'),

  /** Atualiza modo de pagamento (`simulated` vs `mercadopago`), credenciais Mercado Pago ou dados do bar. */
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

  /** Valida ao vivo o Access Token na API oficial do Mercado Pago e retorna o titular conectado. */
  testMercadoPagoToken: (mpAccessToken?: string) =>
    requestJson<MpTokenTestResult>('/api/bar/settings/test-mercadopago', {
      method: 'POST',
      body: JSON.stringify(
        mpAccessToken && mpAccessToken.trim() ? { mp_access_token: mpAccessToken.trim() } : {},
      ),
    }),

  // CRUD de Garrafas (R$/ml)
  /** Lista todas as garrafas/insumos do estoque do bar com métricas de custo, dose e lucro projetado. */
  listBottles: () => requestJson<Bottle[]>('/api/bar/bottles'),

  /** Cadastra uma nova garrafa com cálculo automático de volume útil e preço por mililitro. */
  createBottle: (payload: BottlePayload) =>
    requestJson<Bottle>('/api/bar/bottles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Atualiza preço, custo, cor ou parâmetros técnicos de uma garrafa existente (recalculando drinks vinculados). */
  updateBottle: (id: string, payload: Partial<BottlePayload>) =>
    requestJson<Bottle>(`/api/bar/bottles/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Remove uma garrafa do catálogo do bar e desvincula eventuais bombas que a utilizavam. */
  deleteBottle: (id: string) =>
    requestJson<void>(`/api/bar/bottles/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  // CRUD Completo de Drinks
  /** Lista todas as receitas de drinks do bar (ativas e ocultas) com CMV e margem por copo. */
  listBarDrinks: () => requestJson<DrinkRecipe[]>('/api/bar/drinks'),

  /** Cria uma nova receita autoral ou clássica no cardápio do bar. */
  createDrink: (payload: DrinkPayload) =>
    requestJson<DrinkRecipe>('/api/bar/drinks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Edita receita, etapas de bombas, precificação ou visibilidade (`active`) de um drink. */
  updateDrink: (id: string, payload: Partial<DrinkPayload>) =>
    requestJson<DrinkRecipe>(`/api/bar/drinks/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Exclui permanentemente uma receita de drink do cardápio do estabelecimento. */
  deleteDrink: (id: string) =>
    requestJson<void>(`/api/bar/drinks/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  // Máquinas & 4 Bombas
  /** Lista as máquinas do bar; quando `probe = true`, executa diagnóstico ativo de rede/serial no hardware. */
  listMachines: (probe = false) =>
    requestJson<Machine[]>(`/api/bar/machines${probe ? '?probe=true' : ''}`),

  /** Provisiona uma nova máquina física no bar com token IoT próprio e QR Code SVG exclusivo. */
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

  /** Atualiza parâmetros comerciais ou modo de transporte IoT de uma máquina instalada. */
  updateMachine: (id: string, payload: Record<string, unknown>) =>
    requestJson<Machine>(`/api/bar/machines/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Puxa a rede Wi-Fi conectada, sincroniza secrets.h, provisiona o ESP e varre a LAN. */
  discoverMachineNetwork: (id: string) =>
    requestJson<Machine>(`/api/bar/machines/${encodeURIComponent(id)}/discover`, {
      method: 'POST',
    }),

  /** Vincula uma garrafa do estoque a uma das 4 bombas físicas ou calibra sua vazão (`flow_rate_ml_s`). */
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

  /** Registra a troca rápida por garrafa cheia (100% do volume nominal) em 1 clique pela equipe de balcão. */
  refillPump: (machineId: string, pumpId: PumpId, remainingMl?: number) =>
    requestJson<PumpSlot[]>(
      `/api/bar/machines/${encodeURIComponent(machineId)}/pumps/${pumpId}/refill`,
      {
        method: 'POST',
        body: JSON.stringify(remainingMl !== undefined ? { remaining_ml: remainingMl } : {}),
      },
    ),

  /** Aciona corte imediato de todas as bombas da máquina em caso de incidente no balcão. */
  emergencyStopMachine: (machineId: string) =>
    requestJson<PreparationStatus>(`/api/bar/machines/${encodeURIComponent(machineId)}/stop`, {
      method: 'POST',
    }),

  // Pedidos & Financeiro
  /** Retorna histórico completo de pedidos, fila e lucro líquido por transação do bar. */
  listBarOrders: () => requestJson<Order[]>('/api/bar/orders'),

  /** Obtém os KPIs financeiros consolidados (faturamento Pix, CMV em litros/R$ e lucro líquido). */
  getBarAnalytics: () => requestJson<BarAnalytics>('/api/bar/analytics'),

  /** Executa estorno financeiro do Pix (simulado ou via API Mercado Pago) de um pedido elegível. */
  refundOrder: (orderId: string) =>
    requestJson<Order>(`/api/bar/orders/${encodeURIComponent(orderId)}/refund`, {
      method: 'POST',
    }),

  /** Reenvia à fila de preparo um pedido que sofreu interrupção física (`FAILED_DISPENSE`). */
  retryOrder: (orderId: string) =>
    requestJson<Order>(`/api/bar/orders/${encodeURIComponent(orderId)}/retry`, {
      method: 'POST',
    }),

  // Super-Admin Multi-Bares
  /** Carrega indicadores globais da rede SaaS (GMV Pix, Split acumulado, total de máquinas e bares). */
  getPlatformOverview: () => requestJson<PlatformOverview>('/api/superadmin/overview'),

  /** Credencia um novo Bar cliente (tenant isolado) já com login do proprietário e 1ª máquina pronta para uso. */
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

  /** Atualiza dados contratuais, status ativo ou percentual de Split SaaS de um bar cliente. */
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

  /** Remove um tenant de bar e todas as entidades a ele associadas na plataforma. */
  deleteBarTenant: (barId: string) =>
    requestJson<void>(`/api/superadmin/bars/${encodeURIComponent(barId)}`, {
      method: 'DELETE',
    }),
};

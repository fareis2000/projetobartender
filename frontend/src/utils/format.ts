/**
 * @file src/utils/format.ts
 * @description Utilitários de formatação monetária BRL (centavos e frações por ml), gestão de sessão
 * anônima do consumidor, persistência de autenticação JWT, impersonation B2B (`X-Bar-Id`) e navegação SPA.
 *
 * Papel na Jornada Comercial & Precisão Financeira:
 * - Zero erro de ponto flutuante na cobrança: o backend opera em centavos inteiros (`cents`) e
 *   preço por litro em centavos (`pricePerLiterCents`), enquanto o frontend converte apenas na camada
 *   visual para Real Brasileiro (`pt-BR`), inclusive exibindo 3 casas decimais quando um mixer custa
 *   frações de centavo por mililitro (ex.: `R$ 0,035/ml`).
 * - Sessão sem cadastro (`getOrCreateCustomerSessionId`): permite que o cliente compre um drink em
 *   segundos apenas lendo o QR Code no 4G, mantendo seu pedido e lugar na fila salvos no navegador
 *   mesmo se ele alternar para o aplicativo do banco para pagar o Pix.
 * - Suporte nativo ao Super-Admin (`INSPECT_BAR_KEY`): viabiliza suporte técnico remoto ("impersonation")
 *   em que a equipe da plataforma inspeciona ou configura garrafas/cardápio de qualquer bar cliente.
 */

/** Chave do `localStorage` que identifica de forma persistente o aparelho do cliente na fila da máquina. */
const SESSION_KEY = 'bartender_v3_customer_session';

/** Chave do `localStorage` onde o token Bearer JWT de Dono de Bar ou Super-Admin é armazenado. */
const AUTH_TOKEN_KEY = 'bartender_v3_auth_token';

/** Chave do `localStorage` usada pelo Super-Admin para inspecionar um estabelecimento específico via header `X-Bar-Id`. */
const INSPECT_BAR_KEY = 'bartender_v3_inspect_bar_id';

/**
 * Formata um valor inteiro em centavos para moeda Real Brasileiro (`R$ XX,XX`).
 *
 * @param cents Valor monetário em centavos inteiros (ex.: `1850` -> `"R$ 18,50"`).
 * @returns String formatada no padrão monetário `pt-BR`.
 */
export function formatBrl(cents: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format((cents || 0) / 100);
}

/**
 * Formata o preço unitário por mililitro a partir do valor em centavos por litro (`price_per_liter_cents`).
 * Exibe automaticamente 3 casas decimais para insumos econômicos (< R$ 0,10/ml, como energéticos/tônicas),
 * garantindo transparência total na calculadora "Monte por ml".
 *
 * @param pricePerLiterCents Preço de 1 litro (1000 ml) expresso em centavos (ex.: `20000` -> `"R$ 0,20"`/ml).
 * @returns String monetária em BRL representando o preço exato de 1 ml.
 */
export function formatPerMl(pricePerLiterCents: number): string {
  const reaisPerMl = (pricePerLiterCents || 0) / 100_000;
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: reaisPerMl < 0.1 ? 3 : 2,
    maximumFractionDigits: 3,
  }).format(reaisPerMl);
}

/**
 * Recupera ou gera um identificador único de sessão para o smartphone do consumidor (`cust_...`).
 * Dispensa tela de login/cadastro para o público final no bar, maximizando a conversão por impulso,
 * enquanto protege ações sensíveis do pedido (cancelar, pausar/retomar vez e confirmar copo na base).
 *
 * @returns Identificador persistente da sessão do cliente salvo no `localStorage`.
 */
export function getOrCreateCustomerSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id || id.length < 8) {
    id = `cust_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

/**
 * Lê o token JWT administrativo atualmente armazenado no navegador.
 *
 * @returns Token Bearer JWT ou `null` caso não autenticado.
 */
export function getStoredAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * Armazena ou limpa o token JWT administrativo no `localStorage`.
 * Ao fazer logout (`token = null`), remove também qualquer contexto de inspeção (`INSPECT_BAR_KEY`)
 * para evitar vazamento de escopo entre sessões administrativas.
 *
 * @param token Novo token JWT retornado pelo login ou `null` para encerrar sessão.
 */
export function setStoredAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(INSPECT_BAR_KEY);
  }
}

/**
 * Obtém o ID do bar que está sendo inspecionado pelo Super-Admin da plataforma, se houver.
 *
 * @returns UUID/ID do bar alvo ou `null` quando operando normalmente como dono do próprio bar.
 */
export function getInspectBarId(): string | null {
  return localStorage.getItem(INSPECT_BAR_KEY);
}

/**
 * Define ou limpa o estabelecimento alvo que o Super-Admin deseja gerenciar remotamente no `/painel`.
 *
 * @param barId Identificador do bar cliente a ser injetado no cabeçalho `X-Bar-Id`, ou `null` para sair.
 */
export function setInspectBarId(barId: string | null): void {
  if (barId) {
    localStorage.setItem(INSPECT_BAR_KEY, barId);
  } else {
    localStorage.removeItem(INSPECT_BAR_KEY);
  }
}

/**
 * Realiza navegação SPA instantânea atualizando a URL via `history.pushState` e notificando
 * o roteador reativo em `App.tsx` através de um evento `popstate` sintético.
 *
 * @param path Caminho interno de destino (ex.: `"/painel"`, `"/superadmin"`, `"/m/maq-01"`).
 */
export function navigateTo(path: string): void {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

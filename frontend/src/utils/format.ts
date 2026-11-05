const SESSION_KEY = 'bartender_v3_customer_session';
const AUTH_TOKEN_KEY = 'bartender_v3_auth_token';
const INSPECT_BAR_KEY = 'bartender_v3_inspect_bar_id';

export function formatBrl(cents: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format((cents || 0) / 100);
}

export function formatPerMl(pricePerLiterCents: number): string {
  const reaisPerMl = (pricePerLiterCents || 0) / 100_000;
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: reaisPerMl < 0.1 ? 3 : 2,
    maximumFractionDigits: 3,
  }).format(reaisPerMl);
}

export function getOrCreateCustomerSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id || id.length < 8) {
    id = `cust_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function getStoredAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setStoredAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(INSPECT_BAR_KEY);
  }
}

export function getInspectBarId(): string | null {
  return localStorage.getItem(INSPECT_BAR_KEY);
}

export function setInspectBarId(barId: string | null): void {
  if (barId) {
    localStorage.setItem(INSPECT_BAR_KEY, barId);
  } else {
    localStorage.removeItem(INSPECT_BAR_KEY);
  }
}

export function navigateTo(path: string): void {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

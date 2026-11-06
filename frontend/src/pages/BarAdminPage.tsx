/**
 * @file src/pages/BarAdminPage.tsx
 * @description Painel Operacional e Financeiro do Dono do Bar (`/painel` ou `/admin`).
 *
 * Proposta de Valor B2B ("ERP Completo de Coquetelaria Automática no Bolso"):
 * - **DRE Instantâneo no Topo**: exibe Faturamento Pix Pago, Custo das Garrafas Consumidas (com litros
 *   servidos), Lucro Líquido Real do Bar (já descontando insumos e split da plataforma) e Modo Pix ativo.
 * - **5 Abas Integradas**:
 *   1. `Garrafas & R$/ml` (`BottlesCrudSection`): cadastro de estoque com calculadora de markup/dose;
 *   2. `Cardápio` (`DrinksCrudSection`): criação visual de drinks com custo e margem por copo;
 *   3. `Máquinas, Bombas & QR Code` (`MachinesPumpsSection`): gestão física das 4 mangueiras e credenciais ESP;
 *   4. `Vendas & Fila Pix`: auditoria de pedidos com botões de `"Reenviar à Fila"` e `"Estornar Pix"`;
 *   5. `Conta Pix / Mercado Pago`: chaveamento imediato entre modo Sandbox (`simulated`) para testes e
 *      liquidação Pix Oficial Banco Central (`mercadopago`) direto na conta do estabelecimento.
 * - Suporta também acesso em modo de inspeção pelo `superadmin` (`← Voltar p/ Bares`).
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  Banknote,
  CheckCircle2,
  Citrus,
  CreditCard,
  ExternalLink,
  Eye,
  EyeOff,
  LogOut,
  Palmtree,
  QrCode,
  Receipt,
  RotateCcw,
  ShieldCheck,
  Wine,
} from 'lucide-react';
import { bartenderApi } from '../api/client';
import { BottlesCrudSection } from '../components/admin/BottlesCrudSection';
import { DrinksCrudSection } from '../components/admin/DrinksCrudSection';
import { MachinesPumpsSection } from '../components/admin/MachinesPumpsSection';
import type {
  BarAnalytics,
  BarSettings,
  Bottle,
  DrinkRecipe,
  Machine,
  Order,
  PaymentProvider,
  PrincipalUser,
} from '../types/bartender';
import {
  formatBrl,
  getInspectBarId,
  getStoredAuthToken,
  navigateTo,
  setInspectBarId,
  setStoredAuthToken,
} from '../utils/format';

/** Identificadores das 5 abas de gestão do estabelecimento. */
type AdminTab = 'bottles' | 'drinks' | 'machines' | 'orders' | 'pix';

/**
 * Página administrativa do tenant Bar com login integrado, KPIs financeiros e CRUDs modulares.
 */
export const BarAdminPage: React.FC = () => {
  const [user, setUser] = useState<PrincipalUser | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  // Credenciais pré-preenchidas com conta demo para agilizar avaliação comercial / pitch
  const [loginEmail, setLoginEmail] = useState('dono@bartropical.com');
  const [loginPassword, setLoginPassword] = useState('bar123');
  const [loginError, setLoginError] = useState<string | null>(null);

  const [tab, setTab] = useState<AdminTab>('bottles');
  const [bottles, setBottles] = useState<Bottle[]>([]);
  const [drinks, setDrinks] = useState<DrinkRecipe[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [analytics, setAnalytics] = useState<BarAnalytics | null>(null);
  const [barSettings, setBarSettings] = useState<BarSettings | null>(null);

  // Campos aba Pix
  const [provider, setProvider] = useState<PaymentProvider>('simulated');
  const [mpToken, setMpToken] = useState('');
  const [showMpToken, setShowMpToken] = useState(false);
  const [savingPix, setSavingPix] = useState(false);
  const [testingPix, setTestingPix] = useState(false);
  const [pixSavedMsg, setPixSavedMsg] = useState<string | null>(null);
  const [pixErrorMsg, setPixErrorMsg] = useState<string | null>(null);

  /**
   * Carrega em paralelo (`Promise.all`) todo o ecossistema operacional e financeiro do bar,
   * minimizando latência ao abrir o painel ou após mutações de CRUD.
   */
  const loadAllBarData = useCallback(async (probe = false) => {
    const [bList, dList, mList, oList, an, st] = await Promise.all([
      bartenderApi.listBottles(),
      bartenderApi.listBarDrinks(),
      bartenderApi.listMachines(probe),
      bartenderApi.listBarOrders(),
      bartenderApi.getBarAnalytics(),
      bartenderApi.getBarSettings(),
    ]);
    setBottles(bList);
    setDrinks(dList);
    setMachines(mList);
    setOrders(oList);
    setAnalytics(an);
    setBarSettings(st);
    setProvider(st.payment_provider);
  }, []);

  /** Verifica sessão JWT salva ao montar a página e redireciona Super-Admin sem `inspectBarId` para `/superadmin`. */
  useEffect(() => {
    const check = async () => {
      const tok = getStoredAuthToken();
      if (!tok) {
        setAuthChecking(false);
        return;
      }
      try {
        const me = await bartenderApi.getMe();
        if (me.role === 'superadmin' && !getInspectBarId()) {
          navigateTo('/superadmin');
          return;
        }
        setUser(me);
        await loadAllBarData(false);
      } catch {
        setStoredAuthToken(null);
      } finally {
        setAuthChecking(false);
      }
    };
    void check();
  }, [loadAllBarData]);

  /** Realiza login do operador e direciona automaticamente conforme seu papel (`bar_owner` vs `superadmin`). */
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    try {
      const res = await bartenderApi.login(loginEmail, loginPassword);
      setStoredAuthToken(res.access_token);
      if (res.user.role === 'superadmin') {
        navigateTo('/superadmin');
        return;
      }
      setUser(res.user);
      await loadAllBarData(false);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Falha no login.');
    }
  };

  /** Encerra a sessão administrativa local. */
  const handleLogout = () => {
    setStoredAuthToken(null);
    setUser(null);
  };

  /** Salva o provedor Pix (`simulated` ou `mercadopago`) e atualiza o Access Token se informado. */
  const handleSavePixSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingPix(true);
    setPixSavedMsg(null);
    setPixErrorMsg(null);
    try {
      const updated = await bartenderApi.updateBarSettings({
        payment_provider: provider,
        ...(mpToken.trim() ? { mp_access_token: mpToken.trim() } : {}),
      });
      setBarSettings(updated);
      setMpToken('');
      setPixSavedMsg('Configurações de Pix salvas com sucesso!');
    } catch (err) {
      setPixErrorMsg(err instanceof Error ? err.message : 'Erro ao salvar configurações Pix.');
    } finally {
      setSavingPix(false);
    }
  };

  /** Valida ao vivo o Access Token digitado (ou já salvo) diretamente na API oficial do Mercado Pago. */
  const handleTestMercadoPago = async () => {
    setTestingPix(true);
    setPixSavedMsg(null);
    setPixErrorMsg(null);
    try {
      const res = await bartenderApi.testMercadoPagoToken(mpToken);
      setPixSavedMsg(`✅ ${res.message}`);
    } catch (err) {
      setPixErrorMsg(err instanceof Error ? err.message : 'Falha ao testar Access Token no Mercado Pago.');
    } finally {
      setTestingPix(false);
    }
  };

  /** Solicita confirmação e executa o estorno financeiro Pix de um pedido pago. */
  const handleRefund = async (o: Order) => {
    if (!window.confirm(`Estornar o Pix de ${formatBrl(o.total_cents)} do pedido #${o.order_number}?`)) {
      return;
    }
    try {
      await bartenderApi.refundOrder(o.id);
      await loadAllBarData(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Falha no estorno.');
    }
  };

  if (authChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm font-bold text-[#69432e]">
        Carregando Painel do Bar...
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="w-full max-w-md linen-card rounded-[32px] border border-[#ecd0b1] p-8 space-y-6 shadow-xl">
          <div className="text-center space-y-2">
            <div className="w-12 h-12 mx-auto rounded-2xl bg-gradient-to-br from-[#ea580c] to-[#e11d48] text-white flex items-center justify-center shadow-md">
              <Palmtree className="w-6 h-6" />
            </div>
            <h1 className="font-display text-3xl font-extrabold text-[#2d1810]">
              Painel do Dono do Bar
            </h1>
            <p className="text-xs text-[#7c533d]">
              Gerencie garrafas (R$/ml), cardápio, QR Codes e recebimento Pix.
            </p>
          </div>

          {loginError && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs font-bold text-rose-700">
              {loginError}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">E-mail do Bar</label>
              <input
                type="email"
                required
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-semibold"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Senha</label>
              <input
                type="password"
                required
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-semibold"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white font-bold text-sm shadow-lg cursor-pointer"
            >
              Entrar no Painel
            </button>
          </form>

          <div className="p-3.5 rounded-2xl bg-[#fdf5ea] border border-[#ecd3b5] text-[11px] text-[#69432e] space-y-1">
            <strong className="block text-[#2d1810]">Acessos padrão de demonstração:</strong>
            <div>• Dono do Bar: <code>dono@bartropical.com</code> / <code>bar123</code></div>
            <div>• Plataforma (Multi-Bares): <code>superadmin@bartender.os</code> / <code>admin123</code></div>
          </div>

          <div className="flex justify-between text-xs font-bold text-[#b45309]">
            <button
              type="button"
              onClick={() => navigateTo('/m/maq-01')}
              className="inline-flex items-center gap-1 hover:underline cursor-pointer"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Ver Cardápio Cliente
            </button>
            <button
              type="button"
              onClick={() => navigateTo('/superadmin')}
              className="inline-flex items-center gap-1 hover:underline cursor-pointer"
            >
              <ShieldCheck className="w-3.5 h-3.5" /> Super-Admin
            </button>
          </div>
        </div>
      </div>
    );
  }

  const primaryMachine = machines[0];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Barra Superior Admin */}
      <header className="sticky top-0 z-40 border-b border-[#ead0b2] bg-[#fffaf2]/95 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {user.role === 'superadmin' && (
              <button
                type="button"
                onClick={() => {
                  setInspectBarId(null);
                  navigateTo('/superadmin');
                }}
                className="px-3 py-1.5 rounded-xl bg-[#2d1810] text-white text-xs font-bold cursor-pointer"
              >
                ← Voltar p/ Bares
              </button>
            )}
            <div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#b45309]">
                Gestão Comercial do Estabelecimento
              </span>
              <h1 className="font-display text-xl sm:text-2xl font-extrabold text-[#2d1810]">
                {barSettings?.name ?? user.bar_name ?? 'Meu Bar'}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {primaryMachine && (
              <button
                type="button"
                onClick={() => navigateTo(`/m/${primaryMachine.slug}`)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-bold text-emerald-800 cursor-pointer"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Abrir Visão do Cliente (/m/{primaryMachine.slug})
              </button>
            )}
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#f6e6cf] text-xs font-bold text-[#5c3724] cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sair
            </button>
          </div>
        </div>

        {/* Navegação de Abas do CRUD */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-3 flex flex-wrap gap-2">
          {[
            { id: 'bottles', label: 'Garrafas & R$/ml', icon: Wine },
            { id: 'drinks', label: 'Cardápio (CRUD Drinks)', icon: Citrus },
            { id: 'machines', label: 'Máquinas, Bombas & QR Code', icon: QrCode },
            { id: 'orders', label: 'Vendas & Fila Pix', icon: Receipt },
            { id: 'pix', label: 'Conta Pix / Mercado Pago', icon: CreditCard },
          ].map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id as AdminTab)}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer ${
                  active
                    ? 'bg-[#2d1810] text-white shadow-sm'
                    : 'bg-white/80 text-[#69432e] hover:bg-white border border-[#e6c8a5]'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* KPIs Financeiros Rápidos no Topo */}
        {analytics && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Faturamento Pix Pago</span>
              <strong className="block font-display text-2xl font-extrabold text-[#15803d] mt-1">
                {formatBrl(analytics.gross_revenue_cents)}
              </strong>
              <span className="text-[11px] text-[#8a614a]">
                {analytics.paid_orders_count} pedido(s) pagos
              </span>
            </div>

            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Custo das Garrafas Usadas</span>
              <strong className="block font-display text-2xl font-extrabold text-[#2d1810] mt-1">
                {formatBrl(analytics.total_cost_cents)}
              </strong>
              <span className="text-[11px] text-[#8a614a]">
                {(analytics.total_ml_dispensed / 1000).toFixed(2)} L servidos
              </span>
            </div>

            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Lucro Líquido do Bar</span>
              <strong className="block font-display text-2xl font-extrabold text-emerald-700 mt-1">
                {formatBrl(analytics.net_profit_cents)}
              </strong>
              <span className="text-[11px] text-[#8a614a]">
                Já descontando insumos e taxas
              </span>
            </div>

            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Modo Pix Atual</span>
              <strong className="block font-display text-xl font-extrabold text-[#b45309] mt-1">
                {barSettings?.payment_provider === 'mercadopago'
                  ? 'Mercado Pago Oficial'
                  : 'Pix Simulado (Teste)'}
              </strong>
              <button
                type="button"
                onClick={() => setTab('pix')}
                className="text-[11px] font-bold text-[#ea580c] hover:underline cursor-pointer"
              >
                Configurar chave/token →
              </button>
            </div>
          </div>
        )}

        {tab === 'bottles' && (
          <BottlesCrudSection bottles={bottles} onRefresh={() => loadAllBarData(false)} />
        )}

        {tab === 'drinks' && (
          <DrinksCrudSection
            drinks={drinks}
            pumps={primaryMachine?.pumps ?? []}
            cupFeeCents={primaryMachine?.cup_fee_cents ?? 0}
            minOrderCents={primaryMachine?.min_order_cents ?? 500}
            onRefresh={() => loadAllBarData(false)}
          />
        )}

        {tab === 'machines' && (
          <MachinesPumpsSection
            machines={machines}
            bottles={bottles}
            onRefresh={(probe) => loadAllBarData(probe)}
          />
        )}

        {tab === 'orders' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-2xl font-bold text-[#2d1810]">
                Histórico de Pedidos, Fila & Estornos
              </h3>
              <button
                type="button"
                onClick={() => void loadAllBarData(false)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#f6e6cf] text-xs font-bold text-[#5c3724] cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Atualizar
              </button>
            </div>

            <div className="linen-card rounded-3xl border border-[#ecd0b1] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs sm:text-sm">
                  <thead className="bg-[#f7ead8] text-[#5c3724] text-xs uppercase">
                    <tr>
                      <th className="py-3 px-4">Senha</th>
                      <th className="py-3 px-4">Drink / Volume</th>
                      <th className="py-3 px-4">Máquina</th>
                      <th className="py-3 px-4">Valor / Lucro</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#f0dcc2]">
                    {orders.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-[#7c533d]">
                          Nenhum pedido registrado ainda.
                        </td>
                      </tr>
                    ) : (
                      orders.map((o) => (
                        <tr key={o.id} className="hover:bg-white/60">
                          <td className="py-3 px-4 font-bold text-[#2d1810]">
                            #{o.order_number}
                          </td>
                          <td className="py-3 px-4">
                            <strong className="block text-[#2d1810]">{o.drink_name}</strong>
                            <span className="text-xs text-[#7c533d]">{o.total_ml} ml</span>
                          </td>
                          <td className="py-3 px-4 text-xs text-[#69432e]">{o.machine_name}</td>
                          <td className="py-3 px-4">
                            <strong className="text-[#15803d]">{formatBrl(o.total_cents)}</strong>
                            <span className="block text-[11px] text-[#7c533d]">
                              Líquido bar: {formatBrl(o.bar_net_cents - o.cost_total_cents)}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#f6e6cf] text-[#2d1810]">
                              {o.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right space-x-2">
                            {o.status === 'FAILED_DISPENSE' && (
                              <button
                                type="button"
                                onClick={() =>
                                  void bartenderApi.retryOrder(o.id).then(() => loadAllBarData())
                                }
                                className="px-2.5 py-1 rounded-lg bg-amber-600 text-white text-xs font-bold cursor-pointer"
                              >
                                Reenviar à Fila
                              </button>
                            )}
                            {['PAID_QUEUED', 'READY_FOR_CUP', 'PAUSED_TURN', 'COMPLETED', 'FAILED_DISPENSE'].includes(
                              o.status,
                            ) && (
                              <button
                                type="button"
                                onClick={() => void handleRefund(o)}
                                className="px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold cursor-pointer"
                              >
                                Estornar Pix
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'pix' && barSettings && (
          <form
            onSubmit={handleSavePixSettings}
            className="max-w-2xl linen-card rounded-3xl border border-[#ecd0b1] p-6 sm:p-8 space-y-6"
          >
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-2xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
                <Banknote className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-display text-2xl font-bold text-[#2d1810]">
                  Recebimento Pix do Bar
                </h3>
                <p className="text-xs text-[#69432e]">
                  Os pagamentos dos clientes caem diretamente na conta Mercado Pago deste bar.
                </p>
              </div>
            </div>

            {pixSavedMsg && (
              <div className="p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs font-bold text-emerald-800 flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-600" />
                <span>{pixSavedMsg}</span>
              </div>
            )}

            {pixErrorMsg && (
              <div className="p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-xs font-bold text-rose-800 leading-relaxed">
                ⚠️ {pixErrorMsg}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setProvider('simulated')}
                className={`p-4 rounded-2xl border-2 text-left cursor-pointer transition-all ${
                  provider === 'simulated'
                    ? 'border-[#ea580c] bg-[#fff5e4]'
                    : 'border-[#ecd0b1] bg-white'
                }`}
              >
                <strong className="block text-sm text-[#2d1810]">
                  🧪 Modo Pix Simulado (Testes)
                </strong>
                <span className="text-xs text-[#7c533d]">
                  Gera QR Code e Copia e Cola com botão de aprovação em 1 clique para demonstrações.
                </span>
              </button>

              <button
                type="button"
                onClick={() => setProvider('mercadopago')}
                className={`p-4 rounded-2xl border-2 text-left cursor-pointer transition-all ${
                  provider === 'mercadopago'
                    ? 'border-emerald-600 bg-emerald-50/70'
                    : 'border-[#ecd0b1] bg-white'
                }`}
              >
                <strong className="block text-sm text-[#2d1810]">
                  🏦 Mercado Pago Pix Real
                </strong>
                <span className="text-xs text-[#7c533d]">
                  Gera cobranças Pix oficiais do Banco Central direto na conta do seu bar.
                </span>
              </button>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-bold text-[#69432e]">
                Access Token do Mercado Pago (Produção <code>APP_USR-...</code> ou Teste{' '}
                <code>TEST-...</code>)
              </label>
              <div className="relative">
                <input
                  type={showMpToken ? 'text' : 'password'}
                  name="mp_api_access_token_field"
                  autoComplete="off"
                  spellCheck={false}
                  value={mpToken}
                  onChange={(e) => {
                    setMpToken(e.target.value);
                    setPixErrorMsg(null);
                  }}
                  placeholder={
                    barSettings.has_mp_token
                      ? `Já configurado (${barSettings.mp_token_masked}) — cole aqui apenas se quiser trocar`
                      : 'Cole aqui o Access Token (APP_USR-...) do Mercado Pago Developers'
                  }
                  className="w-full pl-4 pr-24 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-xs sm:text-sm font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowMpToken((prev) => !prev)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-[#f7ead8] hover:bg-[#efdabc] text-[11px] font-bold text-[#5c3724] cursor-pointer"
                >
                  {showMpToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  {showMpToken ? 'Ocultar' : 'Mostrar'}
                </button>
              </div>

              {mpToken.trim() !== '' && (() => {
                const trimmed = mpToken.trim().replace(/^Bearer\s+/i, '');
                const isUrl = /^https?:\/\//i.test(trimmed);
                const isPubKey = /^(APP_USR|TEST)-[0-9a-f]{8}-[0-9a-f]{4}-/i.test(trimmed);
                const isGoodPrefix = trimmed.startsWith('APP_USR-') || trimmed.startsWith('TEST-');
                if (isUrl) {
                  return (
                    <p className="text-[11px] font-bold text-rose-700">
                      ⚠️ Atenção: você colou um link web (<code>{trimmed.slice(0, 28)}</code>) em vez do Access Token!
                    </p>
                  );
                }
                if (isPubKey) {
                  return (
                    <p className="text-[11px] font-bold text-rose-700">
                      ⚠️ Essa é a <strong>Public Key</strong> (curta). Copie o 2º campo logo abaixo dela chamado <strong>Access Token</strong>!
                    </p>
                  );
                }
                if (!isGoodPrefix || trimmed.length < 48) {
                  return (
                    <p className="text-[11px] font-bold text-amber-700">
                      ⚠️ O Access Token oficial começa com <code>APP_USR-</code> (ou <code>TEST-</code>) e tem cerca de 70 caracteres.
                    </p>
                  );
                }
                return (
                  <p className="text-[11px] font-bold text-emerald-700">
                    ✓ Formato de Access Token reconhecido ({trimmed.slice(0, 12)}••• · {trimmed.length} caracteres).
                  </p>
                );
              })()}

              <div className="p-3 rounded-2xl bg-amber-50/80 border border-amber-200 text-[11px] text-[#69432e] leading-relaxed">
                <strong>Dica rápida:</strong> No painel <em>Mercado Pago Developers → Credenciais de produção</em> existem 2 linhas:
                ignore a 1ª (<em>Public Key</em>) e clique no ícone de copiar da <strong>2ª linha (Access Token)</strong>. Use o botão{' '}
                <strong>Mostrar</strong> acima para conferir se começa com <code>APP_USR-</code>.
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-[#fdf5ea] border border-[#ecd3b5] text-xs space-y-1.5 text-[#5c3724]">
              <div>
                <strong>Webhook Automático deste Bar:</strong>{' '}
                <code className="bg-white px-2 py-0.5 rounded border border-[#e5c7a3]">
                  {barSettings.public_base_url}/api/webhooks/mercadopago/{barSettings.id}
                </code>
              </div>
              <div>
                <strong>Taxa da Plataforma (Split):</strong>{' '}
                <span>{barSettings.platform_fee_percent}% por pedido pago</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={savingPix}
                className="px-6 py-3.5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white font-bold text-sm shadow-md cursor-pointer disabled:opacity-60"
              >
                {savingPix ? 'Salvando...' : 'Salvar Configuração de Pagamento'}
              </button>

              <button
                type="button"
                disabled={testingPix || (!mpToken.trim() && !barSettings.has_mp_token)}
                onClick={() => void handleTestMercadoPago()}
                className="px-5 py-3.5 rounded-2xl bg-[#2d1810] hover:bg-[#432519] text-white font-bold text-sm shadow-sm cursor-pointer disabled:opacity-40"
              >
                {testingPix ? 'Verificando no Mercado Pago...' : '🔍 Testar Conexão Mercado Pago'}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
};

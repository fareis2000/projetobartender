import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  Banknote,
  Citrus,
  CreditCard,
  ExternalLink,
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

type AdminTab = 'bottles' | 'drinks' | 'machines' | 'orders' | 'pix';

export const BarAdminPage: React.FC = () => {
  const [user, setUser] = useState<PrincipalUser | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

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
  const [savingPix, setSavingPix] = useState(false);
  const [pixSavedMsg, setPixSavedMsg] = useState<string | null>(null);

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

  const handleLogout = () => {
    setStoredAuthToken(null);
    setUser(null);
  };

  const handleSavePixSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingPix(true);
    setPixSavedMsg(null);
    try {
      const updated = await bartenderApi.updateBarSettings({
        payment_provider: provider,
        ...(mpToken.trim() ? { mp_access_token: mpToken.trim() } : {}),
      });
      setBarSettings(updated);
      setMpToken('');
      setPixSavedMsg('Configurações de Pix salvas com sucesso!');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Erro ao salvar configurações Pix.');
    } finally {
      setSavingPix(false);
    }
  };

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
              <div className="p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs font-bold text-emerald-800">
                {pixSavedMsg}
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

            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Access Token do Mercado Pago (Produção <code>APP_USR-...</code> ou Teste{' '}
                <code>TEST-...</code>)
              </label>
              <input
                type="password"
                value={mpToken}
                onChange={(e) => setMpToken(e.target.value)}
                placeholder={
                  barSettings.has_mp_token
                    ? `Já configurado (${barSettings.mp_token_masked}) — digite apenas para substituir`
                    : 'Cole aqui seu Access Token do Mercado Pago Developers'
                }
                className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-mono"
              />
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

            <button
              type="submit"
              disabled={savingPix}
              className="px-6 py-3.5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white font-bold text-sm shadow-md cursor-pointer"
            >
              {savingPix ? 'Salvando...' : 'Salvar Configuração de Pagamento'}
            </button>
          </form>
        )}
      </main>
    </div>
  );
};

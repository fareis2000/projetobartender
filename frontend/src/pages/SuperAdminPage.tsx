import React, { useCallback, useEffect, useState } from 'react';
import {
  Building2,
  ExternalLink,
  LogOut,
  Plus,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { bartenderApi } from '../api/client';
import type { BarSummary, PlatformOverview, PrincipalUser } from '../types/bartender';
import {
  formatBrl,
  getStoredAuthToken,
  navigateTo,
  setInspectBarId,
  setStoredAuthToken,
} from '../utils/format';

export const SuperAdminPage: React.FC = () => {
  const [user, setUser] = useState<PrincipalUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [overview, setOverview] = useState<PlatformOverview | null>(null);

  const [email, setEmail] = useState('superadmin@bartender.os');
  const [password, setPassword] = useState('admin123');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // Novo Bar
  const [formOpen, setFormOpen] = useState(false);
  const [barName, setBarName] = useState('');
  const [barSlug, setBarSlug] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');
  const [ownerPassword, setOwnerPassword] = useState('');
  const [feePct, setFeePct] = useState(5);
  const [machName, setMachName] = useState('Máquina #01 · Balcão');
  const [machSlug, setMachSlug] = useState('');

  const loadOverview = useCallback(async () => {
    const data = await bartenderApi.getPlatformOverview();
    setOverview(data);
  }, []);

  useEffect(() => {
    const run = async () => {
      const tok = getStoredAuthToken();
      if (!tok) {
        setChecking(false);
        return;
      }
      try {
        const me = await bartenderApi.getMe();
        if (me.role === 'superadmin') {
          setUser(me);
          await loadOverview();
        }
      } catch {
        setStoredAuthToken(null);
      } finally {
        setChecking(false);
      }
    };
    void run();
  }, [loadOverview]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrMsg(null);
    try {
      const res = await bartenderApi.login(email, password);
      if (res.user.role !== 'superadmin') {
        setErrMsg('Esta conta pertence a um bar. Use o login Super-Admin da plataforma.');
        return;
      }
      setStoredAuthToken(res.access_token);
      setUser(res.user);
      await loadOverview();
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : 'Erro ao autenticar.');
    }
  };

  const handleCreateBar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await bartenderApi.createBarTenant({
        name: barName.trim(),
        slug: barSlug.trim().toLowerCase(),
        owner_name: ownerName.trim(),
        owner_email: ownerEmail.trim().toLowerCase(),
        owner_password: ownerPassword,
        platform_fee_percent: Number(feePct),
        initial_machine_name: machName.trim(),
        initial_machine_slug: machSlug.trim().toLowerCase(),
      });
      setFormOpen(false);
      setBarName('');
      setBarSlug('');
      setOwnerName('');
      setOwnerEmail('');
      setOwnerPassword('');
      setMachSlug('');
      await loadOverview();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Erro ao cadastrar bar.');
    }
  };

  const handleOpenBarPanel = (bar: BarSummary) => {
    setInspectBarId(bar.id);
    navigateTo('/painel');
  };

  const handleDeleteBar = async (bar: BarSummary) => {
    if (!window.confirm(`Excluir o bar "${bar.name}" e todas as máquinas vinculadas?`)) return;
    await bartenderApi.deleteBarTenant(bar.id);
    await loadOverview();
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm font-bold text-[#69432e]">
        Carregando Super-Admin...
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="w-full max-w-md linen-card rounded-[32px] border border-[#ecd0b1] p-8 space-y-6 shadow-xl">
          <div className="text-center space-y-2">
            <div className="w-12 h-12 mx-auto rounded-2xl bg-[#2d1810] text-amber-400 flex items-center justify-center">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h1 className="font-display text-3xl font-extrabold text-[#2d1810]">
              Super-Admin SaaS
            </h1>
            <p className="text-xs text-[#7c533d]">
              Gestão central de todos os Bares clientes, Máquinas vendidas e Split Pix.
            </p>
          </div>

          {errMsg && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs font-bold text-rose-700">
              {errMsg}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">E-mail Master</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-semibold"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Senha Master</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-semibold"
              />
            </div>
            <button
              type="submit"
              className="w-full py-3.5 rounded-2xl bg-[#2d1810] text-white font-bold text-sm cursor-pointer"
            >
              Acessar Console Multi-Bares
            </button>
          </form>

          <button
            type="button"
            onClick={() => navigateTo('/painel')}
            className="w-full text-center text-xs font-bold text-[#b45309] hover:underline cursor-pointer"
          >
            ← Ir para Login do Dono do Bar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-[#ead0b2] bg-[#2d1810] text-[#fff8ee]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-6 h-6 text-amber-400" />
            <div>
              <h1 className="font-display text-xl font-extrabold">
                Bartender.OS · Console Super-Admin (Multi-Bares)
              </h1>
              <span className="text-xs text-amber-200/80">{user.email}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setStoredAuthToken(null);
              setUser(null);
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-bold cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" /> Sair
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {overview && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Bares Ativos</span>
              <strong className="block font-display text-3xl font-extrabold text-[#2d1810]">
                {overview.active_bars} / {overview.total_bars}
              </strong>
            </div>
            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Máquinas Instaladas</span>
              <strong className="block font-display text-3xl font-extrabold text-[#2d1810]">
                {overview.total_machines}
              </strong>
            </div>
            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Volume Pix Total</span>
              <strong className="block font-display text-2xl font-extrabold text-[#15803d]">
                {formatBrl(overview.total_gross_cents)}
              </strong>
            </div>
            <div className="linen-card rounded-2xl border border-[#ecd0b1] p-4">
              <span className="text-xs font-semibold text-[#7c533d]">Receita Split Plataforma</span>
              <strong className="block font-display text-2xl font-extrabold text-[#ea580c]">
                {formatBrl(overview.total_platform_fees_cents)}
              </strong>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-display text-2xl font-bold text-[#2d1810]">
            Estabelecimentos Clientes
          </h2>
          <button
            type="button"
            onClick={() => setFormOpen((v) => !v)}
            className="inline-flex items-center gap-2 px-5 py-3 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white text-sm font-bold shadow-md cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Cadastrar Novo Bar Cliente</span>
          </button>
        </div>

        {formOpen && (
          <form
            onSubmit={handleCreateBar}
            className="linen-card rounded-3xl border-2 border-[#dfa974] p-6 grid grid-cols-1 md:grid-cols-3 gap-4"
          >
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Nome do Bar *</label>
              <input
                required
                value={barName}
                onChange={(e) => {
                  setBarName(e.target.value);
                  if (!barSlug) {
                    setBarSlug(
                      e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, '-')
                        .replace(/^-|-$/g, ''),
                    );
                  }
                }}
                placeholder="Ex.: Bar do Zé"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Slug do Bar *</label>
              <input
                required
                pattern="^[a-z0-9-]+$"
                value={barSlug}
                onChange={(e) => setBarSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                placeholder="bar-do-ze"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Taxa Split Plataforma (%)
              </label>
              <input
                type="number"
                min={0}
                max={50}
                step={0.5}
                value={feePct}
                onChange={(e) => setFeePct(Number(e.target.value))}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-bold"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Nome Responsável *</label>
              <input
                required
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">E-mail de Login *</label>
              <input
                type="email"
                required
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">Senha Inicial *</label>
              <input
                type="text"
                required
                minLength={4}
                value={ownerPassword}
                onChange={(e) => setOwnerPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Nome 1ª Máquina Vendida *
              </label>
              <input
                required
                value={machName}
                onChange={(e) => setMachName(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Código QR Code da Máquina *
              </label>
              <input
                required
                pattern="^[a-z0-9-]+$"
                value={machSlug}
                onChange={(e) => setMachSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                placeholder="Ex.: maq-ze-01"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-mono"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full py-2.5 px-4 rounded-xl bg-[#15803d] text-white font-bold text-sm cursor-pointer"
              >
                Criar Conta do Bar + Máquina
              </button>
            </div>
          </form>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {overview?.bars.map((b) => (
            <div
              key={b.id}
              className="linen-card rounded-2xl border border-[#ecd0b1] p-5 flex flex-col justify-between gap-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#f6e6cf] text-[#5c3724] flex items-center justify-center">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-display text-xl font-bold text-[#2d1810]">{b.name}</h3>
                    <span className="text-xs text-[#7c533d]">
                      {b.owner_name} ({b.owner_email})
                    </span>
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900">
                  Split {b.platform_fee_percent}%
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 p-3 rounded-xl bg-[#fdf5ea] border border-[#ecd3b5] text-xs">
                <div>
                  <span className="text-[#8a614a] block">Máquinas</span>
                  <strong className="text-sm text-[#2d1810]">{b.machines_count}</strong>
                </div>
                <div>
                  <span className="text-[#8a614a] block">Faturado</span>
                  <strong className="text-sm text-[#15803d]">
                    {formatBrl(b.gross_revenue_cents)}
                  </strong>
                </div>
                <div>
                  <span className="text-[#8a614a] block">Sua Comissão</span>
                  <strong className="text-sm text-[#ea580c]">
                    {formatBrl(b.platform_fees_cents)}
                  </strong>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-[#f0dcc2]">
                <button
                  type="button"
                  onClick={() => handleOpenBarPanel(b)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#2d1810] text-white text-xs font-bold cursor-pointer"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Gerenciar Garrafas / Drinks deste Bar
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteBar(b)}
                  className="p-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 cursor-pointer"
                  title="Excluir bar"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
};

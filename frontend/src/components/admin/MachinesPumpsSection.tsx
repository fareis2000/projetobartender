import React, { useState } from 'react';
import {
  Copy,
  ExternalLink,
  OctagonAlert,
  Plus,
  QrCode,
  RefreshCw,
  Save,
  Wifi,
} from 'lucide-react';
import { bartenderApi } from '../../api/client';
import type { Bottle, ConnectionMode, Machine, PumpId } from '../../types/bartender';
import { formatBrl, formatPerMl, navigateTo } from '../../utils/format';

interface MachinesPumpsSectionProps {
  machines: Machine[];
  bottles: Bottle[];
  onRefresh: (probe?: boolean) => Promise<void>;
}

export const MachinesPumpsSection: React.FC<MachinesPumpsSectionProps> = ({
  machines,
  bottles,
  onRefresh,
}) => {
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');
  const [busy, setBusy] = useState(false);
  const [flowDrafts, setFlowDrafts] = useState<Record<string, string>>({});

  const handleCreateMachine = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await bartenderApi.createMachine({
        name: newName.trim(),
        slug: newSlug.trim().toLowerCase(),
        cup_fee_cents: 150,
        min_order_cents: 500,
        max_cup_ml: 450,
        allow_custom_builder: true,
        connection_mode: 'auto',
      });
      setNewOpen(false);
      setNewName('');
      setNewSlug('');
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Erro ao adicionar máquina.');
    } finally {
      setBusy(false);
    }
  };

  const handleBottleSelect = async (machineId: string, pumpId: PumpId, bottleId: string) => {
    await bartenderApi.updatePumpSlot(machineId, pumpId, {
      bottle_id: bottleId || null,
    });
    await onRefresh();
  };

  const handleRefillFull = async (machineId: string, pumpId: PumpId) => {
    await bartenderApi.refillPump(machineId, pumpId);
    await onRefresh();
  };

  const handleSaveFlow = async (machineId: string, pumpId: PumpId, defaultFlow: number) => {
    const key = `${machineId}:${pumpId}`;
    const val = parseFloat(flowDrafts[key] ?? String(defaultFlow));
    if (Number.isNaN(val) || val <= 1) return;
    await bartenderApi.updatePumpSlot(machineId, pumpId, { flow_rate_ml_s: val });
    await onRefresh();
  };

  const handleUpdateMachineConfig = async (
    m: Machine,
    patch: Record<string, unknown>,
  ) => {
    await bartenderApi.updateMachine(m.id, patch);
    await onRefresh(true);
  };

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="font-display text-2xl font-bold text-[#2d1810]">
            Máquinas, Bombas & QR Codes do Bar
          </h3>
          <p className="text-xs sm:text-sm text-[#69432e]">
            Imprima o QR Code de cada máquina, vincule as garrafas às 4 bombas e acompanhe os ml
            restantes.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void onRefresh(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-2xl bg-[#f6e6cf] text-xs font-bold text-[#5c3724] cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Testar Conexão
          </button>
          <button
            type="button"
            onClick={() => setNewOpen((v) => !v)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white text-xs sm:text-sm font-bold shadow-md cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Nova Máquina</span>
          </button>
        </div>
      </div>

      {newOpen && (
        <form
          onSubmit={handleCreateMachine}
          className="linen-card rounded-3xl border-2 border-[#dfa974] p-5 grid grid-cols-1 sm:grid-cols-3 gap-3 items-end"
        >
          <div>
            <label className="block text-xs font-bold text-[#69432e] mb-1">Nome da Máquina</label>
            <input
              required
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Ex.: Máquina #02 · Pista VIP"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-[#69432e] mb-1">
              Código do QR Code (apenas letras/números/traço)
            </label>
            <input
              required
              pattern="^[a-z0-9-]+$"
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
              placeholder="Ex.: maq-vip-02"
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="py-2.5 px-4 rounded-xl bg-[#15803d] text-white font-bold text-sm cursor-pointer"
          >
            Criar Máquina e QR Code
          </button>
        </form>
      )}

      {machines.map((m) => (
        <div
          key={m.id}
          className="linen-card rounded-[28px] border border-[#ecd0b1] p-6 space-y-6"
        >
          {/* Topo: QR Code + Status + Config Rápida */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center border-b border-[#eed6b8] pb-6">
            <div className="lg:col-span-3 flex flex-col items-center p-4 rounded-2xl bg-white border border-[#ebd0b2] text-center space-y-2">
              <img
                src={`/api/public/m/${encodeURIComponent(m.slug)}/qr.svg`}
                alt={`QR ${m.slug}`}
                className="w-36 h-36"
              />
              <span className="text-xs font-mono font-bold text-[#2d1810]">/m/{m.slug}</span>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(m.qr_url)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#f6e6cf] text-[11px] font-bold text-[#5c3724] cursor-pointer"
                >
                  <Copy className="w-3 h-3" /> Link
                </button>
                <a
                  href={`/api/public/m/${encodeURIComponent(m.slug)}/qr.svg`}
                  download={`qrcode-${m.slug}.svg`}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#2d1810] text-[11px] font-bold text-white"
                >
                  <QrCode className="w-3 h-3" /> Baixar SVG
                </a>
                <button
                  type="button"
                  onClick={() => navigateTo(`/m/${m.slug}`)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-600 text-[11px] font-bold text-white cursor-pointer"
                >
                  <ExternalLink className="w-3 h-3" /> Abrir
                </button>
              </div>
            </div>

            <div className="lg:col-span-9 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h4 className="font-display text-2xl font-bold text-[#2d1810]">{m.name}</h4>
                  <p className="text-xs text-[#69432e] flex items-center gap-1.5 mt-0.5">
                    <Wifi className="w-3.5 h-3.5 text-emerald-600" />
                    <span>{m.hardware.detail}</span>
                  </p>
                </div>

                {m.status.state === 'dispensing' && (
                  <button
                    type="button"
                    onClick={() => void bartenderApi.emergencyStopMachine(m.id).then(() => onRefresh())}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 text-white text-xs font-bold cursor-pointer"
                  >
                    <OctagonAlert className="w-4 h-4" />
                    Parada de Emergência
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                    Modo de Conexão ESP
                  </label>
                  <select
                    value={m.connection_mode}
                    onChange={(e) =>
                      void handleUpdateMachineConfig(m, {
                        connection_mode: e.target.value as ConnectionMode,
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-xs font-bold"
                  >
                    <option value="auto">Automático Inteligente</option>
                    <option value="cloud_iot">Wi-Fi do Bar → Nuvem (IoT)</option>
                    <option value="wifi">LAN Direta (IP Local)</option>
                    <option value="serial">Cabo USB Serial</option>
                    <option value="simulator">Modo Simulador</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                    Taxa Copo/Gelo (R$)
                  </label>
                  <input
                    type="number"
                    step="0.50"
                    min="0"
                    defaultValue={(m.cup_fee_cents / 100).toFixed(2)}
                    onBlur={(e) =>
                      void handleUpdateMachineConfig(m, {
                        cup_fee_cents: Math.round((parseFloat(e.target.value) || 0) * 100),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-xs font-bold"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                    Pedido Mínimo (R$)
                  </label>
                  <input
                    type="number"
                    step="1.00"
                    min="1.00"
                    defaultValue={(m.min_order_cents / 100).toFixed(2)}
                    onBlur={(e) =>
                      void handleUpdateMachineConfig(m, {
                        min_order_cents: Math.max(100, Math.round((parseFloat(e.target.value) || 5) * 100)),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-xs font-bold"
                  />
                </div>

                <div className="flex items-end pb-1.5">
                  <label className="inline-flex items-center gap-2 text-xs font-bold text-[#2d1810] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={m.allow_custom_builder}
                      onChange={(e) =>
                        void handleUpdateMachineConfig(m, {
                          allow_custom_builder: e.target.checked,
                        })
                      }
                      className="w-4 h-4 accent-emerald-600"
                    />
                    <span>Permitir "Monte por ml"</span>
                  </label>
                </div>
              </div>

              {/* Credenciais para gravar no ESP8266/ESP32 do Bar */}
              <details className="rounded-xl bg-[#fdf5ea] border border-[#ecd3b5] p-3 text-xs">
                <summary className="font-bold text-[#5c3724] cursor-pointer">
                  🔌 Ver credenciais Wi-Fi IoT para gravar no ESP8266/ESP32 desta máquina (secrets.h)
                </summary>
                <pre className="mt-2 p-3 rounded-lg bg-[#2d1810] text-[#fff8ee] overflow-x-auto text-[11px] font-mono">
{`#define SECRET_API_TOKEN      "${m.api_token}"
#define SECRET_CLOUD_SYNC_URL "${window.location.origin}/api/iot/${m.slug}/sync"`}
                </pre>
              </details>
            </div>
          </div>

          {/* As 4 Bombas Físicas da Máquina */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {m.pumps.map((p) => {
              const pct = p.bottle_id
                ? Math.min(100, Math.round((p.remaining_ml / Math.max(p.bottle_volume_ml, 1)) * 100))
                : 0;
              const fKey = `${m.id}:${p.pump_id}`;

              return (
                <div
                  key={p.pump_id}
                  className="p-4 rounded-2xl bg-white border border-[#ebd0b2] space-y-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-extrabold uppercase tracking-wider text-[#7c533d]">
                      {p.label} (GPIO {p.gpio})
                    </span>
                    {p.bottle_id && (
                      <span className="text-xs font-bold text-[#15803d]">
                        {formatPerMl(p.price_per_liter_cents)}/ml · 50ml:{' '}
                        {formatBrl(Math.round((50 * p.price_per_liter_cents) / 1000))}
                      </span>
                    )}
                  </div>

                  {/* Dropdown de Garrafa do CRUD */}
                  <div>
                    <label className="block text-[11px] font-semibold text-[#7c533d] mb-1">
                      Garrafa espetada nesta mangueira:
                    </label>
                    <select
                      value={p.bottle_id ?? ''}
                      onChange={(e) => void handleBottleSelect(m.id, p.pump_id, e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-[#fffaf2] border border-[#e5c7a3] text-xs sm:text-sm font-bold text-[#2d1810]"
                    >
                      <option value="">— Sem Garrafa Instalada —</option>
                      {bottles.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} ({b.bottle_volume_ml}ml · {formatPerMl(b.price_per_liter_cents)}/ml)
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Nível Restante + Botão Trocar Garrafa */}
                  {p.bottle_id && (
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-[#69432e]">
                          Nível na garrafa: <strong>{Math.round(p.remaining_ml)} ml</strong> de{' '}
                          {p.bottle_volume_ml} ml
                        </span>
                        <strong className={pct < 20 ? 'text-rose-600' : 'text-emerald-700'}>
                          {pct}%
                        </strong>
                      </div>
                      <div className="h-2.5 w-full rounded-full bg-[#f3e3ce] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: pct < 20 ? '#e11d48' : p.color_hex,
                          }}
                        />
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    {p.bottle_id ? (
                      <button
                        type="button"
                        onClick={() => void handleRefillFull(m.id, p.pump_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold cursor-pointer"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Troquei por Garrafa Cheia ({p.bottle_volume_ml}ml)
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400">Selecione uma garrafa acima</span>
                    )}

                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-[#7c533d]">Vazão:</span>
                      <input
                        type="number"
                        step="0.5"
                        min="2"
                        max="150"
                        value={flowDrafts[fKey] ?? String(p.flow_rate_ml_s)}
                        onChange={(e) =>
                          setFlowDrafts((prev) => ({ ...prev, [fKey]: e.target.value }))
                        }
                        className="w-16 px-2 py-1 rounded-lg border border-[#e5c7a3] text-xs font-bold text-center"
                      />
                      <span className="text-[11px] text-[#7c533d]">ml/s</span>
                      <button
                        type="button"
                        onClick={() => void handleSaveFlow(m.id, p.pump_id, p.flow_rate_ml_s)}
                        className="p-1.5 rounded-lg bg-[#2d1810] text-white cursor-pointer"
                        title="Salvar calibração ml/s"
                      >
                        <Save className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  Droplets,
  Minus,
  Plus,
  QrCode,
  RotateCcw,
  Sparkles,
  Wine,
} from 'lucide-react';
import type { PumpId, PumpSlot } from '../types/bartender';
import { formatBrl, formatPerMl } from '../utils/format';
import { GlassArtwork } from './GlassArtwork';

interface CustomDrinkBuilderProps {
  pumps: PumpSlot[];
  maxCupMl: number;
  cupFeeCents: number;
  minOrderCents: number;
  busyCreating: boolean;
  onSubmitCustom: (payload: {
    name: string;
    amarelo: number;
    vermelho: number;
    verde: number;
    azul: number;
  }) => void;
}

const PUMP_ORDER: PumpId[] = ['amarelo', 'vermelho', 'verde', 'azul'];

export const CustomDrinkBuilder: React.FC<CustomDrinkBuilderProps> = ({
  pumps,
  maxCupMl,
  cupFeeCents,
  minOrderCents,
  busyCreating,
  onSubmitCustom,
}) => {
  const [name, setName] = useState('Meu Drink Exclusivo');
  const [volumes, setVolumes] = useState<Record<PumpId, number>>(() => {
    const initial: Record<PumpId, number> = { amarelo: 0, vermelho: 0, verde: 0, azul: 0 };
    for (const p of pumps) {
      if (p.bottle_id && p.available_ml >= 50) {
        if (p.is_mixer) {
          initial[p.pump_id] = Math.min(200, Math.floor(p.available_ml / 5) * 5);
        } else if (initial.amarelo === 0 && initial.vermelho === 0) {
          initial[p.pump_id] = 50;
        }
      }
    }
    return initial;
  });

  const pumpsById = useMemo(() => {
    const map = {} as Record<PumpId, PumpSlot>;
    for (const p of pumps) map[p.pump_id] = p;
    return map;
  }, [pumps]);

  const totalMl = volumes.amarelo + volumes.vermelho + volumes.verde + volumes.azul;
  const overLimit = totalMl > maxCupMl;
  const underLimit = totalMl < 10;

  // Cálculo ao vivo de preço por ml idêntico ao servidor!
  const pricing = useMemo(() => {
    let liquidsCents = 0;
    let isAlc = false;
    let sec = 0;
    let activeCount = 0;

    for (const pid of PUMP_ORDER) {
      const ml = volumes[pid];
      const slot = pumpsById[pid];
      if (ml > 0 && slot) {
        activeCount++;
        liquidsCents += Math.round((ml * slot.price_per_liter_cents) / 1000);
        if (slot.is_alcoholic) isAlc = true;
        sec += ml / Math.max(slot.flow_rate_ml_s, 1);
      }
    }
    if (activeCount > 1) sec += (activeCount - 1) * 1.2;

    const rawTotal = liquidsCents + cupFeeCents;
    const finalTotal = totalMl >= 10 ? Math.max(minOrderCents, rawTotal) : 0;

    return {
      liquidsCents,
      rawTotal,
      finalTotal,
      minApplied: totalMl >= 10 && rawTotal < minOrderCents,
      isAlc,
      estimatedSeconds: Math.round(sec * 10) / 10,
    };
  }, [volumes, pumpsById, cupFeeCents, minOrderCents, totalMl]);

  const setPumpVolume = (pid: PumpId, nextVal: number) => {
    const slot = pumpsById[pid];
    const maxBottle = slot?.bottle_id ? Math.floor(slot.available_ml / 5) * 5 : 0;
    const maxAllowed = Math.min(350, maxCupMl, maxBottle);
    const clamped = Math.max(0, Math.min(maxAllowed, Math.round(nextVal / 5) * 5));
    setVolumes((prev) => ({ ...prev, [pid]: clamped }));
  };

  const resetAll = () => {
    setVolumes({ amarelo: 0, vermelho: 0, verde: 0, azul: 0 });
  };

  const layers = PUMP_ORDER.map((pid) => ({
    color: pumpsById[pid]?.color_hex ?? '#f97316',
    ml: volumes[pid],
    label: pumpsById[pid]?.ingredient ?? pid,
  }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (overLimit || underLimit || busyCreating) return;
    onSubmitCustom({
      name: name.trim() || 'Drink Personalizado',
      ...volumes,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
      {/* Coluna Esquerda: Sliders por Bomba com Preço por ml */}
      <div className="lg:col-span-7 linen-card rounded-[32px] border border-[#ecd0b1] p-6 sm:p-8 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-[#15803d]">
              <Sparkles className="w-3.5 h-3.5" />
              Precificação Justa ao Mililitro
            </span>
            <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#2d1810] mt-0.5">
              Monte seu Drink na Medida
            </h2>
          </div>

          <button
            type="button"
            onClick={resetAll}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#f7ead8] hover:bg-[#efe0ca] text-[#69432e] transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Zerar Copo
          </button>
        </div>

        <div>
          <label className="block text-xs font-bold text-[#69432e] mb-1.5">
            Dê um nome para sua criação (aparece no seu pedido)
          </label>
          <input
            type="text"
            maxLength={45}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810] focus:outline-none focus:border-[#ea580c]"
            placeholder="Ex.: Mix Tropical da Mesa 4"
          />
        </div>

        {/* Lista das 4 Bombas */}
        <div className="space-y-4">
          {PUMP_ORDER.map((pid) => {
            const slot = pumpsById[pid];
            if (!slot) return null;
            const ml = volumes[pid];
            const hasBottle = Boolean(slot.bottle_id) && slot.available_ml >= 5;
            const maxForSlider = hasBottle ? Math.min(350, maxCupMl, Math.floor(slot.available_ml / 5) * 5) : 0;
            const lineCents = Math.round((ml * slot.price_per_liter_cents) / 1000);

            return (
              <div
                key={pid}
                className={`p-4 sm:p-5 rounded-2xl border transition-all ${
                  ml > 0
                    ? 'bg-white border-[#dfa974] shadow-xs'
                    : 'bg-[#fdf6ec]/80 border-[#ecd3b5]'
                } ${!hasBottle ? 'opacity-55' : ''}`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    <span
                      className="w-4 h-4 rounded-full shrink-0 shadow-xs"
                      style={{ backgroundColor: slot.color_hex }}
                    />
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm sm:text-base text-[#2d1810]">
                          {slot.ingredient}
                        </span>
                        {slot.is_alcoholic && (
                          <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-600 text-white">
                            <Wine className="w-2.5 h-2.5" /> +18
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[#7c533d]">
                        {hasBottle ? (
                          <>
                            <strong>{formatPerMl(slot.price_per_liter_cents)}/ml</strong> · Dose 50ml:{' '}
                            {formatBrl(Math.round((50 * slot.price_per_liter_cents) / 1000))}
                          </>
                        ) : (
                          'Ingrediente esgotado ou indisponível nesta bomba'
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="font-display text-xl font-extrabold text-[#2d1810]">
                      {ml} <small className="text-xs font-sans-ui font-semibold">ml</small>
                    </span>
                    <span className="block text-xs font-bold text-[#15803d]">
                      + {formatBrl(lineCents)}
                    </span>
                  </div>
                </div>

                <input
                  type="range"
                  min={0}
                  max={Math.max(5, maxForSlider)}
                  step={5}
                  disabled={!hasBottle}
                  value={ml}
                  onChange={(e) => setPumpVolume(pid, Number(e.target.value))}
                  className="w-full accent-[#ea580c] cursor-pointer disabled:cursor-not-allowed"
                />

                <div className="flex items-center justify-between gap-2 mt-2.5">
                  <span className="text-[11px] text-[#8a614a]">
                    Disponível: {Math.floor(slot.available_ml)} ml
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      disabled={!hasBottle || ml <= 0}
                      onClick={() => setPumpVolume(pid, ml - 25)}
                      className="px-2.5 py-1 rounded-lg bg-[#f6e6cf] hover:bg-[#ecd3b3] text-xs font-bold text-[#5c3724] disabled:opacity-40 cursor-pointer"
                    >
                      <Minus className="w-3 h-3 inline" /> 25ml
                    </button>
                    <button
                      type="button"
                      disabled={!hasBottle || ml >= maxForSlider}
                      onClick={() => setPumpVolume(pid, ml + 25)}
                      className="px-2.5 py-1 rounded-lg bg-[#f6e6cf] hover:bg-[#ecd3b3] text-xs font-bold text-[#5c3724] disabled:opacity-40 cursor-pointer"
                    >
                      <Plus className="w-3 h-3 inline" /> 25ml
                    </button>
                    <button
                      type="button"
                      disabled={!hasBottle || ml >= maxForSlider}
                      onClick={() => setPumpVolume(pid, ml + 50)}
                      className="px-2.5 py-1 rounded-lg bg-[#ea580c]/15 hover:bg-[#ea580c]/25 text-xs font-bold text-[#b45309] disabled:opacity-40 cursor-pointer"
                    >
                      +50ml
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Coluna Direita: Preview do Copo + Resumo Financeiro + Botão Pix */}
      <div className="lg:col-span-5 linen-card rounded-[32px] border border-[#ecd0b1] p-6 sm:p-8 space-y-6 lg:sticky lg:top-24">
        <div className="flex flex-col items-center justify-center py-5 rounded-3xl bg-gradient-to-b from-[#fff5e4] to-[#ffe6c4] border border-[#edd2b2]">
          <GlassArtwork layers={layers} maxCapacityMl={maxCupMl} size="lg" />
        </div>

        {/* Métricas e Subtotal */}
        <div className="space-y-2.5 text-sm">
          <div className="flex justify-between text-[#69432e]">
            <span className="inline-flex items-center gap-1.5">
              <Droplets className="w-4 h-4 text-sky-600" />
              Volume Total no Copo
            </span>
            <strong className={overLimit ? 'text-rose-600 font-bold' : 'text-[#2d1810]'}>
              {totalMl} / {maxCupMl} ml
            </strong>
          </div>

          <div className="flex justify-between text-[#69432e]">
            <span className="inline-flex items-center gap-1.5">
              <Clock className="w-4 h-4 text-amber-600" />
              Tempo Estimado de Dosagem
            </span>
            <strong className="text-[#2d1810]">~{pricing.estimatedSeconds}s</strong>
          </div>

          <div className="border-t border-[#ebd0b2] pt-2.5 space-y-1.5">
            <div className="flex justify-between text-xs text-[#7c533d]">
              <span>Soma dos líquidos ({totalMl} ml)</span>
              <span>{formatBrl(pricing.liquidsCents)}</span>
            </div>
            {cupFeeCents > 0 && (
              <div className="flex justify-between text-xs text-[#7c533d]">
                <span>Copo descartável + gelo</span>
                <span>{formatBrl(cupFeeCents)}</span>
              </div>
            )}
            {pricing.minApplied && (
              <div className="flex justify-between text-xs text-amber-700 font-medium">
                <span>Consumação mínima por copo</span>
                <span>{formatBrl(minOrderCents)}</span>
              </div>
            )}
            <div className="flex items-baseline justify-between pt-2">
              <span className="font-bold text-base text-[#2d1810]">Total a Pagar (Pix)</span>
              <span className="font-display text-3xl font-extrabold text-[#15803d]">
                {formatBrl(pricing.finalTotal)}
              </span>
            </div>
          </div>
        </div>

        {overLimit && (
          <div className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-xs font-semibold text-rose-700">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              Reduza {totalMl - maxCupMl} ml para não ultrapassar o limite de segurança do copo ({maxCupMl} ml).
            </span>
          </div>
        )}

        <button
          type="submit"
          disabled={overLimit || underLimit || busyCreating}
          className="w-full py-4 px-5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] hover:brightness-105 text-white font-sans-ui font-bold text-base shadow-lg shadow-emerald-700/20 flex items-center justify-center gap-2.5 transition-all cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed"
        >
          <QrCode className="w-5 h-5" />
          <span>
            {busyCreating
              ? 'Gerando seu Pix...'
              : underLimit
                ? 'Adicione pelo menos 10 ml'
                : `Pagar com Pix · ${formatBrl(pricing.finalTotal)}`}
          </span>
        </button>
      </div>
    </form>
  );
};

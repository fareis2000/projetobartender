import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  Droplets,
  Plus,
  RotateCcw,
  Sparkles,
  Wand2,
} from 'lucide-react';
import type { CustomDrinkPayload, PumpConfig, PumpId } from '../types/bartender';
import { GlassArtwork } from './GlassArtwork';

interface CustomDrinkBuilderProps {
  pumps: PumpConfig[];
  disabled: boolean;
  onSubmitCustom: (payload: CustomDrinkPayload) => void;
}

const MAX_CUP_ML = 450;
const PUMP_ORDER: PumpId[] = ['amarelo', 'vermelho', 'verde', 'azul'];

const QUICK_PRESETS: Array<{
  label: string;
  name: string;
  volumes: Record<PumpId, number>;
}> = [
  {
    label: 'Equilíbrio Tropical (320ml)',
    name: 'Tropical Custom',
    volumes: { amarelo: 60, vermelho: 40, verde: 0, azul: 220 },
  },
  {
    label: 'Maçã Cítrica Fizz (300ml)',
    name: 'Green Citrus Fizz',
    volumes: { amarelo: 45, vermelho: 0, verde: 55, azul: 200 },
  },
  {
    label: 'Arco-Íris 4 Bombas (350ml)',
    name: 'Quad Mix',
    volumes: { amarelo: 35, vermelho: 35, verde: 35, azul: 245 },
  },
];

export const CustomDrinkBuilder: React.FC<CustomDrinkBuilderProps> = ({
  pumps,
  disabled,
  onSubmitCustom,
}) => {
  const [name, setName] = useState('Minha Criação');
  const [volumes, setVolumes] = useState<Record<PumpId, number>>({
    amarelo: 50,
    vermelho: 40,
    verde: 0,
    azul: 210,
  });

  const pumpsById = useMemo(() => {
    const map = {} as Record<PumpId, PumpConfig>;
    for (const p of pumps) map[p.id] = p;
    return map;
  }, [pumps]);

  const totalMl = volumes.amarelo + volumes.vermelho + volumes.verde + volumes.azul;
  const overLimit = totalMl > MAX_CUP_ML;
  const underLimit = totalMl < 10;

  const estimatedSeconds = useMemo(() => {
    let sec = 0;
    let activeCount = 0;
    for (const pid of PUMP_ORDER) {
      const ml = volumes[pid];
      if (ml > 0) {
        activeCount++;
        const flow = pumpsById[pid]?.flow_rate_ml_s ?? 32;
        sec += ml / flow;
      }
    }
    if (activeCount > 1) {
      sec += (activeCount - 1) * 1.2;
    }
    return Math.round(sec * 10) / 10;
  }, [volumes, pumpsById]);

  const setPumpVolume = (pid: PumpId, nextVal: number) => {
    const clamped = Math.max(0, Math.min(350, Math.round(nextVal / 5) * 5));
    setVolumes((prev) => ({ ...prev, [pid]: clamped }));
  };

  const resetAll = () => {
    setVolumes({ amarelo: 0, vermelho: 0, verde: 0, azul: 0 });
  };

  const handlePrepare = (e: React.FormEvent) => {
    e.preventDefault();
    if (overLimit || underLimit || disabled) return;
    onSubmitCustom({
      name: name.trim() || 'Mix Personalizado',
      ...volumes,
    });
  };

  const layers = PUMP_ORDER.map((pid) => ({
    color: pumpsById[pid]?.color_hex ?? '#f59e0b',
    ml: volumes[pid],
    label: pumpsById[pid]?.ingredient ?? pid,
  }));

  return (
    <form
      onSubmit={handlePrepare}
      className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start"
    >
      {/* Coluna Esquerda: Controles das 4 Bombas */}
      <div className="lg:col-span-7 space-y-6 rounded-3xl bg-[#11131d]/90 border border-white/10 p-6 sm:p-8 shadow-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-5">
          <div>
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-400">
              <Wand2 className="w-3.5 h-3.5" />
              Estúdio de Mixologia
            </span>
            <h2 className="font-display text-2xl font-bold text-white mt-1">
              Monte seu Drink ao Mililitro
            </h2>
          </div>

          <button
            type="button"
            onClick={resetAll}
            className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-white/[0.05] hover:bg-white/[0.1] border border-white/10 transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Zerar Tudo
          </button>
        </div>

        {/* Nome da Receita + Sugestões Rápidas */}
        <div className="space-y-3">
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
            Nome da sua criação
          </label>
          <input
            type="text"
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex: Sunset Especial"
            className="w-full px-4 py-2.5 rounded-xl bg-[#090b11] border border-white/12 text-white placeholder-slate-500 focus:outline-none focus:border-amber-400 text-sm"
          />

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-400 mr-1">Bases rápidas:</span>
            {QUICK_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setName(preset.name);
                  setVolumes(preset.volumes);
                }}
                className="px-2.5 py-1 rounded-lg text-xs bg-white/[0.04] hover:bg-white/[0.09] text-slate-200 border border-white/10 transition-colors cursor-pointer"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Sliders das 4 Bombas */}
        <div className="space-y-4">
          {PUMP_ORDER.map((pid) => {
            const pump = pumpsById[pid];
            if (!pump) return null;
            const val = volumes[pid];
            const maxSlider = pump.is_mixer ? 350 : 200;

            return (
              <div
                key={pid}
                className="p-4 rounded-2xl bg-[#0b0d14]/90 border border-white/8 hover:border-white/15 transition-colors"
              >
                <div className="flex items-center justify-between gap-2 mb-2.5">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-3.5 h-3.5 rounded-full shadow-sm shrink-0"
                      style={{ backgroundColor: pump.color_hex }}
                    />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-display font-semibold text-sm text-white">
                          {pump.ingredient}
                        </span>
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-white/[0.05] text-slate-400">
                          {pump.label} · GPIO {pump.gpio}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">{pump.description}</p>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="font-display text-lg font-bold text-white">
                      {val}
                    </span>
                    <span className="text-xs text-slate-400 ml-1">ml</span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={maxSlider}
                    step={5}
                    value={val}
                    onChange={(e) => setPumpVolume(pid, Number(e.target.value))}
                    style={{ '--slider-accent': pump.color_hex } as React.CSSProperties}
                    className="pump-slider flex-1"
                  />

                  <button
                    type="button"
                    onClick={() => setPumpVolume(pid, val + 25)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-white/[0.06] hover:bg-white/[0.12] text-slate-200 border border-white/10 cursor-pointer shrink-0"
                  >
                    <Plus className="w-3 h-3" />
                    25ml
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Coluna Direita: Preview do Copo em Tempo Real + Resumo */}
      <div className="lg:col-span-5 rounded-3xl bg-[#11131d]/90 border border-white/10 p-6 sm:p-8 shadow-2xl lg:sticky lg:top-24 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              Simulação Visual
            </p>
            <h3 className="font-display text-xl font-bold text-white">
              {name.trim() || 'Mix Personalizado'}
            </h3>
          </div>
          <div className="text-right">
            <span
              className={`font-display text-2xl font-bold ${
                overLimit ? 'text-rose-400' : 'text-amber-400'
              }`}
            >
              {totalMl} ml
            </span>
            <p className="text-xs text-slate-400">Máx. {MAX_CUP_ML} ml</p>
          </div>
        </div>

        {/* Copo Interativo */}
        <div className="py-4 flex flex-col items-center justify-center rounded-2xl bg-gradient-to-b from-white/[0.03] to-black/30 border border-white/6">
          <GlassArtwork layers={layers} maxCapacityMl={MAX_CUP_ML} size="lg" />
          <div className="mt-3 flex items-center gap-4 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <Droplets className="w-3.5 h-3.5 text-sky-400" />
              Capacidade: {Math.round((totalMl / MAX_CUP_ML) * 100)}%
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              Tempo estimado: ~{Math.ceil(estimatedSeconds)}s
            </span>
          </div>
        </div>

        {/* Resumo das Proporções */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Proporção no copo</span>
            <span>{totalMl} / {MAX_CUP_ML} ml</span>
          </div>
          <div className="h-3 w-full rounded-full bg-white/[0.06] overflow-hidden flex">
            {PUMP_ORDER.map((pid) => {
              const ml = volumes[pid];
              if (ml <= 0 || totalMl <= 0) return null;
              const pct = (ml / Math.max(totalMl, MAX_CUP_ML)) * 100;
              return (
                <div
                  key={pid}
                  style={{
                    width: `${pct}%`,
                    backgroundColor: pumpsById[pid]?.color_hex ?? '#fff',
                  }}
                />
              );
            })}
          </div>

          {overLimit && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 mt-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>
                Volume acima do limite de segurança ({MAX_CUP_ML} ml). Reduza algum ingrediente para evitar transbordamento.
              </span>
            </div>
          )}

          {underLimit && (
            <p className="text-xs text-slate-400 pt-1">
              Adicione pelo menos 10 ml em uma das bombas para liberar o preparo.
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={disabled || overLimit || underLimit}
          className="w-full py-3.5 px-5 rounded-xl font-display font-bold text-sm text-slate-950 bg-gradient-to-r from-amber-400 via-amber-500 to-orange-500 hover:from-amber-300 hover:to-orange-400 shadow-lg shadow-amber-500/25 flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Sparkles className="w-4 h-4" />
          <span>Preparar Minha Receita ({totalMl} ml)</span>
        </button>
      </div>
    </form>
  );
};


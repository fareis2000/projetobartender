/**
 * @file CustomDrinkBuilder.tsx
 * @description Estúdio interativo "Monte seu Drink" para criação de receitas personalizadas ao mililitro.
 *
 * Papel na Arquitetura / Engajamento em Eventos:
 * ----------------------------------------------
 * É o recurso de maior engajamento do público em festas, feiras de tecnologia e ativações:
 *   - Permite batizar o drink com o próprio nome do convidado e ajustar os 4 ingredientes em
 *     passos precisos de `5 ml` (via slider tátil ou botões `-25ml` / `+25ml`), além de contar
 *     com presets rápidos ("Sugestões da casa") para inspiração em 1 toque.
 *   - Calcula localmente e em tempo real a estimativa física de preparo (`estimatedSeconds`),
 *     somando `ml / flow_rate_ml_s` de cada bomba ativa mais as pausas inter-ingredientes (`1.2s`),
 *     espelhando exatamente a lógica do backend (`dispense_custom_drink`).
 *   - Aplica travas visuais e funcionais de segurança física: exige mínimo de `10 ml` e bloqueia
 *     envio caso a soma ultrapasse `MAX_CUP_ML` (`450 ml`), prevenindo transbordamento do copo.
 */
import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Citrus,
  Clock,
  Droplets,
  Minus,
  Plus,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import type { CustomDrinkPayload, PumpConfig, PumpId } from '../types/bartender';
import { GlassArtwork } from './GlassArtwork';

/** Propriedades do estúdio interativo `CustomDrinkBuilder`. */
interface CustomDrinkBuilderProps {
  /** Lista atualizada das 4 bombas físicas e suas vazões calibradas (`ml/s`). */
  pumps: PumpConfig[];
  /** Bloqueia o envio enquanto a máquina estiver ocupada preparando outra bebida. */
  disabled: boolean;
  /** Callback acionado ao submeter uma mistura personalizada válida. */
  onSubmitCustom: (payload: CustomDrinkPayload) => void;
}

/** Limite volumétrico de segurança por copo (espelha `MAX_CUP_ML` no backend). */
const MAX_CUP_ML = 450;

/** Ordem fixa de apresentação e empilhamento visual das camadas no copo. */
const PUMP_ORDER: PumpId[] = ['amarelo', 'vermelho', 'verde', 'azul'];

/** Combinações pré-balanceadas de 1 clique para facilitar a escolha de convidados indecisos. */
const QUICK_PRESETS: Array<{
  label: string;
  name: string;
  volumes: Record<PumpId, number>;
}> = [
  {
    label: 'Pôr do Sol Tropical (320ml)',
    name: 'Pôr do Sol Tropical',
    volumes: { amarelo: 60, vermelho: 40, verde: 0, azul: 220 },
  },
  {
    label: 'Refresco Cítrico Verde (300ml)',
    name: 'Refresco da Ilha',
    volumes: { amarelo: 45, vermelho: 0, verde: 55, azul: 200 },
  },
  {
    label: 'Salada de Frutas Fizz (350ml)',
    name: 'Mix Verão Completo',
    volumes: { amarelo: 35, vermelho: 35, verde: 35, azul: 245 },
  },
];

/**
 * Componente de formulário interativo em duas colunas (controles à esquerda + copo ao vivo à direita).
 */
export const CustomDrinkBuilder: React.FC<CustomDrinkBuilderProps> = ({
  pumps,
  disabled,
  onSubmitCustom,
}) => {
  const [name, setName] = useState('Meu Drink de Verão');
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

  // Verificações instantâneas de limites volumétricos (mín. 10 ml, máx. 450 ml)
  const totalMl = volumes.amarelo + volumes.vermelho + volumes.verde + volumes.azul;
  const overLimit = totalMl > MAX_CUP_ML;
  const underLimit = totalMl < 10;

  /**
   * Estima em tempo real quantos segundos o drink levará para ficar pronto:
   * soma o tempo de bombeamento de cada ingrediente ativo (`ml / vazão`) + `1.2s` de pausa
   * de estabilização entre trocas de bombas.
   */
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

  /** Quantiza o valor em múltiplos de 5 ml e limita entre 0 e 350 ml por ingrediente. */
  const setPumpVolume = (pid: PumpId, nextVal: number) => {
    const clamped = Math.max(0, Math.min(350, Math.round(nextVal / 5) * 5));
    setVolumes((prev) => ({ ...prev, [pid]: clamped }));
  };

  /** Zera todos os sliders ("Esvaziar Copo") para começar uma receita do zero. */
  const resetAll = () => {
    setVolumes({ amarelo: 0, vermelho: 0, verde: 0, azul: 0 });
  };

  /** Valida restrições de segurança e envia o pedido customizado ao orquestrador principal. */
  const handlePrepare = (e: React.FormEvent) => {
    e.preventDefault();
    if (overLimit || underLimit || disabled) return;
    onSubmitCustom({
      name: name.trim() || 'Drink Personalizado',
      ...volumes,
    });
  };

  // Camadas líquidas passadas ao copo vetorial para feedback visual instantâneo a cada mexida no slider
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
      {/* Balcão de Ingredientes (Esquerda) */}
      <div className="linen-card lg:col-span-7 space-y-6 rounded-[30px] border border-[#ebd0b2] p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#eed7bc] pb-5">
          <div>
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-[#15803d]">
              <Citrus className="w-4 h-4" />
              Balcão Tropical Interativo
            </span>
            <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#2d1810] mt-1">
              Misture sua Receita na Medida
            </h2>
          </div>

          <button
            type="button"
            onClick={resetAll}
            className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-[#6e4631] bg-[#f8ebd9] hover:bg-[#f2dec3] border border-[#e5c7a3] transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Esvaziar Copo
          </button>
        </div>

        {/* Nome da Bebida + Combinações Sugeridas */}
        <div className="space-y-3">
          <label className="block text-xs font-bold uppercase tracking-wider text-[#7c533d]">
            Batize o seu drink
          </label>
          <input
            type="text"
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex: Brisa de Maracujá"
            className="w-full px-4 py-3 rounded-2xl bg-white border border-[#e5c7a3] text-[#2d1810] placeholder-[#b08c74] focus:outline-none focus:border-[#ea580c] text-sm font-medium shadow-2xs"
          />

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs font-medium text-[#7c533d] mr-1">Sugestões da casa:</span>
            {QUICK_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setName(preset.name);
                  setVolumes(preset.volumes);
                }}
                className="px-3 py-1.5 rounded-full text-xs font-semibold bg-[#fff6e9] hover:bg-[#ffead0] text-[#5e3925] border border-[#e7c9a6] transition-colors cursor-pointer"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Controles das 4 Frutas / Bombas */}
        <div className="space-y-4">
          {PUMP_ORDER.map((pid) => {
            const pump = pumpsById[pid];
            if (!pump) return null;
            const val = volumes[pid];
            // Bases diluidoras (`is_mixer`, ex: Água com Gás) permitem até 350ml; xaropes concentrados até 200ml
            const maxSlider = pump.is_mixer ? 350 : 200;

            return (
              <div
                key={pid}
                className="p-4 sm:p-5 rounded-2xl bg-[#fffdf9] border border-[#eed6ba] hover:border-[#dfba90] transition-colors shadow-2xs"
              >
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-3">
                    <span
                      className="w-4 h-4 rounded-full shadow-xs shrink-0 ring-4 ring-[#f9efe2]"
                      style={{ backgroundColor: pump.color_hex }}
                    />
                    <div>
                      <span className="font-display font-bold text-base text-[#2d1810] block">
                        {pump.ingredient}
                      </span>
                      <p className="text-xs text-[#7c533d]">{pump.description}</p>
                    </div>
                  </div>

                  <div className="text-right shrink-0 bg-[#fdf3e6] px-3 py-1 rounded-xl border border-[#edd4b6]">
                    <span className="font-display text-lg font-bold text-[#2d1810]">
                      {val}
                    </span>
                    <span className="text-xs font-medium text-[#7c533d] ml-1">ml</span>
                  </div>
                </div>

                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={() => setPumpVolume(pid, val - 25)}
                    className="p-2 rounded-xl bg-[#f7e9d6] hover:bg-[#efdac0] text-[#5c3724] border border-[#e6c8a4] cursor-pointer shrink-0"
                    title="Diminuir 25 ml"
                  >
                    <Minus className="w-3.5 h-3.5" />
                  </button>

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
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold bg-[#f7e9d6] hover:bg-[#efdac0] text-[#4a2b1b] border border-[#e6c8a4] cursor-pointer shrink-0"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    25ml
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Prévia do Copo Tropical (Direita) */}
      <div className="linen-card lg:col-span-5 rounded-[30px] border border-[#ebd0b2] p-6 sm:p-8 lg:sticky lg:top-24 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wider text-[#15803d] font-bold">
              Prévia no Copo
            </p>
            <h3 className="font-display text-2xl font-bold text-[#2d1810]">
              {name.trim() || 'Drink Personalizado'}
            </h3>
          </div>
          <div className="text-right">
            <span
              className={`font-display text-2xl font-bold ${
                overLimit ? 'text-rose-600' : 'text-[#ea580c]'
              }`}
            >
              {totalMl} ml
            </span>
            <p className="text-xs text-[#7c533d]">Limite {MAX_CUP_ML} ml</p>
          </div>
        </div>

        {/* Palco Ensolarado do Copo */}
        <div className="py-5 flex flex-col items-center justify-center rounded-3xl bg-gradient-to-b from-[#fff4e0] via-[#ffecd1] to-[#ffe2bd] border border-[#edd1b0]">
          <GlassArtwork layers={layers} maxCapacityMl={MAX_CUP_ML} size="lg" />
          <div className="mt-3 flex items-center gap-4 text-xs font-medium text-[#6e4631]">
            <span className="inline-flex items-center gap-1.5">
              <Droplets className="w-3.5 h-3.5 text-sky-600" />
              Copo em {Math.round((totalMl / MAX_CUP_ML) * 100)}%
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-600" />
              Pronto em ~{Math.ceil(estimatedSeconds)}s
            </span>
          </div>
        </div>

        {/* Barra de Proporção */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-medium text-[#6e4631]">
            <span>Equilíbrio de sabores</span>
            <span>{totalMl} / {MAX_CUP_ML} ml</span>
          </div>
          <div className="h-3 w-full rounded-full bg-[#f3e3ce] overflow-hidden flex p-0.5 gap-0.5">
            {PUMP_ORDER.map((pid) => {
              const ml = volumes[pid];
              if (ml <= 0 || totalMl <= 0) return null;
              const pct = (ml / Math.max(totalMl, MAX_CUP_ML)) * 100;
              return (
                <div
                  key={pid}
                  className="rounded-full"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: pumpsById[pid]?.color_hex ?? '#ea580c',
                  }}
                />
              );
            })}
          </div>

          {overLimit && (
            <div className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-xs text-rose-800 mt-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-600" />
              <span>
                O copo comporta até {MAX_CUP_ML} ml com segurança. Diminua um pouquinho algum ingrediente!
              </span>
            </div>
          )}

          {underLimit && (
            <p className="text-xs text-[#7c533d] pt-1">
              Escolha pelo menos 10 ml de bebida para preparar seu drink.
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={disabled || overLimit || underLimit}
          className="w-full py-4 px-5 rounded-2xl font-sans-ui font-bold text-sm text-white bg-gradient-to-r from-[#15803d] via-[#0d9488] to-[#0ea5e9] hover:brightness-105 shadow-lg shadow-emerald-700/20 flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed"
        >
          <Sparkles className="w-4 h-4" />
          <span>Servir Minha Receita ({totalMl} ml)</span>
        </button>
      </div>
    </form>
  );
};

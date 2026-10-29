import React from 'react';
import { Clock, Droplets, Play } from 'lucide-react';
import type { DrinkRecipe, PumpConfig, PumpId } from '../types/bartender';
import { GlassArtwork } from './GlassArtwork';

interface DrinkCardProps {
  drink: DrinkRecipe;
  pumpsById: Record<PumpId, PumpConfig>;
  disabled: boolean;
  onDispense: (drink: DrinkRecipe) => void;
}

export const DrinkCard: React.FC<DrinkCardProps> = ({
  drink,
  pumpsById,
  disabled,
  onDispense,
}) => {
  const layers = drink.steps.map((s) => ({
    color: pumpsById[s.pump]?.color_hex ?? drink.glass_color,
    ml: s.ml,
    label: pumpsById[s.pump]?.ingredient ?? s.pump,
  }));

  return (
    <article className="group relative flex flex-col rounded-2xl bg-[#11131d]/90 border border-white/10 hover:border-white/20 transition-all duration-300 overflow-hidden shadow-xl shadow-black/40 hover:-translate-y-1">
      {/* Faixa luminosa superior */}
      <div
        className="h-1 w-full opacity-80 group-hover:opacity-100 transition-opacity"
        style={{
          backgroundImage: `linear-gradient(90deg, ${drink.accent_from}, ${drink.accent_to})`,
        }}
      />

      {/* Área visual do copo */}
      <div className="relative pt-6 pb-3 px-6 flex items-center justify-center bg-gradient-to-b from-white/[0.03] to-transparent">
        <span className="absolute top-4 left-4 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide bg-white/[0.06] text-slate-200 border border-white/10">
          {drink.badge}
        </span>

        <div className="flex items-center gap-3 text-xs text-slate-400 absolute top-4 right-4">
          <span className="inline-flex items-center gap-1">
            <Droplets className="w-3.5 h-3.5 text-sky-400" />
            {drink.total_ml} ml
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            ~{Math.ceil(drink.estimated_seconds)}s
          </span>
        </div>

        <div className="mt-4 transform group-hover:scale-105 transition-transform duration-300">
          <GlassArtwork layers={layers} maxCapacityMl={400} size="md" />
        </div>
      </div>

      {/* Corpo textual */}
      <div className="flex-1 flex flex-col px-6 pb-6 pt-2">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {drink.subtitle}
        </p>
        <h3 className="font-display text-xl font-bold text-white mt-0.5">
          {drink.name}
        </h3>
        <p className="text-sm text-slate-300/85 leading-relaxed mt-2 mb-5">
          {drink.description}
        </p>

        {/* Barra de composição das bombas */}
        <div className="mt-auto space-y-2.5 mb-5">
          <div className="h-2 w-full rounded-full bg-white/[0.06] overflow-hidden flex">
            {drink.steps.map((step, i) => {
              const pct = drink.total_ml > 0 ? (step.ml / drink.total_ml) * 100 : 0;
              const hex = pumpsById[step.pump]?.color_hex ?? '#f59e0b';
              return (
                <div
                  key={`${step.pump}-${i}`}
                  style={{ width: `${pct}%`, backgroundColor: hex }}
                  title={`${pumpsById[step.pump]?.ingredient ?? step.pump}: ${step.ml} ml`}
                />
              );
            })}
          </div>

          <div className="flex flex-wrap gap-1.5">
            {drink.steps.map((step, i) => {
              const pump = pumpsById[step.pump];
              return (
                <span
                  key={`${step.pump}-${i}`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs bg-white/[0.04] border border-white/8 text-slate-300"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: pump?.color_hex ?? '#fff' }}
                  />
                  <span className="truncate max-w-[135px]">
                    {pump?.ingredient ?? step.pump}
                  </span>
                  <strong className="font-display text-white">{step.ml}ml</strong>
                </span>
              );
            })}
          </div>
        </div>

        {/* Botão de Preparo */}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDispense(drink)}
          className="w-full py-3 px-4 rounded-xl font-display font-semibold text-sm text-white flex items-center justify-center gap-2 shadow-lg transition-all cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed active:scale-[0.99]"
          style={{
            backgroundImage: `linear-gradient(90deg, ${drink.accent_from}, ${drink.accent_to})`,
          }}
        >
          <Play className="w-4 h-4 fill-current" />
          <span>Preparar Drink</span>
        </button>
      </div>
    </article>
  );
};


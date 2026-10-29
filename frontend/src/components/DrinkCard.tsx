import React from 'react';
import { Clock, Droplets, GlassWater } from 'lucide-react';
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
    <article className="linen-card group relative flex flex-col rounded-[28px] border border-[#ecd0b1] hover:border-[#dfa974] transition-all duration-300 overflow-hidden hover:-translate-y-1.5">
      {/* Nicho ensolarado em arco para o copo */}
      <div
        className="relative pt-6 pb-2 px-6 flex items-center justify-center overflow-hidden"
        style={{
          background: `radial-gradient(circle at 50% 75%, ${drink.accent_from}22 0%, #fff6e8 75%)`,
        }}
      >
        {/* Selo artesanal */}
        <span className="absolute top-4 left-4 px-3 py-1 rounded-full text-xs font-semibold bg-white/90 text-[#5c3724] border border-[#ebd0b3] shadow-xs">
          {drink.badge}
        </span>

        {/* Tempo e Volume */}
        <div className="flex items-center gap-2.5 text-xs font-medium text-[#754d38] absolute top-4 right-4 bg-white/80 px-2.5 py-1 rounded-full border border-[#ebd0b3]">
          <span className="inline-flex items-center gap-1">
            <Droplets className="w-3.5 h-3.5 text-sky-600" />
            {drink.total_ml} ml
          </span>
          <span className="text-[#d6b493]">•</span>
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-amber-600" />
            {Math.ceil(drink.estimated_seconds)}s
          </span>
        </div>

        <div className="mt-5 transform group-hover:scale-105 transition-transform duration-300">
          <GlassArtwork layers={layers} maxCapacityMl={400} size="md" />
        </div>
      </div>

      {/* Informações da Receita */}
      <div className="flex-1 flex flex-col px-6 pb-6 pt-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#b45309]">
          {drink.subtitle}
        </p>
        <h3 className="font-display text-2xl font-bold text-[#2d1810] mt-0.5">
          {drink.name}
        </h3>
        <p className="text-sm text-[#634130] leading-relaxed mt-2 mb-5">
          {drink.description}
        </p>

        {/* Ingredientes e Proporções */}
        <div className="mt-auto space-y-2.5 mb-5">
          <div className="h-2.5 w-full rounded-full bg-[#f3e3ce] overflow-hidden flex p-0.5 gap-0.5">
            {drink.steps.map((step, i) => {
              const pct = drink.total_ml > 0 ? (step.ml / drink.total_ml) * 100 : 0;
              const hex = pumpsById[step.pump]?.color_hex ?? '#f59e0b';
              return (
                <div
                  key={`${step.pump}-${i}`}
                  className="rounded-full"
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
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs bg-[#fdf5ea] border border-[#ecd3b5] text-[#593826]"
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: pump?.color_hex ?? '#f97316' }}
                  />
                  <span className="truncate max-w-[140px]">
                    {pump?.ingredient ?? step.pump}
                  </span>
                  <strong className="font-semibold text-[#2d1810]">{step.ml}ml</strong>
                </span>
              );
            })}
          </div>
        </div>

        {/* Botão Quente e Convidativo */}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDispense(drink)}
          className="w-full py-3.5 px-4 rounded-2xl font-sans-ui font-bold text-sm text-white flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed active:scale-[0.99]"
          style={{
            backgroundImage: `linear-gradient(95deg, ${drink.accent_from}, ${drink.accent_to})`,
          }}
        >
          <GlassWater className="w-4 h-4" />
          <span>Preparar Drink</span>
        </button>
      </div>
    </article>
  );
};

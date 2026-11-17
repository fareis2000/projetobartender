/**
 * @file src/components/DrinkCard.tsx
 * @description Card de vitrine gastronômica para venda rápida de receitas prontas em 1 toque via Pix.
 *
 * Papel na Conversão de Vendas & Transparência ao Consumidor:
 * - Comunica instantaneamente tudo o que o cliente precisa para decidir em menos de 5 segundos:
 *   ilustração das camadas reais no copo (`GlassArtwork`), selo `+18` automático se alcoólico,
 *   volume exato em `ml`, tempo estimado de serviço em segundos, barra proporcional de ingredientes
 *   e eventual desconto de combo (`-X% combo`).
 * - Prevenção automática de frustração/estorno: quando uma das garrafas da receita entra na reserva
 *   mínima de segurança, o card desabilita o botão de compra em tempo real e exibe `unavailable_reason`.
 */
import React from 'react';
import { AlertCircle, Clock, Droplets, QrCode, Wine } from 'lucide-react';
import type { DrinkRecipe, PumpId, PumpSlot } from '../types/bartender';
import { formatBrl } from '../utils/format';
import { GlassArtwork } from './GlassArtwork';

/**
 * Propriedades do card individual de receita (`DrinkCard`).
 */
interface DrinkCardProps {
  /** Receita enriquecida com disponibilidade, tempo de preparo e preço final em centavos. */
  drink: DrinkRecipe;
  /** Mapa indexado das 4 bombas da máquina para resolver nomes e cores das garrafas instaladas. */
  pumpsById: Record<PumpId, PumpSlot>;
  /** Bloqueia cliques duplicados enquanto uma cobrança Pix está sendo gerada no backend. */
  busyCreating: boolean;
  /** Callback acionado ao clicar em `"Pedir no Pix"`, iniciando o checkout imediato. */
  onOrderDrink: (drink: DrinkRecipe) => void;
}

/**
 * Componente de card de produto otimizado para toque mobile e escaneabilidade visual.
 */
export const DrinkCard: React.FC<DrinkCardProps> = ({
  drink,
  pumpsById,
  busyCreating,
  onOrderDrink,
}) => {
  // Converte as etapas da receita em camadas visuais para o copo SVG usando as cores reais das garrafas
  const layers = drink.steps.map((s) => ({
    color: pumpsById[s.pump]?.color_hex ?? drink.glass_color,
    ml: s.ml,
    label: pumpsById[s.pump]?.ingredient ?? s.pump,
  }));

  const canBuy = drink.available && !busyCreating;

  return (
    <article className="linen-card group relative flex flex-col rounded-[28px] border border-[#ecd0b1] hover:border-[#dfa974] transition-all duration-300 overflow-hidden hover:-translate-y-1">
      {/* Nicho ensolarado para o copo */}
      <div
        className="relative pt-6 pb-2 px-6 flex items-center justify-center overflow-hidden"
        style={{
          background: `radial-gradient(circle at 50% 75%, ${drink.accent_from}22 0%, #fff6e8 75%)`,
        }}
      >
        {/* Selo artesanal + Aviso +18 se alcoólico */}
        <div className="absolute top-4 left-4 flex items-center gap-1.5">
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-white/90 text-[#5c3724] border border-[#ebd0b3] shadow-xs">
            {drink.badge}
          </span>
          {drink.is_alcoholic && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-600 text-white shadow-xs">
              <Wine className="w-3 h-3" />
              +18
            </span>
          )}
        </div>

        {/* Tempo e Volume */}
        <div className="flex items-center gap-2 text-xs font-medium text-[#754d38] absolute top-4 right-4 bg-white/85 px-2.5 py-1 rounded-full border border-[#ebd0b3]">
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

        <div className="mt-6 transform group-hover:scale-105 transition-transform duration-300">
          <GlassArtwork layers={layers} maxCapacityMl={400} size="md" />
        </div>
      </div>

      {/* Informações da Receita + Preço */}
      <div className="flex-1 flex flex-col px-6 pb-6 pt-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[#b45309]">
              {drink.subtitle}
            </p>
            <h3 className="font-display text-2xl font-bold text-[#2d1810] mt-0.5">
              {drink.name}
            </h3>
          </div>
          <div className="text-right shrink-0">
            <span className="block font-display text-2xl font-extrabold text-[#15803d]">
              {formatBrl(drink.final_price_cents)}
            </span>
            {drink.pricing_mode === 'auto_ml' && drink.discount_pct > 0 && (
              <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                -{drink.discount_pct}% combo
              </span>
            )}
          </div>
        </div>

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
                  <span className="truncate max-w-[135px]">
                    {pump?.ingredient ?? step.pump}
                  </span>
                  <strong className="font-semibold text-[#2d1810]">{step.ml}ml</strong>
                </span>
              );
            })}
          </div>
        </div>

        {!drink.available && drink.unavailable_reason && (
          <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800">
            <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
            <span>{drink.unavailable_reason}</span>
          </div>
        )}

        {/* Botão Pedir com Pix */}
        <button
          type="button"
          disabled={!canBuy}
          onClick={() => onOrderDrink(drink)}
          className="w-full py-3.5 px-4 rounded-2xl font-sans-ui font-bold text-sm text-white flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed active:scale-[0.99]"
          style={{
            backgroundImage: drink.available
              ? `linear-gradient(95deg, ${drink.accent_from}, ${drink.accent_to})`
              : 'linear-gradient(95deg, #9ca3af, #6b7280)',
          }}
        >
          <QrCode className="w-4 h-4" />
          <span>
            {drink.available
              ? `Pedir no Pix · ${formatBrl(drink.final_price_cents)}`
              : 'Indisponível no Momento'}
          </span>
        </button>
      </div>
    </article>
  );
};

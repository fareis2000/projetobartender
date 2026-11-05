import React, { useMemo, useState } from 'react';
import { Edit3, Eye, EyeOff, Plus, Trash2, X } from 'lucide-react';
import { bartenderApi } from '../../api/client';
import type {
  DoseStep,
  DrinkPayload,
  DrinkPricingMode,
  DrinkRecipe,
  PumpId,
  PumpSlot,
} from '../../types/bartender';
import { formatBrl } from '../../utils/format';
import { GlassArtwork } from '../GlassArtwork';

interface DrinksCrudSectionProps {
  drinks: DrinkRecipe[];
  pumps: PumpSlot[];
  cupFeeCents: number;
  minOrderCents: number;
  onRefresh: () => Promise<void>;
}

const PUMP_OPTIONS: PumpId[] = ['amarelo', 'vermelho', 'verde', 'azul'];

export const DrinksCrudSection: React.FC<DrinksCrudSectionProps> = ({
  drinks,
  pumps,
  cupFeeCents,
  minOrderCents,
  onRefresh,
}) => {
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('Clássicos da Casa');
  const [badge, setBadge] = useState('Especial');
  const [accentFrom, setAccentFrom] = useState('#ea580c');
  const [accentTo, setAccentTo] = useState('#f97316');
  const [pricingMode, setPricingMode] = useState<DrinkPricingMode>('auto_ml');
  const [fixedPriceReais, setFixedPriceReais] = useState('16.90');
  const [discountPct, setDiscountPct] = useState(0);
  const [active, setActive] = useState(true);
  const [steps, setSteps] = useState<DoseStep[]>([
    { pump: 'vermelho', ml: 60, pause_ms: 1200 },
    { pump: 'azul', ml: 220, pause_ms: 0 },
  ]);

  const pumpsById = useMemo(() => {
    const m = {} as Record<PumpId, PumpSlot>;
    for (const p of pumps) m[p.pump_id] = p;
    return m;
  }, [pumps]);

  const livePreview = useMemo(() => {
    let rawLiquids = 0;
    let totalMl = 0;
    for (const s of steps) {
      totalMl += s.ml;
      const slot = pumpsById[s.pump];
      if (slot) {
        rawLiquids += Math.round((s.ml * slot.price_per_liter_cents) / 1000);
      }
    }
    const rawWithCup = rawLiquids + cupFeeCents;
    const fixedCents = Math.max(100, Math.round((parseFloat(fixedPriceReais.replace(',', '.')) || 0) * 100));
    const autoCents = Math.max(minOrderCents, Math.round(rawWithCup * (1 - discountPct / 100)));
    return {
      totalMl,
      rawWithCup,
      finalCents: pricingMode === 'fixed' ? fixedCents : autoCents,
      layers: steps.map((s) => ({
        color: pumpsById[s.pump]?.color_hex ?? accentFrom,
        ml: s.ml,
      })),
    };
  }, [steps, pumpsById, cupFeeCents, fixedPriceReais, pricingMode, minOrderCents, discountPct, accentFrom]);

  const openNew = () => {
    setEditingId(null);
    setName('');
    setSubtitle('Coquetel Exclusivo da Casa');
    setDescription('');
    setCategory('Clássicos da Casa');
    setBadge('Novidade');
    setAccentFrom('#ea580c');
    setAccentTo('#e11d48');
    setPricingMode('auto_ml');
    setFixedPriceReais('16.90');
    setDiscountPct(0);
    setActive(true);
    setSteps([
      { pump: 'amarelo', ml: 60, pause_ms: 1200 },
      { pump: 'azul', ml: 220, pause_ms: 0 },
    ]);
    setError(null);
    setFormOpen(true);
  };

  const openEdit = (d: DrinkRecipe) => {
    setEditingId(d.id);
    setName(d.name);
    setSubtitle(d.subtitle);
    setDescription(d.description);
    setCategory(d.category);
    setBadge(d.badge);
    setAccentFrom(d.accent_from);
    setAccentTo(d.accent_to);
    setPricingMode(d.pricing_mode);
    setFixedPriceReais((d.fixed_price_cents / 100).toFixed(2));
    setDiscountPct(d.discount_pct);
    setActive(d.active);
    setSteps(d.steps.map((s) => ({ ...s })));
    setError(null);
    setFormOpen(true);
  };

  const updateStep = (idx: number, patch: Partial<DoseStep>) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const addStep = () => {
    if (steps.length >= 6) return;
    setSteps((prev) => [...prev, { pump: 'azul', ml: 50, pause_ms: 0 }]);
  };

  const removeStep = (idx: number) => {
    if (steps.length <= 1) return;
    setSteps((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const fixedCents = Math.max(100, Math.round((parseFloat(fixedPriceReais.replace(',', '.')) || 0) * 100));
    const payload: DrinkPayload = {
      name: name.trim(),
      subtitle: subtitle.trim(),
      description: description.trim(),
      category: category.trim() || 'Cardápio',
      badge: badge.trim() || 'Especial',
      accent_from: accentFrom,
      accent_to: accentTo,
      glass_color: accentFrom,
      pricing_mode: pricingMode,
      fixed_price_cents: fixedCents,
      discount_pct: Number(discountPct),
      active,
      steps,
    };
    try {
      if (editingId) {
        await bartenderApi.updateDrink(editingId, payload);
      } else {
        await bartenderApi.createDrink(payload);
      }
      setFormOpen(false);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar drink.');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (d: DrinkRecipe) => {
    await bartenderApi.updateDrink(d.id, { active: !d.active });
    await onRefresh();
  };

  const handleDeleteDrink = async (d: DrinkRecipe) => {
    if (!window.confirm(`Excluir permanentemente o drink "${d.name}" do cardápio?`)) return;
    await bartenderApi.deleteDrink(d.id);
    await onRefresh();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="font-display text-2xl font-bold text-[#2d1810]">
            Cardápio de Drinks (CRUD Completo)
          </h3>
          <p className="text-xs sm:text-sm text-[#69432e]">
            Crie receitas autorais, pause bebidas em falta ou exclua qualquer drink do cardápio.
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="inline-flex items-center gap-2 px-5 py-3 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white text-sm font-bold shadow-md cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>Criar Novo Drink</span>
        </button>
      </div>

      {formOpen && (
        <form
          onSubmit={handleSubmit}
          className="linen-card rounded-3xl border-2 border-[#dfa974] p-6 space-y-5 shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-[#ecd3b5] pb-3">
            <h4 className="font-display text-xl font-bold text-[#2d1810]">
              {editingId ? 'Editar Receita de Drink' : 'Nova Receita de Drink'}
            </h4>
            <button
              type="button"
              onClick={() => setFormOpen(false)}
              className="p-1.5 rounded-xl bg-[#f5e5ce] text-[#5c3724] cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs font-bold text-rose-700">
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-8 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-[#69432e] mb-1">Nome do Drink *</label>
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Ex.: Gin Tropical Sunset"
                    className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-[#69432e] mb-1">Subtítulo</label>
                  <input
                    value={subtitle}
                    onChange={(e) => setSubtitle(e.target.value)}
                    placeholder="Ex.: Maracujá, Morango & Tônica"
                    className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-[#69432e] mb-1">Categoria</label>
                  <input
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    placeholder="Ex.: Autorais da Casa"
                    className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-1">
                    <label className="block text-xs font-bold text-[#69432e] mb-1">Selo</label>
                    <input
                      value={badge}
                      onChange={(e) => setBadge(e.target.value)}
                      className="w-full px-2.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-xs font-semibold"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-[#69432e] mb-1">Cor 1</label>
                    <input
                      type="color"
                      value={accentFrom}
                      onChange={(e) => setAccentFrom(e.target.value)}
                      className="w-full h-10 rounded-xl cursor-pointer"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-[#69432e] mb-1">Cor 2</label>
                    <input
                      type="color"
                      value={accentTo}
                      onChange={(e) => setAccentTo(e.target.value)}
                      className="w-full h-10 rounded-xl cursor-pointer"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#69432e] mb-1">Descrição no Cardápio</label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
                />
              </div>

              {/* Etapas das Bombas */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#2d1810]">
                    Etapas de Dosagem ({livePreview.totalMl} ml total)
                  </span>
                  <button
                    type="button"
                    onClick={addStep}
                    className="text-xs font-bold text-[#ea580c] hover:underline cursor-pointer"
                  >
                    + Adicionar Etapa
                  </button>
                </div>

                {steps.map((st, idx) => (
                  <div
                    key={idx}
                    className="grid grid-cols-12 gap-2 items-center bg-white p-2.5 rounded-xl border border-[#ebd0b2]"
                  >
                    <div className="col-span-6">
                      <select
                        value={st.pump}
                        onChange={(e) => updateStep(idx, { pump: e.target.value as PumpId })}
                        className="w-full px-2.5 py-1.5 rounded-lg border border-[#e5c7a3] text-xs font-bold text-[#2d1810]"
                      >
                        {PUMP_OPTIONS.map((pid) => (
                          <option key={pid} value={pid}>
                            {pumpsById[pid]?.label ?? pid} ({pumpsById[pid]?.ingredient ?? 'Sem garrafa'})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-3">
                      <input
                        type="number"
                        min={5}
                        max={400}
                        step={5}
                        value={st.ml}
                        onChange={(e) => updateStep(idx, { ml: Number(e.target.value) })}
                        className="w-full px-2.5 py-1.5 rounded-lg border border-[#e5c7a3] text-xs font-bold"
                        title="Volume em ml"
                      />
                    </div>
                    <div className="col-span-2">
                      <input
                        type="number"
                        min={0}
                        max={5000}
                        step={250}
                        value={st.pause_ms}
                        onChange={(e) => updateStep(idx, { pause_ms: Number(e.target.value) })}
                        className="w-full px-2 py-1.5 rounded-lg border border-[#e5c7a3] text-xs"
                        title="Pausa após etapa (ms)"
                      />
                    </div>
                    <div className="col-span-1 text-right">
                      <button
                        type="button"
                        disabled={steps.length <= 1}
                        onClick={() => removeStep(idx)}
                        className="text-rose-600 disabled:opacity-30 cursor-pointer"
                      >
                        <Trash2 className="w-4 h-4 inline" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Coluna Direita: Copo + Regra de Preço */}
            <div className="lg:col-span-4 rounded-2xl bg-[#fdf5ea] border border-[#ecd3b5] p-4 flex flex-col justify-between space-y-4">
              <div className="flex justify-center py-2">
                <GlassArtwork layers={livePreview.layers} size="sm" />
              </div>

              <div className="space-y-3">
                <label className="block text-xs font-bold text-[#2d1810]">Modo de Precificação</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setPricingMode('auto_ml')}
                    className={`py-2 px-2.5 rounded-xl text-xs font-bold border cursor-pointer ${
                      pricingMode === 'auto_ml'
                        ? 'bg-[#2d1810] text-white border-[#2d1810]'
                        : 'bg-white text-[#5c3724] border-[#e5c7a3]'
                    }`}
                  >
                    Automático (ml)
                  </button>
                  <button
                    type="button"
                    onClick={() => setPricingMode('fixed')}
                    className={`py-2 px-2.5 rounded-xl text-xs font-bold border cursor-pointer ${
                      pricingMode === 'fixed'
                        ? 'bg-[#2d1810] text-white border-[#2d1810]'
                        : 'bg-white text-[#5c3724] border-[#e5c7a3]'
                    }`}
                  >
                    Preço Fixo
                  </button>
                </div>

                {pricingMode === 'auto_ml' ? (
                  <div>
                    <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                      Desconto Combo da Casa (%)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={80}
                      value={discountPct}
                      onChange={(e) => setDiscountPct(Number(e.target.value))}
                      className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm font-bold"
                    />
                  </div>
                ) : (
                  <div>
                    <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                      Preço Fixo no Cardápio (R$)
                    </label>
                    <input
                      type="number"
                      step="0.50"
                      min="1.00"
                      value={fixedPriceReais}
                      onChange={(e) => setFixedPriceReais(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm font-bold"
                    />
                  </div>
                )}

                <div className="p-3 rounded-xl bg-white border border-[#ebd0b2] text-xs space-y-1">
                  <div className="flex justify-between">
                    <span>Soma avulsa dos ml:</span>
                    <span>{formatBrl(livePreview.rawWithCup)}</span>
                  </div>
                  <div className="flex justify-between font-bold text-sm text-[#15803d] pt-1 border-t border-[#f3e3ce]">
                    <span>Preço Final:</span>
                    <span>{formatBrl(livePreview.finalCents)}</span>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={saving}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white text-sm font-bold shadow-md cursor-pointer"
              >
                {saving ? 'Salvando...' : editingId ? 'Salvar Drink' : 'Adicionar ao Cardápio'}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Lista Real de Drinks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {drinks.map((d) => (
          <div
            key={d.id}
            className={`linen-card rounded-2xl border p-5 flex items-center justify-between gap-4 ${
              d.active ? 'border-[#ecd0b1]' : 'border-dashed border-gray-300 opacity-65'
            }`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-[#f6e6cf] text-[#5c3724]">
                  {d.category}
                </span>
                {!d.active && (
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
                    Oculto
                  </span>
                )}
              </div>
              <h4 className="font-display text-xl font-bold text-[#2d1810]">{d.name}</h4>
              <p className="text-xs text-[#7c533d]">
                {d.total_ml} ml · Custo Líquido: <strong>{formatBrl(d.estimated_cost_cents)}</strong> ·
                Lucro/copo:{' '}
                <strong className="text-emerald-700">{formatBrl(d.estimated_profit_cents)}</strong>
              </p>
              <div className="pt-1">
                <span className="font-display text-xl font-extrabold text-[#15803d]">
                  {formatBrl(d.final_price_cents)}
                </span>
                <span className="text-[11px] text-[#8a614a] ml-2">
                  ({d.pricing_mode === 'auto_ml' ? 'Automático por ml' : 'Preço Fixo'})
                </span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-end sm:items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => handleToggleActive(d)}
                title={d.active ? 'Pausar drink no cardápio' : 'Reativar drink'}
                className="p-2 rounded-xl bg-[#f6e6cf] hover:bg-[#ebd3b3] text-[#5c3724] cursor-pointer"
              >
                {d.active ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </button>
              <button
                type="button"
                onClick={() => openEdit(d)}
                className="p-2 rounded-xl bg-[#f6e6cf] hover:bg-[#ebd3b3] text-[#5c3724] cursor-pointer"
                title="Editar receita"
              >
                <Edit3 className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => handleDeleteDrink(d)}
                className="p-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 cursor-pointer"
                title="Excluir drink permanentemente"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

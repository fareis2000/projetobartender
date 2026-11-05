import React, { useState } from 'react';
import { Calculator, Edit3, Plus, Trash2, Wine, X } from 'lucide-react';
import { bartenderApi } from '../../api/client';
import type { Bottle, BottlePayload } from '../../types/bartender';
import { formatBrl, formatPerMl } from '../../utils/format';

interface BottlesCrudSectionProps {
  bottles: Bottle[];
  onRefresh: () => Promise<void>;
}

const PRESET_COLORS = [
  '#f59e0b',
  '#ef4444',
  '#10b981',
  '#0ea5e9',
  '#8b5cf6',
  '#ec4899',
  '#eab308',
  '#14b8a6',
];

export const BottlesCrudSection: React.FC<BottlesCrudSectionProps> = ({
  bottles,
  onRefresh,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [colorHex, setColorHex] = useState('#f97316');
  const [isAlcoholic, setIsAlcoholic] = useState(false);
  const [isMixer, setIsMixer] = useState(false);
  const [volumeMl, setVolumeMl] = useState(750);
  const [costReais, setCostReais] = useState('65.00');
  const [lossPct, setLossPct] = useState(3);
  // Preço em centavos por Litro (ex: 20000 = R$ 0,20/ml -> dose 50ml = R$ 10,00)
  const [pricePerLiterCents, setPricePerLiterCents] = useState(20000);

  const usableMl = Math.max(1, Math.round(volumeMl * (1 - lossPct / 100)));
  const costCents = Math.max(0, Math.round(( parseFloat(costReais.replace(',', '.')) || 0 ) * 100));
  const dose50Reais = ((50 * pricePerLiterCents) / 100_000).toFixed(2);
  const bottleTargetReais = ((usableMl * pricePerLiterCents) / 100_000).toFixed(2);
  const estProfitCents = Math.round((usableMl * pricePerLiterCents) / 1000) - costCents;

  const openNew = () => {
    setEditingId(null);
    setName('');
    setDescription('');
    setColorHex('#f59e0b');
    setIsAlcoholic(false);
    setIsMixer(false);
    setVolumeMl(750);
    setCostReais('50.00');
    setLossPct(3);
    setPricePerLiterCents(16000); // R$ 8,00 / 50ml
    setError(null);
    setFormOpen(true);
  };

  const openEdit = (b: Bottle) => {
    setEditingId(b.id);
    setName(b.name);
    setDescription(b.description);
    setColorHex(b.color_hex);
    setIsAlcoholic(b.is_alcoholic);
    setIsMixer(b.is_mixer);
    setVolumeMl(b.bottle_volume_ml);
    setCostReais((b.cost_cents / 100).toFixed(2));
    setLossPct(b.loss_pct);
    setPricePerLiterCents(b.price_per_liter_cents);
    setError(null);
    setFormOpen(true);
  };

  // Calculadora Sincronizada 1: Dono define quanto quer cobrar em 50 ml
  const handleDose50Change = (valStr: string) => {
    const val = parseFloat(valStr.replace(',', '.'));
    if (!Number.isNaN(val) && val > 0) {
      // dose 50ml em reais -> 1L (1000ml) = 20x
      setPricePerLiterCents(Math.max(100, Math.round(val * 20 * 100)));
    }
  };

  // Calculadora Sincronizada 2: Dono define quanto quer apurar na garrafa inteira
  const handleBottleRevenueChange = (valStr: string) => {
    const val = parseFloat(valStr.replace(',', '.'));
    if (!Number.isNaN(val) && val > 0 && usableMl > 0) {
      const centsTotal = val * 100;
      setPricePerLiterCents(Math.max(100, Math.round((centsTotal / usableMl) * 1000)));
    }
  };

  // Calculadora Sincronizada 3: Multiplicador de Markup rápido (2x, 3x, 4x)
  const applyMarkup = (mult: number) => {
    if (costCents <= 0 || usableMl <= 0) return;
    const targetCents = costCents * mult;
    setPricePerLiterCents(Math.max(100, Math.round((targetCents / usableMl) * 1000)));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const payload: BottlePayload = {
      name: name.trim(),
      description: description.trim(),
      color_hex: colorHex,
      is_alcoholic: isAlcoholic,
      is_mixer: isMixer,
      bottle_volume_ml: Number(volumeMl),
      cost_cents: costCents,
      loss_pct: Number(lossPct),
      price_per_liter_cents: Math.max(100, pricePerLiterCents),
    };
    try {
      if (editingId) {
        await bartenderApi.updateBottle(editingId, payload);
      } else {
        await bartenderApi.createBottle(payload);
      }
      setFormOpen(false);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar garrafa.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (b: Bottle) => {
    const warn =
      b.installed_in_pumps > 0
        ? `Atenção: "${b.name}" está instalada em ${b.installed_in_pumps} bomba(s) agora! Excluir irá desvincular essa bomba. Continuar?`
        : `Tem certeza que deseja excluir a garrafa "${b.name}" do estoque?`;
    if (!window.confirm(warn)) return;
    try {
      await bartenderApi.deleteBottle(b.id);
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Erro ao excluir garrafa.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="font-display text-2xl font-bold text-[#2d1810]">
            Estoque & Precificação de Garrafas (R$/ml)
          </h3>
          <p className="text-xs sm:text-sm text-[#69432e]">
            Cadastre suas garrafas pelo preço de custo ou valor da dose — o sistema calcula o preço
            por mililitro automaticamente.
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="inline-flex items-center gap-2 px-5 py-3 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white text-sm font-bold shadow-md cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>Nova Garrafa</span>
        </button>
      </div>

      {/* Formulário Modal / Card de Criação e Edição */}
      {formOpen && (
        <form
          onSubmit={handleSubmit}
          className="linen-card rounded-3xl border-2 border-[#dfa974] p-6 space-y-5 shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-[#ecd3b5] pb-3">
            <h4 className="font-display text-xl font-bold text-[#2d1810]">
              {editingId ? 'Editar Garrafa' : 'Cadastrar Nova Garrafa'}
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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Nome da Garrafa / Ingrediente *
              </label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex.: Gin Tanqueray 750ml"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810]"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Descrição Curta (visível para o cliente)
              </label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Ex.: Destilado botânico seco importado"
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#69432e] mb-1">
                Volume da Garrafa Fechada (ml) *
              </label>
              <input
                type="number"
                required
                min={100}
                max={20000}
                step={10}
                value={volumeMl}
                onChange={(e) => setVolumeMl(Number(e.target.value))}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-[#69432e] mb-1">
                  Custo Pago na Garrafa (R$)
                </label>
                <input
                  type="number"
                  min={0}
                  step="0.50"
                  value={costReais}
                  onChange={(e) => setCostReais(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810]"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-[#69432e] mb-1">
                  Perda Mangueira (%)
                </label>
                <input
                  type="number"
                  min={0}
                  max={30}
                  step={0.5}
                  value={lossPct}
                  onChange={(e) => setLossPct(Number(e.target.value))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-[#e5c7a3] text-sm font-semibold text-[#2d1810]"
                />
              </div>
            </div>
          </div>

          {/* Cor e Flags */}
          <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#69432e]">Cor no Copo:</span>
              <input
                type="color"
                value={colorHex}
                onChange={(e) => setColorHex(e.target.value)}
                className="w-9 h-9 rounded-lg cursor-pointer border border-[#e5c7a3]"
              />
              <div className="flex gap-1.5">
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setColorHex(c)}
                    className={`w-6 h-6 rounded-full cursor-pointer border-2 ${
                      colorHex.toLowerCase() === c ? 'border-[#2d1810] scale-110' : 'border-white'
                    }`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>

            <div className="flex items-center gap-5 text-xs font-bold text-[#2d1810]">
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isAlcoholic}
                  onChange={(e) => setIsAlcoholic(e.target.checked)}
                  className="w-4 h-4 accent-rose-600"
                />
                <span>Bebida Alcoólica (+18)</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isMixer}
                  onChange={(e) => setIsMixer(e.target.checked)}
                  className="w-4 h-4 accent-sky-600"
                />
                <span>Base / Mixer (Soda, Tônica, Suco)</span>
              </label>
            </div>
          </div>

          {/* Calculadora Inteligente de Preço de Venda */}
          <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-[#fff5e4] to-[#ffe8c8] border border-[#e5c299] space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wider text-[#b45309]">
                <Calculator className="w-4 h-4" />
                Calculadora de Preço de Venda (edite qualquer campo!)
              </span>
              {costCents > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-[#7c533d]">Markup rápido:</span>
                  {[2, 2.5, 3, 4].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => applyMarkup(m)}
                      className="px-2.5 py-1 rounded-lg bg-white hover:bg-[#2d1810] hover:text-white text-xs font-bold text-[#2d1810] border border-[#e0be96] transition-colors cursor-pointer"
                    >
                      {m}x Custo
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-white/90 p-3.5 rounded-xl border border-[#ebd0b2]">
                <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                  Preço de 1 Dose (50 ml) em R$
                </label>
                <input
                  type="number"
                  step="0.25"
                  min="0.10"
                  value={dose50Reais}
                  onChange={(e) => handleDose50Change(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[#e5c7a3] font-display text-lg font-extrabold text-[#15803d]"
                />
              </div>

              <div className="bg-white/90 p-3.5 rounded-xl border border-[#ebd0b2]">
                <label className="block text-[11px] font-bold text-[#7c533d] mb-1">
                  Faturamento da Garrafa ({usableMl} ml úteis)
                </label>
                <input
                  type="number"
                  step="1.00"
                  min="1.00"
                  value={bottleTargetReais}
                  onChange={(e) => handleBottleRevenueChange(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[#e5c7a3] font-display text-lg font-extrabold text-[#2d1810]"
                />
              </div>

              <div className="bg-emerald-50/90 p-3.5 rounded-xl border border-emerald-200 flex flex-col justify-center">
                <span className="text-[11px] font-bold text-emerald-800">
                  Valor Gravado por Mililitro:
                </span>
                <strong className="font-display text-2xl font-extrabold text-[#15803d]">
                  {formatPerMl(pricePerLiterCents)} / ml
                </strong>
                <span className="text-[11px] font-semibold text-emerald-900 mt-0.5">
                  Lucro estimado/garrafa:{' '}
                  <strong>{formatBrl(estProfitCents)}</strong>
                </span>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setFormOpen(false)}
              className="px-4 py-2.5 rounded-xl bg-[#f5e5ce] text-xs font-bold text-[#5c3724] cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white text-sm font-bold shadow-md cursor-pointer"
            >
              {saving ? 'Salvando...' : editingId ? 'Salvar Alterações' : 'Cadastrar Garrafa'}
            </button>
          </div>
        </form>
      )}

      {/* Lista de Garrafas Cadastradas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {bottles.map((b) => (
          <div
            key={b.id}
            className="linen-card rounded-2xl border border-[#ecd0b1] p-5 flex flex-col justify-between gap-4"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span
                    className="w-4 h-4 rounded-full shrink-0 shadow-xs"
                    style={{ backgroundColor: b.color_hex }}
                  />
                  <h4 className="font-bold text-base text-[#2d1810]">{b.name}</h4>
                </div>
                <div className="flex items-center gap-1">
                  {b.is_alcoholic && (
                    <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-600 text-white">
                      <Wine className="w-2.5 h-2.5" /> +18
                    </span>
                  )}
                  {b.installed_in_pumps > 0 && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      Em uso ({b.installed_in_pumps})
                    </span>
                  )}
                </div>
              </div>

              {b.description && (
                <p className="text-xs text-[#7c533d] mt-1">{b.description}</p>
              )}

              <div className="mt-4 p-3 rounded-xl bg-[#fdf5ea] border border-[#ecd3b5] grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-[#8a614a] block">Preço / ml</span>
                  <strong className="text-sm font-extrabold text-[#15803d]">
                    {formatPerMl(b.price_per_liter_cents)}
                  </strong>
                </div>
                <div>
                  <span className="text-[#8a614a] block">Dose 50 ml</span>
                  <strong className="text-sm font-bold text-[#2d1810]">
                    {formatBrl(b.dose_50ml_cents)}
                  </strong>
                </div>
                <div>
                  <span className="text-[#8a614a] block">Garrafa ({b.bottle_volume_ml}ml)</span>
                  <span className="font-semibold text-[#5c3724]">
                    Custo: {formatBrl(b.cost_cents)}
                  </span>
                </div>
                <div>
                  <span className="text-[#8a614a] block">Lucro / Garrafa</span>
                  <strong className="text-emerald-700">
                    {formatBrl(b.estimated_bottle_profit_cents)}
                  </strong>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#f0dcc2]">
              <button
                type="button"
                onClick={() => openEdit(b)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#f6e6cf] hover:bg-[#ebd3b3] text-xs font-bold text-[#5c3724] cursor-pointer"
              >
                <Edit3 className="w-3.5 h-3.5" />
                Editar
              </button>
              <button
                type="button"
                onClick={() => handleDelete(b)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-xs font-bold text-rose-700 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Excluir
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

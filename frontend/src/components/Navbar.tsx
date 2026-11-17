/**
 * @file src/components/Navbar.tsx
 * @description Barra superior fixa (sticky) da experiência Mobile-First de autoatendimento do consumidor.
 *
 * Papel na Conversão Mobile & Confiança do Usuário:
 * - Ancoragem imediata de contexto: exibe o nome oficial do Bar e um selo verde confirmando a qual
 *   máquina física (`machineName` / `machineSlug`) o smartphone está sincronizado via QR Code.
 * - Alternância sem fricção entre compra rápida em 1 toque (`Cardápio`) e experiência gamificada de
 *   alta margem (`Monte por ml`), respeitando a flag `allowCustomBuilder` configurada pelo dono do bar.
 * - Botão pulsante persistente de retomada (`Pedido #...`) caso o cliente minimize o modal de pagamento
 *   ou navegue pelo cardápio enquanto aguarda sua vez na fila.
 */
import React from 'react';
import { Citrus, Palmtree, QrCode, Receipt, Sparkles, Users } from 'lucide-react';
import type { Order } from '../types/bartender';
import { formatBrl } from '../utils/format';

/** Abas principais disponíveis na visão pública da máquina. */
export type ActiveTab = 'menu' | 'custom';

/**
 * Propriedades do componente `Navbar`.
 */
interface NavbarProps {
  /** Nome fantasia do estabelecimento exibido em destaque. */
  barName: string;
  /** Nome amigável da máquina conectada (ex.: `"Máquina #01 · Balcão"`). */
  machineName: string;
  /** Código slug da máquina lido no QR Code. */
  machineSlug: string;
  /** Controla se a aba `"Monte por ml"` deve ser exibida ao consumidor. */
  allowCustomBuilder: boolean;
  /** Aba atualmente selecionada pelo cliente. */
  activeTab: ActiveTab;
  /** Callback disparado ao alternar entre `"Cardápio"` e `"Monte por ml"`. */
  onChangeTab: (tab: ActiveTab) => void;
  /** Quantidade atual de pedidos pagos aguardando na fila da máquina. */
  queueLength: number;
  /** Pedido em andamento pertencente à sessão deste aparelho, se existir. */
  activeOrder: Order | null;
  /** Reabre o modal/bottom-sheet (`CustomerOrderSheet`) do pedido ativo ao tocar no indicador. */
  onOpenActiveOrder: () => void;
}

/**
 * Cabeçalho responsivo com backdrop-blur para a jornada de compra via celular.
 */
export const Navbar: React.FC<NavbarProps> = ({
  barName,
  machineName,
  machineSlug,
  allowCustomBuilder,
  activeTab,
  onChangeTab,
  queueLength,
  activeOrder,
  onOpenActiveOrder,
}) => {
  return (
    <header className="sticky top-0 z-40 border-b border-[#ead0b2]/80 bg-[#fffaf2]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center justify-between gap-3">
        {/* Identidade do Bar + Sincronização da Máquina */}
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#ff8a3d] via-[#f97316] to-[#e11d48] flex items-center justify-center shadow-md shadow-orange-500/25 text-white shrink-0">
            <Palmtree className="w-6 h-6" />
          </div>
          <div>
            <span className="font-display font-bold text-lg sm:text-xl text-[#2d1810] block leading-tight">
              {barName}
            </span>
            <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#11694b] bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full mt-0.5">
              <QrCode className="w-3 h-3" />
              <span>{machineName}</span>
              <span className="text-emerald-700/60">({machineSlug})</span>
            </span>
          </div>
        </div>

        {/* Abas Centrais */}
        {allowCustomBuilder && (
          <nav className="flex items-center p-1 rounded-2xl bg-[#f6e6cf]/80 border border-[#e7c9a5] order-3 sm:order-2 w-full sm:w-auto justify-center">
            <button
              type="button"
              onClick={() => onChangeTab('menu')}
              className={`flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-all cursor-pointer ${
                activeTab === 'menu'
                  ? 'bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white shadow-md shadow-orange-500/25'
                  : 'text-[#69432e] hover:text-[#2d1810] hover:bg-white/50'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Cardápio</span>
            </button>

            <button
              type="button"
              onClick={() => onChangeTab('custom')}
              className={`flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-all cursor-pointer ${
                activeTab === 'custom'
                  ? 'bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white shadow-md shadow-emerald-600/20'
                  : 'text-[#69432e] hover:text-[#2d1810] hover:bg-white/50'
              }`}
            >
              <Citrus className="w-4 h-4" />
              <span>Monte por ml</span>
            </button>
          </nav>
        )}

        {/* Indicador de Fila / Pedido Ativo */}
        <div className="flex items-center gap-2 order-2 sm:order-3">
          {queueLength > 0 && (
            <span className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200 text-xs font-semibold text-amber-800">
              <Users className="w-3.5 h-3.5" />
              Fila: {queueLength}
            </span>
          )}

          {activeOrder && (
            <button
              type="button"
              onClick={onOpenActiveOrder}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white text-xs font-bold shadow-md animate-pulse cursor-pointer"
            >
              <Receipt className="w-4 h-4" />
              <span>
                Pedido #{activeOrder.order_number} · {formatBrl(activeOrder.total_cents)}
              </span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

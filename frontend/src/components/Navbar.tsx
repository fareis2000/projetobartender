import React from 'react';
import { Citrus, GlassWater, Palmtree, Settings2, Sparkles, Usb, Wifi, WifiOff } from 'lucide-react';
import type { HardwareHealth } from '../types/bartender';

export type ActiveTab = 'menu' | 'custom';

interface NavbarProps {
  activeTab: ActiveTab;
  onChangeTab: (tab: ActiveTab) => void;
  hardware: HardwareHealth | null;
  onOpenSettings: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onChangeTab,
  hardware,
  onOpenSettings,
}) => {
  const renderConnectionBadge = () => {
    if (!hardware) {
      return (
        <span className="inline-flex items-center gap-2 text-xs font-medium text-[#7a543e]">
          <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
          Conectando...
        </span>
      );
    }

    if (hardware.active_transport === 'wifi') {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#11694b]">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <Wifi className="w-3.5 h-3.5" />
          ESP32 Wi-Fi
        </span>
      );
    }

    if (hardware.active_transport === 'serial') {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0e6490]">
          <span className="h-2 w-2 rounded-full bg-sky-500" />
          <Usb className="w-3.5 h-3.5" />
          USB ({hardware.serial_port})
        </span>
      );
    }

    if (hardware.active_transport === 'simulator') {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#b45309]">
          <span className="h-2 w-2 rounded-full bg-amber-500" />
          Modo Demonstração
        </span>
      );
    }

    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700">
        <span className="h-2 w-2 rounded-full bg-rose-500" />
        <WifiOff className="w-3.5 h-3.5" />
        ESP32 Offline
      </span>
    );
  };

  return (
    <header className="sticky top-0 z-40 border-b border-[#ead0b2]/80 bg-[#fffaf2]/85 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between gap-4">
        {/* Identidade Tropical */}
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#ff8a3d] via-[#f97316] to-[#e11d48] flex items-center justify-center shadow-md shadow-orange-500/25 text-white">
            <Palmtree className="w-6 h-6" />
          </div>
          <div>
            <span className="font-display font-bold text-xl sm:text-2xl text-[#2d1810] block leading-none">
              Bartender <span className="text-[#ea580c] italic">Tropical</span>
            </span>
            <span className="text-xs text-[#7c533d] hidden sm:block mt-0.5">
              Drinks frescos preparados na hora
            </span>
          </div>
        </div>

        {/* Abas Centrais */}
        <nav className="flex items-center p-1.5 rounded-2xl bg-[#f6e6cf]/80 border border-[#e7c9a5]">
          <button
            type="button"
            onClick={() => onChangeTab('menu')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all cursor-pointer ${
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
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all cursor-pointer ${
              activeTab === 'custom'
                ? 'bg-gradient-to-r from-[#15803d] to-[#0d9488] text-white shadow-md shadow-emerald-600/20'
                : 'text-[#69432e] hover:text-[#2d1810] hover:bg-white/50'
            }`}
          >
            <Citrus className="w-4 h-4" />
            <span>Monte seu Drink</span>
          </button>
        </nav>

        {/* Botão de Conexão / Calibração */}
        <button
          type="button"
          onClick={onOpenSettings}
          title="Configurar máquina ESP32 e calibrar bebidas"
          className="flex items-center gap-2.5 px-3.5 py-2 rounded-2xl bg-white/80 hover:bg-white border border-[#e6c8a5] shadow-sm transition-all cursor-pointer"
        >
          <div className="hidden md:block">{renderConnectionBadge()}</div>
          <GlassWater className="w-4 h-4 text-[#ea580c] md:hidden" />
          <Settings2 className="w-4 h-4 text-[#69432e]" />
        </button>
      </div>
    </header>
  );
};

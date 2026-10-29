import React from 'react';
import { Cpu, FlaskConical, Martini, Settings2, Sparkles, Usb, Wifi, WifiOff } from 'lucide-react';
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
        <span className="inline-flex items-center gap-2 text-xs text-slate-400">
          <span className="h-2 w-2 rounded-full bg-slate-500 animate-pulse" />
          Verificando ESP32...
        </span>
      );
    }

    if (hardware.active_transport === 'wifi') {
      return (
        <span className="inline-flex items-center gap-2 text-xs font-medium text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          <Wifi className="w-3.5 h-3.5" />
          ESP32 Wi-Fi · {hardware.wifi_ip ?? hardware.esp32_host}
        </span>
      );
    }

    if (hardware.active_transport === 'serial') {
      return (
        <span className="inline-flex items-center gap-2 text-xs font-medium text-sky-300">
          <span className="h-2 w-2 rounded-full bg-sky-400 shadow-[0_0_8px_#38bdf8]" />
          <Usb className="w-3.5 h-3.5" />
          ESP32 USB · {hardware.serial_port}
        </span>
      );
    }

    if (hardware.active_transport === 'simulator') {
      return (
        <span className="inline-flex items-center gap-2 text-xs font-medium text-amber-300">
          <span className="h-2 w-2 rounded-full bg-amber-400 shadow-[0_0_8px_#fbbf24]" />
          <Cpu className="w-3.5 h-3.5" />
          Simulador Ativo (Auto)
        </span>
      );
    }

    return (
      <span className="inline-flex items-center gap-2 text-xs font-medium text-rose-300">
        <span className="h-2 w-2 rounded-full bg-rose-500" />
        <WifiOff className="w-3.5 h-3.5" />
        ESP32 Desconectado
      </span>
    );
  };

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#08090e]/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between gap-4">
        {/* Marca */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 via-orange-500 to-rose-500 p-[1px] shadow-lg shadow-orange-500/20">
            <div className="w-full h-full rounded-[11px] bg-[#0e1018] flex items-center justify-center">
              <Martini className="w-5 h-5 text-amber-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display font-bold text-lg tracking-tight text-white">
                Bartender<span className="text-amber-400">.OS</span>
              </span>
              <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-white/5 text-slate-300 border border-white/10">
                ESP32 Edition
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              Coquetelaria Automatizada de Precisão
            </p>
          </div>
        </div>

        {/* Navegação Central */}
        <nav className="flex items-center p-1 rounded-xl bg-white/[0.04] border border-white/10">
          <button
            type="button"
            onClick={() => onChangeTab('menu')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              activeTab === 'menu'
                ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-slate-950 shadow-md shadow-amber-500/20 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Cardápio</span>
          </button>

          <button
            type="button"
            onClick={() => onChangeTab('custom')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              activeTab === 'custom'
                ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-slate-950 shadow-md shadow-amber-500/20 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            }`}
          >
            <FlaskConical className="w-4 h-4" />
            <span>Monte seu Drink</span>
          </button>
        </nav>

        {/* Status do Hardware + Botão de Configuração */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenSettings}
            title="Configurar conexão ESP32 e bombas"
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 transition-colors cursor-pointer"
          >
            <div className="hidden md:block">{renderConnectionBadge()}</div>
            <Settings2 className="w-4 h-4 text-slate-300" />
          </button>
        </div>
      </div>
    </header>
  );
};


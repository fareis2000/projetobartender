import React, { useEffect, useState } from 'react';
import { Check, RefreshCw, Save, Server, Sliders, X } from 'lucide-react';
import type {
  ConnectionConfigPayload,
  ConnectionMode,
  HardwareHealth,
  PumpConfig,
  PumpId,
} from '../types/bartender';

interface SettingsDrawerProps {
  open: boolean;
  hardware: HardwareHealth | null;
  pumps: PumpConfig[];
  onClose: () => void;
  onSaveConnection: (cfg: ConnectionConfigPayload) => Promise<void>;
  onSavePump: (
    pumpId: PumpId,
    data: { ingredient: string; flow_rate_ml_s: number },
  ) => Promise<void>;
  onProbe: () => Promise<void>;
}

export const SettingsDrawer: React.FC<SettingsDrawerProps> = ({
  open,
  hardware,
  pumps,
  onClose,
  onSaveConnection,
  onSavePump,
  onProbe,
}) => {
  const [mode, setMode] = useState<ConnectionMode>('auto');
  const [host, setHost] = useState('bartender.local');
  const [port, setPort] = useState(80);
  const [serialPort, setSerialPort] = useState('COM3');
  const [serialBaud, setSerialBaud] = useState(115200);
  const [savingConn, setSavingConn] = useState(false);
  const [probing, setProbing] = useState(false);

  const [pumpDrafts, setPumpDrafts] = useState<
    Record<string, { ingredient: string; flow_rate_ml_s: number }>
  >({});
  const [savedPumpId, setSavedPumpId] = useState<string | null>(null);

  useEffect(() => {
    if (hardware) {
      setMode(hardware.mode);
      setHost(hardware.esp32_host);
      setPort(hardware.esp32_port);
      setSerialPort(hardware.serial_port);
      setSerialBaud(hardware.serial_baud);
    }
  }, [hardware]);

  useEffect(() => {
    const next: Record<string, { ingredient: string; flow_rate_ml_s: number }> = {};
    for (const p of pumps) {
      next[p.id] = {
        ingredient: p.ingredient,
        flow_rate_ml_s: p.flow_rate_ml_s,
      };
    }
    setPumpDrafts(next);
  }, [pumps]);

  if (!open) return null;

  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConn(true);
    try {
      await onSaveConnection({
        mode,
        esp32_host: host.trim() || 'bartender.local',
        esp32_port: Number(port) || 80,
        serial_port: serialPort.trim() || 'COM3',
        serial_baud: Number(serialBaud) || 115200,
      });
    } finally {
      setSavingConn(false);
    }
  };

  const handleProbe = async () => {
    setProbing(true);
    try {
      await onProbe();
    } finally {
      setProbing(false);
    }
  };

  const handlePumpSave = async (pid: PumpId) => {
    const draft = pumpDrafts[pid];
    if (!draft) return;
    await onSavePump(pid, draft);
    setSavedPumpId(pid);
    setTimeout(() => setSavedPumpId(null), 1500);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/65 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-[#0d0f18] border-l border-white/10 h-full overflow-y-auto p-6 sm:p-7 space-y-8 shadow-2xl">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <div>
            <h2 className="font-display text-xl font-bold text-white">
              Hardware ESP32 & Calibração
            </h2>
            <p className="text-xs text-slate-400">
              Configure a comunicação Wi-Fi / USB Serial e as vazões das 4 bombas
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Diagnóstico Atual */}
        {hardware && (
          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/10 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Status Atual
              </span>
              <button
                type="button"
                onClick={handleProbe}
                disabled={probing}
                className="inline-flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${probing ? 'animate-spin' : ''}`} />
                Testar Agora
              </button>
            </div>
            <p className="text-sm text-slate-200">{hardware.detail}</p>
            {hardware.available_serial_ports.length > 0 && (
              <p className="text-xs text-slate-400">
                Portas COM detectadas: {hardware.available_serial_ports.join(', ')}
              </p>
            )}
          </div>
        )}

        {/* Formulário de Conexão ESP32 */}
        <form onSubmit={handleSaveConnection} className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Server className="w-4 h-4 text-amber-400" />
            <span>Modo de Comunicação</span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { id: 'auto', label: 'Auto (Wi-Fi → USB → Sim)' },
                { id: 'wifi', label: 'Apenas Wi-Fi (HTTP)' },
                { id: 'serial', label: 'Apenas USB Serial' },
                { id: 'simulator', label: 'Modo Simulador' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setMode(opt.id)}
                className={`p-2.5 rounded-xl text-xs font-medium border text-left transition-all cursor-pointer ${
                  mode === opt.id
                    ? 'bg-amber-500/15 border-amber-400 text-amber-200'
                    : 'bg-white/[0.03] border-white/10 text-slate-300 hover:bg-white/[0.06]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-slate-400 mb-1">
                Host / IP do ESP32 (Wi-Fi)
              </label>
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="bartender.local ou 192.168.1.50"
                className="w-full px-3 py-2 rounded-xl bg-[#08090e] border border-white/12 text-sm text-white"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Porta HTTP</label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-[#08090e] border border-white/12 text-sm text-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Porta USB Serial
              </label>
              <input
                type="text"
                value={serialPort}
                onChange={(e) => setSerialPort(e.target.value)}
                placeholder="COM3"
                className="w-full px-3 py-2 rounded-xl bg-[#08090e] border border-white/12 text-sm text-white"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Baudrate</label>
              <input
                type="number"
                value={serialBaud}
                onChange={(e) => setSerialBaud(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-[#08090e] border border-white/12 text-sm text-white"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={savingConn}
            className="w-full py-2.5 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-display font-bold text-xs flex items-center justify-center gap-2 cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{savingConn ? 'Salvando...' : 'Salvar Configuração de Conexão'}</span>
          </button>
        </form>

        {/* Calibração das 4 Bombas */}
        <div className="space-y-4 border-t border-white/10 pt-6">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Sliders className="w-4 h-4 text-amber-400" />
            <span>Ingredientes & Vazão das Bombas (ESP32-WROOM-32)</span>
          </div>

          <div className="space-y-3">
            {pumps.map((p) => {
              const draft = pumpDrafts[p.id] ?? {
                ingredient: p.ingredient,
                flow_rate_ml_s: p.flow_rate_ml_s,
              };

              return (
                <div
                  key={p.id}
                  className="p-3.5 rounded-2xl bg-white/[0.03] border border-white/10 space-y-2.5"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="inline-flex items-center gap-2 font-semibold text-white">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: p.color_hex }}
                      />
                      {p.label}
                    </span>
                    <span className="text-slate-400">GPIO {p.gpio}</span>
                  </div>

                  <div className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-7">
                      <label className="block text-[11px] text-slate-400 mb-1">
                        Bebida instalada
                      </label>
                      <input
                        type="text"
                        value={draft.ingredient}
                        onChange={(e) =>
                          setPumpDrafts((prev) => ({
                            ...prev,
                            [p.id]: { ...draft, ingredient: e.target.value },
                          }))
                        }
                        className="w-full px-2.5 py-1.5 rounded-lg bg-[#08090e] border border-white/12 text-xs text-white"
                      />
                    </div>
                    <div className="col-span-3">
                      <label className="block text-[11px] text-slate-400 mb-1">
                        Vazão (ml/s)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        min="1"
                        max="200"
                        value={draft.flow_rate_ml_s}
                        onChange={(e) =>
                          setPumpDrafts((prev) => ({
                            ...prev,
                            [p.id]: {
                              ...draft,
                              flow_rate_ml_s: Number(e.target.value),
                            },
                          }))
                        }
                        className="w-full px-2.5 py-1.5 rounded-lg bg-[#08090e] border border-white/12 text-xs text-white"
                      />
                    </div>
                    <div className="col-span-2">
                      <button
                        type="button"
                        onClick={() => handlePumpSave(p.id)}
                        className="w-full py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-white flex items-center justify-center cursor-pointer"
                        title="Salvar bomba"
                      >
                        {savedPumpId === p.id ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          'OK'
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};


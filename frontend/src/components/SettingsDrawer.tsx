/**
 * @file SettingsDrawer.tsx
 * @description Gaveta administrativa lateral para diagnóstico do ESP32, escolha de transporte e calibração de vazão.
 *
 * Papel na Arquitetura / Operação de Campo:
 * -----------------------------------------
 * Elimina a necessidade de editar código-fonte ou arquivos JSON manualmente durante a montagem
 * do bar em um evento:
 *   1. Diagnóstico sob demanda ("Testar Agora") exibindo IP resolvido, portas `COM` detectadas
 *      no Windows/Linux e status detalhado da comunicação.
 *   2. Seletor dos 4 modos de operação (`auto`, `wifi`, `serial`, `simulator`) + campos de
 *      `Host / IP`, `Porta HTTP`, `Porta USB Serial` e `Baud Rate` salvos em `connection.json`.
 *   3. Editor individual para cada uma das 4 bombas (com indicação do pino `GPIO` físico),
 *      permitindo trocar o nome da bebida na garrafa e calibrar a vazão em `ml/s` — gravando
 *      tanto em `pumps.json` no servidor quanto na Flash NVS do próprio ESP32 via Wi-Fi!
 */
import React, { useEffect, useState } from 'react';
import { Check, Radar, RefreshCw, Save, Server, Sliders, Wifi, X } from 'lucide-react';
import { bartenderApi } from '../api/client';
import type {
  ConnectionConfigPayload,
  ConnectionMode,
  HardwareHealth,
  PumpConfig,
  PumpId,
} from '../types/bartender';

/** Propriedades do painel lateral `SettingsDrawer`. */
interface SettingsDrawerProps {
  /** Indica se a gaveta lateral está aberta. */
  open: boolean;
  /** Estado atual de saúde e configuração de conectividade do ESP32. */
  hardware: HardwareHealth | null;
  /** Lista atual das 4 bombas físicas. */
  pumps: PumpConfig[];
  /** Fecha a gaveta lateral. */
  onClose: () => void;
  /** Persiste e retesta a configuração de conexão (`PUT /api/connection`). */
  onSaveConnection: (cfg: ConnectionConfigPayload) => Promise<void>;
  /** Salva nome da bebida e vazão calibrada (`ml/s`) de uma bomba (`PUT /api/pumps/{id}`). */
  onSavePump: (
    pumpId: PumpId,
    data: { ingredient: string; flow_rate_ml_s: number },
  ) => Promise<void>;
  /** Executa sondagem imediata do hardware (`GET /api/connection`). */
  onProbe: () => Promise<void>;
}

/**
 * Gaveta lateral de configuração técnica e calibração hidráulica.
 */
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
  const [syncingNet, setSyncingNet] = useState(false);
  const [syncBanner, setSyncBanner] = useState<string | null>(null);

  // Rascunhos locais das 4 bombas para edição controlada antes de clicar em "OK"
  const [pumpDrafts, setPumpDrafts] = useState<
    Record<string, { ingredient: string; flow_rate_ml_s: number }>
  >({});
  const [savedPumpId, setSavedPumpId] = useState<string | null>(null);

  // Sincroniza os campos do formulário sempre que um novo diagnóstico `hardware` chega do servidor
  useEffect(() => {
    if (hardware) {
      setMode(hardware.mode);
      setHost(hardware.esp32_host);
      setPort(hardware.esp32_port);
      setSerialPort(hardware.serial_port);
      setSerialBaud(hardware.serial_baud);
    }
  }, [hardware]);

  // Inicializa os rascunhos de edição com os valores atuais das bombas
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

  /** Envia os novos parâmetros de transporte aplicando fallbacks seguros caso campos fiquem vazios. */
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

  /** Aciona sondagem manual com spinner visual no botão "Testar Agora". */
  const handleProbe = async () => {
    setProbing(true);
    try {
      await onProbe();
    } finally {
      setProbing(false);
    }
  };

  /** Puxa a rede Wi-Fi atual do servidor, atualiza secrets.h, provisiona o ESP e varre a LAN. */
  const handleSyncNetwork = async () => {
    setSyncingNet(true);
    setSyncBanner(null);
    try {
      const res = await bartenderApi.syncNetwork();
      setSyncBanner(res.message);
      await onProbe();
    } catch (e: unknown) {
      setSyncBanner(e instanceof Error ? e.message : 'Erro ao sincronizar rede');
    } finally {
      setSyncingNet(false);
    }
  };

  /** Salva os ajustes de uma bomba individual e exibe ícone de confirmação (`Check`) por 1,5s. */
  const handlePumpSave = async (pid: PumpId) => {
    const draft = pumpDrafts[pid];
    if (!draft) return;
    await onSavePump(pid, draft);
    setSavedPumpId(pid);
    setTimeout(() => setSavedPumpId(null), 1500);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#2d1810]/40 backdrop-blur-xs">
      <div className="w-full max-w-lg bg-[#fffaf3] border-l border-[#ead0b2] h-full overflow-y-auto p-6 sm:p-7 space-y-8 shadow-2xl text-[#2d1810]">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between border-b border-[#eed6ba] pb-4">
          <div>
            <h2 className="font-display text-2xl font-bold text-[#2d1810]">
              Conexão ESP32 & Bebidas
            </h2>
            <p className="text-xs text-[#7c533d]">
              Ajuste o endereço Wi-Fi/USB do ESP32 e calibre as 4 bombas
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl bg-[#f7e9d6] hover:bg-[#efdac0] text-[#5c3724] cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Diagnóstico Atual */}
        {hardware && (
          <div className="p-4 rounded-2xl bg-[#fff3e2] border border-[#ebd0b0] space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-[#8a583c]">
                Diagnóstico da Máquina & Rede Atual
              </span>
              <button
                type="button"
                onClick={handleProbe}
                disabled={probing}
                className="inline-flex items-center gap-1.5 text-xs font-bold text-[#ea580c] hover:text-[#c2410c] cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${probing ? 'animate-spin' : ''}`} />
                Testar Agora
              </button>
            </div>
            <p className="text-sm font-medium text-[#3b2116]">{hardware.detail}</p>
            <div className="flex flex-wrap gap-2 text-[11px] text-[#69432e]">
              {hardware.connected_ssid && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#ffedd5] border border-[#fed7aa] font-semibold">
                  <Wifi className="w-3 h-3 text-[#ea580c]" />
                  Wi-Fi PC: {hardware.connected_ssid}
                  {hardware.esp_target_ssid && hardware.esp_target_ssid !== hardware.connected_ssid
                    ? ` (2.4G: ${hardware.esp_target_ssid})`
                    : ''}
                </span>
              )}
              {hardware.server_lan_ip && (
                <span className="px-2 py-0.5 rounded-md bg-white border border-[#e6c8a5] font-mono">
                  IP Servidor: {hardware.server_lan_ip}:8000
                </span>
              )}
              {hardware.wifi_ip && (
                <span className="px-2 py-0.5 rounded-md bg-[#dcfce7] border border-[#86efac] text-[#166534] font-mono font-semibold">
                  IP ESP: {hardware.wifi_ip}
                </span>
              )}
            </div>
            {hardware.available_serial_ports.length > 0 && (
              <p className="text-xs text-[#7c533d]">
                Portas COM detectadas: {hardware.available_serial_ports.join(', ')}
              </p>
            )}
            <button
              type="button"
              onClick={handleSyncNetwork}
              disabled={syncingNet}
              className="w-full mt-1 py-2 px-3 rounded-xl bg-[#2d1810] hover:bg-[#432519] text-[#fffaf3] text-xs font-bold flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <Radar className={`w-3.5 h-3.5 text-[#fb923c] ${syncingNet ? 'animate-spin' : ''}`} />
              <span>
                {syncingNet
                  ? 'Localizando ESP na Rede Atual...'
                  : 'Localizar ESP & Puxar Rede Atual Automaticamente'}
              </span>
            </button>
            {syncBanner && (
              <p className="text-[11px] font-medium text-[#15803d] bg-[#dcfce7]/70 px-2.5 py-1.5 rounded-lg border border-[#86efac]">
                {syncBanner}
              </p>
            )}
          </div>
        )}

        {/* Formulário de Conexão ESP32 */}
        <form onSubmit={handleSaveConnection} className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-[#2d1810]">
            <Server className="w-4 h-4 text-[#ea580c]" />
            <span>Modo de Comunicação</span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { id: 'auto', label: 'Automático (Recomendado)' },
                { id: 'wifi', label: 'Apenas Wi-Fi (HTTP)' },
                { id: 'serial', label: 'Apenas Cabo USB' },
                { id: 'simulator', label: 'Modo Demonstração' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setMode(opt.id)}
                className={`p-2.5 rounded-xl text-xs font-semibold border text-left transition-all cursor-pointer ${
                  mode === opt.id
                    ? 'bg-[#ffedd5] border-[#ea580c] text-[#9a3412]'
                    : 'bg-white border-[#e6c8a5] text-[#69432e] hover:bg-[#fff6ea]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-semibold text-[#7c533d] mb-1">
                Host / IP do ESP32 (Wi-Fi)
              </label>
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="bartender.local ou 192.168.1.50"
                className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#7c533d] mb-1">
                Porta HTTP
              </label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-[#7c533d] mb-1">
                Porta USB Serial
              </label>
              <input
                type="text"
                value={serialPort}
                onChange={(e) => setSerialPort(e.target.value)}
                placeholder="COM3"
                className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#7c533d] mb-1">
                Velocidade (Baud)
              </label>
              <input
                type="number"
                value={serialBaud}
                onChange={(e) => setSerialBaud(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-white border border-[#e5c7a3] text-sm text-[#2d1810]"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={savingConn}
            className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:brightness-105 text-white font-sans-ui font-bold text-xs flex items-center justify-center gap-2 shadow-sm cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{savingConn ? 'Salvando...' : 'Salvar Configuração de Conexão'}</span>
          </button>
        </form>

        {/* Calibração das 4 Bombas */}
        <div className="space-y-4 border-t border-[#eed6ba] pt-6">
          <div className="flex items-center gap-2 text-sm font-bold text-[#2d1810]">
            <Sliders className="w-4 h-4 text-[#15803d]" />
            <span>Garrafas & Calibração de Vazão</span>
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
                  className="p-3.5 rounded-2xl bg-white border border-[#ecd2b4] space-y-2.5"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="inline-flex items-center gap-2 font-bold text-[#2d1810]">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: p.color_hex }}
                      />
                      {p.label}
                    </span>
                    <span className="text-[#8a5d42] font-medium">Pino GPIO {p.gpio}</span>
                  </div>

                  <div className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-7">
                      <label className="block text-[11px] font-medium text-[#7c533d] mb-1">
                        Bebida na garrafa
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
                        className="w-full px-2.5 py-1.5 rounded-lg bg-[#fffaf3] border border-[#e5c7a3] text-xs text-[#2d1810]"
                      />
                    </div>
                    <div className="col-span-3">
                      <label className="block text-[11px] font-medium text-[#7c533d] mb-1">
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
                        className="w-full px-2.5 py-1.5 rounded-lg bg-[#fffaf3] border border-[#e5c7a3] text-xs text-[#2d1810]"
                      />
                    </div>
                    <div className="col-span-2">
                      <button
                        type="button"
                        onClick={() => handlePumpSave(p.id)}
                        className="w-full py-1.5 rounded-lg bg-[#15803d] hover:bg-[#166534] text-xs font-bold text-white flex items-center justify-center cursor-pointer"
                        title="Salvar bomba"
                      >
                        {savedPumpId === p.id ? (
                          <Check className="w-4 h-4 text-white" />
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

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, FlaskConical, Gauge, Sparkles, Zap } from 'lucide-react';
import { bartenderApi } from './api/client';
import { CustomDrinkBuilder } from './components/CustomDrinkBuilder';
import { DrinkCard } from './components/DrinkCard';
import { type ActiveTab, Navbar } from './components/Navbar';
import { PreparationModal } from './components/PreparationModal';
import { SettingsDrawer } from './components/SettingsDrawer';
import type {
  ConnectionConfigPayload,
  CustomDrinkPayload,
  DrinkRecipe,
  HardwareHealth,
  PreparationStatus,
  PumpConfig,
  PumpId,
  SystemSnapshot,
} from './types/bartender';

const INITIAL_STATUS: PreparationStatus = {
  state: 'idle',
  drink_id: null,
  drink_name: null,
  progress: 0,
  current_pump: null,
  current_step_index: 0,
  total_steps: 0,
  message: 'Pronto para preparar seu próximo drink',
  transport: null,
  elapsed_seconds: 0,
  total_seconds: 0,
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('menu');
  const [selectedCategory, setSelectedCategory] = useState<string>('Todos');
  const [drinks, setDrinks] = useState<DrinkRecipe[]>([]);
  const [pumps, setPumps] = useState<PumpConfig[]>([]);
  const [status, setStatus] = useState<PreparationStatus>(INITIAL_STATUS);
  const [hardware, setHardware] = useState<HardwareHealth | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadCatalogAndPumps = useCallback(async () => {
    try {
      const [drinksData, pumpsData, snap] = await Promise.all([
        bartenderApi.getDrinks(),
        bartenderApi.getPumps(),
        bartenderApi.getStatus(true),
      ]);
      setDrinks(drinksData);
      setPumps(pumpsData);
      setStatus(snap.status);
      setHardware(snap.hardware);
      if (snap.status.state === 'dispensing') {
        setModalOpen(true);
      }
      setErrorBanner(null);
    } catch (err) {
      setErrorBanner(
        err instanceof Error
          ? err.message
          : 'Não foi possível conectar à API FastAPI.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalogAndPumps();
  }, [loadCatalogAndPumps]);

  // WebSocket em tempo real com reconexão automática
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let unmounted = false;

    const connectWs = () => {
      if (unmounted) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`);

      ws.onmessage = (event) => {
        try {
          const snap = JSON.parse(event.data) as SystemSnapshot;
          setStatus(snap.status);
          setHardware(snap.hardware);
          if (snap.status.state === 'dispensing') {
            setModalOpen(true);
          }
        } catch {
          // ignora pacote malformado
        }
      };

      ws.onclose = () => {
        if (!unmounted) {
          reconnectTimer = window.setTimeout(connectWs, 2500);
        }
      };
    };

    connectWs();

    return () => {
      unmounted = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  const pumpsById = useMemo(() => {
    const map = {} as Record<PumpId, PumpConfig>;
    for (const p of pumps) map[p.id] = p;
    return map;
  }, [pumps]);

  const categories = useMemo(() => {
    const unique = Array.from(new Set(drinks.map((d) => d.category)));
    return ['Todos', ...unique];
  }, [drinks]);

  const filteredDrinks = useMemo(() => {
    if (selectedCategory === 'Todos') return drinks;
    return drinks.filter((d) => d.category === selectedCategory);
  }, [drinks, selectedCategory]);

  const handleDispensePreset = async (drink: DrinkRecipe) => {
    setErrorBanner(null);
    try {
      const st = await bartenderApi.dispensePreset(drink.id);
      setStatus(st);
      setModalOpen(true);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : 'Erro ao iniciar preparo.',
      );
    }
  };

  const handleDispenseCustom = async (payload: CustomDrinkPayload) => {
    setErrorBanner(null);
    try {
      const st = await bartenderApi.dispenseCustom(payload);
      setStatus(st);
      setModalOpen(true);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : 'Erro ao iniciar drink customizado.',
      );
    }
  };

  const handleEmergencyStop = async () => {
    try {
      const st = await bartenderApi.emergencyStop();
      setStatus(st);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : 'Falha ao enviar parada.',
      );
    }
  };

  const handleSaveConnection = async (cfg: ConnectionConfigPayload) => {
    const updated = await bartenderApi.updateConnection(cfg);
    setHardware(updated);
  };

  const handleSavePump = async (
    pumpId: PumpId,
    data: { ingredient: string; flow_rate_ml_s: number },
  ) => {
    await bartenderApi.updatePump(pumpId, data);
    const [drinksData, pumpsData] = await Promise.all([
      bartenderApi.getDrinks(),
      bartenderApi.getPumps(),
    ]);
    setDrinks(drinksData);
    setPumps(pumpsData);
  };

  const handleProbe = async () => {
    const updated = await bartenderApi.getConnection();
    setHardware(updated);
  };

  const isBusy = status.state === 'dispensing';

  return (
    <div className="min-h-screen flex flex-col relative">
      {/* Iluminação ambiente de fundo */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden -z-10">
        <div className="absolute -top-40 left-1/4 w-[520px] h-[520px] rounded-full bg-amber-500/10 blur-[130px]" />
        <div className="absolute top-1/3 -right-32 w-[460px] h-[460px] rounded-full bg-rose-500/10 blur-[130px]" />
        <div className="absolute -bottom-32 left-10 w-[420px] h-[420px] rounded-full bg-sky-500/8 blur-[130px]" />
      </div>

      <Navbar
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        hardware={hardware}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 space-y-8">
        {/* Alerta de erro se houver */}
        {errorBanner && (
          <div className="flex items-center justify-between gap-4 p-4 rounded-2xl bg-rose-500/12 border border-rose-500/30 text-sm text-rose-200">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
              <span>{errorBanner}</span>
            </div>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-xs font-semibold text-white shrink-0 cursor-pointer"
            >
              Configurar ESP32
            </button>
          </div>
        )}

        {activeTab === 'menu' ? (
          <>
            {/* Hero / Banner Principal */}
            <section className="relative rounded-3xl bg-gradient-to-br from-[#131624] via-[#10121c] to-[#17121c] border border-white/10 p-6 sm:p-10 overflow-hidden shadow-2xl">
              <div className="max-w-2xl space-y-4">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs font-semibold">
                  <Zap className="w-3.5 h-3.5" />
                  <span>Dosagem Volumétrica Controlada por ESP32</span>
                </div>

                <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-white tracking-tight leading-tight">
                  Seu drink favorito, dosado com{' '}
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-orange-400 to-rose-400">
                    precisão robótica.
                  </span>
                </h1>

                <p className="text-sm sm:text-base text-slate-300/90 leading-relaxed">
                  Escolha uma receita assinada no cardápio ou abra o estúdio{' '}
                  <strong className="text-white">Monte seu Drink</strong> para combinar
                  os mililitros exatos de cada uma das 4 bombas peristálticas.
                </p>

                <div className="pt-2 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setActiveTab('custom')}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-400 to-orange-500 hover:from-amber-300 hover:to-orange-400 text-slate-950 font-display font-bold text-sm shadow-lg shadow-amber-500/20 transition-all cursor-pointer"
                  >
                    <FlaskConical className="w-4 h-4" />
                    <span>Criar Drink Personalizado</span>
                  </button>

                  <div className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-xs text-slate-300">
                    <Gauge className="w-4 h-4 text-sky-400" />
                    <span>4 Bombas Ativas · GPIOs 16, 17, 18, 19</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Barra de Categorias */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-amber-400" />
                <h2 className="font-display text-xl font-bold text-white">
                  Cardápio de Drinks
                </h2>
              </div>

              <div className="flex flex-wrap gap-2">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                      selectedCategory === cat
                        ? 'bg-white text-slate-950 shadow'
                        : 'bg-white/[0.05] text-slate-300 hover:bg-white/[0.1] border border-white/10'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Grid de Cards */}
            {loading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-96 rounded-2xl bg-white/[0.03] border border-white/8 animate-pulse"
                  />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredDrinks.map((drink) => (
                  <DrinkCard
                    key={drink.id}
                    drink={drink}
                    pumpsById={pumpsById}
                    disabled={isBusy}
                    onDispense={handleDispensePreset}
                  />
                ))}
              </div>
            )}
          </>
        ) : (
          <CustomDrinkBuilder
            pumps={pumps}
            disabled={isBusy}
            onSubmitCustom={handleDispenseCustom}
          />
        )}
      </main>

      <footer className="border-t border-white/8 py-6 mt-12 text-center text-xs text-slate-500">
        Bartender Automático v2.0 · React + TypeScript + Tailwind CSS · FastAPI · ESP32-WROOM-32
      </footer>

      <PreparationModal
        visible={modalOpen}
        status={status}
        pumpsById={pumpsById}
        onEmergencyStop={handleEmergencyStop}
        onClose={() => setModalOpen(false)}
      />

      <SettingsDrawer
        open={settingsOpen}
        hardware={hardware}
        pumps={pumps}
        onClose={() => setSettingsOpen(false)}
        onSaveConnection={handleSaveConnection}
        onSavePump={handleSavePump}
        onProbe={handleProbe}
      />
    </div>
  );
};
export default App;


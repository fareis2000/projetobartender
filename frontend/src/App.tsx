import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Citrus, Sparkles, Sun } from 'lucide-react';
import { bartenderApi } from './api/client';
import { CustomDrinkBuilder } from './components/CustomDrinkBuilder';
import { DrinkCard } from './components/DrinkCard';
import { type ActiveTab, Navbar } from './components/Navbar';
import { PreparationModal } from './components/PreparationModal';
import { SettingsDrawer } from './components/SettingsDrawer';
import { TropicalBackdropLeaves, TropicalHeroArt } from './components/TropicalDecor';
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
          : 'Não foi possível conectar ao servidor do bar.',
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
        err instanceof Error ? err.message : 'Erro ao iniciar drink personalizado.',
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
      {/* Folhagens de palmeira, costela-de-adão e luz de pôr do sol */}
      <TropicalBackdropLeaves />

      <Navbar
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        hardware={hardware}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 space-y-10">
        {/* Aviso caso haja erro de comunicação */}
        {errorBanner && (
          <div className="flex items-center justify-between gap-4 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-sm text-rose-800 shadow-xs">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
              <span>{errorBanner}</span>
            </div>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white shrink-0 cursor-pointer"
            >
              Ajustar Conexão
            </button>
          </div>
        )}

        {activeTab === 'menu' ? (
          <>
            {/* Banner Tropical de Verão */}
            <section className="relative rounded-[34px] bg-gradient-to-br from-[#fff5e4] via-[#ffe6c4] to-[#ffd2a6] border border-[#ebcaa3] p-7 sm:p-10 lg:px-12 overflow-hidden shadow-[0_24px_50px_-20px_rgba(165,82,25,0.2)]">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                <div className="lg:col-span-7 space-y-4">
                  <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/80 border border-[#e7c59d] text-[#b45309] text-xs font-bold shadow-2xs">
                    <Sun className="w-4 h-4 text-[#f59e0b]" />
                    <span>Bar Tropical Automatizado</span>
                  </div>

                  <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#2d1810] leading-[1.12]">
                    Refrescância de verão,{' '}
                    <span className="text-[#ea580c] italic">
                      servida na medida perfeita.
                    </span>
                  </h1>

                  <p className="text-sm sm:text-base text-[#5e3b29] leading-relaxed max-w-xl">
                    Escolha um dos nossos coquetéis tropicais abaixo ou misture frutas
                    cítricas, morango, maçã verde e água gaseificada bem gelada no nosso
                    balcão interativo.
                  </p>

                  <div className="pt-2 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setActiveTab('custom')}
                      className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] hover:brightness-105 text-white font-sans-ui font-bold text-sm shadow-lg shadow-emerald-700/20 transition-all cursor-pointer"
                    >
                      <Citrus className="w-4 h-4" />
                      <span>Montar Meu Próprio Drink</span>
                    </button>
                  </div>
                </div>

                {/* Ilustração Tropical à Direita */}
                <div className="lg:col-span-5">
                  <TropicalHeroArt />
                </div>
              </div>
            </section>

            {/* Seletor de Categorias do Cardápio */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-5 h-5 text-[#ea580c]" />
                <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#2d1810]">
                  Nosso Cardápio de Verão
                </h2>
              </div>

              <div className="flex flex-wrap gap-2">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-4 py-2 rounded-full text-xs font-bold transition-all cursor-pointer ${
                      selectedCategory === cat
                        ? 'bg-[#2d1810] text-[#fff8ee] shadow-sm'
                        : 'bg-white/80 text-[#69432e] hover:bg-white border border-[#e6c8a5]'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Grade de Drinks */}
            {loading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-7">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-96 rounded-[28px] bg-white/50 border border-[#ebd0b2] animate-pulse"
                  />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-7">
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

      <footer className="border-t border-[#ead0b2]/70 bg-[#fffaf2]/60 py-6 mt-14 text-center text-xs font-medium text-[#7c533d]">
        🍹 Bartender Tropical · Coquetelaria Automatizada com ESP32
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

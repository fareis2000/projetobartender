/**
 * @file src/pages/CustomerMachinePage.tsx
 * @description Página principal de Autoatendimento Mobile-First (`/m/:machineSlug`) acionada quando o
 * cliente aponta a câmera do celular para o QR Code da máquina Bartender.OS.
 *
 * Arquitetura de Resiliência Mobile 4G/5G & Jornada de Conversão em 3 Toques:
 * - **Zero App / Zero Wi-Fi Local**: roda direto no navegador padrão do iOS/Android pela rede móvel do
 *   cliente, eliminando a barreira de baixar app ou pedir senha de Wi-Fi no bar lotado.
 * - **Tripla Sincronização Resiliente**:
 *   1. **WebSocket dedicado** (`/api/ws/machines/:slug`) com reconexão automática a cada 2.5s para
 *      atualizar progresso das bombas, fila e estoque das garrafas em tempo real;
 *   2. **Evento `visibilitychange`**: assim que o cliente sai do navegador para pagar o Pix no app do
 *      banco (Nubank, Itaú, Inter, etc.) e volta para a aba do drink, a página ressincroniza no mesmo
 *      milissegundo (`loadContext` + `refreshOrder`), já exibindo o Pix aprovado!
 *   3. **Polling leve de segurança (2.2s)** enquanto houver pedido ativo não-terminal, blindando a UX
 *      contra quedas silenciosas de pacotes TCP quando o 4G alterna de antena dentro da balada.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Citrus, Lock, QrCode, Sparkles, Sun } from 'lucide-react';
import { bartenderApi } from '../api/client';
import { CustomDrinkBuilder } from '../components/CustomDrinkBuilder';
import { CustomerOrderSheet } from '../components/CustomerOrderSheet';
import { DrinkCard } from '../components/DrinkCard';
import { type ActiveTab, Navbar } from '../components/Navbar';
import { TropicalBackdropLeaves, TropicalHeroArt } from '../components/TropicalDecor';
import type {
  DrinkRecipe,
  MachinePublicContext,
  MachineRealtimeSnapshot,
  Order,
  PumpId,
  PumpSlot,
} from '../types/bartender';
import { getOrCreateCustomerSessionId, navigateTo } from '../utils/format';

/**
 * Propriedades da página pública da máquina (`CustomerMachinePage`).
 */
interface CustomerMachinePageProps {
  /** Identificador único da máquina extraído da rota `/m/:machineSlug`. */
  machineSlug: string;
}

/**
 * Orquestrador completo da jornada do consumidor final: vitrine de drinks, construtor por ml,
 * pagamento Pix e liberação segura das bombas.
 */
export const CustomerMachinePage: React.FC<CustomerMachinePageProps> = ({ machineSlug }) => {
  /** Identificador persistente da sessão deste smartphone no `localStorage`. */
  const sessionId = useMemo(() => getOrCreateCustomerSessionId(), []);
  const [activeTab, setActiveTab] = useState<ActiveTab>('menu');
  const [selectedCategory, setSelectedCategory] = useState<string>('Todos');
  /** Contexto público completo do bar e da máquina sincronizada. */
  const [ctx, setCtx] = useState<MachinePublicContext | null>(null);
  /** Pedido ativo pertencente ao cliente atual (restaurado inclusive após F5 ou retorno do banco). */
  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [busyCreating, setBusyCreating] = useState(false);
  const [busyOrderAction, setBusyOrderAction] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * Carrega cardápio, bombas e estado da máquina, reabrindo automaticamente o `CustomerOrderSheet`
   * caso esta sessão já possua um pedido pago ou aguardando pagamento (`active_customer_order`).
   */
  const loadContext = useCallback(async () => {
    try {
      const data = await bartenderApi.getPublicMachine(machineSlug, sessionId);
      setCtx(data);
      if (data.active_customer_order) {
        setCurrentOrder(data.active_customer_order);
        setSheetOpen(true);
      }
      setErrorBanner(null);
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : 'Não foi possível sincronizar com esta máquina.',
      );
    } finally {
      setLoading(false);
    }
  }, [machineSlug, sessionId]);

  useEffect(() => {
    setLoading(true);
    void loadContext();
  }, [loadContext]);

  /** Consulta o status mais recente do pedido ativo e força a abertura do modal na hora de pôr o copo. */
  const refreshOrder = useCallback(async (ordId: string) => {
    try {
      const updated = await bartenderApi.getOrder(ordId);
      setCurrentOrder(updated);
      if (updated.status === 'READY_FOR_CUP' || updated.status === 'DISPENSING') {
        setSheetOpen(true);
      }
    } catch {
      // ignora oscilação momentânea de 4G
    }
  }, []);

  // Reconexão imediata quando o cliente volta do aplicativo do banco (visibilitychange)!
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void loadContext();
        if (currentOrder?.id) {
          void refreshOrder(currentOrder.id);
        }
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [currentOrder?.id, loadContext, refreshOrder]);

  // Polling leve do pedido ativo (garante atualização mesmo se 4G trocar de antena)
  useEffect(() => {
    if (!currentOrder) return;
    if (['COMPLETED', 'CANCELED', 'EXPIRED', 'REFUNDED'].includes(currentOrder.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshOrder(currentOrder.id);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [currentOrder, refreshOrder]);

  // WebSocket em tempo real da máquina específica (/api/ws/machines/:slug)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let unmounted = false;

    const connectWs = () => {
      if (unmounted) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(
        `${protocol}//${window.location.host}/api/ws/machines/${encodeURIComponent(machineSlug)}`,
      );

      ws.onmessage = (event) => {
        try {
          const snap = JSON.parse(event.data) as MachineRealtimeSnapshot;
          setCtx((prev) =>
            prev
              ? {
                  ...prev,
                  status: snap.status,
                  hardware: snap.hardware,
                  queue_length: snap.queue_length,
                  ready_order_number: snap.ready_order_number,
                  pumps: snap.pumps,
                }
              : prev,
          );
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
  }, [machineSlug]);

  /** Dicionário indexado das bombas atuais da máquina. */
  const pumpsById = useMemo(() => {
    const map = {} as Record<PumpId, PumpSlot>;
    for (const p of ctx?.pumps ?? []) map[p.pump_id] = p;
    return map;
  }, [ctx?.pumps]);

  /** Lista única de categorias extraída dinamicamente dos drinks ativos do bar. */
  const categories = useMemo(() => {
    const unique = Array.from(new Set((ctx?.drinks ?? []).map((d) => d.category)));
    return ['Todos', ...unique];
  }, [ctx?.drinks]);

  /** Lista de receitas filtrada pela pílula de categoria escolhida pelo usuário. */
  const filteredDrinks = useMemo(() => {
    const list = ctx?.drinks ?? [];
    if (selectedCategory === 'Todos') return list;
    return list.filter((d) => d.category === selectedCategory);
  }, [ctx?.drinks, selectedCategory]);

  /** Inicia pedido Pix de 1 toque para uma receita pronta do cardápio. */
  const handleOrderPreset = async (drink: DrinkRecipe) => {
    setBusyCreating(true);
    setErrorBanner(null);
    setOrderError(null);
    try {
      const ord = await bartenderApi.createPresetOrder(machineSlug, {
        drink_id: drink.id,
        customer_session_id: sessionId,
      });
      setCurrentOrder(ord);
      setSheetOpen(true);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : 'Erro ao gerar pedido Pix.');
    } finally {
      setBusyCreating(false);
    }
  };

  /** Inicia pedido Pix para uma combinação autoral criada na aba `"Monte por ml"`. */
  const handleOrderCustom = async (payload: {
    name: string;
    amarelo: number;
    vermelho: number;
    verde: number;
    azul: number;
  }) => {
    setBusyCreating(true);
    setErrorBanner(null);
    setOrderError(null);
    try {
      const ord = await bartenderApi.createCustomOrder(machineSlug, {
        ...payload,
        customer_session_id: sessionId,
      });
      setCurrentOrder(ord);
      setSheetOpen(true);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : 'Erro ao criar drink personalizado.');
    } finally {
      setBusyCreating(false);
    }
  };

  /** Confirma pagamento simulado (Sandbox) para testes e demonstrações comerciais. */
  const handleSimulatePay = async () => {
    if (!currentOrder) return;
    setBusyOrderAction(true);
    setOrderError(null);
    try {
      const updated = await bartenderApi.simulatePayOrder(currentOrder.id);
      setCurrentOrder(updated);
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Falha ao simular pagamento.');
    } finally {
      setBusyOrderAction(false);
    }
  };

  /** Cancela cobrança Pix ainda não paga e fecha o modal. */
  const handleCancelPending = async () => {
    if (!currentOrder) return;
    setBusyOrderAction(true);
    setOrderError(null);
    try {
      await bartenderApi.cancelOrder(currentOrder.id, sessionId);
      setCurrentOrder(null);
      setSheetOpen(false);
      await loadContext();
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Erro ao cancelar pedido.');
    } finally {
      setBusyOrderAction(false);
    }
  };

  /** Reativa a vez do cliente na frente da máquina ou adiciona fôlego extra no timer de copo. */
  const handleResumeTurn = async () => {
    if (!currentOrder) return;
    setBusyOrderAction(true);
    setOrderError(null);
    try {
      const updated = await bartenderApi.resumeOrderTurn(currentOrder.id, sessionId);
      setCurrentOrder(updated);
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Erro ao renovar vez.');
    } finally {
      setBusyOrderAction(false);
    }
  };

  /** Confirma copo posicionado na plataforma e ordena o início imediato da dosagem física. */
  const handleConfirmCupAndDispense = async (confirmed: boolean) => {
    if (!currentOrder) return;
    setBusyOrderAction(true);
    setOrderError(null);
    try {
      const updated = await bartenderApi.confirmCupAndDispense(
        currentOrder.id,
        sessionId,
        confirmed,
      );
      setCurrentOrder(updated);
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : 'Não foi possível iniciar o preparo.');
    } finally {
      setBusyOrderAction(false);
    }
  };

  const activeLiveOrder =
    currentOrder &&
    !['COMPLETED', 'CANCELED', 'EXPIRED', 'REFUNDED'].includes(currentOrder.status)
      ? currentOrder
      : null;

  return (
    <div className="min-h-screen flex flex-col relative">
      <TropicalBackdropLeaves />

      <Navbar
        barName={ctx?.bar_name ?? 'Bartender.OS'}
        machineName={ctx?.machine_name ?? 'Sincronizando...'}
        machineSlug={machineSlug}
        allowCustomBuilder={ctx?.allow_custom_builder ?? true}
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        queueLength={ctx?.queue_length ?? 0}
        activeOrder={activeLiveOrder}
        onOpenActiveOrder={() => setSheetOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-7 sm:py-10 space-y-9">
        {errorBanner && (
          <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-sm text-rose-800">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <span>{errorBanner}</span>
          </div>
        )}

        {activeTab === 'menu' || !ctx?.allow_custom_builder ? (
          <>
            {/* Hero Sincronizado com a Máquina */}
            <section className="relative rounded-[34px] bg-gradient-to-br from-[#fff5e4] via-[#ffe6c4] to-[#ffd2a6] border border-[#ebcaa3] p-6 sm:p-10 lg:px-12 overflow-hidden shadow-[0_24px_50px_-20px_rgba(165,82,25,0.2)]">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                <div className="lg:col-span-7 space-y-4">
                  <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/85 border border-[#e7c59d] text-[#b45309] text-xs font-bold">
                    <QrCode className="w-4 h-4 text-[#ea580c]" />
                    <span>Conectado à {ctx?.machine_name ?? machineSlug} · Pague via Pix no Celular</span>
                  </div>

                  <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#2d1810] leading-[1.12]">
                    Peça na tela, pague no Pix e{' '}
                    <span className="text-[#ea580c] italic">sirva na medida exata.</span>
                  </h1>

                  <p className="text-sm sm:text-base text-[#5e3b29] leading-relaxed max-w-xl">
                    Sem filas no caixa e sem precisar conectar no Wi-Fi: escolha um drink pronto do{' '}
                    <strong>{ctx?.bar_name ?? 'bar'}</strong> ou monte sua receita pagando apenas
                    pelos mililitros escolhidos.
                  </p>

                  {ctx?.allow_custom_builder && (
                    <div className="pt-1 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setActiveTab('custom')}
                        className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] hover:brightness-105 text-white font-sans-ui font-bold text-sm shadow-lg shadow-emerald-700/20 transition-all cursor-pointer"
                      >
                        <Citrus className="w-4 h-4" />
                        <span>Montar Meu Drink por ml</span>
                      </button>
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#69432e]">
                        <Sun className="w-4 h-4 text-[#f59e0b]" />
                        Bombas só ligam quando seu copo estiver posicionado
                      </span>
                    </div>
                  )}
                </div>

                <div className="lg:col-span-5 hidden sm:block">
                  <TropicalHeroArt />
                </div>
              </div>
            </section>

            {/* Categorias */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-5 h-5 text-[#ea580c]" />
                <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#2d1810]">
                  Cardápio da Máquina
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
            ) : filteredDrinks.length === 0 ? (
              <div className="p-10 text-center rounded-3xl bg-white/75 border border-[#ebd0b2] text-sm text-[#69432e]">
                Nenhum drink cadastrado nesta categoria no momento.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-7">
                {filteredDrinks.map((drink) => (
                  <DrinkCard
                    key={drink.id}
                    drink={drink}
                    pumpsById={pumpsById}
                    busyCreating={busyCreating}
                    onOrderDrink={handleOrderPreset}
                  />
                ))}
              </div>
            )}
          </>
        ) : (
          ctx && (
            <CustomDrinkBuilder
              pumps={ctx.pumps}
              maxCupMl={ctx.max_cup_ml}
              cupFeeCents={ctx.cup_fee_cents}
              minOrderCents={ctx.min_order_cents}
              busyCreating={busyCreating}
              onSubmitCustom={handleOrderCustom}
            />
          )
        )}
      </main>

      <footer className="border-t border-[#ead0b2]/70 bg-[#fffaf2]/70 py-6 mt-12 px-4 text-center text-xs font-medium text-[#7c533d] flex flex-col sm:flex-row items-center justify-center gap-4">
        <span>🍹 Bartender.OS v3.0 · Autosserviço Inteligente via Pix</span>
        <button
          type="button"
          onClick={() => navigateTo('/painel')}
          className="inline-flex items-center gap-1 text-[#b45309] hover:underline font-semibold cursor-pointer"
        >
          <Lock className="w-3 h-3" />
          <span>Área do Dono do Bar</span>
        </button>
      </footer>

      {ctx && (
        <CustomerOrderSheet
          visible={sheetOpen}
          order={currentOrder}
          machineStatus={ctx.status}
          pumpsById={pumpsById}
          busyAction={busyOrderAction}
          errorMsg={orderError}
          onSimulatePay={handleSimulatePay}
          onCancelPending={handleCancelPending}
          onResumeTurn={handleResumeTurn}
          onConfirmCupAndDispense={handleConfirmCupAndDispense}
          onClose={() => {
            setSheetOpen(false);
            if (currentOrder?.status === 'COMPLETED') {
              setCurrentOrder(null);
              void loadContext();
            }
          }}
        />
      )}
    </div>
  );
};

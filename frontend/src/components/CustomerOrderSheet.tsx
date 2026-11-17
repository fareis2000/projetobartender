/**
 * @file src/components/CustomerOrderSheet.tsx
 * @description Bottom-sheet / Modal de checkout Pix, fila inteligente anti-travamento, confirmação
 * obrigatória de copo na base e telemetria visual de dosagem em tempo real.
 *
 * Papel Crítico na Operação Real de Bar & Mitigação de Riscos Físicos:
 * - **Etapa 1 (`PENDING_PAYMENT`)**: Prioriza o botão gigante `"Pix Copia e Cola"` pensado para quem já
 *   está segurando o próprio celular, deixando a imagem do QR Code recolhida em `<details>` para quem
 *   paga com um segundo aparelho. Inclui também o botão de aprovação em 1 clique quando em modo `simulated`,
 *   perfeito para feiras, pitches e demonstrações comerciais B2B.
 * - **Etapa 2 (`PAID_QUEUED` / `PAUSED_TURN`)**: Gerencia filas de balcão movimentado sem caos: avisa para
 *   NÃO colocar o copo enquanto outra pessoa está na frente, e se o cliente demorar para chegar até a
 *   máquina, pausa sua vez (`PAUSED_TURN`) preservando 100% do crédito pago sem travar os próximos clientes!
 * - **Etapa 3 (`READY_FOR_CUP`)**: Vibra o smartphone (`navigator.vibrate`) quando chega a vez do cliente
 *   e exige um checkbox explícito confirmando que o copo vazio está posicionado no centro da bandeja antes
 *   de energizar as bombas — eliminando derramamento de bebida cara no balcão.
 * - **Etapa 4 (`DISPENSING` / `COMPLETED` / `FAILED_DISPENSE`)**: Mostra o copo enchendo ao vivo sincronizado
 *   via WebSocket com o progresso real das bombas ou orienta reenvio/estorno caso ocorra parada física.
 */
import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  GlassWater,
  PartyPopper,
  Play,
  QrCode,
  Sparkles,
  Users,
  X,
  Zap,
} from 'lucide-react';
import type { Order, PreparationStatus, PumpId, PumpSlot } from '../types/bartender';
import { formatBrl } from '../utils/format';
import { GlassArtwork } from './GlassArtwork';

/**
 * Propriedades do componente `CustomerOrderSheet`.
 */
interface CustomerOrderSheetProps {
  /** Define se a folha/modal está aberta na tela do cliente. */
  visible: boolean;
  /** Objeto completo do pedido atual do cliente (`null` se nenhum pedido ativo). */
  order: Order | null;
  /** Estado em tempo real das bombas da máquina recebido via WebSocket/REST. */
  machineStatus: PreparationStatus;
  /** Mapa das 4 bombas para colorir o jato ativo com a cor exata do ingrediente em curso. */
  pumpsById: Record<PumpId, PumpSlot>;
  /** Desabilita botões de transição enquanto uma requisição de ação do pedido está pendente. */
  busyAction: boolean;
  /** Mensagem de erro contextual das ações do modal, se houver. */
  errorMsg: string | null;
  /** Aprova pagamento instantâneo quando o bar opera em modo de demonstração (`simulated`). */
  onSimulatePay: () => void;
  /** Cancela a cobrança Pix pendente e libera o cliente para escolher outro drink. */
  onCancelPending: () => void;
  /** Retoma uma vez pausada (`PAUSED_TURN`) ou renova +60s para o cliente buscar gelo/copo. */
  onResumeTurn: () => void;
  /** Envia a confirmação de segurança de copo posicionado e inicia o despejo físico das bombas. */
  onConfirmCupAndDispense: (confirmed: boolean) => void;
  /** Minimiza ou encerra o modal quando permitido pelo estado atual do pedido. */
  onClose: () => void;
}

/**
 * Orquestrador visual das 4 fases pós-clique de compra no smartphone do consumidor.
 */
export const CustomerOrderSheet: React.FC<CustomerOrderSheetProps> = ({
  visible,
  order,
  machineStatus,
  pumpsById,
  busyAction,
  errorMsg,
  onSimulatePay,
  onCancelPending,
  onResumeTurn,
  onConfirmCupAndDispense,
  onClose,
}) => {
  /** Feedback visual temporário ("Copiado!") após copiar o código EMV Pix. */
  const [copied, setCopied] = useState(false);
  /** Estado do aceite obrigatório confirmando que o copo está centralizado na plataforma. */
  const [cupChecked, setCupChecked] = useState(false);
  /** Contador regressivo local em segundos para expiração do Pix. */
  const [localPixCountdown, setLocalPixCountdown] = useState(0);
  /** Contador regressivo local em segundos da janela de vez na frente da máquina. */
  const [localTurnCountdown, setLocalTurnCountdown] = useState(0);

  // Reseta o checkbox de confirmação de copo sempre que o pedido ou seu status mudar
  useEffect(() => {
    setCupChecked(false);
  }, [order?.id, order?.status]);

  // Sincroniza os cronômetros locais com os valores autoritativos calculados pelo servidor
  useEffect(() => {
    setLocalPixCountdown(order?.seconds_until_pix_expiry ?? 0);
    setLocalTurnCountdown(order?.seconds_until_turn_expiry ?? 0);
  }, [order?.seconds_until_pix_expiry, order?.seconds_until_turn_expiry, order?.status]);

  // Decrementa suavemente a cada 1 segundo para feedback visual fluido entre polls de rede
  useEffect(() => {
    if (!visible || !order) return;
    const timer = window.setInterval(() => {
      setLocalPixCountdown((s) => Math.max(0, s - 1));
      setLocalTurnCountdown((s) => Math.max(0, s - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [visible, order]);

  // Vibra o celular quando chega a vez de colocar o copo!
  useEffect(() => {
    if (order?.status === 'READY_FOR_CUP' && 'vibrate' in navigator) {
      try {
        navigator.vibrate([180, 90, 220]);
      } catch {
        // ignora se navegador bloquear
      }
    }
  }, [order?.status]);

  if (!visible || !order) return null;

  /** Copia o payload Pix Copia e Cola para a área de transferência do celular. */
  const copyPix = async () => {
    try {
      await navigator.clipboard.writeText(order.pix_qr_code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 3000);
    } catch {
      // fallback seleção
    }
  };

  /** Formata segundos inteiros em `MM:SS` (ex.: `04:59`). */
  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const r = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
  };

  const isMyPour =
    order.status === 'DISPENSING' ||
    (machineStatus.order_id === order.id && machineStatus.state === 'dispensing');

  const activePumpColor = machineStatus.current_pump
    ? pumpsById[machineStatus.current_pump]?.color_hex ?? '#ea580c'
    : null;

  const orderLayers = order.items.map((it) => ({
    color: it.color_hex,
    ml: it.ml,
    label: it.ingredient,
  }));

  // Impede fechar acidentalmente o modal no momento crítico de confirmar o copo ou durante o jato
  const canDismiss =
    order.status === 'COMPLETED' ||
    order.status === 'CANCELED' ||
    order.status === 'EXPIRED' ||
    order.status === 'REFUNDED' ||
    order.status === 'PENDING_PAYMENT' ||
    order.status === 'PAID_QUEUED';

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-[#2d1810]/55 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[92vh] overflow-y-auto rounded-t-[32px] sm:rounded-[32px] bg-[#fffaf2] border-2 border-[#ebd0b2] p-6 sm:p-7 shadow-2xl space-y-5">
        {/* Cabeçalho do Pedido */}
        <div className="flex items-center justify-between gap-3 border-b border-[#eed6b8] pb-3.5">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-[#b45309]">
              Senha #{order.order_number} · {order.machine_name}
            </span>
            <h3 className="font-display text-xl sm:text-2xl font-bold text-[#2d1810]">
              {order.drink_name}
            </h3>
          </div>
          {canDismiss && (
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-full bg-[#f5e5ce] hover:bg-[#ebd3b2] text-[#5c3724] cursor-pointer"
              title="Minimizar janela"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {errorMsg && (
          <div className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-xs font-semibold text-rose-700">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* ==================== ETAPA 1: PAGAMENTO PIX NO CELULAR ==================== */}
        {order.status === 'PENDING_PAYMENT' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 rounded-2xl bg-gradient-to-r from-[#fff3df] to-[#ffe6c4] border border-[#ebd0b2]">
              <div>
                <span className="text-xs font-semibold text-[#7c533d] block">
                  Total ({order.total_ml} ml)
                </span>
                <span className="font-display text-3xl font-extrabold text-[#15803d]">
                  {formatBrl(order.total_cents)}
                </span>
              </div>
              <div className="text-right">
                <span className="inline-flex items-center gap-1 text-xs font-bold text-[#b45309] bg-white/80 px-3 py-1 rounded-full border border-[#e7c59d]">
                  <Clock className="w-3.5 h-3.5" />
                  Expira em {formatTimer(localPixCountdown)}
                </span>
              </div>
            </div>

            {/* Botão Principal p/ Celular: PIX COPIA E COLA */}
            <div className="space-y-2.5">
              <button
                type="button"
                onClick={copyPix}
                className={`w-full py-4 px-5 rounded-2xl font-sans-ui font-bold text-base flex items-center justify-center gap-2.5 shadow-lg transition-all cursor-pointer ${
                  copied
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:brightness-105 text-white'
                }`}
              >
                {copied ? (
                  <>
                    <Check className="w-5 h-5" />
                    <span>Código Pix Copiado! Abra o app do seu banco</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-5 h-5" />
                    <span>Copiar Código Pix (Copia e Cola)</span>
                  </>
                )}
              </button>

              <p className="text-xs text-center text-[#7c533d]">
                1. Toque acima para copiar · 2. Pague no app do seu banco · 3. Volte para esta tela!
              </p>
            </div>

            {/* QR Code Secundário */}
            {order.pix_qr_base64 && (
              <details className="rounded-2xl bg-white border border-[#ecd3b5] p-3 text-center">
                <summary className="text-xs font-bold text-[#69432e] cursor-pointer flex items-center justify-center gap-1.5">
                  <QrCode className="w-4 h-4 text-[#ea580c]" />
                  <span>Mostrar imagem do QR Code (caso pague com outro celular)</span>
                </summary>
                <div className="pt-3 flex flex-col items-center">
                  <img
                    src={order.pix_qr_base64}
                    alt="QR Code Pix"
                    className="w-44 h-44 rounded-xl border border-[#ebd0b2]"
                  />
                </div>
              </details>
            )}

            {/* Resumo dos ml */}
            <div className="rounded-2xl bg-[#fdf5ea] border border-[#ecd3b5] p-3.5 space-y-1.5 text-xs text-[#593826]">
              {order.items.map((it) => (
                <div key={it.pump} className="flex justify-between">
                  <span>
                    {it.ml} ml · <strong>{it.ingredient}</strong>
                  </span>
                  <span>{formatBrl(it.price_cents)}</span>
                </div>
              ))}
              {order.cup_fee_cents > 0 && (
                <div className="flex justify-between text-[#7c533d]">
                  <span>Copo + gelo</span>
                  <span>{formatBrl(order.cup_fee_cents)}</span>
                </div>
              )}
            </div>

            {/* Faixa Sandbox caso o bar esteja em Modo Pix Simulado */}
            {order.payment_provider === 'simulated' && (
              <div className="p-3.5 rounded-2xl bg-amber-50 border border-dashed border-amber-400 space-y-2">
                <div className="flex items-center justify-center gap-1.5 text-xs font-bold text-amber-900">
                  <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                  <span>Ambiente de Demonstração (Pix Simulado Ativo)</span>
                </div>
                <button
                  type="button"
                  disabled={busyAction}
                  onClick={onSimulatePay}
                  className="w-full py-2.5 px-4 rounded-xl bg-[#2d1810] hover:bg-[#432519] text-[#fff8ee] text-xs font-bold flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  <Zap className="w-4 h-4 text-amber-400" />
                  <span>Simular Confirmação Instantânea do Banco</span>
                </button>
              </div>
            )}

            <button
              type="button"
              disabled={busyAction}
              onClick={onCancelPending}
              className="w-full py-2.5 text-xs font-semibold text-rose-700 hover:underline cursor-pointer"
            >
              Cancelar pedido
            </button>
          </div>
        )}

        {/* ==================== ETAPA 2: AGUARDANDO NA FILA ==================== */}
        {order.status === 'PAID_QUEUED' && (
          <div className="text-center space-y-4 py-2">
            <div className="w-16 h-16 mx-auto rounded-3xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <Users className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <span className="inline-block px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
                Pix Confirmado! Você está na fila
              </span>
              <h4 className="font-display text-2xl font-bold text-[#2d1810]">
                Posição #{order.queue_position} na fila da máquina
              </h4>
              <p className="text-sm text-[#69432e]">
                Há um preparo em andamento na sua frente.{' '}
                <strong>Ainda não coloque o seu copo!</strong> Avisaremos você aqui assim que a
                plataforma estiver livre.
              </p>
            </div>
          </div>
        )}

        {/* ==================== ETAPA 2B: VEZ PAUSADA (NÃO TRAVA A FILA) ==================== */}
        {order.status === 'PAUSED_TURN' && (
          <div className="text-center space-y-4 py-2">
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 space-y-2">
              <h4 className="font-display text-xl font-bold text-amber-950">
                Seu crédito está guardado! (Senha #{order.order_number})
              </h4>
              <p className="text-xs text-amber-800 leading-relaxed">
                Como o tempo de espera na frente da máquina passou, liberamos a vez para não travar a
                fila — mas seu drink continua 100% pago!
              </p>
            </div>
            <button
              type="button"
              disabled={busyAction}
              onClick={onResumeTurn}
              className="w-full py-4 px-5 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white font-bold text-sm shadow-lg flex items-center justify-center gap-2 cursor-pointer"
            >
              <Play className="w-4 h-4" />
              <span>Já estou na frente da máquina — Liberar minha vez!</span>
            </button>
          </div>
        )}

        {/* ==================== ETAPA 3: PERGUNTA OBRIGATÓRIA DO COPO ==================== */}
        {order.status === 'READY_FOR_CUP' && !isMyPour && (
          <div className="space-y-4">
            <div className="p-4 rounded-3xl bg-gradient-to-br from-emerald-50 to-teal-50 border-2 border-emerald-400 text-center space-y-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-600 text-white text-xs font-bold">
                <CheckCircle2 className="w-3.5 h-3.5" />
                SUA VEZ NA MÁQUINA! ({formatTimer(localTurnCountdown)})
              </span>
              <h4 className="font-display text-2xl font-extrabold text-[#14532d]">
                Seu copo já está na plataforma?
              </h4>
              <p className="text-xs sm:text-sm text-[#166534]">
                Posicione um copo vazio (mín. <strong>{Math.ceil(order.total_ml + 40)} ml</strong>) bem
                no centro da base da <strong>{order.machine_name}</strong> antes de ligar as bombas!
              </p>
            </div>

            {/* Confirmação Obrigatória */}
            <label className="flex items-start gap-3 p-4 rounded-2xl bg-white border-2 border-[#e5c7a3] hover:border-emerald-500 cursor-pointer select-none transition-colors">
              <input
                type="checkbox"
                checked={cupChecked}
                onChange={(e) => setCupChecked(e.target.checked)}
                className="mt-0.5 w-5 h-5 accent-emerald-600 rounded cursor-pointer"
              />
              <span className="text-xs sm:text-sm font-semibold text-[#2d1810] leading-snug">
                Sim! Confirmo que o meu copo já está posicionado na plataforma da máquina e posso
                iniciar o despejo agora.
              </span>
            </label>

            <button
              type="button"
              disabled={!cupChecked || busyAction}
              onClick={() => onConfirmCupAndDispense(cupChecked)}
              className="w-full py-4 px-5 rounded-2xl bg-gradient-to-r from-[#15803d] to-[#0d9488] hover:brightness-105 text-white font-sans-ui font-extrabold text-base shadow-xl shadow-emerald-700/25 flex items-center justify-center gap-2.5 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <GlassWater className="w-5 h-5" />
              <span>{busyAction ? 'Acionando Bombas...' : 'SERVIR MEU DRINK AGORA!'}</span>
            </button>

            <div className="text-center">
              <button
                type="button"
                onClick={onResumeTurn}
                className="text-xs font-semibold text-[#7c533d] hover:underline cursor-pointer"
              >
                Preciso de mais +60 segundos para pegar gelo/copo
              </button>
            </div>
          </div>
        )}

        {/* ==================== ETAPA 4: SERVINDO AO VIVO & CONCLUÍDO ==================== */}
        {(isMyPour || order.status === 'COMPLETED' || order.status === 'FAILED_DISPENSE') && (
          <div className="text-center space-y-4">
            <div className="flex flex-col items-center justify-center py-4 rounded-3xl bg-gradient-to-b from-[#fff3df] to-[#ffe6c4] border border-[#edd2b2]">
              <GlassArtwork
                layers={orderLayers}
                fillOverridePercent={
                  order.status === 'COMPLETED' ? 92 : Math.max(8, machineStatus.progress)
                }
                pouringColor={isMyPour ? activePumpColor : null}
                size="md"
              />
            </div>

            {order.status === 'COMPLETED' ? (
              <div className="space-y-2">
                <div className="inline-flex items-center gap-1.5 text-[#15803d] text-sm font-bold">
                  <PartyPopper className="w-5 h-5" />
                  <span>Saúde! Seu drink está 100% servido!</span>
                </div>
                <p className="text-xs text-[#69432e]">
                  Já pode retirar seu copo da plataforma e aproveitar!
                </p>
                <button
                  type="button"
                  onClick={onClose}
                  className="w-full mt-2 py-3.5 px-4 rounded-2xl bg-gradient-to-r from-[#ea580c] to-[#f97316] text-white font-bold text-sm shadow-md cursor-pointer"
                >
                  Fechar e Pedir Outro
                </button>
              </div>
            ) : order.status === 'FAILED_DISPENSE' ? (
              <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-xs text-rose-800 space-y-1">
                <strong className="block text-sm">Houve uma interrupção na máquina</strong>
                <p>
                  Fique tranquilo: informe a senha <strong>#{order.order_number}</strong> ao bar para
                  reenviar seu drink à fila ou receber estorno imediato no Pix!
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-[#2d1810]">
                  {machineStatus.message || 'Servindo seu drink...'}
                </p>
                <div className="h-3.5 w-full rounded-full bg-[#f2e2cd] overflow-hidden p-0.5">
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.max(5, machineStatus.progress)}%`,
                      backgroundColor: activePumpColor ?? '#16a34a',
                    }}
                  />
                </div>
                <p className="text-xs text-[#7c533d]">
                  Não retire o copo até chegar em <strong>100%</strong> ({machineStatus.progress}%)
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

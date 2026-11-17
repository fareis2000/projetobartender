/**
 * @file PreparationModal.tsx
 * @description Modal de telemetria ao vivo durante a preparação do drink com botão de Parada de Emergência.
 *
 * Papel na Arquitetura / Segurança Operacional:
 * ---------------------------------------------
 * Abre automaticamente em todas as telas conectadas ao WebSocket (`/api/ws`) assim que
 * `status.state === 'dispensing'`:
 *   - Exibe o copo `GlassArtwork` enchendo gradualmente de `0%` a `100%` com o feixe líquido
 *     na cor exata da bomba ligada naquele instante (`activePumpColor`);
 *   - Mostra cronômetro ao vivo (`elapsed_seconds` vs `total_seconds`) e o meio de transporte ativo;
 *   - Destaca em vermelho de alto contraste o botão **"Parar Agora (Desligar Bombas)"**,
 *     permitindo que qualquer operador ou usuário interrompa os motores instantaneamente caso o
 *     copo seja removido antes do fim;
 *   - Ao concluir (`completed`), comemora visualmente e libera o fechamento do modal.
 */
import React from 'react';
import { CheckCircle2, OctagonAlert, PartyPopper, XCircle } from 'lucide-react';
import type { PreparationStatus, PumpConfig, PumpId } from '../types/bartender';
import { GlassArtwork } from './GlassArtwork';

/** Propriedades do componente `PreparationModal`. */
interface PreparationModalProps {
  /** Controla se o overlay modal está visível na tela. */
  visible: boolean;
  /** Telemetria instantânea atualizada continuamente via WebSocket. */
  status: PreparationStatus;
  /** Dicionário das 4 bombas para traduzir `current_pump` em nome da bebida e cor hexadecimal. */
  pumpsById: Record<PumpId, PumpConfig>;
  /** Aciona o corte imediato de energia dos relés (`POST /api/stop`). */
  onEmergencyStop: () => void;
  /** Fecha o modal após finalização, erro ou parada manual. */
  onClose: () => void;
}

/**
 * Janela modal bloqueante para acompanhamento visual do preparo e controle de segurança.
 */
export const PreparationModal: React.FC<PreparationModalProps> = ({
  visible,
  status,
  pumpsById,
  onEmergencyStop,
  onClose,
}) => {
  if (!visible) return null;

  const isDispensing = status.state === 'dispensing';
  const isCompleted = status.state === 'completed';
  const isStopped = status.state === 'stopped';
  const isError = status.state === 'error';

  // Cor hexadecimal do ingrediente que está jorrando na mangueira ativa neste exato momento
  const activePumpColor = status.current_pump
    ? pumpsById[status.current_pump]?.color_hex ?? '#ea580c'
    : null;

  const displayLayers = [
    {
      color: activePumpColor ?? (isCompleted ? '#10b981' : '#f97316'),
      ml: Math.max(15, status.progress * 3.5),
    },
  ];

  const transportLabel =
    status.transport === 'wifi'
      ? 'ESP32 via Wi-Fi'
      : status.transport === 'serial'
        ? 'ESP32 via Cabo USB'
        : 'Demonstração ao Vivo';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#2d1810]/45 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-[32px] bg-[#fffaf2] border-2 border-[#ebd0b2] p-7 shadow-2xl text-center space-y-5">
        {/* Topo informativo */}
        <div className="flex items-center justify-between text-xs font-medium text-[#7c533d]">
          <span className="px-3 py-1 rounded-full bg-[#f8ebd8] border border-[#e6c8a5]">
            {transportLabel}
          </span>
          {status.total_seconds > 0 && (
            <span>
              {status.elapsed_seconds.toFixed(1)}s de ~{status.total_seconds.toFixed(1)}s
            </span>
          )}
        </div>

        {/* Copo animado recebendo a bebida */}
        <div className="flex flex-col items-center justify-center py-3 rounded-3xl bg-gradient-to-b from-[#fff3df] to-[#ffe6c4] border border-[#edd2b2]">
          <GlassArtwork
            layers={displayLayers}
            fillOverridePercent={isCompleted ? 92 : status.progress}
            pouringColor={isDispensing ? activePumpColor : null}
            size="md"
          />
        </div>

        {/* Mensagem principal */}
        <div className="space-y-1.5">
          {isCompleted && (
            <div className="inline-flex items-center gap-1.5 text-[#15803d] text-sm font-bold">
              <PartyPopper className="w-4 h-4" />
              <span>Saúde! Seu drink está servido!</span>
            </div>
          )}
          {(isStopped || isError) && (
            <div className="inline-flex items-center gap-1.5 text-rose-600 text-sm font-bold">
              <XCircle className="w-4 h-4" />
              <span>{isStopped ? 'Preparo Interrompido' : 'Ops! Falha na Conexão'}</span>
            </div>
          )}

          <h3 className="font-display text-2xl font-bold text-[#2d1810]">
            {status.drink_name ?? 'Preparando Drink'}
          </h3>
          <p className="text-sm text-[#69432e]">{status.message}</p>
        </div>

        {/* Barra de Progresso */}
        <div className="space-y-2">
          <div className="h-3.5 w-full rounded-full bg-[#f2e2cd] overflow-hidden p-0.5">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${status.progress}%`,
                backgroundColor:
                  isError || isStopped
                    ? '#e11d48'
                    : isCompleted
                      ? '#16a34a'
                      : (activePumpColor ?? '#f97316'),
              }}
            />
          </div>
          <div className="flex justify-between text-xs font-medium text-[#7c533d]">
            <span>
              {status.current_pump
                ? `Servindo: ${pumpsById[status.current_pump]?.ingredient ?? status.current_pump}`
                : isCompleted
                  ? 'Pronto para retirar'
                  : 'Aguarde um instante'}
            </span>
            <strong className="font-bold text-[#2d1810]">{status.progress}%</strong>
          </div>
        </div>

        {/* Botão de ação */}
        <div className="pt-1">
          {isDispensing ? (
            <button
              type="button"
              onClick={onEmergencyStop}
              className="w-full py-3.5 px-4 rounded-2xl font-sans-ui font-bold text-sm text-white bg-rose-600 hover:bg-rose-500 shadow-md shadow-rose-600/25 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <OctagonAlert className="w-4 h-4" />
              <span>Parar Agora (Desligar Bombas)</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="w-full py-3.5 px-4 rounded-2xl font-sans-ui font-bold text-sm text-white bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:brightness-105 shadow-md flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Fechar e Aproveitar</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

import React from 'react';
import { CheckCircle2, OctagonAlert, PartyPopper, XCircle } from 'lucide-react';
import type { PreparationStatus, PumpConfig, PumpId } from '../types/bartender';
import { GlassArtwork } from './GlassArtwork';

interface PreparationModalProps {
  visible: boolean;
  status: PreparationStatus;
  pumpsById: Record<PumpId, PumpConfig>;
  onEmergencyStop: () => void;
  onClose: () => void;
}

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

  const activePumpColor = status.current_pump
    ? pumpsById[status.current_pump]?.color_hex ?? '#f59e0b'
    : null;

  const displayLayers = [
    {
      color: activePumpColor ?? (isCompleted ? '#10b981' : '#f59e0b'),
      ml: Math.max(15, status.progress * 3.5),
    },
  ];

  const transportLabel =
    status.transport === 'wifi'
      ? 'ESP32 via Wi-Fi'
      : status.transport === 'serial'
        ? 'ESP32 via USB Serial'
        : 'Simulador em Tempo Real';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md">
      <div className="w-full max-w-md rounded-3xl bg-[#11131d] border border-white/15 p-7 shadow-2xl text-center space-y-5">
        {/* Tag de canal */}
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span className="px-2.5 py-1 rounded-full bg-white/[0.06] border border-white/10">
            {transportLabel}
          </span>
          {status.total_seconds > 0 && (
            <span>
              {status.elapsed_seconds.toFixed(1)}s / ~{status.total_seconds.toFixed(1)}s
            </span>
          )}
        </div>

        {/* Visual central */}
        <div className="flex flex-col items-center justify-center py-2">
          <GlassArtwork
            layers={displayLayers}
            fillOverridePercent={isCompleted ? 92 : status.progress}
            pouringColor={isDispensing ? activePumpColor : null}
            size="md"
          />
        </div>

        {/* Título e mensagem */}
        <div className="space-y-1.5">
          {isCompleted && (
            <div className="inline-flex items-center gap-1.5 text-emerald-400 text-sm font-semibold">
              <PartyPopper className="w-4 h-4" />
              <span>Drink Pronto!</span>
            </div>
          )}
          {(isStopped || isError) && (
            <div className="inline-flex items-center gap-1.5 text-rose-400 text-sm font-semibold">
              <XCircle className="w-4 h-4" />
              <span>{isStopped ? 'Preparo Interrompido' : 'Falha na Comunicação'}</span>
            </div>
          )}

          <h3 className="font-display text-2xl font-bold text-white">
            {status.drink_name ?? 'Preparando Drink'}
          </h3>
          <p className="text-sm text-slate-300">{status.message}</p>
        </div>

        {/* Barra de Progresso */}
        <div className="space-y-2">
          <div className="h-3 w-full rounded-full bg-white/[0.08] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${status.progress}%`,
                backgroundColor: isError || isStopped ? '#f43f5e' : isCompleted ? '#10b981' : (activePumpColor ?? '#f59e0b'),
              }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-400">
            <span>
              {status.current_pump
                ? `Ativa: ${pumpsById[status.current_pump]?.label ?? status.current_pump}`
                : isCompleted
                  ? 'Finalizado com sucesso'
                  : 'Aguardando etapa'}
            </span>
            <strong className="font-display text-white">{status.progress}%</strong>
          </div>
        </div>

        {/* Ações */}
        <div className="pt-2">
          {isDispensing ? (
            <button
              type="button"
              onClick={onEmergencyStop}
              className="w-full py-3 px-4 rounded-xl font-display font-bold text-sm text-white bg-rose-600 hover:bg-rose-500 shadow-lg shadow-rose-600/30 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <OctagonAlert className="w-4 h-4" />
              <span>Parada de Emergência (Desligar Bombas)</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="w-full py-3 px-4 rounded-xl font-display font-bold text-sm text-slate-950 bg-gradient-to-r from-amber-400 to-orange-500 hover:from-amber-300 hover:to-orange-400 flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Concluir</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};


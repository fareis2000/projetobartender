import React from 'react';

export interface LiquidLayer {
  color: string;
  ml: number;
  label?: string;
}

interface GlassArtworkProps {
  layers: LiquidLayer[];
  maxCapacityMl?: number;
  fillOverridePercent?: number;
  pouringColor?: string | null;
  size?: 'sm' | 'md' | 'lg';
}

export const GlassArtwork: React.FC<GlassArtworkProps> = ({
  layers,
  maxCapacityMl = 400,
  fillOverridePercent,
  pouringColor = null,
  size = 'md',
}) => {
  const uid = React.useId().replace(/:/g, '');
  const totalMl = layers.reduce((acc, l) => acc + Math.max(0, l.ml), 0);

  const computedFillPct =
    fillOverridePercent !== undefined
      ? Math.max(0, Math.min(100, fillOverridePercent))
      : Math.max(0, Math.min(96, (totalMl / maxCapacityMl) * 92));

  // Coordenadas internas do copo Highball no viewBox 0 0 180 220
  const glassTopY = 36;
  const glassBottomY = 192;
  const usableHeight = glassBottomY - glassTopY; // 156
  const totalLiquidHeight = (computedFillPct / 100) * usableHeight;
  const liquidStartY = glassBottomY - totalLiquidHeight;

  const dimensions =
    size === 'sm'
      ? 'w-28 h-36'
      : size === 'lg'
        ? 'w-48 h-60'
        : 'w-36 h-44';

  // Calcula fatias proporcionais empilhadas de baixo para cima
  let cursorY = glassBottomY;
  const renderedSlices =
    totalMl > 0 && totalLiquidHeight > 0
      ? layers
          .filter((l) => l.ml > 0)
          .map((l, idx) => {
            const h = (l.ml / totalMl) * totalLiquidHeight;
            cursorY -= h;
            return {
              key: `${idx}-${l.color}`,
              color: l.color,
              y: cursorY,
              height: h + 0.8,
            };
          })
      : [];

  const primaryGlow =
    layers.find((l) => l.ml > 0)?.color ?? pouringColor ?? '#f59e0b';

  return (
    <div className={`relative flex items-center justify-center select-none ${dimensions}`}>
      {/* Brilho ambiente de fundo */}
      <div
        className="absolute inset-4 rounded-full blur-2xl opacity-30 transition-colors duration-500 pointer-events-none"
        style={{ backgroundColor: primaryGlow }}
      />

      <svg
        viewBox="0 0 180 220"
        className="w-full h-full drop-shadow-[0_12px_24px_rgba(0,0,0,0.55)]"
        aria-hidden="true"
      >
        <defs>
          <clipPath id={`glass-clip-${uid}`}>
            <path d="M44 34 L136 34 L126 188 Q125 196 116 196 L64 196 Q55 196 54 188 Z" />
          </clipPath>
          <linearGradient id={`glass-sheen-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.24" />
            <stop offset="22%" stopColor="#ffffff" stopOpacity="0.06" />
            <stop offset="78%" stopColor="#ffffff" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.18" />
          </linearGradient>
        </defs>

        {/* Canudo metálico estilizado */}
        <path
          d="M108 190 L126 12 L136 10"
          fill="none"
          stroke="rgba(255,255,255,0.32)"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Jato ativo quando uma bomba está dosando */}
        {pouringColor && (
          <line
            x1="90"
            y1="4"
            x2="90"
            y2={Math.max(44, liquidStartY + 6)}
            stroke={pouringColor}
            strokeWidth="5"
            strokeLinecap="round"
            className="stream-flow"
          />
        )}

        {/* Conteúdo recortado dentro do copo */}
        <g clipPath={`url(#glass-clip-${uid})`}>
          {/* Fundo translúcido do vidro */}
          <rect x="36" y="30" width="108" height="172" fill="rgba(255,255,255,0.03)" />

          {/* Camadas líquidas */}
          {renderedSlices.map((slice) => (
            <rect
              key={slice.key}
              x="36"
              y={slice.y}
              width="108"
              height={slice.height}
              fill={slice.color}
              fillOpacity={0.86}
              style={{ transition: 'y 260ms ease, height 260ms ease' }}
            />
          ))}

          {/* Menisco iluminado no topo do líquido */}
          {totalLiquidHeight > 3 && (
            <ellipse
              cx="90"
              cy={liquidStartY}
              rx="45"
              ry="4"
              fill="#ffffff"
              fillOpacity="0.32"
            />
          )}

          {/* Cubos de gelo translúcidos quando há líquido */}
          {totalLiquidHeight > 30 && (
            <g opacity="0.35">
              <rect
                x="62"
                y={Math.min(155, liquidStartY + 14)}
                width="22"
                height="22"
                rx="5"
                transform={`rotate(-12 73 ${Math.min(155, liquidStartY + 25)})`}
                fill="#ffffff"
                fillOpacity="0.45"
                stroke="#ffffff"
                strokeWidth="1.2"
              />
              <rect
                x="92"
                y={Math.min(162, liquidStartY + 28)}
                width="20"
                height="20"
                rx="5"
                transform={`rotate(16 102 ${Math.min(162, liquidStartY + 38)})`}
                fill="#ffffff"
                fillOpacity="0.38"
                stroke="#ffffff"
                strokeWidth="1.2"
              />
            </g>
          )}

          {/* Bolhas de gás animadas */}
          {totalLiquidHeight > 24 && (
            <g fill="#ffffff" fillOpacity="0.55">
              <circle cx="72" cy="182" r="2.2" className="bubble-rise" style={{ animationDelay: '0s' }} />
              <circle cx="94" cy="186" r="1.8" className="bubble-rise" style={{ animationDelay: '0.8s' }} />
              <circle cx="110" cy="180" r="2.5" className="bubble-rise" style={{ animationDelay: '1.5s' }} />
              <circle cx="83" cy="176" r="1.6" className="bubble-rise" style={{ animationDelay: '2.0s' }} />
            </g>
          )}

          {/* Reflexo vertical de cristal */}
          <rect x="38" y="32" width="104" height="168" fill={`url(#glass-sheen-${uid})`} />
        </g>

        {/* Base espessa de cristal e contorno do copo */}
        <path
          d="M54 190 L126 190 L124 202 Q123 207 115 207 L65 207 Q57 207 56 202 Z"
          fill="rgba(255,255,255,0.14)"
          stroke="rgba(255,255,255,0.28)"
          strokeWidth="1.4"
        />
        <path
          d="M44 34 L136 34 L126 188 Q125 196 116 196 L64 196 Q55 196 54 188 Z"
          fill="none"
          stroke="rgba(255,255,255,0.34)"
          strokeWidth="2"
        />
        {/* Borda superior do copo */}
        <ellipse
          cx="90"
          cy="34"
          rx="46"
          ry="4.2"
          fill="rgba(255,255,255,0.06)"
          stroke="rgba(255,255,255,0.42)"
          strokeWidth="1.6"
        />
      </svg>
    </div>
  );
};


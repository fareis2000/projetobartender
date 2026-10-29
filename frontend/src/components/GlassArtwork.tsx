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
      : Math.max(0, Math.min(95, (totalMl / maxCapacityMl) * 92));

  // Coordenadas internas do copo Highball no viewBox 0 0 200 230
  const glassTopY = 44;
  const glassBottomY = 198;
  const usableHeight = glassBottomY - glassTopY; // 154
  const totalLiquidHeight = (computedFillPct / 100) * usableHeight;
  const liquidStartY = glassBottomY - totalLiquidHeight;

  const dimensions =
    size === 'sm'
      ? 'w-32 h-38'
      : size === 'lg'
        ? 'w-52 h-64'
        : 'w-40 h-48';

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
              height: h + 1,
            };
          })
      : [];

  const primaryGlow =
    layers.find((l) => l.ml > 0)?.color ?? pouringColor ?? '#fb923c';

  return (
    <div className={`relative flex items-center justify-center select-none ${dimensions}`}>
      {/* Aura solar colorida atrás do copo */}
      <div
        className="absolute inset-5 rounded-full blur-2xl opacity-25 transition-colors duration-500 pointer-events-none"
        style={{ backgroundColor: primaryGlow }}
      />

      <svg
        viewBox="0 0 200 230"
        className="w-full h-full drop-shadow-[0_14px_20px_rgba(120,58,20,0.18)]"
        aria-hidden="true"
      >
        <defs>
          <clipPath id={`glass-clip-${uid}`}>
            <path d="M54 42 L146 42 L136 194 Q135 202 126 202 L74 202 Q65 202 64 194 Z" />
          </clipPath>
          <linearGradient id={`glass-sheen-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
            <stop offset="24%" stopColor="#ffffff" stopOpacity="0.16" />
            <stop offset="76%" stopColor="#ffffff" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.42" />
          </linearGradient>
        </defs>

        {/* Rodela de Limão/Laranja encaixada na borda esquerda do copo */}
        <g transform="translate(52, 38) rotate(-18)">
          <circle cx="0" cy="0" r="21" fill="#16a34a" />
          <circle cx="0" cy="0" r="17.5" fill="#ecfccb" />
          {[0, 60, 120, 180, 240, 300].map((deg) => (
            <path
              key={deg}
              d="M2,2 L14,4 A14,14 0 0,1 4,14 Z"
              fill="#84cc16"
              transform={`rotate(${deg})`}
            />
          ))}
          <circle cx="0" cy="0" r="2.5" fill="#f7fee7" />
        </g>

        {/* Folhas frescas de Hortelã no topo direito */}
        <g transform="translate(124, 38)">
          <path
            d="M0,8 C-4,-8 10,-20 24,-16 C20,-2 10,8 0,8 Z"
            fill="#15803d"
          />
          <path
            d="M-4,10 C-16,-2 -12,-18 2,-20 C8,-8 4,4 -4,10 Z"
            fill="#22c55e"
          />
        </g>

        {/* Canudo listrado tropical (coral e creme) */}
        <path
          d="M114 196 L138 14 L152 10"
          fill="none"
          stroke="#fb7185"
          strokeWidth="6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M114 196 L138 14 L152 10"
          fill="none"
          stroke="#fff7ed"
          strokeWidth="6"
          strokeDasharray="6 7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Jato ativo quando uma bomba está dosando */}
        {pouringColor && (
          <line
            x1="100"
            y1="6"
            x2="100"
            y2={Math.max(50, liquidStartY + 6)}
            stroke={pouringColor}
            strokeWidth="6"
            strokeLinecap="round"
            className="stream-flow"
          />
        )}

        {/* Sombra elíptica na mesa */}
        <ellipse cx="100" cy="216" rx="44" ry="6" fill="rgba(120,62,24,0.14)" />

        {/* Interior recortado do copo */}
        <g clipPath={`url(#glass-clip-${uid})`}>
          {/* Fundo cristalino levemente azulado/quente */}
          <rect x="46" y="38" width="108" height="170" fill="rgba(255, 255, 255, 0.58)" />

          {/* Camadas líquidas das frutas/bombas */}
          {renderedSlices.map((slice) => (
            <rect
              key={slice.key}
              x="46"
              y={slice.y}
              width="108"
              height={slice.height}
              fill={slice.color}
              fillOpacity={0.88}
              style={{ transition: 'y 280ms ease, height 280ms ease' }}
            />
          ))}

          {/* Espuma / brilho no topo do líquido */}
          {totalLiquidHeight > 3 && (
            <ellipse
              cx="100"
              cy={liquidStartY}
              rx="45"
              ry="4.5"
              fill="#ffffff"
              fillOpacity="0.55"
            />
          )}

          {/* Cubos de gelo cristalinos */}
          {totalLiquidHeight > 28 && (
            <g>
              <rect
                x="70"
                y={Math.min(160, liquidStartY + 12)}
                width="23"
                height="23"
                rx="5.5"
                transform={`rotate(-14 81 ${Math.min(160, liquidStartY + 23)})`}
                fill="#ffffff"
                fillOpacity="0.5"
                stroke="#ffffff"
                strokeOpacity="0.75"
                strokeWidth="1.4"
              />
              <rect
                x="101"
                y={Math.min(168, liquidStartY + 26)}
                width="21"
                height="21"
                rx="5"
                transform={`rotate(15 111 ${Math.min(168, liquidStartY + 36)})`}
                fill="#ffffff"
                fillOpacity="0.45"
                stroke="#ffffff"
                strokeOpacity="0.7"
                strokeWidth="1.4"
              />
            </g>
          )}

          {/* Borbulhas de gás subindo */}
          {totalLiquidHeight > 22 && (
            <g fill="#ffffff" fillOpacity="0.75">
              <circle cx="80" cy="188" r="2.4" className="bubble-rise" style={{ animationDelay: '0s' }} />
              <circle cx="102" cy="192" r="2.0" className="bubble-rise" style={{ animationDelay: '0.7s' }} />
              <circle cx="118" cy="185" r="2.6" className="bubble-rise" style={{ animationDelay: '1.4s' }} />
              <circle cx="91" cy="180" r="1.8" className="bubble-rise" style={{ animationDelay: '1.9s' }} />
            </g>
          )}

          {/* Brilho vertical do vidro */}
          <rect x="48" y="40" width="104" height="166" fill={`url(#glass-sheen-${uid})`} />
        </g>

        {/* Gotículas geladas de condensação no vidro */}
        <circle cx="72" cy="112" r="1.8" fill="#ffffff" fillOpacity="0.8" />
        <circle cx="127" cy="138" r="1.5" fill="#ffffff" fillOpacity="0.8" />
        <circle cx="78" cy="154" r="1.4" fill="#ffffff" fillOpacity="0.75" />

        {/* Fundo espesso de vidro e contorno delicado */}
        <path
          d="M64 196 L136 196 L134 208 Q133 213 125 213 L75 213 Q67 213 66 208 Z"
          fill="rgba(255, 255, 255, 0.72)"
          stroke="rgba(120, 74, 42, 0.25)"
          strokeWidth="1.6"
        />
        <path
          d="M54 42 L146 42 L136 194 Q135 202 126 202 L74 202 Q65 202 64 194 Z"
          fill="none"
          stroke="rgba(120, 74, 42, 0.28)"
          strokeWidth="2.2"
        />
        <ellipse
          cx="100"
          cy="42"
          rx="46"
          ry="4.5"
          fill="rgba(255, 255, 255, 0.45)"
          stroke="rgba(120, 74, 42, 0.32)"
          strokeWidth="1.8"
        />
      </svg>
    </div>
  );
};

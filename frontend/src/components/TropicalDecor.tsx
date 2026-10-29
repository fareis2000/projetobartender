import React from 'react';

/**
 * Folhagens botânicas tropicais (Palmeiras + Costela-de-Adão) que emolduram a página
 * com movimento suave de brisa.
 */
export const TropicalBackdropLeaves: React.FC = () => {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden -z-10 select-none">
      {/* Sol dourado difuso no horizonte superior */}
      <div className="absolute -top-28 left-1/2 -translate-x-1/2 w-[560px] h-[300px] rounded-full bg-gradient-to-b from-[#ffd166]/45 via-[#ff9f43]/20 to-transparent blur-3xl" />

      {/* Folhas de Palmeira Esquerda */}
      <svg
        viewBox="0 0 340 420"
        className="palm-sway-left hidden sm:block absolute -top-8 -left-12 w-64 lg:w-80 text-[#156145] opacity-[0.16]"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M-10,10 C80,30 175,90 250,185 C185,150 115,135 50,145 C125,175 190,225 235,295 C165,255 95,235 25,240 C90,275 140,325 170,390 C105,345 45,318 -15,315 Z" />
        <path
          d="M-20,-10 C95,-5 205,35 295,115 C220,92 145,88 75,102 C160,122 230,160 285,220 C205,190 125,180 55,192 Z"
          opacity="0.7"
        />
      </svg>

      {/* Folhas de Palmeira & Hibisco Direita */}
      <svg
        viewBox="0 0 340 420"
        className="palm-sway-right hidden sm:block absolute -top-6 -right-12 w-64 lg:w-80 text-[#0f7656] opacity-[0.15]"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M350,10 C260,30 165,90 90,185 C155,150 225,135 290,145 C215,175 150,225 105,295 C175,255 245,235 315,240 C250,275 200,325 170,390 C235,345 295,318 355,315 Z" />
        <path
          d="M360,-10 C245,-5 135,35 45,115 C120,92 195,88 265,102 C180,122 110,160 55,220 C135,190 215,180 285,192 Z"
          opacity="0.65"
        />
      </svg>

      {/* Costela-de-Adão sutil no rodapé inferior */}
      <svg
        viewBox="0 0 260 260"
        className="hidden md:block absolute -bottom-14 -left-10 w-56 text-[#1b6b4c] opacity-[0.11]"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M20,250 C15,150 75,65 185,40 C155,85 135,115 110,130 C150,115 190,105 225,95 C195,145 155,185 110,200 C145,195 175,195 205,190 C160,235 90,255 20,250 Z" />
      </svg>
    </div>
  );
};

/**
 * Ilustração vetorial ensolarada para o Banner Principal (Pôr do sol + Rodela Cítrica + Folhas).
 */
export const TropicalHeroArt: React.FC = () => {
  return (
    <div className="relative w-full max-w-[290px] aspect-square mx-auto flex items-center justify-center select-none">
      <svg viewBox="0 0 280 280" className="w-full h-full drop-shadow-md" aria-hidden="true">
        <defs>
          <linearGradient id="sunset-disc" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fde047" />
            <stop offset="52%" stopColor="#fb923c" />
            <stop offset="100%" stopColor="#f43f5e" />
          </linearGradient>
          <linearGradient id="ocean-wave" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0d9488" />
            <stop offset="100%" stopColor="#0284c7" />
          </linearGradient>
        </defs>

        {/* Disco do Pôr do Sol Tropical */}
        <circle cx="145" cy="132" r="88" fill="url(#sunset-disc)" opacity="0.92" />

        {/* Listras horizontais de horizonte */}
        <rect x="48" y="168" width="194" height="5" rx="2.5" fill="#fff7ed" opacity="0.65" />
        <rect x="56" y="182" width="178" height="7" rx="3.5" fill="#fff7ed" opacity="0.8" />
        <rect x="70" y="198" width="150" height="9" rx="4.5" fill="#fff7ed" opacity="0.92" />

        {/* Ondas turquesa na base */}
        <path
          d="M42 195 Q95 178 145 195 T248 195 L235 224 Q145 242 55 224 Z"
          fill="url(#ocean-wave)"
          opacity="0.88"
        />

        {/* Folha Tropical Esquerda */}
        <path
          d="M28 188 C32 118 82 72 138 66 C104 96 86 122 82 146 C108 128 134 120 158 118 C122 152 78 178 28 188 Z"
          fill="#115e46"
        />
        <path
          d="M36 205 C56 155 96 130 142 126 C114 148 96 168 90 186 C112 176 132 172 150 172 C116 198 76 210 36 205 Z"
          fill="#10b981"
        />

        {/* Rodela de Laranja / Limão Tropical */}
        <g transform="translate(186, 178)">
          <circle cx="0" cy="0" r="42" fill="#f97316" />
          <circle cx="0" cy="0" r="36" fill="#fef3c7" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
            <path
              key={deg}
              d="M3,3 L29,9 A30,30 0 0,1 9,29 Z"
              fill="#fbbf24"
              transform={`rotate(${deg})`}
            />
          ))}
          <circle cx="0" cy="0" r="4.5" fill="#fffbeb" />
        </g>

        {/* Flor de Hibisco Coral */}
        <g transform="translate(82, 198)">
          {[0, 72, 144, 216, 288].map((deg) => (
            <ellipse
              key={deg}
              cx="0"
              cy="-14"
              rx="10"
              ry="15"
              fill="#f43f5e"
              transform={`rotate(${deg})`}
            />
          ))}
          <circle cx="0" cy="0" r="5" fill="#fde047" />
        </g>
      </svg>
    </div>
  );
};


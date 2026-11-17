/**
 * @file vite.config.ts
 * @description Configuração de build e servidor de desenvolvimento Vite 6 para o Bartender.OS v3.0.
 *
 * Papel na Arquitetura & Jornada Comercial SaaS:
 * - Garante um bundle web ultraleve (React 19 + Tailwind CSS v4 nativo via `@tailwindcss/vite`),
 *   essencial para carregamento instantâneo em redes móveis 4G/5G quando o cliente do bar escaneia
 *   o QR Code físico da máquina sem precisar baixar aplicativo nem conectar no Wi-Fi do local.
 * - Configura proxy reverso transparente (`/api` -> `http://localhost:8010`) com suporte a upgrade
 *   de protocolo WebSocket (`ws: true`), permitindo telemetria em tempo real de bombas, fila e
 *   progresso de dosagem durante o desenvolvimento local integrado ao backend FastAPI.
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/**
 * Exporta a configuração oficial do Vite para ambiente de desenvolvimento (porta 5174)
 * e geração do bundle estático de produção (`dist/`) servido diretamente pelo FastAPI.
 */
export default defineConfig({
  // Plugins oficiais: compilação JSX/Fast Refresh do React e motor CSS zero-runtime do Tailwind v4
  plugins: [react(), tailwindcss()],
  server: {
    // Porta dedicada para o frontend dev, evitando colisão com outras ferramentas locais
    port: 5174,
    proxy: {
      // Redireciona chamadas REST (/api/*) e conexões WebSocket (/api/ws/*) ao backend FastAPI
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

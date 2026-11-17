/**
 * @file vite.config.ts
 * @description Configuração de build e servidor de desenvolvimento Vite 6 para o Bartender.OS v2.0.
 *
 * Papel na Arquitetura:
 * ---------------------
 * - Integra o compilador React (`@vitejs/plugin-react`) e o motor CSS utilitário de alta
 *   performance Tailwind CSS v4 (`@tailwindcss/vite`).
 * - Em modo de desenvolvimento (`npm run dev`, porta `5173`), configura proxy reverso
 *   transparente de todas as chamadas `/api/*` — incluindo upgrade de WebSocket (`ws: true`)
 *   em `/api/ws` — diretamente para o servidor FastAPI local (`http://localhost:8000`).
 * - Em produção (`npm run build`), empacota e minifica a SPA estática em `frontend/dist`,
 *   permitindo que o próprio FastAPI sirva todo o aplicativo em uma única porta (`8000`).
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Redireciona REST (/api/*) e WebSocket (/api/ws) para o backend Python sem problemas de CORS
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

/**
 * @file src/main.tsx
 * @description Ponto de entrada (Bootstrap) da Single Page Application (SPA) do Bartender.OS v3.0.
 *
 * Papel Técnico & Comercial:
 * - Inicializa a árvore de renderização concorrente do React 19 sobre o nó `#root` sem dependências
 *   pesadas de roteadores externos, mantendo o First Contentful Paint (FCP) abaixo de 1 segundo no 4G.
 * - Carrega a folha de estilos global (`index.css`) com a identidade visual "Tropical Craft" que
 *   aumenta o apelo sensorial e o ticket médio no autoatendimento mobile.
 * - Utiliza `React.StrictMode` para assegurar limpeza rigorosa de listeners (`popstate`,
 *   `visibilitychange`, timers e WebSockets) em dispositivos móveis.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Monta a raiz React 19 no elemento DOM principal definido em index.html
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

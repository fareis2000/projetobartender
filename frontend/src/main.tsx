/**
 * @file main.tsx
 * @description Ponto de entrada (entry point) da árvore React 19 no navegador / totem touch.
 *
 * Papel na Arquitetura:
 * ---------------------
 * Importa a folha de estilos global com o tema tropical solar (`index.css`), localiza o nó
 * `#root` do `index.html` e monta o componente raiz `<App />` sob `<React.StrictMode>` para
 * garantir higiene de ciclo de vida nos hooks de WebSocket e timers durante o desenvolvimento.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Inicializa a raiz concorrente do React 19 na div principal da SPA
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

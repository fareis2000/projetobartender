/**
 * @file src/App.tsx
 * @description Roteador SPA leve baseado na History API nativa para as 3 personas do Bartender.OS v3.0.
 *
 * Papel na Arquitetura Multi-Tenant & Jornada Comercial:
 * - Elimina o peso de bibliotecas externas de roteamento para priorizar abertura instantânea via QR Code.
 * - Segrega de forma limpa as três jornadas de negócio do ecossistema SaaS em um único bundle:
 *   1. `/superadmin` -> Console Master da Plataforma (gestão B2B de bares clientes, máquinas vendidas e split Pix).
 *   2. `/painel` ou `/admin` -> ERP de bolso do Dono do Bar (estoque em R$/ml, engenharia de cardápio, bombas e Pix).
 *   3. `/m/:machineSlug` (e rota raiz `/`) -> Autoatendimento Mobile-First do consumidor final em frente à máquina.
 */
import React, { useEffect, useState } from 'react';
import { BarAdminPage } from './pages/BarAdminPage';
import { CustomerMachinePage } from './pages/CustomerMachinePage';
import { SuperAdminPage } from './pages/SuperAdminPage';

/**
 * Componente raiz que observa mudanças de URL (`popstate`) disparadas pelo navegador
 * ou pelo helper programático `navigateTo()` e decide qual experiência renderizar.
 */
export const App: React.FC = () => {
  /** Caminho reativo atual da janela (ex.: `/m/maq-01`, `/painel`, `/superadmin`). */
  const [pathname, setPathname] = useState<string>(() => window.location.pathname);

  /**
   * Registra listener global de navegação SPA sem recarregamento completo de página,
   * mantendo transições instantâneas entre cardápio público e painéis administrativos.
   */
  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // Jornada 1: Governança SaaS Multi-Bares (Operador/Fabricante da Plataforma)
  if (pathname.startsWith('/superadmin')) {
    return <SuperAdminPage />;
  }

  // Jornada 2: Painel Operacional e Financeiro do Estabelecimento (Dono/Gerente do Bar)
  if (pathname.startsWith('/painel') || pathname.startsWith('/admin')) {
    return <BarAdminPage />;
  }

  // Jornada 3: Autoatendimento Mobile do Consumidor Final via QR Code colado no gabinete
  // Rota de QR Code da Máquina: /m/:machineSlug
  const match = pathname.match(/^\/m\/([a-zA-Z0-9-]+)\/?$/);
  const machineSlug = match ? match[1].toLowerCase() : 'maq-01';

  return <CustomerMachinePage machineSlug={machineSlug} />;
};

export default App;

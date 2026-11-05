import React, { useEffect, useState } from 'react';
import { BarAdminPage } from './pages/BarAdminPage';
import { CustomerMachinePage } from './pages/CustomerMachinePage';
import { SuperAdminPage } from './pages/SuperAdminPage';

export const App: React.FC = () => {
  const [pathname, setPathname] = useState<string>(() => window.location.pathname);

  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  if (pathname.startsWith('/superadmin')) {
    return <SuperAdminPage />;
  }

  if (pathname.startsWith('/painel') || pathname.startsWith('/admin')) {
    return <BarAdminPage />;
  }

  // Rota de QR Code da Máquina: /m/:machineSlug
  const match = pathname.match(/^\/m\/([a-zA-Z0-9-]+)\/?$/);
  const machineSlug = match ? match[1].toLowerCase() : 'maq-01';

  return <CustomerMachinePage machineSlug={machineSlug} />;
};

export default App;

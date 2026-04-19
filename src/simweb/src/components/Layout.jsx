import { useState } from 'react';
import Sidebar from './Sidebar.jsx';

export default function Layout({ children, activePanel, onNavigate }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        activePanel={activePanel}
        onNavigate={onNavigate}
        onToggle={() => setSidebarOpen((o) => !o)}
      />
      <main className="main-content">
        {children}
      </main>
    </div>
  );
}

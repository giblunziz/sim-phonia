import { useState } from 'react';
import Layout from './components/Layout.jsx';
import StartScreen from './components/StartScreen.jsx';
import ChatScreen from './components/ChatScreen.jsx';
import ServerPanel from './components/admin/ServerPanel.jsx';
import MemoryPanel from './components/admin/MemoryPanel.jsx';
import StorageCharactersPanel from './components/storage/StorageCharactersPanel.jsx';
import StorageKnowledgePanel from './components/storage/StorageKnowledgePanel.jsx';
import StorageActivitiesPanel from './components/storage/StorageActivitiesPanel.jsx';
import StorageSchemasPanel from './components/storage/StorageSchemasPanel.jsx';
import StorageScenesPanel from './components/storage/StorageScenesPanel.jsx';
import StorageInstancesPanel from './components/storage/StorageInstancesPanel.jsx';

export default function App() {
  const [session, setSession]         = useState(null);
  const [activePanel, setActivePanel] = useState('chat');

  const handleNavigate = (panel) => {
    setActivePanel(panel);
  };

  const renderPanel = () => {
    switch (activePanel) {
      case 'chat':
        return session
          ? <ChatScreen session={session} onClose={() => setSession(null)} />
          : <StartScreen onStart={setSession} />;
      case 'server':
        return <ServerPanel />;
      case 'memory':
        return <MemoryPanel />;
      case 'storage-characters':
        return <StorageCharactersPanel />;
      case 'storage-knowledge':
        return <StorageKnowledgePanel />;
      case 'storage-activities':
        return <StorageActivitiesPanel />;
      case 'storage-schemas':
        return <StorageSchemasPanel />;
      case 'storage-scenes':
        return <StorageScenesPanel />;
      case 'storage-instances':
        return <StorageInstancesPanel />;
      default:
        return null;
    }
  };

  return (
    <Layout activePanel={activePanel} onNavigate={handleNavigate}>
      {renderPanel()}
    </Layout>
  );
}

import { useState } from 'react';
import Layout from './components/Layout.jsx';
import StartScreen from './components/StartScreen.jsx';
import ChatScreen from './components/ChatScreen.jsx';
import ServerPanel from './components/admin/ServerPanel.jsx';
import MemoryPanel from './components/admin/MemoryPanel.jsx';
import StorageCharactersPanel from './components/storage/StorageCharactersPanel.jsx';
import StorageKnowledgePanel from './components/storage/StorageKnowledgePanel.jsx';

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

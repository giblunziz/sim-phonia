import { useState } from 'react';
import StartScreen from './components/StartScreen.jsx';
import ChatScreen from './components/ChatScreen.jsx';

export default function App() {
  const [session, setSession] = useState(null);

  return (
    <div className="app">
      {session
        ? <ChatScreen session={session} onClose={() => setSession(null)} />
        : <StartScreen onStart={setSession} />
      }
    </div>
  );
}

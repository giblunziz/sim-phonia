import { useState, useEffect, useRef } from 'react';
import { chatReply, chatStop, openEventStream } from '../api/simphonia.js';

function Message({ speaker, text, isFrom }) {
  return (
    <div className={`message ${isFrom ? 'message-from' : 'message-to'}`}>
      <span className="message-speaker">{speaker}</span>
      <p className="message-text">{text}</p>
    </div>
  );
}

export default function ChatScreen({ session, onClose }) {
  const { session_id, fromChar, toChar, say, reply, human } = session;

  const [messages, setMessages] = useState([
    { id: 0, speaker: fromChar, text: say, isFrom: true },
    { id: 1, speaker: toChar, text: reply, isFrom: false },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [closed, setClosed] = useState(false);
  const bottomRef = useRef(null);
  const idRef = useRef(2);

  const addMsg = (speaker, text, isFrom) => {
    setMessages((prev) => [
      ...prev,
      { id: idRef.current++, speaker, text, isFrom },
    ]);
  };

  // SSE pour le mode autonome (human=false)
  useEffect(() => {
    if (human) return;
    const es = openEventStream(session_id);
    es.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.type === 'said') {
        addMsg(event.from_char, event.content, event.from_char === fromChar);
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [session_id, human, fromChar]);

  // Scroll automatique vers le bas
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleReply = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setError(null);
    setLoading(true);
    addMsg(fromChar, text, true);
    setInput('');
    try {
      const result = await chatReply(session_id, fromChar, text, human);
      addMsg(toChar, result.reply, false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      await chatStop(session_id);
    } catch {
      // best-effort
    }
    setClosed(true);
    onClose();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleReply(e);
    }
  };

  return (
    <div className="chat-screen">
      <header className="chat-header">
        <div className="chat-title">
          <span className="char-from">{fromChar}</span>
          <span className="arrow">{human ? '(humain)' : '⇌'}</span>
          <span className="char-to">{toChar}</span>
        </div>
        <div className="chat-meta">
          <span className="session-id">{session_id}</span>
          <button className="btn-stop" onClick={handleStop} disabled={closed}>
            Fermer
          </button>
        </div>
      </header>

      <div className="messages-area">
        {messages.map((m) => (
          <Message key={m.id} speaker={m.speaker} text={m.text} isFrom={m.isFrom} />
        ))}
        {loading && (
          <div className="typing-indicator">
            <span>{toChar} réfléchit</span>
            <span className="dots"><span>.</span><span>.</span><span>.</span></span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <p className="error error-inline">{error}</p>}

      {human && !closed && (
        <form className="reply-form" onSubmit={handleReply}>
          <textarea
            className="reply-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`${fromChar} répond… (Entrée pour envoyer, Maj+Entrée pour sauter une ligne)`}
            rows={3}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-primary btn-send"
            disabled={loading || !input.trim()}
          >
            Envoyer
          </button>
        </form>
      )}

      {!human && !closed && (
        <div className="autonomous-notice">
          Dialogue autonome en cours — les personnages échangent librement.
        </div>
      )}
    </div>
  );
}

import { useState, useEffect } from 'react';
import { listCharacters, chatStart } from '../api/simphonia.js';

export default function StartScreen({ onStart }) {
  const [characters, setCharacters] = useState([]);
  const [fromChar, setFromChar] = useState('');
  const [toChar, setToChar] = useState('');
  const [say, setSay] = useState('');
  const [human, setHuman] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listCharacters()
      .then((chars) => {
        setCharacters(chars ?? []);
        if (chars?.length > 0) setFromChar(chars[0]);
        if (chars?.length > 1) setToChar(chars[1]);
      })
      .catch(() => setError('Impossible de charger les personnages. Le serveur est-il démarré ?'));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!say.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const result = await chatStart(fromChar, toChar, say.trim(), human);
      onStart({ ...result, fromChar, toChar, say: say.trim(), human });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="start-screen">
      <header className="start-header">
        <div className="logo">sim-phonia</div>
        <p className="subtitle">Nouveau dialogue</p>
      </header>

      <form className="start-form" onSubmit={handleSubmit}>
        <div className="field-row">
          <div className="field">
            <label htmlFor="from-char">De</label>
            <select
              id="from-char"
              value={fromChar}
              onChange={(e) => setFromChar(e.target.value)}
              disabled={loading}
            >
              {characters.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="to-char">À</label>
            <select
              id="to-char"
              value={toChar}
              onChange={(e) => setToChar(e.target.value)}
              disabled={loading}
            >
              {characters.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label htmlFor="say">Premier message</label>
          <textarea
            id="say"
            value={say}
            onChange={(e) => setSay(e.target.value)}
            placeholder="Que dit le personnage pour ouvrir le dialogue ?"
            rows={3}
            required
            disabled={loading}
          />
        </div>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={human}
            onChange={(e) => setHuman(e.target.checked)}
            disabled={loading}
          />
          <span>Mode humain</span>
          <span className="hint">
            {human
              ? 'Vous incarnez « ' + (fromChar || '…') + ' » — vous répondrez manuellement.'
              : 'Dialogue autonome entre LLMs.'}
          </span>
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="btn-primary" disabled={loading || !fromChar || !toChar}>
          {loading ? 'Démarrage…' : 'Démarrer le dialogue'}
        </button>
      </form>
    </div>
  );
}

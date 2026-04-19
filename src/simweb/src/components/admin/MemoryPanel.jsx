import { useState, useEffect } from 'react';
import { listCharacters, memoryRecall, memoryResync } from '../../api/simphonia.js';

export default function MemoryPanel() {
  const [chars, setChars]         = useState([]);
  const [fromChar, setFromChar]   = useState('');
  const [about, setAbout]         = useState('');
  const [context, setContext]     = useState('');
  const [results, setResults]     = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [resyncing, setResyncing] = useState(false);
  const [resyncMsg, setResyncMsg] = useState(null);

  useEffect(() => {
    listCharacters()
      .then((list) => {
        const c = list ?? [];
        setChars(c);
        if (c.length > 0) setFromChar(c[0]);
      })
      .catch(() => {});
  }, []);

  const handleResync = async () => {
    if (!confirm('Reconstruire l\'index ChromaDB depuis MongoDB ? L\'opération peut prendre plusieurs minutes.')) return;
    setResyncing(true);
    setResyncMsg(null);
    try {
      const res = await memoryResync();
      setResyncMsg(`✓ ${res.reindexed} document(s) réindexé(s).`);
    } catch (e) {
      setResyncMsg(`✗ Erreur : ${e.message}`);
    } finally {
      setResyncing(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!context.trim()) return;
    setError(null);
    setLoading(true);
    try {
      setResults(await memoryRecall(fromChar, context.trim(), about || undefined));
    } catch (err) {
      setError(err.message);
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  const relevance = (distance) => Math.round((1 - distance) * 100);

  return (
    <div className="admin-panel">
      <h2>Mémoire</h2>

      <section className="panel-section">
        <h3>Index ChromaDB</h3>
        <div className="panel-actions">
          <button className="btn-secondary" onClick={handleResync} disabled={resyncing}>
            {resyncing ? 'Resync en cours…' : '↺ Resync Chroma'}
          </button>
          {resyncMsg && <span className={`reset-msg ${resyncMsg.startsWith('✗') ? 'error-inline' : ''}`}>{resyncMsg}</span>}
        </div>
      </section>

      <section className="panel-section">
        <h3>Requête recall</h3>
        <form className="memory-form" onSubmit={handleSubmit}>
          <div className="field-row">
            <div className="field">
              <label htmlFor="mem-from">Personnage</label>
              <select
                id="mem-from"
                value={fromChar}
                onChange={(e) => setFromChar(e.target.value)}
                disabled={loading}
              >
                {chars.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div className="field">
              <label htmlFor="mem-about">À propos de <span className="label-opt">(optionnel)</span></label>
              <select
                id="mem-about"
                value={about}
                onChange={(e) => setAbout(e.target.value)}
                disabled={loading}
              >
                <option value="">— tous —</option>
                {chars.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="mem-context">Contexte</label>
            <textarea
              id="mem-context"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Décrivez la situation pour laquelle vous cherchez des souvenirs…"
              rows={3}
              required
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !fromChar || !context.trim()}
            style={{ alignSelf: 'flex-start' }}
          >
            {loading ? 'Recherche…' : 'Recall'}
          </button>
        </form>

        {error && <p className="error">{error}</p>}
      </section>

      {results !== null && (
        <section className="panel-section">
          <h3>Résultats ({results.length})</h3>
          {results.length === 0
            ? <p className="empty-note">Aucun souvenir pertinent trouvé.</p>
            : (
              <div className="memory-results">
                {results.map((m, i) => (
                  <div key={i} className="memory-entry">
                    <div className="memory-entry-meta">
                      {m.about    && <span className="memory-tag about">{m.about}</span>}
                      {m.category && <span className="memory-tag category">{m.category}</span>}
                      {m.scene    && <span className="memory-tag">{m.scene}</span>}
                      <span className="memory-distance">{relevance(m.distance)}% pertinent</span>
                    </div>
                    <p className="memory-text">{m.value}</p>
                  </div>
                ))}
              </div>
            )
          }
        </section>
      )}
    </div>
  );
}

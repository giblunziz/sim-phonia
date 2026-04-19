import { useState, useEffect } from 'react';
import { listCharacters, getCharacter, resetCharacters } from '../../api/simphonia.js';

export default function CharactersPanel() {
  const [chars, setChars]         = useState([]);
  const [selected, setSelected]   = useState(null);
  const [detail, setDetail]       = useState(null);
  const [resetMsg, setResetMsg]   = useState(null);
  const [busy, setBusy]           = useState({});
  const [error, setError]         = useState(null);

  useEffect(() => {
    loadChars();
  }, []);

  const loadChars = async () => {
    try {
      setChars(await listCharacters() ?? []);
    } catch {
      setError('Impossible de charger les personnages.');
    }
  };

  const handleSelect = async (name) => {
    if (selected === name) {
      setSelected(null);
      setDetail(null);
      return;
    }
    setSelected(name);
    setDetail(null);
    setBusy((b) => ({ ...b, detail: true }));
    try {
      setDetail(await getCharacter(name));
    } catch {
      setDetail(null);
    } finally {
      setBusy((b) => ({ ...b, detail: false }));
    }
  };

  const handleReset = async () => {
    setBusy((b) => ({ ...b, reset: true }));
    setResetMsg(null);
    try {
      const count = await resetCharacters();
      setResetMsg(`${count} fiche(s) rechargée(s).`);
      await loadChars();
      setSelected(null);
      setDetail(null);
    } catch (e) {
      setResetMsg(`Erreur : ${e.message}`);
    } finally {
      setBusy((b) => ({ ...b, reset: false }));
    }
  };

  return (
    <div className="admin-panel">
      <h2>Personnages</h2>

      {error && <p className="error">{error}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Fiches ({chars.length})</h3>
          <button className="btn-secondary" onClick={handleReset} disabled={busy.reset}>
            {busy.reset ? '…' : 'Recharger'}
          </button>
          {resetMsg && <span className="reset-msg">{resetMsg}</span>}
        </div>

        <div className="characters-grid">
          {chars.map((name) => (
            <button
              key={name}
              className={`character-chip ${selected === name ? 'selected' : ''}`}
              onClick={() => handleSelect(name)}
            >
              {name}
            </button>
          ))}
        </div>
      </section>

      {selected && (
        <section className="panel-section">
          <h3>{selected}</h3>
          {busy.detail
            ? <p className="empty-note">Chargement…</p>
            : detail
              ? (
                <div className="character-detail">
                  <pre>{JSON.stringify(detail, null, 2)}</pre>
                </div>
              )
              : <p className="empty-note">Fiche introuvable.</p>
          }
        </section>
      )}
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import {
  storageListCharacters,
  storageGetCharacter,
  storagePutCharacter,
  storageDeleteCharacter,
  resetCharacters,
} from '../../api/simphonia.js';

const EMPTY_SCHEMA = {
  _id: '',
  code: '',
  full_name: '',
  given_name: '',
  family_name: '',
  age: null,
  gender: '',
  orientation: { label: '', details: [] },
  relationship: { status: '', partner: '', duration: '', details: [] },
  background: {
    job: { title: '', sector: '', location: '', details: '' },
    education: '',
    family: { parents: '', siblings: '', home: '' },
    marking_events: [],
  },
  psychology: {
    insight: {
      adapted: { colors: '', details: '' },
      real: { colors: '', details: '' },
      gap: [],
    },
    transactional: { dominant: '', adult: '', parent: '', child: '' },
    values: [],
    defense: '',
    comfort: [],
    threat: [],
  },
  flaws: [],
  social: [],
  likes: [],
  game: { phobia: [], secret: [], prior_knowledge: [] },
  memory: { slots: 5, style: '' },
  appearance: { height: '', hair: '', eyes: '', build: '', facial_hair: '', style: '' },
  events: [],
};

export default function StorageCharactersPanel() {
  const [chars, setChars]         = useState([]);
  const [selected, setSelected]   = useState(null);
  const [detail, setDetail]       = useState(null);
  const [editJson, setEditJson]   = useState('');
  const [editing, setEditing]     = useState(false);
  const [jsonError, setJsonError] = useState(null);
  const [busy, setBusy]           = useState({});
  const [msg, setMsg]             = useState(null);
  const [error, setError]         = useState(null);

  const load = useCallback(async () => {
    try { setChars(await storageListCharacters() ?? []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSelect = async (id) => {
    if (selected === id) { setSelected(null); setDetail(null); return; }
    setSelected(id);
    setDetail(null);
    setEditing(false);
    setBusy((b) => ({ ...b, detail: true }));
    try { setDetail(await storageGetCharacter(id)); }
    finally { setBusy((b) => ({ ...b, detail: false })); }
  };

  const handleEdit = () => {
    setEditJson(JSON.stringify(detail, null, 2));
    setJsonError(null);
    setEditing(true);
  };

  const handleSave = async () => {
    let parsed;
    try { parsed = JSON.parse(editJson); }
    catch { setJsonError('JSON invalide'); return; }
    if (!parsed._id) { setJsonError('`_id` obligatoire'); return; }
    setBusy((b) => ({ ...b, save: true }));
    try {
      const updated = await storagePutCharacter(parsed);
      setDetail(updated);
      setEditing(false);
      setMsg('Fiche sauvegardée.');
      await resetCharacters();
      await load();
    } catch (e) {
      setJsonError(e.message);
    } finally {
      setBusy((b) => ({ ...b, save: false }));
    }
  };

  const handleCreate = () => {
    setSelected(null);
    setDetail(null);
    setEditJson(JSON.stringify(EMPTY_SCHEMA, null, 2));
    setJsonError(null);
    setEditing(true);
  };

  const handleDelete = async (id) => {
    if (!confirm(`Supprimer « ${id} » ?`)) return;
    setBusy((b) => ({ ...b, delete: true }));
    try {
      await storageDeleteCharacter(id);
      setSelected(null);
      setDetail(null);
      setMsg(`« ${id} » supprimé.`);
      await resetCharacters();
      await load();
    } finally {
      setBusy((b) => ({ ...b, delete: false }));
    }
  };

  return (
    <div className="admin-panel">
      <h2>Storage — Personnages</h2>

      {error && <p className="error">{error}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Fiches ({chars.length})</h3>
          <button className="btn-secondary" onClick={handleCreate}>+ Nouveau</button>
          <button className="btn-secondary" onClick={load}>↻ Actualiser</button>
          {msg && <span className="reset-msg">{msg}</span>}
        </div>
        <div className="characters-grid">
          {chars.map((c) => (
            <button
              key={c._id}
              className={`character-chip ${selected === c._id ? 'selected' : ''}`}
              onClick={() => handleSelect(c._id)}
            >
              {c._id}
            </button>
          ))}
        </div>
      </section>

      {(detail !== null || editing) && (
        <section className="panel-section">
          <div className="panel-actions">
            <h3>{selected ?? 'Nouvelle fiche'}</h3>
            {!editing && detail?._id && (
              <>
                <button className="btn-secondary" onClick={handleEdit}>Éditer</button>
                <button className="btn-secondary btn-danger" onClick={() => handleDelete(selected)} disabled={busy.delete}>
                  Supprimer
                </button>
              </>
            )}
            {editing && (
              <>
                <button className="btn-primary" onClick={handleSave} disabled={busy.save}
                  style={{ padding: '0.4rem 0.9rem', fontSize: '0.83rem' }}>
                  {busy.save ? '…' : 'Sauvegarder'}
                </button>
                <button className="btn-secondary" onClick={() => { setEditing(false); if (!selected) setDetail(null); }}>
                  Annuler
                </button>
              </>
            )}
          </div>

          {editing ? (
            <>
              <textarea
                className="json-editor"
                value={editJson}
                onChange={(e) => { setEditJson(e.target.value); setJsonError(null); }}
                rows={28}
                spellCheck={false}
              />
              {jsonError && <p className="error">{jsonError}</p>}
            </>
          ) : detail ? (
            <div className="character-detail">
              <pre>{JSON.stringify(detail, null, 2)}</pre>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}

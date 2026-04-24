import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  shadowEntriesList,
  shadowEntryGet,
  shadowEntryUpdate,
  shadowEntryDelete,
  shadowChromaResync,
  listCharacters,
} from '../../api/simphonia.js';
import JsonEditor from '../common/JsonEditor.jsx';

const PAGE_SIZE = 50;
const BUS_ORIGINS = ['activity', 'chat'];  // peuplé hardcodé V1 (cf. doc § UI)

export default function ShadowDataPanel() {
  // ── filtres ──────────────────────────────────────────────────
  const [busOrigin, setBusOrigin] = useState('');
  const [fromChar, setFromChar]   = useState('');
  const [characters, setCharacters] = useState([]);

  // ── pagination + données ─────────────────────────────────────
  const [entries, setEntries] = useState([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(0);

  // ── modale lecture / édition ─────────────────────────────────
  const [viewing, setViewing]     = useState(null);   // dict payload formaté
  const [editing, setEditing]     = useState(null);   // { entry_id, doc }
  const [editedDoc, setEditedDoc] = useState(null);

  // ── état UI ──────────────────────────────────────────────────
  const [busy, setBusy]   = useState({});
  const [error, setError] = useState(null);
  const [msg, setMsg]     = useState(null);

  const filter = useMemo(() => {
    const f = {};
    if (busOrigin) f.bus_origin = busOrigin;
    if (fromChar)  f.from       = fromChar;
    return f;
  }, [busOrigin, fromChar]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ── chargement ───────────────────────────────────────────────
  const load = useCallback(async () => {
    setBusy((b) => ({ ...b, list: true }));
    setError(null);
    try {
      const result = await shadowEntriesList(filter, page * PAGE_SIZE, PAGE_SIZE);
      setEntries(result?.entries ?? []);
      setTotal(result?.total ?? 0);
    } catch (e) {
      setError(`entries.list : ${e.message}`);
    } finally {
      setBusy((b) => ({ ...b, list: false }));
    }
  }, [filter, page]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    listCharacters()
      .then((list) => setCharacters(Array.isArray(list) ? list : []))
      .catch((e) => console.error('character/list KO :', e));
  }, []);

  // Reset page si on change un filtre
  useEffect(() => { setPage(0); }, [busOrigin, fromChar]);

  // ── actions par ligne ────────────────────────────────────────

  const handleView = async (entry_id) => {
    setError(null);
    try {
      const entry = await shadowEntryGet(entry_id);
      if (!entry) { setError(`Entry ${entry_id} introuvable`); return; }
      setViewing(entry.payload ?? {});
    } catch (e) { setError(`entries.get : ${e.message}`); }
  };

  const handleEdit = async (entry_id) => {
    setError(null);
    try {
      const entry = await shadowEntryGet(entry_id);
      if (!entry) { setError(`Entry ${entry_id} introuvable`); return; }
      setEditing({ entry_id, original: entry });
      setEditedDoc(entry);
    } catch (e) { setError(`entries.get : ${e.message}`); }
  };

  const handleEditSave = async () => {
    if (!editing || !editedDoc) return;
    setBusy((b) => ({ ...b, save: true }));
    setError(null);
    try {
      await shadowEntryUpdate(editing.entry_id, editedDoc);
      setMsg(`Entry ${editing.entry_id} mise à jour. Pense à resync Chroma si l'embedding doit suivre.`);
      setEditing(null);
      setEditedDoc(null);
      await load();
    } catch (e) { setError(`entries.update : ${e.message}`); }
    finally { setBusy((b) => ({ ...b, save: false })); }
  };

  const handleDelete = async (entry_id) => {
    if (!window.confirm(`Supprimer l'entrée ${entry_id} (Mongo + Chroma) ?`)) return;
    setBusy((b) => ({ ...b, [entry_id]: true }));
    setError(null);
    try {
      const ok = await shadowEntryDelete(entry_id);
      if (ok) setMsg(`Entry ${entry_id} supprimée.`);
      else    setError(`Entry ${entry_id} introuvable.`);
      await load();
    } catch (e) { setError(`entries.delete : ${e.message}`); }
    finally { setBusy((b) => ({ ...b, [entry_id]: false })); }
  };

  const handleResync = async () => {
    if (!window.confirm('Reconstruire entièrement l\'index ChromaDB depuis MongoDB ?\nCette opération drop la collection Chroma puis re-pousse tout — peut prendre du temps si beaucoup d\'entrées.')) return;
    setBusy((b) => ({ ...b, resync: true }));
    setError(null);
    setMsg(null);
    try {
      const indexed = await shadowChromaResync();
      setMsg(`Resync terminé — ${indexed} entrée(s) réindexée(s).`);
    } catch (e) { setError(`chroma.resync : ${e.message}`); }
    finally { setBusy((b) => ({ ...b, resync: false })); }
  };

  // ── rendu ────────────────────────────────────────────────────

  return (
    <div className="shadow-panel">
      <header className="shadow-header">
        <h2>Tobias — Subconscient</h2>
        <div className="shadow-header-actions">
          <button
            className="btn-secondary"
            onClick={() => load()}
            disabled={busy.list}
          >↻ Refresh</button>
          <button
            className="btn-secondary"
            onClick={handleResync}
            disabled={busy.resync}
          >{busy.resync ? '⌛ Resync…' : '↺ Resync Chroma'}</button>
        </div>
      </header>

      {error && <div className="alert-error">{error}</div>}
      {msg   && <div className="alert-info">{msg}</div>}

      <section className="shadow-filters">
        <label>
          Bus origin :
          <select value={busOrigin} onChange={(e) => setBusOrigin(e.target.value)}>
            <option value="">— tous —</option>
            {BUS_ORIGINS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>

        <label>
          From char :
          <select value={fromChar} onChange={(e) => setFromChar(e.target.value)}>
            <option value="">— tous —</option>
            {characters.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </section>

      <section className="shadow-list">
        <div className="shadow-list-meta">
          {total} entrée(s) {filter && Object.keys(filter).length ? `(filtrées)` : ''}
        </div>

        <table className="shadow-table">
          <thead>
            <tr>
              <th>from</th>
              <th>bus_origin</th>
              <th>ts</th>
              <th>preview</th>
              <th>actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e._id}
                  className="shadow-row"
                  onClick={() => handleView(e._id)}
                  title="Cliquer pour voir le payload">
                <td>{e.from}</td>
                <td>{e.bus_origin}</td>
                <td>{formatTs(e.ts)}</td>
                <td className="shadow-preview" title={previewFull(e.payload)}>
                  {previewTrunc(e.payload, 250)}
                </td>
                <td className="shadow-actions" onClick={(ev) => ev.stopPropagation()}>
                  <button className="btn-icon" title="Éditer" onClick={() => handleEdit(e._id)}>✎</button>
                  <button className="btn-icon btn-danger" title="Supprimer"
                          onClick={() => handleDelete(e._id)}
                          disabled={busy[e._id]}>✕</button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && !busy.list && (
              <tr><td colSpan={5} className="shadow-empty">Aucune entrée</td></tr>
            )}
          </tbody>
        </table>

        <div className="shadow-pagination">
          <button
            className="btn-secondary"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >◀ Précédente</button>
          <span>Page {page + 1} / {totalPages}</span>
          <button
            className="btn-secondary"
            disabled={page + 1 >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >Suivante ▶</button>
        </div>
      </section>

      {viewing != null && (
        <div className="modal-backdrop" onClick={() => setViewing(null)}>
          <div className="modal" onClick={(ev) => ev.stopPropagation()}>
            <header className="modal-header">
              <h3>Payload</h3>
              <button className="btn-icon" onClick={() => setViewing(null)}>✕</button>
            </header>
            <pre className="modal-body json-pre">
              {JSON.stringify(viewing, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {editing && (
        <div className="modal-backdrop">
          <div className="modal modal-wide">
            <header className="modal-header">
              <h3>Édition — {editing.entry_id}</h3>
              <button className="btn-icon" onClick={() => { setEditing(null); setEditedDoc(null); }}>✕</button>
            </header>
            <div className="modal-body">
              <JsonEditor value={editing.original} onChange={setEditedDoc} rows={20} />
              <p className="modal-warning">
                ⚠ Le resync Chroma n'est pas automatique. Clique sur « Resync Chroma » après si tu veux que l'index suive.
              </p>
            </div>
            <footer className="modal-footer">
              <button className="btn-secondary"
                      onClick={() => { setEditing(null); setEditedDoc(null); }}>
                Annuler
              </button>
              <button className="btn-primary"
                      disabled={busy.save || !editedDoc}
                      onClick={handleEditSave}>
                {busy.save ? '⌛' : 'Sauver'}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function formatTs(ts) {
  if (!ts) return '';
  // ts est ISO-8601 côté serveur (cf. _serialize)
  try {
    const d = new Date(ts);
    return d.toLocaleString('fr-FR', {
      year: '2-digit', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return ts; }
}

function previewFull(payload) {
  if (payload == null) return '';
  try { return JSON.stringify(payload); }
  catch { return String(payload); }
}

function previewTrunc(payload, max) {
  const full = previewFull(payload);
  return full.length > max ? full.slice(0, max) + '…' : full;
}

import { useState, useEffect, useCallback } from 'react';
import { schemaList, schemaPut, schemaDelete } from '../../api/simphonia.js';
import JsonEditor from '../common/JsonEditor.jsx';

const EMPTY_FORM = { slug: '', prompt: '', payload: {} };

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleDateString('fr-FR', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return ts; }
}

function excerpt(text, n = 80) {
  return text?.length > n ? text.slice(0, n) + '…' : (text ?? '');
}

export default function StorageSchemasPanel() {
  const [entries, setEntries]   = useState([]);
  const [editId, setEditId]     = useState(null);
  const [form, setForm]         = useState(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy]         = useState({});
  const [msg, setMsg]           = useState(null);
  const [error, setError]       = useState(null);

  const load = useCallback(async () => {
    try { setEntries(await schemaList() ?? []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setError(null);
    setShowForm(true);
  };

  const openEdit = (entry) => {
    setForm({
      slug:    entry._id,
      prompt:  entry.prompt ?? '',
      payload: entry.payload ?? {},
    });
    setEditId(entry._id);
    setError(null);
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const id = editId ?? form.slug.trim();
    if (!id) { setError('Le slug est obligatoire.'); return; }
    setBusy((b) => ({ ...b, save: true }));
    setError(null);
    try {
      await schemaPut(id, { prompt: form.prompt, payload: form.payload });
      setMsg(editId ? 'Schéma mis à jour.' : 'Schéma créé.');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, save: false }));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm(`Supprimer le schéma "${id}" ?`)) return;
    await schemaDelete(id);
    setMsg('Schéma supprimé.');
    await load();
  };

  return (
    <div className="admin-panel">
      <h2>Storage — Schémas</h2>

      {error && <p className="error">{error}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Référentiel ({entries.length})</h3>
          <button className="btn-secondary" onClick={openCreate}>+ Nouveau</button>
          <button className="btn-secondary" onClick={load}>↻ Actualiser</button>
          {msg && <span className="reset-msg">{msg}</span>}
        </div>
      </section>

      {showForm && (
        <section className="panel-section">
          <h3>{editId ? `Éditer — ${editId}` : 'Nouveau schéma'}</h3>
          <form onSubmit={handleSubmit}>

            {!editId && (
              <div className="field">
                <label htmlFor="sch-slug">Slug <span className="label-opt">(identifiant unique)</span></label>
                <input id="sch-slug" type="text" placeholder="ex: activity_response_schema"
                  value={form.slug}
                  onChange={(e) => setForm((p) => ({ ...p, slug: e.target.value }))}
                  disabled={busy.save}
                  style={{ width: '100%' }}
                />
              </div>
            )}

            <div className="field">
              <label htmlFor="sch-prompt">Prompt</label>
              <textarea id="sch-prompt" rows={3}
                value={form.prompt}
                onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
                disabled={busy.save}
                placeholder="Instruction injectée dans le contexte avec ce schéma…"
              />
            </div>

            <div className="field">
              <label>Payload <span className="label-opt">(schéma JSON)</span></label>
              <JsonEditor
                value={form.payload}
                onChange={(v) => setForm((p) => ({ ...p, payload: v }))}
                disabled={busy.save}
                rows={18}
              />
            </div>

            <div className="panel-actions" style={{ marginTop: '0.75rem' }}>
              <button type="submit" className="btn-primary"
                style={{ padding: '0.45rem 1rem', fontSize: '0.83rem' }} disabled={busy.save}>
                {busy.save ? '…' : editId ? 'Mettre à jour' : 'Créer'}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
            </div>
          </form>
        </section>
      )}

      <section className="panel-section">
        {entries.length === 0
          ? <p className="empty-note">Aucun schéma.</p>
          : (
            <div className="knowledge-grid" style={{ gridTemplateColumns: '1.2fr 2.5fr 1fr auto' }}>
              <div className="knowledge-header">
                <span>Slug</span><span>Prompt</span><span>Modifié le</span><span></span>
              </div>
              {entries.map((e) => (
                <div key={e._id} className="knowledge-row">
                  <span className="kc-tag">{e._id}</span>
                  <span className="kc-dim">{excerpt(e.prompt)}</span>
                  <span className="kc-dim">{formatTs(e.ts_updated)}</span>
                  <span className="kc-actions">
                    <button className="btn-row" onClick={() => openEdit(e)}>✎</button>
                    <button className="btn-row btn-row-danger" onClick={() => handleDelete(e._id)}>✕</button>
                  </span>
                </div>
              ))}
            </div>
          )
        }
      </section>
    </div>
  );
}

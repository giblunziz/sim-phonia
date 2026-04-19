import { useState, useEffect, useCallback } from 'react';
import {
  listCharacters,
  storageListKnowledge,
  storagePushKnowledge,
  storageUpdateKnowledge,
  storageDeleteKnowledge,
} from '../../api/simphonia.js';

const KNOWN_CATEGORIES = ['perceived_traits', 'assumptions', 'approach', 'watchouts'];
const EMPTY_FORM = { from: '', about: '', activity: '', category: '', scene: '', value: '' };

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

function CategoryCombo({ value, onChange, disabled }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem' }}>
      <select
        value={KNOWN_CATEGORIES.includes(value) ? value : ''}
        onChange={(e) => e.target.value && onChange({ target: { value: e.target.value } })}
        disabled={disabled}
        style={{ flex: '0 0 auto', width: '180px' }}
      >
        <option value="">— raccourci —</option>
        {KNOWN_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder="Catégorie libre"
        disabled={disabled}
        style={{ flex: 1 }}
      />
    </div>
  );
}

export default function StorageKnowledgePanel() {
  const [chars, setChars]       = useState([]);
  const [entries, setEntries]   = useState([]);
  const [form, setForm]         = useState(EMPTY_FORM);
  const [editId, setEditId]     = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [filters, setFilters]   = useState({ from: '', about: '', category: '' });
  const [busy, setBusy]         = useState({});
  const [msg, setMsg]           = useState(null);
  const [error, setError]       = useState(null);

  const load = useCallback(async () => {
    try { setEntries(await storageListKnowledge() ?? []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => {
    load();
    listCharacters().then((list) => setChars(list ?? [])).catch(() => {});
  }, [load]);

  const filtered = entries.filter((e) =>
    (!filters.from     || e.from === filters.from) &&
    (!filters.about    || e.about === filters.about) &&
    (!filters.category || e.category?.includes(filters.category))
  );

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setShowForm(true);
    setError(null);
  };

  const openEdit = (entry) => {
    setForm({
      from: entry.from ?? '', about: entry.about ?? '',
      activity: entry.activity ?? '', category: entry.category ?? '',
      scene: entry.scene ?? '', value: entry.value ?? '',
    });
    setEditId(entry._id);
    setShowForm(true);
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.value.trim()) return;
    setBusy((b) => ({ ...b, save: true }));
    setError(null);
    try {
      if (editId) {
        await storageUpdateKnowledge(editId, form);
        setMsg('Entrée mise à jour.');
      } else {
        await storagePushKnowledge(form);
        setMsg('Entrée ajoutée.');
      }
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, save: false }));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Supprimer cette entrée ?')) return;
    await storageDeleteKnowledge(id);
    setMsg('Entrée supprimée.');
    await load();
  };

  const field = (key) => ({
    value: form[key],
    onChange: (e) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  return (
    <div className="admin-panel">
      <h2>Storage — Knowledge</h2>

      {error && <p className="error">{error}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Entrées ({filtered.length} / {entries.length})</h3>
          <button className="btn-secondary" onClick={openCreate}>+ Nouveau</button>
          <button className="btn-secondary" onClick={load}>↻ Actualiser</button>
          {msg && <span className="reset-msg">{msg}</span>}
        </div>

        <div className="knowledge-filters">
          <select value={filters.from} onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}>
            <option value="">De — tous</option>
            {chars.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filters.about} onChange={(e) => setFilters((f) => ({ ...f, about: e.target.value }))}>
            <option value="">À propos — tous</option>
            {chars.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            className="filter-input"
            placeholder="catégorie"
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
          />
        </div>
      </section>

      {showForm && (
        <section className="panel-section">
          <h3>{editId ? 'Éditer' : 'Nouvelle entrée'}</h3>
          <form className="knowledge-form" onSubmit={handleSubmit}>
            <div className="field-row">
              <div className="field">
                <label htmlFor="kf-from">De</label>
                <select id="kf-from" value={form.from}
                  onChange={(e) => setForm((f) => ({ ...f, from: e.target.value }))}
                  disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {chars.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="kf-about">À propos de</label>
                <select id="kf-about" value={form.about}
                  onChange={(e) => setForm((f) => ({ ...f, about: e.target.value }))}
                  disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {chars.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="kf-activity">Activité</label>
                <input id="kf-activity" {...field('activity')} disabled={busy.save} />
              </div>
              <div className="field">
                <label htmlFor="kf-scene">Scène</label>
                <input id="kf-scene" {...field('scene')} disabled={busy.save} />
              </div>
            </div>
            <div className="field">
              <label>Catégorie <span className="label-opt">(optionnelle)</span></label>
              <CategoryCombo
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                disabled={busy.save}
              />
            </div>
            <div className="field">
              <label htmlFor="kf-value">Contenu <span className="label-opt">(obligatoire)</span></label>
              <textarea id="kf-value" rows={4} required {...field('value')} disabled={busy.save} />
            </div>
            <div className="panel-actions">
              <button type="submit" className="btn-primary"
                style={{ padding: '0.45rem 1rem', fontSize: '0.83rem' }} disabled={busy.save}>
                {busy.save ? '…' : editId ? 'Mettre à jour' : 'Ajouter'}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
            </div>
          </form>
        </section>
      )}

      <section className="panel-section">
        {filtered.length === 0
          ? <p className="empty-note">Aucune entrée.</p>
          : (
            <div className="knowledge-grid">
              <div className="knowledge-header">
                <span>De</span><span>À propos</span><span>Catégorie</span>
                <span>Scène</span><span>Contenu</span><span>Date</span><span></span>
              </div>
              {filtered.map((e) => (
                <div key={e._id} className="knowledge-row">
                  <span className="kc-tag">{e.from}</span>
                  <span className="kc-tag">{e.about}</span>
                  <span className="kc-cat">{e.category}</span>
                  <span className="kc-dim">{e.scene}</span>
                  <span className="kc-value" title={e.value}>{excerpt(e.value)}</span>
                  <span className="kc-dim">{formatTs(e.ts)}</span>
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

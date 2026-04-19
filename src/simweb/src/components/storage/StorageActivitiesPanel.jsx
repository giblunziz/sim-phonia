import { useState, useEffect, useCallback } from 'react';
import { activityList, activityPut, activityDelete, schemaList } from '../../api/simphonia.js';
import MarkdownEditor from '../common/MarkdownEditor.jsx';

const EMPTY_FORM = {
  slug:        '',
  label:       '',
  description: '',
  rules_mj:     '',
  rules_players:'',
  system:      [],          // [{enabled, schema}]
  wm_enabled:  false,
  wm_distribution: 'random',
  wm_deck:     [],          // string[]
  debrief_enabled: true,
  debrief_schema:  '',
};

const DISTRIBUTION_OPTIONS = ['random', 'fixed', 'ordered'];

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleDateString('fr-FR', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return ts; }
}

function excerpt(text, n = 60) {
  return text?.length > n ? text.slice(0, n) + '…' : (text ?? '');
}

function entryToForm(entry) {
  const wm = entry.winning_mode ?? {};
  const db = entry.debrief ?? {};
  return {
    slug:            entry._id ?? '',
    label:           entry.label ?? '',
    description:     entry.description ?? '',
    rules_mj:        entry.rules?.mj ?? '',
    rules_players:   entry.rules?.players ?? '',
    system:          (entry.system ?? []).map((s) => ({ ...s })),
    wm_enabled:      wm.enabled ?? false,
    wm_distribution: wm.distribution ?? 'random',
    wm_deck:         [...(wm.deck ?? [])],
    debrief_enabled: db.enabled ?? true,
    debrief_schema:  db.schema ?? '',
  };
}

function formToPayload(form) {
  return {
    label:       form.label,
    description: form.description,
    rules: {
      mj:      form.rules_mj,
      players: form.rules_players,
    },
    system: form.system,
    winning_mode: {
      enabled:      form.wm_enabled,
      distribution: form.wm_distribution,
      deck:         form.wm_deck,
    },
    debrief: {
      enabled: form.debrief_enabled,
      schema:  form.debrief_schema,
    },
  };
}

// ── sous-composants ────────────────────────────────────────────────────────────

function DeckEditor({ deck, onChange, disabled }) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim();
    if (!v) return;
    onChange([...deck, v]);
    setInput('');
  };

  const remove = (i) => onChange(deck.filter((_, idx) => idx !== i));

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem', marginBottom: '0.4rem' }}>
        {deck.map((card, i) => (
          <span key={i} className="kc-tag" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
            {card}
            {!disabled && (
              <button type="button" className="btn-row btn-row-danger"
                style={{ padding: '0 0.25rem', lineHeight: 1 }}
                onClick={() => remove(i)}>✕</button>
            )}
          </span>
        ))}
        {deck.length === 0 && <span className="kc-dim">Aucune carte</span>}
      </div>
      {!disabled && (
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
            placeholder="Nom de la carte…"
            style={{ flex: 1 }}
          />
          <button type="button" className="btn-secondary" onClick={add}>+ Ajouter</button>
        </div>
      )}
    </div>
  );
}

function SystemList({ items, onChange, disabled, schemas }) {
  const update = (i, patch) =>
    onChange(items.map((item, idx) => idx === i ? { ...item, ...patch } : item));
  const add = () => onChange([...items, { enabled: true, schema: '' }]);
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div>
      {items.map((item, i) => (
        <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.4rem' }}>
          <input type="checkbox" checked={item.enabled}
            onChange={(e) => update(i, { enabled: e.target.checked })} disabled={disabled} />
          <select value={item.schema}
            onChange={(e) => update(i, { schema: e.target.value })}
            disabled={disabled} style={{ flex: 1 }}>
            <option value="">— schéma —</option>
            {schemas.map((s) => <option key={s._id} value={s._id}>{s._id}</option>)}
          </select>
          {!disabled && (
            <button type="button" className="btn-row btn-row-danger" onClick={() => remove(i)}>✕</button>
          )}
        </div>
      ))}
      {!disabled && (
        <button type="button" className="btn-secondary" onClick={add}>+ Ajouter</button>
      )}
    </div>
  );
}

// ── panneau principal ──────────────────────────────────────────────────────────

export default function StorageActivitiesPanel() {
  const [entries, setEntries]     = useState([]);
  const [schemas, setSchemas]     = useState([]);
  const [editId, setEditId]       = useState(null);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [showForm, setShowForm]   = useState(false);
  const [busy, setBusy]           = useState({});
  const [msg, setMsg]             = useState(null);
  const [error, setError]         = useState(null);

  const load = useCallback(async () => {
    try { setEntries(await activityList() ?? []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => {
    load();
    schemaList().then((list) => setSchemas(list ?? [])).catch(() => {});
  }, [load]);

  const f = (key) => ({
    value: form[key],
    onChange: (e) => setForm((prev) => ({ ...prev, [key]: e.target.value })),
  });

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setError(null);
    setShowForm(true);
  };

  const openEdit = (entry) => {
    setForm(entryToForm(entry));
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
      await activityPut(id, formToPayload(form));
      setMsg(editId ? 'Activité mise à jour.' : 'Activité créée.');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, save: false }));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm(`Supprimer l'activité "${id}" ?`)) return;
    await activityDelete(id);
    setMsg('Activité supprimée.');
    await load();
  };

  return (
    <div className="admin-panel">
      <h2>Storage — Activités</h2>

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
          <h3>{editId ? `Éditer — ${editId}` : 'Nouvelle activité'}</h3>
          <form onSubmit={handleSubmit}>

            {/* ── identifiant ── */}
            {!editId && (
              <div className="field">
                <label htmlFor="act-slug">Slug <span className="label-opt">(identifiant unique)</span></label>
                <input id="act-slug" type="text" placeholder="ex: action_verite"
                  disabled={busy.save} {...f('slug')} style={{ width: '100%' }} />
              </div>
            )}

            {/* ── infos générales ── */}
            <div className="field-row">
              <div className="field">
                <label htmlFor="act-label">Label</label>
                <input id="act-label" type="text" disabled={busy.save} {...f('label')} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="act-desc">Description</label>
              <textarea id="act-desc" rows={2} disabled={busy.save} {...f('description')} />
            </div>

            {/* ── règles ── */}
            <div className="field">
              <MarkdownEditor
                label="Règles — MJ"
                value={form.rules_mj}
                onChange={(e) => setForm((p) => ({ ...p, rules_mj: e.target.value }))}
                disabled={busy.save}
                rows={10}
              />
            </div>
            <div className="field">
              <MarkdownEditor
                label="Règles — Joueurs"
                value={form.rules_players}
                onChange={(e) => setForm((p) => ({ ...p, rules_players: e.target.value }))}
                disabled={busy.save}
                rows={10}
              />
            </div>

            {/* ── system prompts ── */}
            <div className="field">
              <label>Prompts système</label>
              <SystemList
                items={form.system}
                onChange={(v) => setForm((p) => ({ ...p, system: v }))}
                disabled={busy.save}
                schemas={schemas}
              />
            </div>

            {/* ── winning mode ── */}
            <div className="field">
              <label>
                <input type="checkbox" checked={form.wm_enabled}
                  onChange={(e) => setForm((p) => ({ ...p, wm_enabled: e.target.checked }))}
                  disabled={busy.save}
                  style={{ marginRight: '0.4rem' }}
                />
                Winning mode
              </label>
              {form.wm_enabled && (
                <div style={{ marginTop: '0.5rem', paddingLeft: '1rem', borderLeft: '2px solid var(--border)' }}>
                  <div className="field">
                    <label htmlFor="act-wm-dist">Distribution</label>
                    <select id="act-wm-dist" value={form.wm_distribution}
                      onChange={(e) => setForm((p) => ({ ...p, wm_distribution: e.target.value }))}
                      disabled={busy.save}>
                      {DISTRIBUTION_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label>Deck de cartes</label>
                    <DeckEditor
                      deck={form.wm_deck}
                      onChange={(v) => setForm((p) => ({ ...p, wm_deck: v }))}
                      disabled={busy.save}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* ── debrief ── */}
            <div className="field">
              <label>
                <input type="checkbox" checked={form.debrief_enabled}
                  onChange={(e) => setForm((p) => ({ ...p, debrief_enabled: e.target.checked }))}
                  disabled={busy.save}
                  style={{ marginRight: '0.4rem' }}
                />
                Debrief
              </label>
              {form.debrief_enabled && (
                <div style={{ marginTop: '0.5rem', paddingLeft: '1rem', borderLeft: '2px solid var(--border)' }}>
                  <div className="field">
                    <label htmlFor="act-db-schema">Schéma de debrief</label>
                    <select id="act-db-schema"
                      value={form.debrief_schema}
                      onChange={(e) => setForm((p) => ({ ...p, debrief_schema: e.target.value }))}
                      disabled={busy.save}
                      style={{ width: '100%' }}>
                      <option value="">— schéma —</option>
                      {schemas.map((s) => <option key={s._id} value={s._id}>{s._id}</option>)}
                    </select>
                  </div>
                </div>
              )}
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

      {/* ── liste ── */}
      <section className="panel-section">
        {entries.length === 0
          ? <p className="empty-note">Aucune activité.</p>
          : (
            <div className="knowledge-grid" style={{ gridTemplateColumns: '1fr 1.5fr 2fr 1fr auto' }}>
              <div className="knowledge-header">
                <span>Slug</span><span>Label</span><span>Description</span>
                <span>Modifié le</span><span></span>
              </div>
              {entries.map((e) => (
                <div key={e._id} className="knowledge-row">
                  <span className="kc-tag">{e._id}</span>
                  <span>{e.label}</span>
                  <span className="kc-dim">{excerpt(e.description)}</span>
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

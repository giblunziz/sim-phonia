import { useState, useEffect, useCallback, useRef } from 'react';
import {
  instanceList, instancePut, instanceDelete,
  activityList, sceneList, providerList, listCharacters,
  activityRun,
} from '../../api/simphonia.js';
import MarkdownEditor from '../common/MarkdownEditor.jsx';

const TURNING_MODES = ['starter', 'named', 'round_robin', 'next_remaining', 'random_remaining', 'random'];
// V1 : human + autonomous. `human_in_loop` sera exposé à l'étape #5 du mj_service.
const MJ_MODES = ['human', 'autonomous'];

const EMPTY_FORM = {
  slug: '',
  activity: '',
  scene: '',
  players: [],
  provider_mj: '',
  provider_players: '',
  max_rounds: 3,
  temperature: 0.8,
  turning_mode: 'named',
  mj_mode: 'human',
  starter: '',
  amorce: '',
  events: [],
  instructions: [],
};

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleDateString('fr-FR', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return ts; }
}

function entryToForm(e) {
  return {
    slug:             e._id ?? '',
    activity:         e.activity ?? '',
    scene:            e.scene ?? '',
    players:          [...(e.players ?? [])],
    provider_mj:      e.providers?.mj ?? '',
    provider_players: e.providers?.players ?? '',
    max_rounds:       e.max_rounds ?? 3,
    temperature:      e.temperature ?? 0.8,
    // Legacy tolerance : les valeurs bancales ('mj', autre) retombent sur la défaut.
    turning_mode:     TURNING_MODES.includes(e.turning_mode) ? e.turning_mode : 'named',
    mj_mode:          MJ_MODES.includes(e.mj_mode) ? e.mj_mode : 'human',
    starter:          e.starter ?? '',
    amorce:           e.amorce ?? '',
    events:           (e.events ?? []).map((x) => ({ ...x })),
    instructions:     (e.instructions ?? []).map((x) => ({ ...x })),
  };
}

function formToPayload(f) {
  return {
    activity:     f.activity,
    scene:        f.scene,
    players:      f.players,
    providers:    { mj: f.provider_mj, players: f.provider_players },
    max_rounds:   Number(f.max_rounds),
    temperature:  Number(f.temperature),
    turning_mode: f.turning_mode,
    mj_mode:      f.mj_mode,
    starter:      f.starter || null,
    amorce:       f.amorce,
    events:       f.events,
    instructions: f.instructions,
  };
}

// ── PlayerOrderList ────────────────────────────────────────────────────────────

function PlayerOrderList({ players, allChars, onChange, disabled }) {
  const dragIdx = useRef(null);

  const addPlayer = (name) => {
    if (!players.includes(name)) onChange([...players, name]);
  };

  const removePlayer = (name) =>
    onChange(players.filter((p) => p !== name));

  const onDragStart = (i) => { dragIdx.current = i; };

  const onDragOver = (e, i) => {
    e.preventDefault();
    if (dragIdx.current === null || dragIdx.current === i) return;
    const next = [...players];
    const [moved] = next.splice(dragIdx.current, 1);
    next.splice(i, 0, moved);
    dragIdx.current = i;
    onChange(next);
  };

  const available = allChars.filter((c) => !players.includes(c));

  return (
    <div>
      {/* liste ordonnée */}
      <div className="player-order-list">
        {players.length === 0 && (
          <p className="empty-note" style={{ margin: '0.4rem 0', fontSize: '0.82rem' }}>
            Aucun joueur — ajoutez-en ci-dessous.
          </p>
        )}
        {players.map((p, i) => (
          <div
            key={p}
            className={`player-order-item${disabled ? ' disabled' : ''}`}
            draggable={!disabled}
            onDragStart={() => onDragStart(i)}
            onDragOver={(e) => onDragOver(e, i)}
            onDragEnd={() => { dragIdx.current = null; }}
          >
            <span className="player-order-handle" title="Glisser pour réordonner">⠿</span>
            <span className="player-order-pos">{i + 1}</span>
            <span className="player-order-name kc-tag">{p}</span>
            {!disabled && (
              <button type="button" className="btn-row btn-row-danger"
                style={{ marginLeft: 'auto' }}
                onClick={() => removePlayer(p)}>✕</button>
            )}
          </div>
        ))}
      </div>

      {/* personnages disponibles */}
      {!disabled && available.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem' }}>
          {available.map((c) => (
            <button key={c} type="button" className="btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem' }}
              onClick={() => addPlayer(c)}>
              + {c}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── EventsList ─────────────────────────────────────────────────────────────────

function EventsList({ items, onChange, disabled }) {
  const update = (i, patch) => onChange(items.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const add    = () => onChange([...items, { round: 1, instruction: '' }]);
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div>
      {items.map((item, i) => (
        <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', width: '80px', flexShrink: 0 }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Tour</label>
            <input type="number" min={1} value={item.round}
              onChange={(e) => update(i, { round: Number(e.target.value) })}
              disabled={disabled} style={{ width: '100%' }} />
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Instruction</label>
            <textarea rows={2} value={item.instruction}
              onChange={(e) => update(i, { instruction: e.target.value })}
              disabled={disabled} style={{ width: '100%', resize: 'vertical' }} />
          </div>
          {!disabled && (
            <button type="button" className="btn-row btn-row-danger"
              style={{ alignSelf: 'flex-end', marginBottom: '2px' }}
              onClick={() => remove(i)}>✕</button>
          )}
        </div>
      ))}
      {!disabled && <button type="button" className="btn-secondary" onClick={add}>+ Ajouter</button>}
    </div>
  );
}

// ── InstructionsList ────────────────────────────────────────────────────────────

function InstructionsList({ items, onChange, disabled, players }) {
  const update = (i, patch) => onChange(items.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const add    = () => onChange([...items, { round: 1, who: '', instruction: '' }]);
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div>
      {items.map((item, i) => {
        const isNumeric = typeof item.who === 'number';
        return (
          <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.6rem', marginBottom: '0.5rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.4rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', width: '80px', flexShrink: 0 }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Tour</label>
                <input type="number" min={1} value={item.round}
                  onChange={(e) => update(i, { round: Number(e.target.value) })}
                  disabled={disabled} style={{ width: '100%' }} />
              </div>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Destinataire
                  {!disabled && (
                    <button type="button"
                      style={{ marginLeft: '0.5rem', fontSize: '0.7rem', background: 'none', border: '1px solid var(--border)', borderRadius: '3px', color: 'var(--accent)', cursor: 'pointer', padding: '0 0.35rem' }}
                      onClick={() => update(i, { who: isNumeric ? '' : 1 })}>
                      {isNumeric ? '→ personnage' : '→ position'}
                    </button>
                  )}
                </label>
                {isNumeric
                  ? <input type="number" min={1} value={item.who}
                      onChange={(e) => update(i, { who: Number(e.target.value) })}
                      disabled={disabled} placeholder="Position (1-based)" style={{ width: '100%' }} />
                  : <select value={item.who}
                      onChange={(e) => update(i, { who: e.target.value })}
                      disabled={disabled} style={{ width: '100%' }}>
                      <option value="">— personnage —</option>
                      {players.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                }
              </div>
              {!disabled && (
                <button type="button" className="btn-row btn-row-danger"
                  style={{ alignSelf: 'flex-end' }}
                  onClick={() => remove(i)}>✕</button>
              )}
            </div>
            <textarea rows={3} value={item.instruction}
              onChange={(e) => update(i, { instruction: e.target.value })}
              disabled={disabled} placeholder="Instruction (whisper)…"
              style={{ width: '100%', resize: 'vertical' }} />
          </div>
        );
      })}
      {!disabled && <button type="button" className="btn-secondary" onClick={add}>+ Ajouter</button>}
    </div>
  );
}

// ── Panneau principal ───────────────────────────────────────────────────────────

export default function StorageInstancesPanel({ onLaunch }) {
  const [entries, setEntries]     = useState([]);
  const [activities, setActivities] = useState([]);
  const [scenes, setScenes]       = useState([]);
  const [providers, setProviders] = useState([]);
  const [chars, setChars]         = useState([]);
  const [editId, setEditId]       = useState(null);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [showForm, setShowForm]   = useState(false);
  const [busy, setBusy]           = useState({});
  const [msg, setMsg]             = useState(null);
  const [error, setError]         = useState(null);
  const [slugError, setSlugError] = useState(false);

  const load = useCallback(async () => {
    try { setEntries(await instanceList() ?? []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => {
    load();
    activityList().then((l) => setActivities(l ?? [])).catch(() => {});
    sceneList().then((l) => setScenes(l ?? [])).catch(() => {});
    providerList().then((l) => setProviders(l ?? [])).catch(() => {});
    listCharacters().then((l) => setChars(l ?? [])).catch(() => {});
  }, [load]);

  const set = (key, val) => setForm((p) => ({ ...p, [key]: val }));

  const setPlayers = (next) =>
    setForm((p) => ({
      ...p,
      players: next,
      starter: next.includes(p.starter) ? p.starter : '',
    }));

  const openCreate    = () => { setForm(EMPTY_FORM); setEditId(null); setError(null); setSlugError(false); setShowForm(true); };
  const openEdit      = (e)  => { setForm(entryToForm(e)); setEditId(e._id); setError(null); setSlugError(false); setShowForm(true); };
  const openDuplicate = (e)  => {
    // Deep-copy via entryToForm puis reset du slug — l'utilisateur saisit un nouvel identifiant
    setForm({ ...entryToForm(e), slug: '' });
    setEditId(null);          // mode création (nouveau document Mongo)
    setError(null);
    setSlugError(false);
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const id = editId ?? form.slug.trim();
    if (!id) {
      setError('Le slug est obligatoire.');
      setSlugError(true);
      return;
    }
    setSlugError(false);
    setBusy((b) => ({ ...b, save: true }));
    setError(null);
    try {
      await instancePut(id, formToPayload(form));
      setMsg(editId ? 'Instance mise à jour.' : 'Instance créée.');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, save: false }));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm(`Supprimer l'instance "${id}" ?`)) return;
    await instanceDelete(id);
    setMsg('Instance supprimée.');
    await load();
  };

  const handleLaunch = async (id) => {
    setBusy((b) => ({ ...b, [id]: true }));
    setError(null);
    try {
      const result = await activityRun(id);
      if (onLaunch) onLaunch(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
    }
  };

  return (
    <div className="admin-panel">
      <h2>Storage — Instances d'activité</h2>

      {error && <p className="error">{error}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Instances ({entries.length})</h3>
          <button className="btn-secondary" onClick={openCreate}>+ Nouveau</button>
          <button className="btn-secondary" onClick={load}>↻ Actualiser</button>
          {msg && <span className="reset-msg">{msg}</span>}
        </div>
      </section>

      {showForm && (
        <section className="panel-section">
          <h3>{editId ? `Éditer — ${editId}` : 'Nouvelle instance'}</h3>
          <form onSubmit={handleSubmit}>

            {/* slug */}
            {!editId && (
              <div className="field">
                <label htmlFor="ins-slug">
                  Slug <span className="label-opt">(identifiant unique, obligatoire)</span>
                  {slugError && <span style={{ color: 'var(--danger)', marginLeft: '0.5rem', fontSize: '0.78rem' }}>⚠ requis</span>}
                </label>
                <input
                  id="ins-slug"
                  type="text"
                  required
                  aria-invalid={slugError || undefined}
                  placeholder="ex: action_verite_20260420"
                  value={form.slug}
                  onChange={(e) => { set('slug', e.target.value); if (slugError && e.target.value.trim()) setSlugError(false); }}
                  disabled={busy.save}
                  style={{
                    width: '100%',
                    borderColor: slugError ? 'var(--danger)' : undefined,
                    outlineColor: slugError ? 'var(--danger)' : undefined,
                  }}
                />
              </div>
            )}

            {/* activité + scène */}
            <div className="field-row">
              <div className="field">
                <label htmlFor="ins-act">Activité</label>
                <select id="ins-act" value={form.activity}
                  onChange={(e) => set('activity', e.target.value)} disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {activities.map((a) => <option key={a._id} value={a._id}>{a._id}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ins-scene">Scène</label>
                <select id="ins-scene" value={form.scene}
                  onChange={(e) => set('scene', e.target.value)} disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {scenes.map((s) => <option key={s._id} value={s._id}>{s._id}</option>)}
                </select>
              </div>
            </div>

            {/* providers */}
            <div className="field-row">
              <div className="field">
                <label htmlFor="ins-prov-mj">Provider — MJ</label>
                <select id="ins-prov-mj" value={form.provider_mj}
                  onChange={(e) => set('provider_mj', e.target.value)} disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {providers.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ins-prov-pl">Provider — Joueurs</label>
                <select id="ins-prov-pl" value={form.provider_players}
                  onChange={(e) => set('provider_players', e.target.value)} disabled={busy.save}>
                  <option value="">— choisir —</option>
                  {providers.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>

            {/* config numérique */}
            <div className="field-row">
              <div className="field">
                <label htmlFor="ins-rounds">Tours max</label>
                <input id="ins-rounds" type="number" min={1} value={form.max_rounds}
                  onChange={(e) => set('max_rounds', e.target.value)} disabled={busy.save} />
              </div>
              <div className="field">
                <label htmlFor="ins-temp">Température</label>
                <input id="ins-temp" type="number" min={0} max={2} step={0.05} value={form.temperature}
                  onChange={(e) => set('temperature', e.target.value)} disabled={busy.save} />
              </div>
              <div className="field">
                <label htmlFor="ins-mode">Mode de tour</label>
                <select id="ins-mode" value={form.turning_mode}
                  onChange={(e) => set('turning_mode', e.target.value)} disabled={busy.save}>
                  {TURNING_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ins-mj-mode">Mode MJ <span className="label-opt">(préconisation)</span></label>
                <select id="ins-mj-mode" value={form.mj_mode}
                  onChange={(e) => set('mj_mode', e.target.value)} disabled={busy.save}>
                  {MJ_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            </div>

            {/* joueurs */}
            <div className="field">
              <label>Joueurs <span className="label-opt">(ordre de jeu — glisser pour réordonner)</span></label>
              <PlayerOrderList
                players={form.players}
                allChars={chars}
                onChange={setPlayers}
                disabled={busy.save}
              />
            </div>

            {/* starter */}
            <div className="field">
              <label htmlFor="ins-starter">Starter <span className="label-opt">(optionnel — aléatoire si vide)</span></label>
              <select id="ins-starter" value={form.starter}
                onChange={(e) => set('starter', e.target.value)} disabled={busy.save}>
                <option value="">— aléatoire —</option>
                {form.players.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {/* amorce */}
            <div className="field">
              <MarkdownEditor label="Amorce" value={form.amorce}
                onChange={(e) => set('amorce', e.target.value)}
                disabled={busy.save} rows={6} />
            </div>

            {/* events */}
            <div className="field">
              <label>Événements programmés</label>
              <EventsList items={form.events}
                onChange={(v) => set('events', v)} disabled={busy.save} />
            </div>

            {/* instructions / whispers */}
            <div className="field">
              <label>Instructions ciblées <span className="label-opt">(whispers)</span></label>
              <InstructionsList items={form.instructions}
                onChange={(v) => set('instructions', v)}
                disabled={busy.save} players={form.players} />
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
          ? <p className="empty-note">Aucune instance.</p>
          : (
            <div className="knowledge-grid" style={{ gridTemplateColumns: '1.2fr 1fr 1fr 1fr 1fr auto' }}>
              <div className="knowledge-header">
                <span>Slug</span><span>Activité</span><span>Scène</span>
                <span>Joueurs</span><span>Modifié le</span><span></span>
              </div>
              {entries.map((e) => (
                <div key={e._id} className="knowledge-row">
                  <span className="kc-tag">{e._id}</span>
                  <span className="kc-dim">{e.activity}</span>
                  <span className="kc-dim">{e.scene}</span>
                  <span className="kc-dim">{(e.players ?? []).length} joueur(s)</span>
                  <span className="kc-dim">{formatTs(e.ts_updated)}</span>
                  <span className="kc-actions">
                    <button className="btn-row" title="Éditer" onClick={() => openEdit(e)}>✎</button>
                    <button className="btn-row" title="Dupliquer (slug à saisir)" onClick={() => openDuplicate(e)}>⎘</button>
                    <button
                      className="btn-row"
                      style={{ background: 'var(--accent)', color: '#fff', fontWeight: 600 }}
                      disabled={busy[e._id]}
                      title="Lancer l'activité"
                      onClick={() => handleLaunch(e._id)}
                    >
                      {busy[e._id] ? '…' : '▶'}
                    </button>
                    <button className="btn-row btn-row-danger" title="Supprimer" onClick={() => handleDelete(e._id)}>✕</button>
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

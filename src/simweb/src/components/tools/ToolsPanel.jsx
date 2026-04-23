import { useState, useEffect, useCallback, useRef } from 'react';
import {
  toolsListCollections,
  toolsListIds,
  toolsTasksList,
  toolsTasksGet,
  toolsTasksPut,
  toolsRun,
  toolsStatus,
  toolsCancel,
  schemaList,
} from '../../api/simphonia.js';

const DEFAULT_TEMPERATURE = 0.8;

export default function ToolsPanel() {
  const [tasks, setTasks]         = useState([]);
  const [selectedTask, setSelectedTask] = useState('');
  const [slug, setSlug]           = useState('');
  const [prompt, setPrompt]       = useState('');
  const [temperature, setTemperature] = useState(DEFAULT_TEMPERATURE);

  const [collections, setCollections] = useState([]);
  const [schemas, setSchemas]     = useState([]);

  const [sourceColl, setSourceColl]   = useState('');
  const [sourceIds, setSourceIds]     = useState([]);        // liste des _id disponibles
  const [sourceSelected, setSourceSelected] = useState(new Set());

  const [subjectColl, setSubjectColl]     = useState('');
  const [subjectIds, setSubjectIds]       = useState([]);
  const [subjectSelected, setSubjectSelected] = useState(new Set());

  const [schemaId, setSchemaId]   = useState('');
  const [skipSelf, setSkipSelf]   = useState(true);

  const [busy, setBusy]           = useState({});
  const [error, setError]         = useState(null);
  const [msg, setMsg]             = useState(null);

  const [runId, setRunId]         = useState(null);
  const [status, setStatus]       = useState(null);
  const pollRef                   = useRef(null);

  // ── chargement initial ─────────────────────────────────────────

  const loadTasks = useCallback(async () => {
    try { setTasks(await toolsTasksList() ?? []); }
    catch (e) { setError(`tasks.list : ${e.message}`); }
  }, []);

  const loadCollections = useCallback(async () => {
    try { setCollections(await toolsListCollections() ?? []); }
    catch (e) { setError(`collections.list : ${e.message}`); }
  }, []);

  const loadSchemas = useCallback(async () => {
    try { setSchemas(await schemaList() ?? []); }
    catch { /* optionnel */ }
  }, []);

  useEffect(() => { loadTasks(); loadCollections(); loadSchemas(); }, [loadTasks, loadCollections, loadSchemas]);

  // ── sélection task → charge slug/prompt/temperature ────────────

  const handleSelectTask = async (newSlug) => {
    setSelectedTask(newSlug);
    setError(null); setMsg(null);
    if (!newSlug) {
      setSlug(''); setPrompt(''); setTemperature(DEFAULT_TEMPERATURE);
      return;
    }
    try {
      const task = await toolsTasksGet(newSlug);
      if (task) {
        setSlug(task._id ?? newSlug);
        setPrompt(task.prompt ?? '');
        setTemperature(task.temperature ?? DEFAULT_TEMPERATURE);
      }
    } catch (e) { setError(`tasks.get : ${e.message}`); }
  };

  const handleSave = async () => {
    if (!slug.trim()) { setError('Slug obligatoire'); return; }
    setBusy((b) => ({ ...b, save: true }));
    setError(null);
    try {
      await toolsTasksPut(slug.trim(), prompt, Number(temperature));
      setMsg(`Task « ${slug} » sauvegardée.`);
      await loadTasks();
      setSelectedTask(slug.trim());
    } catch (e) { setError(`tasks.put : ${e.message}`); }
    finally { setBusy((b) => ({ ...b, save: false })); }
  };

  // ── collections source/subject ─────────────────────────────────

  const loadIds = async (collectionName, setter) => {
    if (!collectionName) { setter([]); return; }
    try {
      const ids = await toolsListIds(collectionName);
      setter(ids ?? []);
    } catch (e) { setError(`ids.list ${collectionName} : ${e.message}`); }
  };

  const handleSourceColl = async (name) => {
    setSourceColl(name);
    setSourceSelected(new Set());
    await loadIds(name, setSourceIds);
  };

  const handleSubjectColl = async (name) => {
    setSubjectColl(name);
    setSubjectSelected(new Set());
    await loadIds(name, setSubjectIds);
  };

  const toggleId = (set, setter) => (_id) => {
    const next = new Set(set);
    if (next.has(_id)) next.delete(_id); else next.add(_id);
    setter(next);
  };

  const handleRefresh = () => {
    loadCollections();
    if (sourceColl) loadIds(sourceColl, setSourceIds);
    if (subjectColl) loadIds(subjectColl, setSubjectIds);
  };

  // ── run + polling ──────────────────────────────────────────────

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  const handleRun = async () => {
    if (!slug.trim()) { setError('Slug obligatoire'); return; }
    if (!prompt.trim()) { setError('Prompt obligatoire'); return; }
    if (!sourceColl || sourceSelected.size === 0) {
      setError('Sélectionne au moins une source'); return;
    }
    setError(null); setMsg(null);
    setBusy((b) => ({ ...b, run: true }));
    setStatus(null);

    try {
      const result = await toolsRun({
        task_slug:          slug.trim(),
        prompt,
        temperature:        Number(temperature),
        source_collection:  sourceColl,
        source_ids:         [...sourceSelected],
        subject_collection: subjectColl || null,
        subject_ids:        subjectColl ? [...subjectSelected] : null,
        schema_id:          schemaId || null,
        skip_self:          skipSelf,
      });
      setRunId(result.run_id);

      pollRef.current = setInterval(async () => {
        try {
          const st = await toolsStatus(result.run_id);
          if (!st) return;
          setStatus(st);
          if (['completed', 'failed', 'cancelled'].includes(st.status)) {
            stopPolling();
            setBusy((b) => ({ ...b, run: false }));
            setMsg(`Run ${st.status} — ${st.succeeded}/${st.total} réussies.`);
          }
        } catch (e) {
          stopPolling();
          setError(`status : ${e.message}`);
          setBusy((b) => ({ ...b, run: false }));
        }
      }, 1000);
    } catch (e) {
      setError(`run : ${e.message}`);
      setBusy((b) => ({ ...b, run: false }));
    }
  };

  const handleStop = async () => {
    if (!runId) return;
    setBusy((b) => ({ ...b, stop: true }));
    try {
      await toolsCancel(runId);
      setMsg('Interruption demandée — prise en compte entre deux cellules.');
    } catch (e) {
      setError(`cancel : ${e.message}`);
    } finally {
      setBusy((b) => ({ ...b, stop: false }));
    }
  };

  // ── rendu ──────────────────────────────────────────────────────

  const progressPct = status && status.total
    ? Math.round((status.completed / status.total) * 100)
    : 0;

  return (
    <div className="admin-panel tools-panel">
      <h2>Tools — atelier one-shot</h2>

      {error && <p className="error">{error}</p>}
      {msg && <p className="reset-msg">{msg}</p>}

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Task</h3>
          <select value={selectedTask} onChange={(e) => handleSelectTask(e.target.value)}>
            <option value="">— nouvelle task —</option>
            {tasks.map((t) => <option key={t._id} value={t._id}>{t._id}</option>)}
          </select>
          <button className="btn-secondary" onClick={loadTasks}>↻</button>
        </div>
        <div className="field-row" style={{ marginTop: '0.5rem' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Slug</label>
            <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="identifiant" />
          </div>
          <div className="field" style={{ width: '8rem' }}>
            <label>Temperature</label>
            <input type="number" min="0" max="2" step="0.1" value={temperature}
              onChange={(e) => setTemperature(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Prompt (commande user)</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
            rows={6} placeholder="Ce que le LLM doit faire..." />
        </div>
        <button className="btn-secondary" onClick={handleSave} disabled={busy.save}>
          {busy.save ? '…' : '💾 Save'}
        </button>
      </section>

      <section className="panel-section">
        <div className="panel-actions">
          <h3>Sélection</h3>
          <button className="btn-secondary" onClick={handleRefresh} title="Recharger collections + ids">↻ Refresh</button>
        </div>

        <div className="field-row" style={{ alignItems: 'flex-start' }}>
          {/* Source */}
          <div className="field" style={{ flex: 1 }}>
            <label>Source — collection</label>
            <select value={sourceColl} onChange={(e) => handleSourceColl(e.target.value)}>
              <option value="">— choisir —</option>
              {collections.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <div className="tools-id-list">
              {sourceIds.map((id) => (
                <label key={id} className="tools-id-checkbox">
                  <input type="checkbox"
                    checked={sourceSelected.has(id)}
                    onChange={() => toggleId(sourceSelected, setSourceSelected)(id)} />
                  <span>{id}</span>
                </label>
              ))}
              {sourceIds.length === 0 && <span className="empty-note">— aucune —</span>}
            </div>
          </div>

          {/* Subject */}
          <div className="field" style={{ flex: 1 }}>
            <label>Subject — collection (optionnel)</label>
            <select value={subjectColl} onChange={(e) => handleSubjectColl(e.target.value)}>
              <option value="">— aucun —</option>
              {collections.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <div className="tools-id-list">
              {subjectIds.map((id) => (
                <label key={id} className="tools-id-checkbox">
                  <input type="checkbox"
                    checked={subjectSelected.has(id)}
                    onChange={() => toggleId(subjectSelected, setSubjectSelected)(id)} />
                  <span>{id}</span>
                </label>
              ))}
              {subjectIds.length === 0 && subjectColl && <span className="empty-note">— aucune —</span>}
            </div>
          </div>
        </div>
      </section>

      <section className="panel-section">
        <div className="field-row" style={{ alignItems: 'center', gap: '1rem' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Schéma JSON (optionnel)</label>
            <select value={schemaId} onChange={(e) => setSchemaId(e.target.value)}>
              <option value="">— aucun —</option>
              {schemas.map((s) => <option key={s._id} value={s._id}>{s._id}</option>)}
            </select>
          </div>
          <label className="checkbox-label" style={{ marginTop: '1.4rem' }}>
            <input type="checkbox" checked={skipSelf} onChange={(e) => setSkipSelf(e.target.checked)} />
            <span>Skip self</span>
          </label>
          <button className="btn-primary" onClick={handleRun}
            disabled={busy.run} style={{ marginTop: '1.4rem' }}>
            {busy.run ? '…' : '▶ Run'}
          </button>
          {busy.run && runId && (
            <button className="btn-secondary btn-danger" onClick={handleStop}
              disabled={busy.stop} style={{ marginTop: '1.4rem' }}>
              {busy.stop ? '…' : '⏹ Stop'}
            </button>
          )}
        </div>
      </section>

      {status && (
        <section className="panel-section">
          <h3>Run {status.run_id}</h3>
          <div className="tools-progress">
            <div className="tools-progress-bar" style={{ width: `${progressPct}%` }} />
          </div>
          <p>
            {status.completed} / {status.total} — ✅ {status.succeeded} · ❌ {status.failed} — <em>{status.status}</em>
          </p>
          {status.cells?.length > 0 && (
            <ul className="tools-cells">
              {status.cells.map((c, i) => (
                <li key={i} className={c.status === 'succeeded' ? 'ok' : 'ko'}>
                  {c.status === 'succeeded' ? '✅' : '❌'}&nbsp;
                  <code>{c.source}{c.subject ? ` → ${c.subject}` : ''}</code>
                  {c.file && <span className="hint"> — {c.file}</span>}
                  {c.error && <span className="hint"> — {c.error}</span>}
                </li>
              ))}
            </ul>
          )}
          {status.output_dir && (
            <p className="hint">📁 {status.output_dir}</p>
          )}
        </section>
      )}
    </div>
  );
}

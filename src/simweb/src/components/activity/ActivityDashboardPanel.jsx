import { useState, useEffect, useRef, useCallback } from 'react';
import {
  runsList, runsDelete, knowledgeDeleteByActivity,
  activityResume, activityGiveTurn, activityNextRound, activityEnd,
  openActivityStream,
} from '../../api/simphonia.js';

// ── helpers ────────────────────────────────────────────────────────────────────

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return ts; }
}

function StateChip({ state }) {
  const color = state === 'ended' ? 'var(--text-dim)' : 'var(--accent)';
  return (
    <span style={{ color, fontWeight: 600, fontSize: '0.8rem' }}>{state ?? '—'}</span>
  );
}

// ── ExchangeCard ───────────────────────────────────────────────────────────────

function ExchangeCard({ exchange }) {
  const [showPrivate, setShowPrivate] = useState(false);
  const pub     = exchange.public  ?? {};
  const priv    = exchange.private ?? {};
  const hasPriv = Object.values(priv).some(Boolean);

  return (
    <div className="exchange-card">
      <div className="exchange-header">
        <span className="exchange-speaker">{exchange.from}</span>
        {pub.to && <span className="exchange-to">→ {pub.to}</span>}
        <span className="exchange-round">tour {exchange.round}</span>
        <span className="exchange-ts">{formatTs(exchange.ts)}</span>
      </div>
      <div className="exchange-body">
        {pub.talk    && <p className="exchange-talk">"{pub.talk}"</p>}
        {pub.actions && <p className="exchange-field"><span>Actions</span> {Array.isArray(pub.actions) ? pub.actions.join(' / ') : pub.actions}</p>}
        {pub.body    && <p className="exchange-field"><span>Corps</span> {pub.body}</p>}
        {pub.mood    && <p className="exchange-field"><span>Humeur</span> {pub.mood}</p>}
      </div>
      {exchange.whisper && (
        <div className="exchange-whisper">
          <span>📨 Instruction reçue :</span> {exchange.whisper}
        </div>
      )}
      {hasPriv && (
        <div className="exchange-private">
          <button className="exchange-private-toggle" onClick={() => setShowPrivate((v) => !v)}>
            🔒 Privé {showPrivate ? '▴' : '▾'}
          </button>
          {showPrivate && (
            <div className="exchange-private-body">
              {priv.inner         && <p><span>Inner</span> {priv.inner}</p>}
              {priv.inner_thought && <p><span>Inner</span> {priv.inner_thought}</p>}
              {priv.noticed       && <p><span>Noticed</span> {priv.noticed}</p>}
              {priv.expected      && <p><span>Expected</span> {priv.expected}</p>}
              {priv.memory        && <p><span>Memory</span> {priv.memory}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SkippedCard({ event }) {
  return (
    <div className="exchange-card exchange-card-skipped">
      <div className="exchange-header">
        <span className="exchange-speaker">{event.speaker}</span>
        <span className="exchange-round">tour {event.round ?? '?'}</span>
      </div>
      <p style={{ color: 'var(--danger)', fontSize: '0.82rem', marginTop: '0.3rem' }}>
        Pas de réponse ({event.reason})
      </p>
    </div>
  );
}

// ── RunsList ───────────────────────────────────────────────────────────────────

function RunsList({ onResume }) {
  const [runs, setRuns]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy]     = useState({});
  const [error, setError]   = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRuns(await runsList() ?? []); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleResume = async (run) => {
    setBusy((b) => ({ ...b, [run._id]: 'resume' }));
    setError(null);
    try {
      const sessionData = await activityResume(run._id);
      onResume(sessionData);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy((b) => ({ ...b, [run._id]: null }));
    }
  };

  const handleDelete = async (run) => {
    if (!confirm(`Supprimer le run "${run._id}" ?`)) return;
    const withKnowledge = confirm(`Supprimer également les knowledge associés à "${run._id}" ?`);

    setBusy((b) => ({ ...b, [run._id]: 'delete' }));
    setError(null);
    try {
      if (withKnowledge) await knowledgeDeleteByActivity(run._id);
      await runsDelete(run._id);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy((b) => ({ ...b, [run._id]: null }));
    }
  };

  if (loading) return <p className="empty-note">Chargement…</p>;

  const COL = 'minmax(110px,1.6fr) minmax(80px,1fr) 72px 52px minmax(70px,0.9fr) 108px 46px 46px 76px';

  return (
    <div className="admin-panel">
      <div className="panel-actions" style={{ marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0 }}>Dashboard MJ</h2>
        <button className="btn-secondary" onClick={load}>↻ Actualiser</button>
      </div>

      {error && <p className="error">{error}</p>}

      {runs.length === 0
        ? <p className="empty-note">Aucun run d'activité.</p>
        : (
          <div className="knowledge-grid">
            <div className="knowledge-header" style={{ gridTemplateColumns: COL }}>
              <span>Run</span>
              <span>Activité</span>
              <span>État</span>
              <span>Éch.</span>
              <span>Scène</span>
              <span>Modifié le</span>
              <span>Tour</span>
              <span>Max</span>
              <span></span>
            </div>
            {runs.map((r) => {
              const isEnded = r.state === 'ended';
              const isBusy  = !!busy[r._id];
              return (
                <div key={r._id} className="knowledge-row" style={{ gridTemplateColumns: COL }}>
                  <span className="kc-tag" style={{ fontSize: '0.76rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r._id}</span>
                  <span className="kc-dim">{r.activity}</span>
                  <span><StateChip state={r.state} /></span>
                  <span className="kc-dim" style={{ textAlign: 'center' }}>{r.exchange_count ?? 0}</span>
                  <span className="kc-dim">{r.scene || '—'}</span>
                  <span className="kc-dim">{formatTs(r.ts_updated)}</span>
                  <span className="kc-dim">{r.current_round ?? '—'}</span>
                  <span className="kc-dim">{r.max_rounds ?? '—'}</span>
                  <span className="kc-actions">
                    {!isEnded && (
                      <button
                        className="btn-row"
                        style={{ background: 'var(--accent)', color: '#fff', fontWeight: 600 }}
                        disabled={isBusy}
                        title="Reprendre l'activité"
                        onClick={() => handleResume(r)}
                      >
                        {busy[r._id] === 'resume' ? '…' : '▶'}
                      </button>
                    )}
                    <button
                      className="btn-row btn-row-danger"
                      disabled={isBusy}
                      title="Supprimer ce run"
                      onClick={() => handleDelete(r)}
                    >
                      {busy[r._id] === 'delete' ? '…' : '✕'}
                    </button>
                  </span>
                </div>
              );
            })}
          </div>
        )
      }
    </div>
  );
}

// ── MJDashboard ────────────────────────────────────────────────────────────────

function MJDashboard({ sessionData, onClose }) {
  const {
    session_id, run_id, players, round: initRound,
    amorce, event: initEvent, starter,
    exchanges: initExchanges, max_rounds: initMaxRounds,
    state: initState,
  } = sessionData;

  const [round, setRound]             = useState(initRound ?? 1);
  const [roundEvent, setRoundEvent]   = useState(initEvent ?? null);
  const [exchanges, setExchanges]     = useState(
    (initExchanges ?? []).map((ex) => ({ ...ex, public: ex.public ?? {}, private: ex.private ?? {} }))
  );
  const [instruction, setInstruction] = useState('');
  const [pending, setPending]         = useState(false);
  const [ended, setEnded]             = useState(initState === 'ended');
  const [error, setError]             = useState(null);
  const [showAmorce, setShowAmorce]   = useState(true);

  const logRef  = useRef(null);
  const sseRef  = useRef(null);
  const maxRounds = initMaxRounds ?? null;

  // SSE
  useEffect(() => {
    if (ended) return;
    const es = openActivityStream(session_id);
    sseRef.current = es;

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        if (evt.type === 'keepalive') return;

        if (evt.type === 'activity.turn_complete') {
          setExchanges((prev) => [...prev, {
            from:    evt.speaker,
            round:   evt.round,
            ts:      new Date().toISOString(),
            public:  evt.public  ?? {},
            private: evt.private ?? {},
            whisper: evt.whisper ?? null,
          }]);
          setPending(false);
        }

        if (evt.type === 'activity.turn_skipped') {
          setExchanges((prev) => [...prev, { _skipped: true, speaker: evt.speaker, round, reason: evt.reason }]);
          setPending(false);
        }

        if (evt.type === 'activity.round_changed') {
          setRound(evt.round);
          setRoundEvent(evt.event ?? null);
        }

        if (evt.type === 'activity.ended') {
          setEnded(true);
          setPending(false);
          es.close();
        }
      } catch { /* JSON parse error ignoré */ }
    };

    es.onerror = () => {
      if (!ended) setError('Connexion SSE perdue.');
    };

    return () => es.close();
  }, [session_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [exchanges]);

  const handleGiveTurn = async (target) => {
    if (pending || ended) return;
    setPending(true);
    setError(null);
    try {
      await activityGiveTurn(session_id, target, instruction || null);
      setInstruction('');
    } catch (e) {
      setError(e.message);
      setPending(false);
    }
  };

  const handleNextRound = async () => {
    if (pending || ended) return;
    setError(null);
    try {
      const res = await activityNextRound(session_id);
      if (res.state === 'ended') { setEnded(true); return; }
      setRound(res.round);
      setRoundEvent(res.event ?? null);
    } catch (e) { setError(e.message); }
  };

  const handleEnd = async () => {
    if (!confirm('Terminer l\'activité ?')) return;
    setError(null);
    try {
      await activityEnd(session_id);
      setEnded(true);
    } catch (e) { setError(e.message); }
  };

  return (
    <div className="mj-dashboard">

      <div className="dashboard-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <h2 style={{ margin: 0 }}>
            {ended ? '✓ Terminé — ' : '▶ '}{run_id ?? session_id}
          </h2>
          <span className="dashboard-round-badge">
            Round {round}{maxRounds ? ` / ${maxRounds}` : ''}
          </span>
          {starter && <span className="kc-dim" style={{ fontSize: '0.8rem' }}>starter : {starter}</span>}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {!ended && (
            <>
              <button className="btn-secondary" onClick={handleNextRound} disabled={pending}>
                Round suivant ↓
              </button>
              <button className="btn-secondary" style={{ color: 'var(--danger)' }} onClick={handleEnd} disabled={pending}>
                Terminer
              </button>
            </>
          )}
          <button className="btn-secondary" onClick={onClose}>← Retour</button>
        </div>
      </div>

      {error && <p className="error" style={{ margin: '0.5rem 1rem' }}>{error}</p>}

      <div className="dashboard-body">

        <div className="dashboard-controls">
          {amorce && (
            <div className="dashboard-block dashboard-block-amorce">
              <button className="dashboard-block-title" onClick={() => setShowAmorce((v) => !v)}>
                🔒 Amorce MJ {showAmorce ? '▴' : '▾'}
              </button>
              {showAmorce && <div className="dashboard-amorce-text">{amorce}</div>}
            </div>
          )}

          {roundEvent && (
            <div className="dashboard-block dashboard-block-event">
              <div className="dashboard-block-title">📋 Événement — Round {round}</div>
              <div style={{ marginTop: '0.4rem', fontSize: '0.88rem' }}>
                {roundEvent.instruction || roundEvent.content || JSON.stringify(roundEvent)}
              </div>
            </div>
          )}

          <div className="dashboard-block">
            <label className="dashboard-block-title" htmlFor="mj-instruction">Instruction (optionnel)</label>
            <textarea
              id="mj-instruction"
              rows={3}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              disabled={pending || ended}
              placeholder="Whisper au prochain joueur appelé…"
              style={{ width: '100%', resize: 'vertical', marginTop: '0.4rem' }}
            />
          </div>

          <div className="dashboard-block">
            <div className="dashboard-block-title">Joueurs</div>
            <div className="dashboard-players">
              {players.map((p) => (
                <button
                  key={p}
                  className="btn-player"
                  disabled={pending || ended}
                  onClick={() => handleGiveTurn(p)}
                >
                  {pending ? '⏳' : '▶'} {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="dashboard-log" ref={logRef}>
          <div className="dashboard-block-title" style={{ padding: '0.75rem 1rem 0.5rem', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
            Historique ({exchanges.length} échange{exchanges.length !== 1 ? 's' : ''})
          </div>
          {exchanges.length === 0
            ? <p className="empty-note" style={{ padding: '1rem' }}>Aucun échange pour l'instant.</p>
            : exchanges.map((ex, i) =>
                ex._skipped
                  ? <SkippedCard key={i} event={ex} />
                  : <ExchangeCard key={i} exchange={ex} />
              )
          }
        </div>

      </div>
    </div>
  );
}

// ── Entry point ────────────────────────────────────────────────────────────────

export default function ActivityDashboardPanel({ initialSession, onSessionClear }) {
  const [sessionData, setSessionData] = useState(initialSession ?? null);

  useEffect(() => {
    if (initialSession) setSessionData(initialSession);
  }, [initialSession]);

  const handleClose = () => {
    setSessionData(null);
    if (onSessionClear) onSessionClear();
  };

  if (sessionData) {
    return <MJDashboard sessionData={sessionData} onClose={handleClose} />;
  }
  return <RunsList onResume={setSessionData} />;
}

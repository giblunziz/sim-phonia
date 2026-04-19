import { useState } from 'react';
import { ping, getAllCommands } from '../../api/simphonia.js';

export default function ServerPanel() {
  const [pingResult, setPingResult] = useState(null);
  const [commands, setCommands]     = useState(null);
  const [busy, setBusy]             = useState({});

  const handlePing = async () => {
    setBusy((b) => ({ ...b, ping: true }));
    try {
      const value = await ping();
      setPingResult({ ok: true, value, ts: new Date().toLocaleTimeString() });
    } catch (e) {
      setPingResult({ ok: false, value: e.message, ts: new Date().toLocaleTimeString() });
    } finally {
      setBusy((b) => ({ ...b, ping: false }));
    }
  };

  const handleLoadCommands = async () => {
    setBusy((b) => ({ ...b, cmds: true }));
    try {
      setCommands(await getAllCommands());
    } catch {
      setCommands([]);
    } finally {
      setBusy((b) => ({ ...b, cmds: false }));
    }
  };

  return (
    <div className="admin-panel">
      <h2>Serveur</h2>

      <section className="panel-section">
        <h3>État</h3>
        <button className="btn-secondary" onClick={handlePing} disabled={busy.ping}>
          {busy.ping ? '…' : 'Ping'}
        </button>
        {pingResult && (
          <div className={`ping-result ${pingResult.ok ? 'ok' : 'ko'}`}>
            {pingResult.ok ? '✓' : '✗'}&nbsp;{pingResult.value}
            <span className="ping-ts">{pingResult.ts}</span>
          </div>
        )}
      </section>

      <section className="panel-section">
        <h3>Commandes enregistrées</h3>
        <button className="btn-secondary" onClick={handleLoadCommands} disabled={busy.cmds}>
          {busy.cmds ? '…' : commands ? 'Actualiser' : 'Charger'}
        </button>
        {commands !== null && (
          commands.length === 0
            ? <p className="empty-note">Aucune commande trouvée.</p>
            : (
              <table className="commands-table">
                <thead>
                  <tr><th>Bus</th><th>Code</th><th>Description</th></tr>
                </thead>
                <tbody>
                  {commands.map((cmd, i) => (
                    <tr key={i}>
                      <td><code>{cmd.bus}</code></td>
                      <td><code>{cmd.code}</code></td>
                      <td>{cmd.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
        )}
      </section>
    </div>
  );
}

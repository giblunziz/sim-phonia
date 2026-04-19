const BASE = '/bus';

async function dispatch(bus, code, payload = {}) {
  const res = await fetch(`${BASE}/${bus}/dispatch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, payload }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail?.error?.message ?? `HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.result;
}

export async function listCharacters() {
  return dispatch('character', 'list');
}

export async function getCharacter(name) {
  return dispatch('character', 'get', { name });
}

export async function resetCharacters() {
  return dispatch('character', 'reset');
}

export async function ping() {
  return dispatch('system', 'ping');
}

export async function getAllCommands() {
  const busRes = await fetch(`${BASE}`);
  if (!busRes.ok) throw new Error(`HTTP ${busRes.status}`);
  const buses = await busRes.json();

  const results = [];
  for (const bus of buses) {
    const cmdsRes = await fetch(`${BASE}/${bus.name}/commands`);
    if (!cmdsRes.ok) continue;
    const cmds = await cmdsRes.json();
    for (const cmd of cmds) {
      results.push({ bus: bus.name, code: cmd.code, description: cmd.description });
    }
  }
  return results;
}

// ── character_storage ─────────────────────────────────────────────────────────

export const storageListCharacters  = (filter)       => dispatch('character_storage', 'characters.list',   { filter });
export const storageGetCharacter    = (character_id) => dispatch('character_storage', 'characters.get',    { character_id });
export const storagePutCharacter    = (character)    => dispatch('character_storage', 'characters.put',    { character });
export const storageDeleteCharacter = (character_id) => dispatch('character_storage', 'characters.delete', { character_id });

export const storageListKnowledge   = (filter)                  => dispatch('character_storage', 'knowledge.list',   { filter });
export const storageGetKnowledge    = (knowledge_id)            => dispatch('character_storage', 'knowledge.get',    { knowledge_id });
export const storagePushKnowledge   = (entry)                   => dispatch('character_storage', 'knowledge.push',   { entry });
export const storageUpdateKnowledge = (knowledge_id, patch)     => dispatch('character_storage', 'knowledge.update', { knowledge_id, patch });
export const storageDeleteKnowledge = (knowledge_id)            => dispatch('character_storage', 'knowledge.delete', { knowledge_id });

export const memoryResync = () => dispatch('memory', 'resync');

// ── memory ────────────────────────────────────────────────────────────────────

export async function memoryRecall(fromChar, context, about) {
  const payload = { from_char: fromChar, context };
  if (about) payload.about = about;
  return dispatch('memory', 'recall', payload);
}

export async function chatStart(fromChar, to, say, human) {
  return dispatch('chat', 'start', { from_char: fromChar, to, say, human });
}

export async function chatReply(sessionId, fromChar, say, human) {
  return dispatch('chat', 'reply', { session_id: sessionId, from_char: fromChar, say, human });
}

export async function chatStop(sessionId) {
  return dispatch('chat', 'stop', { session_id: sessionId });
}

export function openEventStream(sessionId) {
  return new EventSource(`${BASE}/chat/stream/${sessionId}`);
}

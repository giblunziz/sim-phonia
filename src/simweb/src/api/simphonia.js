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

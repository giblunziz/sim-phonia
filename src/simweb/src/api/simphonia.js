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

// ── activity_storage ──────────────────────────────────────────────────────────

export const activityList   = (filter)                => dispatch('activity_storage', 'activities.list',   { filter });
export const activityGet    = (activity_id)           => dispatch('activity_storage', 'activities.get',    { activity_id });
export const activityPut    = (activity_id, data)     => dispatch('activity_storage', 'activities.put',    { activity_id, data });
export const activityDelete = (activity_id)           => dispatch('activity_storage', 'activities.delete', { activity_id });

export const schemaList   = (filter)              => dispatch('activity_storage', 'schemas.list',   { filter });
export const schemaGet    = (schema_id)           => dispatch('activity_storage', 'schemas.get',    { schema_id });
export const schemaPut    = (schema_id, data)     => dispatch('activity_storage', 'schemas.put',    { schema_id, data });
export const schemaDelete = (schema_id)           => dispatch('activity_storage', 'schemas.delete', { schema_id });

export const sceneList   = (filter)             => dispatch('activity_storage', 'scenes.list',   { filter });
export const sceneGet    = (scene_id)           => dispatch('activity_storage', 'scenes.get',    { scene_id });
export const scenePut    = (scene_id, data)     => dispatch('activity_storage', 'scenes.put',    { scene_id, data });
export const sceneDelete = (scene_id)           => dispatch('activity_storage', 'scenes.delete', { scene_id });

export const instanceList   = (filter)                  => dispatch('activity_storage', 'instances.list',   { filter });
export const instanceGet    = (instance_id)             => dispatch('activity_storage', 'instances.get',    { instance_id });
export const instancePut    = (instance_id, data)       => dispatch('activity_storage', 'instances.put',    { instance_id, data });
export const instanceDelete = (instance_id)             => dispatch('activity_storage', 'instances.delete', { instance_id });

export const providerList = () => dispatch('providers', 'list');

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

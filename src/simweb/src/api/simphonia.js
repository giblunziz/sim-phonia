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

export async function getCharacterTypes() {
  return dispatch('character', 'types');
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

export async function chatStart(fromChar, to, say, human, sceneId = null) {
  return dispatch('chat', 'start', { from_char: fromChar, to, say, human, scene_id: sceneId });
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

// ── photo (génération d'images Z-Image Turbo) ─────────────────────────────────

export function openPhotoStream(sessionId) {
  // Reçoit les events `{type: "photo.published", photo_id, from_char,
  // photo_type, url}` quand une photo prise dans cette session est prête.
  return new EventSource(`${BASE}/photo/stream/${sessionId}`);
}

// URL servable de l'image — `<img src={photoUrl(photo_id)}/>`. Le path est
// servi par simphonia (FastAPI) via `GET /photos/{photo_id}`.
export function photoUrl(photoId) {
  return `/photos/${photoId}`;
}

// ── activity engine ───────────────────────────────────────────────────────────

export const activityRun       = (instance_id, human_player = null) => dispatch('activity', 'run',        { instance_id, human_player });
export const activityResume    = (run_id)                          => dispatch('activity', 'resume',     { run_id });
export const activityGiveTurn  = (session_id, target, instruction) => dispatch('activity', 'give_turn', { session_id, target, instruction: instruction || null });
export const activityNextRound = (session_id)                      => dispatch('activity', 'next_round', { session_id });
export const activityEnd       = (session_id)                      => dispatch('activity', 'end',        { session_id });
export const activitySubmitHumanTurn = (session_id, target, to, talk, actions) =>
  dispatch('activity', 'submit_human_turn', { session_id, target, to, talk, actions });

export const runsList  = (filter)  => dispatch('activity_storage', 'runs.list',   { filter });
export const runsGet   = (run_id)  => dispatch('activity_storage', 'runs.get',    { run_id });
export const runsDelete = (run_id) => dispatch('activity_storage', 'runs.delete', { run_id });

export const knowledgeDeleteByActivity = (activity_id) =>
  dispatch('character_storage', 'knowledge.delete_by_activity', { activity_id });

export function openActivityStream(sessionId) {
  return new EventSource(`${BASE}/activity/stream/${sessionId}`);
}

// ── mj (orchestration step-by-step) ───────────────────────────────────────────

export const mjNextTurn = (session_id) => dispatch('mj', 'next_turn', { session_id });

// ── tools (atelier one-shot) ──────────────────────────────────────────────────

export const toolsListCollections = ()                           => dispatch('tools', 'collections.list');
export const toolsListIds         = (collection_name)            => dispatch('tools', 'ids.list', { collection_name });
export const toolsGetDocument     = (collection_name, _id)       => dispatch('tools', 'get_document', { collection_name, _id });

export const toolsTasksList   = ()                           => dispatch('tools', 'tasks.list');
export const toolsTasksGet    = (slug)                       => dispatch('tools', 'tasks.get',    { slug });
export const toolsTasksPut    = (slug, prompt, temperature)  => dispatch('tools', 'tasks.put',    { slug, prompt, temperature });
export const toolsTasksDelete = (slug)                       => dispatch('tools', 'tasks.delete', { slug });

export const toolsRun    = (payload) => dispatch('tools', 'run', payload);
export const toolsStatus = (run_id)   => dispatch('tools', 'status', { run_id });
export const toolsCancel = (run_id)   => dispatch('tools', 'cancel', { run_id });

// ── shadow_storage (subconscient des joueurs — Tobias) ────────────────────────

export const shadowEntriesList = (filter, skip = 0, limit = 50) =>
  dispatch('shadow_storage', 'entries.list', { filter, skip, limit });
export const shadowEntryGet    = (entry_id)        => dispatch('shadow_storage', 'entries.get',    { entry_id });
export const shadowEntryUpdate = (entry_id, doc)   => dispatch('shadow_storage', 'entries.update', { entry_id, doc });
export const shadowEntryDelete = (entry_id)        => dispatch('shadow_storage', 'entries.delete', { entry_id });
export const shadowChromaResync = ()               => dispatch('shadow_storage', 'chroma.resync');

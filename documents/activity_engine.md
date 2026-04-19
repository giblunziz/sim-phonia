# Cahier des charges — activity_engine

## 1. Rôle

Orchestrateur de session d'activité. Gère le cycle de vie complet : initialisation, tours de parole pilotés par le MJ, transitions de round, fin. Consomme `context_builder`, `provider_registry`, `character_service`, `character_storage`, `activity_storage`.

Il ne dialogue pas avec le LLM directement — il prépare les entrées via `context_builder` et délègue l'appel au provider.

## 2. Localisation

- `src/simphonia/services/activity_service/engine.py` — module flat dans le package `activity_service` existant.
- `src/simphonia/commands/activity.py` — commandes bus.

## 3. Commandes bus (`activity`)

| Code | Payload | Retour immédiat |
|------|---------|-----------------|
| `run` | `{instance_id}` | `{session_id, players, round, starter, amorce, event}` |
| `give_turn` | `{session_id, target, instruction?}` | `{status: "pending"}` — résultat via SSE |
| `next_round` | `{session_id}` | `{round, event, state}` |
| `end` | `{session_id}` | `{state: "ended"}` |

`activity/debrief` est hors scope V1 (backlog WARM W2).

Pas de `mcp=True` sur ces commandes — le MJ est humain, elles sont pilotées par simweb.

## 4. SessionState

État en mémoire pendant la durée de vie d'une session. Singleton `_sessions: dict[str, SessionState]` dans `engine.py`.

```python
@dataclass
class SessionState:
    session_id:       str
    instance_id:      str
    instance:         dict                    # snapshot chargé au run (events, instructions, amorce, etc.)
    activity:         dict                    # template d'activité (rules, json_schema, …)
    scene:            dict                    # fiche scène
    characters:       dict[str, dict]         # slug → fiche personnage
    knowledge:        dict[str, list[dict]]   # slug → knowledge_entries filtrées (présentation)
    provider_name:    str                     # instance['providers'][0]
    round:            int                     # round courant (1-based)
    state:            str                     # "running" | "ended"
    exchange_history: list[dict]              # append-only, croît à chaque give_turn
    retry_counts:     dict[tuple, int]        # (round, speaker) → nb tentatives consécutives
```

Pause / reprise (rechargement depuis storage dans `exchange_history`) : YAGNI — hors scope V1.

## 5. `activity/run`

1. Charge `instance` → `activity_storage / instances.get(instance_id)`.
2. Charge `activity` (template) → `activity_storage / activities.get(instance['activity'])`.
3. Charge `scene` → `activity_storage / scenes.get(instance['scene'])`.
4. Pour chaque `player` dans `instance['players']` :
   - `characters[player]` ← `character_service.get_character(player)`
   - `knowledge[player]` ← `character_storage / knowledge.list(filter={"from": player, "about": {"$in": autres_joueurs}})`
5. Génère `session_id` (UUID4).
6. Crée `SessionState` (round=1, state="running", exchange_history=[], retry_counts={}).
7. Persiste via `activity_storage / instances.put` : ajoute `state`, `current_round`, `ts_started`, `exchanges=[]`, `mj=[]`.
8. Résout `event` = premier élément de `instance['events']` dont `round == 1`, ou `None`.
9. Publie SSE `activity.started` avec payload complet.
10. Retourne `{session_id, players, round:1, starter, amorce, event}`.

`amorce` = `instance.get('amorce')` — affiché uniquement dans le dashboard MJ, **jamais injecté** dans les messages des joueurs.

## 6. `activity/give_turn`

Non-bloquant : retourne `{status: "pending"}` immédiatement et exécute le pipeline en thread.

### Pipeline (thread)

1. `_get_session(session_id)` — lève `SessionNotFound` si absent.
2. Résout `target` → slug via `character_service.get_identifier(target)`.
3. Récupère `character` et `knowledge_entries` depuis `SessionState`.
4. `current_round_event` = élément de `instance['events']` dont `round == session.round`, ou `None`.
5. `whisper` = élément de `instance['instructions']` dont `round == session.round` et `who` résolu vers `target` (position 1-based ou slug), ou `None`.
6. Si `instruction` fourni dans le payload : append dans `instance['mj']` + persiste (put partiel).
7. Construit `mj_instruction = {"instruction": instruction}` si fourni, sinon `None`.
8. Appelle `context_builder.build_system_prompt(target, instance, activity, scene, character, knowledge_entries)`.
9. Appelle `context_builder.build_messages(target, instance, exchange_history, current_round_event, whisper, mj_instruction, amorce=None)`.
10. Appelle `context_builder.get_tools(activity)`.
11. Appelle `provider.call(system_prompt, messages, tools=tools, tool_executor=_make_tool_executor(target))`.
12. Parse via `parse_llm_json(raw_response)`.
13. **Circuit breaker** : si parse échoue ou provider lève exception, incrémente `retry_counts[(round, target)]` et retry jusqu'à 3. Au 3e échec : publie SSE `activity.turn_skipped` et abandonne.
14. Construit l'exchange :

```json
{
  "round": 1,
  "speaker": "isabelle",
  "ts": "2026-04-19T14:32:00Z",
  "raw_response": "<réponse brute LLM>",
  "public":  {"to": "...", "talk": "...", "actions": "...", "body": "...", "mood": "..."},
  "private": {"inner": "...", "noticed": "...", "expected": "...", "memory": "..."}
}
```

15. Appende à `session.exchange_history`.
16. Persiste : `instances.put` avec `exchanges` mis à jour.
17. Publie SSE `activity.turn_complete`.

### Tool executor

Même pattern que `chat_service._make_tool_executor` : dispatch bus local avec `from_char = target` injecté.

### Sélection du provider

V1 : `provider_registry.get(instance['providers'][0])` pour tous les joueurs. Pas de vérification capability `tool_use` en V1 (tous les providers implémentés la supportent).

## 7. `activity/next_round`

1. `_get_session(session_id)`.
2. `session.round += 1`.
3. Si `session.round > instance['max_rounds']` → délègue à `activity/end`, retourne son résultat.
4. Purge `session.retry_counts` (reset circuit breaker pour le nouveau round).
5. Résout `event` pour le nouveau round.
6. Persiste : `instances.put` avec `current_round` mis à jour.
7. Publie SSE `activity.round_changed`.
8. Retourne `{round, event, state: "running"}`.

## 8. `activity/end`

1. `_get_session(session_id)`.
2. `session.state = "ended"`.
3. Persiste : `instances.put` avec `state="ended"`, `ts_ended`.
4. Publie SSE `activity.ended`.
5. `del _sessions[session_id]`.
6. Retourne `{state: "ended"}`.

## 9. SSE

Endpoint : `GET /bus/activity/stream/{session_id}` — même mécanisme que `GET /bus/chat/stream/{session_id}` (même `sse.subscribe` / `sse.publish`, namespacing assuré par l'UUID `session_id`).

| Événement | Champs payload |
|-----------|---------------|
| `activity.started` | `session_id, players, round, starter, amorce, event` |
| `activity.turn_complete` | `session_id, speaker, public, private, round` |
| `activity.turn_skipped` | `session_id, speaker, reason` |
| `activity.round_changed` | `session_id, round, event, state` |
| `activity.ended` | `session_id` |

Tous les payloads portent un champ `type` égal au nom de l'événement.

## 10. Circuit breaker

- Compteur par `(round, speaker)` dans `session.retry_counts`.
- Seuil : 3 tentatives consécutives → skip, SSE `activity.turn_skipped`.
- Reset complet au `next_round`.
- Tentative échouée : `parse_llm_json` retourne `None`, exception provider (timeout, HTTP error, etc.).

## 11. Schemaless & robustesse

- Tous les accès aux dicts via `.get()`, jamais d'indexation directe.
- Champs manquants → comportement dégradé documenté : `event=None`, `whisper=None`, section omise, etc.
- Raise explicite uniquement sur invariants techniques : `SessionNotFound`, `InstanceNotFound`.

## 12. Plan d'implémentation

| # | Étape | Livrable |
|---|-------|----------|
| 1 | `SessionState` + dict `_sessions` + `_get_session` | `engine.py` squelette |
| 2 | `activity/run` complet (sans SSE) | retour synchrone, persistance, test manuel via simcli |
| 3 | Endpoint SSE `activity/stream` | `routes.py` + réutilisation `http/sse.py` |
| 4 | `activity/give_turn` (thread + circuit breaker + SSE) | tour complet avec un joueur |
| 5 | `activity/next_round` + `activity/end` | transitions complètes |
| 6 | Dashboard MJ simweb | écran de pilotage connecté au SSE |
| 7 | Test bout-en-bout : lancer une instance, donner 3 tours, next_round, end | validation MJ |

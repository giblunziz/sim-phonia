# Backlog

Gestion des priorités : **HOT** > **WARM** > **COLD** > **FROZEN** > **DONE**.
Une entrée ne passe en `DONE` qu'après validation de l'utilisateur (tests manuels OK).

## HOT

### H1 — Modélisation des entités cardinales (pydantic + collections MongoDB)

- Schéma `Character` aligné sur `.working/antoine.json` (identité, appearance, background, flaws, psychology.transactional, psychology.insight, values, relationship, game.phobia/secret/prior_knowledge, memory.slots)
- Schéma `PerceptionEntry` aligné sur `.working/antoine_manon_cross.json` : `from`, `about`, `scene`, `activity`, `category`, `value`, `ts` — append-only
- Schéma `Activity` aligné sur `.working/insight_20260410_2338.json` : `events[]`, `mj[]`, `exchanges[]`, `debrief[]`, `stats`
- **Catégories de perception figées** : `perceived_traits` / `assumptions` / `approach` / `watchouts` + `about: "self"`
- **Visibilité figée** sur `exchange.response` : `talk` / `actions` / `body` / `mood` = public ; `inner` / `noticed` / `expected` / `memory` = privé

### H2 — Bus `mj` (game-flow)

- Commande `mj/give_turn(activity_id, target, instruction)` → append dans `activity.mj[]`
- Commande `mj/next_round(activity_id, instruction)`
- Commande `mj/end_activity(activity_id)`
- Invariants : `activity.mj[]` est append-only horodaté ; transitions cohérentes avec `max_rounds`

### H3 — `memory_service` (MongoDB + ChromaDB)

- Adapter MongoDB : CRUD `characters`, `perceptions`, `activities`
- Adapter ChromaDB : indexation append-only des `perceptions` (embeddings par entrée)
- Bus `memory` : commandes `record(entry)`, `query(from, about, context)`
- **Autorisation via `from`** : filtrer les résultats à ce que ce joueur peut légitimement connaître (ses propres perceptions + publics de sa scène, jamais la fiche d'un autre)

### H4 — Façade MCP (tool accessible au LLM joueur)

- Exposer `memory.query(from, about, context)` en tool MCP (via `simphonia`, agent MCP **unique**)
- Chaîne d'appel cible : `LLM → simphonia (MCP) → memory_service → shadow_memory_service → response`
- Prompt système à injecter dans chaque LLM joueur : indication d'usage du tool, contrainte de ne pas inventer d'infos sur les autres

### H6 — Moteur de tour de joueur (boucle agentique tool-use)

- Orchestrateur : `prompt → tool_call* → final_response` avec borne d'itérations configurable
- Output structuré conforme au schéma `exchange.response` (function-calling / structured output)
- Abstraction provider-agnostique : interface commune, `OllamaProvider` en premier (défaut), `ClaudeProvider` / `OpenAIProvider` ensuite
- Capability flag `tool_use` sur le provider/model → refuser modèles non compatibles

## WARM

### W1 — Compression mémoire (recaps)

- Mécanisme de recap quand `memory.slots` du perso sature
- Intégrer au schéma `Activity.stats.recaps` déjà prévu

### W2 — Debrief post-activité orchestré

- Bus `mj/debrief(activity_id)` qui pilote un tour de réflexion par joueur
- Persistance des `debrief[]` et mise à jour automatique de la cross-knowledge (catégorie `self` incluse)

### W3 — Concepts Scene / Session

- Formaliser la `scene` au-delà d'un simple string (participants de la scène, props, contraintes narratives)
- Grouper plusieurs activités dans une `session`

## COLD

### 🔧 INFRA — Cascades + validation startup + smoke E2E

Spec dans `documents/simphonia.md` § *Services cascadés*. Prérequis historique de `shadow_memory_service` (H5.c) — gelé conjointement avec H5.

| # | Étape | Livrable |
|---|-------|----------|
| **#11** | `@cascade` + `ShortCircuit` | Décorateur, exception, storage trié `(priority, discovery_order)` dans `BusRegistry` |
| **#12** | `Bus.dispatch` refactor | Pipeline `before* → call → after*`, injection `from_char` (par nom dans signature), gestion d'erreurs spécifiée |
| **#13** | Validation startup | Cascade orpheline → fail ; `mcp=True` sans `from_char` → fail |
| **#15** | Smoke test E2E | Bloqué sur #11/#12/#13 |

### H5 — `shadow_memory_service` + "psy"

Synthèse d'étude figée dans `documents/shadow_memory.md` (2026-04-17). Rôle, chaîne d'exécution, opacité, deux casquettes du psy (runtime + production) sont actés.

**Actions identifiées** :

- **H5.a — Agent `psy`** : nouveau PNJ avec fiche + system prompt dédié, branché sur l'infra providers (OpenAI/Claude) avec config par perso + fallback. Dev/proto en gemma4. Préalable : `character_service` porté.
- **H5.b — Collection shadow MongoDB** : spec du schéma d'entrée (point ouvert : calque `PerceptionEntry` avec catégorie spéciale vs schéma propre avec `intensity` / `source_event_id` / `last_reinforced_at`). Initialiser la collection + le process de sync mongo→chroma (collection dédiée, séparée de `knowledge`).
- **H5.c — `shadow_memory_service`** : service dédié exposant deux fonctions — `shadow_before_call` (cascade `memory/recall` before, réécrit la query via un appel au psy) et `shadow_after_call` (cascade `memory/recall` after, 2e RAG sur la collection shadow + fusion). Dépend de #11/#12 (cascades) et de H5.a.
- **H5.d — État "focus" unilatéral** : choisir la forme de stockage (poids vs typologie vs hybride), le déclencheur d'update (après événement notable), les règles de priorité multi-focus.
- **H5.e — Garde-fous coût LLM** : skip quand aucun focus actif sur la cible, cache par hash de query, rate-limit par tour — à benchmarker une fois la chaîne complète en place.
- **H5.f — Trigger de re-sync mongo→chroma** pendant le jeu : identifier l'événement déclencheur (fin d'exchange ? insert mongo ? commande explicite ?) et le câbler.

**Préalables bloquants** : #11/#12 (cascades, en COLD) + H1 (modélisation).

### 🎭 MJ — Dialog de lancement d'`activity_run` avec override `mj_mode`

Aujourd'hui `▶ Lancer` depuis `StorageInstancesPanel` appelle `activity/run(instance_id)` sans paramètre ; le run hérite de la préconisation `mj_mode` de l'instance (snapshot deep-copy immuable).

À terme : dialog pré-rempli depuis `instance.mj_mode`, override optionnel avant confirmation. Le `turning_mode` reste non-overridable (couplé aux règles et whispers scénarisés).

YAGNI V1. À réévaluer une fois les 3 modes MJ livrés et retour d'usage.

### 🤖 Résolution dynamique du fine-tune Ollama via `character.type`

Le même discriminant `character.type` qui filtre les tools MCP (livré 2026-04-22) pourrait piloter aussi la résolution du fine-tune LLM à utiliser.

**Convention de nommage** : `{base_model}_{type}` (séparateur `_`). Ex : `simphonia_player`, `simphonia_psy`, `simphonia_npc`.

**Découverte auto au boot** :

```
1. db.characters.aggregate([{$group: {_id: "$type"}}])  →  types réellement utilisés
2. Pour chaque type, vérifier que `{base_model}_{type}` existe côté Ollama (GET /api/tags)
3. Si présent  → resolver[type] = `{base_model}_{type}`
   Si absent   → resolver[type] = default_model  (+ warning log)
```

**Config YAML imaginée** :

```yaml
services:
  chat_service:
    base_model: simphonia           # préfixe commun
    default_model: simphonia_player # fallback si fine-tune spécifique absent
```

**Changement technique** : déplacer la résolution du provider de l'init statique (aujourd'hui `chat_service.init(model=...)` one-shot au boot) à chaque appel LLM via un helper `provider_registry.resolve_for(character_type)`.

**Scope** : `chat_service`, `activity_engine`. Pas `tools_service` (l'atelier utilise un model fixe neutre, cf. `gemma4-original`).

**Préalables** : aucun bloquant — `character.type` existe déjà, `provider_registry` aussi. Chantier self-contained, ~1 après-midi.

## FROZEN

_(vide)_

## DONE

### 2026-04-25 — 🧑 Mode `human-in-the-loop` — joueur humain dans une activité

Spec complète dans [`documents/human_in_the_loop.md`](./documents/human_in_the_loop.md). Brainstorm + 5 étapes incrémentales livrées en une session.

**Concept** : un participant désigné comme humain (`type: "human"` dans la fiche, ou override session via combo simweb) prend la place du LLM. L'`activity_engine.give_turn` détecte le tour humain, court-circuite l'appel LLM, publie un SSE `activity.input_required`, et attend une saisie via la commande `activity/submit_human_turn`. Cardinalité **0..1** par activité — un seul humain (l'utilisateur lui-même).

**Mécanisme transverse** — pas de service dédié, juste une bifurcation dans des pipelines existants.

**Back** :
- `core/errors.py` : `InvalidHumanSubmit`, `EmptyTurn`
- `services/activity_service/engine.py` :
  - `SessionState.human_player: str | None` + `pending_human_input: dict | None`
  - Helper `_resolve_human_player(char_svc, players, override)` — override session prime sur scan fiches `type=="human"`, warning si > 1, fallback `None`
  - `run(instance_id, human_player=None)` — résolution + persistance dans `instances.put` (pour reprise)
  - `resume()` restaure `human_player` depuis le doc Mongo (figé au démarrage, pas de re-résolution)
  - `_do_give_turn` : bifurcation HITL après persistance MJ, publie `activity.input_required` (payload minimal `{session_id, target, round}` — Q11), retour sans appel LLM
  - `submit_human_turn(session_id, target, to, talk, actions)` : validations (running, target match, pending non vide, talk/actions pas vides simultanément), wrapping `str → list[str]` côté stockage (préserve schéma exchange), `raw_response: null` (signature humaine), append history + persistance + SSE `activity.turn_complete` + hook MJ
- `services/activity_service/context_builder.py` : helper `_synthesize_raw_from_public(from_char, public)` — fallback dans `build_messages` quand `raw_response` absent (sinon les exchanges humains étaient invisibles dans le contexte des autres joueurs)
- `commands/activity.py` : signature `run(instance_id, human_player=None)` + nouvelle commande `submit_human_turn` (sans `mcp=True` — un LLM n'a aucune raison de l'appeler)

**Front simweb** :
- `api/simphonia.js` : `activityRun(instance_id, human_player)` étendu, `activitySubmitHumanTurn` ajouté
- `StorageInstancesPanel.jsx` : combo « Joué par humain » par ligne d'instance (`[— auto — / participant1 / …]`), state `humanPlayerByInstance` éphémère, grille élargie `minmax(280px, auto)` pour rendre la combo visible. Si `auto` → serveur scan les fiches.
- `ActivityDashboardPanel.jsx` : composant `HumanInputForm` en bas du dashboard (combo `to` stateful + 2 textareas `talk`/`actions`), activé sur SSE `activity.input_required`, désactivé sur `turn_complete`. Auto-déclenche `mj.next_turn` après envoi **uniquement** si `mj_mode === 'human'` (en `autonomous`, le MJ LLM enchaîne déjà via son hook `on_turn_complete`)

**Doc** :
- `human_in_the_loop.md` créé (Description / Cahier des charges / 12 décisions Q1-Q12 / Plan 5 étapes)
- `activity_engine.md` mis à jour : §3 commandes (run + human_player, submit_human_turn), §4 SessionState (champs HITL), §6 give_turn (étape 8 bifurcation), §9 SSE (input_required, started/resumed enrichis avec human_player)
- `CLAUDE.md` index Spécifications

**Tests** : 30 TU verts répartis en 2 fichiers
- `test_engine_human_player.py` (11) — `_resolve_human_player` : override valide, résolu via `get_identifier`, override prime sur scan, override invalide + fallback, scan multi-humains avec warning, scan sans humain, edge cases (string vide, players vide)
- `test_engine_human_submit.py` (19) — bifurcation `_do_give_turn` (publie input_required, persiste instruction MJ avant bifurcation, résolution identifier, payload minimal sans whisper/event), `submit_human_turn` happy path (wrapping, identifier, talk seul, actions seul, to spécifique, to=all par défaut), erreurs (session introuvable, ended, target ≠ human_player, pas de pending, empty turn whitespace), intégration context_builder (synthesize_raw_from_public, exchange humain visible côté Antoine, role assistant côté Valère)

Suite complète : 200/200 verts, zéro régression. Build simweb OK.

**Propriétés** :
- Type `human` dans `character_service` déjà existant (livré 2026-04-22) — aucune modif de ce service nécessaire
- `chat_service` non touché — son flag `human` ad-hoc reste pour les tests dev (le « vrai » 1-to-1 est une activité à 2 joueurs)
- `raw_response: null` côté exchange humain est sémantique — le helper `_synthesize_raw_from_public` génère le format LLM-équivalent au moment de la lecture, pas du stockage. Aucune fausse signature LLM en base.
- Pas de timeout — l'activité attend indéfiniment la saisie humaine (l'humain n'est pas un signal d'échec)
- Form `to` stateful sur la session UI (init `"all"`, modifiable, conservé entre exchanges, reset au lancement/reprise) — pas de cookie/localStorage cross-activité
- Auto `mj.next_turn` après submit en mode MJ humain : confort UI sans coût (si l'auto échoue, le bouton ▶ Next reste accessible manuellement)

**Bug fix en cours de validation** : les exchanges humains n'apparaissaient pas dans le contexte des autres joueurs (`build_messages` lisait `raw_response` qui était `null`). Corrigé par `_synthesize_raw_from_public` qui reconstruit un JSON équivalent depuis le `public` de l'exchange.

**Validation E2E** : Valère désigné humain via combo Storage, bifurcation `give_turn`, form HITL activé via SSE, saisie + envoi → exchange visible des autres joueurs LLM, auto-give_turn enchaîne sur le suivant en mode MJ humain.

**Validation utilisateur** : OK 2026-04-25.

---

### 2026-04-24 — 🧠 `shadow_storage` — capture passive du subconscient des joueurs (T1→T8)

Spec complète dans [`documents/shadow_storage.md`](./documents/shadow_storage.md). Plan T1→T8 livré.

**Concept** : alimentation **passive** d'une collection `subconscient` (Mongo + ChromaDB) via le nouveau bus `messages` + un mécanisme **observer pattern** sur le `Bus` core. Aucune modif fonctionnelle dans `activity_service` / `chat_service` — juste un fan-out fire-and-forget après parsing LLM. Préalable matériel pour Tobias runtime (H5 — la cognition se nourrira de ce subconscient).

**Distinction `subconscient` vs `psy_memory`** :
- `subconscient` (livré aujourd'hui) — matière brute par joueur, alimentée passivement
- `psy_memory` (à venir avec H5) — analyses/scores écrits par Tobias en relisant le subconscient

**Back** :
- `core/bus.py` : `Bus.subscribe(listener)` + fan-out post-callback dans `dispatch()`, isolation best-effort des exceptions listener (callback exception ≠ subscriber exception)
- `commands/messages.py` : bus `messages` + commande no-op `published` (sert de canal nommé pour le pub/sub)
- `services/activity_service/engine.py` : helper `_publish_messages("activity", slug, exchange)` après `_build_exchange()`
- `services/chat_service/strategies/default_strategy.py` : helper `_publish_messages(from_char, data)` après `json.loads` réussi (perdu si fallback texte brut, par construction)
- `services/shadow_storage/` : ABC `ShadowStorageService` + factory + `MongoShadowStorage` (Mongo + Chroma + embedder `paraphrase-multilingual-MiniLM-L12-v2` dédié, denylist `excluded_keys` configurable YAML, schemaless `_extract_candidates` avec déballage des wrappers `private`/`public`, push atomique Mongo→Chroma, `resync_chroma` full rebuild)
- `commands/shadow_storage.py` : 5 commandes bus (`entries.list/get/update/delete`, `chroma.resync`) — admin/UI uniquement, aucun `mcp=True`
- `bootstrap.py` : `shadow_storage.init(section)` après discovery, auto-subscribe sur les bus listés dans YAML `subscriptions: [messages]`
- `simphonia.yaml` : section `services.shadow_storage` complète (strategy, mongo URI, collection `subconscient`, chroma collection `subconscient`, subscriptions, excluded_keys)

**Front simweb** :
- `api/simphonia.js` : 5 endpoints `shadowEntriesList/Get/Update/Delete` + `shadowChromaResync`
- `components/tobias/ShadowDataPanel.jsx` : header (Refresh + Resync Chroma), filtres `bus_origin` (hardcodé `["activity", "chat"]`) + `from_char` (peuplé via `character/list`), table colonnes `from / bus_origin / ts / preview / actions`, pagination 50/page, click ligne → modale lecture (fermable au backdrop), modale édition `JsonEditor` (fermeture explicite uniquement, pas de perte accidentelle), delete confirmé, resync Chroma confirmé
- `components/Sidebar.jsx` : nouvelle rubrique **Tobias** + sous-item **Subconscient**
- `App.jsx` : route vers `ShadowDataPanel`
- `index.css` : section *Tobias / Subconscient* + composants réutilisables (`.modal*`, `.alert-error/info`, `.btn-icon`, `.json-pre`)

**Tests** : 44 TU verts répartis en 3 fichiers
- `test_bus_subscribe.py` (18) — subscription basics, fan-out, isolation des erreurs, ordre callback/listener
- `test_messages_bus.py` (7) — registration, no-op, fan-out
- `test_shadow_storage.py` (19) — `_extract_candidates` schemaless, filtre admission, embedding text déterministe, init/subscribe, get guard

Suite complète : 159/160 verts (1 KO pré-existant `test_exact_four_categories` lié à l'ajout de `presentation` dans `MEMORIZE_CATEGORIES`, hors scope).

**Propriétés** :
- Engine/chat ignorent l'existence de Tobias — ne savent même pas qui écoute
- Schemaless de bout en bout — les producteurs émettent leur format, le shadow filtre ce qu'il sait extraire
- Denylist plutôt qu'allowlist → tout nouveau champ d'exchange est admis automatiquement
- Update payload n'auto-resync pas Chroma (compromis perf — bouton manuel)
- Listeners synchrones, exceptions isolées (un listener KO n'impacte ni le dispatch ni les autres)

**Validation E2E** : collection Mongo `subconscient` se remplit en temps réel à chaque tour de jeu (activity ou chat). Filtres + édition + delete + resync Chroma vérifiés côté UI.

**Dette technique notée** : embedder SentenceTransformer chargé deux fois au boot (`memory_service` + `shadow_storage`) → ~840 Mo RAM + ~10s cold start. Mutualisable plus tard via un `embedder_service` partagé. À scheduler quand un 3e service en aura besoin (futur `psy_memory` typiquement).

**Validation utilisateur** : OK 2026-04-24.

---

### 2026-04-23 — 🛠️ `tools_service` — atelier one-shot piloté par LLM (port modernisé de `run_task.py`)

Spec complète dans [`documents/tools_service.md`](./documents/tools_service.md). Plan T1→T9 livré.

**Concept** : atelier de préparation de données hors scénario, hors session, hors bus applicatif. Double boucle `sources × subjects`, outputs `.txt` dans `./output/<task_slug>/<YYMMDD_HHMMSS>/`. MongoDB-first — fini les fichiers de vérité.

**Back** :
- `services/tools_service/` : ABC + factory + singleton + `MongoToolsService` (lecture `task_collection` avec `$project _id:1`, CRUD `tasks`, lecture schemaless des documents des collections exposables)
- `services/tools_service/builder.py` : `build_tools_system_prompt(source, subject?, schema?)` — format minimaliste SOURCE / SUBJECT / schéma, déconnecté de `context_builder` (trop riche pour l'atelier)
- `services/tools_service/runner.py` : moteur thread background, progress state in-process, `skip_self`, best-effort erreurs par cellule, `_run.meta.json` en fin de run
- `commands/tools.py` : 9 commandes bus `tools/*` (aucune MCP — atelier non accessible aux LLM incarnés)
- `simphonia.yaml` : section `services.tools_service` (model, collections, output_dir)
- `bootstrap.py` : `tools_service.init(...)` après les autres services

**Front** :
- `api/simphonia.js` : 9 endpoints (`toolsListCollections`, `toolsListIds`, `toolsGetDocument`, `toolsTasksList/Get/Put/Delete`, `toolsRun`, `toolsStatus`)
- `components/tools/ToolsPanel.jsx` : task top (dropdown + slug + prompt + temperature + Save) + 2 colonnes source/subject avec checkbox-listes + Refresh + dropdown schéma + checkbox `Skip self` + Run + progress bar + cells log
- `components/Sidebar.jsx` : rubrique *Atelier* → *Tools*
- `App.jsx` : route vers `ToolsPanel`
- `index.css` : styles `.tools-id-list`, `.tools-progress`, `.tools-cells`

**Tests** : 7 TU verts sur `builder.py` (`tests/test_tools_builder.py`) — cas source seul, source+subject, cohérence subject_id/subject_doc, schéma payload dict/str, ordre SOURCE>SUBJECT>schéma, absence de bloc schéma.

**Propriétés** :
- Fallback safe : fiche absente → erreur cellule ciblée, run continue
- `skip_self` par défaut — filtre `source_id == subject_id`, décochable
- Aucun tool MCP injecté côté LLM (1 seul aller-retour, pas de boucle tool-use)
- Documents source/subject injectés tels quels (schemaless, zéro filtre PRIVATE/PUBLIC)
- Polling via `tools/status` toutes les 1s — pas de SSE ni bus scénario
- Runs en mémoire, pas de persistance cross-process

**Validation E2E** :
- Phase 1 presentations : `./output/presentation/20260422_235955/`
- Phase 2 cross-analyse : `./output/cross-analyse/20260423_000452/` (incluant `diane_vera.txt`)

**Validation utilisateur** : OK 2026-04-23.

---

### 2026-04-23 — 💬 chat simple : scène optionnelle + composition via `context_builder`

Le StartScreen du chat (outil de test) devient cohérent avec le pipeline de l'`activity_engine` : même fonction de composition du system prompt, mêmes sources de vérité (scène + knowledge + fiche).

**Back** :
- `context_builder.build_system_prompt` — `instance` / `activity` / `scene` tolèrent `None`. Si `activity is None`, la section "Règles du jeu" est entièrement omise (plus de warning `rules.players absent`). Usage hors activity_engine officialisé.
- `chat_service/types.py` — `DialogueState.scene: dict` ajouté, résolu 1 seule fois au `start`.
- `chat_service/strategies/default_strategy.py` :
  - `_build_system_prompt` délègue à `context_builder.build_system_prompt(player=to, activity=None, scene=state.scene, character=to_card, knowledge_entries=<list_knowledge(from=to)>)`
  - Knowledge chargés à chaque tour via `character_storage.get().list_knowledge(filter={"from": responder})` — continuité avec les `memorize` du jeu principal
  - Suffixé par `interlocutor` + `_TALK_SCHEMA` hardcodé (schéma `{talk}` propre au chat simple, YAGNI system_schemas)
  - `start(..., scene_id=None)` : résout via `activity_storage.get().get_scene(scene_id)` + stocke dans `state.scene` ; `reply` / `auto_reply` utilisent `state.scene`
- `chat_service/__init__.py` — ABC `start` avec `scene_id`
- `commands/chat.py` — `start_command` avec `scene_id`

**Front** :
- `api/simphonia.js::chatStart(..., sceneId=null)`
- `StartScreen.jsx` — select scène optionnel peuplé via `sceneList()`, option "— aucune —" en tête, fail-silent si fetch KO

**Propriétés** :
- Chat simple sans scène → comportement identique à avant (pas de régression)
- Chat simple avec scène → section `## Scène` + knowledge + fiche dans le system prompt, interlocutor + schéma `{talk}` en suffixe
- Un personnage gagne en continuité de persona entre activités et chat simple (mêmes knowledge injectés)
- Le schéma `{talk}` reste hardcodé côté chat_service (YAGNI refacto vers schemas activity_storage)
- Le system prompt en saisie a été écarté (YAGNI)

**Validation utilisateur** : OK 2026-04-23.

---

### 2026-04-22 — 🎭 `character.type` (player|npc|human) + filtre MCP dynamique

Nouveau discriminant de nature sur les fiches, consommé par les pipelines MCP pour filtrer les tools exposés au LLM incarné.

**Back** :
- `services/character_service` : constantes `CHARACTER_TYPES = ("player", "npc", "human")` + `DEFAULT_CHARACTER_TYPE = "player"`, méthode concrète `CharacterService.get_type(name) -> str` sur l'ABC (fallback safe triple : `CharacterNotFound` / attribut absent / valeur hors whitelist → `player`)
- `commands/character.py` : commande `character/types` → `list[str]`
- `services/activity_service/context_builder.py` : `get_tools(activity, role="player")` — param `role` ajouté (forward à `mcp_tool_definitions`)
- `services/activity_service/engine.py::_do_give_turn` : `role = char_svc.get_type(slug)` → propagé à `mcp_tool_hints` + `get_tools`
- `services/chat_service/strategies/default_strategy.py` :
  - `_build_system_prompt(to_card, from_char, human, role)` : param `role` ajouté
  - `_get_mcp_tools(role)` : param `role` ajouté
  - `_call_llm` : dérive `role = character_service.get().get_type(from_char)` quand `from_char` fourni
  - 3 callers (`start` / `reply` / `auto_reply`) : calculent `to_role` / `speaker_role` / `other_role` via `get_type()` et le passent

**Front simweb** :
- `api/simphonia.js` : `getCharacterTypes()` dispatch `character/types`
- `StorageCharactersPanel.jsx` : `<select>` peuplé dynamiquement depuis le back en mode édition/création. Option "— non défini (défaut : player) —" en tête → attribut `type` **supprimé** du JSON au save (cohérent schemaless). Les 3 options back renvoyées sont affichées ensuite. Fallback silencieux si `character/types` KO (log console + select réduit à l'option vide).

**Propriétés** :
- Aucune régression : toute fiche sans `type` → fallback `player` → comportement identique
- Fiche `type="npc"` → `mcp_tool_definitions(role="npc")` retourne `[]`, le LLM incarné ne reçoit ni tools ni hints narratifs
- Fiche `type="human"` → idem (pas encore court-circuité au niveau moteur LLM — point ouvert)
- Façade MCP SSE externe (`facade/server.py`) non touchée : expose toujours `"player"` sur `/sse` et `"mj"` sur `/sse/mj` (consommation externe type Claude Desktop)

**Validation utilisateur** : OK 2026-04-22.

---

### 2026-04-18 — C1 `chat_service` (providers + sessions de dialogue 1-to-1)

Spec : [`documents/chat_service.md`](./documents/chat_service.md). Étapes 1-6 validées 2026-04-18.

- Providers LLM portés (`ollama` + `anthropic`) dans `src/simphonia/providers/`
- `provider_registry` — factory + `init/get` depuis config YAML `providers:`
- Squelette `chat_service` (ABC + `DialogueState` + start/reply/stop)
- Logger fichier `/logs/chat.log` (reset au boot)
- Commandes bus `chat` + câblage bootstrap
- Génération LLM + schéma JSON `{talk:[...]}` dans system prompt

**Étape 7 (façade MCP) sans objet** : l'expo auto des `@command(mcp=True)` couvre déjà les tools consommés par le LLM incarné (`memory/recall` + `memory/memorize`). Les commandes `chat/*` sont du pilotage client, pas des tools LLM.

---

### 2026-04-20 — 🧠 `memory/memorize` — push live Mongo+Chroma avec dédup sémantique (10 étapes complètes)

Spec : [`documents/memory_service.md`](./documents/memory_service.md) (sections `memorize`, décisions, plan §10). Mini-backlog intégralement `DONE`.

**Architecture livrée** :
- ABC `MemoryService.memorize(from_char, notes, activity, scene) -> dict` — contrat symétrique de `recall`
- `chroma_strategy.memorize` — embed unique réutilisé, dédup sémantique `where=(from, about, category)` seuil `dedup_threshold=0.2`, push atomique Mongo (via `character_storage.push_knowledge`) puis ChromaDB (réutilise `_id`/`ts` Mongo). Zéro exception levée — chaque note traitée indépendamment, erreurs reportées dans `details[]`.
- Commande bus `memory/memorize` avec `mcp=True, mcp_role="player"`, JSONSchema array sur `notes` (`minItems: 1`), enum `category` ∈ `[perceived_traits, assumptions, approach, watchouts]`, `mcp_description` rédigé pour donner l'agentivité au LLM
- Façade MCP `/sse` : exposition auto via `list_mcp_commands(role="player")` + spécial-case markdown via `format_memorize_markdown` (helper réutilisable)
- `SessionState.memorize_log: dict[str, list[str]]` (activity_engine) et `DialogueState.memorize_log` (chat_service) — trace par speaker des markdowns de confirmation
- `context_builder.build_messages` + `chat_service._build_messages` ré-injectent « ## Tes mémorisations récentes » au début du prompt à chaque tour — cohérence narrative, évite le « mémorise et oublie »
- Config YAML `services.memory_service.dedup_threshold: 0.2` (cosine distance)
- 12 TU nouveaux (97 total) — format markdown, dispatch command, catégories figées, tool_executor activity_engine (append log, accumulation multi-calls), context_builder injection (ordre whisper → memorize_log → historique)

**Validation E2E** :
- Isabelle mémorise simultanément `perceived_traits` sur elle-même + `approach` sur Louis en un seul appel (multi-notes via `notes: []`)
- Formulation 1re personne respectée (« Ma volonté s'efface devant la sienne », « Pour regagner sa faveur, je dois prouver une discipline exe[mplaire] »)
- Déclenchement initial via whisper MJ (pertinent), puis reformulation utilisateur du `mcp_description` pour favoriser les triggers spontanés

**Hors scope V1 (backlog COLD)** :
- Weight / boost de confirmation sémantique (zone moyenne)
- Flag `contradicted_by` pour observations opposées
- Enforcement serveur « 1 appel memorize par tour » (auto-discipline LLM pour l'instant)
- Rate-limit `N notes / tour`

**Validation utilisateur** : OK 2026-04-20.

---

### 2026-04-21 — 🎯 `mcp_hint` + groupes narratifs `register_mcp_group(bus, role)`

Correction d'un missing piece identifié après E2E `memorize` : les LLM incarnés ne déclenchaient pas spontanément `recall`/`memorize` sans un hint explicite dans leur system_prompt. Hard-code transitoire ajouté dans `chat_service._build_system_prompt` et `activity_engine._do_give_turn`, puis généralisé proprement.

**Architecture** :
- `Command.mcp_hint: str | None` — texte narratif « quand/pourquoi » activer le tool, côté expérience subjective du personnage
- `@command(..., mcp_hint="...")` — validation decoration-time, rejet si `mcp=False`
- `MCP_ROLES = {"player", "mj", "npc"}` — ajout du `"npc"` pour préparer les futurs PNJ intelligents (backlog Aurore, Lorenzo)
- `core/mcp.py::McpGroup` + `register_mcp_group(bus, role, intro, outro)` + `get_mcp_group` + `mcp_tool_hints(role)` : compose intro + hints des commandes du groupe + outro, séparateur `\n\n---\n\n` entre groupes `(bus, role)`
- `commands/memory.py` : `register_mcp_group(memory, player, intro=..., outro=...)` + `mcp_hint` sur `recall_command` et `memorize_command`
- Consumers nettoyés : `chat_service._build_system_prompt` + `activity_engine._do_give_turn` remplacent leur hard-code par `mcp_tool_hints(role="player")` préfixé au system_prompt
- 12 TU nouveaux (109 total) — attribut, validation, registration (retrieve/overwrite warning), composition (single/no-group/no-hints/empty/filter-role/multi-bus)

**Propriétés** :
- Source unique : le texte narratif vit avec la commande (`mcp_hint`) et le contexte thématique (`register_mcp_group`)
- Extensible : ajouter un futur bus `actions` / `shadow` / `npc` = nouvelles commandes + groupe, **aucune modif consumer**
- Multi-audience : la clé `(bus, role)` supporte 3 façades MCP à terme (player, mj, npc)

**Validation utilisateur** : OK 2026-04-21.

---

### 2026-04-20 — 🎭 `mj_service` + port Beholder autonome (8 étapes complètes)

Spec : [`documents/mj_service.md`](./documents/mj_service.md). Mini-backlog §10 entièrement DONE.

**Deux axes orthogonaux livrés** :
- `mj_mode` ∈ `human` | `autonomous`
- `turning_mode` ∈ `starter` | `named` | `round_robin` | `next_remaining` | `random_remaining` | `random`

**Couches livrées** :
- `services/activity_service/turning_modes.py` — 6 helpers purs + `TurningMode(StrEnum)` + dispatch (38 TU)
- `services/mj_service/` — ABC `MJService` (4 hooks : `on_session_start` / `on_turn_complete` / `on_next_turn` / `on_session_end`), factory runtime `build_mj_service(mode)`, stratégies `HumanMJ` (preview SSE `mj.next_ready`) + `AutonomousMJ` (briefing initial, boucle tool-use, safety guard `max_iter = max(max_rounds×10, 30)`, SSE `mj.thinking` + `mj.decision`)
- `commands/mj.py` — orchestrateur générique `mj/next_turn(session_id)` : `give_turn` / `next_round` / `end` selon `turning_mode` (utilisé par bouton ▶ Next humain ET en raccourci par MJ autonome)
- `core/command.py` + `core/decorators.py` + `core/mcp.py` — attribut `mcp_role` ∈ {`player`, `mj`} sur `@command`, validation décoration-time, `list_mcp_commands(role=...)` filtré
- `facade/server.py` — refactor en 2 endpoints SSE (`/sse` player + `/sse/mj` MJ), dispatch générique via bus, fallback markdown pour `recall`
- `commands/activity.py` — `give_turn`/`next_round`/`end` exposés en `mcp=True, mcp_role="mj"` au LLM MJ
- `activity_service/engine.py` — instanciation `mj_service` à `run`/`resume`, hooks `_notify_mj_session_start` / `_notify_mj_turn_complete` / `_notify_mj_session_end` (best-effort)
- `simweb` — `StorageInstancesPanel` (turning_mode 6 valeurs réelles, select `mj_mode`, action ⎘ Duplicate avec slug obligatoire), `ActivityDashboardPanel` (colonne `mj_mode` dans RunsList, bouton `▶ Next` step-by-step + label preview « Prochain : X »)
- Migration silencieuse : `player_rules` → `rules.players` (audit 4 couches conformes dès le départ, seul `context_builder` à patcher)

**Validation E2E** :
- 85 TU verts (turning_modes 38 + mj_service 11 + engine_hooks 9 + mj_command 6 + autonomous_mj 7 + mcp_roles 12 + chat retro 2)
- Run autonomous validé sur louis/isabelle round_robin : 8 iterations en 3min23, `end()` décidé par le MJ lui-même (pas safety guard), conversation continue gérée par le provider

**Reste en COLD (YAGNI V1)** : dialog de lancement avec override `mj_mode` au run.

**Validation utilisateur** : OK 2026-04-20.

---

### 2026-04-20 — simweb : action ⎘ Duplicate sur `StorageInstancesPanel` (W4)

- Bouton ⎘ par ligne d'instance → deep-copy via `entryToForm`, slug reset, formulaire en mode création
- Validation slug : `required` HTML5 + `aria-invalid` + label « ⚠ requis » + bordure danger sur l'input quand soumission échoue, clear automatique à la saisie
- Cas d'usage : dériver rapidement une variante (ex: même config mais `mj_mode=autonomous` au lieu de `human`)
- Validation utilisateur : OK 2026-04-20.

---

### 2026-04-19 — Audit refactor : source unique MCP + RunState + confirm delete conditionnelle

**1. Source unique pour les tool definitions MCP**

- `src/simphonia/core/mcp.py` : helpers `list_mcp_commands()`, `to_tool_definitions()`, `mcp_tool_definitions()` — parcourent `BusRegistry`, filtrent `mcp=True`, retournent le format provider-agnostic `{name, description, parameters}` consommé par `AnthropicProvider` / `OllamaProvider` / façade MCP.
- `core/__init__.py` : re-export des trois helpers.
- `activity_service/context_builder.py` : `_TOOL_MEMORY_RECALL` et `_ALL_TOOLS` supprimés. `get_tools(activity)` délègue à `mcp_tool_definitions()` (paramètre `activity` conservé pour futur filtrage par allowlist).
- `chat_service/default_strategy.py::_get_mcp_tools` : délègue au helper.
- `facade/server.py` : utilise `list_mcp_commands()` — conserve son schema patching `from_char` local.
- `activity_service/engine.py::_make_tool_executor` : fallback `"memory/recall"` supprimé (le helper n'émet que `"recall"`, aligné sur `cmd.code`).
- **Reste à faire (ticket séparé)** : généralisation des `_make_tool_executor` (3 implémentations hard-codent encore `if name == "recall"`). Requiert un formatter par commande côté service.

**2. `RunState(StrEnum)` + `TURN_STATUS_PENDING` dans `activity_service/engine.py`**

- Enum `RunState` avec `RUNNING` / `ENDED` — `StrEnum` (Python 3.11+) pour sérialisation JSON/BSON transparente et comparaison directe avec strings reçues de l'extérieur.
- Constante `TURN_STATUS_PENDING = "pending"` — sémantique distincte (retour async de `give_turn`, pas un state de session).
- 7 littéraux remplacés dans `engine.py` (dataclass default, `run_data`, `resume`, `end`, retour `give_turn`).
- Renommage `SessionState` → `RunState` pour éviter la collision avec le dataclass `SessionState` existant ; cohérent avec `run_id` / `activity_runs`.
- Front simweb non touché : les strings réseau restent identiques.

**3. simweb — confirmation delete knowledge conditionnelle**

- `ActivityDashboardPanel.jsx::handleDelete` : la seconde confirmation "Supprimer également les knowledge associés à ... ?" n'apparaît que si `run.exchange_count > 0`. Sinon `withKnowledge = false` direct, suppression du run sans question superflue.

Validation utilisateur : OK 2026-04-19.

---

### 2026-04-19 — Dashboard MJ v2 (révision complète)

- **Storage > Instances** : bouton ▶ Lancer par ligne → `activityRun` + navigation vers Dashboard.
- **Dashboard MJ** : liste `activity_runs` (agrégation MongoDB, tri `ts_updated: -1`), colonnes `_id / activity / state / échanges / scene / ts_updated / current_round / max_round / actions`. Colonne échanges calculée via `$addFields { exchange_count: $size $exchanges }`. Scroll via `main-content { overflow-y: auto }`.
- **Reprise** : `activity/resume(run_id)` reconstruit `SessionState` complet depuis MongoDB (exchange_history pré-peuplé), nouveau `session_id` UUID, même `run_id`.
- **Delete** : double confirmation — suppression optionnelle des `knowledge` liés (`character_storage/knowledge.delete_by_activity`), puis suppression du run.
- **Backend** : `CharacterStorageService.delete_knowledge_by_activity` (ABC + MongoDB), commande bus `knowledge.delete_by_activity`.
- **Layout scroll** : `main-content { overflow-y: auto }` — admin panels scrollent via le conteneur parent ; mj-dashboard (`overflow: hidden`) gère son propre scroll interne.
- Validation utilisateur : OK 2026-04-19.

---

### 2026-04-19 — `activity_engine` + `activity_runs` + Dashboard MJ v1

- **`core/errors.py`** : `InstanceNotFound` ajouté.
- **`services/activity_service/engine.py`** : orchestrateur de session — `SessionState` (dataclass), `run()` / `give_turn()` (thread non-bloquant) / `next_round()` / `end()`. Circuit breaker (3 retries par speaker/round), persistance `activity_runs` à chaque mutation.
- **`services/activity_storage/`** : 4 nouvelles méthodes ABC + implémentation MongoDB (`list_runs/get_run/put_run/delete_run`), collection `activity_runs` configurée dans `simphonia.yaml`.
- **`commands/activity.py`** : 4 commandes bus `activity/run`, `activity/give_turn`, `activity/next_round`, `activity/end`.
- **`http/routes.py`** : endpoint SSE `GET /bus/activity/stream/{session_id}`.
- **`services/activity_service/context_builder.py`** : `build_system_prompt` étendu avec `system_schemas: list[dict]` — injecte les schémas JSON activés dans le system prompt.
- **`logging.yaml`** : handler `file_activity` + logger `simphonia.activity` (console + fichier).
- **simweb — Dashboard MJ v1** : `ActivityDashboardPanel.jsx` — sélection d'instance → session MJ (SSE, instruction textarea, boutons joueurs, historique exchanges avec public/private/whisper). `SkippedCard` + `ExchangeCard`. Sidebar section "Jeu".
- **simweb — `StorageInstancesPanel.jsx`** : liste ordonnée de joueurs avec drag-and-drop natif (`PlayerOrderList`) remplace les checkboxes.
- **`index.css`** : styles dashboard complets, fix layout scroll (chain `flex: 1; min-height: 0`).
- Fixes : provider resolution dict vs list, messages vides (fallback "C'est ton tour"), `has_schema` corrigé vers `system_schemas`, whisper transmis dans SSE.
- Validation utilisateur : OK 2026-04-19.

---

### 2026-04-19 — ACB `activity_context_builder`

- `format_exchange(speaker, raw_response)` — markdown public-only, `mood` public, `inner_thought` privé.
- `build_system_prompt(player, instance, activity, scene, character, knowledge_entries, system_schemas)` — ordre : schema JSON > scène > règles > knowledge > fiche personnage.
- `build_messages(player, instance, exchange_history, ...)` — amorce > event > whisper > historique > instruction MJ.
- `get_tools(activity=None)` — retourne `[memory/recall]` en format provider-agnostic.
- `src/simphonia/utils/parser.py` — port de `parse_llm_json` depuis Symphonie.
- Spec dans `documents/activity_context_builder.md`.
- Validation utilisateur : OK 2026-04-19 (validé via activity_engine opérationnel).

---

### 2026-04-19 — Instances d'activité + providers/list + simweb Storage

- **`commands/providers.py`** : bus `providers`, commande `list` → `provider_registry.list_names()`.
- **`activity_storage`** étendu : collection `activity_instances`, 4 commandes `instances.list/get/put/delete`.
- **`simphonia.yaml`** : `activity_instances: activity_instances`.
- **simweb — Storage > Instances** : formulaire complet — activité/scène/providers (selects), joueurs (checkboxes), starter (select dynamique sur les joueurs sélectionnés), max_rounds/temperature/turning_mode, amorce (`MarkdownEditor`), events[] (round + textarea), instructions/whispers[] (round + destinataire toggle personnage/position + textarea).
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — Référentiel scènes + simweb Storage

- **`activity_storage`** étendu : collection `scenes` (list/get/put/delete), `scenes_collection` dans factory + YAML.
- **`commands/activity_storage.py`** : 4 commandes `scenes.list/get/put/delete`.
- **simweb — Storage > Scènes** : slug, description (courte, text input), contenu scène (`MarkdownEditor`).
- **simweb — Storage > Activités** : champ `scene` retiré (la scène appartient à l'instance, pas au template).
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — Référentiel activités + schémas + simweb Storage

- **`services/activity_storage/`** : ABC `ActivityStorageService` + factory + singleton. Collections `activities` et `schemas`. Stratégie `mongodb_strategy` — upsert via `$setOnInsert` (ts_created) / `$set` (ts_updated), `_id` = slug utilisateur, `datetime → ISO-8601`.
- **`commands/activity_storage.py`** : 8 commandes sur le bus `activity_storage` (`activities.list/get/put/delete`, `schemas.list/get/put/delete`). Pas de MCP.
- **`simphonia.yaml`** : section `activity_storage` (collections `activities` + `schemas`).
- **`bootstrap.py`** : `activity_storage.init()` après `character_storage`.
- **simweb — Storage > Activités** : formulaire complet (slug, label, description, scène, règles MJ + Joueurs en `MarkdownEditor`, prompts système avec select schéma, winning mode avec deck de cartes, debrief avec select schéma).
- **simweb — Storage > Schémas** : grille + formulaire (slug, prompt textarea, payload `JsonEditor`).
- **`MarkdownEditor.jsx`** : composant réutilisable — textarea monospace + aperçu rendu (`react-markdown`), bascule Éditer/Aperçu.
- **`JsonEditor.jsx`** : composant réutilisable — textarea monospace + validation JSON live + bouton Formater + indicateur ✓/erreur.
- **`react-markdown`** ajouté aux dépendances `simweb`.
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — `character_storage` + refactor + `memory/resync` + simweb Storage

- **`services/character_storage/`** : ABC `CharacterStorageService` + factory + singleton. Stratégie `mongodb_strategy` (CRUD `characters` + `knowledge`, sérialisation `ObjectId → str`, `datetime → ISO-8601`).
- **`commands/character_storage.py`** : 9 commandes sur le bus `character_storage` (`characters.list/get/put/delete`, `knowledge.list/get/push/update/delete`). Pas de MCP.
- **`character_service.mongodb_strategy`** refactoré : délègue à `character_storage`, plus de `MongoClient` direct. `database_uri`/`database_name` supprimés de `services.character_service` dans le YAML.
- **`memory/resync`** : reconstruit ChromaDB depuis `character_storage.list_knowledge()`, batch 100. Fix bug décorateurs empilés (`@command recall` + `@command resync` sur `resync_command`).
- **`bootstrap.py`** : `character_storage.init()` en premier, MongoDB désormais obligatoire.
- **simweb — Storage > Personnages** : grille CRUD, schéma vide complet à la création, JSON brut. Appel `character/reset` après put/delete pour synchroniser le cache `character_service`.
- **simweb — Storage > Knowledge** : grille colonnes (sans `_id`), filtres from/about en dropdowns, CRUD, formulaire avec `CategoryCombo` (select raccourci + input libre toujours visible).
- **simweb — Memory** : bouton Resync Chroma avec confirmation.
- **`documents/service_character_storage.md`** créé + indexé dans `CLAUDE.md`.
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — simweb : sidebar collapsible + section Administration

- **Layout** : `Layout.jsx` + `Sidebar.jsx` — sidebar collapsible (210 px ↔ 38 px, transition CSS), accordéon 2 sections (*Chat* / *Administration*) avec état expand/collapse indépendant par section. `simcli` abandonné comme outil de pilotage quotidien au profit du front web.
- **ServerPanel** : ping serveur + chargement dynamique de toutes les commandes bus (`GET /bus` + `GET /bus/{name}/commands`).
- **CharactersPanel** : grille de chips personnages, clic → fiche JSON via `character/get`, bouton Recharger (`character/reset`).
- **MemoryPanel** : formulaire recall (`from_char`, `about` optionnel, `context`) → cartes résultats avec tags `about` / `category` / scène et pourcentage de pertinence `(1 − distance) × 100`.
- **`api/simphonia.js`** enrichi : `ping`, `getAllCommands`, `getCharacter`, `resetCharacters`, `memoryRecall`.
- **`index.css`** : styles sidebar, accordéon, bouton secondaire, panneaux admin, cartes mémoire.
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — Logging par service + fix uvicorn + `get_identifier` fuzzy

- `src/simphonia/logging.yaml` : configuration par service — handlers fichier dédiés (`file_chat`, `file_memory`, `file_character`, `file_mcp`, `file_providers`, `file_chromadb`), tous en `mode: w` (reset au boot). Loggers isolés (`propagate: false`) dirigés vers console + fichier ou fichier seul (chromadb).
- `src/simphonia/logging_config.py` : `setup_logging()` — charge `logging.yaml`, corrige les chemins vers `PROJECT_ROOT/logs/`, crée le dossier `logs/`, appelle `logging.config.dictConfig()`. Appelé dans `main()` avant `asyncio.run()`.
- `__main__.py` : fix `log_level="info"` → `log_config=None` dans les deux `uvicorn.Config` pour empêcher uvicorn d'écraser le logging custom.
- `character_service/__init__.py` : `_normalize(s)` (NFD + strip Mn) + `_resolve_identifier(name, cache)` (3 niveaux : exact → token → partiel, min 3 chars). Méthode abstraite `get_identifier(name) -> str | None` ajoutée à `CharacterService`.
- `json_strategy.py` + `mongodb_strategy.py` : implémentent `get_identifier` via `_resolve_identifier`.
- `facade/server.py` : utilise `character_service.get().get_identifier()` pour normaliser `from_char` et `about` avant l'appel recall.
- Validation utilisateur : OK 2026-04-19.

### 2026-04-19 — Façade MCP + tool use `memory.recall` dans `chat_service`

- `src/simphonia/facade/` : serveur MCP SSE (SDK `mcp` 1.x) exposant les `@command(mcp=True)` comme tools. Démarre toujours sur `MCP_PORT` (défaut 8001) — `--character <slug>` injecte `from_char` (caché du LLM) ; sans flag, `from_char` est ajouté au schema comme paramètre requis.
- `commands/memory.py` : `mcp=True` sur `recall` avec `mcp_description` + `mcp_params` JSONSchema complet (`about`, `context`).
- `providers/base.py` : `ToolExecutor` type alias + params optionnels `tools` / `tool_executor` dans `call()`.
- `providers/anthropic.py` : boucle tool-use (max 5 iter) — detect `tool_use` blocks → exécute → injecte `tool_result` → relance. Throttle et retry 429/529 préservés.
- `providers/ollama.py` : boucle tool-use (max 5 iter) — detect `tool_calls` → exécute → message `role:tool` → relance.
- `chat_service/default_strategy.py` : `_get_mcp_tools()` + `_make_tool_executor(from_char)` + `_call_llm(..., from_char=<speaker>)` — tool use câblé sur `start`, `reply`, `auto_reply`. System prompt mis à jour avec hint `recall`.
- `__main__.py` : deux serveurs (HTTP 8000 + MCP 8001) démarrés via `asyncio.gather`, `--character` optionnel, `--port` / `--mcp-port` configurables.
- Bug fix : filtre `min_distance` inversé dans `chroma_strategy` (`>` au lieu de `<`).
- `documents/memory_service.md` : créé — rétro-doc complète + sections façade MCP et intégration chat_service.
- `pyproject.toml` + `requirements.txt` : `mcp>=1.0` ajouté.
- Validation : Aurore consulte ses souvenirs sur Élise via `recall` (Gemma4, tool use déclenché autonomement) avant de répondre à Antoine — réponse contextuelle validée.

### 2026-04-18 — Module `simweb` (front-end React, interface de chat)

- `src/simweb/` : application React + Vite. Proxy Vite `/bus → http://localhost:8000` (pas de CORS à gérer en dev).
- **`StartScreen`** : combos *De* / *À* chargées dynamiquement via `character.list`, textarea premier message, checkbox mode humain avec hint contextuel.
- **`ChatScreen`** : fil de messages colorés par personnage (bleu = `from_char`, violet = `to`), indicateur de frappe animé, scroll automatique, bouton Fermer (`chat.stop`). Zone de saisie (Entrée = envoyer, Maj+Entrée = saut de ligne) uniquement en mode humain.
- **SSE** : `GET /bus/chat/stream/{session_id}` — stream des événements `chat.said` pour le mode autonome (LLM↔LLM).
- **Côté serveur** : CORS activé (`app.py`), endpoint SSE ajouté (`routes.py`), publisher thread-safe `http/sse.py`, `said_command` publie l'événement avant de lancer `auto_reply`.
- Spec dans `documents/simweb.md`.
- Validation utilisateur : OK 2026-04-18.


### 2026-04-17 — `configuration_service` + loader YAML avec interpolation d'env

- `src/simphonia/services/configuration_service.py` : loader flat (module, pas package — pas de multi-stratégie). API `init(path=None)`, `get("dotted.path", default)`, `section("dotted.path")`, `as_dict()`. Toutes les lectures retournent des `deepcopy` — snapshot immuable côté consommateurs.
- `src/simphonia/simphonia.yaml` : fichier de configuration à la racine du module (localisation par défaut), sections `services.character_service` et `services.memory_service` avec stratégies et paramètres.
- **Interpolation `${VAR}` / `$VAR`** : appliquée récursivement sur tous les scalaires string de l'arbre via `os.path.expandvars`. Variables non définies → restent littérales, c'est au service consommateur de remonter une erreur explicite au startup (voir `mongodb_strategy`). Les env vars proviennent du `.env` (chargé via `python-dotenv` au bootstrap).
- **Flag CLI** : `simphonia --configuration <path>` — `src/simphonia/__main__.py` parse et stocke dans `SIMPHONIA_CONFIG_PATH`, lu par le loader.
- `bootstrap.py` : `configuration_service.init()` appelé en premier, puis `memory_service.init(section(...))` et `character_service.init(section(...))`.
- `config.py` nettoyé : plus de `DEFAULT_MEMORY_STRATEGY`, plus de `DEFAULT_CHARACTER_STRATEGY`, plus d'override env var `CHARACTER_SERVICE_STRATEGY`. Ne contient plus que les vraies constantes runtime (chemins, modèle embedding, etc.).
- `documents/configuration.md` : section "Service d'accès à la configuration" + doc de l'interpolation + exemple YAML mongodb complet.
- `src/simphonia/services/CLAUDE.md` : section "Accès à la configuration" — verrouille le pattern DI (stratégies reçoivent leurs params en kwargs, n'importent pas `configuration_service`).
- `pyproject.toml` + `requirements.txt` : `pyyaml>=6.0` en runtime.
- Validation : démarrage avec `mongodb_strategy` actif via interpolation YAML `${MONGO_URI}` / `${MONGO_DATABASE}` depuis `.env` — `MongoCharacterService prêt — 10 fiche(s) chargée(s) depuis symphonie.characters`.

### 2026-04-17 — `memory_service/recall` : résolution slots/load_factor/min_distance depuis character_service + config

- `commands/memory.py` : suppression des paramètres `top_k`, `factor`, `max_distance` de `recall_command`.
- `services/memory_service/__init__.py` : ABC `recall` mis à jour (idem) ; factory extrait `load_factor` et `min_distance` de la config et les passe au constructeur `ChromaMemoryService`.
- `chroma_strategy.py` : constructeur stocke `_load_factor` / `_min_distance`. Dans `recall`, appel `character_service.get().get_character(from_char)` → lecture `memory.slots` (fallback `DEFAULT_MEMORY_SLOTS=5` si `CharacterNotFound`) ; `n_results = max(int(slots * load_factor), 5)` ; filtre de sortie `distance < min_distance` → rejeté. Import `character_service` en lazy (inside method) pour éviter la dépendance circulaire à l'import du module.
- `simphonia.yaml` déjà à jour : `load_factor: 1.5`, `min_distance: 0.7`.
- Validation utilisateur : OK 2026-04-17.

### 2026-04-17 — `character_service` / `mongodb_strategy` + normalisation `memory_service`

- `src/simphonia/services/memory_service/` : normalisation sur le pattern interface/strategies. ABC `MemoryService` (`recall`, `stats`), factory `build_memory_service(service_config)` avec import dynamique, `init(service_config)` / `get()`. Unique stratégie pour l'instant : `chroma_strategy` — implémentation existante portée telle quelle dans `strategies/chroma_strategy.py` (fusion de l'ancien `__init__` + `init()` dans `__init__` direct, suppression du flag `ready`). Ancien `memory_service.py` supprimé.
- `commands/memory.py` : migration vers `memory_service.get().recall(...)`.
- `src/simphonia/services/character_service/strategies/mongodb_strategy.py` : `MongoCharacterService(database_uri, database_name)` — chargement eager `db.characters.find()` au startup, cache `{_id: dict}`, `reset` relance `find()`, warnings sur `_id` non-string / doublons. Paramètres injectés par la factory (pas de lecture directe `os.environ`). Collection cible fixée : `characters`.
- Factory `build_character_service` : dispatch `json_strategy` / `mongodb_strategy`, lève une erreur claire si `database_uri` / `database_name` manquants/vides (y compris après interpolation ratée).
- `pyproject.toml` + `requirements.txt` : `pymongo>=4.6`, `python-dotenv>=1.0` ajoutés en runtime.
- `documents/character_service.md` + `documents/configuration.md` : `mongodb_strategy` documentée, entrées `database_uri` / `database_name`.
- Validation : démarrage complet avec mongo actif — `MongoCharacterService prêt — 10 fiche(s) chargée(s) depuis symphonie.characters`, 3 bus, 2 commandes system, chargement Chroma OK (1671 documents), mongo OK.

### 2026-04-17 — `character_service` v1 (interface + `json_strategy`, bus `character`)

- `documents/character_service.md` : cahier des charges — API (`get_character_list`, `get_character`, `reset`), pattern interface + stratégies, config YAML (`services/<svc>/strategy`), choix d'architecture **schemaless** (dict brut, schéma déporté chez le consommateur), normalisation **`_id` à la MongoDB** (indexation par `_id`, pas par nom de fichier).
- `documents/configuration.md` : doc du fichier de configuration `simphonia.yaml` (défauts obligatoires, override CLI `--configuration <path>`), première entrée `services.character_service.strategy` documentée (`json_strategy` par défaut, `mongodb_strategy` à venir). YAML pas encore chargé — stratégie hardcodée via `DEFAULT_CHARACTER_STRATEGY`.
- `documents/commands.md` : cheatsheet install / build / lancement serveur & client, lint, tests.
- `src/simphonia/services/CLAUDE.md` : conventions locales — un dossier par service multi-stratégies, ABC (pas `Protocol`), factory avec imports dynamiques, pas de singleton module-level quand la construction dépend de la config.
- `src/simphonia/services/character_service/__init__.py` : ABC `CharacterService` (`get_character_list`, `get_character`, `reset`), `build_character_service(strategy)`, `init(strategy)` / `get()` — singleton après bootstrap.
- `src/simphonia/services/character_service/strategies/json_strategy.py` : chargement eager dans `__init__`, cache mémoire `{_id: dict}`, warnings (ignorés sans faire planter le boot) sur fiche illisible / `_id` manquant / doublon d'`_id`. `reset()` = clear + reload, retourne le count.
- `src/simphonia/commands/character.py` : `character/list` → `list[str]`, `character/get` → `dict`, `character/reset` → `int`. Pas de `mcp=True` pour l'instant.
- `src/simphonia/config.py` : `CHARACTERS_DIR = PROJECT_ROOT / "resources" / "characters"`, `DEFAULT_CHARACTER_STRATEGY = "json_strategy"`.
- `src/simphonia/core/errors.py` : `CharacterNotFound(SimphoniaError, KeyError)`.
- `src/simphonia/bootstrap.py` : `character_service.init(DEFAULT_CHARACTER_STRATEGY)` après `memory_service.init()`.
- `.claude/settings.local.json` : ajout `$schema` pour autocomplétion IDE + deny-list de sécurité standard (`.env*`, `*secret*`, `*credential*`, `*.pem/.key`, clés SSH, `.aws/credentials`, `.npmrc`/`.pypirc`/`.netrc` sur Read/Edit/Write/Grep ; `rm -rf /*`, `rm -rf ~*`, `sudo rm *`, `mkfs*`, `dd if=* of=/dev/*`, `chmod 777 /*`, `curl|wget … | sh|bash` sur Bash).
- Validation : dispatch `character/list`, `character/get --payload '{"name":"<id>"}'`, `character/reset` via simcli — OK côté utilisateur. Préalable H5.a (`character_service` porté) satisfait.

### 2026-04-17 — Première brique `memory_service` + commande bus `memory/recall`

- `src/simphonia/config.py` : `PROJECT_ROOT`, `CHROMA_DIR`, `COLLECTION_NAME="knowledge"`, `EMBEDDING_MODEL="paraphrase-multilingual-MiniLM-L12-v2"`, `DEFAULT_MEMORY_SLOTS=5`.
- `src/simphonia/services/memory_service.py` : port simplifié du legacy Symphonie — `init` / `embed` / `recall` / `stats` + singleton `memory_service`. **Exclus** : sync MongoDB, push, reset, drop_*, format_*. Usage interne uniquement (pas de ré-export via `services/__init__.py`).
- `src/simphonia/commands/memory.py` : `@command(bus="memory", code="recall")` avec signature `(from_char, context, top_k?, about?, participants?, factor?, max_distance?)`. **Pas de `mcp=True`** — commande locale uniquement pour l'instant. Délègue au singleton.
- `src/simphonia/bootstrap.py` : appel `memory_service.init()` après `discover()`, avant `create_app()`. Fail-fast si init KO (modèle ~5s + 420 Mo RAM au startup, zéro cold-start ensuite).
- `pyproject.toml` + `requirements.txt` : `chromadb>=0.5` et `sentence-transformers>=2.7` en runtime.
- Validation : dispatch `memory/recall` via simcli sur la bdd `data/chromadb` pré-initialisée (1671 documents, 9 personnages) retourne les souvenirs triés par distance cosine avec metadata `about/category/activity/scene`.

### 2026-04-17 — #10 `@command` étendu (attributs MCP)

- `Command` (dataclass frozen) : ajout de `mcp: bool = False`, `mcp_description: str | None = None`, `mcp_params: dict[str, Any] | None = None`.
- Décorateur `@command` : nouveaux kwargs `mcp`, `mcp_description`, `mcp_params` + validation decoration-time via `CommandContractError` :
  - rejet si `mcp=False` mais champ MCP fourni (contrat incohérent)
  - `mcp=True` exige `mcp_description` non vide
  - `mcp=True` exige `mcp_params` en dict JSONSchema (`type: "object"` + `properties: dict`)
- `CommandContractError(SimphoniaError, ValueError)` ajoutée dans `core/errors.py` et exposée via `simphonia.core`.
- Compat préservée : `system/help`, `system/ping` fonctionnent inchangés (`mcp=False` par défaut).
- Hors scope #10 (laissé à #13) : check `from_char` dans la signature au startup, check cascade orpheline.

### 2026-04-16 — Module `simcli`

- `src/simcli/client.py` : `SimphoniaClient` (wrapper `httpx.Client`, context-manager) avec `list_buses()`, `list_commands(bus_name)`, `dispatch(bus_name, code, payload)`. Gestion erreurs : `NotFound` (404), `ServerError` (≥400), `ServerUnreachable` (réseau).
- `src/simcli/cli.py` + `src/simcli/__main__.py` : CLI `argparse` avec sous-commandes `bus list`, `bus commands <name>`, `dispatch <bus> <code> [--payload JSON]`. Option globale `--url` (défaut `http://127.0.0.1:8000`). Sortie JSON formatée sur stdout, erreurs sur stderr.
- `src/simcli/errors.py` : hiérarchie `SimcliError` / `NotFound` / `ServerUnreachable` / `ServerError` / `InvalidPayload`.
- Codes de sortie : 0 OK · 1 erreur générique · 2 arguments/payload invalides · 3 serveur injoignable · 4 404 · 5 5xx.
- Choix stack : `httpx` + `argparse` (pas de `click`/`typer`, conformément au principe "simple").
- `pyproject.toml` : `httpx` remonté en runtime, script `simcli = "simcli.cli:main"` ajouté ; `requirements.txt` synchronisé.
- Docs : création de `documents/simcli.md` (spécs module), mise à jour de `documents/architecture.md` pour y pointer.

### 2026-04-16 — Squelette projet + architecture bus/commandes `simphonia`

- Création de l'arborescence `src/simphonia/{core,commands,http}` et `src/simcli/`.
- Couche `core/` :
  - `Command` (dataclass frozen : `code`, `description`, `callback`, `bus_name`).
  - `Bus` (register / get / list / dispatch, fail-fast sur doublon).
  - `BusRegistry` singleton (`default_registry()`, `reset()` pour tests).
  - Décorateur `@command(bus=..., code=..., description=...)`.
  - `discover(package)` via `pkgutil.walk_packages` pour forcer l'import récursif.
  - Hiérarchie d'erreurs : `SimphoniaError`, `BusNotFound`, `CommandNotFound`, `DuplicateCommand`, `DispatchError`.
- Commandes `system` :
  - `help` → liste `(code, description)` de toutes les commandes du bus `system`.
  - `ping` → `"pong"`.
- Couche HTTP (FastAPI + pydantic v2) :
  - `GET /healthz`, `GET /bus`, `GET /bus/{name}/commands`, `POST /bus/{name}/dispatch`.
  - Schémas pydantic : `BusDTO`, `CommandDTO`, `DispatchRequest/Response`, `ErrorBody/Response`.
  - Mapping erreurs → 404 / 500 avec body normalisé.
- Bootstrap & packaging :
  - `bootstrap.py` : pré-crée le bus `system`, appelle `discover("simphonia.commands")`, assertion présence `system/help`, log du compte.
  - `__main__.py` : `uvicorn.run("simphonia.bootstrap:app", ...)`.
  - `pyproject.toml` (hatchling) : deps runtime (fastapi, pydantic, uvicorn), extras `dev` (pytest, httpx, ruff), script `simphonia`, config ruff + pytest.
  - `requirements.txt` racine (miroir des deps runtime).
- Conventions projet consignées dans `CLAUDE.md` :
  - Toute nouvelle dépendance runtime → `pyproject.toml` **et** `requirements.txt` dans le même commit ; les deps de dev restent en extras.
  - Maintien d'un `backlog.md` unique avec priorités HOT/WARM/COLD/FROZEN/DONE, mis à jour uniquement après validation utilisateur.
- `.gitignore` Python / venv / PyCharm / `.env`.

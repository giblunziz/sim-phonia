# Backlog

Gestion des priorités : **HOT** > **WARM** > **COLD** > **FROZEN** > **DONE**.
Une entrée ne passe en `DONE` qu'après validation de l'utilisateur (tests manuels OK).

## HOT

### 🔧 INFRA — Backbone bus + cascades + façade MCP (en cours)

**Objectif immédiat** : poser l'infrastructure du serveur de services avant de porter quoi que ce soit depuis Symphonie. Décisions techniques figées dans `documents/simphonia.md` § *Conventions d'implémentation*.

**Plan séquencé (chaque tâche est testable isolément)** :

| # | Étape | Livrable |
|---|---|---|
| **#10** | `@command` étendu | `mcp=True`, `mcp_description`, `mcp_params` (JSONSchema riche) stockés sur `Command` |
| **#11** | `@cascade` + `ShortCircuit` | Décorateur, exception, storage trié `(priority, discovery_order)` dans `BusRegistry` |
| **#12** | `Bus.dispatch` refactor | Pipeline `before* → call → after*`, injection `from_char` (par nom dans signature), gestion d'erreurs spécifiée |
| **#13** | Validation startup | Cascade orpheline → fail | `mcp=True` sans `from_char` → fail |
| **#14** | Façade MCP | Second serveur sur `MCP_PORT` (SDK officiel `mcp`), tools générés depuis registry, `from_char` injecté, sortie markdown |
| **#15** | Smoke test E2E | Mock `memory/recall` + cascade `decay/after_recall`, validation via simcli + via client MCP |

**Prochaine étape : #10** (`@command` étendu — extension du décorateur sans casser l'existant `system/help`, `system/ping`).

**Hors scope de ce bloc** : moteur de tour joueur, vrai memory_service / knowledge_service (port Symphonie ultérieur), authentification MCP.

**Dépendance nouvelle prévue** : `mcp` (SDK officiel Anthropic) à ajouter dans `pyproject.toml` + `requirements.txt` à l'étape #14.

---

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

### H5 — Spécification `shadow_memory_service`

- Clarifier le rôle (mentionné par l'utilisateur comme maillon post-`memory_service` dans la chaîne d'appel)
- Définir interface, invariants, événements déclencheurs
- Positionner vs `memory_service` : transformation ? enrichissement ? observation/trace ?

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

_(vide)_

## FROZEN

_(vide)_

## DONE

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

# Backlog

Gestion des priorités : **HOT** > **WARM** > **COLD** > **FROZEN** > **DONE**.
Une entrée ne passe en `DONE` qu'après validation de l'utilisateur (tests manuels OK).

## HOT



### 🔧 INFRA — Backbone bus + cascades + façade MCP (en cours)

**Objectif immédiat** : poser l'infrastructure du serveur de services avant de porter quoi que ce soit depuis Symphonie. Décisions techniques figées dans `documents/simphonia.md` § *Conventions d'implémentation*.

**Plan séquencé (chaque tâche est testable isolément)** :

| # | Étape | Livrable |
|---|---|---|
| ~~#10~~ | ~~`@command` étendu~~ | ✅ livré 2026-04-17 (voir `DONE`) |
| **#11** | `@cascade` + `ShortCircuit` | Décorateur, exception, storage trié `(priority, discovery_order)` dans `BusRegistry` |
| **#12** | `Bus.dispatch` refactor | Pipeline `before* → call → after*`, injection `from_char` (par nom dans signature), gestion d'erreurs spécifiée |
| **#13** | Validation startup | Cascade orpheline → fail | `mcp=True` sans `from_char` → fail |
| **#14** | Façade MCP | Second serveur sur `MCP_PORT` (SDK officiel `mcp`), tools générés depuis registry, `from_char` injecté, sortie markdown |
| **#15** | Smoke test E2E | Mock `memory/recall` + cascade `decay/after_recall`, validation via simcli + via client MCP |

**Prochaine étape : #12** (`Bus.dispatch` refactor — pipeline `before* → call → after*`, injection `from_char`, gestion d'erreurs spécifiée).

**Hors scope de ce bloc** : moteur de tour joueur, vrai memory_service / knowledge_service (port Symphonie ultérieur), authentification MCP.

**Dépendance nouvelle prévue** : `mcp` (SDK officiel Anthropic) à ajouter dans `pyproject.toml` + `requirements.txt` à l'étape #14.

---

### C1 — `chat_service` (providers + sessions de dialogue 1-to-1)

Spec complète dans `documents/chat_service.md`. Validé utilisateur le 2026-04-18.

| # | Étape | Statut |
|---|---|---|
| ~~1~~ | ~~Porter providers LLM (ollama + anthropic) dans `src/simphonia/providers/`~~ | ✅ validé 2026-04-18 |
| ~~2~~ | ~~`provider_registry` — factory + `init/get` depuis config YAML `providers:`~~ | ✅ validé 2026-04-18 |
| ~~3~~ | ~~Squelette `chat_service` (ABC + `DialogueState` + start/reply/stop sans LLM)~~ | ✅ validé 2026-04-18 |
| ~~4~~ | ~~Logger fichier `/logs/chat.log` (reset au boot)~~ | ✅ validé 2026-04-18 |
| ~~5~~ | ~~Commandes bus `chat` + câblage bootstrap~~ | ✅ validé 2026-04-18 |
| ~~6~~ | ~~Génération LLM + schéma JSON `{talk:[...]}` dans system prompt~~ | ✅ validé 2026-04-18 |
| 7 | Façade MCP (bloqué sur INFRA #14) | En attente |

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

### H5 — Implémentation `shadow_memory_service` + "psy"

Synthèse d'étude figée dans `documents/shadow_memory.md` (2026-04-17). Rôle, chaîne d'exécution, opacité, deux casquettes du psy (runtime + production) sont actés.

**Actions identifiées** :

- **H5.a — Agent `psy`** : nouveau PNJ avec fiche + system prompt dédié, branché sur l'infra providers (OpenAI/Claude) avec config par perso + fallback. Dev/proto en gemma4. Préalable : `character_service` porté.
- **H5.b — Collection shadow MongoDB** : spec du schéma d'entrée (point ouvert : calque `PerceptionEntry` avec catégorie spéciale vs schéma propre avec `intensity` / `source_event_id` / `last_reinforced_at`). Initialiser la collection + le process de sync mongo→chroma (collection dédiée, séparée de `knowledge`).
- **H5.c — `shadow_memory_service`** : service dédié exposant deux fonctions — `shadow_before_call` (cascade `memory/recall` before, réécrit la query via un appel au psy) et `shadow_after_call` (cascade `memory/recall` after, 2e RAG sur la collection shadow + fusion). Dépend de #11/#12 (cascades) et de H5.a.
- **H5.d — État "focus" unilatéral** : choisir la forme de stockage (poids vs typologie vs hybride), le déclencheur d'update (après événement notable), les règles de priorité multi-focus.
- **H5.e — Garde-fous coût LLM** : skip quand aucun focus actif sur la cible, cache par hash de query, rate-limit par tour — à benchmarker une fois la chaîne complète en place.
- **H5.f — Trigger de re-sync mongo→chroma** pendant le jeu : identifier l'événement déclencheur (fin d'exchange ? insert mongo ? commande explicite ?) et le câbler.

**Préalables bloquants** : tickets #11 / #12 (cascades) et #14 (façade MCP) du bloc INFRA, plus H1 (modélisation) et le port de `character_service`.

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

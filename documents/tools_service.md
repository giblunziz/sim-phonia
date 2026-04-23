# tools_service

Service utilitaire — atelier de préparation de données piloté par LLM. Hors scénario, hors session, hors bus applicatif. Un clic, un run, un résultat dans `./output/`.

## Contexte

Historique : port simplifié et modernisé de `run_task.py` (legacy Symphonie). Dans l'ancienne archi, les tasks étaient décrites par fichiers YAML, les inputs par fichiers markdown sur disque, les outputs par fichiers structurés ou non. Ici tout bascule en **MongoDB-first** — fini les fichiers de vérité, seuls les outputs de travail restent sur disque (fichiers txt bruts à re-importer manuellement après validation).

Le `tools_service` vit en parallèle du pipeline de jeu (`activity_engine`, `chat_service`). Il partage peu d'infrastructure : juste le `character_storage` mongo pour accéder aux fiches, et les `activity_storage.schemas` pour les schémas JSON de sortie. Aucun bus scénario, aucune persistance de session, aucun MJ.

## Concepts

### Source / Subject / Prompt — le triptyque

Chaque run se décrit par trois entrées :

- **Source** : liste de documents mongo qui jouent le rôle de "personnage qui exécute" — leur fiche complète est injectée dans le system prompt. Équivalent du `runner` en legacy. Une collection + N `_id` cochés.
- **Subject** (optionnel) : liste de documents mongo qui jouent le rôle de "cible d'analyse" — leur document est aussi injecté dans le system prompt, une itération par subject. Une collection + N `_id` cochés, ou rien.
- **Prompt** : la commande en langage naturel, passée comme user prompt. Saisie dans l'UI et persistable dans la collection `tasks` pour réutilisation.

Moteur : **double boucle `sources × subjects`**. Si `subjects` est vide, une seule itération par source (équivalent mode "simple" legacy).

**Checkbox UI `skip self`** : quand cochée (comportement par défaut), les cellules où `source_id == subject_id` sont ignorées — évite par exemple `manon ⇔ manon` dans un cross-analyse. Décochable quand l'auto-analyse est volontaire (ex: un perso se décrit lui-même sur la base de sa fiche + une présentation antérieure).

### Registre `task_collection`

Collection mongo spéciale qui liste les **collections exposables** comme sources ou subjects dans l'UI. L'utilisateur gère cette collection à la main (mongosh / Compass / script) — pas de CRUD UI en V1.

Schéma :

```json
{ "_id": "characters", "description": "Liste des personnages" }
{ "_id": "presentation", "description": "Présentations publiques générées" }
```

Le back ne lit que le champ `_id` (projection `{_id: 1}`). La `description` est là pour le confort de l'utilisateur quand il édite la collection en direct.

Quand une entrée pointe vers une collection mongo, le back liste les `_id` de cette collection pour peupler les checkbox. Extensible : pour exposer une nouvelle collection, l'utilisateur la crée en mongo puis ajoute une entrée dans `task_collection` et clique sur `↻ Refresh` côté UI.

### Documents schemaless

Tous les documents lus dans les collections référencées sont traités comme **schemaless** du point de vue du tools_service : on les récupère tels quels via `find_one({_id})` et on les sérialise (`json.dumps(indent=2)`) pour injection dans le system prompt. Aucun filtre PUBLIC/PRIVATE, aucune transformation. L'utilisateur assume — c'est son atelier de préparation, pas le jeu.

### Collection `tasks`

Collection mongo de prompts réutilisables. Schéma strict :

```json
{ "_id": "presentation", "prompt": "Présente-toi en quelques lignes...", "temperature": 0.8 }
```

Trois champs, pas plus :
- **`_id`** (slug) : identifiant humain, choisi par l'utilisateur
- **`prompt`** (str) : le user prompt complet
- **`temperature`** (float) : température par défaut, rechargée dans l'UI à la sélection de la task, modifiable par run avant le [Run]

Le choix du runner/subject/schéma/provider **n'est pas persisté** dans la task — chaque run est reconfiguré depuis l'UI.

### Schéma JSON de sortie (optionnel)

Injecté depuis `activity_storage.schemas` (structure `{_id, prompt, payload}` déjà en place). Si un schéma est sélectionné dans l'UI, il est ajouté en bas du system prompt selon le même format que le `system_schemas` de `context_builder`.

## Workflow utilisateur

### Exemple Phase 1 — Presentations

L'utilisateur veut générer des présentations publiques pour chaque personnage du cast.

1. Section *Tools* de simweb
2. Dropdown `tasks` → sélection `presentation` → prompt + temperature rechargés
3. Colonne **Source** : dropdown collection → `characters`, cocher `antoine`, `manon`
4. Colonne **Subject** : rien
5. Aucun schéma (texte brut)
6. [Run] → 2 itérations, progress bar
7. Résultats dans `./output/presentation/20260423_1430/antoine.txt` + `manon.txt`
8. Hors tools_service : l'utilisateur valide, copie manuellement le contenu dans une collection `presentation` qu'il gère en direct (mongosh / Compass)

### Exemple Phase 2 — Cross-analyse

L'utilisateur veut que `manon` analyse la présentation d'`antoine`.

1. Dropdown `tasks` → sélection `cross_analyse`
2. Colonne **Source** : collection `characters`, cocher `manon`
3. Colonne **Subject** : collection `presentation`, cocher `antoine`
4. Dropdown `schema` → sélection du schéma JSON attendu (catégories `perceived_traits`, `assumptions`, etc.)
5. [Run] → 1 itération
6. Résultat dans `./output/cross_analyse/20260423_1445/manon_antoine.txt` (contient du JSON, mais extension `.txt` — l'utilisateur gère le post-processing car le LLM glisse parfois des backticks markdown)

## Composition du system prompt

Builder dédié au tools_service (ne passe pas par `activity_service.context_builder` — trop riche pour ce cas, logique scène/knowledge/règles inutile ici). Format minimaliste :

```
## SOURCE: <source_id>
<json.dumps(source_doc, indent=2)>

## SUBJECT: <subject_id>           # uniquement si subject fourni
<json.dumps(subject_doc, indent=2)>

<bloc schéma JSON si fourni>        # format identique à system_schemas
```

Le user prompt = le `prompt` saisi dans la textarea (éventuellement chargé depuis la task mongo).

Ordre strict — une seule passe, aucune boucle tool-use côté provider (pas de `memory/recall` ni `memorize` en tools_service — on est en atelier, pas en jeu).

## API fonctionnelle

Le service expose (ABC `ToolsService`) :

| Fonction | Description | Retour |
|---|---|---|
| `list_exposable_collections()` | Lit `task_collection` avec `$project _id: 1` | `list[str]` |
| `list_ids(collection_name)` | Liste les `_id` d'une collection donnée (après contrôle contre `task_collection`) | `list[str]` |
| `get_document(collection_name, _id)` | Récupère un document complet (schemaless) | `dict` |
| `list_tasks()` | Liste les tasks stockées | `list[dict]` |
| `get_task(slug)` | Charge une task | `dict` |
| `put_task(slug, prompt, temperature)` | Upsert d'une task | `dict` |
| `delete_task(slug)` | Suppression d'une task | `int` |
| `run(task_slug, prompt, temperature, source_collection, source_ids, subject_collection, subject_ids, schema_id, skip_self) -> dict` | Exécution synchrone du run, écriture des fichiers output, retour du résumé | `dict` |

Exposition bus HTTP sur `tools/*` — pas de `mcp=True`, pas de `mcp_role`. L'atelier n'est pas accessible aux LLM incarnés.

**Pas de tools MCP injectés côté LLM pendant un run** : le provider est appelé en un seul aller-retour, sans `tools=[...]` ni `tool_executor`. Ni `recall`, ni `memorize`, ni aucun autre outil scénario. Le LLM de l'atelier lit ce qu'on lui donne (source, subject, schéma, prompt), produit sa réponse, point. Aucun couplage avec `memory_service` / `character_service.get_identifier` / etc.

## Architecture

### Storage

Une seule stratégie : **MongoDB**. Pas d'abstraction multi-stratégies (YAGNI, atelier = base locale dev).

Collections gérées :
- `tasks` — écriture en `put_task` / `delete_task`
- `task_collection` — lecture seule côté back (l'utilisateur la gère en direct)
- Autres collections — lecture seule via `get_document` (contrôlée par `task_collection`)

### Service

`services/tools_service/` — même pattern que les autres services multi-stratégies, même si ici on n'a qu'une stratégie mongo :

```
services/tools_service/
├── __init__.py           # ABC ToolsService + factory + init/get
├── builder.py            # _build_system_prompt(source, subject?, schema?)
└── strategies/
    ├── __init__.py
    └── mongodb_strategy.py
```

La stratégie `mongodb_strategy` instancie un `MongoClient` dédié (partage éventuel à voir avec `character_storage` et `activity_storage` — point d'optim plus tard).

### Exécution

**Synchrone** : `run()` enchaîne les itérations dans un seul appel. Durée attendue : de quelques secondes (1 source × 0 subject) à plusieurs minutes (N × M grosse matrice).

**Progress** : pour alimenter une progress bar côté UI sans utiliser le bus scénario ni SSE scénario, deux options à trancher à l'implémentation :
- **A** : endpoint SSE dédié `GET /tools/progress/{run_id}` (préférable UX, plus de boulot)
- **B** : polling `GET /tools/status/{run_id}` toutes les 1-2s (plus simple, moins fluide)

V1 : **Option B** si ça suffit, sinon A. À valider au plan d'implémentation.

**Erreurs par cellule** : best-effort. Une cellule qui plante (timeout provider, réponse vide après retries) est loguée, le fichier output n'est pas écrit, le run continue. Résumé final avec compteur `succeeded / failed`.

**Retry sur réponse vide** : si le provider renvoie `reply` vide/`None`, la cellule est relancée jusqu'à `max_retries` tentatives (défaut `3`, configurable via YAML `services.tools_service.max_retries`). Passé le quota, la cellule échoue proprement. Aucun retry sur exception du provider — seul le cas "réponse vide" est concerné, les erreurs réseau/timeout remontent directement en échec cellule.

**Interruption utilisateur (`cancel`)** : commande bus `tools/cancel(run_id)` + bouton `⏹ Stop` dans l'UI. L'interruption prend effet **entre deux cellules** (pas d'annulation d'un appel LLM en cours — le provider ne l'expose pas). Le run passe en status `cancelled`, écrit son `_run.meta.json` et se termine proprement. Latence max ≈ durée d'une cellule. Les cellules déjà terminées avec succès conservent leur fichier de sortie.

### Output

Structure : `./output/<task_slug>/<YYMMDD_HHMMSS>/`

Fichiers dedans :
- `<source_id>.txt` si pas de subject
- `<source_id>_<subject_id>.txt` si subject

Toujours `.txt`, jamais `.json` — même si la réponse est structurée, les LLM glissent régulièrement des backticks markdown (```` ```json ... ``` ````) que l'utilisateur nettoie lui-même à l'import vers mongo.

Bonus : un fichier `_run.meta.json` dans le même dossier avec les métadonnées du run (prompt, sources, subjects, schéma, provider, stats, timestamps) — utile pour reproduire / debugger.

## Configuration YAML

```yaml
services:
  tools_service:
    model: anthropic_opus           # référence un provider du provider_registry
    tasks_collection: tasks
    registry_collection: task_collection
    output_dir: output              # racine des fichiers de travail
    max_retries: 3                  # retry par cellule si réponse LLM vide (défaut 3)
```

**`model`** : identique au mécanisme des autres services (`chat_service.model`, etc.). Le `provider_registry` doit connaître ce `_id`. Le model est **fixe** (configuré au boot, pas overridable par run dans l'UI — on a la température pour ça).

## UI simweb

Section dédiée dans la sidebar (nouvelle rubrique *Tools* ou *Atelier*). Un seul écran pour démarrer.

### Disposition

```
┌─ Task ─────────────────────────────────────────────────┐
│ Task : [presentation ▼]   Slug : [presentation    ]    │
│ Prompt :                                               │
│ ┌──────────────────────────────────────────────────┐   │
│ │ Présente-toi en quelques lignes...                │   │
│ └──────────────────────────────────────────────────┘   │
│ Temperature : [0.8]    [💾 Save]                       │
└────────────────────────────────────────────────────────┘

┌─ Source ─────────────────┬─ Subject ───────────────────┐
│ Collection : [characters▼]│ Collection : [— aucune ▼]  │
│ [↻] Refresh               │ [↻] Refresh                 │
│  ☑ antoine                │  ☐ antoine                  │
│  ☐ aurore                 │  ☐ aurore                   │
│  ☑ manon                  │  ☐ manon                    │
│  …                        │  …                          │
└───────────────────────────┴─────────────────────────────┘

Schéma : [— aucun ▼]    ☑ Skip self      [▶ Run]

(progress bar pendant run)
(zone résultats : liens vers les fichiers .txt générés)
```

### Actions

- **[💾 Save]** : upsert de `{_id: slug, prompt, temperature}` dans la collection `tasks`. Si slug inchangé → update. Si slug modifié → création d'une nouvelle entrée.
- **[↻ Refresh]** : recharge les `task_collection` et les `_id` de la collection sélectionnée.
- **[▶ Run]** : lance `tools/run` avec tous les paramètres courants. Désactive les contrôles pendant l'exécution. Affiche la progress bar.

## Contraintes transverses

- Collection `task_collection` gérée **hors UI** par l'utilisateur (mongosh/Compass). Le tools_service la consulte en lecture seule avec projection `_id`.
- Documents injectés tels quels — **aucun filtre** de visibilité (PRIVATE/PUBLIC). Hors-scope jeu.
- Outputs toujours `.txt`, jamais parsés — l'utilisateur gère le post-processing et l'import mongo manuel.
- Une dépendance mongo supplémentaire n'est pas requise (on réutilise `pymongo` déjà en runtime).

## Hors scope V1 (YAGNI)

- CRUD UI pour `task_collection` (l'utilisateur édite en direct)
- Auto-upsert des résultats vers une collection cible (validation manuelle obligatoire)
- Boucle tool-use (recall/memorize) côté atelier — inutile, pas de persona live
- Composition déclarative `task → task` (chaînage)
- Reprise sur crash (un run qui plante = on relance à zéro)
- Multi-schémas cumulés dans le system prompt (0 ou 1)
- Historique des runs passés côté UI (les métadonnées `_run.meta.json` suffisent pour l'investigation)

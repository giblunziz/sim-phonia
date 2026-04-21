# memory_service — Cahier des charges

## Rôle

Service de **mémoire contextuelle RAG** d'un personnage : recherche sémantique de souvenirs (`recall`) **et** ajout volontaire de nouvelles convictions (`memorize`). Le LLM joueur déclenche les deux via tool-use MCP.

L'ABC `MemoryService` couvre lecture (`recall`) + mutation contrôlée (`memorize`) + observabilité (`stats`). Les autres mutations (purge, drop, sync) restent hors de l'interface — pilotées par cascades ou par le futur `shadow_memory_service`.

---

## Architecture — pattern interface + stratégies

```
services/memory_service/
├── __init__.py          # ABC MemoryService + factory build_memory_service() + singleton init/get
└── strategies/
    ├── __init__.py
    └── chroma_strategy.py   # implémentation ChromaDB (seule stratégie active)
```

Initialisé au bootstrap depuis `configuration_service.section("services.memory_service")`.

---

## Interface

```python
class MemoryService(ABC):
    def recall(
        self,
        from_char: str,
        context: str,
        about: str | None = None,
        participants: list[str] | None = None,
    ) -> list[dict]: ...

    def memorize(
        self,
        from_char: str,
        notes: list[dict],
    ) -> dict: ...

    def stats(self) -> dict: ...
```

### `recall`

Retourne les souvenirs d'un personnage pertinents pour un contexte donné.

| Paramètre | Type | Rôle |
|---|---|---|
| `from_char` | `str` | Identifiant du personnage propriétaire des souvenirs |
| `context` | `str` | Texte encodé en vecteur pour la recherche sémantique |
| `about` | `str?` | Filtre : souvenirs à propos d'un sujet précis |
| `participants` | `list[str]?` | Filtre : souvenirs à propos d'un groupe de sujets |

Retourne une liste de `dict` :

```json
{
  "value": "texte du souvenir",
  "about": "sujet (personnage ou entité)",
  "category": "catégorie sémantique",
  "activity": "activité associée",
  "scene": "scène d'origine",
  "distance": 0.7234
}
```

### `memorize`

Permet au LLM joueur d'enregistrer volontairement de nouvelles convictions sur les autres participants (ou sur lui-même). Symétrique de `recall`. Push **live** dans MongoDB (source de vérité) **et** dans ChromaDB (index sémantique) — pas de batch ni de re-sync différée.

| Paramètre | Type | Rôle |
|---|---|---|
| `from_char` | `str` | Identifiant du personnage qui mémorise (auto-injecté) |
| `notes` | `list[dict]` | Liste de notes à enregistrer en un seul appel — voir schéma ci-dessous |

#### Payload `notes[]`

```json
[
  {
    "about":    "prénom d'un participant — utilise ton propre prénom pour une note réflexive sur toi-même",
    "category": "perceived_traits | assumptions | approach | watchouts",
    "value":    "Ce que tu as appris, confirmé ou révisé sur cette personne. Formule-le comme une conviction intime."
  }
]
```

| Champ | Type | Validation |
|---|---|---|
| `about` | `str` | Slug ou nom — résolu via `character_service.get_identifier()` (fuzzy). `from_char` ou `"self"` autorisé pour l'introspection. |
| `category` | `enum[4]` | `perceived_traits` \| `assumptions` \| `approach` \| `watchouts` (catégories figées du backlog H1) |
| `value` | `str` | Texte libre, formulé à la première personne |

#### Algorithme

Pour chaque note :

1. Résolution `about_slug` via `character_service.get_identifier(note.about)`. Si `note.about == from_char` ou `"self"` → la note est réflexive.
2. Encodage du `value` en embedding (SentenceTransformer, calculé une seule fois et réutilisé pour l'insert).
3. **Dédup sémantique** : query ChromaDB `n_results=1, where={from, about, category}`. Si `distance < dedup_threshold` (défaut `0.2`) → la note est considérée comme un quasi-doublon, **skippée** + loggée dans `logs/memory.log`.
4. Sinon, insertion atomique :
   - **MongoDB** `knowledge` : nouveau document avec `from`, `about`, `category`, `value`, `activity`, `scene`, `ts`.
   - **ChromaDB** `knowledge` : ajout du document avec metadata + embedding pré-calculé.

#### Retour structuré

```python
{
    "added":   2,                  # nombre de notes effectivement insérées
    "skipped": 1,                  # nombre de notes skippées par dédup
    "details": [
        {"about": "antoine", "category": "perceived_traits", "status": "added"},
        {"about": "élise",   "category": "assumptions",      "status": "skipped",
         "reason": "semantic_duplicate", "distance": 0.12},
        {"about": "self",    "category": "watchouts",        "status": "added"},
    ],
}
```

#### Format de retour MCP (markdown)

Le LLM reçoit un message de confirmation **explicite** pour ancrer ses notes dans son contexte de raisonnement immédiat :

```
✅ Tu as mémorisé 2 nouvelle(s) note(s) :
- (perceived_traits) à propos de antoine : Il est jaloux et le cache mal.
- (watchouts) à propos de toi-même : Je dois éviter de me laisser provoquer.

ℹ️ 1 note ignorée car déjà présente dans ta mémoire :
- (assumptions) à propos de élise : Elle ne dit pas tout ce qu'elle pense.
```

Cas dégradés (toutes les notes skippées, ou notes vides, ou erreur de validation) : message explicite, jamais d'erreur levée.

#### Persistance dans le contexte de session

Pour éviter le « mémorise et oublie au prochain tour » qui casserait la cohérence narrative, le markdown de confirmation est conservé dans `SessionState.memorize_log[from_char]: list[str]` et **ré-injecté** dans le system_prompt joueur à chaque `give_turn` via `context_builder.build_messages` :

```
## Tes mémorisations récentes
✅ Tu as mémorisé ... (round 2)
✅ Tu as mémorisé ... (round 3)
```

Léger overlap accepté avec ce que `recall` peut remonter — ça renforce l'ancrage.

---

## Stratégie active : `chroma_strategy`

### Stack technique

| Composant | Choix |
|---|---|
| Vector store | ChromaDB — persistant local (`data/chromadb/`) |
| Distance | Cosine (HNSW) |
| Embedding | `paraphrase-multilingual-MiniLM-L12-v2` (SentenceTransformer) |
| Collection | `"knowledge"` (unique, partagée entre tous les personnages) |

### Constantes (issues de `config.py`)

| Constante | Valeur |
|---|---|
| `CHROMA_DIR` | `PROJECT_ROOT / "data" / "chromadb"` |
| `COLLECTION_NAME` | `"knowledge"` |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` |
| `DEFAULT_MEMORY_SLOTS` | `5` |

### Algorithme `recall`

1. Lecture de `char.memory.slots` via `character_service` (fallback : `DEFAULT_MEMORY_SLOTS`)
2. `n_results = max(slots × load_factor, DEFAULT_MEMORY_SLOTS)`
3. Construction du filtre `where` ChromaDB :
   - `about` fourni → `{from: from_char, about: about}`
   - `participants` fourni → `{from: from_char, about: {$in: participants ∪ {from_char}}}`
   - sinon → `{from: from_char}`
4. Encodage de `context` en vecteur via SentenceTransformer
5. Requête ChromaDB : `n_results` au plus, include `documents / metadatas / distances`
6. Filtre post-query : élimine les entrées avec `distance > min_distance` (bruit sémantique)
7. Retourne la liste filtrée

> Distance cosine ChromaDB : 0 = identique, 1 = orthogonal. `min_distance` est la **distance maximale utile** : tout souvenir avec `distance > min_distance` est du bruit et est éliminé. Config prod : `min_distance: 0.7`.

---

## Schéma de métadonnées ChromaDB (observations)

Chaque document dans la collection `"knowledge"` porte ces métadonnées :

| Champ | Type | Description |
|---|---|---|
| `from` | `str` | Personnage propriétaire du souvenir |
| `about` | `str` | Sujet du souvenir (personnage ou entité) |
| `category` | `str` | Catégorie sémantique |
| `activity` | `str` | Activité associée |
| `scene` | `str` | Scène d'origine |

Le corps du document est le texte brut du souvenir.

---

## Bus

Bus : `"memory"`.

| Code | Paramètres | Retour | `mcp_role` |
|---|---|---|---|
| `memory.recall` | `from_char, context, about?, participants?` | `list[dict]` | `player` |
| `memory.memorize` | `from_char, notes: list[dict]` | `dict` (cf. retour structuré §memorize) | `player` |
| `memory.resync` | `—` | `dict` | n/a |

**Réponse MCP `recall` — format markdown :**

```
# Vos souvenirs à propos de <about>
- Souvenir 1
- Souvenir 2
```

Cas dégradés (personnage `about` inconnu **ou** aucun souvenir remonté) — réponse identique :

```
Je n'ai aucun souvenir de <about>.
```

**Réponse MCP `memorize`** : voir bloc markdown de la section `memorize` ci-dessus.

Le handler MCP rend toujours la main au LLM, jamais d'erreur levée.

---

Non câblés sur le bus (administration, observabilité) :
- `memory.drop` — supprimer un souvenir
- `memory.reset` — vider la mémoire d'un personnage
- `memory.stats` — observabilité

---

## Configuration YAML (`services.memory_service`)

| Paramètre | Défaut | Description |
|---|---|---|
| `strategy` | `chroma_strategy` | Stratégie à instancier |
| `load_factor` | `1.0` | Multiplicateur `n_results = slots × load_factor` (recall) |
| `min_distance` | `1.0` | Seuil post-query — distance maximale utile (recall) |
| `dedup_threshold` | `0.2` | Distance maximale en deçà de laquelle une note `memorize` est considérée comme un doublon sémantique et skippée |

Config prod actuelle (`simphonia.yaml`) : `load_factor: 1.5`, `min_distance: 0.7`, `dedup_threshold: 0.2`.

---

## Façade MCP (`simphonia/facade/`)

Serveur MCP SSE dual exposant `memory.recall` **et** `memory.memorize` comme tools aux LLM joueurs (endpoint `/sse`, `mcp_role="player"`). Les tools MJ (`activity/give_turn`, etc.) sont sur `/sse/mj` (`mcp_role="mj"`). Démarre toujours sur `MCP_PORT` (défaut 8001) en même temps que le serveur HTTP.

### Démarrage

```bash
simphonia                       # MCP sur 8001, from_char requis dans les appels
simphonia --character antoine   # MCP sur 8001, from_char injecté (invisible du LLM)
simphonia --mcp-port 8002       # port alternatif
```

### Comportement selon le mode

| Mode | `from_char` dans schema | Injection |
|---|---|---|
| Sans `--character` | Oui (requis) | Non — passé par le LLM |
| Avec `--character <slug>` | Non (caché) | Oui — injecté par le serveur |

### Endpoint SSE

```
GET  http://127.0.0.1:8001/sse          # ouvre le stream SSE
POST http://127.0.0.1:8001/messages/    # envoie les messages JSON-RPC
```

### Format de retour

```markdown
# Vos souvenirs à propos de <about>
- Souvenir 1
- Souvenir 2
```

Cas dégradé (personnage inconnu ou aucun souvenir) :
```
Je n'ai aucun souvenir de <about>.
```

---

## Intégration chat_service — tool use natif

`memory.recall` **et** `memory.memorize` sont exposés comme tools natifs aux providers LLM (Anthropic et Ollama) dans le `chat_service`. Le LLM décide lui-même quand les appeler.

### Chaîne d'exécution

```
chat_service._call_llm(system_prompt, messages, from_char=<speaker>)
  → provider.call(..., tools=[recall_def], tool_executor=<executor>)
    → LLM décide d'appeler recall(about=..., context=...)
    → executor injecte from_char=<speaker>, appelle memory_service.recall()
    → résultat markdown injecté dans l'historique messages
    → LLM génère sa réponse finale {"talk": "..."}
```

### System prompt

Le system prompt de chaque personnage inclut :

> *"Tu as accès à l'outil `recall` pour consulter tes souvenirs sur quelqu'un avant de répondre, et à l'outil `memorize` pour enregistrer de nouvelles convictions sur les autres ou sur toi-même. Utilise-les librement si la situation le nécessite. `memorize` accepte plusieurs notes en un seul appel — regroupe tes nouvelles convictions dans la liste."*

### Format tool definition (provider-agnostic)

```python
{
    "name": "recall",
    "description": "Cherche dans tes souvenirs ce que tu sais sur quelqu'un dans un contexte donné.",
    "parameters": {
        "type": "object",
        "properties": {
            "about":   {"type": "string", "description": "Le prénom de la personne dont tu veux te souvenir"},
            "context": {"type": "string", "description": "La situation ou le sujet qui t'occupe en ce moment"},
        },
        "required": ["about", "context"],
    }
}
```

### Comportement modèles

| Provider | Tool use | Notes |
|---|---|---|
| Anthropic (Claude) | ✅ Fiable | Appel natif, format `tool_use` blocks |
| Ollama (Gemma4) | ⚠️ Best-effort | Déclenche parfois, pas systématique |

---

## Intégration `activity_engine` — `memorize_log`

Pour préserver la cohérence narrative (mémoriser et oublier au prochain tour casserait l'illusion), le `SessionState` garde une trace par speaker des notes mémorisées :

```python
@dataclass
class SessionState:
    ...
    memorize_log: dict[str, list[str]] = field(default_factory=dict)
    # speaker_slug → liste ordonnée des markdowns de confirmation memorize
```

- Le **tool_executor** (`activity_service` + `chat_service`) appelle `memory.memorize` puis append le markdown de confirmation dans `session.memorize_log[from_char]`.
- `context_builder.build_messages` injecte ces markdowns au début du contexte joueur (après amorce/event/whisper, avant l'historique des exchanges) sous une section « ## Tes mémorisations récentes ».
- La trace est **éphémère** : vit avec la session, jetée au `end()` (les notes restent en MongoDB/ChromaDB).
- Léger overlap accepté avec ce que `recall` peut remonter — renforcement positif de l'ancrage.

---

## Décisions de conception

| Num | Question | Décision retenue | Raison |
|-----|----------|------------------|--------|
| 1 | Quand le LLM peut-il appeler `memorize` ? | Libre, comme `recall`. Pas de phase imposée. | Symétrie avec `recall`. Confiance LLM. |
| 2 | Quels champs dans le payload ? | `{about, category, value}` — `from` auto-injecté ; `category` ∈ enum `[perceived_traits, assumptions, approach, watchouts]` | Catégories figées du backlog H1. `from` jamais sous contrôle du LLM (sécurité). |
| 3 | Persistance | Push **live** Mongo + Chroma, pas de batch | Cohérence immédiate. Le re-sync prend du temps, on évite. |
| 4 | Doublons sémantiques | Dédup par cosine `where=(from, about, category)`, seuil `0.2` (configurable YAML), skip + log | String match (b) inutile (LLM paraphrase systématiquement). Coût query Chroma négligeable vs appel LLM. Évite la pollution du RAG. |
| 5 | `mcp_role` | `player` uniquement | Pas de mémorisation autonome côté MJ. |
| 6 | Visibilité `about` | `about` ∈ `{autre_perso, from_char, "self"}` ; `from = from_char` toujours | Introspection autorisée (« je dois éviter X »). `from` jamais sous contrôle LLM. |
| 7 | Garde-fou « 1 par tour » | Auto-discipline LLM via `mcp_description`, schéma `notes: array` qui force le regroupement. Pas d'enforcement serveur en V1. | Confiance LLM. Si dérapage observé, basculer en compteur serveur (V2). |
| 8 | Exposition du tool | Partout : `chat_service`, `activity_engine`, façade MCP `/sse` | Symétrie totale avec `recall`. |
| 9 | Format de retour | Markdown structuré (added/skipped) ré-injecté à chaque tour via `SessionState.memorize_log` | Empêche le « mémorise et oublie ». Cohérence narrative. |

---

## Plan d'implémentation séquencé

États : `TODO` / `WIP` / `DONE` / `BLOCKED`. Convention : ne basculer en `DONE` qu'après validation explicite utilisateur.

| # | Étape | Livrable | Dépendances | État |
|---|-------|----------|-------------|------|
| 1 | Étendre `MemoryService` ABC : ajouter `memorize(from_char, notes) -> dict` | Contrat figé, signature claire | — | `TODO` |
| 2 | `chroma_strategy.memorize` : embed unique, query dédup `where=(from, about, category)` seuil `dedup_threshold`, skip si distance < seuil, sinon insert Mongo + Chroma | Mutation atomique avec dédup sémantique | #1 | `TODO` |
| 3 | Configuration YAML : `dedup_threshold: 0.2` dans `simphonia.yaml`, propagation jusqu'au constructeur stratégie | Param configurable | #2 | `TODO` |
| 4 | Commande bus `memory/memorize` avec `mcp=True, mcp_role="player"`, JSONSchema array sur `notes`, `mcp_description` du point de vue du personnage | Tool exposable LLM | #2 | `TODO` |
| 5 | Façade MCP : intégration générique (déjà OK via `list_mcp_commands(role="player")`) — vérifier que `memorize` apparaît bien sur `/sse` et que le dispatch via bus fonctionne | Tool actif côté façade | #4 | `TODO` |
| 6 | `SessionState.memorize_log: dict[str, list[str]]` + tool_executor `activity_engine` qui appelle memory_service.memorize, formate en markdown, append dans `memorize_log[from_char]` | Trace en mémoire de session | #4 | `TODO` |
| 7 | `context_builder.build_messages` : injection « ## Tes mémorisations récentes » au début du contexte joueur si `memorize_log[player]` non vide | Persistance contexte LLM | #6 | `TODO` |
| 8 | `chat_service` : intégration symétrique du tool_executor pour `memorize` (équivalent activity_engine, scope session chat) | Symétrie chat 1-to-1 | #4 | `TODO` |
| 9 | Tests unitaires : `chroma_strategy.memorize` (mock Chroma, vérif dédup), `commands/memory.memorize` (validation payload, dispatch), tool_executor (mock memory_service, vérif memorize_log) | TU verts | #2, #4, #6 | `DONE` (12 TU, 97 total 2026-04-20) |
| 10 | Smoke test E2E : run réel avec un LLM joueur qui doit mémoriser puis raisonner sur ses propres notes au tour suivant | Validation utilisateur | #1-#9 | `DONE` (Isabelle mémorise sur Louis + réflexive sur elle-même, multi-notes en un appel, formulation 1re pers, 2026-04-20) |

**Convention de maintenance** : à chaque complétion d'étape, `TODO` → `WIP` au démarrage, `WIP` → `DONE` après validation utilisateur explicite. Ne pas anticiper le `DONE`.

---

## Hors scope V1

- **Weight / boost de confirmation** : si une note est sémantiquement proche d'une existante (zone moyenne, distance > seuil dédup mais < seuil bruit), bumper un champ `weight` au lieu d'insérer. Backlog COLD.
- **Détection de contradiction** : flag `contradicted_by` quand deux notes opposent leur sens sur (from, about, category). Demande une analyse sémantique fine. Backlog COLD.
- **Enforcement serveur du « 1 appel memorize par tour »** : compteur dans SessionState + rejet du 2e appel. Si dérapage LLM observé.
- **Garde-fou rate-limit** : N notes max par tour, M par activité.
- **Exposition `stats` / `drop` / `reset`** sur le bus : non requis pour le LLM joueur.

---

## Points ouverts (résiduels)

1. **Collection unique** — tous les personnages partagent `"knowledge"` : isolation par filtre `from` uniquement. Suffisant pour V1, à monitorer.
2. **Embedding multilingual** — modèle fixé en dur dans `config.py`, pas configurable par YAML.
3. **`force_cpu`** — paramètre du constructeur non exposé dans la config YAML.
4. **`stats`** — non exposé sur le bus, uniquement accessible en interne.
5. **`get_identifier` (C2)** — utilisé par `recall` (about), à utiliser par `memorize` (about). Cohérent avec l'existant.

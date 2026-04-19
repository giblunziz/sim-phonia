# memory_service — Cahier des charges

## Rôle

Service de **mémoire contextuelle RAG** : retrouver les souvenirs sémantiquement proches d'un personnage pour un contexte donné. Accès en lecture seule sur le bus ; la mutation est gérée en dehors du service (cascades, shadow_memory_service).

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

### `stats`

Observabilité : nombre de documents indexés, modèle d'embedding, chemin ChromaDB.

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

Bus : `"memory"` — un seul handler enregistré à ce jour.

| Code | Paramètres | Retour |
|---|---|---|
| `memory.recall` | `from_char, context, about?, participants?` | `list[dict]` |

**Réponse MCP — format markdown :**

```
# Vos souvenirs à propos de <about>
- Souvenir 1
- Souvenir 2
```

Cas dégradés (personnage `about` inconnu **ou** aucun souvenir remonté) — réponse identique :

```
Je n'ai aucun souvenir de <about>.
```

Le handler MCP rend toujours la main au LLM, jamais d'erreur levée.

---

Non câblés sur le bus (mutation, observabilité) :
- `memory.push` — ajouter un souvenir
- `memory.drop` — supprimer un souvenir
- `memory.reset` — vider la mémoire d'un personnage
- `memory.stats` — observabilité

---

## Configuration YAML (`services.memory_service`)

| Paramètre | Défaut | Description |
|---|---|---|
| `strategy` | `chroma_strategy` | Stratégie à instancier |
| `load_factor` | `1.0` | Multiplicateur `n_results = slots × load_factor` |
| `min_distance` | `1.0` | Seuil post-query (voir ⚠️ ci-dessus) |

Config prod actuelle (`simphonia.yaml`) : `load_factor: 1.5`, `min_distance: 0.7`.

---

## Façade MCP (`simphonia/facade/`)

Serveur MCP SSE exposant `memory.recall` comme tool aux LLM externes. Démarre toujours sur `MCP_PORT` (défaut 8001) en même temps que le serveur HTTP.

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

`memory.recall` est exposé comme tool natif aux providers LLM (Anthropic et Ollama) dans le `chat_service`. Le LLM décide lui-même quand l'appeler.

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

> *"Tu as accès à l'outil `recall` pour consulter tes souvenirs sur quelqu'un avant de répondre. Utilise-le librement si la situation le nécessite."*

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

## Points ouverts

1. **Mutation** — `push / drop / reset` absents du bus : qui les appelle ? via cascades ? via shadow_memory_service ?
2. **Collection unique** — tous les personnages partagent `"knowledge"` : isolation par filtre `from` seulement — suffisant ?
3. **Embedding multilingual** — modèle fixé en dur dans `config.py`, pas configurable par YAML
4. **`force_cpu`** — paramètre du constructeur non exposé dans la config YAML
5. **`stats`** — non exposé sur le bus, uniquement accessible en interne
6. **Absence de `push` dans l'interface ABC** — l'écriture n'est pas contractualisée
7. **`get_identifier` (C2)** — normalisation fuzzy `from_char`/`about` non encore implémentée

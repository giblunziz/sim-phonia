# Etude du service service_character_storage

## Description

`character_storage` est le service d'administration centralisant les accès MongoDB structurés sur deux collections métier : `characters` (fiches personnages schemaless) et `knowledge` (entrées de perception append-only). Il constitue la source de vérité pour les données administrables du projet, et sert de dépendance à `character_service.mongodb_strategy` (lecture des fiches en jeu) et à `memory_service.chroma_strategy` (resync des knowledges vers ChromaDB). Il ne gère aucune logique de jeu ni aucun RAG sémantique — ces aspects restent dans `character_service` et `memory_service`.

## Cahier des charges

### 1. Périmètre

**Ce que le service EST**
- Un service **d'administration** centralisant les accès MongoDB sur `characters` et `knowledge`.
- La **source de vérité** : toute écriture passe par lui, toute lecture côté admin et côté run s'appuie sur lui.
- Une **dépendance technique** pour `character_service.mongodb_strategy` (lecture fiches) et `memory_service.chroma_strategy` (resync knowledges).
- Exposé sur le **bus** `character_storage` (commandes admin) et consommé par simweb admin.

**Ce que le service N'EST PAS**
- Pas de logique de jeu, pas de prompt LLM.
- Pas un moteur RAG — la recherche sémantique reste dans `memory_service`.
- Pas exposé via MCP — ses commandes ne sont pas destinées aux LLM en jeu.
- Pas un ORM — contrat schemaless, documents retournés en `dict` bruts.

### 2. Interface ABC

```python
class CharacterStorageService(ABC):

    # --- characters ---

    @abstractmethod
    def list_characters(self, *, filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def get_character(self, character_id: str) -> dict | None:
        """Retourne None si absent."""

    @abstractmethod
    def put_character(self, character: dict) -> dict:
        """Upsert sur _id. Retourne le document stocké."""

    @abstractmethod
    def delete_character(self, character_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""

    # --- knowledge (append-only) ---

    @abstractmethod
    def list_knowledge(self, *, filter: dict | None = None) -> list[dict]:
        """Liste toutes les entrées knowledge. Consommé par memory_service lors du resync."""

    @abstractmethod
    def get_knowledge(self, knowledge_id: str) -> dict | None: ...

    @abstractmethod
    def push_knowledge(self, entry: dict) -> dict:
        """INSERT — injecte _id (ObjectId) et ts (UTC now) si absents. Retourne le document stocké."""

    @abstractmethod
    def update_knowledge(self, knowledge_id: str, patch: dict) -> dict | None:
        """Met à jour les champs fournis dans patch. Retourne le document mis à jour, None si absent."""

    @abstractmethod
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """Retourne True si supprimé, False si absent."""
```

**Conventions de retour**
- `dict | None` pour les `get_*` — `None` si absent.
- `list[dict]` pour les `list_*` — liste vide si aucun résultat.
- Documents retournés tels quels depuis MongoDB (schemaless).

### 3. Collections MongoDB

#### `characters`

- **Mode** : upsert (lecture, création, mise à jour, suppression).
- **Clé primaire** : `_id` string (slug, ex. `antoine`).
- **Schéma** : schemaless. Même structure que les fiches `resources/characters/*.json`. Chaque consommateur extrait les clés dont il a besoin.

#### `knowledge`

- **Mode** : append-only — INSERT uniquement, jamais d'UPDATE ni de REPLACE.
- **Clé primaire** : `_id` ObjectId MongoDB (généré automatiquement).
- **Schéma réel** (source de vérité côté Mongo et ChromaDB) :

```json
{
  "_id":      { "$oid": "..." },
  "about":    "aurore",
  "activity": "presentation",
  "category": "perceived_traits",
  "from":     "antoine",
  "scene":    "yacht",
  "ts":       { "$date": "2026-04-01T00:00:00.000Z" },
  "value":    "Souriante, chaleureuse, immédiatement à l'aise"
}
```

- **Rationale append-only** : traçabilité, cohérence avec le RAG (on enrichit, on ne modifie pas l'historique).
- `push_knowledge` accepte un dict avec les champs métier (`about`, `activity`, `category`, `from`, `scene`, `value`) ; le service injecte `_id` (ObjectId) et `ts` (datetime UTC now) si absents.

### 4. Contrat schemaless

- Documents stockés/retournés en `dict` bruts.
- Pas de modèle Pydantic imposé.
- Une validation minimale à l'entrée des méthodes d'écriture (clés structurelles présentes, types primitifs cohérents) est acceptable mais n'impose rien sur le contenu métier.
- Seuls `_id` et `ts` sont gérés par le service pour `knowledge`. Tout le reste est libre.

### 5. Intégration avec `character_service.mongodb_strategy`

- `mongodb_strategy` ne se connecte **plus directement** à MongoDB — il reçoit une instance de `CharacterStorageService` via le bootstrap et délègue.
- `list_characters()` → `character_storage.list_characters()`
- `get_character(name)` → `character_storage.get_character(name)`
- Les transformations spécifiques au mode jeu (normalisation fuzzy via `_resolve_identifier`, cache mémoire) restent dans `mongodb_strategy` — `character_storage` retourne du brut.

### 6. Intégration avec `memory_service.chroma_strategy`

- `chroma_strategy` ne touche pas à MongoDB directement.
- La commande bus `memory/resync` déclenche : `character_storage.list_knowledge()` → réindexation complète dans ChromaDB.
- Pour chaque entrée knowledge, les champs ChromaDB sont : `document = entry["value"]`, metadata = `{about, activity, category, from, scene, ts}`.
- Politique : **Mongo = source de vérité**, **Chroma = index dérivé reconstructible à volonté**.
- **`character_storage` n'a aucune connaissance de `memory_service`** — couplage zéro dans les deux sens. C'est `memory_service` qui appelle `character_storage`, jamais l'inverse.

### 7. Exposition sur le bus

Bus : `character_storage`. Commandes d'administration — **pas de façade MCP**.

| Code | Méthode | Description |
|---|---|---|
| `characters.list` | `list_characters` | Liste des fiches (dict bruts) |
| `characters.get` | `get_character` | Fiche par `_id` |
| `characters.put` | `put_character` | Upsert d'une fiche |
| `characters.delete` | `delete_character` | Suppression par `_id` |
| `knowledge.list` | `list_knowledge` | Toutes les entrées (consommé aussi par `memory/resync`) |
| `knowledge.get` | `get_knowledge` | Entrée par `_id` |
| `knowledge.push` | `push_knowledge` | Nouvelle entrée (INSERT, injecte `_id` et `ts`) |
| `knowledge.update` | `update_knowledge` | Mise à jour partielle par `_id` |
| `knowledge.delete` | `delete_knowledge` | Suppression par `_id` |

### 8. Exposition dans simweb (admin)

Sidebar : nouvelle entrée **Storage** avec deux sous-panneaux.

#### Panneau `Characters`

Reprend et remplace l'actuel `CharactersPanel` (qui passait par `character_service`) :
- Tableau : `_id`, `updated_at` + champs libres.
- Fiche détaillée (JSON formaté).
- Actions : créer, mettre à jour, supprimer.

#### Panneau `Knowledge`

Nouveau — même mode grille que Characters :
- Grille des entrées tri anti-chronologique (`ts` desc) : colonnes `from`, `about`, `category`, `scene`, extrait de `value`, `ts`. Pas de colonne `_id` (auto-généré MongoDB, non affiché).
- CRUD complet : création, édition, suppression.
- Formulaire : `from`, `about`, `activity`, `category`, `scene`, `value` (textarea). Le `_id` et le `ts` sont injectés par le service à l'insertion.

> **Note** : le bouton Resync Chroma (`memory/resync`) est dans le panneau **Memory** de simweb, pas ici. `character_storage` n'a aucune connaissance de ChromaDB.

### 9. Configuration (`simphonia.yaml`)

```yaml
services:
  character_storage:
    strategy: mongodb_strategy
    database_uri: ${MONGO_URI}
    database_name: ${MONGO_DATABASE}
    collections:
      characters: characters
      knowledge: knowledge
```

Même mécanique dotenv que les autres services. `collections` permet de renommer les collections sans toucher au code.

### 10. Arborescence cible

```
src/simphonia/services/character_storage/
    __init__.py              # ABC CharacterStorageService + factory + init/get
    strategies/
        __init__.py
        mongodb_strategy.py  # MongoCharacterStorageService (pymongo)
```

### 11. Dépendances

- `pymongo` — déjà présent. Pas de nouvelle dépendance runtime.

## Décisions de conception

| Num | Question | Décision retenue | Raison |
|---|---|---|---|
| 1 | Sync Mongo→Chroma | `memory/resync` bus command — `chroma_strategy` appelle `character_storage.list_knowledge()` | Mongo = source de vérité, Chroma = index dérivé. Pas de stratégie alternative mongo-only. |
| 2 | knowledge dans quel service ? | Intégré dans `character_storage` (pas de `knowledge_service` séparé) | Domaine administration — tout l'accès MongoDB administrable dans un seul service. |
| 3 | CRUD knowledge | CRUD complet (push/update/delete) exposé dès v1 | simweb admin expose une grille éditable ; le service ne connaît pas l'usage, il expose les primitives. |
| 4 | Schéma knowledge | Schemaless, champs réels : `about`, `activity`, `category`, `from`, `scene`, `ts`, `value` | ISO au schéma MongoDB existant et à ce que `chroma_strategy` consomme déjà. |

## Plan d'implémentation

### Décisions validées

| # | Question | Décision |
|---|---|---|
| R1 | Sérialisation ObjectId/datetime | Le service convertit `_id → str` et `ts → ISO-8601` dans tous les dicts retournés |
| R2 | Cache `MongoCharacterService` après refactor | Cache maintenu, `reset()` le vide et le repeuple depuis `character_storage` |
| R3 | Init conditionnelle | MongoDB obligatoire — `character_storage.init()` inconditionnel, fail-fast si absent |
| R4 | `database_uri`/`database_name` dans `character_service` YAML | Supprimés — un seul point de déclaration Mongo dans `character_storage` |
| R5 | Édition fiches personnages simweb | JSON brut (textarea), schemaless |

### Étapes

```
1 → 2 → 3 → 4
          ↓   ↓
          5   6
              ↓
              7 → 8
                → 9
                → 10
          → 11 (docs, en dernier)
```

| # | Étape | Fichiers | Dépend de |
|---|---|---|---|
| 1 | ABC + factory + singleton `character_storage` | `services/character_storage/__init__.py` | — |
| 2 | `mongodb_strategy` (CRUD complet, sérialisation) | `strategies/mongodb_strategy.py` | 1 |
| 3 | Câblage YAML + bootstrap | `simphonia.yaml`, `bootstrap.py` | 2 |
| 4 | Commandes bus `character_storage` | `commands/character_storage.py` | 3 |
| 5 | Refactor `character_service.mongodb_strategy` | `mongodb_strategy.py`, `character_service/__init__.py`, YAML | 3 |
| 6 | Commande `memory/resync` | `memory_service/__init__.py`, `chroma_strategy.py`, `commands/memory.py` | 3 |
| 7 | API JS client | `api/simphonia.js` | 4, 6 |
| 8 | simweb panneau `Storage > Characters` | `StorageCharactersPanel.jsx`, `Sidebar.jsx`, `App.jsx` | 7 |
| 9 | simweb panneau `Storage > Knowledge` | `StorageKnowledgePanel.jsx` | 7 |
| 10 | simweb bouton Resync Chroma dans `MemoryPanel` | `MemoryPanel.jsx` | 7 |
| 11 | Documentation | `CLAUDE.md`, `configuration.md`, `character_service.md`, `memory_service.md`, `simweb.md` | tout |

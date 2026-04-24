# shadow_storage

Service de capture passive du **subconscient des joueurs** — la matière brute alimentée par les sorties LLM (tous les champs psychiques et expressifs : `inner`, `body`, `expected`, `noticed`, `talk`, `mood`, etc.) tour après tour. Persistance Mongo + ChromaDB. Aucune interprétation, aucune analyse — juste un journal intime sémantiquement indexé, prêt à être consommé par **Tobias** (le `shadow_memory_service`, à venir avec H5).

## Contexte

### Subconscient ≠ psy_memory

Deux collections distinctes, deux rôles distincts :

- **`subconscient`** (cette spec) — matière brute, par joueur. Append-only. Alimentée passivement par capture des exchanges LLM. **Input** du futur Tobias.
- **`psy_memory`** (à venir, doc `cognition.md`) — analyses, scores, observations cognitives écrites par Tobias lui-même. **Output** du futur Tobias.

Cette spec ne couvre que `subconscient`. `psy_memory` viendra avec H5.

### Pourquoi maintenant

Avant d'implémenter Tobias (cascades AOP sur `memory/recall`, scoring DISC, intervention, etc.), on a besoin de **données**. Le subconscient est un préalable matériel : il faut des mois de gameplay accumulés avant de pouvoir tuner les seuils d'intervention. Cette V1 met en place la captation passive ; tout le travail cognitif viendra ensuite.

### Contrainte d'architecture forte

Demande Valère 2026-04-24 : **zéro hook explicite à Tobias dans `activity_service` ou `chat_service`**. Le service doit s'alimenter via un mécanisme **passif et générique**, sans que les producteurs (engine, chat) sachent qu'il existe.

→ Solution retenue : **bus `messages` + observer pattern** sur le bus core.

## Architecture

### Bus `messages` — canal pub/sub central

Nouveau bus dont la fonction est de **republier en fire-and-forget** les messages parsés en sortie de LLM, depuis tous les services producteurs. Schéma uniforme, payload schemaless.

```
┌───────────────────────────────────────────────────────────────┐
│ Producteurs                                                    │
│  ┌─────────────────────┐    ┌──────────────────────────────┐  │
│  │ activity_engine     │    │ chat_service/default_strategy│  │
│  │ après _build_exchange│    │ après parsing JSON           │  │
│  └──────────┬──────────┘    └────────────┬─────────────────┘  │
│             └─────────────┬──────────────┘                      │
│                           ▼                                      │
│                  bus("messages").dispatch("published", {...})   │
└───────────────────────────┼───────────────────────────────────┘
                            │ fan-out passif (observer pattern)
                            ▼
┌───────────────────────────────────────────────────────────────┐
│ Subscribers                                                     │
│   shadow_storage.feed(payload)                                  │
│   (futurs : metrics_service, audit_log, etc.)                   │
└───────────────────────────────────────────────────────────────┘
```

**Propriétés** :
- Le bus a UNE commande no-op `published` (callback `lambda **kw: None`) qui sert de canal nommé
- Les subscribers sont notifiés **après** l'exécution du callback no-op
- Best-effort : exception d'un subscriber → log warning, n'impacte pas le dispatch ni les autres subscribers
- Pas de garantie d'ordre entre subscribers
- Synchrone (pas de thread) — un subscriber lent ralentit le tour de jeu, à ne jamais oublier

### Structure du message dispatché

```python
{
    "bus_origin": "activity",       # str — source du message
    "from_char":  "antoine",         # str | None — pivot pour router le subconscient
    "payload":    { ... }            # dict schemaless — le contenu brut tel que produit
}
```

| Champ | Obligatoire | Description |
|---|---|---|
| `bus_origin` | ✓ | Identifie la source. V1 : `"activity"`, `"chat"`. Extensible. |
| `from_char` | ✗ | Slug du personnage à qui appartient le message. `None` si non applicable (le shadow_storage filtre dans ce cas). |
| `payload` | ✓ | Dict brut. Aucune contrainte de schéma — chaque producteur émet ce qui a du sens pour lui. Le shadow_storage admet par défaut tout sauf les métadonnées listées dans `excluded_keys`. |

### Producteurs (1 ligne par site)

**`activity_service/engine.py`** — après `_build_exchange()` :

```python
exchange = _build_exchange(session.round, slug, raw_response or "", parsed)
session.exchange_history.append(exchange)
session.instance.setdefault("exchanges", []).append(exchange)
_persist(session)

# Fan-out vers le bus messages — fire-and-forget
default_registry().bus("messages").dispatch("published", {
    "bus_origin": "activity",
    "from_char":  slug,
    "payload":    exchange,
})
```

**`chat_service/strategies/default_strategy.py`** — après `parse_llm_json` :

```python
default_registry().bus("messages").dispatch("published", {
    "bus_origin": "chat",
    "from_char":  responder,
    "payload":    parsed,
})
```

Aucune autre logique métier n'est portée par le producteur. C'est juste un appel fire-and-forget.

### Mécanisme `subscribe` dans `core/bus.py`

Ajout au `Bus` existant d'un mécanisme observer pattern :

```python
class Bus:
    def __init__(self, name: str) -> None:
        ...
        self._listeners: list[Callable[[dict], None]] = []

    def subscribe(self, listener: Callable[[dict], None]) -> None:
        """Enregistre un listener appelé après chaque dispatch sur ce bus.

        Le listener reçoit uniquement le payload (pas de code, pas de result).
        Best-effort : exceptions logguées, n'impactent pas le dispatch.
        Synchrone : tenir compte du coût d'exécution.
        """
        self._listeners.append(listener)

    def dispatch(self, code, payload=None):
        cmd = self.get(code)
        try:
            result = cmd.callback(**(payload or {}))
        except (CommandNotFound, DispatchError):
            raise
        except Exception as exc:
            raise DispatchError(self.name, code, exc) from exc

        # Fan-out post-call vers les listeners
        for listener in self._listeners:
            try:
                listener(payload or {})
            except Exception as exc:
                log.warning(
                    "[bus.%s] listener %r failed: %s",
                    self.name, getattr(listener, '__qualname__', listener), exc
                )

        return result
```

**Granularité** : abonnement au **bus entier**, pas par commande. Cohérent avec la philosophie schemaless — le subscriber filtre lui-même ce qui l'intéresse dans le payload.

### Service `shadow_storage`

Pattern projet standard : `services/shadow_storage/` avec ABC + factory + stratégies.

```
services/shadow_storage/
├── __init__.py           # ABC ShadowStorageService + factory + init/get
└── strategies/
    ├── __init__.py
    └── mongodb_strategy.py   # implémentation Mongo + ChromaDB
```

**ABC** :

```python
class ShadowStorageService(ABC):

    @abstractmethod
    def feed(self, message: dict) -> None:
        """Listener générique branché sur le bus messages.
        Filtre interne : ignore si pas de from_char, ou si tous les champs sont exclus."""

    @abstractmethod
    def list_entries(self, filter: dict | None = None,
                     skip: int = 0, limit: int = 50) -> list[dict]:
        """Liste paginée. filter : dict Mongo direct."""

    @abstractmethod
    def count_entries(self, filter: dict | None = None) -> int:
        """Pour la pagination UI."""

    @abstractmethod
    def get_entry(self, entry_id: str) -> dict:
        """Récupère une entrée par _id."""

    @abstractmethod
    def update_entry(self, entry_id: str, doc: dict) -> dict:
        """Update intégral du document (resync chroma à faire à part)."""

    @abstractmethod
    def delete_entry(self, entry_id: str) -> int:
        """Suppression Mongo + Chroma. Retourne le count supprimé."""

    @abstractmethod
    def resync_chroma(self) -> int:
        """Reconstruction de la collection ChromaDB depuis Mongo. Retourne le count indexé."""
```

### Filtre côté `feed` — `excluded_keys` (denylist)

**Principe** : on capture **tout par défaut**, on exclut uniquement les métadonnées structurelles (identifiants, indices de tour, horodatages). Tout le reste est *présumé utile* — y compris les champs PUBLIC du jeu (`talk`, `mood`, `body`, `action`) car Tobias détecte l'écart adapté/réel et a donc besoin des deux faces.

**Pourquoi denylist plutôt qu'allowlist** : le schéma des exchanges évolue en design actif. Avec une allowlist, ajouter un nouveau champ pertinent (`dream`, `body_signal`, `flash`, ...) demande une modif YAML supplémentaire et risque l'oubli. Avec une denylist, le nouveau champ est ingéré automatiquement — on n'ajoute à `excluded_keys` que si on constate du bruit.

**Distinction avec `PRIVATE_FIELDS` du `context_builder`** : aucun rapport. `PRIVATE_FIELDS` est un clivage de **visibilité du jeu** (cachable aux autres joueurs). `excluded_keys` est un filtre **structurel/métadonnées** pour le subconscient. Les deux concepts ne se croisent pas.

Configuration YAML (cf. section *Configuration YAML* plus bas) :

```yaml
excluded_keys:
  - from
  - to
  - round
  - ts
  - _id
  - id
```

Code :

```python
def feed(self, message: dict) -> None:
    from_char = message.get("from_char")
    if not from_char:
        return  # pas de pivot, on jette

    payload = message.get("payload") or {}
    candidates = self._extract_candidates(payload)
    if not candidates:
        return  # tout est exclu → rien à garder

    self._store(
        from_char=from_char,
        bus_origin=message.get("bus_origin", "unknown"),
        payload=payload,
    )

def _extract_candidates(self, payload: dict) -> dict:
    """Récolte tous les champs feuilles non exclus, en aplatissant les
    wrappers connus (`public`, `private`).

    - Les wrappers eux-mêmes (clés `public`/`private`) sont déballés
      automatiquement (ce sont des conteneurs, pas des feuilles à indexer)
    - Tout champ feuille non vide et non listé dans `self._excluded_keys`
      est conservé
    - En cas de collision entre niveaux (ex: `from` à plat ET dans `private`),
      la première occurrence rencontrée gagne — sans importance car le `from`
      est exclu de toute façon."""
    found = {}
    for source in (payload.get("private") or {},
                   payload.get("public")  or {},
                   payload):
        for k, v in source.items():
            if k in ("private", "public"):
                continue            # wrapper déjà déballé
            if k in self._excluded_keys:
                continue
            if not v:
                continue
            if k not in found:
                found[k] = v
    return found
```

### Schéma collection Mongo `subconscient`

Schemaless mais convention :

| Champ | Type | Description |
|---|---|---|
| `_id` | ObjectId | Auto-généré |
| `from` | str | Slug du personnage (= `from_char` du message) |
| `bus_origin` | str | `"activity"` / `"chat"` / autre |
| `payload` | dict | Le contenu brut tel que reçu, intégral (le filtre `excluded_keys` ne sert qu'au test d'admission et à l'embedding, pas à l'écriture Mongo) |
| `ts` | datetime | Horodatage de capture (côté serveur, UTC ISO-8601) |

**Note** : on stocke le **payload complet**, sans appliquer `excluded_keys` à l'écriture Mongo. La raison : Tobias aura besoin du contexte structurel (round, IDs, etc.) pour ses analyses futures. Le filtre `excluded_keys` sert uniquement à (a) décider si l'exchange a de la matière à ingérer (test d'admission) et (b) construire le texte d'embedding pour ChromaDB.

### Indexation ChromaDB

Collection séparée du `knowledge` joueur — nom : `subconscient`.

**Embedding** : concaténation de tous les champs admis (= non listés dans `excluded_keys`), séparateur `\n`. Ordre déterministe (alphabétique sur les clés) pour que l'embedding soit reproductible. C'est le matériau psychique + expressif brut.

**Métadonnées Chroma** :
- `_id` Mongo (string) — clé de jointure
- `from` (str)
- `bus_origin` (str)
- `ts` (str ISO-8601)

**Modèle d'embedding** : même que `memory_service` → `paraphrase-multilingual-MiniLM-L12-v2`. Mutualisation possible plus tard, V1 on instancie séparément.

## Configuration YAML

```yaml
services:
  shadow_storage:
    strategy: mongodb_strategy
    database_uri: ${MONGO_URI}
    database_name: ${MONGO_DATABASE}
    collection: subconscient
    chroma_collection: subconscient
    subscriptions:
      - messages              # bus à écouter (V1 : un seul)
    excluded_keys:            # denylist — métadonnées structurelles, le reste est admis et indexé
      - from
      - to
      - round
      - ts
      - _id
      - id
```

**Champs** :
- `strategy` : pour l'instant `mongodb_strategy` uniquement
- `database_uri` / `database_name` : Mongo (interpolé depuis `.env`)
- `collection` : nom Mongo
- `chroma_collection` : nom de la collection ChromaDB dédiée (jamais partagé avec `knowledge`)
- `subscriptions` : liste de noms de bus à écouter. Le bootstrap appelle `bus(name).subscribe(svc.feed)` pour chaque entrée.
- `excluded_keys` : **denylist** des champs à ignorer (métadonnées structurelles). Tout champ non listé est admis automatiquement et participera à l'embedding ChromaDB. Permet d'absorber sans friction tout nouveau champ ajouté au schéma des exchanges.

## Bootstrap

Ordre d'initialisation :

```python
# bootstrap.py
configuration_service.init(...)
character_storage.init(...)
activity_storage.init(...)
character_service.init(...)
memory_service.init(...)
chat_service.init(...)
tools_service.init(...)

# Crée le bus messages (commande no-op published)
discover("simphonia.commands")

# Crée le service et l'abonne aux bus listés dans subscriptions
shadow_storage.init(configuration_service.section("services.shadow_storage"))
```

Le bus `messages` est créé via discovery normale d'une commande `commands/messages.py` :

```python
@command(bus="messages", code="published",
         description="Canal de fan-out — payload schemaless, fire-and-forget.")
def published_command(**kwargs):
    """No-op. Le travail est fait par les listeners (cf. Bus.subscribe)."""
    return None
```

Au moment de `shadow_storage.init(section)`, on parcourt `subscriptions` et on s'abonne :

```python
def init(section: dict) -> None:
    global _instance
    _instance = build_shadow_storage(section)
    for bus_name in section.get("subscriptions", []):
        try:
            default_registry().bus(bus_name).subscribe(_instance.feed)
        except BusNotFound:
            log.warning("subscription bus %r introuvable", bus_name)
```

## API fonctionnelle (commandes bus)

Toutes les commandes sur le bus **`shadow_storage`**. Aucune `mcp=True` (admin uniquement, pas accessible aux LLM).

| Commande | Payload | Retour |
|---|---|---|
| `entries.list` | `{filter?: dict, skip?: int, limit?: int}` | `{entries: list[dict], total: int}` |
| `entries.get` | `{entry_id: str}` | `dict` |
| `entries.update` | `{entry_id: str, doc: dict}` | `dict` (le document mis à jour) |
| `entries.delete` | `{entry_id: str}` | `int` (count supprimé) |
| `chroma.resync` | `{}` | `int` (count indexé) |

`entries.list` filter accepte directement la structure Mongo : `{from: "antoine", bus_origin: "activity"}`. Pas de DSL custom.

## UI simweb — panneau **Tobias > Subconscient**

### Sidebar

Nouvelle rubrique **Tobias** dans la sidebar (au même niveau que *Storage*, *Atelier*, *Jeu*), avec un sous-item **Subconscient** pour V1. La rubrique est extensible : *Psy Memory*, *Dashboard cognitif*, etc. viendront s'y greffer.

### Écran `ShadowDataPanel.jsx`

```
┌─ Filtres ────────────────────────────────────────────────────┐
│ Bus origin : [— tous ▼]    From char : [— tous ▼]   [↻]      │
└──────────────────────────────────────────────────────────────┘

┌─ Entries (1234 total)                            [Resync Chroma] ─┐
│ ┌────────────┬───────────┬────────────┬────────────┬──────────┐ │
│ │ _id        │ from      │ bus_origin │ ts         │ actions  │ │
│ ├────────────┼───────────┼────────────┼────────────┼──────────┤ │
│ │ 6627a...   │ antoine   │ activity   │ 14:32:18   │ 👁 ✎ ✕   │ │
│ │ 6627a...   │ manon     │ activity   │ 14:32:05   │ 👁 ✎ ✕   │ │
│ │ ...        │           │            │            │          │ │
│ └────────────┴───────────┴────────────┴────────────┴──────────┘ │
│ ◀ Page 1 / 25 ▶                                                  │
└──────────────────────────────────────────────────────────────────┘

(modale au clic 👁 → JSON formaté du payload)
(modale au clic ✎ → JsonEditor sur le doc complet)
(confirmation au clic ✕)
```

### Composants & comportement

- **Filtres** :
  - `bus_origin` : dropdown peuplé dynamiquement (`distinct` Mongo côté serveur, ou hardcodé `["activity", "chat"]` V1)
  - `from_char` : dropdown peuplé via `character/list`
  - Bouton ↻ pour recharger
  - Pas de filtre date, pas de recherche full-text (YAGNI)
- **Pagination** : `.skip(N*size).limit(50)` côté serveur. Boutons précédent/suivant + indicateur page courante / total.
- **Actions par ligne** :
  - 👁 *View* → modale lecture seule, JSON formatté du `payload` uniquement (pas du wrapper Mongo)
  - ✎ *Edit* → modale `JsonEditor` sur le document complet (édition libre, validation JSON live, bouton Sauver)
  - ✕ *Delete* → confirmation simple, puis appel `entries.delete`
- **Resync Chroma** : bouton en haut à droite, confirmation, appel `chroma.resync`. Affiche le count indexé en toast.

### API frontend (`api/simphonia.js`)

5 fonctions miroir des commandes bus :

```js
shadowEntriesList(filter, skip, limit)
shadowEntryGet(entryId)
shadowEntryUpdate(entryId, doc)
shadowEntryDelete(entryId)
shadowChromaResync()
```

## Cycle de vie d'une entrée

1. LLM produit une réponse JSON
2. Service producteur (engine ou chat) la parse
3. Service producteur dispatche sur `messages/published` (fire-and-forget)
4. Bus `messages` exécute le callback no-op puis fan-out vers les listeners
5. `shadow_storage.feed(payload)` est appelé
6. Filtre : `from_char` présent + au moins un champ admis (= non exclu) → on poursuit, sinon STOP
7. Push Mongo (insert) du payload complet
8. Embed concat des champs admis → push Chroma (avec `_id` Mongo)
9. Log info, retour None (fire-and-forget)

Si une étape échoue, log warning, le tour de jeu continue. Le subconscient est best-effort par design.

## Hors scope V1 (YAGNI)

- API `recall` / `query` sur le subconscient (viendra avec H5 / Tobias runtime)
- Indexation incrémentale ChromaDB (V1 : full resync sur demande, pas auto-sync à chaque insert — on évalue le besoin après)
- Stratégie alternative non-Mongo (`json_strategy` etc.)
- Filtre de capture par règle complexe (V1 : simple denylist `excluded_keys`)
- Compactage / archivage des entrées anciennes
- Édition assistée structurée (V1 : JSON brut)
- Recherche full-text dans le payload
- Filtre date (range from/to)
- Notifications SSE de nouvelles entrées (V1 : refresh manuel)
- Alimentation depuis sources externes au bus `messages` (V1 : seul ce bus est subscribed)

## Préalables / dépendances

- **Aucun bloquant** — toute l'infra existe déjà :
  - `core/bus.py` (juste à étendre avec `subscribe`)
  - `services/character_storage` pour réutiliser le pattern
  - `memory_service.chroma_strategy` pour l'inspiration ChromaDB
  - `simweb` panel pattern (cf. `StorageCharactersPanel`, `ToolsPanel`)

## Plan d'implémentation (T1→T9)

| # | Étape | Livrable |
|---|---|---|
| **T1** | `Bus.subscribe` + dispatch fan-out | `core/bus.py` étendu, TU sur le mécanisme observer |
| **T2** | Bus `messages` + commande no-op `published` | `commands/messages.py`, intégration au boot via discovery |
| **T3** | Producteurs : dispatch fan-out | 1 ligne dans `engine.py`, 1 ligne dans `default_strategy.py` |
| **T4** | Service `shadow_storage` (ABC + factory + mongo strategy) | `services/shadow_storage/` complet, init via YAML |
| **T5** | ChromaDB intégration + filtre `_extract_private` + push atomique | `mongodb_strategy.py` complet |
| **T6** | Commandes bus `shadow_storage/*` | `commands/shadow_storage.py` (5 commandes) |
| **T7** | Bootstrap : init + subscription depuis YAML | `bootstrap.py` updaté, section YAML opérationnelle |
| **T8** | Front : sidebar + ShadowDataPanel + 5 endpoints API | `simweb` complet pour V1 |
| **T9** | Tests + validation E2E | TU sur `_extract_private` / `feed` filter / fan-out, validation utilisateur sur un run réel |

Chaque étape testée individuellement, validée par l'utilisateur avant de passer à la suivante.

# character_service

Service utilitaire fournissant l'accès aux fiches de personnages (NPC, PC) du jeu. Premier d'une série de services utilitaires partagés (scene_service, etc.).

## Cahier des charges

### Contexte

Le `character_service` fait partie des **services utilitaires** consommés par plusieurs composants du jeu. Il doit être accessible à la fois :

- **via un bus** (`character`) — pour l'intégration événementielle avec le reste du système simphonia ;
- **en tant que service exportable** — pour un usage direct (in-process) par d'autres composants qui en dépendent.

### API fonctionnelle

Le service expose, pour cette première itération, deux fonctions :

| Fonction | Description | Retour |
|---|---|---|
| `get_character_list` | Retourne la liste des identifiants (`_id`) des personnages connus | `list[str]` |
| `get_character`     | Retourne la fiche complète d'un personnage donné                  | `dict` (fiche complète, **schemaless**) |
| `get_identifier`    | Résolution fuzzy d'un nom (exact → token → partiel) vers `_id`    | `str \| None` |
| `get_type`          | Retourne le type du personnage — `player` / `npc` / `human` (fallback safe `player`) | `str` |
| `reset`             | Recharge toutes les fiches depuis la source de données            | `int` (nombre de fiches chargées) |

Ces commandes :

- sont **publiées sur le bus `character`** (dispatch via le bus event-bus simphonia) ;
- sont **exportées comme service** (appel direct par d'autres composants).

**Sémantique de `reset`** : le comportement dépend de la stratégie active.

- `json_strategy` → rescan intégral du répertoire `./resources/characters/` et reconstruction du cache.
- `mongodb_strategy` → nouvel appel `db.characters.find()` et repopulation du cache.

Dans tous les cas, `reset` est **destructif côté cache** : tout état mémoire est vidé puis reconstruit depuis la source de vérité.

### Indexation des fiches — normalisation "à la MongoDB"

La clé d'indexation **n'est pas le nom de fichier** mais le champ **`_id`** de la fiche elle-même (convention MongoDB). Le nom de fichier n'a qu'une valeur documentaire. Les stratégies doivent :

- ignorer (avec warning) les fiches sans `_id` valide ;
- ignorer (avec warning) les doublons d'`_id` — premier arrivé, premier servi.

### Choix d'architecture : schemaless

`get_character` retourne un **`dict` brut**, **pas un schéma formalisé** (pas de modèle Pydantic / dataclass contraignant la structure de la fiche).

- C'est un choix d'architecture assumé : les fiches évoluent librement côté contenu, le runtime du `character_service` n'a **pas** à connaître les attributs d'une fiche.
- Chaque **service/consommateur** est responsable de savoir quelles clés il lit et comment les interpréter — la connaissance du schéma est **déportée chez l'appelant**.
- Un **dictionnaire des clés gérées** (par le code, pour les clés explicitement consommées) pourra être exposé au besoin — en support, pas en contrainte. Jamais comme source de vérité normative sur la fiche.

### Sémantique de retour : référence cache vs source canonique

`get_character` renvoie **la référence directe du `dict` en cache** (pas de `deepcopy`). Raison fonctionnelle : certains services consommateurs sont amenés à **enrichir la fiche en mémoire** pendant une session avec des clés de runtime (états éphémères, annotations, caches dérivés). Ces enrichissements sont partagés entre consommateurs via la référence commune — c'est voulu.

Règles qui encadrent ce comportement :

- La **source** (fichiers JSON pour `json_strategy`, documents Mongo pour `mongodb_strategy`) est **canonique et read-only**. Aucune mutation du `dict` en cache n'est jamais propagée vers la source. Le service n'écrit pas.
- Le **cache mémoire** est, lui, mutable et partagé. Les clés runtime ajoutées par les services y survivent tant que le process tourne.
- La commande **`reset`** vide le cache et le reconstruit depuis la source — c'est le mécanisme officiel pour effacer les enrichissements accumulés en session.

Corollaire : les clés runtime ne sont jamais persistées. Un redémarrage (ou un `reset`) les fait disparaître. Si un service veut persister un enrichissement, c'est à lui de le gérer dans sa propre couche de stockage.

### Attribut `type` (optionnel, schemaless)

Chaque fiche peut déclarer un attribut racine **`type`** pris dans la whitelist figée : `player`, `npc`, `human`.

- **Défaut** : `player` — tout `character.type` absent, invalide, ou valeur hors whitelist est traité comme `player`.
- **Lecture safe** : `character_service.get().get_type(name)` applique le fallback de bout en bout (fiche introuvable → `player`, attribut absent → `player`, valeur inconnue → `player`). Jamais d'exception.
- **Consommation** : les consumers MCP (`chat_service`, `activity_engine`, `context_builder.get_tools`) dérivent le rôle MCP du LLM incarné via `get_type(speaker)` et l'utilisent pour filtrer `mcp_tool_definitions(role=...)` et `mcp_tool_hints(role=...)`.
- **Constantes exportées** : `CHARACTER_TYPES = ("player", "npc", "human")` et `DEFAULT_CHARACTER_TYPE = "player"` depuis `services.character_service`.
- **Commande bus** : `character/types` → `list[str]` (les types autorisés). Consommée par simweb pour peupler dynamiquement le select de saisie.

Sémantique par type :

| Type | LLM incarné ? | Tools MCP exposés |
|---|---|---|
| `player` | Oui | Tools `mcp_role="player"` (recall, memorize, …) |
| `npc`    | Oui | Tools `mcp_role="npc"` (liste vide aujourd'hui — à définir) |
| `human`  | Non (input clavier) | Aucun (côté moteur, un `human` ne devrait pas passer par la boucle LLM) |

Cohérent avec l'architecture schemaless : l'attribut n'est pas obligatoire, le fallback `player` préserve le comportement historique.

### Architecture : interface + stratégies (provider)

L'implémentation suit un pattern **interface + implémentations interchangeables** :

- Une **interface** `character_service` définit le contrat (les deux fonctions ci-dessus).
- Plusieurs **providers/stratégies** implémentent ce contrat :
  - `json_strategy` — lecture des fiches depuis des fichiers JSON locaux (implémentation de départ).
  - `mongodb_strategy` — lecture depuis une collection MongoDB `characters`.
  - *(d'autres stratégies pourront s'ajouter plus tard.)*

### Stratégie initiale : `json_strategy`

- Source : un fichier JSON par personnage dans `./resources/characters/`.
- Le nom du fichier (sans extension) correspond à l'identifiant du personnage (ex. `aurore.json` → `aurore`).
- `get_character_list` énumère ces fichiers et renvoie la liste des identifiants.
- `get_character(name)` charge et retourne le contenu JSON parsé du fichier correspondant.

Personnages actuellement disponibles : `aurore`, `camille`, `diane`, `elise`, `julien`, `manon`, `marc`, `theo`.

### Configuration du backend

Le choix de la stratégie active est piloté par un **fichier de configuration YAML** :

- **Fichier par défaut** : `simphonia.yaml` à la racine du module `simphonia`.
- **Override en ligne de commande** : `--configuration <path_to_configuration/configuration_file.yaml>` permet de pointer un autre fichier.

**Schéma du YAML** — nœud `services/<nom_du_service>/strategy` :

```yaml
services:
  character_service:
    strategy: json_strategy   # stratégie active ; ici l'implémentation JSON locale
```

Ce schéma est générique : il s'applique à tous les services utilitaires à venir (`scene_service`, etc.).

### Documentation de la configuration

En parallèle de chaque élément de configuration introduit, un fichier **`./documents/configuration.md`** doit être maintenu avec la **documentation exhaustive** de :

- tous les paramètres disponibles ;
- toutes les options/valeurs possibles pour chaque paramètre.

Exemple : si `character_service` propose `json_strategy` et `mongodb_strategy`, les deux options doivent être documentées dans `configuration.md` (prérequis, format de la source, comportement attendu, etc.).

Ce fichier doit rester **synchronisé à chaque évolution** des paramètres (ajout/suppression/renommage d'option ou de stratégie).

### Contraintes transverses

- Publication bus `character` **ET** export service in-process (double exposition obligatoire).
- Chaque nouvelle stratégie = nouvelle entrée documentée dans `configuration.md`.
- Respect de la convention projet : dépendances runtime déclarées à la fois dans `pyproject.toml` et `requirements.txt`.

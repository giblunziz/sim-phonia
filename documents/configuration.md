# Configuration simphonia

Documentation exhaustive de tous les paramètres de configuration du module `simphonia`.

## Rôle du fichier

Le fichier YAML de configuration est le **point d'entrée de paramétrage** du module `simphonia`. Il centralise toutes les options externalisées (choix de stratégies de services, paramètres runtime, etc.).

### Principes directeurs

- **Tout paramètre externalisé doit avoir une valeur par défaut** dans le fichier de configuration livré avec le module. Démarrer sans configuration custom doit toujours produire un runtime fonctionnel.
- **Certains paramètres peuvent être surchargés en ligne de commande** (précisé au cas par cas dans la documentation du paramètre).
- **Un seul fichier, un seul format** : YAML.
- **Interpolation d'environnement** : les valeurs scalaires peuvent référencer des variables d'environnement avec la syntaxe `${VAR}` ou `$VAR`. L'interpolation est appliquée récursivement sur tous les scalaires string de l'arbre via `os.path.expandvars`. Les variables non définies restent littérales — c'est au service consommateur de détecter l'absence et de lever une erreur explicite au startup.
- Les variables d'environnement peuvent elles-mêmes provenir d'un fichier `.env` à la racine du projet (chargé automatiquement par `python-dotenv` au bootstrap).
- Les paramètres sont documentés **au fur et à mesure** de leur introduction. Toute évolution (ajout / renommage / suppression d'option) doit être répercutée ici dans le même commit.

## Service d'accès à la configuration

La configuration chargée au startup est exposée aux autres services via le **`configuration_service`** (`src/simphonia/services/configuration_service.py`). Les services **ne lisent jamais le fichier eux-mêmes** — ils interrogent ce service, qui garantit :

- un **chargement unique** au startup (idempotent) ;
- des **copies défensives** (`deepcopy`) sur toute sous-section ou snapshot retournés — aucune mutation accidentelle ne peut remonter vers le snapshot racine ;
- l'**interpolation ${ENV}** appliquée une fois pour toutes à la charge.

API :

- `configuration_service.init(path=None)` — charge la configuration (appelé au bootstrap).
- `configuration_service.get("services.character_service.strategy", default=None)` — lecture par chemin pointé.
- `configuration_service.section("services.character_service")` — sous-section dict (copie défensive).
- `configuration_service.as_dict()` — snapshot complet (copie défensive).

## Localisation et override

| Mode | Chemin |
|---|---|
| **Défaut** | `src/simphonia/simphonia.yaml` (racine du module `simphonia`) |
| **Override CLI** | `simphonia --configuration <path>` (stocké en interne via `SIMPHONIA_CONFIG_PATH`) |

Le flag `--configuration` remplace intégralement le fichier par défaut (pas de merge). Les paramètres absents du fichier pointé reprennent la valeur par défaut interne documentée ci-dessous.

## Structure générale

```yaml
services:
  <nom_du_service>:
    strategy: <nom_de_la_stratégie>
    # ... paramètres spécifiques à la stratégie choisie
```

La racine `services/` regroupe la configuration de tous les **services utilitaires** (character_service, futurs scene_service, etc.). Chaque service choisit sa stratégie d'implémentation via le champ `strategy`.

---

## Paramètres

### `services.character_service`

Service utilitaire fournissant l'accès aux fiches de personnages. Voir [character_service.md](./character_service.md).

#### `services.character_service.strategy`

- **Rôle** : sélectionne l'implémentation active du `character_service`.
- **Valeurs possibles** :
  - `json_strategy` — charge les fiches depuis des fichiers JSON locaux dans `./resources/characters/` (un fichier par personnage, nommé `<id>.json`).
  - `mongodb_strategy` — charge les fiches depuis une collection MongoDB `characters` (chaque document a un `_id` de type `str`).
- **Défaut** (si la clé `strategy` est absente du YAML) : `json_strategy`
- **Override CLI** : non
- **Exemple** :

```yaml
services:
  character_service:
    strategy: json_strategy
```

#### `services.character_service.database_uri` *(mongodb_strategy)*

- **Rôle** : URI de connexion MongoDB utilisée par `mongodb_strategy`.
- **Type** : `str`
- **Défaut** : aucun — la clé est obligatoire si `strategy: mongodb_strategy`. Une erreur explicite est levée au startup si la valeur est manquante ou vide (y compris après interpolation ratée).
- **Override CLI** : non
- **Usage typique** : interpolation `${MONGO_URI}` depuis le `.env`.

#### `services.character_service.database_name` *(mongodb_strategy)*

- **Rôle** : nom de la base MongoDB utilisée par `mongodb_strategy`. Collection cible fixée : `characters`.
- **Type** : `str`
- **Défaut** : aucun — la clé est obligatoire si `strategy: mongodb_strategy`. Même traitement que `database_uri` (erreur explicite au startup si absente).
- **Override CLI** : non
- **Usage typique** : interpolation `${MONGO_DATABASE}` depuis le `.env`.

**Exemple complet** :

```yaml
services:
  character_service:
    strategy: mongodb_strategy
    database_uri: ${MONGO_URI}
    database_name: ${MONGO_DATABASE}
```

### `services.memory_service`

Service utilitaire de mémoire contextuelle (RAG) — retourne les souvenirs pertinents d'un personnage pour un contexte donné. Exposé via le bus `memory` (commande `recall`).

#### `services.memory_service.strategy`

- **Rôle** : sélectionne l'implémentation active du `memory_service`.
- **Valeurs possibles** :
  - `chroma_strategy` — vector store local ChromaDB (collection `knowledge`, modèle d'embedding `paraphrase-multilingual-MiniLM-L12-v2`). Répertoire persistant : `./data/chromadb/`.
- **Défaut** : `chroma_strategy`
- **Override CLI** : non
- **Exemple** :

```yaml
services:
  memory_service:
    strategy: chroma_strategy
```

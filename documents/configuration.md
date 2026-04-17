# Configuration simphonia

Documentation exhaustive de tous les paramètres de configuration du module `simphonia`.

## Rôle du fichier

Le fichier YAML de configuration est le **point d'entrée de paramétrage** du module `simphonia`. Il centralise toutes les options externalisées (choix de stratégies de services, paramètres runtime, etc.).

### Principes directeurs

- **Tout paramètre externalisé doit avoir une valeur par défaut** dans le fichier de configuration livré avec le module. Démarrer sans configuration custom doit toujours produire un runtime fonctionnel.
- **Certains paramètres peuvent être surchargés en ligne de commande** (précisé au cas par cas dans la documentation du paramètre).
- **Un seul fichier, un seul format** : YAML.
- Les paramètres sont documentés **au fur et à mesure** de leur introduction. Toute évolution (ajout / renommage / suppression d'option) doit être répercutée ici dans le même commit.

## Localisation et override

| Mode | Chemin |
|---|---|
| **Défaut** | `simphonia.yaml` à la racine du module `simphonia` |
| **Override CLI** | `--configuration <path_to_configuration/configuration_file.yaml>` |

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
  - `mongodb_strategy` — *(à venir)* charge les fiches depuis une base MongoDB.
- **Défaut** : `json_strategy`
- **Override CLI** : non
- **Exemple** :

```yaml
services:
  character_service:
    strategy: json_strategy
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

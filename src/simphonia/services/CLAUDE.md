# Conventions — `simphonia/services/`

Guide d'architecture pour l'ajout et la maintenance des services utilitaires du module `simphonia` (`character_service`, futurs `scene_service`, etc.).

## Structure — un dossier par service

Chaque service utilitaire suivant le pattern **interface + stratégies** vit dans **son propre sous-répertoire** :

```
services/
├── <service_name>/
│   ├── __init__.py           # interface (ABC) + factory build_<service_name>(strategy)
│   └── strategies/
│       ├── __init__.py       # vide
│       ├── <strategy_a>.py   # implémentation A
│       └── <strategy_b>.py   # implémentation B
└── <autre_service>/
    └── ...
```

Principe : un service = un dossier cohérent ; interface et implémentations vivent ensemble, une évolution d'API touche un seul répertoire.

**Exception** : un service trivial sans variantes interchangeables *peut* rester en module plat (`<service>.py`). En pratique, dès qu'on anticipe qu'une alternative de provider pourrait exister un jour (même un seul provider aujourd'hui), on part directement sur la structure en sous-dossier — c'est ce qui a été fait pour `memory_service` (provider unique `chroma_strategy` pour l'instant, mais abstraction posée).

## Interface — `ABC`, pas `Protocol`

Les interfaces de services sont définies en **classe abstraite (`abc.ABC`)**, pas en `typing.Protocol`.

**Pourquoi** : le pattern strategy demande qu'un provider déclare explicitement son contrat (`class JsonX(XService):`). `Protocol` (duck typing structurel) est adapté au typage de lecture, pas à la sélection dynamique d'implémentations.

## Factory avec import dynamique

L'interface expose une fonction `build_<service_name>(strategy: str) -> <Service>` qui instancie la stratégie demandée. Les imports des modules de stratégie se font **à l'intérieur** de la factory, jamais en tête de fichier.

**Pourquoi** : éviter de charger les dépendances de *toutes* les stratégies (ex. pilote MongoDB, client S3, …) quand une seule est utilisée. L'import reste inerte tant que la stratégie n'est pas sélectionnée.

**Exemple** :

```python
def build_character_service(strategy: str) -> CharacterService:
    if strategy == "json_strategy":
        from simphonia.services.character_service.strategies.json_strategy import (
            JsonCharacterService,
        )
        return JsonCharacterService()
    raise ValueError(f"Unknown character_service strategy: {strategy!r}")
```

## Pas de singleton module-level quand la construction dépend de la config

Contrairement à `memory_service = MemoryService()` (service mono-implémentation, instanciable sans paramètre), les services **multi-stratégies** n'exposent **pas** de singleton `<service>_<name> = <Service>()` en bas de module.

L'instance est construite au **bootstrap** à partir de la configuration YAML, puis injectée / enregistrée là où elle est consommée. C'est le bootstrap qui appelle la factory, pas le module de service.

## Accès à la configuration

Les services **ne lisent jamais** le fichier de configuration, les variables d'environnement (`os.environ`), ni un `.env` directement. Le **`configuration_service`** (`services/configuration_service.py`) est la seule porte d'entrée :

- Il est initialisé en premier au bootstrap (`configuration_service.init()`).
- Il expose la config sous forme de **snapshot immuable** (copies défensives `deepcopy`) via `get(path)` / `section(path)` / `as_dict()`.
- L'interpolation `${ENV_VAR}` est appliquée à la charge — une fois pour toutes.

Côté factory d'un service multi-stratégies : elle reçoit en argument la sous-section dict (`configuration_service.section("services.<svc>")`) et passe les kwargs à la stratégie instanciée. Les stratégies n'importent **pas** `configuration_service` — elles reçoivent leurs paramètres explicitement par leur constructeur (DI simple).

## Contrat schemaless

Les services qui servent des **entités de jeu** (fiches personnages, scènes, etc.) retournent des **`dict` bruts**, pas des modèles Pydantic / dataclass. La connaissance du schéma est déportée chez le consommateur (voir `documents/character_service.md`). Cette règle vaut pour tout futur service utilitaire exposant ce type de données.

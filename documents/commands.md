# Commandes — compilation & lancement

Référence rapide des commandes pour installer, builder et lancer le serveur `simphonia` et le client `simcli`.

Toutes les commandes sont à exécuter depuis la racine du projet (`X:\git\sim-phonia`) sauf mention contraire.

## Installation

### Mode développement (éditable)

Installe le paquet en mode éditable avec les extras de dev (pytest, ruff) :

```bash
pip install -e ".[dev]"
```

Les deux entry points (`simphonia`, `simcli`) sont alors disponibles dans le `PATH` du venv.

### Installation runtime seule

```bash
pip install -e .
```

### Depuis `requirements.txt`

Utile pour reproduire l'environnement runtime sans passer par pyproject :

```bash
pip install -r requirements.txt
```

## Build

Build wheel + sdist via Hatchling (backend déclaré dans `pyproject.toml`) :

```bash
pip install build
python -m build
```

Artefacts produits dans `./dist/`.

## Lancement du serveur `simphonia`

### Via l'entry point (recommandé)

```bash
simphonia
```

Équivalent à `uvicorn simphonia.bootstrap:app --host 127.0.0.1 --port 8000` (voir `src/simphonia/__main__.py`).

### Via module Python

```bash
python -m simphonia
```

### Via uvicorn directement (reload pour dev)

```bash
uvicorn simphonia.bootstrap:app --host 127.0.0.1 --port 8000 --reload
```

## Lancement du client `simcli`

### Via l'entry point

```bash
simcli --help
simcli bus list
simcli bus commands <bus_name>
simcli dispatch <bus_name> <code> --payload '{"key": "value"}'
```

### Via module Python

```bash
python -m simcli bus list
```

### URL serveur personnalisée

Par défaut le client cible `http://127.0.0.1:8000`. Pour pointer ailleurs :

```bash
simcli --url http://hôte:port bus list
```

## Qualité & tests

### Lint

```bash
ruff check .
ruff format .
```

### Tests

```bash
pytest
```

`pyproject.toml` positionne `pythonpath = ["src"]` et `testpaths = ["tests"]`.

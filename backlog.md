# Backlog

Gestion des priorités : **HOT** > **WARM** > **COLD** > **FROZEN** > **DONE**.
Une entrée ne passe en `DONE` qu'après validation de l'utilisateur (tests manuels OK).

## HOT

_(vide)_

## WARM

_(vide)_

## COLD

_(vide)_

## FROZEN

_(vide)_

## DONE

### 2026-04-16 — Module `simcli`

- `src/simcli/client.py` : `SimphoniaClient` (wrapper `httpx.Client`, context-manager) avec `list_buses()`, `list_commands(bus_name)`, `dispatch(bus_name, code, payload)`. Gestion erreurs : `NotFound` (404), `ServerError` (≥400), `ServerUnreachable` (réseau).
- `src/simcli/cli.py` + `src/simcli/__main__.py` : CLI `argparse` avec sous-commandes `bus list`, `bus commands <name>`, `dispatch <bus> <code> [--payload JSON]`. Option globale `--url` (défaut `http://127.0.0.1:8000`). Sortie JSON formatée sur stdout, erreurs sur stderr.
- `src/simcli/errors.py` : hiérarchie `SimcliError` / `NotFound` / `ServerUnreachable` / `ServerError` / `InvalidPayload`.
- Codes de sortie : 0 OK · 1 erreur générique · 2 arguments/payload invalides · 3 serveur injoignable · 4 404 · 5 5xx.
- Choix stack : `httpx` + `argparse` (pas de `click`/`typer`, conformément au principe "simple").
- `pyproject.toml` : `httpx` remonté en runtime, script `simcli = "simcli.cli:main"` ajouté ; `requirements.txt` synchronisé.
- Docs : création de `documents/simcli.md` (spécs module), mise à jour de `documents/architecture.md` pour y pointer.

### 2026-04-16 — Squelette projet + architecture bus/commandes `simphonia`

- Création de l'arborescence `src/simphonia/{core,commands,http}` et `src/simcli/`.
- Couche `core/` :
  - `Command` (dataclass frozen : `code`, `description`, `callback`, `bus_name`).
  - `Bus` (register / get / list / dispatch, fail-fast sur doublon).
  - `BusRegistry` singleton (`default_registry()`, `reset()` pour tests).
  - Décorateur `@command(bus=..., code=..., description=...)`.
  - `discover(package)` via `pkgutil.walk_packages` pour forcer l'import récursif.
  - Hiérarchie d'erreurs : `SimphoniaError`, `BusNotFound`, `CommandNotFound`, `DuplicateCommand`, `DispatchError`.
- Commandes `system` :
  - `help` → liste `(code, description)` de toutes les commandes du bus `system`.
  - `ping` → `"pong"`.
- Couche HTTP (FastAPI + pydantic v2) :
  - `GET /healthz`, `GET /bus`, `GET /bus/{name}/commands`, `POST /bus/{name}/dispatch`.
  - Schémas pydantic : `BusDTO`, `CommandDTO`, `DispatchRequest/Response`, `ErrorBody/Response`.
  - Mapping erreurs → 404 / 500 avec body normalisé.
- Bootstrap & packaging :
  - `bootstrap.py` : pré-crée le bus `system`, appelle `discover("simphonia.commands")`, assertion présence `system/help`, log du compte.
  - `__main__.py` : `uvicorn.run("simphonia.bootstrap:app", ...)`.
  - `pyproject.toml` (hatchling) : deps runtime (fastapi, pydantic, uvicorn), extras `dev` (pytest, httpx, ruff), script `simphonia`, config ruff + pytest.
  - `requirements.txt` racine (miroir des deps runtime).
- Conventions projet consignées dans `CLAUDE.md` :
  - Toute nouvelle dépendance runtime → `pyproject.toml` **et** `requirements.txt` dans le même commit ; les deps de dev restent en extras.
  - Maintien d'un `backlog.md` unique avec priorités HOT/WARM/COLD/FROZEN/DONE, mis à jour uniquement après validation utilisateur.
- `.gitignore` Python / venv / PyCharm / `.env`.

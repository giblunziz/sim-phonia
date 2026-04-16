# simcli

- Module CLI en ligne de commande
- développé en python
- pilote le serveur `simphonia` via son API HTTP
- ne contient **aucune** logique métier : toute la logique réside côté serveur, le CLI est un client mince
- pas de dépendance à `simphonia` (module totalement autonome, ne partage que le contrat HTTP)

## commandes

### `simcli bus list`

Affiche la liste des bus connus du serveur avec leur nombre de commandes.

### `simcli bus commands <bus_name>`

Affiche la liste des commandes (`code`, `description`) enregistrées sur un bus donné.

### `simcli dispatch <bus_name> <code> [--payload JSON]`

Invoque la commande `code` sur le bus `bus_name`. Le `--payload` est un objet JSON passé en `**kwargs` à la callback côté serveur. Exemple :

```
simcli dispatch system ping
simcli dispatch system help
simcli dispatch math add --payload '{"a": 2, "b": 3}'
```

## options globales

- `--url URL` : URL de base du serveur simphonia (défaut : `http://127.0.0.1:8000`).

## codes de sortie

- `0` : succès
- `1` : erreur générique côté CLI
- `2` : arguments invalides ou payload JSON mal formé
- `3` : serveur injoignable
- `4` : bus ou commande introuvable (404)
- `5` : erreur serveur (5xx)

## stack

- `httpx` pour le client HTTP (sync)
- `argparse` (stdlib) pour le parsing des arguments — choix délibéré de rester minimal, pas de dépendance à `click` / `typer`
- sortie systématiquement en JSON formaté sur `stdout`, erreurs sur `stderr`

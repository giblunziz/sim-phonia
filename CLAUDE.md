# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This repository is newly initialized and does not yet contain source code, a build system, or tests. The sections below are placeholders — fill them in (or re-run `/init`) once the project takes shape.

## Architecture

- Se référer aux documents dans ./documents/*.md

## Index des documents

Cartographie des documents de spéc, d'analyse et de synthèse (mon RAG projet — à consulter au démarrage de chaque session pour récupérer le contexte).

### Spécifications

- [architecture.md](./documents/architecture.md) — topologie générale (modules `simphonia` + `simcli`, lien HTTP)
- [simphonia.md](./documents/simphonia.md) — serveur event-bus : bus, commandes, cascades, façade MCP, conventions d'implémentation
- [simcli.md](./documents/simcli.md) — CLI HTTP pour piloter le serveur (commandes, codes de sortie, stack)
- [commands.md](./documents/commands.md) — cheatsheet install / build / lancement serveur & client, lint, tests

### Études & synthèses

- [shadow_memory.md](./documents/shadow_memory.md) — `shadow_memory_service` + le "psy" : rôle, chaîne d'exécution, deux casquettes du psy, points ouverts

## Conventions

- tu travail toujours en mode dev sénior
- À la racine du projet, tu maintiens un unique fichier `backlog.md` avec une gestion de priorités `HOT`, `WARM`, `COLD`, `FROZEN`, `DONE`. Une entrée ne bascule en `DONE` **qu'après validation explicite de l'utilisateur** (tests manuels OK de son côté) ; tant que la validation n'a pas eu lieu, l'entrée reste dans sa section de priorité d'origine. Ne jamais marquer soi-même un item comme `DONE` de sa propre initiative.
- Toute nouvelle dépendance Python runtime doit être ajoutée **à la fois** dans `pyproject.toml` et dans `requirements.txt` (racine du projet) dans le même commit. Les dépendances de dev vont uniquement dans `pyproject.toml` sous `[project.optional-dependencies].dev`.
- **Tout nouveau document d'étude, d'analyse ou de synthèse déposé dans `./documents/`** doit être ajouté à la section *Index des documents* de ce `CLAUDE.md` dans le même commit, sous la sous-section appropriée (*Spécifications* ou *Études & synthèses*), avec une ligne descriptive courte. C'est le RAG projet — l'index doit refléter l'état réel à chaque instant.

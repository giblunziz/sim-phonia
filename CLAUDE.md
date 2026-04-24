# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This repository is newly initialized and does not yet contain source code, a build system, or tests. The sections below are placeholders — fill them in (or re-run `/init`) once the project takes shape.

## Architecture

- Se référer aux documents dans ./documents/*.md

## Index des documents

Cartographie des documents de spéc, d'analyse et de synthèse (mon RAG projet — à consulter au démarrage de chaque session pour récupérer le contexte).

### Spécifications

- [architecture.md](./documents/architecture.md) — topologie générale (modules `simphonia` + `simcli` + `simweb`, lien HTTP)
- [simphonia.md](./documents/simphonia.md) — serveur event-bus : bus, commandes, cascades, façade MCP, conventions d'implémentation
- [simcli.md](./documents/simcli.md) — CLI HTTP pour piloter le serveur (commandes, codes de sortie, stack)
- [commands.md](./documents/commands.md) — cheatsheet install / build / lancement serveur & client, lint, tests
- [character_service.md](./documents/character_service.md) — cahier des charges du `character_service` (interface + stratégies, bus `character`, config YAML, json_strategy)
- [configuration.md](./documents/configuration.md) — doc exhaustive des paramètres du fichier de configuration YAML (défauts, overrides CLI)
- [chat_service.md](./documents/chat_service.md) — cahier des charges du `chat_service` (dialogue 1-to-1 LLM/humain, cycle start/reply/stop, providers, schéma JSON)
- [simweb.md](./documents/simweb.md) — module front-end React/Vite : écrans StartScreen/ChatScreen, API HTTP, SSE pour mode autonome, câblage serveur
- [memory_service.md](./documents/memory_service.md) — cahier des charges du `memory_service` (RAG contextuel, ChromaDB, interface recall/stats/resync, bus, points ouverts)
- [service_character_storage.md](./documents/service_character_storage.md) — cahier des charges du `character_storage` (source de vérité MongoDB, collections `characters` + `knowledge`, CRUD, bus admin, intégration simweb)
- [activity_engine.md](./documents/activity_engine.md) — cahier des charges de l'`activity_engine` (orchestrateur de session MJ-driven, SessionState, commandes bus activity, SSE, circuit breaker, persistance MongoDB)
- [mj_service.md](./documents/mj_service.md) — cahier des charges du `mj_service` (mj_mode human|human_in_loop|autonomous × turning_mode starter|named|round_robin|next_remaining|random_remaining|random, façade MCP dual avec mcp_role, port Beholder)
- [tools_service.md](./documents/tools_service.md) — cahier des charges du `tools_service` (atelier utilitaire one-shot, double boucle source×subject, registre mongo task_collection, outputs fichiers .txt)
- [shadow_storage.md](./documents/shadow_storage.md) — cahier des charges du `shadow_storage` : capture passive du subconscient des joueurs via bus `messages` + observer pattern, persistance Mongo + ChromaDB, panneau **Tobias > Subconscient** côté simweb

### Études & synthèses

- [shadow_memory.md](./documents/shadow_memory.md) — `shadow_memory_service` + le "psy" : rôle, chaîne d'exécution, deux casquettes du psy, points ouverts
- [activity_presentation.md](./documents/activity_presentation.md) — activité `presentation` : phases onboarding/cross-analyse, alimentation de `knowledge`, format d'injection dans le context builder
- [activity_context_builder.md](./documents/activity_context_builder.md) — cahier des charges + plan du `activity_context_builder` : assemblage system prompt + messages, constantes PUBLIC/PRIVATE_FIELDS, interface `build_system_prompt / build_messages / get_tools`
- [cognition.md](./documents/cognition.md) — synthèse piste de travail 2026-04-23 : mécanique du psy/shadow_memory (AOP cascades sur `memory/recall`, intervention DISC, formule `memory.slots × coeff_transactionnel`, séparation Décideur/Narrateur, scénario pilote Antoine/Manon/Élise)

## Conventions

- tu travail toujours en mode dev sénior
- À la racine du projet, tu maintiens un unique fichier `backlog.md` avec une gestion de priorités `HOT`, `WARM`, `COLD`, `FROZEN`, `DONE`. Une entrée ne bascule en `DONE` **qu'après validation explicite de l'utilisateur** (tests manuels OK de son côté) ; tant que la validation n'a pas eu lieu, l'entrée reste dans sa section de priorité d'origine. Ne jamais marquer soi-même un item comme `DONE` de sa propre initiative.
- Toute nouvelle dépendance Python runtime doit être ajoutée **à la fois** dans `pyproject.toml` et dans `requirements.txt` (racine du projet) dans le même commit. Les dépendances de dev vont uniquement dans `pyproject.toml` sous `[project.optional-dependencies].dev`.
- **Tout nouveau document d'étude, d'analyse ou de synthèse déposé dans `./documents/`** doit être ajouté à la section *Index des documents* de ce `CLAUDE.md` dans le même commit, sous la sous-section appropriée (*Spécifications* ou *Études & synthèses*), avec une ligne descriptive courte. C'est le RAG projet — l'index doit refléter l'état réel à chaque instant.

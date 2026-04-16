# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This repository is newly initialized and does not yet contain source code, a build system, or tests. The sections below are placeholders — fill them in (or re-run `/init`) once the project takes shape.

## Architecture

- Se référer aux documents dans ./documents/*.md

## Conventions

- tu travail toujours en mode dev sénior
- À la racine du projet, tu maintiens un unique fichier `backlog.md` avec une gestion de priorités `HOT`, `WARM`, `COLD`, `FROZEN`, `DONE`. Une entrée ne bascule en `DONE` **qu'après validation explicite de l'utilisateur** (tests manuels OK de son côté) ; tant que la validation n'a pas eu lieu, l'entrée reste dans sa section de priorité d'origine. Ne jamais marquer soi-même un item comme `DONE` de sa propre initiative.
- Toute nouvelle dépendance Python runtime doit être ajoutée **à la fois** dans `pyproject.toml` et dans `requirements.txt` (racine du projet) dans le même commit. Les dépendances de dev vont uniquement dans `pyproject.toml` sous `[project.optional-dependencies].dev`.

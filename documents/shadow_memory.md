# shadow_memory_service & le "psy"

Synthèse d'étude — 2026-04-17.

## Principe cardinal

- **`memory_service`** = **mémoire consciente** du personnage. Accédé directement par le LLM joueur (via tool MCP `recall`, futur). Le LLM formule sa question ; le paramètre `top_k` n'est jamais dans sa main, il est lu depuis `memory.slots` de sa fiche (via `character_service` à porter). Filtre `from` = garde anti-triche.
- **`shadow_memory_service`** = **subconscient**. Ne s'adresse jamais directement au LLM. S'insère autour de `memory/recall` via deux cascades :
  - **`shadow_before_call`** → détournement de query.
  - **`shadow_after_call`** → altération / enrichissement via une 2e RAG sur une collection dédiée.
- **Le `psy`** = **PNJ à part entière** : fiche + system prompt dédié, même infrastructure providers que les autres agents (config par perso + fallback), potentiellement modèle différent (gemma4/qwen pour le psy, opus pour le joueur). Dev/proto en gemma4. Il reçoit derniers échanges / événements + fiche du perso concerné.

## Deux casquettes du psy

1. **Runtime** — il *est* la fonction de réécriture. `shadow_before_call` et `shadow_after_call` sont des appels au psy : pas un switch case par type de focus, c'est le LLM analytique qui décide.
2. **Production** — il écrit aussi des entrées dans MongoDB (collection shadow dédiée, séparée de `knowledge`) et déclenche la sync ChromaDB.

## Données

- **MongoDB = source de vérité**. ChromaDB = index reconstructible ; on peut drop chroma sans perte.
- **Collection shadow séparée** de `knowledge` — même moteur RAG, corpus distinct (matière refoulée / ancrages / obsessions / ruminations).
- **Sync** au démarrage + à chaque mutation mongo pendant le jeu (pratique : inserts manuels en test → re-sync chroma).

## État "focus" unilatéral

Concept en cours de design. Propriétés déjà fixées :

- **Unilatéral** : que A pense à B ne signifie pas que B pense à A (ex: Marc flashe sur la barista qui ne l'a même pas remarqué).
- Mis à jour en fonction du comportement du personnage lui-même (pas du comportement de la cible).
- Alimente le psy pour ses décisions de détournement/enrichissement.

**Non défini** : forme de stockage (poids simple vs typologie), déclencheur de mise à jour, règles de priorité quand plusieurs focus co-existent.

## Opacité

Le LLM joueur ne voit **jamais** qu'un détour a eu lieu. Le retour du tool `recall` lui paraît répondre à sa question d'origine. Du point de vue personnage : inconscient/subconscient. Du point de vue technique : retour du tool RAG, point.

## Chaîne d'exécution cible (recall)

```
LLM joueur (tool MCP recall)
  → simphonia (façade MCP)
  → bus memory
    → shadow_before_call   (psy → réécrit la query, ou la laisse)
    → memory_service.recall (knowledge, top_k depuis fiche perso)
    → shadow_after_call    (psy → 2e RAG sur collection shadow + fusion)
  → retour LLM joueur (opaque)
```

## Contraintes

- Joueurs libres de communiquer **hors activité** ; le `mj` n'intervient qu'en activité. Le shadow opère dans les deux contextes.
- **Coût LLM** : potentiellement 2 appels psy par recall. Budget à surveiller (skip si aucun focus actif sur la cible, rate-limit par tour, cache par hash de query — à trancher).

## Points ouverts à trancher

1. Forme de l'**état focus** (poids `{(from, about): score}` vs typologie attirance/culpabilité/méfiance/… vs structure hybride).
2. **Déclencheur d'update** du focus (probablement le psy lui-même, après événement notable — à préciser : fin d'activité ? après chaque exchange ? polling ?).
3. **Schéma d'une entrée shadow** (calque `PerceptionEntry` avec catégorie spéciale vs schéma propre avec `intensity` / `source_event_id` / `last_reinforced_at` pour decay).
4. **Garde-fous budget LLM** (skip, cache, rate-limit).
5. **Trigger du re-sync mongo → chroma** pendant le jeu (qui lance la sync ? après quel événement ?).
6. **Short-circuit** éventuel sur le `before` (cache hit, validation bloquante) — dispo techniquement via `ShortCircuit`, à décider si pertinent.

## Pré-requis avant implémentation

- `character_service` porté (lecture de `memory.slots` + fiche psy).
- Cascades opérationnelles (`@cascade` + `ShortCircuit` — ticket #11).
- Façade MCP opérationnelle (ticket #14) pour la chaîne complète.
- Collection shadow MongoDB spec'ée et initialisée.

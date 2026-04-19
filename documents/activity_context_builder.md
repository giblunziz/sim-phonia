# Etude du service activity_context_builder

## Description

Le service `activity_context_builder` est le composant central qui assemble le contexte LLM complet (system prompt + liste de messages) pour chaque joueur à chaque tour d'activité. Il concatène dans un ordre strict le schema JSON attendu, la scène, les règles, les impressions croisées issues de la collection `knowledge`, la fiche personnage, puis construit la chronologie des messages (événement de round, whisper, historique public formaté en markdown, instruction MJ). Il expose également le tool recall pour permettre au LLM d'interroger la mémoire long-terme.

## Cahier des charges

### 1. Rôle

Service interne à `activity_service` responsable de la production du contexte LLM pour chaque tour d'activité. Il est appelé par le moteur d'activité (activity engine) juste avant chaque invocation du provider LLM. Il ne dialogue pas avec le LLM lui-même — il prépare les entrées.

### 2. Localisation

Module flat : `src/simphonia/services/activity_service/context_builder.py`. Pas de sous-dossier `context_builder/` tant que les besoins ne justifient pas un service indépendant avec stratégies.

### 3. Interface publique

```python
def build_system_prompt(
    player: str,
    instance: dict,
    activity: dict,
    scene: dict,
    character: dict,
    knowledge_entries: list[dict],
) -> str: ...

def get_tools(activity: dict | None = None) -> list[dict]: ...

def build_messages(
    player: str,
    instance: dict,
    exchange_history: list[dict],
    current_round_event: dict | None = None,
    whisper: str | None = None,
    mj_instruction: dict | None = None,
    amorce: str | None = None,
) -> list[dict]: ...

def format_exchange(speaker: str, raw_response: str) -> str: ...
```

Toutes les entrées sont des `dict` bruts (schemaless). Le builder ne valide pas les schémas — il extrait les champs connus et ignore le reste.

Le paramètre `amorce` est réservé au MJ. Le caller décide de le passer ou non selon que `player == instance['mj']`. Le builder ne résout pas lui-même l'identité MJ.

### 4. System prompt — ordre strict

1. **Schema JSON** — schéma de réponse attendu du LLM, lu depuis `activity['json_schema']`, injecté en tête. Le retour LLM est parsé via `parse_llm_json` dans tous les cas (qui gère les blocs markdown et le JSON brut). Le prompt doit explicitement demander du JSON sans encadrement :

   ```
   Réponds UNIQUEMENT en JSON valide respectant ce schéma. Ne l'encadre pas de bloc de code markdown.
   <json_schema brut>
   ```

   Section omise si `json_schema` absent ou vide.
2. **Scène** — bloc markdown décrivant la scène. Source : `scene` dict.
3. **Règles joueur** — règles publiques issues du template `activity`.
4. **Impressions sur les autres** — issues de `knowledge_entries` (filtrés et passés par le caller, jamais requêtés par le builder). Format markdown figé :

   ```
   ## Tes impressions sur les autres participants
   Ces analyses reflètent tes premières impressions. Elles guident ta manière d'interagir avec chacun.
   ### Ce que tu sais à propos de <about>
   - **<category>** : <value>
   ```

   Groupement : par `about` puis par `category`. Si `knowledge_entries` est vide, la section entière est omise.
5. **Fiche personnage** — JSON brut (`json.dumps(character, ensure_ascii=False, indent=2)`) en bloc de code markdown, en dernier.

Le caller est responsable du filtre knowledge :
```
knowledge.find({
  from: player,
  activity: "presentation",
  about: { $in: instance.players \ {player} }
})
```

### 5. Messages — ordre strict

1. **Amorce MJ** — si `amorce` est fourni (non-None), injecté en tout premier comme `role=user`. Jamais reformaté — transmission littérale. Ne concerne que le MJ ; les joueurs standard reçoivent `amorce=None`.
2. **Événement de round** — si `instance.events` contient une entrée matchant le round courant, message `role=user`.
3. **Whisper** — message privé `role=user` au joueur, si fourni.
4. **Historique des échanges publics** — chaque échange passé est transformé via `format_exchange()`. Rôles : `role=assistant` pour les tours du joueur courant, `role=user` pour les tours des autres. Filtrage strict des champs privés.
5. **Instruction MJ** — si `instance.instructions` contient une entrée matchant `(round, who)` où `who` est le slug joueur ou sa position 1-based, message `role=user` en dernier.

L'amorce n'entre jamais dans l'historique public des joueurs. Le MJ la digère et compose ses instructions ; c'est celles-ci qui atteignent les joueurs.

### 6. format_exchange()

Port direct de `MemoryUserContextBuilder.format_exchange` (legacy Symphonie). Signature : `(speaker: str, raw_response: str) -> str`.

- Tente de parser `raw_response` en JSON ; si échec, retourne la chaîne brute.
- Extrait uniquement les champs `PUBLIC_FIELDS` : `to`, `talk`/`message`, `action`/`actions`, `body`, `mood`.
- Ignore systématiquement `PRIVATE_FIELDS` : `inner_thought`, `inner`, `expected`, `noticed`, `memory`.
- Produit :

  ```
  ### <from> s'adresse à <to|tous>
  - <talk>
  ### <from> a agi ainsi:
  - <action>
  ### le corps de <from> réagit ainsi:
  - <body>
  ```

- Les sous-sections absentes sont omises (pas de ligne vide parasite).

### 7. Constantes

```python
PRIVATE_FIELDS = {"inner_thought", "inner", "expected", "noticed", "memory"}
PUBLIC_FIELDS  = {"from", "to", "talk", "message", "action", "actions", "body", "mood"}
```

`mood` est un état visible des autres joueurs — il appartient aux champs publics (correction par rapport au legacy où il était mal classé). `inner_thought` reste privé (monologue intérieur non perceptible). Exposées au niveau module.

### 8. Tool recall

- `get_tools(activity: dict | None = None) -> list[dict]` retourne les tool signatures à passer au provider.
- Par défaut (sans `activity`) : retourne tous les tools référencés (ex : `memory/recall`).
- Plus tard : `activity` permettra de filtrer la liste aux tools autorisés par activité.
- L'orchestrateur appelle `get_tools()` séparément et passe le résultat directement au provider — `build_system_prompt` n'a pas connaissance des tools.
- Compatibilité Anthropic + Gemma : la forme des tools est celle attendue par `providers/base.py`.

### 9. Résolution `who` position → slug

Le context_builder résout lui-même les références positionnelles dans `instance.instructions`. Il dispose de `instance` et `player` : la résolution est un simple lookup `instance['players'][who - 1]` (1-based). Pas d'appel externe.

### 10. Points d'extension

Aucun hook d'extension dans le context_builder. `shadow_memory` est un intercepteur du `memory_service`. Le psy est un joueur LLM particulier sans fiche réelle, portant des instructions dédiées à l'analyse psychologique — il passe par le même builder que n'importe quel joueur et altère les joueurs en amont via le `memory_service`.

### 11. Compaction

Hors scope V1 (YAGNI). L'algo legacy `compact_history` est jugé trop approximatif. À retraiter dans un ticket dédié.

### 12. Schemaless & robustesse

- Accès aux dicts par `.get()` systématique, jamais d'indexation directe.
- Champs manquants → section/message simplement omis, pas d'erreur.
- Aucun raise sauf sur invariants techniques.

### 13. Tests

- Tests unitaires sur `format_exchange()` (JSON valide, JSON invalide, champs privés présents, tous champs absents).
- Tests sur `build_system_prompt()` avec/sans knowledge, sans tools.
- Tests sur `build_messages()` avec combinatoires (amorce présente/absente, event/whisper/mj_instruction présents ou non, historique vide, rôles assistant/user).

## Décisions de conception

| Num | Question | Décision retenue | Raison |
| --- | -------- | ---------------- | ------ |
| 1 | Qui exécute la requête knowledge ? | Le caller passe `knowledge_entries` déjà filtré — le builder ne touche jamais le storage | Séparation des responsabilités : builder = fonction pure, sans effet de bord ni dépendance bus, testable unitairement |
| 2 | Rôle des messages dans l'historique public ? | `role=assistant` pour les tours du joueur courant, `role=user` pour les autres | Aligné sur la convention déjà en place dans `chat_service` ; le LLM voit sa propre voix comme `assistant` |
| 3 | Où vit le schema JSON de sortie ? | Dans le template d'activité (`activity['json_schema']`), défini par activité | Chaque activité a son propre contrat de sortie ; le builder reste agnostique |
| 4 | Résolution `who` position→slug ? | Dans le context_builder (`instance['players'][who-1]`) | Seul endroit qui formate le texte LLM ; lookup dict pur, pas d'appel externe |
| 5 | Hook d'extension pour sections custom ? | Non — shadow_memory = intercepteur memory_service, psy = joueur LLM spécial | YAGNI + KISS ; builder à surface fermée ; toute altération contextuelle se fait en amont |
| 6 | Injection de l'amorce ? | Paramètre `amorce: str | None = None` dans `build_messages`, injecté en premier `role=user` uniquement si non-None | L'amorce est un briefing MJ exclusif, jamais vu des joueurs ; le caller porte la règle métier `player == mj` |

## Plan d'implémentation

### Étape 0 — Préparation du package

Fichiers créés :
- `src/simphonia/services/activity_service/__init__.py` (vide)

### Étape 1 — Squelette + constantes + imports

Fichier créé : `src/simphonia/services/activity_service/context_builder.py`

- Imports : `json`, `parse_llm_json` depuis `simphonia.utils.parser`
- Constantes `PRIVATE_FIELDS`, `PUBLIC_FIELDS`
- Stubs des trois fonctions publiques (corps `raise NotImplementedError`)

### Étape 2 — `format_exchange`

Port fidèle de `MemoryUserContextBuilder.format_exchange` (legacy Symphonie). Fonction pure, sans `self`. Tests unitaires : JSON complet, JSON invalide (fallback), champs privés absents de la sortie.

### Étape 3 — `build_system_prompt`

Assemblage dans l'ordre strict (schema JSON → scène → règles → impressions → fiche). `knowledge_entries` groupés par `about` puis `category` via `defaultdict`. `tools` ignoré pour cette itération (YAGNI). Tests : avec/sans knowledge, sections vides omises.

### Étape 4 — `build_messages`

Assemblage dans l'ordre strict (amorce → event → whisper → historique → instruction MJ). Rôles : `assistant` si `entry['from'] == player`, sinon `user`. Tests : combinatoires amorce/event/whisper/mj présents ou non, rôles corrects.

### Étape 5 — Test visuel bout-en-bout

Script jetable qui affiche system prompt + messages pour relecture humaine. Pas d'assertions — review de format markdown.

### Étape 6 — Commit

```
feat(activity_service): add context_builder (system prompt + messages + format_exchange)
```

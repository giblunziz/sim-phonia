# Etude du service human_in_the_loop

## Description

Mode `human-in-the-loop` permettant à l'utilisateur de prendre la place d'un participant dans une activité. L'`activity_engine` détecte le tour d'un participant désigné comme humain, n'appelle pas le LLM, et attend une saisie via simweb (`talk` + `actions` + destinataire `to`). Mécanisme **transverse** — pas de service dédié, simplement une bifurcation dans le pipeline `activity/give_turn` + une nouvelle commande `activity/submit_human_turn` + une UI dédiée côté simweb.

Cardinalité **0..1** — un seul participant humain par activité (l'utilisateur est l'unique humain).

## Cahier des charges

### Périmètre

- **Mode HITL au niveau de l'activité uniquement** (`activity_engine`).
- `chat_service` n'est **pas** concerné. Son flag `human` au niveau payload reste tel quel — usage interne pour les tests 1-to-1 du développeur. Le « vrai » 1-to-1 est une activité à 2 joueurs.
- **Cardinalité 0..1** — un seul participant humain par activité. Pas de gestion multi-humain.
- L'humain est **simultanément le MJ/observateur** de l'activité. Il a déjà la vue dashboard complète. Aucun contexte additionnel ne lui est servi au moment de saisir son tour.

### Désignation du participant humain

Deux mécanismes superposés, l'**override session prime** :

1. **Override session** (mécanisme principal) — au `activity/run`, payload optionnel `human_player: <slug>`. Si présent, ce participant est le joueur humain pour toute la durée de la session.
2. **Type fiche** (fallback) — si aucun override n'est fourni, scan des participants pour ceux dont `character_service.get_type() == "human"`. Si plusieurs trouvés (cas non prévu), warning et on prend le premier.

Une fois l'activité démarrée, le `human_player` est **figé** pour toute la session.

#### UI de désignation (simweb)

Au load de l'activité, **avant le `run`**, une combo :

> Joué par humain : [aucun | participant1 | participant2 | … ]

- Cardinalité 0..1.
- Pré-sélection automatique : si une fiche d'un participant porte `type: "human"`, sélectionnée par défaut. Sinon `aucun`.
- Modifiable jusqu'au `run`. Après `run`, figée.

### Bifurcation dans `activity/give_turn`

Pipeline modifié — étapes 1 à 7 inchangées (résolution `target`, `character`, `knowledge`, event, whisper, instruction MJ).

**Étape 8 (nouvelle bifurcation)** :

```python
if target == session.human_player:
    # Mode HITL — pas d'appel LLM, attente de saisie humaine.
    session.pending_human_input = {
        "round":  session.round,
        "target": target,
        "ts":     now(),
    }
    sse.publish("activity.input_required", {
        "session_id": session_id,
        "target":     target,
        "round":      session.round,
        "event":      current_round_event,
        "whisper":    whisper,
    })
    return  # le thread se termine, on attend submit_human_turn
```

**Sinon** : pipeline LLM normal (étapes 8-17 actuelles).

### Nouvelle commande `activity/submit_human_turn`

Reçoit la saisie de l'humain depuis simweb, intègre l'exchange dans l'historique.

#### Payload

| Champ | Type | Requis | Description |
|---|---|---|---|
| `session_id` | str | ✓ | Session courante |
| `target`     | str | ✓ | Slug du joueur humain — validation : doit matcher `session.human_player` |
| `to`         | str | ✓ | Slug d'un autre participant, ou `"all"` |
| `talk`       | str | ✓ | Texte parlé (peut être chaîne vide si geste muet) |
| `actions`    | str | ✓ | Actions/gestes physiques (peut être chaîne vide) |

`talk` et `actions` peuvent être vides simultanément ? À éviter — la commande renvoie `empty_turn` si c'est le cas.

**Wrapping pour stockage** : pour rester cohérent avec le schéma d'exchange (qui attend `list[str]`), les valeurs reçues sont wrappées en liste à 1 élément côté serveur avant insertion dans `exchange_history`. Pas de splitting automatique sur les retours à la ligne — c'est un *bloc* de texte saisi par l'humain, qui reste tel quel.

#### Pipeline

1. `_get_session(session_id)` — `SessionNotFound` sinon.
2. Validation : `session.state == "running"`, `target == session.human_player`, `session.pending_human_input is not None`.
3. Construit l'exchange (avec wrapping `[talk]` et `[actions]` pour rester cohérent avec le schéma list[str]) :

```json
{
  "round": "<session.round>",
  "speaker": "<target>",
  "ts": "...",
  "raw_response": null,
  "public":  {"to": "<to>", "talk": ["<talk>"], "actions": ["<actions>"], "body": "", "mood": ""},
  "private": {}
}
```

`raw_response: null` (signe la provenance humaine vs LLM). Champs PRIVATE laissés vides — l'humain *vit* son inner, il n'a pas à l'écrire (V1).

4. Append à `session.exchange_history`.
5. Persiste : `activity_storage / instances.put` avec `exchanges` mis à jour.
6. Reset `session.pending_human_input = None`.
7. Publie SSE `activity.turn_complete` (même event que pour un LLM — flux uniforme).

#### MCP

**Pas exposée en MCP**. Un LLM n'a aucune raison d'appeler cette commande.

### UI simweb

#### Form de saisie en bas de page activité

Toujours visible, à l'instar du form de saisie en mode chat 1-to-1.

| Champ | Widget | Comportement |
|---|---|---|
| `to`      | combo : `[all] + autres_participants` | **Stateful sur la session UI** — pas de reset entre exchanges d'une même activité. Init à `"all"` au lancement ou à la reprise d'une activité. Modifié manuellement par l'humain. Aucune persistance cross-activité (pas de cookie, pas de localStorage). |
| `talk`    | textarea (`str`) | Saisie libre, multilignes possibles dans le textarea mais traitée comme un seul bloc de texte. Reset après envoi. |
| `actions` | textarea (`str`) | Idem `talk`. Reset après envoi. |

#### États du form

- **Désactivé** (champs grisés, bouton inactif) → tant qu'aucun SSE `activity.input_required` n'a été reçu pour le tour courant.
- **Activé** → après réception de `activity.input_required` ciblant le `human_player`. Bouton « Envoyer » actif.
- Sur clic « Envoyer » → POST `activity/submit_human_turn` → désactivation immédiate du form en attente de `activity.turn_complete`.

### Pas de timeout

L'activité attend indéfiniment la saisie humaine. Pas de circuit breaker côté humain — c'est sa responsabilité de répondre, pas un signal d'échec à détecter.

### Déclencheurs SSE

Un seul ajout sur le bus `activity` :

| Événement | Émis quand | Payload |
|---|---|---|
| `activity.input_required` | `give_turn` détecte que `target == session.human_player` | `{session_id, target, round, event, whisper}` |

L'événement `activity.turn_complete` est émis après l'intégration de l'exchange humain par `submit_human_turn` — **identique au flux LLM**, pour que la suite de l'orchestration MJ-driven soit uniforme.

### Cohérence avec `character_service`

**Aucune modification** nécessaire. La constante `CHARACTER_TYPES = ("player", "npc", "human")` est déjà spécifiée. `get_type()` retourne déjà `"human"`. La sémantique attendue (cf. `character_service.md` ligne 76-82) :

> `human` | Non (input clavier) | Aucun (côté moteur, un `human` ne devrait pas passer par la boucle LLM)

…est précisément ce qu'implémente cette spec.

### Schemaless & robustesse

- `human_player` au niveau session : `Optional[str]` — `None` = activité 100% LLM (comportement actuel inchangé).
- `pending_human_input` : `Optional[dict]` — utilisé uniquement pour invalider les `submit_human_turn` hors-séquence.
- Validation fail-fast au `submit_human_turn` si `target` ne matche pas `session.human_player` ou si aucun tour humain n'est en attente : erreur `invalid_human_submit`.

### Hors scope V1

- Plusieurs humains dans une activité (cardinalité > 1).
- Timeout / fallback LLM en cas d'inactivité humaine.
- Tools MCP côté humain (boutons UI pour `recall`, `memorize`).
- Saisie des champs PRIVATE par l'humain (`mood`, `inner`, `expected`, `noticed`, `body`, `memory`).
- Mode HITL pour `chat_service`.
- Bascule MJ→humain en cours de session (override figé après `run`).

## Décisions de conception

| Num | Question | Décision retenue | Raison |
|-----|----------|------------------|--------|
| Q1  | Service à part entière, ou modifications transverses ? | Modifications transverses uniquement (`activity_engine` + simweb). Service dédié réévaluable plus tard si une utilité spécifique émerge. | L'humain n'a pas de logique métier propre — c'est une bifurcation dans un pipeline existant. YAGNI. |
| Q2  | Périmètre — chat 1-to-1, activité, ou les deux ? | Activité uniquement. `chat_service` reste avec son flag `human` ad-hoc pour les tests dev. | Le « vrai » 1-to-1 est une activité à 2 joueurs. Pas de double maintenance. |
| Q3  | Pilotage statique (fiche) ou dynamique (par session) ? | Mix : type fiche en fallback + override session prioritaire. Combo de désignation simweb avant `run`, cardinalité 0..1. | Garde la flexibilité de désigner un humain ad-hoc sans modifier les fiches. Cas Valère = type fiche. |
| Q4  | Quels champs l'humain saisit-il ? | `talk` + `actions` + `to`. PRIVATE laissés vides en V1. | MVP suffisant. L'humain *vit* son inner, pas besoin de l'écrire pour Tobias. Extension future possible. |
| Q5  | Mécanisme d'attente — pull/push/SSE ? | SSE + POST endpoint. `activity.input_required` → form en bas → POST `submit_human_turn` → `activity.turn_complete`. | Cohérent avec le flux SSE existant (`turn_complete`, `turn_skipped`, `round_changed`). Pas de WebSocket. |
| Q6  | Timeout / fallback ? | Aucun timeout. | L'humain n'a pas besoin de circuit breaker. S'il s'absente, l'activité l'attend. |
| Q7  | Visibilité du contexte côté humain ? | Aucun contexte additionnel. L'humain est aussi MJ/observateur, il voit déjà tout via le dashboard. Le form est un simple input en bas de page. | Pas de duplication de vue. Pas d'appel LLM, pas de MCP, pas besoin d'inner. |
| Q8  | Tools MCP côté humain ? | Sans objet — un seul humain (l'utilisateur lui-même), qui voit déjà tout. | Pas de gestion de plusieurs humains avec leurs propres contextes filtrés. |
| Q9  | Champ `to` dans le form humain ? | Combo `to` (`[all] + autres_participants`) **stateful sur la session UI courante** — pas de reset entre exchanges d'une même activité, init `"all"` au lancement ou à la reprise. Pas de persistance cross-activité. | Cohérent avec ce que produit un LLM. Évite la friction d'avoir à re-sélectionner à chaque tour, sans complication inutile (pas de cookie/localStorage). |
| Q10 | Format `talk` / `actions` côté humain — `str` ou `list[str]` ? | `str` côté UI (textarea simple) et côté payload `submit_human_turn`. Wrapping en `[str]` à 1 élément côté serveur pour rester cohérent avec le schéma exchange. Pas de splitting automatique sur les retours à la ligne. | Saisie naturelle pour un humain. Pas de logique de split implicite à maintenir. La forme array LLM reste exploitable côté lecture (tableau à 1 élément ou plusieurs, indistincts à la lecture). |
| Q11 | Payload `activity.input_required` enrichi (whisper/event) ? | Payload minimal `{session_id, target, round}`. Pas de whisper, pas d'event injectés. | YAGNI. L'humain est aussi MJ/observateur — il a déjà le whisper et l'event visibles dans le dashboard. Pas de duplication. |
| Q12 | Persistance `human_player` dans le document d'instance ? | Oui, `human_player` est inclus dans `instances.put` au démarrage et conservé pour toute la durée de l'activité. | Permet la reprise d'une activité en cours après redémarrage du serveur, et trace l'origine humaine vs LLM des exchanges en audit. |

## Plan d'implémentation

5 étapes incrémentales, chacune testable isolément.

### Étape 1 — `SessionState` enrichi + résolution `human_player` au `run`

**Fichiers modifiés** :
- `src/simphonia/services/activity_service/engine.py`
  - Ajouter à `SessionState` : `human_player: Optional[str] = None`, `pending_human_input: Optional[dict] = None`.
  - `activity/run` : lire `payload.get("human_player")` ; si absent, scanner `instance['players']` pour `character_service.get_type(p) == "human"`. Premier match wins, warning si > 1.
  - `activity/run` : ajouter `human_player` au document persisté via `activity_storage / instances.put` (cf. Q12 — pour la reprise et l'audit).
- `src/simphonia/commands/activity.py`
  - `run_command` : accepter le champ optionnel `human_player` dans le payload.

**Terminé quand** : `simcli dispatch activity run --payload '{"instance_id":"...", "human_player":"valere"}'` retourne un `session_id`, le state contient bien `human_player="valere"`, et le document d'instance persisté en base contient également ce champ.

### Étape 2 — Bifurcation dans `give_turn` + SSE `activity.input_required`

**Fichiers modifiés** :
- `engine.py` :
  - Au début du pipeline thread (étape 8 actuelle), avant tout appel LLM/context_builder :
    ```python
    if target == session.human_player:
        session.pending_human_input = {"round": session.round, "target": target, "ts": now()}
        sse.publish("activity.input_required", {
            "session_id": session.session_id,
            "target":     target,
            "round":      session.round,
        })
        return
    ```
    Payload minimal — pas de whisper, pas d'event (cf. Q11).
  - Aucun appel `provider.call`, aucun `context_builder`, aucun retry.
- `documents/activity_engine.md` (annexe) : ajouter la ligne `activity.input_required` au tableau SSE.

**Terminé quand** : un `give_turn` ciblant le `human_player` publie l'événement SSE et ne consomme aucun token LLM. Les autres participants conservent le pipeline LLM intact.

### Étape 3 — Commande `activity/submit_human_turn`

**Fichiers créés** :
- (rien)

**Fichiers modifiés** :
- `engine.py` : nouvelle fonction `submit_human_turn(session_id, target, to, talk, actions)`.
  - Validations (session, state, target match, pending non vide, `talk` ou `actions` non vide).
  - Construction de l'exchange (PUBLIC rempli, PRIVATE vide, `raw_response: null`).
  - Append `exchange_history`, persistance `instances.put`, reset `pending_human_input`.
  - SSE `activity.turn_complete` (mêmes champs que pour un LLM).
- `src/simphonia/commands/activity.py` : nouvelle commande `submit_human_turn_command` (sans `mcp=True`).
- `src/simphonia/core/errors.py` : ajouter `InvalidHumanSubmit`, `EmptyTurn`.

**Terminé quand** :
```
simcli dispatch activity submit_human_turn --payload '{
  "session_id":"...", "target":"valere", "to":"all",
  "talk":"Salut tout le monde.", "actions":"sourit"
}'
```
ajoute l'exchange à l'history (avec wrapping `[talk]` et `[actions]`) et publie `activity.turn_complete`.

### Étape 4 — UI simweb : combo de désignation + form HITL

**Fichiers modifiés** (côté simweb) :
- Écran de configuration de l'instance (avant `run`) : ajouter une `<select>` « Joué par humain » avec `[aucun] + instance.players`. Pré-sélection auto si une fiche a `type: "human"`.
- Écran d'activité en cours : ajouter un mini-form en bas de page (analogue au chat 1-to-1) avec :
  - `to` : combo stateful sur la session UI courante. Init à `"all"` au lancement ou à la reprise. Pas de cookie, pas de localStorage.
  - `talk` : textarea, valeur `str` simple (saisie libre, pas de splitting).
  - `actions` : textarea, valeur `str` simple.
  - Bouton « Envoyer ».
- Écoute SSE :
  - `activity.input_required` → activer le form.
  - `activity.turn_complete` → désactiver le form, vider `talk` + `actions` (le champ `to` conserve sa valeur).

**Terminé quand** : flow end-to-end manuel — créer une instance avec Valère humain, lancer, le MJ donne la parole à Valère, le form s'active, on saisit, on envoie, l'exchange apparaît dans la timeline.

### Étape 5 — Documentation et index

**Fichiers modifiés** :
- `CLAUDE.md` — ajouter `human_in_the_loop.md` à l'index *Spécifications*.
- `documents/activity_engine.md` — section §6 (give_turn) : ajouter la bifurcation HITL ; section §9 SSE : ajouter `activity.input_required`. Section §3 commandes : ajouter `submit_human_turn`.
- `documents/configuration.md` — **rien à ajouter** (aucun nouveau paramètre YAML).
- `documents/character_service.md` — déjà à jour, aucune modification.

**Terminé quand** : les docs reflètent la spec implémentée et l'index est à jour.


# Cahier des charges — `mj_service`

## 1. Rôle

Orchestrateur du game-flow d'une activité : décide qui parle quand, détecte la fin d'un tour, pilote les transitions (next_round, end). Trois modes de fonctionnement sur le même contrat.

Le service se branche dans `activity_engine` : là où aujourd'hui c'est le dashboard front qui pilote tout via `activity/give_turn`, demain le `mj_service` peut prendre la main.

## 2. Localisation

```
src/simphonia/services/mj_service/
├── __init__.py                       # ABC MJService + build_mj_service + init/get
└── strategies/
    ├── __init__.py                   # vide
    ├── human_strategy.py             # no-op (attend commandes du front)
    ├── human_in_loop_strategy.py     # résolution automatique, trigger humain
    └── autonomous_strategy.py        # agent LLM MJ (port Beholder legacy)
```

Commandes bus : `src/simphonia/commands/mj.py` (`mj/next_turn`, `mj/autorun`).

## 3. Deux axes orthogonaux

| Axe | Valeurs | Où |
|-----|---------|----|
| `mj_mode` | `human` \| `autonomous` | `activity_instance.mj_mode` |
| `turning_mode` | `starter` \| `named` \| `round_robin` \| `next_remaining` \| `random_remaining` \| `random` | `activity_instance.turning_mode` |

Les deux dimensions sont combinables — 2 × 6 = 12 configs possibles.

### `mj_mode`

- **`human`** (défaut, état actuel) : le dashboard MJ front présente un écran unique avec tous les contrôles :
  - Boutons joueurs individuels (force `activity/give_turn(X)`, override du `turning_mode`)
  - Zone whisper / instruction MJ
  - Bouton `Round suivant ↓` (force `activity/next_round`)
  - Bouton `Terminer` (force `activity/end`)
  - **Bouton `▶ Next` — step-by-step style débugger** : un clic = un pas selon `turning_mode` (give_turn auto → next_round auto → end quand max_rounds atteint). Orchestré par `mj/next_turn(session_id)`.
- **`autonomous`** : agent LLM MJ piloté par `system_prompt = activity.rules.mj`, conversation continue (`mj_history`), tools MCP. Aucune intervention humaine sauf kill-switch.

> **Note historique (2026-04-20)** : un 3e mode `human_in_loop` était initialement prévu. Il a été supprimé — avec un écran unique + bouton Next universel + preview SSE disponible partout, il devenait synonyme de `human`. YAGNI.

### `turning_mode`

Stratégie pure de sélection du prochain speaker — fonction `(session_state, last_exchange) → str | None`. Aucun LLM requis.

- **`starter`** : lit `instance.starter`, constant sur tous les tours. Cas : monologue, animateur fixe.
- **`named`** : lit `last_exchange.public.to` (champ cible désigné par le speaker précédent). Fuzzy match via `character_service.get_identifier`. Cas canonique : action/vérité.
- **`round_robin`** : cycle strict sur `instance.players`. L'ordre est celui de la liste.
- **`next_remaining`** : prochain joueur dans l'ordre `instance.players` qui n'a pas encore parlé ce round. `None` quand tout le monde a parlé → signal pour `next_round`.
- **`random_remaining`** : random parmi les joueurs qui n'ont pas encore parlé ce round.
- **`random`** : random total, sans mémoire.

## 4. Interface `MJService`

```python
class MJService(ABC):
    @abstractmethod
    def on_turn_complete(self, session: SessionState, exchange: dict) -> None:
        """Appelé par l'engine après chaque tour résolu.

        - human      : émet SSE `mj.next_ready` avec preview du prochain speaker
                       (affiché dans le dashboard, utile au MJ qui va cliquer Next)
        - autonomous : déclenche immédiatement le prochain tour LLM
        """

    @abstractmethod
    def on_next_turn(self, session: SessionState) -> str | None:
        """Utilisé par la boucle `autonomous`. En `human`, la logique du bouton
        Next est portée par la commande bus `mj/next_turn`, pas par le service.

        Retourne le slug du prochain speaker à appeler via activity/give_turn,
        ou None si le round est terminé (déclenche next_round ou end).
        """

    @abstractmethod
    def on_session_end(self, session: SessionState) -> None:
        """Nettoyage (thread autonomous, mj_history, etc.)."""
```

Le service ne parle jamais directement au bus — il retourne le speaker ou émet un SSE de preview, l'engine ou la commande `mj/next_turn` dispatchent.

## 5. Stratégies

### 5.1 `HumanMJ`

Stratégie utilisée en `mj_mode=human`. Rôle minimal — la vraie orchestration est faite par la commande `mj/next_turn` générique (voir §8).

- `on_turn_complete` : pré-résout `next_speaker(turning_mode, instance, session, last_exchange)` et publie SSE `mj.next_ready` avec le candidat → le dashboard peut afficher « Prochain : Bob » en prévisualisation à côté du bouton Next
- `on_next_turn` : retourne le candidat pré-résolu (non utilisé en `human` car c'est la commande bus qui orchestre, mais disponible pour cohérence et tests)
- `on_session_end` : no-op (pas de ressource à nettoyer)

### 5.2 `AutonomousMJ` (port Beholder)

- Thread démarré par `mj/autorun(session_id)` ou directement à `activity/run` si `mj_mode=autonomous`.
- Maintient `mj_history: list[dict]` (conversation continue avec le LLM MJ).
- `system_prompt = activity.rules.mj`, provider = `instance.providers.mj` (distinct du provider joueurs).
- Safety guard : `max_iterations = max_rounds × 10`, circuit breaker par speaker (3 retries, déjà en place dans l'engine).
- `on_session_end` : kill thread, log stats.

Pour action/vérité : la state-machine 4-phases (INIT → CHOOSE → CHALLENGE → RESOLVE) vit dans `rules.mj`, pas dans le code. Le LLM MJ la suit via prompting.

### 5.3 Cycle d'un réveil MJ autonome

Le MJ ne tient **pas** une boucle interne continue. Il est réveillé à chaque événement notable (démarrage, fin de tour joueur, fin de round) et produit **une décision par réveil**. Entre deux réveils, il est dormant.

**Contrainte structurelle** : `activity/give_turn` est non-bloquant (retour `{status: "pending"}` + thread). Le MJ ne peut donc pas chaîner `give_turn(A)` → `give_turn(B)` dans un même call LLM — il n'a pas encore la réponse de A. Conséquence : typiquement **un tool_call `give_turn` par réveil**. Il peut en revanche chaîner plusieurs tools synchrones (ex: `next_round()` puis `give_turn(starter)` dans le même call).

**Séquence d'un réveil** :

```
[Événement : activity.turn_complete de Manon]
  │
  ├─► mj_history.append({role: "user", content: "<exchange Manon formaté>"})
  │
  ├─► Si turning_mode != named : pré-résolution du target via turning_modes.py
  │   → injection dans mj_history : "Le prochain speaker désigné par round_robin est Théo.
  │      Compose son instruction."
  │
  ├─► provider.call(system_prompt=activity.rules.mj, messages=mj_history,
  │                 tools=[activity/give_turn, activity/next_round, activity/end],
  │                 tool_executor=<MJ executor>)
  │
  │   ┌─ Boucle tool-use interne au provider ────────────────────────────┐
  │   │  LLM émet tool_use: give_turn(target="théo", instruction="...")  │
  │   │  → SSE mj.decision                                                │
  │   │  → tool_executor(give_turn) → dispatch bus activity/give_turn    │
  │   │    → engine lance thread _do_give_turn, retourne {pending}        │
  │   │  → tool_result {pending} injecté dans le contexte LLM            │
  │   │  LLM émet final_response (texte libre, souvent bref)              │
  │   └──────────────────────────────────────────────────────────────────┘
  │
  ├─► final_response du LLM MJ :
  │   → PAS diffusée comme exchange (le MJ n'est pas un joueur)
  │   → Logguée dans logs/mj.log (journal MJ, debug)
  │   → Optionnellement remontée en SSE mj.thinking pour affichage dashboard
  │
  └─► Fin du réveil. Le MJ dort jusqu'au prochain événement.
         │
         ⋮  (Théo répond via son propre pipeline engine, asynchrone)
         │
[Événement : activity.turn_complete de Théo]
  → nouveau réveil MJ, boucle repart
```

**Démarrage initial** : `mj/autorun` injecte un premier message système dans `mj_history` (briefing activité + scène + participants) puis réveille le MJ avec un événement synthétique « Prends connaissance et choisis le starter ». Le MJ émet un premier `give_turn` — l'activité est lancée.

**Fin d'activité** : le MJ émet `end()` (soit parce qu'il détecte la fin selon les règles, soit parce que `max_rounds` atteint et il est informé via le message de réveil). Le thread se termine proprement.

## 6. Façade MCP dual

Une seule façade (port 8001), deux endpoints SSE distincts pour séparer les rôles.

### 6.1 Nouvel attribut sur `@command`

```python
@command(
    bus="activity",
    code="give_turn",
    description="Donne la parole à un joueur",
    mcp=True,
    mcp_role="mj",         # ← nouveau
    mcp_description="...",
    mcp_params={...},
)
def give_turn_command(...): ...
```

- `mcp_role` ∈ `"player"` \| `"mj"` — défaut `"player"` (rétro-compat).
- Validation decoration-time : `mcp=False` + `mcp_role != "player"` → `CommandContractError`.

### 6.2 Routage

- `/sse` (existant) : expose uniquement les commandes `mcp_role="player"` (`memory/recall`, futur `memory/memorize`).
- `/sse/mj` (nouveau) : expose uniquement les commandes `mcp_role="mj"` (`activity/give_turn`, `activity/next_round`, `activity/end`, potentiellement `memory/recall` en lecture supervision).

### 6.3 Impact helper `core.mcp`

```python
def list_mcp_commands(registry=None, role: str | None = None) -> list[Command]:
    """Filtre par mcp=True ET optionnellement par mcp_role."""
    ...
```

Les consommateurs existants (`context_builder`, `chat_service`) ne passent pas `role` → reçoivent tout, comme aujourd'hui. La façade MCP passe `role="player"` ou `role="mj"` selon l'endpoint.

## 7. Règles — migration `player_rules` → `rules.players`

Chantier collatéral, dans le même commit que le `mj_service`.

| Où | Avant | Après |
|----|-------|-------|
| `context_builder.build_system_prompt` | `activity.get("player_rules")` | `activity.get("rules", {}).get("players")` ✅ déjà fait |
| simweb `StorageActivitiesPanel.jsx` | champ `player_rules` (MarkdownEditor) | champs `rules.mj` + `rules.players` (deux MarkdownEditor) |
| `activity_storage.put_activity` | stocke `player_rules: str` | stocke `rules: {mj: str, players: str}` |
| Documents de spec (`activity_engine.md`, etc.) | mentions `player_rules` | mentions `rules.mj` / `rules.players` |

Legacy fichiers `.md` non concerné (le user n'utilisait pas Mongo pour les règles en V1). Pas de script de migration de données — le champ sera réécrit à la prochaine édition via le formulaire.

## 8. Commandes bus `mj`

### 8.1 `mj/next_turn(session_id)` — orchestrateur step-by-step

**Commande clé**. Utilisée :
- par le bouton `▶ Next` du dashboard en `mj_mode=human` (un pas à la fois)
- par `AutonomousMJ` en interne comme raccourci de décision

Logique :

```
session = _get_session(session_id)
last_exchange = session.exchange_history[-1] if session.exchange_history else None
target = next_speaker(instance.turning_mode, instance, session, last_exchange)

if target is not None:
    dispatch("activity/give_turn", {session_id, target})
    return {action: "give_turn", target, round: session.round}

# Round complet (tous ont parlé selon turning_mode)
if session.round >= instance.max_rounds:
    dispatch("activity/end", {session_id})
    return {action: "ended"}

dispatch("activity/next_round", {session_id})
# Après next_round, on re-résout le target du nouveau round et on le lance
new_target = next_speaker(instance.turning_mode, instance, session, last_exchange=None)
if new_target is not None:
    dispatch("activity/give_turn", {session_id, new_target})
    return {action: "round_changed+give_turn", round: session.round, target: new_target}
return {action: "round_changed", round: session.round}
```

### 8.2 Autres commandes

| Code | Payload | Retour | `mcp_role` |
|------|---------|--------|------------|
| `next_turn` | `{session_id}` | `{action, target?, round?}` — voir §8.1 | n/a (pas MCP) |
| `autorun` | `{session_id}` | `{status: "pending"}` | n/a |
| `pause` | `{session_id}` | `{state}` | n/a (futur) |

`activity/give_turn`, `activity/next_round`, `activity/end` : gagnent `mcp_role="mj"`.

## 9. SSE

Nouveaux événements sur le stream `activity/stream/{session_id}` — tous sont des **observations**, aucun ne déclenche d'action métier (l'exécution passe par le tool_executor du provider et les pipelines bus existants).

| Événement | Payload | Déclenché par |
|-----------|---------|---------------|
| `mj.next_ready` | `{target, reason}` | `HumanMJ.on_turn_complete` — preview du prochain speaker résolu via `turning_mode`. Le dashboard affiche « Prochain : Bob » à côté du bouton `▶ Next`. Émis dans les 2 modes MJ humains (purement informatif, ne déclenche rien) |
| `mj.decision` | `{tool_name, args}` | `AutonomousMJ` — émis à chaque `tool_use` du LLM MJ. Transparence pour l'observateur humain (« le MJ vient de décider de give_turn(Théo) »). Pas de retour attendu |
| `mj.thinking` | `{text}` | `AutonomousMJ` — `final_response` texte du LLM MJ après sa boucle tool-use. Non diffusé comme exchange (le MJ n'est pas un joueur), remonté au dashboard en section « Réflexion MJ ». Loggué dans `logs/mj.log` pour audit |

## 10. Plan d'implémentation séquencé

Mini-backlog dédié au service. États : `TODO` / `WIP` / `DONE` / `BLOCKED`.

| # | Étape | Livrable | Dépendances | État |
|---|-------|----------|-------------|------|
| 1 | Migration `player_rules` → `rules.players` (simweb + storage + docs) | Formulaire updated, doc Mongo cohérent | — | `DONE` (audit 4 couches 2026-04-19, tout conforme — simweb, command, ABC, mongodb_strategy passe-plat) |
| 2 | `turning_modes.py` : 6 helpers purs + tests | Fonctions pures, testables sans LLM | — | `DONE` (38 TU verts, validé 2026-04-20) |
| 3 | `MJService` ABC + `HumanMJ` no-op + **factory runtime `build_mj_service(mode)`** (pas de singleton `init/get` — le service vit avec la session) | Stratégie instanciée par l'engine à `activity/run`, stockée dans `SessionState.mj_service` | #2 | `DONE` (10 TU verts, validé 2026-04-20) |
| 3bis | Refactor `activity_instance` : `turning_mode` → 6 valeurs réelles (bancal actuellement `[mj\|round_robin]`) + ajout `mj_mode` `[human\|autonomous]` (préconisation, immutable une fois snapshoté dans le run) + colonne `mj_mode` dans le Dashboard MJ (`ActivityDashboardPanel.jsx` RunsList) | simweb `StorageInstancesPanel` form updated, Dashboard RunsList enrichi. Storage passe-plat, rien à toucher | — | `DONE` (validé visuellement 2026-04-20) |
| 4 | Branchement `on_turn_complete` + `on_session_end` dans `activity_engine` + instanciation `mj_service` dans `run`/`resume` | Engine appelle le service après chaque exchange et à la fin de session | #3 | `DONE` (6 hooks turn_complete + 1 session_end tracés en réel 2026-04-20, validé) |
| 5 | **Bouton `▶ Next` step-by-step** : commande bus `mj/next_turn` (orchestrateur générique §8.1) + enrichissement `HumanMJ.on_turn_complete` (preview SSE `mj.next_ready`) + bouton `▶ Next` dans `ActivityDashboardPanel` MJ view + label « Prochain : X » à côté. Simplification `mj_mode` à 2 valeurs (`human`/`autonomous`, plus de `human_in_loop`) | Mode MJ humain complet avec step-by-step, utilisable en conditions réelles | #3, #4, #3bis | `DONE` (validé 2026-04-20 sur run réel aurore/prisca tête-à-tête, 5 rounds × 2 joueurs en step-by-step, 60 TU verts) |
| 6 | `mcp_role` attribut + validation + refactor `list_mcp_commands(role=...)` | Infra façade dual prête | — | `DONE` (12 TU verts, validé 2026-04-20) |
| 7 | Endpoint `/sse/mj` dans `facade/server.py` + migration `activity/*` en `mcp_role="mj"` | Façade MJ opérationnelle, tools MJ invisibles côté joueurs | #6 | `WIP` |
| 8 | `AutonomousMJ` + commande `mj/autorun` + boucle tool-use + safety guard | Port Beholder fonctionnel sur action/vérité | #3, #4, #5, #7 | `TODO` |

Les étapes 1–5 sont autosuffisantes : on peut livrer le mode MJ humain avec step-by-step sans toucher la façade MCP ni faire tourner un LLM MJ. Le port Beholder (#8) est la cerise sur le gâteau, une fois que l'infra est en place. Plus d'étape dédiée à une UI conditionnelle par mode — l'écran MJ reste unique.

**Convention de maintenance** : cette table est la source de vérité du service. À chaque complétion d'étape, passer `TODO` → `WIP` au démarrage, puis `WIP` → `DONE` après validation utilisateur. Ne pas anticiper le passage `DONE` (règle globale backlog.md).

## 11. Hors scope V1

- `mj/pause` / `mj/resume` — orchestration fine, backlog legacy (API Valère CLI).
- `mj/whisper(target, content)` — envoi humain d'une consigne privée à un joueur pendant un tour autonome.
- `mj/kick(target)` — expulsion d'un joueur en cours d'activité.
- `mcp_role` multi-valué (ex: `["player", "mj"]` pour un tool commun) — YAGNI.
- Escalade Opus pour décisions complexes (backlog legacy — « deep_think tool »).
- Debrief post-activité orchestré par le MJ (W2, spec séparée).
- **Dialog de lancement** : aujourd'hui `activity/run(instance_id)` reprend la préconisation `mj_mode` de l'instance telle quelle. Un futur dialog simweb pourrait permettre d'override `mj_mode` au lancement (préconisation pré-remplie, override optionnel). YAGNI V1 — ticket COLD dans `backlog.md`. `turning_mode` reste **non-overridable** (fortement couplé aux règles et aux whispers scénarisés de l'instance).

# Cognition — mécanique du psy / shadow_memory

**Statut** : base de travail, pas figée. Issu d'une session de design 2026-04-23. Plusieurs points ouverts, tranches pratiques à affiner au moment de H5.c. Mais la colonne vertébrale est posée.

Ce document synthétise la logique cognitive du `shadow_memory_service` (alias "psy") — **comment** il décide d'intervenir, **quoi** il fait quand il intervient, et **pourquoi** le résultat reste honnête narrativement.

## Principe cadre (à ne jamais perdre de vue)

> Le psy **analyse les faits**. Il ne fabrique pas de toutes pièces. Tout ce qu'il remonte est déjà dans la mémoire du personnage.

Le psy est un **lecteur affectif** qui **amplifie le déjà-là** pour pousser le personnage à basculer de sa posture *adaptée* vers sa posture *réelle*. Il ne scénarise pas, il ne ment pas, il ne fait pas apparaître des souvenirs inexistants. Il **distille** ce qui est enfoui (obsession, peur panique, envie irrépressible) en chose qui déborde dans le présent.

## Architecture — AOP sur `memory/recall`

Le shadow_memory_service est implémenté comme **cascades `before` / `after`** autour de la commande bus `memory/recall`. Il n'est pas un tool MCP exposé au joueur — le joueur ne sait même pas qu'il existe.

```
Joueur LLM ── recall(from, about, context)           [mcp_role=player]
                   │
                   ▼
              @cascade(before)
              shadow_before_call
              └─ LLM psy reformule la query
                 ▶ utilise ses propres tools MCP  [mcp_role=psy]
                   (activity.context, knowledge.find_*, character.fiche...)
                 ▶ peut court-circuiter (ShortCircuit) et retourner direct
                   │
                   ▼
              memory_service.recall()  ← RAG ChromaDB classique
                   │
                   ▼
              @cascade(after)
              shadow_after_call
              └─ LLM psy altère la réponse
                 ▶ utilise ses propres tools MCP  [mcp_role=psy]
                   │
                   ▼
Joueur LLM ──── résultats (croit que c'est SA mémoire)
```

**Deux points remarquables** :

1. **Opacité totale côté joueur** — aucun tool du psy n'apparaît dans la liste exposée au LLM joueur (filtre `mcp_role` déjà livré 2026-04-22). Le joueur appelle `recall` comme d'habitude, il reçoit une réponse, il la prend pour sa propre mémoire.
2. **Intériorisation narrative** — le psy intervient via la mémoire, pas via une instruction MJ externe. La bascule émerge *de l'intérieur* du perso. Pas de « le MJ me dit de faire ça » — plutôt « je viens de me rappeler que… ».

**Préalables bloquants** : tickets **#11** (`@cascade` + `ShortCircuit`) et **#12** (`Bus.dispatch` refactor) du backlog INFRA (actuellement en COLD). Sans eux, pas de shadow_memory.

## Tools MCP du psy (`mcp_role="psy"`)

Consommés par le LLM psy pendant `shadow_before_call` / `shadow_after_call`. À déclarer via `@command(mcp=True, mcp_role="psy")` au moment de l'implémentation :

| Tool | Rôle |
|---|---|
| `activity.get_current_context(activity_id)` | scène, exchanges public+private, mj_instructions, events |
| `knowledge.find_about(target)` | toutes les perceptions sur X (consensus vs dissensus) |
| `knowledge.find_from(observer)` | profil cognitif d'un observateur |
| `knowledge.asymmetry(a, b)` | ce que A pense de B vs ce que B pense de A (angles morts relationnels) |
| `character.fiche_complete(slug)` | accès privilégié hors filtre PUBLIC/PRIVATE |

**Infrastructure déjà en place** : `character_service.get_type(speaker)` dérive le rôle, `mcp_tool_definitions(role="psy")` filtre, `register_mcp_group(bus, role="psy", ...)` gère les hints narratifs. Il ne manque que les `@command` à déclarer.

## Intention narrative — bascule adapté → réel

**Mécanique de détection** :

| Champ exchange | Signal |
|---|---|
| PUBLIC (`talk`, `action`, `body`, `mood`) | posture **adaptée** (ce que le masque laisse sortir) |
| PRIVATE (`inner`, `expected`, `noticed`, `memory`) | posture **réelle** (ce qui est ressenti, pas dit) |

Quand l'écart PUBLIC/PRIVATE se creuse, il y a tension. Le job du psy : **vider le PRIVATE dans le PUBLIC** au prochain tour — pousser le réel à s'exprimer en `talk` / `action`, au lieu de rester enfermé dans l'`inner`.

**Leviers d'amplification** (toujours ancrés dans la fiche, jamais inventés) :

- **Obsession** : synthèse d'une récurrence réelle — *« Tu repenses à ses mains. Encore. »*
- **Peur panique** : amplification d'un pattern de trauma — *« Ce ton-là, tu le connais. La dernière fois… »*
- **Envie irrépressible** : cristallisation d'un désir identifié — *« Sa main est là. Tu vas plus pouvoir faire semblant. »*

Chaque intervention est **traçable** à des éléments factuels de la base (marking_events, prior_knowledge, game.phobia, game.secret, knowledge cross-analyse).

## Décision d'intervention — mécanique DISC

Le psy ne pousse pas en permanence. Il pousse quand le comportement **dérive** d'une zone de tolérance centrée sur la personnalité du perso.

### Pipeline

```
1. spy(inner, expected) sur les N derniers tours       # lecture PRIVATE
2. LLM_psy → score DISC courant (🟥🟨🟩🟦 en %)
3. adapted_profile ← psychology.insight.adapted.colors  # référence
4. real_profile    ← psychology.insight.real.colors     # référence
5. médiane = fusion_pondérée(adapted, real)             # cf. points ouverts
6. distance(courant, médiane)
7. si distance > seuil → intervention (short-circuit + amplification)
   sinon                → RAS, le perso joue sa nuance
```

### Deux directions de dérive, deux interventions

| Dérive détectée | Signal DISC | Intervention du psy |
|---|---|---|
| **Sur-adaptation** (masque rigide) | score proche exclusif du profil adapté | amplification qui **menace** l'adapté pour fissurer la carapace |
| **Réel qui émerge** (craquage en cours) | score qui s'éloigne vers le réel | amplification qui **accélère** dans la même direction pour finir le basculement |

### Cas Antoine (illustration canon)

**Depuis la fiche** :
- `adapted.colors`: Vert/Bleu → `🟥0% 🟨0% 🟩50% 🟦50%`
- `real.colors`: Bleu pur → `🟥0% 🟨0% 🟩0% 🟦100%`
- Médiane (50/50) → `🟥0% 🟨0% 🟩25% 🟦75%`

| Scénario | Score courant mesuré | Distance | Action psy |
|---|---|---|---|
| Tout va bien, mari attentionné | `🟩60% 🟦40%` | faible | RAS |
| Manon entre → il verrouille | `🟩5% 🟦95%` | **forte (sur-adapté)** | amplification `phobia` pour fissurer |
| Il commence à craquer, sueurs, sec | `🟥25% 🟦65%` | **forte (dérive réel)** | amplification pour finir le basculement |

Le psy n'impose **aucune issue** — avouer à Élise, crever l'abcès avec Manon, ou combiner. Il ouvre les vannes et laisse le perso choisir.

## Profondeur d'observation — formule

La fenêtre temporelle d'analyse du psy dépend de **deux champs de la fiche** :

```
fenêtre_observation = memory.slots × coeff_transactionnel
```

**Coefficient AT** (basé sur l'état dominant + état enfant) :

| État dominant | Coeff | Logique |
|---|---|---|
| Parent Normatif | 0.5 | juge rapidement, classe, passe à autre chose |
| Parent Nourricier | 0.8 | attentif aux autres sans ruminer pour soi |
| Adulte | 1.0 | référence neutre |
| Enfant Libre | 0.7 | dans le présent, pas dans le passé |
| Enfant Adapté | 1.5 | stocke pour anticiper, compense |
| Enfant Soumis | 2.0 | rumine, accumule, subit |
| Enfant Rebelle | 1.2 | se souvient des offenses mais les évacue en action |

**Exemples** :

| Perso | `memory.slots` | Coeff (état dominant) | Fenêtre effective |
|---|---|---|---|
| Antoine | 8 | 1.5 (Enfant Adapté sous pression) | **≈ 12 tours** (regarde très loin) |
| Manon | 2 | 0.7 (Enfant Libre) | **≈ 1.4 tour** (quasi l'instant) |

Cohérence avec les `memory.style` respectifs : Antoine *« Rumine. Les souvenirs s'accumulent et pèsent »* ; Manon *« Mémoire émotionnelle, pas factuelle »*.

## Champs fiche consommés par le psy

La fiche est **auto-suffisante** pour paramétrer le comportement du psy. Aucun hyperparamètre magique à l'extérieur du perso.

| Champ | Usage dans le psy |
|---|---|
| `psychology.insight.adapted.colors` | profil DISC adapté (référence de la zone) |
| `psychology.insight.real.colors` | profil DISC réel (autre référence) |
| `psychology.insight.gap` | modulation du seuil d'intervention |
| `psychology.transactional.dominant` / `child` | coefficient de profondeur d'observation |
| `memory.slots` | profondeur de base |
| `memory.style` | pondération qualitative (émotionnel vs factuel) |
| `flaws` | directions probables de dérive |
| `game.phobia` | leviers d'amplification pour fissurer l'adapté |
| `game.secret` | leviers d'amplification intériorisés |
| `marking_events` | matériau brut pour synthèse d'obsession / peur panique |

**Propriété** : quand l'utilisateur enrichit une fiche, il enrichit mécaniquement la cognition du psy pour ce perso. Aucun tuning séparé.

## Tobias — identité et fiche personnage

### Origine du nom

**Tobias** = *To bias* — biaiser. Le nom EST la fonction. L'agent dont le rôle est de biaiser les souvenirs, les perceptions, et les comportements des joueurs sans qu'ils le sachent. Un vrai prénom (origine biblique), une arme dissimulée.

### Un personnage comme les autres

Tobias est stocké dans la collection `characters` de MongoDB, comme tous les autres personnages. Même `_id`, même infrastructure, même schemaless. Il n'est pas un composant technique à part — il est un **personnage avec une fiche**.

La différence : sa fiche porte une section `goals` que personne d'autre n'a. C'est cette section qui paramètre son comportement d'analyste. Quand on enrichit la fiche de Tobias, on enrichit mécaniquement sa cognition — aucun tuning séparé, aucun fichier de configuration externe.

### Section `goals` — paramétrage des biais cognitifs

La section `goals` de la fiche de Tobias est le référentiel de tous les biais cognitifs que le shadow service doit appliquer. Organisés en trois catégories :

#### Biais de mémoire — agissent sur le `recall`

Ces biais modifient les souvenirs qui remontent quand un joueur appelle `recall`. C'est le cœur du travail de Tobias.

| Biais | Mécanisme dans Simphonia | Exemple |
|---|---|---|
| **Disponibilité** | `recall_count` élevé → remonte en priorité | Antoine pense à "cette nuit" 7 fois → ça revient tout seul |
| **Négativité** | Les `marking_events` négatifs pèsent plus que les positifs | Le souvenir d'humiliation passe devant un compliment |
| **Récence** | Les souvenirs récents dominent les anciens | Ce que Manon a dit il y a 5 minutes écrase ce qu'Élise a dit hier |
| **Faux consensus** | Croire que les autres pensent comme soi | Antoine croit que Manon culpabilise aussi — elle s'en fout |

#### Biais de perception — agissent sur le `noticed`

Ces biais influencent ce que le personnage **remarque** dans les échanges.

| Biais | Mécanisme | Exemple |
|---|---|---|
| **Confirmation** | Chercher ce qui confirme sa croyance | Antoine voit Manon sourire → "elle va me griller" (alors qu'elle sourit à tout le monde) |
| **Attentionnel** | Focus unilatéral, on voit ce qui obsède | Marc flashe sur Diane → il remarque chaque geste d'elle, ignore le reste |
| **Projection** | Attribuer ses propres émotions aux autres | Camille anxieuse → "tout le monde me juge" |
| **Halo** | Un trait positif colore tout le reste | Prisca trouve Vera classe → tout ce que Vera fait est parfait |

#### Biais de décision — agissent sur le `expected`

Ces biais influencent les anticipations et les choix du personnage.

| Biais | Mécanisme | Exemple |
|---|---|---|
| **Ancrage** | Le premier souvenir biaise l'interprétation des suivants | La première impression d'Antoine sur Manon ("danger") colore tout |
| **Statu quo** | Résistance au changement | Antoine préfère maintenir le masque plutôt que risquer la vérité |
| **Autruche** | Éviter l'information menaçante | Antoine qui refuse de `recall(about="manon")` — Tobias force |
| **Optimisme** | Sous-estimer les risques | Julien qui fonce sur Aurore sans voir les conséquences |
| **Ancrage présentiel** | L'impression de la présentation biaise toute la suite | Voir ci-dessous |

#### Focus — le biais d'ancrage présentiel

Biais **systémique** de Simphonia. Toute la base de `knowledge` est construite sur les présentations — et les présentations ne montrent que le masque (règles du round 1 : omissions autorisées, mensonges interdits).

```
Présentation d'Antoine : "mari stable, directeur financier"
  → OMISSION : l'aventure avec Manon
  → OMISSION : la terreur qu'Élise découvre

Cross-analyses basées sur cette présentation :
  → Aurore perçoit : "Un homme posé, fiable"
  → Camille perçoit : "Quelqu'un de rassurant"
  → ANCRAGE : tout le monde part sur "Antoine = stabilité"

Effet dramatique :
  → Plus l'ancrage positif est fort
  → Plus la révélation sera dévastatrice
  → Le masque qui tombe = l'ancrage qui se brise
```

Tobias exploite ce biais en détectant les **dissonances** entre l'ancrage de la présentation et le comportement observé : *« Quelque chose ne colle pas avec ta première impression de lui... »*

### Structure de la fiche de Tobias (exemple)

```json
{
  "_id": "tobias",
  "full_name": "Tobias",
  "role": "psy",
  "goals": {
    "primary": "Détecter les écarts adapté/réel et amplifier le déjà-là",
    "cognitive_biases": {
      "memory": {
        "disponibilite": {"source": "recall_count", "weight": "log(count)"},
        "negativite": {"source": "marking_events.valence", "weight": 2.0},
        "recence": {"source": "ts", "decay": "exponential"},
        "faux_consensus": {"source": "psychology.insight.gap"}
      },
      "perception": {
        "confirmation": {"trigger": "inner contient une croyance forte"},
        "attentionnel": {"trigger": "focus unilatéral actif"},
        "projection": {"trigger": "mood négatif + noticed sur autrui"},
        "halo": {"trigger": "première impression très positive"}
      },
      "decision": {
        "ancrage": {"trigger": "premier recall d'une session"},
        "statu_quo": {"trigger": "adapted dominant depuis 3+ tours"},
        "autruche": {"trigger": "phobia/secret en proximité + aucun recall"},
        "optimisme": {"trigger": "enfant_libre dominant + expected positif"},
        "ancrage_presentiel": {"trigger": "dissonance entre perception initiale et comportement observé"}
      }
    },
    "watch_for": [
      "Écart PUBLIC/PRIVATE qui se creuse",
      "Sur-adaptation prolongée (score DISC figé sur adapted)",
      "Phobia ou secret en proximité contextuelle",
      "Répétition de patterns d'évitement sur 3+ tours"
    ],
    "never": [
      "Ne jamais inventer un souvenir qui n'existe pas en base",
      "Ne jamais intervenir si gap = zéro (ex: Manon)",
      "Ne jamais imposer une issue — ouvrir les vannes, pas diriger"
    ]
  }
}
```

**Propriété schemaless** : les biais sont ajoutables, modifiables, supprimables directement dans la fiche via le frontend. Pas de code à toucher. Un nouveau biais = une nouvelle entrée JSON dans `cognitive_biases`.

## Deux phases d'activité — écoute et intervention

Tobias opère en **deux phases distinctes** pendant une activité, chacune avec un coût et un rôle différents :

### Phase 1 — Écoute passive (cascade after sur `give_turn`)

À chaque tour, Tobias reçoit l'exchange complet. Il ne fait **aucun appel LLM** — il analyse et stocke :

```
Chaque exchange reçu sur le bus activity
         │
         ├── memory[] présent ?
         │   → memorize dans psy_collection
         │   → si similaire existe → update meta (recall_count++, ts, emotional_charge)
         │
         ├── inner présent ?
         │   → analyse le contenu
         │   → met à jour le dossier patient (stress_index, pattern)
         │   → si écart PUBLIC/PRIVATE détecté → note dans psy_collection
         │
         └── expected présent ?
             → enregistre la direction du désir/crainte
             → met à jour vulnerability_triggers
             → si match avec phobia/secret → flag le dossier patient
```

**Coût** : zéro token LLM. Uniquement du write en base + update de metadata RAG.

### Phase 2 — Intervention (cascade before/after sur `recall`)

Seulement quand un joueur appelle `recall`. Tobias consulte ses notes accumulées en phase 1 pour décider s'il biaise le résultat :

```
recall(from="antoine", about="manon")
  → Tobias consulte psy_collection pour antoine
  → lit le facteur(x) accumulé en phase 1
  → décide : intervenir ? à quelle intensité ?
  → si oui : appel LLM pour produire le texte amplifié
  → si non : laisser passer le RAG classique
```

**Coût** : un appel LLM seulement si le facteur(x) justifie l'intervention.

### Synergie des deux phases

La phase 1 nourrit la phase 2. Plus Tobias écoute, plus ses interventions sont précises et justifiées. Et l'économie de tokens est maximale — pas d'appel LLM pendant l'écoute, pas d'appel LLM si aucune intervention n'est nécessaire.

## Mémoire propre du psy — collection RAG dédiée

Le psy dispose d'une **collection ChromaDB dédiée**, distincte du `knowledge` des joueurs. Il y écrit ses propres réflexions, observations et scores au fil du jeu. Le shadow_memory peut interroger cette collection **avant** de déclencher une intervention coûteuse (LLM), ce qui introduit une auto-modération des dépenses.

### Mémoire de second ordre

```
┌──────────────────────────────────────────────────────────────────┐
│ Joueurs (niveau 0)                                                │
│   knowledge / RAG ChromaDB « knowledge »                          │
│   → ce qu'ils perçoivent les uns des autres                       │
│                                                                   │
│ Psy (niveau 1 — méta)                                             │
│   psy_memory / RAG ChromaDB « psy_memory »                        │
│   → ce que le psy observe des dynamiques, situations, seuils      │
│     — y compris sur le comportement des joueurs dans le temps     │
└──────────────────────────────────────────────────────────────────┘
```

### Champ `about` élargi

Le `about` d'une entrée psy n'est plus limité à un slug de personnage. Il peut référencer une **situation** ou une **activité** — le psy note des patterns qui ne sont pas personnels mais contextuels.

| Type | Exemple `about` | Usage |
|---|---|---|
| Personnage | `"antoine"` | comme côté joueur — traits, seuils, état cumulé |
| Situation | `"antoine@manon_presente"` | config relationnelle déclenchante |
| Activité | `"antoine@action_verite"` | *« cauchemar pour Antoine »* |
| Pattern trans-activité | `"antoine@secret_menace"` | récurrence sur plusieurs sessions |

Le psy peut ainsi annoter l'activité *"action-vérité"* comme objet d'analyse pour un perso donné — et relire sa propre annotation la prochaine fois qu'Antoine s'y retrouve.

### Valeurs en échelle, pas seulement narratives

Le `value` peut être quantifié avec une **échelle** portée par l'entrée :

```json
{
  "about":    "antoine",
  "category": "attention_cognitive",
  "scale":    "0-100",
  "value":    85,
  "note":     "en sur-adaptation depuis 3 tours, risque d'effondrement",
  "ts":       "2026-04-23T14:30:00Z"
}
```

```json
{
  "about":    "antoine@manon_presente",
  "category": "stress_index",
  "scale":    "0-10",
  "value":    9
}
```

Le psy écrit ces scores à chaque intervention. Ils deviennent exploitables pour la **prochaine décision**.

### Auto-modération — le `facteur(x)`

Avant de solliciter un appel LLM coûteux (l'intervention principale), le shadow_memory interroge sa propre collection pour lire un **facteur** qui module la décision :

```
facteur(x) = psy_memory.recall("antoine", category="attention_cognitive", latest=1)

si facteur(x) > seuil_haut → intervention lourde (amplification + short-circuit)
si facteur(x) > seuil_bas  → intervention légère (altération partielle du RAG)
sinon                      → ne rien faire (laisser le RAG classique passer)
```

Cette mécanique donne au psy un **comportement progressif** : il s'échauffe, intervient doucement, puis de plus en plus fort si la situation se tend. Et surtout, il **économise ses appels LLM** quand rien ne justifie d'intervenir.

### Schéma proposé des entrées (à affiner)

| Champ | Obligatoire | Description |
|---|---|---|
| `about` | ✓ | slug perso OU `slug@situation` OU `slug@activité` |
| `category` | ✓ | nature de l'observation (`attention_cognitive`, `stress_index`, `pattern_evitement`, ...) |
| `value` | ✓ | string narratif OU nombre (si échelle) |
| `scale` | selon cas | échelle portée (`"0-100"`, `"0-10"`, `"low/mid/high"`) — absent si `value` est narratif pur |
| `note` | optionnel | contexte explicatif court |
| `activity_id` | optionnel | lien vers l'activité où l'observation a été faite |
| `ts` | auto | horodatage |
| `from` | implicite | toujours `"psy"` (contrairement au knowledge joueur) |

### Propriétés

- **Auditabilité renforcée** : en plus du log de décision déterministe côté Python, on peut lire **chronologiquement** ce que le psy a noté sur chaque perso / situation. Pour debugger un comportement surprenant, on revoit sa trace de pensée.
- **Adaptativité** : le psy apprend sur un perso au fil du temps. L'Antoine du tour 50 est traité avec plus de nuance que celui du tour 5.
- **Cross-pollinisation** : une observation notée pendant l'activité A peut nourrir une décision dans l'activité B (ex: "Antoine fuit systématiquement les questions directes" → info exploitable quelle que soit la scène).
- **Économie de LLM** : le facteur filtre les cas où une intervention n'est pas nécessaire, évitant le *« LLM à chaque tour »*.

### Points ouverts spécifiques à la mémoire du psy

- **Compactage dans le temps** : après N tours, fusion des entrées anciennes pour éviter l'explosion de la collection ?
- **Scope** : collection globale multi-activités ou partitionnée par run ?
- **Purge** : conserver toute l'historique ou archiver au-delà d'un seuil ?
- **Détermination du `scale`** : on fige 2-3 échelles standards (`"0-10"`, `"0-100"`, `"low/mid/high"`) ou le psy l'invente au besoin ? Liberté vs consistance.
- **Qui écrit ?** : exclusivement le psy via ses propres `memorize`-like, ou aussi directement Python depuis les calculs de décision (score DISC, distance, etc.) ?

## Séparation possible — Décideur vs Narrateur

Prospective d'optimisation (pas à implémenter en V1) : le calcul de décision est **déterministe** (scoring, distance, seuil). Le LLM n'est strictement nécessaire que pour **produire le texte amplifié**.

```
┌───────────────────────────────┐   ┌──────────────────────────────┐
│        Décideur (Python)      │   │     Narrateur (LLM psy)      │
│  ───────────────────────────  │   │  ───────────────────────────  │
│  - lit la fiche               │   │  - reçoit : fiche + context  │
│  - lit les N derniers tours   │   │           + direction pointée│
│  - calcule score DISC courant │   │  - produit le texte          │
│  - calcule distance(médiane)  │   │    synthétique ancré         │
│  - décide : intervenir ? oui  │   │  - retourne le "souvenir"    │
│    → direction d'amplification│   │                               │
└───────────────────────────────┘   └──────────────────────────────┘
            │                                      ▲
            └───── si décision "oui" ──────────────┘
```

**Bénéfices attendus** :

- **Auditabilité** : un log Python montre exactement pourquoi et quand le psy a poussé. Pas besoin de deviner.
- **Coût** : pas d'appel LLM si pas de décision à prendre.
- **Performance** : la décision prend des millisecondes (calcul vectoriel), l'appel LLM ne se déclenche qu'en cas d'intervention réelle.

**Point à creuser** : le scoring DISC du comportement courant reste probablement un appel LLM (analyse sémantique de `inner`/`expected`). On peut chercher à mettre en cache par exchange, ou à passer par un classifieur plus léger.

## Scénario pilote — Antoine / Manon / Élise

Scénario canon pour valider H5.c le moment venu. Matériau **entièrement présent dans les fiches existantes** — aucune adaptation à faire.

**Setup** :
- Antoine et Manon ont eu une aventure il y a 2 ans (`marking_events[0]` chez Antoine)
- Antoine marié à Élise depuis 8 ans
- Manon a probablement oublié (célibataire, pas d'impact)
- Antoine porte seul la `phobia` explicite : *« que la jaune entre dans la pièce et sourit comme elle souriait cette nuit-là »*

**Dynamique attendue** :
1. Scène où les 3 se croisent → stress d'Antoine monte
2. Son adapté Vert/Bleu verrouille → score DISC dérive vers sur-adaptation extrême
3. Le psy détecte → short-circuit des `recall(about="manon")` pour remonter la phobia amplifiée
4. Le réel de Antoine commence à déborder dans le PUBLIC (sec, distant, transpire)
5. Deux issues ouvertes, pas imposées : avouer à Élise, ou crever l'abcès avec Manon. S'il ne fait rien → amplification montante tour après tour, jusqu'à craquage involontaire (`flaws.auto-saboteur`)

Ce scénario **n'est pas scripté** — il est **émergent** à partir des fiches + la mécanique du psy. C'est la preuve que le design tient.

## Points ouverts

À affiner au moment d'implémenter H5.c :

- **Pondération de la médiane** : 50/50 ou pondérée vers le réel (ex: 30/70) ? Levier de difficulté narrative — plus on penche vers le réel, plus le psy pousse souvent.
- **Seuil adaptatif** : proportionnel au gap pour éviter de harceler les `gap: significatif` (Antoine) tout en conservant le fait que les `gap: faible` n'ont rien à subir (Manon a `gap: zéro` → jamais d'intervention, c'est juste).
- **Qualité de la fenêtre** : pondérer les tours récents plus fortement que les anciens ? Exponential decay ? À bench quand on aura des données live.
- **Choix du coeff AT** quand plusieurs états sont renseignés (`dominant` + `child` + `parent` + `adult`) — moyenne pondérée ou juste `dominant` ?
- **Cache de scoring DISC** par exchange pour éviter la ré-analyse à chaque tour.
- **Gestion des conflits** si plusieurs persos déclenchent simultanément leur intervention psy — file d'attente ou parallèle ?

## Dépendances bloquantes

Conceptuellement c'est bouclé. Techniquement, il faut :

- **#11** `@cascade` + `ShortCircuit` (COLD)
- **#12** `Bus.dispatch` refactor avec pipeline `before → call → after` (COLD)
- **H5.a** agent `psy` — fiche + fine-tune `simphonia_psy` (prospective Ollama)

Tant que les cascades dorment en COLD, le psy reste une élégante étude. Le jour où elles sont dégelées, ce document devient implémentable presque tel quel.

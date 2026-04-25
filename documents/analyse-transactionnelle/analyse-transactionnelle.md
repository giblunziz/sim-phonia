# Analyse Transactionnelle — application à Simphonia

**Statut** : étude exploratoire, non implémenté. Issu d'un brainstorm 2026-04-25.

Ce document synthétise les concepts de l'Analyse Transactionnelle (AT) pertinents pour Simphonia et décrit l'agent d'analyse transactionnelle envisagé pour observer et classifier les interactions entre personnages en temps réel.

---

## Fondements théoriques

### Origine

L'Analyse Transactionnelle a été créée dans les années 60 par le médecin psychiatre et psychanalyste **Éric Berne**. C'est à la fois une théorie de la personnalité, une théorie de la communication, et une théorie du développement de l'enfant.

Berne définit l'AT comme une « théorie de la personnalité et de l'action sociale ainsi qu'une méthode clinique de psychothérapie fondée sur l'analyse de toutes les transactions possibles entre deux personnes ou plus, sur la base des états du moi définis spécifiquement. »

L'AT sert à **opérer des changements de vie** — exactement ce que Simphonia cherche à faire émerger chez ses personnages.

### Constat dynamique vs état stable

L'AT couvre **deux niveaux de réalité psychique** souvent confondus, et il faut les tenir séparés pour ne pas mélanger les choses au moment d'implémenter Tobias :

- **La transaction est un constat dynamique** — un échange P-A-E entre deux personnes, observable et fluctuant tour après tour. C'est ce qu'analyse le présent document à travers ses tableaux de transactions parallèles / croisées / cachées. Cette dimension est l'origine historique du nom *« Analyse Transactionnelle »* (Berne, *Transactional Analysis in Psychotherapy*, 1961).

- **Le scénario est un état stable** — une architecture interne au sujet, construite dans l'enfance et qui persiste. Il contient les états du moi structuraux, les drivers de Kahler, les positions de vie, le sentiment racket par défaut, et la *boîte de timbres* (cf. plus bas). Ces structures ne changent pas en cours de partie ; elles déterminent **comment** le sujet va générer ses transactions et **comment** il va y réagir.

> **Conséquence pour Simphonia** : la **transaction** (constat) se mesure à chaque tour par l'**agent AT observateur** — c'est un signal volatile. Le **scénario** (état) est inscrit dans la **fiche** du personnage et matérialisé par la **boîte de timbres** que Tobias accumule au fil de l'activité. Les deux dimensions nourrissent les décisions de Tobias mais via des canaux différents et à des fréquences différentes.

### Les 3 états du moi

Notre psychisme se compose de trois états du moi qui contiennent tout ce que nous pensons, ressentons, croyons et voulons — toutes nos expériences présentes et passées.

Berne les définit comme « un ensemble cohérent de pensées et de ressentis, manifesté par des comportements correspondants ».

#### Modèle structural (ce qui est DANS le personnage)

Le modèle structural permet de comprendre la construction des structures psychiques : comportements (Agir), pensées (Penser) et sentiments (Ressentir).

| État | Description | Correspondance Simphonia |
|---|---|---|
| **Parent (P)** | Empreintes des personnes qui nous ont élevés ou influencés. Règles sociales, normes, jugements de valeur. *« Je me comporte comme mes parents le faisaient. »* | `psychology.transactional.parent` dans la fiche |
| **Adulte (A)** | Basé sur le présent, l'ici et maintenant. Traite l'information de manière objective, indépendamment du vécu. *« Je réagis à la réalité telle qu'elle est. »* | `psychology.transactional.adult` dans la fiche |
| **Enfant (E)** | Traces de nos ressentis, raisonnements et réactions antérieurs. Siège des besoins, désirs, sentiments, pulsions. *« Je me comporte comme quand j'étais enfant. »* | `psychology.transactional.child` dans la fiche |

**Application Simphonia** : le modèle structural est la **fiche** du personnage. C'est ce qui est construit, ce qui ne change pas en cours de partie. Tobias le lit pour comprendre le personnage.

#### Modèle fonctionnel (ce qui se VOIT dans les interactions)

Le modèle fonctionnel donne les clés de compréhension de l'être humain **en relation avec les autres**. C'est l'aspect observable — le « comment » des comportements et des échanges.

Les 3 fonctions se décomposent en **6 états du moi fonctionnels** :

| État fonctionnel | Comportement positif | Comportement négatif | Exemples Simphonia |
|---|---|---|---|
| **Parent Normatif (PN)** | Pose les limites, le cadre protecteur. Dicte les règles. | Autoritaire, moralisateur, dévalorise. | Élise qui contrôle Antoine. Marc qui impose sa vision. |
| **Parent Nourricier (PNr)** | Protège, encourage, soutient. Écoute avec bienveillance. | Surprotège, étouffe, rend dépendant. | Aurore l'hôtesse qui prend soin de tous. |
| **Adulte (A)** | Rationnel, logique, neutre. Observe et enregistre les faits. | Froid, distant, déconnecté des émotions. | Antoine en mode « contrôle de gestion ». |
| **Enfant Libre (EL)** | Spontané, naturel, authentique. Exprime ses sentiments librement. | Sauvage, égocentrique, sans filtre. | Manon qui dit ce qu'elle pense. Prisca qui vit l'instant. |
| **Enfant Adapté (EA)** | S'adapte aux règles, coopère, cherche à bien faire. | Soumis, inhibé, perd sa spontanéité. | Camille qui cherche à se faire oublier. Antoine sous pression. |
| **Enfant Rebelle (ER)** | S'oppose pour affirmer son identité, résiste à l'injustice. | Provocateur, opposant systématique. | Marc qui refuse le jeu d'Isabelle. Théo qui provoque. |

**Application Simphonia** : le modèle fonctionnel est ce que l'agent AT observe dans les **exchanges**. Le `talk` et les `actions` révèlent l'état fonctionnel social, le `inner` et l'`expected` révèlent l'état fonctionnel psychologique.

---

## Les 3 types de transactions

Une **transaction** est un échange de signes de reconnaissance (un stimulus et une réponse) provenant d'un état du moi d'un interlocuteur et atteignant un état du moi de l'autre.

Éric Berne a défini trois lois de la communication, chacune associée à un type de transaction.

### Transactions parallèles (complémentaires)

**1ère loi** : les échanges se déroulent sans problème. Les états du moi visés sont bien ceux touchés et ceux qui répondent. Ces transactions peuvent se poursuivre à l'infini.

```
Exemple dans Simphonia :

Julien (A→A) : "Tu as vu le coucher de soleil ?"
Aurore (A→A) : "Magnifique. On ne voit pas ça depuis Paris."

→ Transaction parallèle Adulte ↔ Adulte
→ Tension : 0 — tout va bien
→ La conversation peut continuer indéfiniment
```

Les transactions parallèles ne sont pas forcément Adulte ↔ Adulte. Elles sont possibles dans tous les états :

```
Parent ↔ Parent :
  Marc : "Ah les jeunes aujourd'hui..."
  Diane : "Ne m'en parlez pas..."
  → Complicité normative, zéro tension

Enfant ↔ Enfant :
  Prisca : "Oh mon dieu, regarde cette robe !"
  Zoé : "Trop belle ! Je la veux !"
  → Complicité enfantine, zéro tension
```

### Transactions croisées

**2ème loi** : la réponse au stimulus n'arrive pas depuis l'état du moi attendu. La communication est **bloquée** tant que l'un des deux ne change pas d'état du moi.

```
Exemple dans Simphonia :

Isabelle (A→A) : "Le silence est un luxe, ne trouvez-vous pas ?"
Marc (PN→EA) : "Parlons de choses concrètes. On n'est pas là pour faire de la littérature."

→ Isabelle attendait une réponse Adulte
→ Marc répond en Parent Normatif vers son Enfant Adapté
→ CROISEMENT — tension immédiate
→ L'un des deux doit changer d'état pour que ça reprenne
```

```
Autre exemple :

Antoine (A→A) : "Tu te souviens d'Élise ?"
Manon (EL→A) : "Haha, bien sûr ! On a passé une soirée de dingue !"

→ Antoine attendait une réponse Adulte mesurée
→ Manon répond en Enfant Libre — spontanée, sans filtre
→ CROISEMENT — la spontanéité de Manon menace le contrôle d'Antoine
→ Antoine doit s'adapter ou la conversation déraille
```

### Transactions cachées (à double fond)

**3ème loi** : le plus important dans une transaction c'est le **niveau sous-jacent**, pas le niveau apparent. On répond au message psychologique (caché), pas au message social.

C'est **LA mécanique fondamentale du NRShow**. La séparation PUBLIC / PRIVATE des exchanges EST la transaction cachée de Berne :

```
Exemple dans Simphonia — Antoine parle à Manon :

NIVEAU SOCIAL (PUBLIC — talk) :
  Antoine (A→A) : "Ça va bien, merci. Et toi ?"
  → Transaction Adulte ↔ Adulte, tout semble normal

NIVEAU PSYCHOLOGIQUE (PRIVATE — inner) :
  Antoine (EA→PN) : "Mon visage. Surveiller mon visage quand elle sourit comme ça."
  → Transaction Enfant Adapté → Parent Normatif intérieur
  → La peur, le contrôle, la soumission au secret

RÉALITÉ :
  Le message social dit "tout va bien"
  Le message psychologique dit "je suis terrorisé"
  → C'est le message psychologique qui détermine le comportement réel
  → C'est ce que Tobias observe et exploite
```

### Mapping direct avec les exchanges Simphonia

| Champ exchange | Niveau AT | Visibilité |
|---|---|---|
| `talk` | Message social (explicite) | PUBLIC |
| `actions` | Comportement observable | PUBLIC |
| `body` | Signaux non-verbaux (peuvent trahir le psychologique) | PUBLIC |
| `mood` | État émotionnel apparent | PUBLIC |
| `inner` | Message psychologique (implicite) | PRIVATE — MJ + Tobias |
| `expected` | Anticipation / crainte psychologique | PRIVATE — MJ + Tobias |
| `noticed` | Perception sélective (biais attentionnel) | PRIVATE — MJ + Tobias |
| `memory` | Ce que le personnage retient (biais de disponibilité) | PRIVATE — MJ + Tobias |

---

## Concepts AT avancés pertinents pour Simphonia

### Signes de reconnaissance (Strokes)

Un signe de reconnaissance est tout acte impliquant la reconnaissance de la présence d'autrui. Cinq modalités : Donner, Recevoir, Demander, Refuser, Se donner à soi-même.

| Personnage | Pattern de reconnaissance | Conséquence |
|---|---|---|
| Prisca | **Demande** en permanence (likes, compliments, regards) | Vulnérable quand les signes ne viennent pas |
| Vera | **Refuse** d'en donner facilement | Perçue comme froide ou distante |
| Camille | Ne sait pas **recevoir** (rejette les compliments) | S'auto-sabote relationnellement |
| Manon | **Donne** spontanément sans calcul | Perçue comme solaire, attire naturellement |
| Antoine | **Se donne à lui-même** (auto-validation interne pour compenser) | Isolement derrière le masque |

### Triangle dramatique de Karpman

Trois rôles : **Persécuteur**, **Sauveur**, **Victime**. Les personnages changent de rôle dynamiquement.

| Rôle | Personnage(s) | Contexte |
|---|---|---|
| Victime | Antoine (de son propre secret) | Il subit la situation qu'il a créée |
| Persécuteur potentiel | Élise (si elle découvre) | La trahison la transformerait |
| Sauveur potentiel | Aurore (elle écoute, elle comprend) | Mais un Sauveur peut basculer en Persécuteur |
| Victime potentielle | Manon (si le secret éclate) | Accusée à tort d'avoir provoqué |

Le triangle est **dynamique** — les rôles tournent. Antoine passe de Victime à Persécuteur quand il manipule la vérité. Élise passe de Persécuteur à Victime quand elle découvre qu'elle a été trompée.

### Mini-scénarios de Kahler (Drivers)

Cinq injonctions inconscientes qui pilotent le comportement sous stress :

| Driver | Description | Personnage(s) |
|---|---|---|
| **Sois parfait** | Rien n'est jamais assez bien | Antoine (le masque parfait), Vera (l'exigence esthétique) |
| **Sois fort** | Ne montre pas tes émotions | Marc (le roc), Antoine (sous pression) |
| **Fais plaisir** | Passe les autres avant toi | Camille (s'efface pour les autres), Aurore (l'hôtesse parfaite) |
| **Fais effort** | Ce qui compte c'est d'essayer | Julien (toujours en mouvement, jamais satisfait) |
| **Dépêche-toi** | Pas le temps de réfléchir | Prisca (vit à 100 à l'heure), Manon (réagit à l'instant) |

### Positions de vie (OK+ / OK-)

Quatre positions existentielles fondamentales :

| Position | Signification | Personnage(s) |
|---|---|---|
| **OK+ / OK+** | Je suis bien, tu es bien | Manon, Aurore (en surface) |
| **OK+ / OK-** | Je suis bien, tu ne l'es pas | Élise (contrôle), Vera (jugement subtil) |
| **OK- / OK+** | Je ne suis pas bien, tu l'es | Camille (dévalorisation), Antoine sous pression |
| **OK- / OK-** | Personne n'est bien | Antoine en craquage complet |

### Contaminations et exclusions

- **Contamination** : un état du moi envahit un autre. Camille dont le Parent Critique contamine l'Adulte → elle croit objectivement qu'elle est nulle (ce n'est pas un sentiment, c'est une « certitude »).
- **Exclusion** : un état du moi est verrouillé. Antoine qui exclut son Enfant Libre → jamais spontané, jamais authentique, toujours en contrôle.

La bascule adapté → réel de Tobias est une **décontamination** forcée. Le psy pousse le personnage à distinguer ce qu'il croit de ce qu'il ressent vraiment.

### Collection de timbres

> **Terminologie** : *timbres* (français), *trading stamps* (Berne, *Des jeux et des hommes*, 1964) — référence aux timbres-cadeaux des supermarchés US des années 60, qu'on collait dans un livret jusqu'à pouvoir l'échanger contre un grille-pain. La métaphore est précise et toujours en usage en clinique. Le moment de l'échange s'appelle le *payoff* — l'encaissement du livret.

Accumuler des rancœurs, des frustrations, des micro-blessures silencieusement, jusqu'à la décharge. Chaque « timbre » est un petit grief non exprimé qui s'empile dans le livret intérieur.

#### Le timbre comme sentiment substitutif (sentiment racket)

Un timbre n'est pas qu'un grief objectif accumulé — c'est un **sentiment substitutif** appris dans l'enfance, qui remplace un sentiment authentique non autorisé. L'éducation du perso a câblé un *sentiment racket* par défaut, et c'est ce sentiment-là qu'on accumule, pas le sentiment authentique :

- Un enfant à qui on a interdit la colère → ses timbres sont des timbres de **tristesse**. Sa boîte pleine se décharge en effondrement, dépression, somatisation — pas en explosion.
- Un enfant à qui on a interdit la tristesse → ses timbres sont des timbres de **rage**. Décharge en explosion, destruction, claquage de portes.
- Un enfant à qui on a interdit la peur → des timbres de **honte** ou de **culpabilité**. Décharge en auto-flagellation, retrait, départ brutal, confession précipitée.

Le sentiment racket est **prévisible** par lecture de la fiche (`background.parents`, `background.education`, `marking_events`, `psychology.transactional`). Antoine n'accumule pas de la peur d'être démasqué — il accumule de la **culpabilité** (sentiment racket câblé : *« je dois être quelqu'un de bien »*). Sa boîte pleine ne pète pas en rage : elle pète en auto-sabotage, confession précipitée, ou repli sec.

#### Game vs boîte de timbres

Distinction fondamentale qui mérite d'être posée pour ne pas confondre génération et stockage :

- Le **jeu psychologique** (*game* — Berne) est la **séquence relationnelle répétitive** qui produit le timbre. Karpman l'illustre avec son triangle Persécuteur/Sauveur/Victime — c'est le mécanisme de génération.
- La **boîte de timbres** est le **réservoir** où le timbre s'empile. Elle ne génère rien, elle stocke jusqu'à saturation.

Le game se mesure à l'échelle de la **transaction** (par l'agent AT). La boîte se mesure à l'échelle de **l'historique** (par Tobias, via le signal `pressure` — cf. cognition.md).

#### Formes du payoff (encaissement du livret)

Quand la boîte est pleine, le sujet **encaisse son livret** — il dépense ses timbres en payoff cohérent avec son scénario. Plusieurs formes possibles, dictées par le sentiment racket :

- **Explosion bruyante** — envoyer tout le monde se faire voir, casser, hurler. Décharge externalisée immédiate. *(timbres de rage)*
- **Effondrement silencieux** — dépression, mutisme, somatisation, fuite aux toilettes. Décharge intériorisée. *(timbres de tristesse)*
- **Départ brutal** — claquer la porte, démissionner, divorcer du jour au lendemain. Décharge par fuite. *(timbres de honte / lassitude)*
- **Auto-destruction** — rechute, accident, comportement à risque, confession suicidaire au mauvais moment. Décharge par sacrifice. *(timbres de culpabilité)*
- **Scandale justifié** — provoquer un esclandre socialement défendable (« j'avais le droit, après tout ce que j'ai enduré »). Décharge par mise en scène. *(timbres de victimisation)*

La forme du payoff n'est pas un choix au moment de l'explosion — elle est inscrite dans le scénario depuis longtemps. C'est prévisible si on a lu la fiche.

#### Application Simphonia

C'est exactement la **3ème métrique de Tobias** — le signal `pressure` formalisé dans [cognition.md](../cognition.md#trois-signaux-pour-tobias--agrégation). Le `recall_count` accumule, les `marking_events` valencés alimentent, `phobia` et `secret` pondèrent contextuellement. Quand `pressure` atteint son seuil, Tobias amplifie en **orientant la décharge selon le sentiment racket** du perso, pas selon une forme générique. Antoine ne crie pas, il s'effondre dans la honte ; Marc ne pleure pas, il hurle.

---

## Agent d'Analyse Transactionnelle — design pour Simphonia

### Principe

Un agent **observateur** distinct de Tobias. Il ne biaise rien, il ne manipule rien — il **classifie** chaque échange entre deux personnages selon le modèle PAE et détecte le type de transaction (parallèle, croisée, cachée).

Tobias consomme les résultats de l'agent AT pour prendre ses décisions d'intervention.

### Séparation des responsabilités

```
Agent AT (observateur)                    Tobias (interventionniste)
─────────────────────                     ────────────────────────
Classifie chaque échange en PAE           Lit les classifications de l'agent AT
Détecte parallèle / croisée / cachée     Décide d'intervenir ou non
Calcule la tension par paire              Biaise le recall si nécessaire
Stocke dans psy_collection                Produit le texte amplifié

Déterministe — du tagging                 Stratégique — de la décision
Modèle léger (Gemma 4B suffisant)         Modèle lourd (Gemma 26B)
Tourne à chaque tour                      Tourne seulement au recall
```

### Classification d'un exchange

Pour chaque exchange, l'agent AT produit :

```json
{
  "round": 1,
  "turn": 2,
  "speaker": "marc",
  "target": "isabelle",
  "social": {
    "speaker_state": "A",
    "target_state": "A",
    "direction": "A→A"
  },
  "psychological": {
    "speaker_state": "PN",
    "target_state": "EA",
    "direction": "PN→EA"
  },
  "transaction_type": "cachée",
  "tension": 0.7,
  "notes": "Message social Adulte stable mais inner révèle un Parent Normatif jugeant — transaction à double fond"
}
```

**Sources de la classification** :
- `talk` + `actions` + `mood` → état du moi **social** (ce qui se voit)
- `inner` + `expected` → état du moi **psychologique** (ce qui se cache)
- Écart entre les deux → type de transaction (parallèle si alignés, cachée si divergents)

### Graphe transactionnel par paire et par activité

L'agent AT accumule les classifications tour après tour et produit un graphe d'évolution :

```json
{
  "activity_run": "action_verite_260419_1021",
  "pair": ["isabelle", "marc"],
  "transactions": [
    {
      "round": 1, "turn": 1,
      "speaker": "isabelle", "target": "marc",
      "social": {"from": "A", "to": "A"},
      "psycho": {"from": "EL", "to": "?"},
      "type": "cachée",
      "tension": 0.3
    },
    {
      "round": 1, "turn": 2,
      "speaker": "marc", "target": "isabelle",
      "social": {"from": "A", "to": "A"},
      "psycho": {"from": "PN", "to": "EA"},
      "type": "croisée",
      "tension": 0.7
    }
  ],
  "evolution": {
    "social_stability": "parallèle constante (A↔A)",
    "psycho_drift": "croisement croissant (PN↔EL)",
    "tension_curve": [0.3, 0.7, 0.8, 0.9],
    "prediction": "rupture imminente — l'un va sortir du social A↔A"
  }
}
```

### Courbe de tension

La tension évolue selon le type de transaction :

```
Parallèle     → tension stable ou en baisse
Croisée       → tension en hausse immédiate
Cachée        → tension en hausse progressive (accumulation silencieuse)

Seuils :
  0.0 - 0.3   → échange fluide, pas d'intervention
  0.3 - 0.6   → tension montante, Tobias observe
  0.6 - 0.8   → friction relationnelle, Tobias prêt à intervenir
  0.8 - 1.0   → rupture imminente, Tobias amplifie pour accélérer la bascule
```

### Consommation par Tobias

Tobias ne calcule pas les transactions — l'agent AT le fait. Tobias **consomme** les résultats :

```
Tobias reçoit un recall(from="antoine", about="manon")
  → consulte psy_collection : agent AT
  → lit : tension isabelle↔marc = 0.9, transaction cachée depuis 3 tours
  → lit : antoine tension globale = 0.8 (somme pondérée de toutes ses paires)
  → décide : intervention lourde, amplification phobia
```

### Visualisation frontend — dashboard MJ

Perspective pour le dashboard MJ : un **diagramme de transactions** en temps réel.

```
┌─ Transactions en cours ──────────────────────────────────────┐
│                                                                │
│  Isabelle ──A→A──▶ Marc         (social : parallèle ✅)       │
│  Isabelle ──EL→?──▶ Marc        (psycho : cachée ⚠️)         │
│                                                                │
│  Tension : ████████░░ 0.8       (en hausse ↑)                 │
│                                                                │
│  Historique :                                                  │
│  T1: 0.3 ░░░░░░░░░░                                           │
│  T2: 0.7 ██████░░░░                                           │
│  T3: 0.8 ████████░░              ← prédiction : rupture       │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

Le game designer qui voit les flèches PAE, les croisements en rouge, la courbe de tension qui monte. Il sait quand intervenir avec un whisper pour accélérer ou calmer le jeu.

---

## Liens avec les mécaniques existantes de Simphonia

| Concept AT | Implémentation Simphonia | Document de référence |
|---|---|---|
| États du moi (structural) | `psychology.transactional` dans la fiche | `cognition.md` — coeff transactionnel |
| États du moi (fonctionnel) | Observé dans les exchanges par l'agent AT | Ce document |
| Transactions cachées | Séparation PUBLIC / PRIVATE des exchanges | `activity_context_builder.md` |
| Triangle de Karpman | Dynamique relationnelle émergente | À formaliser |
| Drivers de Kahler | Comportement sous stress | `cognition.md` — bascule adapté → réel |
| Collection de timbres | `recall_count` + `emotional_charge` dans les meta | `cognition.md` — biais de disponibilité |
| Contamination / Exclusion | Détection par Tobias (écart structural / fonctionnel) | `cognition.md` — intervention du psy |
| Positions de vie (OK+/OK-) | Déductible des `inner` + `expected` | À formaliser |
| Signes de reconnaissance | Pattern relationnel dans les cross-analyses | `shadow_storage.md` — capture passive |

---

## Points ouverts

- **Modèle de classification** : LLM (Gemma 4B) ou classifieur léger (fine-tuné sur des exemples de transactions PAE) ?
- **Granularité** : classifier chaque tour ou agréger par round ?
- **Stockage** : dans `psy_collection` (partagé avec Tobias) ou collection dédiée `at_analysis` ?
- **Coût** : un appel LLM par exchange pour classifier → à évaluer en volume sur une activité complète.
- **Drivers de Kahler** : les intégrer dans la fiche du personnage ou les laisser émerger de l'analyse ?
- **Triangle de Karpman** : détection automatique des rôles Persécuteur/Sauveur/Victime — faisable par pattern matching sur les transactions croisées ?
- **Formation du modèle** : créer un dataset d'exemples PAE à partir des exchanges existants de Simphonia pour fine-tuner un classifieur ?

---

## Références

- **Éric Berne** — *Que dites-vous après avoir dit bonjour ?* (ouvrage fondateur)
- **Éric Berne** — *Des jeux et des hommes* (jeux psychologiques, Triangle de Karpman)
- **Taibi Kahler** — Mini-scénarios et drivers (Sois parfait, Sois fort, Fais plaisir, Fais effort, Dépêche-toi)
- **Stephen Karpman** — Triangle dramatique
- **Estelle Divet / Tafoga** — [Analyse Transactionnelle : États du moi et Transactions](https://tafoga.com/blog/analyse-transactionnelle-etats-du-moi-transactions)
- **Claude Steiner** — Scénarios de vie et économie des caresses

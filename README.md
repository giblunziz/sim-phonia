# sim-phonia

**simphonia** = *simulation* + *symphonia*. Plateforme de simulation narrative où des LLM incarnent des personnages et interagissent entre eux et avec un humain (*human-in-the-loop*) sous l'orchestration d'un Maître du Jeu (MJ).

## 1. Concept

Métaphore musicale : une symphonie nécessite un **orchestre**, des **musiciens**, des **spectateurs** et un **chef d'orchestre**.

- **Musicien = un LLM incarnant un personnage** — pas un assistant, un rôle complet avec fiche, psychologie, phobies, secrets.
- **Chef d'orchestre = MJ** : orchestre les tours, cadre les scènes, arbitre.
- **Human-in-the-loop** : l'humain peut être MJ, ou lui-même joueur, ou spectateur.

**Finalité** : jeu de rôle narratif où le carburant dramatique vient des **écarts** entre ce que les personnages savent, ce qu'ils révèlent, et ce que les autres en perçoivent.

## 2. Règles de jeu (contrat narratif)

Validées lors d'un POC manuel (8 instances Opus sur Claude.ai, MJ humain relayant les messages à la main, fichier de règles dans le vault du projet).

### 2.1 Fiches de personnage

Chaque joueur possède une fiche — **contrat d'identité** — contenant identité, apparence, background, défauts (`flaws[]`), psychologie (Analyse Transactionnelle, insight colorimétrique avec écart `adapted`/`real`/`gap`), relations, éléments jouables (`phobia`, `secret`, `prior_knowledge[]`), et une **capacité mémoire finie** (`memory.slots: 8`).

→ **Isolation stricte** : un joueur ne connaît QUE sa propre fiche. Les autres lui sont opaques.

### 2.2 Round 1 — présentation

- **Obligation** : s'inspirer de sa fiche
- **Liberté** : dire ce qu'on veut
- **Interdit** : inventer (tout doit être ancré dans la fiche)
- **Interdit** : mentir
- **Autorisé** : omettre — libre arbitre sur ce qu'on révèle

→ *Honnêteté factuelle obligatoire, divulgation discrétionnaire*. Les non-dits sont la matière première.

### 2.3 Cross-knowledge (perception croisée)

Après chaque interaction, chaque joueur consigne ce qu'il perçoit des autres. Stockage **timeline append-only** d'entrées atomiques taguées par catégorie :

| Catégorie | Rôle |
|---|---|
| `perceived_traits` | Traits factuels observés |
| `assumptions` | Hypothèses internes sur les motivations de l'autre |
| `approach` | Stratégie comportementale à adopter envers l'autre |
| `watchouts` | Points de vigilance, signaux à surveiller |

Une entrée peut être `about: "self"` → auto-perception (alimentée au debrief d'activité).

**Cross-knowledge ≠ fiche réelle** → l'écart perception/vérité est le moteur dramatique.

## 3. Modèle de données

Stockage : **MongoDB** (source de vérité) + **ChromaDB** (index vectoriel / RAG sémantique).

### 3.1 Collections

| Collection | Rôle | Exemple réel |
|---|---|---|
| `characters` | Fiches de personnage | `.working/antoine.json` |
| `perceptions` | Cross-knowledge (append-only) | `.working/antoine_manon_cross.json` |
| `activities` | Journaux d'activité | `.working/insight_20260410_2338.json` |

### 3.2 Activité — entité pivot

Une activité = une unité de game-flow persistée en un document :

- **`_id`** : `<type>:YYYYMMDD:HHMM` (ex. `insight:20260410:2338`)
- **`type`** : nature de l'activité (ex. `insight`)
- **`scene`** : ancrage contextuel (ex. `yacht_salon`)
- **`participants[]`** : codes des joueurs
- **`model`**, **`provider`** : LLM utilisé (ex. `gemma4:e4b` / `ollama`)
- **`events[]`** : stimuli (affirmations, situations) injectés à chaque round
- **`mj[]`** : journal d'actions du MJ — verbes `give_turn(target, instruction)`, `next_round(instruction)`, `end_activity`
- **`exchanges[]`** : réponses des joueurs round par round
- **`debrief[]`** : méta-réflexion post-activité + mises à jour de cross-knowledge
- **`stats`** : `calls`, `prompt_tokens`, `output_tokens`, `duration_ms`, `cache_*`, `recaps`

### 3.3 Schéma d'une réponse de joueur (`exchange.response`)

Output LLM **structuré** (structured output / function-calling). Frontière public/privé à respecter absolument :

| Champ | Visibilité | Rôle |
|---|---|---|
| `talk[]` | 🔓 **public** | Paroles prononcées |
| `actions[]` | 🔓 **public** | Gestes / postures visibles |
| `body` | 🔓 **public** | Langage corporel courant |
| `mood` | 🔓 **public (observable)** | Humeur apparente |
| `inner` | 🔒 **privé** | Monologue intérieur |
| `expected` | 🔒 **privé** | Résultat espéré |
| `noticed[]` | 🔒 **privé** | Observations sur les autres |
| `memory[]` | 🔒 **privé** | Nouveaux souvenirs à consigner |

→ La cross-knowledge des autres ne peut s'appuyer **QUE** sur les champs publics.

## 4. Architecture

### 4.1 Principe cardinal — simphonia = agent MCP unique

Pas d'agents MCP disséminés. **`simphonia` est le seul point MCP** exposé aux LLM joueurs. Il reçoit les requêtes et les route vers des services internes, potentiellement en chaîne :

```
LLM ── MCP tool call ──▶ simphonia ──▶ memory_service ──▶ shadow_memory_service ──▶ response
```

Cette centralisation garantit : un seul contrat externe, autorisation unifiée, observabilité consolidée, pas de prolifération d'agents.

### 4.2 Modules

| Module | Rôle |
|---|---|
| **`simphonia`** | Serveur : bus multi-commandes, persistence (MongoDB), RAG (ChromaDB), façade MCP, orchestration MJ, runtime joueur |
| **`simcli`** | CLI d'administration (HTTP) : lister bus/commandes, dispatcher pour debug |

### 4.3 Event-bus multi-bus

Système pub/sub simple. Un bus = un namespace de commandes. Enregistrement au démarrage via `@command(bus=..., code=..., description=...)`, auto-découverte par `pkgutil.walk_packages` sur `simphonia.commands.*`.

| Bus | Rôle | État |
|---|---|---|
| `system` | Commandes de base (`help`, `ping`) | ✅ implémenté |
| `mj` | Game-flow (`give_turn`, `next_round`, `end_activity`) | 🔴 à faire |
| `memory` | Exposition du `memory_service` | 🔴 à faire |

### 4.4 Services internes

- **`memory_service`** : CRUD MongoDB + indexation ChromaDB. Source de vérité pour `characters`, `perceptions`, `activities`. Expose `record(...)` et `query(from, about, context)`.
- **`shadow_memory_service`** : maillon post-`memory_service` dans la chaîne d'appel. **Rôle exact à spécifier** (cf. backlog).

### 4.5 Mémoire, RAG, et bascule v1 → v2

**v1 — actuelle (fonctionnelle mais sub-optimale)** :
- Le MJ formule la query RAG **au nom du joueur** → résultats injectés dans le prompt du joueur.
- Problème : le MJ pense à la place du joueur. Viole l'autonomie de l'agent.

**v2 — cible** :
- Exposition d'un **tool MCP** `memory.query(from, about, context)` directement au LLM joueur.
- Prompt système injecté : *« Si tu as besoin d'infos sur un autre joueur au-delà de ce que tu as acquis lors de la présentation, utilise le tool. »*
- Le LLM décide lui-même **quand** et **quoi** consulter → matche la cognition humaine (« attends, elle a dit quelque chose sur X tout à l'heure… »).

### 4.6 Implications de la bascule v2

1. **Boucle agentique côté joueur** : un tour = `prompt → tool_call* → final_response`. Budget d'itérations à borner.
2. **Autorisation via `from`** : le tool valide que `from == appelant réel` et filtre à ce que ce joueur peut légitimement connaître (ses propres perceptions + événements publics de sa scène).
3. **Contraintes provider** : tool-use requis. Ollama OK sur modèles récents (llama3.1, qwen2.5…), Claude/OpenAI natif.
4. **Observabilité narrative** : chaque tool_call trace *quand* et *pourquoi* un perso consulte sa mémoire. Un perso qui interroge 5 fois sur Manon dans un round = signal dramatique exploitable.
5. **Coût/latence** : +1 roundtrip LLM par tool_call. Acceptable local, à budgéter cloud.

### 4.7 Stack

- Python 3.11+
- FastAPI + pydantic v2 + uvicorn (HTTP REST, base MCP)
- httpx (client simcli)
- MongoDB + ChromaDB (à câbler)
- **Ollama** provider par défaut ; abstraction provider-agnostique prévue (Claude, OpenAI)

## 5. Arborescence

```
src/
├── simphonia/
│   ├── core/          # Bus, Command, BusRegistry, @command, discovery, errors
│   ├── commands/      # Commandes découvertes au démarrage (bus system, mj, memory…)
│   ├── http/          # Routes FastAPI, schémas pydantic, app factory
│   ├── bootstrap.py   # Wiring : registry → discovery → create_app
│   └── __main__.py    # uvicorn entrypoint
└── simcli/
    ├── client.py      # SimphoniaClient (wrapper httpx)
    ├── cli.py         # argparse + dispatch
    └── errors.py

documents/
├── architecture.md    # Cadre général
├── simphonia.md       # Spec serveur
└── simcli.md          # Spec CLI

.working/              # données réelles d'exemple (non committées si .gitignored)
├── antoine.json
├── antoine_manon_cross.json
└── insight_*.json
```

## 6. État actuel

- ✅ Squelette bus/commande, HTTP REST, bus `system` (`help`, `ping`)
- ✅ CLI `simcli` (list/dispatch HTTP)
- 🔴 Modèle de données, `memory_service`, bus `mj`, façade MCP, boucle agentique joueur → cf. `backlog.md` section **HOT**

## 7. Pointeurs

- `backlog.md` — priorités HOT / WARM / COLD / FROZEN / DONE. Mis à jour **uniquement** après validation utilisateur explicite.
- `CLAUDE.md` — conventions de collaboration (mode dev sénior, gestion dépendances, workflow backlog).
- `documents/*.md` — specs détaillées par module.
- `.working/*.json` — données réelles d'exemple (fiche perso, cross-knowledge, log d'activité complet).

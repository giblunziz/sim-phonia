# Etude du service chat_service

## Description

Le `chat_service` orchestre des échanges conversationnels **head-to-head** entre deux personnages. Chaque participant peut être incarné par un LLM (réponse générée en première personne) ou par l'humain (flag `human: bool`, message fourni tel quel). Le service ne gère ni la persistance long terme (mémoire), ni l'identité des personnages (déléguée au `character_service`).

Cycle de vie explicite : `start` (ouverture + premier message), `reply` (échange), `stop` (clôture). État volatile en mémoire, log fichier reset au boot.

## Cahier des charges

### Rôle

Bus unique : `chat`. Quatre commandes : `chat.start`, `chat.reply`, `chat.stop`, `chat.said`.

### `chat.start`

Ouvre une session de dialogue entre deux personnages.

**Payload**
```json
{
  "from_char": "marc",
  "to": "antoine",
  "say": "Salut, on peut parler ?",
  "human": false
}
```

- `from_char` (str, requis) — identifiant du personnage émetteur
- `to` (str, requis) — identifiant du personnage récepteur
- `say` (str, requis) — message initial
- `human` (bool, optionnel, défaut `false`) — si `true`, pas d'appel LLM pour `from_char` ; **non exposé en MCP**

**Retour**
```json
{
  "session_id": "chat_01H...",
  "from_char": "marc",
  "to": "antoine",
  "reply": "Bien sûr, qu'est-ce qui te tracasse ?"
}
```

### `chat.reply`

Poursuit une session existante.

**Payload**
```json
{
  "session_id": "chat_01H...",
  "from_char": "marc",
  "say": "J'ai vu quelque chose d'étrange hier.",
  "human": false
}
```

- `session_id` (str, requis)
- `from_char` (str, requis) — doit appartenir aux participants de la session
- `say` (str, requis)
- `human` (bool, optionnel, défaut `false`) — **non exposé en MCP**

**Retour** : `{"reply": "..."}`

### `chat.stop`

Termine la session, flush le log, libère l'état mémoire.

**Payload** : `{"session_id": "chat_01H..."}`

**Retour** : `{"session_id": "chat_01H...", "status": "closed"}`

### `chat.said`

Notification interne — dispatché automatiquement par le service après génération LLM quand `human=false`. Permet aux services externes de réagir via cascade. Déclenche également le tour autonome suivant (thread daemon).

**Payload** : `{"session_id": "...", "from_char": "antoine", "to": "manon", "content": "..."}`

**Retour** : `{"session_id": "...", "from_char": "...", "to": "...", "received": true}`

**Non exposé en MCP.**

### Sémantique du flag `human`

- `human=false` (défaut) → `say` est utilisé tel quel comme réplique de `from_char` ; après génération de la réponse LLM de `to`, `chat.said` est dispatché sur le bus → tour autonome enchaîné en arrière-plan (thread daemon) via `auto_reply`.
- `human=true` → `say` est utilisé tel quel ; la réponse LLM de `to` est retournée HTTP uniquement, rien n'est publié sur le bus (l'humain répondra manuellement via `chat.reply`).

Exemples :
- `{from_char:'mj', human:true, to:'antoine', say:'Salut'}` — l'utilisateur joue MJ, antoine répond via LLM
- `{from_char:'marc', human:true, to:'antoine', say:'Salut'}` — l'utilisateur joue marc, antoine sait qu'il reçoit un message de marc

Le concept spécial `'mj'` est **abandonné** : `'mj'` devient un `from_char` ordinaire, la distinction humain/LLM se fait uniquement via `human`.

### Construction du prompt LLM

Quand le service génère la réponse du personnage `to` :

1. Récupère la fiche de `to` via `character.get` (mise en cache dans la session au `start`)
2. Construit un prompt en **première personne** :
   - *system* : « Tu es {to.name}. {fiche synthétique}. Réponds en première personne, dans ta propre voix. Ne romps jamais le quatrième mur. »
   - *messages* : historique des tours (`from_char` → rôle `user` ; `to` → rôle `assistant`)
3. Appelle le provider référencé par `chat_service.model`

Quand `human=false`, `auto_reply(session_id, speaker)` génère d'abord la réplique du `speaker` (son propre system prompt, rôles inversés dans l'historique), puis la réponse de l'autre participant, puis dispatche `chat.said` pour continuer la boucle.

### État de session (runtime, volatile)

```python
@dataclass
class DialogueMessage:
    speaker: str
    content: str
    timestamp: datetime

@dataclass
class DialogueState:
    session_id: str
    participants: tuple[str, str]   # (from_char, to)
    history: list[DialogueMessage]
    provider_ref: str               # nom du provider résolu au start
    created_at: datetime
```

Registre : `Dict[str, DialogueState]` en mémoire. Jeté au `chat.stop`.

Pas de cache de fiche personnage dans le `chat_service` : le `character_service` est lui-même le cache (supporte un reset si la fiche est modifiée en cours de session). La stratégie de cache se tient au niveau du **provider**, jamais du **consumer**.

### Journalisation

- Logger `logger.chat` → `/logs/chat.log`
- Reset au démarrage (mode `'w'`)
- Format par tour : `{ts, session_id, from, to, say, reply, human, provider}`

### Configuration

#### Providers (racine de `simphonia.yaml`)

```yaml
providers:
  gemma4:
    protocol: ollama
    url: http://localhost:11434/api/chat
    model: gemma4:e4b
    max_tokens: 2048
    temperature: 0.6
    keep_alive: 5m
  opus:
    protocol: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-opus-4-6
    max_tokens: 4096
    temperature: 0.8
    keep_alive: 5m
```

Clés communes : `protocol` (requis), `model` (requis), `max_tokens`, `temperature`, `keep_alive`.
Clés spécifiques : `url` (ollama) ; clé API via dotenv (anthropic, cf. `configuration_service`).

Implémentations portées depuis `X:\Symphonie\src\symphonie\providers`.

#### Section `chat_service`

```yaml
chat_service:
  model: "gemma4"         # référence à providers.gemma4 — pas un ID modèle brut (gemma4 par défaut en dev)
  log:
    path: "./logs/chat.log"
    reset_on_startup: true
```

Le service résout la référence au boot. Si le provider n'existe pas → fail-fast.

### Façade MCP

`chat.start`, `chat.reply`, `chat.stop` exposées en MCP, **sans** le paramètre `human`. `chat.said` non exposé (notification interne).

### Dépendances inter-services

- **`character_service`** (requis) : résolution d'identité et fiche personnage (appelé à chaque tour, pas de cache local — cf. principe de cache provider-side)
- **`configuration_service`** (requis) : seul point d'entrée autorisé pour lire la configuration ; les services n'accèdent **jamais** directement au fichier YAML ni aux variables d'environnement
- **`memory_service`** : hors scope MVP ; intégration future possible via cascade post-`reply`

### Cas d'erreur

- `session_id` inconnu sur `reply`/`stop` → `session_not_found`
- `from_char` n'appartenant pas à la session sur `reply` → `invalid_participant`
- Provider introuvable au boot → fail-fast (démarrage bloqué)
- Appel LLM en échec → erreur `llm_error` remontée au caller, session préservée

### Non-objectifs MVP

- Chat multi-party (>2 participants)
- Reprise de session après `stop`
- Écriture automatique en mémoire long terme
- Streaming de tokens
- `to='all'` (broadcast)

## Décisions de conception

| Num | Question | Décision retenue | Raison |
|-----|----------|------------------|--------|
| Q1 | Canal | Bus unique `chat`, 3 commandes | Cohérence avec l'archi simphonia |
| Q2 | Participants | Head-to-head uniquement | MVP ; extension multi-party reportée (YAGNI) |
| Q3 | Synchronisme | Synchrone tour par tour | Cas d'usage CLI/MCP |
| Q4 | Persistance | Volatile + log fichier reset au boot | YAGNI |
| Q5 | Fiche personnage | Appelé via `character_service` à chaque tour, pas de cache local | Le cache est provider-side (`character_service`) ; le consumer ne duplique pas |
| Q6 | memory_service | Hors scope MVP | Séparation de responsabilités ; intégration future via cascade |
| Q7 | Incarnation LLM | Première personne — le LLM EST le personnage | Cohérence narrative |
| Q8 | Joueur humain | Flag `human: bool` dans le payload, remplace `'mj'` spécial | Généralise : n'importe quel personnage peut être joué par l'humain |
| Q9 | `chat stop` | Jette l'état, log fil-de-l'eau suffit | YAGNI |
| Q10 | Shape des payloads | `start` → `{session_id, reply}` ; `reply` → `{reply}` ; `stop` → `{status}` | Validé |
| Q11 | Chat multi-party | YAGNI | MVP |
| Q12 | MCP | 3 commandes exposées, sans `human` | Un LLM ne joue jamais un humain |
| Q13 | Config LLM | Système de providers nommés au niveau racine ; `model` dans le service = référence | Découplage config/service, réutilisation cross-service |

## Plan d'implémentation

7 étapes incrémentales, chacune testable isolément.

### Étape 1 — Porter les providers LLM depuis Symphonie

**Fichiers créés** :
- `src/simphonia/providers/base.py` — `LLMProvider(ABC)` + `LLMStats`
- `src/simphonia/providers/ollama.py` — port depuis Symphonie, `print(...)` → `logging`, imports adaptés
- `src/simphonia/providers/anthropic.py` — idem, clé API via `${ANTHROPIC_API_KEY}` dans le YAML
- `src/simphonia/providers/__init__.py` — ré-exports

**Dépendance runtime** : `httpx` dans `pyproject.toml` + `requirements.txt`.

**Terminé quand** : `OllamaProvider(model='gemma4:e4b')` instanciable sans erreur.

### Étape 2 — `provider_registry`

**Fichiers créés** :
- `src/simphonia/services/provider_registry/__init__.py`
  - `init(providers_config: dict)` — dispatch `protocol` → import dynamique, fail-fast si protocol inconnu
  - `get(name: str) -> LLMProvider` — fail-fast si nom introuvable
  - `list_names() -> list[str]`

**Bootstrap** : `provider_registry.init(configuration_service.section("providers"))` ajouté en premier.

**Terminé quand** : `provider_registry.get("gemma4").call(system, messages)` retourne une string non-None.

### Étape 3 — Squelette `chat_service` (sans LLM)

**Fichiers créés** :
- `src/simphonia/services/chat_service/types.py` — `DialogueMessage`, `DialogueState`
- `src/simphonia/services/chat_service/__init__.py` — ABC `ChatService`, factory, singleton `init/get`
- `src/simphonia/services/chat_service/strategies/__init__.py`
- `src/simphonia/services/chat_service/strategies/default_strategy.py` — `DefaultChatService(ChatService)`, registre `Dict[str, DialogueState]`, start/reply/stop fonctionnels, `reply=None`
- `src/simphonia/core/errors.py` (modif) — `SessionNotFound`, `InvalidParticipant`

**Terminé quand** : start/reply/stop fonctionnels en REPL, erreurs correctement levées.

### Étape 4 — Logger fichier (`/logs/chat.log`)

**Fichiers modifiés** :
- `build_chat_service` : helper `_build_chat_logger(log_config)` — FileHandler, `mode='w'` si `reset_on_startup`, path résolu depuis `PROJECT_ROOT`
- `.gitignore` : ajouter `logs/`

**Terminé quand** : log (re)créé au boot, cycle start/reply/stop tracé.

### Étape 5 — Commandes bus `chat`

**Fichiers créés** :
- `src/simphonia/commands/chat.py` — `start_command`, `reply_command`, `stop_command` (sans `mcp=True`)

**Fichiers modifiés** :
- `bootstrap.py` : ordre strict `provider_registry → memory → character → chat`

**Terminé quand** :
```
simcli dispatch chat start --payload '{"from_char":"marc","to":"antoine","say":"Salut","human":true}'
```
retourne un `session_id`.

### Étape 6 — Génération LLM + schéma JSON

**Fichiers modifiés** :
- `default_strategy.py` :
  - `_build_system_prompt(to_card, from_char, human)` :
    - Fiche de `to` en JSON indenté
    - Contexte interlocuteur : `human=True` → "Tu parles avec un humain nommé `<from_char>`" ; `human=False` → "Tu parles avec le personnage `<from_char>`"
    - Contrat JSON MVP dans le system prompt (schéma extensible vers la vision complète) :
      ```
      Réponds UNIQUEMENT avec un objet JSON valide :
      {"talk": ["ligne 1", "ligne 2"]}
      ```
  - `_build_messages(history, to_speaker)` → historique alterné `user/assistant`
  - Appel `self._provider.call(system_prompt, messages)`
  - Strip des balises markdown ` ```json ``` ` avant parsing (certains LLM enveloppent leur JSON)
  - Parsing : JSON valide + `talk` → `reply = "\n".join(talk)` ; sinon fallback texte brut + warning
  - Rollback si `LLMError` (ne pas corrompre l'historique)
- `core/errors.py` : ajouter `LLMError`

**Schéma JSON complet prévu (vision cible, implémenté progressivement)** : `from`, `to`, `talk`, `actions`, `mood`, `inner`, `expected`, `noticed`, `body`, `memory`.

**Terminé quand** : `to` répond en première personne en JSON valide, `talk` extrait correctement.

### Étape 7 — Façade MCP

**Fichiers modifiés** :
- `commands/chat.py` : `mcp=True` + contrats MCP sur les 3 commandes, sans paramètre `human`

**Bloqué sur** : backbone MCP (infra INFRA #14).

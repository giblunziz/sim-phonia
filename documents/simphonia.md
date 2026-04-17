# simphonia

- Module principal de l'application
- développé en python
- repose sur le principe publish/subscribe
- mise en place d'un système de event-bus simple mais multi-bus

## bus

### bus: system

bus destiné à recevoir les commandes systèmes de bases comme, par exemple, la commande /help (retourne la liste de toutes les instructions connues du bus ainsi que le description associées).

chaque commande dois pouvoir s'enregistrer auprès du bus au démarrage du serveur en utilisant le principe des annotations pour chaque commande

une commande est, à minima, composée d'un code unique, d'une description, d'une fonction callback qui sera appelée par le buson f

## Façade MCP

### Principe cardinal

simphonia est le **seul agent MCP** exposé aux LLM. Pas d'agents MCP disséminés dans les services. Un seul point d'entrée, un seul contrat externe.

### Exposition via le décorateur @command

Un service interne (ex: memory_service) expose ses fonctions comme des commandes bus classiques. Pour qu'une commande soit également accessible comme tool MCP par un LLM, le décorateur porte un attribut `mcp=True` avec le contrat MCP associé :

```python
@command(
    bus="memory", 
    code="recall", 
    description="Recherche de souvenirs dans la base de connaissances",
    mcp=True,
    mcp_description="Cherche dans tes souvenirs ce que tu sais sur quelqu'un dans un contexte donné.",
    mcp_params={
        "about": "Le prénom de la personne",
        "context": "Le sujet ou la situation qui te préoccupe"
    }
)
def recall(from_char: str, about: str, context: str) -> str:
    return memory_service.query(from_char, about, context)
```

### Câblage au démarrage

1. La discovery scanne les commandes (existant)
2. Le runtime filtre les commandes marquées `mcp=True`
3. Pour chacune, il déclare un tool MCP avec la description et les paramètres du contrat
4. Le contrat MCP (`mcp_description`, `mcp_params`) est rédigé du point de vue du personnage, pas du développeur

### Routage à l'exécution

```
LLM appelle le tool MCP "recall"
  → simphonia (point MCP unique) reçoit l'appel
  → route vers bus.memory.dispatch("recall", payload)
  → memory_service.query() exécute
  → résultat remonte au LLM
```

### Chaîne de services

Un service peut déléguer à un autre service en interne. Le bus route la commande vers le service déclaré, ce service peut appeler d'autres services dans sa chaîne :

```
LLM → simphonia (MCP) → bus.memory.recall → memory_service.query() 
                                                → shadow_service.intercept() 
                                                → résultat enrichi
```

Le LLM ne voit qu'un seul tool. La complexité interne est invisible.

### Règles

- `mcp_description` est toujours rédigé du point de vue du personnage, en langage naturel
- `mcp_params` décrit les paramètres visibles par le LLM (le `from_char` est injecté automatiquement par le runtime, pas par le LLM)
- Une commande bus sans `mcp=True` reste une commande interne — accessible via CLI et API REST mais invisible pour les LLM

## Conventions d'implémentation

Décisions techniques figées le 2026-04-16 (à respecter à toute extension future) :

### Cache : stratégie provider-side

Le cache est tenu par le **provider** (le service qui détient la donnée), jamais par le **consumer** (le service qui l'appelle). Un consumer appelle toujours le service provider directement à chaque besoin — c'est le provider qui décide de mettre en cache, d'invalider, ou de laisser passer.

Exemple : le `chat_service` appelle `character_service.get()` à chaque tour sans garder de copie locale. Le `character_service` gère son propre cache et supporte un reset si une fiche est modifiée en cours de session. Le consumer ne voit jamais la différence.

**Règle** : si tu te retrouves à mettre en cache une ressource issue d'un autre service dans ton service, c'est le signe que le cache doit être déplacé dans ce service source.

### Détection de `from_char`

- **Convention par nom** : si la signature de la commande contient un paramètre nommé exactement `from_char`, le bus l'injecte automatiquement avant l'appel.
- **Invariant fail-fast au startup** : toute commande déclarée `mcp=True` **doit** avoir `from_char` dans sa signature. Sinon le bootstrap échoue (catch précoce des erreurs de contrat MCP).
- Pas de flag `caller_aware` séparé sur le décorateur — la signature est l'unique source de vérité.

### `mcp_params` = JSONSchema riche

Le contrat exposé au LLM est un **JSONSchema complet** (type, required, enum, description), pas un simple dict `{nom: description}`. Le SDK MCP attend ce format ; on lui donne directement, on ne fait pas de wrapping.

### Format de retour MCP

Les tools MCP renvoient du **texte markdown formaté** (lisible par le LLM, prêt à être ré-injecté dans son raisonnement). La fonction métier peut renvoyer une structure ; un sérialiseur côté façade MCP la convertit en markdown si besoin.

### SDK MCP : officiel d'Anthropic

Bibliothèque utilisée : **`mcp`** (SDK Python officiel d'Anthropic). Pas de wrapper communautaire (FastMCP ou autre) — on évite le risque de divergence/abandon. La façade construit ses tools dynamiquement depuis le `BusRegistry`, donc l'ergonomie d'un wrapper aurait apporté peu.

### Topologie réseau : deux ports, un process

| Service | Port | Rôle |
|---|---|---|
| `HTTP_PORT` | défaut `8000` | API REST + bus + endpoints d'admin (utilisé par `simcli`) |
| `MCP_PORT` | défaut `8001` | Serveur MCP exposé aux LLM (tools générés depuis `@command(mcp=True)`) |

Les deux serveurs vivent dans **le même process Python** (lifecycle commun, mêmes services en mémoire, même `BusRegistry`), simplement avec deux pipelines de transport distincts. Évite la complexité de l'IPC et garantit la cohérence d'état.

### Cascade orpheline

Une `@cascade(bus=X, code=Y)` enregistrée pour un `(X, Y)` qui n'a pas de `@command` correspondante → **fail-fast au startup** (validation post-discovery).

## Services cascadés

### Principe

Certains services ne sont jamais appelés directement. Ils s'insèrent dans la chaîne d'exécution d'un autre service, en amont (before) ou en aval (after). C'est un pattern d'interception — le service principal ne sait pas qu'il est observé ou enrichi.

### Positions dans la chaîne

**After (post-traitement)** — le service cascadé reçoit le résultat du service principal et peut l'enrichir, le filtrer, ou l'altérer avant qu'il ne remonte à l'appelant.

```
bus.memory.recall
  → memory_service.query(from, about, context)
  → résultat brut (5 souvenirs par distance cosine)
  → shadow_service.after_recall(from, about, context, résultat)
  → résultat enrichi (5 souvenirs + 1 ancrage émotionnel injecté)
  → retour à l'appelant
```

**Before (pré-traitement)** — le service cascadé intercepte la requête avant le service principal et peut la transformer, l'enrichir, ou déclencher un effet de bord.

```
bus.memory.store
  → shadow_service.before_store(from, about, value)
  → détecte un pattern d'ancrage émotionnel, met à jour le registre d'ancrages
  → memory_service.store(from, about, value)
  → retour à l'appelant
```

### Exemples concrets

| Commande | Service principal | Service cascadé | Position | Effet |
|---|---|---|---|---|
| `memory.recall` | `memory_service.query()` | `shadow_service.after_recall()` | after | Injecte un ancrage émotionnel dans les résultats si le score de vulnérabilité est atteint |
| `memory.store` | `memory_service.store()` | `shadow_service.before_store()` | before | Détecte des patterns d'interaction récurrents, met à jour le registre d'ancrages entre joueurs |
| `memory.recall` | `memory_service.query()` | `decay_service.after_recall()` | after | Applique le decay temporel et incrémente le `recall_count` des souvenirs retournés |

### Enregistrement

Un service cascadé s'enregistre auprès du bus en déclarant sa position et la commande cible :

```python
@cascade(bus="memory", code="recall", position="after")
def after_recall(from_char, about, context, result):
    # result = ce que memory_service a retourné
    # retourner le résultat enrichi ou modifié
    return enriched_result

@cascade(bus="memory", code="store", position="before")
def before_store(from_char, about, value):
    # intercepter avant le store
    # peut modifier les paramètres ou déclencher des effets de bord
    return modified_args
```

### Règles

- Le service principal ne connaît pas ses intercepteurs — **découplage total**.
- Plusieurs services cascadés peuvent se chaîner sur la même commande. **Ordre d'exécution** : `priority` (entier, plus petit = plus tôt) puis ordre de discovery en cas d'égalité.
- Un service cascadé `after` peut retourner le résultat inchangé — **observation pure** légitime (logging, métriques).
- Un service cascadé `before` peut court-circuiter le service principal en levant l'exception **`ShortCircuit(result)`** (cas typiques : cache hit, validation bloquante). Sans `ShortCircuit`, le `before` retourne les arguments éventuellement modifiés et la chaîne continue.
- Un service cascadé peut être un plugin (`pip install symphonie-shadow`) — il s'enregistre au démarrage via la discovery. **(Plugins externes : hors scope v1, à venir.)**

### Gestion des erreurs — le `call` est l'autorité

Asymétrie volontaire : le service principal (`call`) est ce qui compte ; les cascades sont best-effort autour de lui.

| Étage qui plante | Comportement | Justification |
|---|---|---|
| `before` | **Fail-fast** — le `call` n'est pas exécuté, l'erreur remonte à l'appelant. | Une cascade `before` qui plante est considérée comme une volonté de bloquer la chaîne (équivalent implicite d'un `ShortCircuit` négatif). |
| `call` | **Fail-fast** — aucun `after` n'est exécuté, l'erreur remonte à l'appelant. | S'il n'y a pas de résultat, il n'y a rien à enrichir. |
| `after` | **Erreur ignorée + log warning**. Le résultat du `call` est retourné inchangé. Les `after` suivants s'exécutent quand même. | Une cascade `after` ne doit **jamais** dégrader la disponibilité du service principal. |

Conséquences :
1. Une cascade `before` *peut* servir de garde-fou (autorisation, validation, court-circuit cache).
2. Une cascade `after` *ne peut pas* casser le flux — elle observe ou enrichit best-effort.

## Circuit breaker

Pattern transverse appliqué aux interactions LLM (futur **moteur de tour joueur**). Un appelant qui échoue de manière répétée est temporairement isolé pour préserver le flux global de l'activité.

### Règles

- Compteur de tentatives par **(scope, identité)** — typiquement `(round_courant, joueur)` au niveau du moteur de tour.
- Seuil par défaut : **3 tentatives consécutives échouées** → l'identité est skipée pour le scope courant.
- Réinitialisation au passage du scope suivant (nouveau round → compteurs purgés).
- Une « tentative échouée » = absence de réponse exploitable : LLM timeout, JSON malformé, schéma de sortie invalide, tool call non résolvable après la boucle agentique.

### Périmètre v1

Hérité du pattern Symphonie (`Beholder.MAX_RETRIES = 3`). À porter dans le futur moteur de tour joueur côté simphonia.

### Hors scope v1

- Circuit breaker au niveau des cascades (cascade qui plante trop souvent → désactivée automatiquement).
- Circuit breaker au niveau des providers LLM (provider down → bascule vers fallback).
- Half-open / réarmement automatique après cooldown.

# simweb — Interface web React

## Description

`simweb` est le module front-end de sim-phonia. C'est une SPA React (Vite) qui pilote le serveur `simphonia` via son API HTTP, de la même façon que `simcli` mais depuis un navigateur. Elle ne contient aucune logique métier : tout reste côté serveur.

Sources dans `src/simweb/`.

## Stack

- **React 18** + **Vite 5** — SPA, pas de SSR
- Proxy Vite : `/bus → http://localhost:8000` (pas de CORS en dev, les requêtes partent du même origine)
- Aucune dépendance UI externe (CSS maison, thème sombre)

## Écrans

### StartScreen

Formulaire d'initialisation d'un dialogue.

| Champ | Détail |
|---|---|
| Combo *De* | Liste des personnages connus, chargée via `POST /bus/character/dispatch { code:"list" }` |
| Combo *À* | Idem |
| Textarea *Premier message* | Le `say` du `chat.start` |
| Checkbox *Mode humain* | `human: bool` — si coché, l'utilisateur joue `from_char` et répondra manuellement à chaque tour |

À la soumission : `POST /bus/chat/dispatch { code:"start", payload:{from_char, to, say, human} }`. En cas de succès, bascule vers `ChatScreen` avec le `session_id` et la première réplique de `to`.

### ChatScreen

Écran de chat actif.

**En-tête** : noms des deux participants, identifiant de session, bouton *Fermer*.

**Fil de messages** : bulles colorées par personnage (`from_char` = bleu, `to` = violet), scroll automatique vers le bas, indicateur de frappe animé pendant l'attente LLM.

**Mode humain (`human=true`)** : zone de saisie affichée en bas. Entrée = envoi (`chat.reply`), Maj+Entrée = saut de ligne. Chaque réponse LLM est affichée dès réception de la réponse HTTP synchrone.

**Mode autonome (`human=false`)** : aucune zone de saisie. Un bandeau indique que le dialogue est en cours. Les nouvelles répliques arrivent via SSE (voir ci-dessous).

**Bouton Fermer** : appelle `chat.stop`, puis retourne à `StartScreen`.

## Communication HTTP

Toutes les requêtes passent par le même endpoint :

```
POST /bus/{bus_name}/dispatch
Content-Type: application/json

{ "code": "<commande>", "payload": { ...args } }
```

Réponse : `{ "result": <valeur retournée par le service> }`.

Fonctions exposées dans `src/simweb/src/api/simphonia.js` :

| Fonction | Bus | Code | Payload |
|---|---|---|---|
| `listCharacters()` | `character` | `list` | `{}` |
| `chatStart(fromChar, to, say, human)` | `chat` | `start` | `{from_char, to, say, human}` |
| `chatReply(sessionId, fromChar, say, human)` | `chat` | `reply` | `{session_id, from_char, say, human}` |
| `chatStop(sessionId)` | `chat` | `stop` | `{session_id}` |

## SSE — événements bus en temps réel

Pour le mode autonome (`human=false`), les échanges LLM↔LLM se déroulent en tâche de fond côté serveur. Le front-end s'abonne via Server-Sent Events :

```
GET /bus/chat/stream/{session_id}
```

Chaque événement `chat.said` est poussé sous la forme :

```
data: {"type":"said","session_id":"...","from_char":"marc","to":"antoine","content":"..."}
```

Un keepalive (`{"type":"keepalive"}`) est envoyé toutes les 25 secondes pour maintenir la connexion.

### Câblage côté serveur

| Fichier | Rôle |
|---|---|
| `http/sse.py` | Publisher thread-safe : `publish(session_id, event)` (appelable depuis threads sync via `run_coroutine_threadsafe`), `subscribe(session_id)` générateur async pour `StreamingResponse` |
| `http/routes.py` | Endpoint `GET /bus/chat/stream/{session_id}` |
| `http/app.py` | Middleware CORS (`allow_origins=["*"]` en dev) + hook `startup` pour capturer la loop asyncio |
| `commands/chat.py` | `said_command` appelle `sse.publish(...)` avant de lancer `auto_reply` en thread daemon |

## Lancement

```bash
cd src/simweb
npm install
npm run dev        # → http://localhost:5173
```

Le serveur simphonia doit tourner sur `:8000`.

```bash
# build de production
npm run build      # → dist/
npm run preview    # prévisualise le build
```

## Limites actuelles

- Pas d'authentification.
- Une seule session à la fois (pas de multi-onglets géré).
- En mode autonome, pas de bouton *Pause* — pour arrêter, utiliser *Fermer*.
- Le SSE ne capture que les événements `chat.said` (LLM→LLM). Les répliques synchrones (`chat.start` / `chat.reply`) sont gérées directement depuis la réponse HTTP, pas via SSE.

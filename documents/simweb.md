# simweb — Interface web React

## Description

`simweb` est le module front-end de sim-phonia. C'est une SPA React (Vite) qui pilote le serveur `simphonia` via son API HTTP. Elle ne contient aucune logique métier : tout reste côté serveur.

Sources dans `src/simweb/`.

## Stack

- **React 18** + **Vite 5** — SPA, pas de SSR
- Proxy Vite : `/bus → http://localhost:8000` (pas de CORS en dev)
- Aucune dépendance UI externe (CSS maison, thème sombre)

## Layout

L'interface est organisée en deux zones :

```
┌──────────┬────────────────────────────────────┐
│ Sidebar  │  Panneau principal                 │
│ (210 px) │  (flex-1, scrollable)              │
│          │                                    │
│  ‹ / ›   │  <StartScreen> ou <ChatScreen>     │
│          │  ou <ServerPanel>                  │
│  ▾ Chat  │  ou <CharactersPanel>              │
│  · Conv. │  ou <MemoryPanel>                  │
│          │                                    │
│  ▾ Admin │                                    │
│  · Serveur                                    │
│  · Perso │                                    │
│  · Mémoire                                   │
└──────────┴────────────────────────────────────┘
```

### Sidebar

- Collapsible : bouton ‹/› — bascule entre 210 px et 38 px (transition CSS).
- Accordéon : 2 sections dépliables indépendamment (*Chat*, *Administration*).
- L'item actif est mis en surbrillance (couleur accent + fond teinté).

### Composants principaux

| Fichier | Rôle |
|---|---|
| `App.jsx` | État global (`session`, `activePanel`), rendu conditionnel du panneau actif |
| `components/Layout.jsx` | Wrapper sidebar + main-content, état `sidebarOpen` |
| `components/Sidebar.jsx` | Sidebar collapsible + accordéon de navigation |
| `components/StartScreen.jsx` | Formulaire d'initialisation d'un dialogue |
| `components/ChatScreen.jsx` | Écran de chat actif (mode humain + mode autonome SSE) |
| `components/admin/ServerPanel.jsx` | Ping serveur + tableau de toutes les commandes bus |
| `components/admin/CharactersPanel.jsx` | Liste des persos, fiche détaillée, reset |
| `components/admin/MemoryPanel.jsx` | Formulaire recall + affichage des souvenirs |

## Écrans & panneaux

### StartScreen

Formulaire d'initialisation d'un dialogue.

| Champ | Détail |
|---|---|
| Combo *De* | Liste des personnages via `character/list` |
| Combo *À* | Idem |
| Textarea *Premier message* | Le `say` de `chat.start` |
| Checkbox *Mode humain* | `human: bool` — l'utilisateur joue `from_char` manuellement |

À la soumission : `chat.start`. En cas de succès, bascule vers `ChatScreen`.

### ChatScreen

**En-tête** : noms des participants, identifiant de session, bouton *Fermer*.

**Fil de messages** : bulles colorées (`from_char` = bleu, `to` = violet), scroll auto, indicateur de frappe animé.

**Mode humain** : zone de saisie en bas — Entrée = envoi (`chat.reply`), Maj+Entrée = saut de ligne.

**Mode autonome** : bandeau informatif, répliques reçues via SSE.

**Bouton Fermer** : `chat.stop` puis retour au StartScreen.

### ServerPanel

- Bouton **Ping** → `system/ping` — affiche ✓/✗ + heure.
- Bouton **Charger** → `GET /bus` + `GET /bus/{name}/commands` — tableau de toutes les commandes enregistrées sur tous les bus (bus / code / description).

### CharactersPanel

- Grille de chips, une par personnage (`character/list`).
- Clic sur un chip → charge la fiche via `character/get` et l'affiche en JSON formaté.
- Bouton **Recharger** → `character/reset` — recharge les fiches depuis la source et rafraîchit la liste.

### MemoryPanel

Formulaire **recall** :

| Champ | Détail |
|---|---|
| *Personnage* | `from_char` — select parmi les persos connus |
| *À propos de* | `about` — optionnel, filtre les souvenirs sur une cible précise |
| *Contexte* | `context` — texte libre décrivant la situation |

Résultats affichés sous forme de cartes :
- Tags colorés : `about` (bleu), `category` (violet), `scene` (neutre).
- Pertinence : `(1 − distance) × 100 %`.
- Texte du souvenir.

## Communication HTTP

Toutes les commandes passent par :

```
POST /bus/{bus_name}/dispatch
{ "code": "<commande>", "payload": { ...args } }
→ { "result": <valeur> }
```

Fonctions exposées dans `src/simweb/src/api/simphonia.js` :

| Fonction | Bus | Code |
|---|---|---|
| `listCharacters()` | `character` | `list` |
| `getCharacter(name)` | `character` | `get` |
| `resetCharacters()` | `character` | `reset` |
| `ping()` | `system` | `ping` |
| `getAllCommands()` | HTTP direct | `GET /bus` + `/bus/{n}/commands` |
| `memoryRecall(fromChar, context, about?)` | `memory` | `recall` |
| `chatStart(fromChar, to, say, human)` | `chat` | `start` |
| `chatReply(sessionId, fromChar, say, human)` | `chat` | `reply` |
| `chatStop(sessionId)` | `chat` | `stop` |

## SSE — événements temps réel

Mode autonome (`human=false`) : le front s'abonne via :

```
GET /bus/chat/stream/{session_id}
```

Événements reçus :

```
data: {"type":"said","session_id":"...","from_char":"marc","to":"antoine","content":"..."}
data: {"type":"keepalive"}   ← toutes les 25 s
```

### Câblage côté serveur

| Fichier | Rôle |
|---|---|
| `http/sse.py` | Publisher thread-safe : `publish` / `subscribe` |
| `http/routes.py` | Endpoint `GET /bus/chat/stream/{session_id}` |
| `http/app.py` | Middleware CORS + hook startup asyncio |
| `commands/chat.py` | `said_command` publie l'événement puis lance `auto_reply` |

## Lancement

```bash
cd src/simweb
npm install
npm run dev        # → http://localhost:5173
```

Le serveur simphonia doit tourner sur `:8000`.

```bash
npm run build      # → dist/
npm run preview    # prévisualise le build
```

## Limites actuelles

- Pas d'authentification.
- Une seule session de chat à la fois.
- En mode autonome, pas de bouton *Pause* — utiliser *Fermer*.
- Les répliques synchrones (`chat.start` / `chat.reply`) passent par HTTP, pas SSE.

# Activité — Présentation

## Rôle dans l'architecture

L'activité `presentation` est le point d'entrée de toute session de jeu.
Elle initialise la collection `knowledge` avec les premières impressions croisées entre joueurs — données ensuite injectées dans le system prompt de toutes les activités suivantes.

## Phase 1 — Onboarding et auto-présentation

Chaque joueur reçoit un system prompt expliquant le contexte de sa présence (ex. : gagnant d'une loterie, séjour d'une semaine offert, etc.).

Il lui est demandé de **se présenter aux autres** en texte libre, avec les contraintes suivantes :
- Basé uniquement sur sa fiche personnage
- Interdit d'inventer
- Interdit de mentir
- Pas obligé de tout dévoiler

## Phase 2 — Cross-analyse

Chaque présentation est distribuée à tous les autres joueurs.
Il leur est demandé de **se faire un avis** et de **mémoriser selon leurs propres termes** ce qu'ils retiennent de chaque participant.

Ces informations sont enregistrées dans la collection `knowledge` avec `activity: "presentation"`.

### Exemple d'entrée produite

```json
{
  "from":     "diane",
  "about":    "julien",
  "activity": "presentation",
  "category": "perceived_traits",
  "scene":    "yacht",
  "value":    "Présentation très travaillée — chaque geste, chaque mot semble calibré pour mettre à l'aise"
}
```

Les catégories utilisées sont les catégories standard : `perceived_traits`, `assumptions`, `approach`, `watchouts`.

## Usage dans le context builder

Lors du chargement du contexte d'un joueur pour toute activité suivante, le builder interroge :

```
knowledge.find({
  from:     <player_slug>,
  activity: "presentation",
  about:    { $in: <autres_joueurs_de_l_instance> }
})
```

Les résultats sont groupés par `about` puis par `category`, et injectés dans le system prompt sous la forme :

```
## Tes impressions sur les autres participants

Ces analyses reflètent tes premières impressions. Elles guident ta manière d'interagir avec chacun.

### Ce que tu sais à propos de <about>

- **<category>** : <value>
- **<category>** : <value>
```

## Position dans le cycle de jeu

```
presentation (phases 1+2)  →  knowledge["activity": "presentation"]
       ↓
activity_context_builder  →  injection dans system prompt de chaque activité suivante
       ↓
activités de jeu (action_verite, insight, ...)
       ↓
debrief  →  knowledge["activity": "<slug_activite>"]  →  ChromaDB (via memory/resync)
```

# Modèle de fiche personnage — normalisation

> **Statut** : document vivant. On normalise section par section, en convergeant sur un modèle exploitable à la fois par le LLM (lecture du system prompt) et par l'éditeur de fiche RJSF (UI). La source-of-truth reste MongoDB ; les fichiers `resources/characters/*.json` sont des seeds, pas la cible. Les fiches existantes ne sont pas modifiées dans ce document — on définit le modèle, la migration des seeds viendra ensuite.

## 1. `psychology` — état d'avancement

### 1.1 `psychology.insight` — profil DISC

**Décisions actées**

| Point | Choix |
|---|---|
| Modèle | DISC classique : 4 axes indépendants (Rouge / Vert / Bleu / Jaune) |
| Contrainte | **Pas** de somme imposée — un perso peut être 50/25/75/62. Chaque axe vit sa vie. |
| Naming des clés | Anglais : `red`, `green`, `blue`, `yellow` (cohérence avec les autres clés JSON du projet). |
| Champ `details` | **Conservé** en plus des 4 valeurs — la nuance narrative (« rouge bienveillant » vs « rouge dictateur ») n'est pas capturable en chiffres. C'est ce texte qui nourrit le system prompt LLM. |
| UI | `details` → **text-area** (multiligne). Les 4 axes → sliders ou number 0-100. |
| `gap` | Reste **descriptif** (POV du personnage). La quantification du gap (distance entre adapted et real) est de la responsabilité de **Tobias** (cf. `cognition.md`, intervention DISC du psy), pas du modèle de fiche. |

**Modèle cible**

```json
"psychology": {
  "insight": {
    "adapted": {
      "red":    30,
      "green":  70,
      "blue":   60,
      "yellow": 20,
      "details": "Le mari idéal en surface. Empathique, stable, prévisible…"
    },
    "real": {
      "red":    20,
      "green":  10,
      "blue":   90,
      "yellow": 5,
      "details": "Froid, analytique, en calcul permanent. Sous la surface, il ne sent pas — il évalue…"
    },
    "gap": "Significatif. Le vert est un costume quotidien. Le bleu un bunker quand la pression monte."
  }
}
```

**Contraintes de validation**

- `adapted` et `real` : les 4 axes (`red`, `green`, `blue`, `yellow`) sont **requis**, type entier, `[0, 100]`.
- `details` : requis, string non vide, sans limite haute (text-area).
- `gap` : optionnel, string libre. Pas de version structurée — c'est Tobias qui en dérive les métriques.

**Notes pour l'UI (RJSF)**

- `uiSchema` à prévoir :
  - `adapted.red/green/blue/yellow` → widget `range` (slider 0-100), avec libellé coloré.
  - `adapted.details` → `ui:widget: textarea` + `ui:options: { rows: 4 }`.
  - Idem `real.*`.
  - `gap` → `ui:widget: textarea`.
- Visuellement, possible amélioration future : un radar chart 4 axes côte à côte adapted vs real, avec le gap en hachuré entre les deux. Pas critique pour la v1 de l'éditeur.

**Lecture LLM (system prompt)**

Les 4 valeurs numériques + `details` doivent être rendus ensemble dans le prompt — les chiffres seuls ne suffisent pas à faire jouer le perso. Format de rendu à définir dans `activity_context_builder` quand on y arrivera.

### 1.2 `psychology.transactional` — à normaliser

> À traiter. Aujourd'hui : 4 sous-champs string libres (`dominant`, `adult`, `parent`, `child`), parfois absents. Question ouverte : structure-t-on de la même manière (intensité 0-100 par état du moi + details) ou on reste en texte libre ?

### 1.3 `psychology.values` — à normaliser

> À traiter. Aujourd'hui : array de `{name, details}`. À voir si on ajoute une priorisation / un poids.

### 1.4 `psychology.defense` / `comfort` / `threat`

**Décisions actées**

| Point | Choix |
|---|---|
| Forme | Array de strings — `["…", "…"]` — pour les trois champs. |
| Argument | Cohérence avec `flaws`, `social`, `likes`. KISS. Aujourd'hui mix string/array selon les fiches, on aligne. |
| UI | Array éditable, chaque item en text-area. |
| Cardinalité | `defense` typiquement 1-2 items (mécanisme principal). `comfort` / `threat` : 1 à 6 items, libre. Pas de min/max imposé. |

**Modèle cible**

```json
"psychology": {
  "defense": [
    "L'humour systématique. Il désamorce tout sujet sérieux ou intime par une blague."
  ],
  "comfort": [
    "Avoir un public, faire rire, sentir tous les regards sur lui",
    "Cuisiner pour les autres — pas pour le résultat, pour l'attention"
  ],
  "threat": [
    "Le silence, l'indifférence",
    "Quelqu'un qui voit derrière le masque et lui demande comment il va vraiment"
  ]
}
```

**Note migration** (pour mémoire)

Les fiches actuelles avec une string brute (Théo, Marc partiel) deviennent un array à un seul élément. Pas de perte d'information.

## 2. `flaws` — état d'avancement

**Décisions actées**

| Point | Choix |
|---|---|
| Forme | `flaws: ["…", "…", "…"]` — **array de strings**, pas d'objet structuré. |
| Argument | KISS. Le LLM consomme du texte. La forme `{trait, details}` historique apportait un faux gain de structure (étiquettes `trait` libres et hétérogènes selon les fiches, jamais exploitées par un consommateur). |
| UI | Array éditable, chaque item en text-area. Boutons add/remove standards RJSF. |
| Cardinalité | Pas de min/max imposé. Une fiche NPC light peut avoir 1 entrée, un PC central 5-6. |

**Modèle cible**

```json
"flaws": [
  "Lâche : ne dira pas la vérité, pas par protection mais par peur de perdre le confort, le couple, la façade. Préfère le mensonge au risque de destruction.",
  "Passif : laisse Élise décider de tout, par abdication. A renoncé à avoir un avis le jour où en avoir un impliquait de défendre sa version de la réalité.",
  "Hypocrite : joue le mari attentionné et l'est sincèrement, mais chaque geste tendre est contaminé par la culpabilité."
]
```

**Note migration** (hors scope ce doc — pour mémoire)

Les fiches actuelles en `[{trait, details}]` se concatènent en `f"{trait.capitalize().replace('_', ' ')} : {details}"` (ou laisser au goût du copywriter humain). Théo est déjà au bon format.

## 3. Sections suivantes (à traiter)

- `psychology.transactional` — 4 états du moi : intensité 0-100 + details, ou texte libre ?
- `psychology.values` — array `[{name, details}]`, priorisation à ajouter ?
- `background` — `marking_events`, `family.details`, etc.
- `game` — `phobia`, `secret`, `prior_knowledge`
- `memory` — déjà bien structuré (`slots` + `style`), à confirmer
- `appearance` — beaucoup de champs optionnels variant d'une fiche à l'autre, à figer
- `social`, `likes` — déjà arrays de strings, OK

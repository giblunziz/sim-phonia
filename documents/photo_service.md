# Etude du service photo_service

Description : mise à disposition d'un service photographique permettant aux personnages de prendre des photos et de les diffuser sur le bus.

Deux fonctions MCP exposées aux joueurs :
- `take_shoot` : illustrer une scène devant soi (photo du décor / des autres)
- `take_selfy` : prendre une photo de soi (autoportrait)

## Description

`photo_service` est un service simphonia qui met à disposition des joueurs (LLM) la capacité de **prendre des photos** et de les **diffuser** via le bus. Deux entrées MCP exposées : `take_shoot` (illustrer une scène devant soi) et `take_selfy` (autoportrait).

L'image est générée par une **stratégie** (pattern interface + impl) ; la première implémentation est locale, basée sur **Z-Image Turbo** (modèle DiT distillé, 8 NFE, prompt FR natif via Qwen 3 4B comme text encoder, VAE Flux). La pipeline est chargée via `diffusers` (depuis git, support `ZImagePipeline` non encore en PyPI stable). Les photos sont persistées sur le filesystem du jeu, leurs métadonnées en Mongo, et publiées sur un bus dédié `photo` pour permettre aux services en cascade (Tobias / shadow_memory / futur photo_analyzer) de les exploiter.

En v1 : visibilité uniquement par le joueur qui a pris la photo, restitution côté simweb façon « SMS reçu ».

## Cahier des charges

### 1. Surface MCP

Deux commandes exposées au LLM-joueur, toutes deux `@command(mcp=True)`.

#### 1.1 `take_shoot` — photo de scène

`mcp_description` (point de vue personnage) : *« Prends une photo de la scène devant toi. Décris ce que tu vois et comment tu veux la cadrer. »*

Le LLM est libre sur toutes les sections (`# style`, `# sujet`, `# tenue`, `# attitude`, `# pose`, `# arriere_plan`, `# ambiance`, `# lumière`…). Aucune section n'est imposée ni écrasée par le service — c'est une photo libre.

#### 1.2 `take_selfy` — autoportrait

`mcp_description` (point de vue personnage) : *« Prends un selfie de toi. Décris ton expression, ta tenue, où tu te trouves. »*

Le LLM ne pilote **que** les sections "variables" (`# tenue`, `# attitude`, `# pose`, `# arriere_plan`, `# ambiance`, `# lumière`…). Les sections **réservées** suivantes sont **construites par le service** et écrasent toute valeur fournie par le LLM :

- `# style` ← `photo_service.style_prefix.take_selfy` (config YAML)
- `# sujet` ← `photo_service.subject_template` résolu sur la fiche perso (cf. §4)

Ce verrouillage garantit la cohérence visuelle inter-selfies (Aurore reste Aurore d'une photo à l'autre — auburn, yeux verts, bijoux signature) sans brider le LLM sur le contexte (tenue, pose, lieu).

#### 1.3 Format de réponse — markdown sectionné

**Un seul paramètre MCP** : `markdown: string`. Le LLM produit un blob markdown structuré en sections :

```markdown
# tenue
veste noire, caraco ivoire.

# attitude
regard doux

# pose
allongée sur le dos dans un lit.
```

**Pourquoi markdown plutôt que JSON :**
- Pas d'échappement de guillemets / quotes dans les prose descriptions
- Multilignes naturels
- LLM-friendly (production fluide, pas de risque de JSON malformé)
- Liste de sections **ouverte** : aucune modification de l'API MCP n'est nécessaire pour ajuster les conventions internes au fil de l'eau

**Parsing côté service :** split par `\n# `, dict ordonné `section → contenu`. Sections inconnues : conservées telles quelles, concaténées dans le prompt final.

**Reconstruction du prompt final** (envoyé au provider) :

```markdown
# style
{style_prefix de la commande, depuis YAML}

# sujet
{subject_template résolu sur la fiche, pour take_selfy}

# tenue
{...}

# attitude
{...}

# pose
{...}
```

Cette string markdown est passée telle quelle au provider — Z-Image Turbo (T5-XXL en encoder texte) digère le format strophes nommées en français nativement, démontré sur trois photos d'Aurore en contextes radicalement différents (plage / studio / lit) avec invariants identitaires préservés.

### 2. Stratégie

Pattern identique à `character_service` / `memory_service` : interface ABC unique, stratégies enregistrées, sélection par configuration YAML (clé `strategy:`). Conformément à `simphonia/services/CLAUDE.md`, on utilise `abc.ABC` (pas `typing.Protocol`) — le pattern strategy demande qu'une implémentation déclare explicitement son contrat.

```python
class PhotoService(ABC):
    @abstractmethod
    def take_shoot(self, markdown: str, from_char: str, session_id: str, activity_id: str | None = None) -> dict: ...
    @abstractmethod
    def take_selfy(self, markdown: str, from_char: str, session_id: str, activity_id: str | None = None) -> dict: ...
    @abstractmethod
    def get_photo(self, photo_id: str) -> dict | None: ...
```

Implémentation v1 : `ZImageTurboPhotoService` — pipeline Python directe via `diffusers`, modèle chargé en VRAM dans le process simphonia. Pas de second process Python, pas de queue HTTP. Le pattern strategy garde la porte ouverte pour une variante `ComfyUIPhotoService` plus tard (workflows lourds : LoRAs, ControlNet, upscaling chaînés — hors scope v1).

### 3. Bus `photo`

Bus dédié, cohérent avec le pattern un-bus-par-service. Permet aux cascades shadow_memory / Tobias / futur photo_analyzer de s'attacher proprement, et laisse `messages` sémantiquement réservé au canal texte.

| code | scope | mcp | description |
| ---- | ----- | --- | ----------- |
| `take_shoot` | bus | mcp=True | génère + publie une photo de scène |
| `take_selfy` | bus | mcp=True | génère + publie un autoportrait |
| `publish` | bus | interne | émet l'événement `photo.published` (consommé par cascades + simweb) |
| `get` | bus | interne | retourne une photo par `photo_id` (pour simweb / replay) |

Cascades anticipées (YAGNI v1, design préservé) : `after` sur `take_shoot`/`take_selfy` pour analyse VLM + injection dans shadow_memory.

### 4. Construction du sujet — `subject_template`

Le `# sujet` injecté pour `take_selfy` est construit depuis un **template configurable dans le YAML**, résolu en mode schemaless sur le JSON de la fiche perso.

**Template par défaut :**

```yaml
subject_template: "{_id}, {gender} de {age} ans, {appearance.build}, yeux {appearance.eyes}, cheveux {appearance.hair}, accessoires {appearance.accessories}"
```

**Mécanique de résolution :**

1. Parser les placeholders `{path.dotted}` dans le template.
2. Pour chacun, walk dotted sur le JSON de la fiche (`_id` → `appearance.eyes` → etc.).
3. Si résolu → substituer.
4. Si non-résolu (clé absente, `None`, ou string vide) → **virer le segment entier** délimité par les séparateurs `,` du template.

**Exemple de résolution complète (Aurore) :**

Template :
```
{_id}, {gender} de {age} ans, {appearance.build}, yeux {appearance.eyes}, cheveux {appearance.hair}, accessoires {appearance.accessories}
```

Fiche partielle :
```yaml
_id: aurore
gender: femme
age: 29
appearance:
  build: "Fine, féminine, élancée. Présence naturelle"
  eyes: "Verts, lumineux. Regard accueillant mais attentif"
  hair: "Auburn/dorés, longs, soyeux, ondulations naturelles. Toujours impeccables, jamais attachés"
  accessories: "Collier fin en or, boucles d'oreilles pendantes discrètes, bracelet doré au poignet"
```

Résultat injecté dans `# sujet` :
```
aurore, femme de 29 ans, Fine, féminine, élancée. Présence naturelle, yeux Verts, lumineux. Regard accueillant mais attentif, cheveux Auburn/dorés, longs, soyeux, ondulations naturelles. Toujours impeccables, jamais attachés, accessoires Collier fin en or, boucles d'oreilles pendantes discrètes, bracelet doré au poignet
```

**Exemple avec champs manquants :**

Fiche partielle :
```yaml
_id: marie
gender: femme
age: 35
appearance:
  hair: "noir court"
```

Résultat (les segments `{appearance.build}`, `yeux {appearance.eyes}`, `accessoires {appearance.accessories}` sont supprimés) :
```
marie, femme de 35 ans, cheveux noir court
```

**Avantage :** Valère peut étoffer les fiches au fil de l'eau (ajout de `appearance.skin`, `appearance.distinctive_features`…) sans toucher au code — il suffit d'enrichir le template YAML.

### 5. Persistance

- **Fichier** : binaire PNG sur le filesystem.
  - Path : `<output_dir>/<from_char>/<photo_id>.png`
  - `from_char` = `_id` Mongo brut du personnage (pas de slugification supplémentaire — l'`_id` est déjà canonique).
- **Métadonnées** : Mongo, collection `photos`. Schéma minimum :

```python
{
    "photo_id": str,                   # uuid
    "type": "shoot" | "selfy",
    "from_char": str,                  # _id Mongo du personnage
    "timestamp": datetime,
    "session_id": str,
    "activity_id": str | None,
    "prompt_markdown": str,            # markdown brut produit par le LLM
    "prompt_resolved": str,            # markdown final après injection style/sujet (ce qui est envoyé au provider)
    "file_path": str,                  # path absolu ou relatif au output_dir
    "width": int,
    "height": int,
    "model_used": str,                 # ex: "z_image_turbo"
    "seed": int,
}
```

Mongo est **la source de vérité indexable**. Le path filesystem est une commodité pour le browse manuel et le servage HTTP simweb.

### 6. Mode async — hybride

Génération en arrière-plan, le tour LLM ne bloque pas.

**Séquence :**

1. LLM-joueur appelle `take_selfy(markdown=...)` via MCP.
2. Le service valide rapidement (parsing markdown OK), génère un `photo_id`, enregistre la métadonnée Mongo en état `queued`.
3. **Ack synchrone côté MCP** : `{"status": "queued", "photo_id": "..."}` — le LLM-joueur peut continuer son tour.
4. La génération Z-Image Turbo (~2-4s sur 8 steps en bf16 sur GPU consumer) tourne en background.
5. Une fois l'image écrite sur disque, le service émet `photo.published` sur le bus avec le `photo_id`.
6. Les consommateurs réagissent : simweb (push SSE), cascades shadow_memory (à venir), etc.

Cette séparation en deux temps (ack rapide + événement bus) :
- préserve la fluidité du tour LLM,
- s'aligne sur l'event-bus comme colonne vertébrale,
- scale naturellement si on branche un provider plus lourd (ComfyUI, modèle plus gros).

### 7. Visibilité (v1)

- **Joueur émetteur** : oui, en simweb uniquement (panneau « SMS reçu »). Pas de réinjection dans son prochain contexte LLM v1 — tous les modèles ne supportent pas le multimodal, et ça ouvre une boîte de Pandore qu'on n'ouvre pas tout de suite.
- **Autres joueurs** : non en v1.
- **Côté simweb** : push via le canal **SSE existant** (mode autonome chat/activity), avec ajout d'un type d'événement `photo.published`. Pas de nouveau endpoint SSE — un seul canal par session simweb, multiplexé par type. Cohérent avec l'existant.

### 8. Configuration YAML

Sous `services.photo` :

```yaml
services:
  photo:
    strategy: z_image_turbo
    output_dir: "./data/photo"
    database_uri: ${MONGO_URI}
    database_name: ${MONGO_DATABASE}
    collection: photos
    style_prefix:
      take_shoot: "Photographie réaliste, cadrage soigné, lumière naturelle."
      take_selfy: "Photo selfie réaliste, prise au smartphone, angle naturel. Lumière naturelle."
    subject_template: "{_id}, {gender} de {age} ans, {appearance.build}, yeux {appearance.eyes}, cheveux {appearance.hair}, accessoires {appearance.accessories}"
    strategies:
      z_image_turbo:
        model_id: Tongyi-MAI/Z-Image-Turbo
        steps: 8
        width: 1024
        height: 1024
        seed: null              # null | -1 = random à chaque génération ; entier = reproductible (debug)
        device: cuda
        dtype: bfloat16
```

**Séparation service-level / strategy-level :**
- top-level `services.photo` : sémantique simphonia (style, sujet, storage, choix de la stratégie).
- `strategies.<name>` : params techniques propres à la stratégie active (modèle, device, hyperparams de génération).

`style_prefix` est un **dict par commande**, extensible aux futures variantes (`take_polaroid`, `take_cctv`, etc.) sans modification de structure.

### 9. Overrides CLI

Conformes au pattern d'overrides simphonia (cf. `documents/configuration.md`) :

- `--photo-seed <int>` : force le seed pour la session courante (debug visuel, reproductibilité d'un bug).
- `--photo-provider <name>` : force le provider (test multi-provider à venir).

### 10. Hors scope v1 (mentionné pour mémoire)

- Analyse VLM des photos et injection dans shadow_memory (cascade `after` à venir)
- Diffusion aux autres joueurs présents
- Réinjection de l'image dans le contexte LLM (modèles multimodaux uniquement)
- Édition / retouche / variations
- Stockage cloud / CDN
- Override `photo_style` dans la fiche perso (le `style_prefix` YAML suffit en v1)
- Provider `ComfyUIProvider` pour workflows lourds (LoRAs, ControlNet)

## Décisions de conception

| Q | Choix | Argument court |
| --- | --- | --- |
| Q1 — Mode de run Z-Image Turbo | Pipeline Python directe via `diffusers` | Modèle natif diffusers, pas de second process, strategy garde la porte ouverte pour ComfyUI. |
| Q2 — Bus | Bus `photo` dédié | Cohérent avec le pattern un-bus-par-service ; cascades shadow_memory propres ; `messages` reste le canal texte. |
| Q3 — Mode async | Hybride (ack synchrone + événement bus) | Tour LLM non bloquant ; event-bus = colonne vertébrale ; scale au prochain modèle plus lourd. |
| Q4 — Stockage filesystem | `./data/photo/<from_char>/<photo_id>.png` | Mongo source de vérité ; sous-arbo facilite browse manuel ; `from_char` = `_id` Mongo brut. |
| Q5 — Métadonnées Mongo | Set complet incluant `seed` configurable | Reproductibilité dev/test via `seed: null \| -1 \| <int>`. |
| Q6 — Push simweb | SSE existant multiplexé, type `photo.published` | Un seul canal SSE par session ; moins de plomberie. |
| Q7 — Cohérence visuelle `take_selfy` | (b) `style` et `sujet` auto-construits par le service | `style_prefix` YAML + `subject_template` résolu sur fiche ; le LLM garde la main sur tenue/attitude/pose/contexte. Démontré OK sur 3 photos d'Aurore en contextes différents. |
| Q7.1 — Construction du sujet | Template YAML + walk schemaless + segment-removal sur virgule | Latitude pour étoffer les fiches sans toucher au code. |
| Q7.2 — Préfixe style | `style_prefix` dict par commande dans le YAML | Extensible (futures `take_polaroid` etc.) sans modification de structure. |
| Q8 — Format de la réponse LLM | Markdown sectionné (un param `markdown: string`) | Pas d'échappement, multilignes naturels, LLM-friendly, sections ajustables côté code sans toucher l'API MCP. |

## Évolutions prévues

- **`photo_appearance` dans la fiche perso** : champ optionnel orienté photo, exploité par le `subject_template` (clé supplémentaire utilisable dans le template).
- **Cascade `after` sur `take_shoot` / `take_selfy`** : déclenche un `photo_analyzer` (VLM type Gemma3-Vision / LLaVA) qui produit une description sémantique, injectée dans `shadow_memory` sur le canal du joueur émetteur. Permet à Tobias d'exploiter la photo dans le `recall` (« ce que tu vois sur la photo que tu viens de prendre »).
- **Diffusion aux autres joueurs présents** : avec règle de visibilité par activité (qui voit quoi), restitution simweb identique.
- **Réinjection multimodale** : pour les LLM-joueurs sur modèle vision, ré-injecter l'image dans leur contexte au tour suivant.
- **Provider `ComfyUIProvider`** : workflows complexes (LoRAs perso fine-tunés sur la fiche, ControlNet pour pose imposée, upscaling chaîné).
- **Variations / édition** : `take_variation(photo_id)`, retouche locale.

## Plan d'implémentation

Découpage en 5 lots, tous en priorité **HOT** dans le `backlog.md`.

### Lot 1 — Squelette + config + dépendances *(~0.5j)*

**Objectif :** infrastructure prête, `simphonia` démarre avec le service enregistré (vide).

- Arbo `simphonia/services/photo_service/` :
  - `__init__.py` : ABC `PhotoService`, Protocol `PhotoProvider`, factory `build_photo_service(service_config)` (vide pour l'instant), `init() / get()` (singleton — pattern `character_service`).
  - `strategies/__init__.py` : placeholder.
- Section YAML `services.photo` dans `simphonia.yaml` (structure complète du §8).
- Branchement dans `simphonia/bootstrap.py` : `photo_service.init(configuration_service.section("services.photo"))`, après `character_service`, avant la discovery `commands/`.
- Dépendances dans **`pyproject.toml` ET `requirements.txt`** (même commit) :
  - `diffusers>=0.30`
  - `pillow>=10`
  - `accelerate>=0.30`
  - `torch` explicité (déjà tiré transitivement par `sentence-transformers` mais à pinner ici).

**Critère de fin :** `simphonia` démarre sans erreur, `services.photo` apparaît dans le dump de config.

### Lot 2 — Helpers schemaless réutilisables *(~0.5j)*

**Objectif :** modules purs Python, testables sans GPU.

- `simphonia/services/photo_service/subject_template.py` :
  - `resolve_subject_template(template: str, character: dict) -> str`
  - Parsing placeholders `{path.dotted}` (regex `\{([\w.]+)\}`)
  - Walk schemaless sur le dict (clé absente / `None` / string vide → unresolved)
  - Segment-removal sur virgule pour les non-résolus.
- `simphonia/services/photo_service/markdown_io.py` :
  - `parse_sections(markdown: str) -> dict[str, str]` (split par `\n# `)
  - `render_sections(sections: dict[str, str]) -> str` (concat ordonnée)
  - `merge_with_overrides(llm_sections: dict, overrides: dict) -> dict` (overrides écrasent — utilisé pour `take_selfy`).
- **Tests unitaires** dédiés : cas Aurore complet, cas fiche partielle, sections vides, ordre préservé.

**Critère de fin :** tests verts, helpers utilisables en isolation.

### Lot 3 — Stratégie Z-Image Turbo *(~1-2j, dépend du tuning modèle)*

**Objectif :** générer une PNG depuis un prompt markdown, en local, GPU.

- `simphonia/services/photo_service/strategies/z_image_turbo_strategy.py` :
  - Classe `ZImageTurboProvider` implémentant `PhotoProvider`.
  - Chargement modèle au `init()` (à challenger : lazy au 1er `generate()` si on veut accélérer le boot).
  - `generate(prompt: str, *, width: int, height: int, seed: int | None) -> bytes`
  - Gestion seed (`None`/`-1` → random via `torch.Generator`).
  - Device + dtype depuis config.
- Stratégie de service `PhotoServiceImpl(provider: PhotoProvider, ...)` qui wrappe le provider et porte la logique métier (parsing markdown, application du `subject_template`, etc.).
- **Smoke test manuel** (GPU requis) : `scripts/test_photo_generate.py` qui génère une photo d'Aurore et l'écrit dans `./tmp/aurore-test.png`. À valider visuellement avant de passer au Lot 4.

**Critère de fin :** PNG d'Aurore générée localement, qualité cohérente avec les exemples de référence.

### Lot 4 — Bus `photo` + persistance + commandes *(~1j)*

**Objectif :** service branché sur le bus, commandes MCP fonctionnelles, persistance OK.

- `simphonia/commands/photo.py` — `PHOTO_BUS = "photo"`, 4 commandes :
  - `@command(bus="photo", code="take_shoot", mcp=True)` — params `{markdown, from_char, session_id, activity_id?}`, retourne `{status: "queued", photo_id}`.
  - `@command(bus="photo", code="take_selfy", mcp=True)` — idem, déclenche l'override `style`+`sujet`.
  - `@command(bus="photo", code="publish")` — interne, émis depuis le worker quand l'image est prête.
  - `@command(bus="photo", code="get")` — interne, retourne `{photo_id, file_path, metadata}`.
- Mongo collection `photos` — méthodes `save_metadata(...)`, `update_status(...)`, `get(photo_id)`. Connexion `pymongo` (pattern existant), URI/DB partagées avec les autres services Mongo.
- Filesystem : `output_dir/<from_char>/<photo_id>.png`, création du sous-dossier `<from_char>` à la volée si absent.
- **Génération en background** : le handler de commande lance `asyncio.get_running_loop().run_in_executor(thread_pool, _generate_blocking, ...)`. Thread pool dédié au service (1-2 workers, sérialise les générations GPU pour éviter OOM). Une fois terminé : `bus("photo").dispatch("publish", {photo_id})`.

**Critère de fin :** `simcli photo take_selfy --from aurore --markdown "..."` retourne un `photo_id`, photo apparaît sur disque + Mongo qq secondes après, événement `publish` dispatché.

### Lot 5 — SSE + simweb (panneau « SMS reçu ») *(~1j)*

**Objectif :** la photo s'affiche dans simweb en push.

- **Choix SSE :** endpoint dédié `/bus/photo/stream/{session_id}` cohérent avec l'existant (`activity` et `chat` sont déjà séparés, multiplexage par type intra-canal pas en place).
- `simphonia/http/routes.py` — endpoint SSE photo.
- Listener bus `photo` (via `subscriptions: [photo]` côté SSE ou listener manuel) → `sse.publish(session_id, {"type": "photo.published", "photo_id": ..., "url": ...})`.
- Endpoint HTTP statique `GET /photos/{photo_id}` — renvoie le PNG (ACL minimale v1 : 200 si `from_char` correspond au joueur de la session, sinon 403).
- **simweb** :
  - `api/simphonia.js` — abonnement SSE photo.
  - Composant `PhotoMessage.jsx` — bulle « SMS reçu », `<img src="/photos/{photo_id}" />`.
  - Câblage dans `ChatScreen.jsx` (et/ou `ActivityDashboard.jsx` selon contexte d'usage).

**Critère de fin :** dans simweb, après que le LLM-joueur ait fait `take_selfy`, la photo s'affiche sans refresh.

### Dépendances entre lots

```
Lot 1 ─┬─→ Lot 3 ──→ Lot 4 ──→ Lot 5
       └─→ Lot 2 ───↗
```

Lot 2 indépendant de Lot 1 sur le code (helpers purs) mais doit être branché après. Lot 3 dépend de Lot 1 (config). Lot 4 dépend de Lot 2 + 3. Lot 5 dépend de Lot 4.

### Total estimé

**~4-5 jours d'implémentation v1.** Incertitude principale : Lot 3 (tuning device/dtype/steps Z-Image Turbo pour atteindre la qualité de référence).

### Réalisé — session 2026-04-26

Les 5 lots livrés en une session marathon (~10h), validation utilisateur sur la chaîne bout en bout. Voir l'entrée DONE consolidée dans [`../backlog.md`](../backlog.md).

Synthèse des écarts au plan initial :

- **Q1 partiellement révisé** : `diffusers` pipeline directe confirmée, mais `ZImagePipeline` n'est **pas dans la version PyPI stable** (uniquement git). Dépendance changée en `diffusers @ git+https://github.com/huggingface/diffusers.git`. Et bascule du `model_id` sur un **clone HF local** (`./models/Z-Image-Turbo`) car le réseau utilisateur (firewall/proxy MITM) bloquait l'accès `huggingface_hub` côté Python alors que le navigateur passait.
- **`steps=8` (pas 4)** : workflow ComfyUI de référence + recommandation officielle Z-Image. Le doc a été corrigé.
- **`guidance_scale=1.0` impératif** : ajouté en config (default 1.0). Le default `ZImagePipeline` est 5.0 — détruit la qualité pour un modèle distillé CFG-free. Diagnostic visuel : flou + yeux marron → après fix : netteté ComfyUI-équivalente, yeux verts, peau détaillée.
- **`shift=3.0`** : déjà natif dans le scheduler `FlowMatchEulerDiscreteScheduler` côté config modèle, donc le `ModelSamplingAuraFlow(shift=3)` ComfyUI est appliqué automatiquement par `diffusers`. Rien à câbler.
- **`cpu_offload: true`** ajouté en option config pour la cohabitation avec Ollama (32 GB VRAM 5090 partagés entre DiT Z-Image et LLM Ollama). Active `pipe.enable_model_cpu_offload()` — ~50 % VRAM en moins, ~30-50 % temps en plus.
- **Résolution path** : `model_id` et `output_dir` relatifs (`./models/...`, `./data/...`) résolus par rapport au dossier contenant `pyproject.toml`, pas au cwd Python (cwd dépend de l'IDE / uvicorn / scripts/...).
- **Bonus persistance `activity_runs`** : non prévu dans le plan initial mais ajouté à la demande de l'utilisateur en fin de session. Bridge `_photo_to_activity_runs` dans `engine.py` qui append `{_photo: true, ...}` dans `instance.exchanges[]` avec `current_round` enrichi. Au resume, les photos historiques remontent à leur position chronologique dans le flux `exchanges` (le rendu fait le dispatch `ex._photo` automatiquement). No-op silencieux si le `session_id` n'est pas un run connu (cas du chat).

Aucun écart n'a remis en cause les décisions de conception du cahier des charges.

"""Stratégie `z_image_turbo` — génération via la pipeline `diffusers.ZImagePipeline`.

Z-Image Turbo (Tongyi-MAI) est un DiT distillé qui produit des images en
8 NFE (steps) avec un text encoder Qwen 3 4B et un VAE de type Flux. Le
support `diffusers` n'est pas dans la version PyPI stable — il faut
`pip install git+https://github.com/huggingface/diffusers.git -U`.

Voir `documents/photo_service.md` pour le cahier des charges.
"""

from __future__ import annotations

import io
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simphonia.services.photo_service import PhotoService
from simphonia.services.photo_service.markdown_io import (
    merge_with_overrides,
    parse_sections,
    render_sections,
)
from simphonia.services.photo_service.subject_template import resolve_subject_template

log = logging.getLogger("simphonia.photo.z_image_turbo")


class ZImageTurboPhotoService(PhotoService):
    """Stratégie photo basée sur Z-Image Turbo (DiT 8-NFE, Qwen 3 4B, VAE Flux).

    **Lazy loading partout** :
      - La pipeline `diffusers` ne se charge qu'au premier `_generate_image()`.
      - Le client Mongo ne se connecte qu'au premier accès à la collection.
      - Le constructeur ne touche ni le GPU ni le réseau — `simphonia` peut
        démarrer même si torch/diffusers ne sont pas installés ou si Mongo
        est down (les erreurs surgissent à l'usage, pas au boot).

    **Mode async (Lot 4)** :
      - `take_shoot` / `take_selfy` insèrent immédiatement les métadonnées en
        Mongo en statut `"queued"` et retournent un ack `{status, photo_id}`
        sans attendre la génération.
      - Un `ThreadPoolExecutor` dédié exécute les générations en arrière-plan
        (1 worker par défaut pour sérialiser les accès GPU et éviter l'OOM).
      - Quand l'image est prête : statut `"completed"` + dispatch
        `photo/publish` sur le bus → consommé par les cascades + SSE simweb.
      - En cas d'échec : statut `"failed"` + champ `error` capturé.
    """

    def __init__(self, service_config: dict):
        # --- Config service-level ---
        # `output_dir` peut être relatif au projet (`./data/photo`) ou absolu.
        # On le résout par rapport à la racine projet, pas au cwd Python (qui
        # peut être `src/` ou autre selon le mode de lancement de simphonia).
        self._output_dir = Path(self._resolve_project_path(
            service_config.get("output_dir", "./data/photo")
        ))
        self._style_prefix: dict[str, str] = service_config.get("style_prefix", {}) or {}
        self._subject_template: str = service_config.get("subject_template", "") or ""

        # --- Config Mongo ---
        self._db_uri: str | None = service_config.get("database_uri")
        self._db_name: str | None = service_config.get("database_name")
        self._collection_name: str = service_config.get("collection", "photos")
        self._mongo_client: Any | None = None
        self._mongo_lock = threading.Lock()

        # --- Config strategy-level ---
        strategies = service_config.get("strategies", {}) or {}
        cfg = strategies.get("z_image_turbo", {}) or {}
        self._model_id: str = cfg.get("model_id", "Tongyi-MAI/Z-Image-Turbo")
        self._steps: int = int(cfg.get("steps", 8))
        self._width: int = int(cfg.get("width", 1024))
        self._height: int = int(cfg.get("height", 1024))
        self._seed: int | None = cfg.get("seed")  # peut être None ou -1 (random)
        self._device: str = cfg.get("device", "cuda")
        self._dtype_name: str = cfg.get("dtype", "bfloat16")
        # Z-Image Turbo est un modèle distillé CFG-free : guidance_scale=1.0
        # impératif (le default ZImagePipeline est 5.0 — détruit la qualité).
        # Cf. workflow ComfyUI de référence (KSampler.cfg=1).
        self._guidance_scale: float = float(cfg.get("guidance_scale", 1.0))
        # Active `pipe.enable_model_cpu_offload()` → modèle reste en RAM,
        # transfère par couches en VRAM à la volée. Conso VRAM divisée par
        # ~2-3 (utile quand un autre modèle — Ollama — campe en VRAM en
        # parallèle). Coût : génération ~30-50% plus lente.
        self._cpu_offload: bool = bool(cfg.get("cpu_offload", False))

        # --- État pipeline (lazy) ---
        self._pipeline: Any | None = None
        self._pipeline_lock = threading.Lock()

        # --- Background executor pour génération non bloquante ---
        # 1 worker par défaut : sérialise les accès GPU pour éviter l'OOM
        # (deux générations Z-Image en parallèle sur GPU consumer = crash).
        max_workers = int(cfg.get("max_concurrent_generations", 1))
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="photo-gen",
        )

        log.info(
            "ZImageTurboPhotoService initialized "
            "(model=%s, steps=%d, guidance=%.1f, max_workers=%d, lazy load)",
            self._model_id, self._steps, self._guidance_scale, max_workers,
        )

    # ------------------------------------------------------------------
    # Construction du prompt final (testable sans GPU)
    # ------------------------------------------------------------------

    def build_shoot_prompt(self, markdown: str) -> str:
        """Construit le prompt final pour `take_shoot`.

        Aucune section n'est imposée. Si le LLM omet `# style` et qu'un
        `style_prefix.take_shoot` est défini en config, il est injecté en
        fallback (sinon le markdown LLM est rendu tel quel).
        """
        sections = parse_sections(markdown)
        overrides: dict[str, str] = {}
        if "style" not in sections:
            fallback_style = self._style_prefix.get("take_shoot")
            if fallback_style:
                overrides["style"] = fallback_style
        merged = merge_with_overrides(sections, overrides)
        return render_sections(merged)

    def build_selfy_prompt(self, markdown: str, character: dict) -> str:
        """Construit le prompt final pour `take_selfy`.

        Les sections `# style` et `# sujet` sont **systématiquement** écrasées
        par le service :
        - `# style` ← `style_prefix.take_selfy` (config YAML)
        - `# sujet` ← `subject_template` résolu sur la fiche `character`
        """
        sections = parse_sections(markdown)
        overrides: dict[str, str] = {}
        style_prefix = self._style_prefix.get("take_selfy")
        if style_prefix:
            overrides["style"] = style_prefix
        if self._subject_template:
            sujet = resolve_subject_template(self._subject_template, character)
            if sujet:
                overrides["sujet"] = sujet
        merged = merge_with_overrides(sections, overrides)
        return render_sections(merged)

    # ------------------------------------------------------------------
    # Mongo — connexion lazy + persistance des métadonnées
    # ------------------------------------------------------------------

    def _get_collection(self) -> Any:
        """Lazy load du client Mongo. Lève si `database_uri` n'est pas configuré."""
        if not self._db_uri or not self._db_name:
            raise RuntimeError(
                "photo_service requires `database_uri` and `database_name` "
                "in config to persist photo metadata."
            )
        if self._mongo_client is not None:
            return self._mongo_client[self._db_name][self._collection_name]
        with self._mongo_lock:
            if self._mongo_client is not None:
                return self._mongo_client[self._db_name][self._collection_name]
            from pymongo import MongoClient
            self._mongo_client = MongoClient(self._db_uri)
            log.info(
                "Mongo connected for photos collection (%s.%s)",
                self._db_name, self._collection_name,
            )
            return self._mongo_client[self._db_name][self._collection_name]

    def _save_metadata_queued(
        self,
        *,
        photo_id: str,
        type_: str,
        from_char: str,
        session_id: str,
        activity_id: str | None,
        prompt_markdown: str,
        prompt_resolved: str,
    ) -> None:
        """Insère un doc en statut `queued` au moment de l'ack MCP."""
        doc = {
            "_id": photo_id,
            "photo_id": photo_id,
            "type": type_,
            "from_char": from_char,
            "timestamp": datetime.now(timezone.utc),
            "session_id": session_id,
            "activity_id": activity_id,
            "prompt_markdown": prompt_markdown,
            "prompt_resolved": prompt_resolved,
            "file_path": None,
            "width": self._width,
            "height": self._height,
            "model_used": "z_image_turbo",
            "seed": None if self._seed in (None, -1) else int(self._seed),
            "status": "queued",
        }
        self._get_collection().insert_one(doc)

    def _update_metadata_completed(self, photo_id: str, file_path: Path) -> None:
        self._get_collection().update_one(
            {"_id": photo_id},
            {"$set": {
                "status": "completed",
                "file_path": str(file_path),
                "completed_at": datetime.now(timezone.utc),
            }},
        )

    def _update_metadata_failed(self, photo_id: str, error: BaseException) -> None:
        self._get_collection().update_one(
            {"_id": photo_id},
            {"$set": {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "failed_at": datetime.now(timezone.utc),
            }},
        )

    # ------------------------------------------------------------------
    # Génération — lazy load de la pipeline diffusers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_project_path(path: str) -> str:
        """Si `path` est relatif (`./...`, `../...`), le résout par rapport à
        la **racine du projet** (dossier contenant `pyproject.toml`), pas par
        rapport au `cwd` Python — ce dernier dépend d'où simphonia est lancé
        (uvicorn, IDE, scripts/...).

        Pour un path absolu ou un identifiant non-path (repo HF `owner/name`),
        retourne tel quel.
        """
        if not path.startswith(("./", "../", ".\\", "..\\")):
            return path
        here = Path(__file__).resolve()
        for parent in [here, *here.parents]:
            if (parent / "pyproject.toml").exists():
                resolved = (parent / path).resolve()
                return str(resolved)
        # Fallback : pas de pyproject.toml trouvé — résolution cwd standard.
        return str(Path(path).resolve())

    # Alias rétro-compat pour la résolution `model_id` (peut être un path
    # local OU un repo HF — le helper générique gère les deux cas).
    _resolve_model_id = _resolve_project_path

    def _ensure_pipeline(self) -> Any:
        """Lazy loader thread-safe. Premier appel ≈ chargement modèle.
        Appels suivants : retour immédiat."""
        if self._pipeline is not None:
            return self._pipeline
        with self._pipeline_lock:
            if self._pipeline is not None:
                return self._pipeline
            resolved_model_id = self._resolve_model_id(self._model_id)
            log.info(
                "Loading Z-Image Turbo pipeline from %s (resolved: %s) on %s "
                "(first call — chargement initial)",
                self._model_id, resolved_model_id, self._device,
            )
            import torch  # imports lazy : pas tirés au boot simphonia
            from diffusers import ZImagePipeline

            dtype_map = {
                "bfloat16": torch.bfloat16,
                "float16": torch.float16,
                "fp16": torch.float16,
                "float32": torch.float32,
                "fp32": torch.float32,
            }
            dtype = dtype_map.get(self._dtype_name, torch.bfloat16)

            pipe = ZImagePipeline.from_pretrained(
                resolved_model_id,
                torch_dtype=dtype,
                low_cpu_mem_usage=False,
            )
            if self._cpu_offload:
                # `enable_model_cpu_offload` appelle `.to(device)` en interne —
                # ne pas le doubler.
                pipe.enable_model_cpu_offload()
                log.info(
                    "Z-Image Turbo pipeline ready (cpu_offload=ON, dtype=%s)",
                    self._dtype_name,
                )
            else:
                pipe = pipe.to(self._device)
                log.info(
                    "Z-Image Turbo pipeline ready on %s (dtype=%s)",
                    self._device, self._dtype_name,
                )
            self._pipeline = pipe
            return self._pipeline

    def _generate_image(self, prompt: str, *, seed: int | None = None) -> bytes:
        """Génère une image PNG en bytes à partir d'un prompt markdown.

        Si `seed` est `None` ou `-1`, une seed aléatoire est utilisée
        (générateur torch initialisé sans `manual_seed`). Sinon, la seed
        est appliquée pour reproductibilité.
        """
        pipe = self._ensure_pipeline()
        import torch

        generator = None
        effective_seed = seed if seed is not None else self._seed
        if effective_seed is not None and effective_seed != -1:
            generator = torch.Generator(device=self._device).manual_seed(int(effective_seed))

        result = pipe(
            prompt,
            num_inference_steps=self._steps,
            width=self._width,
            height=self._height,
            generator=generator,
            guidance_scale=self._guidance_scale,
        )
        image = result.images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Persistance filesystem
    # ------------------------------------------------------------------

    def _save_png(self, png_bytes: bytes, from_char: str, photo_id: str) -> Path:
        """Écrit le PNG dans `<output_dir>/<from_char>/<photo_id>.png`,
        crée le sous-dossier `<from_char>` si absent."""
        char_dir = self._output_dir / from_char
        char_dir.mkdir(parents=True, exist_ok=True)
        path = char_dir / f"{photo_id}.png"
        path.write_bytes(png_bytes)
        return path

    # ------------------------------------------------------------------
    # Worker background — exécuté par le ThreadPoolExecutor
    # ------------------------------------------------------------------

    def _generate_in_background(
        self,
        photo_id: str,
        prompt: str,
        from_char: str,
        session_id: str,
        type_: str,
    ) -> None:
        """Worker thread : génère l'image, persiste, dispatch `photo/publish`.

        Aucune exception ne remonte (le futur retourné par `executor.submit`
        n'est jamais consulté). Tout est loggué et reporté sur le doc Mongo.
        """
        try:
            png = self._generate_image(prompt)
            path = self._save_png(png, from_char, photo_id)
            self._update_metadata_completed(photo_id, path)
            log.info("Photo %s ready: %s", photo_id, path)

            # Dispatch publish sur le bus → réveille les listeners (SSE simweb,
            # cascades shadow_memory à venir, etc.). Payload enrichi avec
            # session_id (clé de routage SSE) + from_char + type + url servable.
            try:
                from simphonia.core import default_registry
                default_registry().get("photo").dispatch(
                    "publish",
                    {
                        "photo_id": photo_id,
                        "session_id": session_id,
                        "from_char": from_char,
                        "type": type_,
                        "url": f"/photos/{photo_id}",
                    },
                )
            except Exception as exc:
                log.warning(
                    "Photo %s generated but failed to dispatch photo/publish: %s",
                    photo_id, exc,
                )
        except Exception as exc:
            log.exception("Photo generation failed for %s", photo_id)
            try:
                self._update_metadata_failed(photo_id, exc)
            except Exception:
                log.exception("Also failed to mark photo %s as failed", photo_id)

    # ------------------------------------------------------------------
    # Implémentation ABC PhotoService — mode async (Lot 4)
    # ------------------------------------------------------------------

    def take_shoot(
        self,
        markdown: str,
        from_char: str,
        session_id: str,
        activity_id: str | None = None,
    ) -> dict:
        photo_id = str(uuid.uuid4())
        prompt = self.build_shoot_prompt(markdown)
        log.info("take_shoot from=%s photo_id=%s", from_char, photo_id)
        self._save_metadata_queued(
            photo_id=photo_id,
            type_="shoot",
            from_char=from_char,
            session_id=session_id,
            activity_id=activity_id,
            prompt_markdown=markdown,
            prompt_resolved=prompt,
        )
        self._executor.submit(
            self._generate_in_background, photo_id, prompt, from_char, session_id, "shoot",
        )
        return {"status": "queued", "photo_id": photo_id}

    def take_selfy(
        self,
        markdown: str,
        from_char: str,
        session_id: str,
        activity_id: str | None = None,
    ) -> dict:
        # Récupération de la fiche perso pour résoudre le subject_template.
        # Lazy import pour éviter dépendance circulaire et permettre les tests
        # avec une fiche injectée (cf. smoke test scripts/test_photo_generate.py
        # qui appelle build_selfy_prompt directement).
        from simphonia.services import character_service
        character = character_service.get().get_character(from_char)

        photo_id = str(uuid.uuid4())
        prompt = self.build_selfy_prompt(markdown, character)
        log.info("take_selfy from=%s photo_id=%s", from_char, photo_id)
        self._save_metadata_queued(
            photo_id=photo_id,
            type_="selfy",
            from_char=from_char,
            session_id=session_id,
            activity_id=activity_id,
            prompt_markdown=markdown,
            prompt_resolved=prompt,
        )
        self._executor.submit(
            self._generate_in_background, photo_id, prompt, from_char, session_id, "selfy",
        )
        return {"status": "queued", "photo_id": photo_id}

    def get_photo(self, photo_id: str) -> dict | None:
        """Retourne le doc Mongo de la photo (avec `file_path` résolu si
        statut `completed`), ou `None` si l'identifiant est inconnu.

        Les champs `datetime` sont sérialisés en `isoformat` pour rester
        JSON-friendly côté HTTP.
        """
        doc = self._get_collection().find_one({"_id": photo_id})
        if doc is None:
            return None
        for key in ("timestamp", "completed_at", "failed_at"):
            value = doc.get(key)
            if isinstance(value, datetime):
                doc[key] = value.isoformat()
        return doc

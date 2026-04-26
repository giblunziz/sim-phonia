"""Smoke test du Lot 3 — génère une photo d'Aurore.

Ce script est **volontairement autonome** : il n'instancie pas le bootstrap
simphonia ni `character_service` (donc pas de dépendance Mongo). La fiche
d'Aurore est fournie inline ; le service est instancié manuellement avec sa
config.

Pré-requis :
    - GPU CUDA disponible
    - `pip install -r requirements.txt` (tire diffusers from git, torch, etc.)
    - Le modèle Z-Image Turbo sera téléchargé depuis HF Hub au premier appel
      (~12 GB dans le cache HuggingFace)

Usage :
    python scripts/test_photo_generate.py

Sortie : `./tmp/photo-test/aurore/<uuid>.png`
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ajout du `src/` au path pour exécution sans `pip install -e .`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from simphonia.services.photo_service.strategies.z_image_turbo_strategy import (  # noqa: E402
    ZImageTurboPhotoService,
)


# ----------------------------------------------------------------------
# Config inline (équivalent à la section `services.photo` du YAML)
# ----------------------------------------------------------------------

SERVICE_CONFIG: dict = {
    "strategy": "z_image_turbo",
    "output_dir": "./tmp/photo-test",
    "style_prefix": {
        "take_shoot": "Photographie réaliste, cadrage soigné, lumière naturelle.",
        "take_selfy": (
            "Photo selfie réaliste, prise au smartphone, angle naturel."
        ),
    },
    "subject_template": (
        "{_id}, {gender} de {age} ans, {appearance.build}, "
        "yeux {appearance.eyes}, cheveux {appearance.hair}, "
        "accessoires {appearance.accessories}"
    ),
    "strategies": {
        "z_image_turbo": {
            # Path local du clone HF (cf. simphonia.yaml).
            # Bascule possible vers "Tongyi-MAI/Z-Image-Turbo" pour download
            # automatique si le réseau Python le permet.
            "model_id": "./models/Z-Image-Turbo",
            "steps": 8,
            "guidance_scale": 1.0,  # impératif : Z-Image Turbo est distillé CFG-free
            "width": 1024,
            "height": 1024,
            "seed": 42,  # reproductibilité du smoke test
            "device": "cuda",
            "dtype": "bfloat16",
        }
    },
}

# ----------------------------------------------------------------------
# Fiche Aurore (inline pour ne pas dépendre de Mongo)
# ----------------------------------------------------------------------

AURORE: dict = {
    "_id": "prisca",
    "gender": "femme européenne",
    "age": 23,
    "appearance": {
        "height": "~1m72",
        "hair": "Blond platine, longs, toujours parfaits. Brushing, extensions, jamais un cheveu qui dépasse. Coûte une fortune par mois. Non-négociable",
        "eyes": "Bleus, grands, avec des faux cils en permanence. Le regard de biche travaillé, perfectionné, instagrammable en toute circonstance",
        "build": "Corps de mannequin lingerie. Poitrine refaite (bien faite, subtile — pas le truc qui crie chirurgie). Taille fine, hanches marquées, fesses travaillées à la salle. Le corps est son outil de travail et elle l'entretient comme une athlète",
        "complexion": "Bronzage permanent, jamais naturel mais toujours impeccable. Peau lisse, zéro défaut visible — fond de teint, highlighter, le combo habituel. Sans maquillage elle est jolie. Avec, elle est une arme",
        "distinctive_features": "Lèvres légèrement refaites — pulpeuses, glossées en permanence. Un petit tatouage étoile derrière la cheville. Ongles toujours faits, longs, en amande, roses",
        "style": "Glamour assumé. Robes moulantes, talons, sacs griffés (ou très bonne copie). Bikinis minuscules sur l'île. Le genre de fille qui fait une entrée dans n'importe quelle pièce et que tout le monde regarde. Les hommes par désir. Les femmes par réflexe. Et Prisca par besoin."
    },

}

# ----------------------------------------------------------------------
# Markdown produit par le LLM (sections variables uniquement — style et
# sujet sont injectés par le service en mode `take_selfy`)
# ----------------------------------------------------------------------

LLM_MARKDOWN = """# tenue
veste noir.

# attitude
regard doux

# pose
allongée sur le dos dans un lit.

# ambiance
lumière douce et chaude, ombres douces"""


# ----------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------


def main() -> int:
    print("=" * 70)
    print("Smoke test photo_service — Z-Image Turbo")
    print("=" * 70)

    print("\n[1/4] Instanciation du service (lazy load — pas encore de GPU)...")
    service = ZImageTurboPhotoService(SERVICE_CONFIG)

    print("\n[2/4] Construction du prompt final pour `take_selfy`...")
    prompt = service.build_selfy_prompt(LLM_MARKDOWN, AURORE)
    print("-" * 70)
    print(prompt)
    print("-" * 70)

    print("\n[3/4] Génération de l'image (pipeline lazy load au 1er appel —")
    print("     premier run avec download HF peut prendre plusieurs minutes)...")
    t0 = time.monotonic()
    png = service._generate_image(prompt, seed=42)
    elapsed = time.monotonic() - t0
    print(f"     Génération terminée en {elapsed:.1f}s")
    print(f"     Taille PNG : {len(png) / 1024:.1f} KB")

    print("\n[4/4] Écriture sur disque...")
    out_dir = Path(SERVICE_CONFIG["output_dir"]) / "aurore"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "aurore-smoke.png"
    out.write_bytes(png)
    print(f"     Photo écrite : {out.resolve()}")

    print("\n✓ Smoke test OK — ouvre la photo et valide la qualité visuelle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

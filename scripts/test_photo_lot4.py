"""Smoke test du Lot 4 — chaîne complète async + Mongo + bus dispatch.

Ce script démarre `photo_service` avec sa vraie config YAML (donc Mongo
réel), s'abonne au bus `photo` pour observer l'événement `publish`, lance
un `take_selfy` pour Aurore, attend que la génération background termine,
et vérifie l'état final côté Mongo + filesystem.

Pré-requis :
    - GPU CUDA disponible
    - Mongo accessible (cf. ${MONGO_URI} dans .env)
    - Aurore présente dans `character_storage` (fiche Mongo) — sinon
      `take_selfy` échouera car le `subject_template` ne peut pas se résoudre.

Usage :
    python scripts/test_photo_lot4.py

Ce que ça vérifie :
    - L'ack synchrone `{status: queued, photo_id}` arrive en quelques ms
    - Le doc Mongo passe `queued` → `completed` (ou `failed`)
    - L'événement bus `photo.publish` est dispatché
    - Le PNG existe sur disque dans `./data/photo/aurore/<photo_id>.png`
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Charge .env AVANT toute lecture de config — le configuration_service applique
# `os.path.expandvars` au load YAML, donc les `${MONGO_URI}` etc. doivent être
# définis dans l'environnement à ce moment. C'est ce que fait `bootstrap.py`
# normalement ; ce script court-circuite le bootstrap, on doit le faire à la main.
from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from simphonia.core import default_registry  # noqa: E402
from simphonia.core.discovery import discover  # noqa: E402
from simphonia.services import (  # noqa: E402
    character_service,
    character_storage,
    configuration_service,
    photo_service,
)

XXX="""
# tenue
Un petit top en soie rose très mignon avec des bretelles fines en dentelle blanche.

# attitude
Solaire, un grand sourire, les yeux pétillants, un peu joueuse et affectueuse.

# pose
Assise sur son lit, légèrement penchée vers l'objectif comme pour un appel FaceTime, une main qui effleure sa joue.

# arriere_plan
Sa chambre aux tons rose et blanc, avec un éclairage doux et matinal.

# ambiance
Douceur du matin, intimité et tendresse."
"""

LLM_MARKDOWN = """# tenue
pull en laine épaisse gris clair.petite lunette se soleil ronde.

# attitude
regard direct, demi-sourire amusé.

# pose
debout, légèrement de profil, main passant dans les cheveux.

# arriere_plan
ruelle pavée, fin de journée, devanture de café floue derrière.

# ambiance
lumière dorée rasante, ambiance estivale chaleureuse."""


def main() -> int:
    print("=" * 70)
    print("Smoke test Lot 4 — async + Mongo + bus publish")
    print("=" * 70)

    # 1. Bootstrap minimal — config + storage + character_service + photo_service
    print("\n[1/6] Bootstrap minimal...")
    configuration_service.init()
    character_storage.init(configuration_service.section("services.character_storage"))
    discover("simphonia.commands")
    character_service.init(configuration_service.section("services.character_service"))
    photo_service.init(configuration_service.section("services.photo"))

    # 2. Subscribe au bus `photo` pour observer le publish
    publish_events: list[dict] = []
    def on_photo_publish(payload: dict) -> None:
        print(f"     [BUS] photo.publish reçu : {payload}")
        publish_events.append(payload)

    default_registry().get("photo").subscribe(on_photo_publish)
    print("     Listener `photo.publish` enregistré.")

    # 3. Vérifier qu'Aurore est en base
    print("\n[2/6] Vérification fiche Aurore...")
    try:
        aurore = character_service.get().get_character("aurore")
        print(f"     Aurore trouvée. _id={aurore.get('_id')}, age={aurore.get('age')}")
    except Exception as exc:
        print(f"     ✗ ERREUR : {exc}")
        print("     Aurore doit être présente dans `character_storage` Mongo.")
        return 1

    # 4. Lancer take_selfy (mode async — retour immédiat)
    print("\n[3/6] take_selfy (ack synchrone attendu)...")
    t0 = time.monotonic()
    ack = photo_service.get().take_selfy(
        markdown=XXX,
        from_char="prisca",
        session_id="smoke-test-lot4",
        activity_id=None,
    )
    ack_time = (time.monotonic() - t0) * 1000
    print(f"     Ack en {ack_time:.0f}ms : {ack}")
    photo_id = ack.get("photo_id")
    if not photo_id or ack.get("status") != "queued":
        print(f"     ✗ Ack inattendu : {ack}")
        return 2

    # 5. Vérifier le doc Mongo en statut queued
    print("\n[4/6] Vérification doc Mongo en statut `queued`...")
    doc = photo_service.get().get_photo(photo_id)
    if doc is None:
        print(f"     ✗ Doc Mongo absent pour photo_id={photo_id}")
        return 3
    print(f"     Doc Mongo OK. status={doc.get('status')}, type={doc.get('type')}, "
          f"prompt_resolved (50 chars): {doc.get('prompt_resolved', '')[:50]!r}...")

    # 6. Polling jusqu'à completion (max 60s)
    print("\n[5/6] Polling completion (max 60s)...")
    deadline = time.monotonic() + 60.0
    final_status = None
    while time.monotonic() < deadline:
        doc = photo_service.get().get_photo(photo_id)
        status = doc.get("status") if doc else None
        if status in ("completed", "failed"):
            final_status = status
            break
        time.sleep(0.5)

    elapsed = time.monotonic() - t0
    print(f"     Statut final : {final_status} (après {elapsed:.1f}s)")

    if final_status == "failed":
        print(f"     ✗ Échec génération : {doc.get('error')}")
        return 4
    if final_status != "completed":
        print(f"     ✗ Timeout — la photo n'est jamais passée à `completed`.")
        return 5

    # 7. Vérifier le fichier sur disque + l'événement publish
    print("\n[6/6] Vérifications finales...")
    file_path = doc.get("file_path")
    if not file_path or not Path(file_path).exists():
        print(f"     ✗ Fichier absent : {file_path}")
        return 6
    file_size_kb = Path(file_path).stat().st_size / 1024
    print(f"     ✓ Fichier OK : {file_path} ({file_size_kb:.1f} KB)")

    if not publish_events:
        print("     ✗ Événement `photo.publish` non reçu sur le bus.")
        return 7
    if not any(e.get("photo_id") == photo_id for e in publish_events):
        print(f"     ✗ Aucun publish event avec photo_id={photo_id}")
        return 8
    print(f"     ✓ Événement bus `photo.publish` reçu ({len(publish_events)} total).")

    print("\n" + "=" * 70)
    print(f"✓ Lot 4 smoke test OK — chaîne async + Mongo + bus opérationnelle.")
    print(f"  Photo : {file_path}")
    print(f"  photo_id : {photo_id}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
